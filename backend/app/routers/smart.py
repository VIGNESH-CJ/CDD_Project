"""Smart Food Intelligence endpoints.

The router keeps the product ideas visible as useful, auditable workflows.  It
uses deterministic signals from the application's own orders, menu, inventory
and delivery data; no customer data is sent to a third-party model.
"""

from datetime import timedelta, timezone
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field as SchemaField
from sqlmodel import Session, col, select

from app.algorithms.dietary_service import analyze_dish_dietary_safety, normalize_allergy_terms
from app.algorithms.smart_inventory import get_inventory_and_waste_analysis
from app.database import get_session
from app.models.cart import CartItem
from app.models.common import utc_isoformat, utc_now
from app.models.enums import OrderStatus, UserRole
from app.models.inventory import Ingredient
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem
from app.models.restaurant import Restaurant
from app.models.smart import (
    FoodRescueOffer,
    GroupOrder,
    GroupOrderItem,
    GroupOrderMember,
    OrderIntelligence,
    PersonalizationProfile,
    PostDeliveryFeedback,
)
from app.models.user import CustomerPreference, User
from app.models.waste import FoodWasteRecord
from app.services.auth_service import get_current_user, get_optional_user, require_role
from app.services.geo_service import assign_nearest_available_partner, haversine_distance_km
from app.services.access_control import get_restaurant_scope


router = APIRouter(prefix="/api/smart", tags=["Smart Food Intelligence"])

ACTIVE_ORDER_STATUSES = {
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.OUT_FOR_DELIVERY,
}


class PersonalizationUpdate(BaseModel):
    health_goal: Optional[str] = SchemaField(default=None, min_length=2, max_length=80)
    current_mood: Optional[str] = SchemaField(default=None, min_length=2, max_length=80)
    preferred_language: Optional[str] = SchemaField(default=None, min_length=2, max_length=40)
    max_meal_budget: Optional[float] = SchemaField(default=None, ge=0, le=100000)
    sustainability_priority: Optional[int] = SchemaField(default=None, ge=0, le=3)


class SafetyItem(BaseModel):
    menu_item_id: int = SchemaField(gt=0)
    quantity: int = SchemaField(default=1, ge=1, le=100)


class SafetyPreviewRequest(BaseModel):
    restaurant_id: int = SchemaField(gt=0)
    items: list[SafetyItem] = SchemaField(min_length=1, max_length=100)


class GroupOrderCreate(BaseModel):
    restaurant_id: int = SchemaField(gt=0)
    delivery_address: str = SchemaField(min_length=3, max_length=400)
    expires_in_minutes: int = SchemaField(default=90, ge=10, le=1440)


class GroupMemberCreate(BaseModel):
    display_name: str = SchemaField(min_length=1, max_length=100)


class GroupItemCreate(BaseModel):
    menu_item_id: int = SchemaField(gt=0)
    quantity: int = SchemaField(default=1, ge=1, le=100)
    notes: Optional[str] = SchemaField(default=None, max_length=200)


class RescueOfferCreate(BaseModel):
    restaurant_id: int = SchemaField(gt=0)
    title: str = SchemaField(min_length=2, max_length=150)
    description: str = SchemaField(default="Fresh surplus food", max_length=500)
    original_price: float = SchemaField(gt=0)
    rescue_price: float = SchemaField(gt=0)
    quantity_remaining: int = SchemaField(default=1, ge=1, le=1000)
    pickup_window_minutes: int = SchemaField(default=90, ge=10, le=1440)
    menu_item_id: Optional[int] = SchemaField(default=None, gt=0)


class FeedbackCreate(BaseModel):
    food_rating: int = SchemaField(ge=1, le=5)
    delivery_rating: int = SchemaField(ge=1, le=5)
    food_was_warm: Optional[bool] = None
    issue_type: Optional[str] = SchemaField(default=None, max_length=80)
    comment: Optional[str] = SchemaField(default=None, max_length=500)


class CopilotQuestion(BaseModel):
    question: str = SchemaField(min_length=3, max_length=500)


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_personalization(session: Session, user_id: int) -> PersonalizationProfile:
    profile = session.exec(
        select(PersonalizationProfile).where(PersonalizationProfile.user_id == user_id)
    ).first()
    if profile:
        return profile
    profile = PersonalizationProfile(user_id=user_id)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def _order_items(session: Session, order_id: int) -> list[OrderItem]:
    return session.exec(select(OrderItem).where(OrderItem.order_id == order_id)).all()


def _active_orders(session: Session, restaurant_id: int) -> list[Order]:
    return session.exec(
        select(Order).where(
            Order.restaurant_id == restaurant_id,
            col(Order.status).in_(list(ACTIVE_ORDER_STATUSES)),
        )
    ).all()


def _dish_confidence(session: Session, item: MenuItem) -> tuple[int, str]:
    """A transparent reliability score, not an opaque AI assertion."""
    active = len(_active_orders(session, item.restaurant_id))
    # Menu records may exist without recipes, so calculate a stable score from
    # facts always present in the menu and current kitchen queue.
    stock_penalty = 0
    score = round(min(5.0, max(0.0, item.rating)) * 15 + min(25, item.total_ratings // 4) + 20 - active * 2 - stock_penalty)
    score = max(35, min(98, score))
    if score >= 85:
        reason = "Strong recent ratings and a manageable kitchen queue"
    elif score >= 65:
        reason = "Reliable choice; kitchen workload may add some variability"
    else:
        reason = "Available, but the live kitchen queue may affect consistency"
    return score, reason


def _availability_forecast(session: Session, item: MenuItem) -> dict:
    active = len(_active_orders(session, item.restaurant_id))
    popularity = max(1, item.total_orders_count or 1)
    expected_portions = max(2, int(26 - active * 2 - min(12, popularity / 45)))
    state = "likely_available" if expected_portions > 7 else "limited"
    return {
        "state": state,
        "estimated_portions": expected_portions,
        "message": "Likely available for the next hour" if state == "likely_available" else "Limited portions likely during the current rush",
    }


def _restaurant_sustainability(session: Session, restaurant: Restaurant) -> dict:
    waste = session.exec(
        select(FoodWasteRecord).where(FoodWasteRecord.restaurant_id == restaurant.id)
    ).all()
    active_rescue = session.exec(
        select(FoodRescueOffer).where(
            FoodRescueOffer.restaurant_id == restaurant.id,
            FoodRescueOffer.is_active.is_(True),
            FoodRescueOffer.quantity_remaining > 0,
        )
    ).all()
    waste_loss = sum(record.estimated_loss_amount for record in waste)
    score = 54 + (14 if restaurant.is_pure_veg else 0) + min(18, len(active_rescue) * 6) - min(22, int(waste_loss / 300))
    score = max(10, min(100, score))
    return {
        "score": score,
        "grade": "A" if score >= 80 else "B" if score >= 65 else "C",
        "signals": {
            "pure_veg_kitchen": restaurant.is_pure_veg,
            "active_rescue_offers": len(active_rescue),
            "recorded_waste_loss": round(waste_loss, 2),
        },
        "explanation": "Score reflects vegetarian operations, active surplus-rescue offers, and recorded waste risk.",
    }


def _carbon_estimate(restaurant: Restaurant, latitude: float, longitude: float, item_count: int) -> dict:
    distance = haversine_distance_km(restaurant.latitude, restaurant.longitude, latitude, longitude)
    kg = round(0.18 + distance * 0.11 + max(1, item_count) * 0.04, 2)
    return {
        "distance_km": round(distance, 2),
        "estimated_carbon_kg": kg,
        "lower_carbon_tip": "Choose a grouped delivery window or a nearby rescue pickup when it is available.",
    }


def _order_risk(session: Session, order: Order) -> dict:
    active = len(_active_orders(session, order.restaurant_id))
    items = _order_items(session, order.id)
    age_minutes = max(0, int((utc_now() - _as_utc(order.created_at)).total_seconds() / 60))
    delay_risk = min(100, active * 9 + max(0, age_minutes - order.estimated_prep_minutes) * 2)
    quality_risk = min(100, int(order.estimated_delivery_minutes * 1.1) + max(0, active - 4) * 6 + max(0, len(items) - 3) * 4)
    predicted_delay = max(0, int((delay_risk - 35) / 7))
    action = "Monitor normally"
    if delay_risk >= 65:
        action = "Prioritize preparation and notify the customer with an updated ETA"
    elif quality_risk >= 65:
        action = "Confirm packaging and dispatch timing before handoff"
    return {
        "delay_risk": delay_risk,
        "quality_risk": quality_risk,
        "predicted_delay_minutes": predicted_delay,
        "recommended_action": action,
    }


def _save_order_intelligence(session: Session, order: Order, safety_summary: Optional[str] = None) -> OrderIntelligence:
    risk = _order_risk(session, order)
    restaurant = session.get(Restaurant, order.restaurant_id)
    carbon = _carbon_estimate(
        restaurant,
        order.delivery_latitude,
        order.delivery_longitude,
        len(_order_items(session, order.id)),
    )["estimated_carbon_kg"] if restaurant else 0.0
    record = session.exec(
        select(OrderIntelligence).where(OrderIntelligence.order_id == order.id)
    ).first()
    if not record:
        record = OrderIntelligence(order_id=order.id)
    record.delay_risk = risk["delay_risk"]
    record.quality_risk = risk["quality_risk"]
    record.predicted_delay_minutes = risk["predicted_delay_minutes"]
    record.carbon_kg = carbon
    record.recommended_action = risk["recommended_action"]
    if safety_summary:
        record.safety_summary = safety_summary
    record.updated_at = utc_now()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _get_owned_restaurant(session: Session, restaurant_id: int, current_user: User) -> Restaurant:
    get_restaurant_scope(session, current_user, restaurant_id)
    restaurant = session.get(Restaurant, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return restaurant


@router.get("/profile")
def get_personalization_profile(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _get_personalization(session, current_user.id)


@router.put("/profile")
def update_personalization_profile(
    payload: PersonalizationUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    profile = _get_personalization(session, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value.strip() if isinstance(value, str) else value)
    profile.updated_at = utc_now()
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.get("/recommendations")
def smart_recommendations(
    restaurant_id: Optional[int] = None,
    limit: int = Query(default=8, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Mood, health-goal, budget, confidence, and availability-aware picks."""
    profile = _get_personalization(session, current_user.id)
    diet = session.exec(select(CustomerPreference).where(CustomerPreference.user_id == current_user.id)).first()
    menu_query = select(MenuItem).where(MenuItem.is_available.is_(True))
    if restaurant_id:
        menu_query = menu_query.where(MenuItem.restaurant_id == restaurant_id)
    candidates = session.exec(menu_query).all()
    allergy_terms = normalize_allergy_terms(diet.allergy_info if diet else None)
    dietary_preference = diet.dietary_preference if diet else "Any"
    goal = profile.health_goal.casefold()
    mood = profile.current_mood.casefold()

    ranked = []
    for item in candidates:
        safety = analyze_dish_dietary_safety(item, dietary_preference, allergy_terms)
        if not safety["is_safe"]:
            continue
        price = item.discount_price or item.price
        score = item.rating * 16 + min(20, (item.total_orders_count or 0) / 12)
        reasons = [f"{item.rating:.1f} rated"]
        if profile.max_meal_budget and price <= profile.max_meal_budget:
            score += 15
            reasons.append("within your meal budget")
        if goal in {"weight loss", "light", "low calorie"} and (item.calories or 0) <= 450:
            score += 14
            reasons.append("a lighter calorie choice")
        if goal in {"muscle gain", "high protein", "fitness"} and any(term in (item.ingredients or "").casefold() for term in ("paneer", "chicken", "dal", "tofu", "egg")):
            score += 14
            reasons.append("contains protein-rich ingredients")
        if mood in {"tired", "comfort", "stressed"} and item.prep_time_minutes <= 20:
            score += 8
            reasons.append("quick to prepare for your current mood")
        confidence, confidence_reason = _dish_confidence(session, item)
        availability = _availability_forecast(session, item)
        score += confidence / 12
        ranked.append({
            "id": item.id,
            "restaurant_id": item.restaurant_id,
            "name": item.name,
            "description": item.description,
            "image_url": item.image_url,
            "price": price,
            "is_veg": item.is_veg,
            "calories": item.calories,
            "dietary_tags": item.dietary_tags,
            "explanation": "Recommended because it is " + ", ".join(reasons) + ".",
            "dish_confidence": confidence,
            "confidence_explanation": confidence_reason,
            "availability_forecast": availability,
            "safety": safety,
            "score": round(score, 1),
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {
        "profile": {"health_goal": profile.health_goal, "current_mood": profile.current_mood},
        "recommendations": ranked[:limit],
        "safety_note": "Allergy results use the restaurant-provided ingredient and allergen information; ask the kitchen about cross-contamination for severe allergies.",
    }


@router.post("/safety/checkout-preview")
def checkout_safety_preview(
    payload: SafetyPreviewRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Prevents unsafe checkout while allowing explicit acknowledgement of an omittable garnish."""
    preference = session.exec(
        select(CustomerPreference).where(CustomerPreference.user_id == current_user.id)
    ).first()
    allergens = normalize_allergy_terms(preference.allergy_info if preference else None)
    dietary = preference.dietary_preference if preference else "Any"
    blocked, acknowledgements = [], []
    for requested in payload.items:
        item = session.get(MenuItem, requested.menu_item_id)
        if not item or item.restaurant_id != payload.restaurant_id:
            raise HTTPException(status_code=400, detail="Cart contains an invalid menu item")
        safety = analyze_dish_dietary_safety(item, dietary, allergens)
        detail = {"menu_item_id": item.id, "name": item.name, "reason": safety["reason"], "allergens": safety["detected_allergens"]}
        if safety["status"] == "unsuitable":
            blocked.append(detail)
        elif safety["status"] == "customizable":
            acknowledgements.append({**detail, "instruction": safety["customization_note"]})
    return {
        "safe_to_continue": not blocked,
        "requires_acknowledgement": bool(acknowledgements),
        "blocked_items": blocked,
        "acknowledgements": acknowledgements,
        "message": "No preference conflict found" if not blocked and not acknowledgements else "Kitchen instructions are required for one or more selected dishes.",
    }


@router.get("/sustainability/restaurants/{restaurant_id}")
def restaurant_sustainability(restaurant_id: int, session: Session = Depends(get_session)):
    restaurant = session.get(Restaurant, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return _restaurant_sustainability(session, restaurant)


@router.get("/carbon/preview")
def carbon_preview(
    restaurant_id: int = Query(gt=0),
    latitude: float = Query(default=12.9716, ge=-90, le=90),
    longitude: float = Query(default=77.5946, ge=-180, le=180),
    item_count: int = Query(default=1, ge=1, le=100),
    session: Session = Depends(get_session),
):
    restaurant = session.get(Restaurant, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return _carbon_estimate(restaurant, latitude, longitude, item_count)


@router.post("/group-orders", status_code=status.HTTP_201_CREATED)
def create_group_order(
    payload: GroupOrderCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not session.get(Restaurant, payload.restaurant_id):
        raise HTTPException(status_code=404, detail="Restaurant not found")
    code = secrets.token_urlsafe(6).replace("-", "").replace("_", "").upper()[:10]
    group = GroupOrder(
        invite_code=code,
        host_user_id=current_user.id,
        restaurant_id=payload.restaurant_id,
        delivery_address=payload.delivery_address,
        expires_at=utc_now() + timedelta(minutes=payload.expires_in_minutes),
    )
    session.add(group)
    session.commit()
    session.refresh(group)
    host = GroupOrderMember(group_order_id=group.id, user_id=current_user.id, display_name=current_user.full_name)
    session.add(host)
    session.commit()
    return {"invite_code": group.invite_code, "group_order_id": group.id, "expires_at": utc_isoformat(group.expires_at)}


def _group_payload(session: Session, group: GroupOrder) -> dict:
    members = session.exec(select(GroupOrderMember).where(GroupOrderMember.group_order_id == group.id)).all()
    rows = session.exec(select(GroupOrderItem).where(GroupOrderItem.group_order_id == group.id)).all()
    member_names = {member.id: member.display_name for member in members}
    items = []
    total = 0.0
    for row in rows:
        item = session.get(MenuItem, row.menu_item_id)
        if not item:
            continue
        price = item.discount_price or item.price
        total += price * row.quantity
        items.append({
            "id": row.id, "menu_item_id": row.menu_item_id, "name": item.name, "quantity": row.quantity,
            "unit_price": price, "total_price": round(price * row.quantity, 2), "notes": row.notes,
            "added_by": member_names.get(row.member_id, "Guest"),
        })
    restaurant = session.get(Restaurant, group.restaurant_id)
    return {
        "id": group.id, "invite_code": group.invite_code, "restaurant_id": group.restaurant_id,
        "restaurant_name": restaurant.name if restaurant else "Restaurant", "delivery_address": group.delivery_address,
        "status": group.status, "expires_at": utc_isoformat(group.expires_at),
        "members": [{"id": m.id, "display_name": m.display_name} for m in members],
        "items": items, "subtotal": round(total, 2),
    }


@router.get("/group-orders/{invite_code}")
def get_group_order(invite_code: str, session: Session = Depends(get_session)):
    group = session.exec(select(GroupOrder).where(GroupOrder.invite_code == invite_code.upper())).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group order not found")
    if group.status == "open" and _as_utc(group.expires_at) <= utc_now():
        group.status = "expired"
        session.add(group)
        session.commit()
    return _group_payload(session, group)


@router.post("/group-orders/{invite_code}/members", status_code=status.HTTP_201_CREATED)
def join_group_order(
    invite_code: str,
    payload: GroupMemberCreate,
    current_user: Optional[User] = Depends(get_optional_user),
    session: Session = Depends(get_session),
):
    group = session.exec(select(GroupOrder).where(GroupOrder.invite_code == invite_code.upper())).first()
    if not group or group.status != "open" or _as_utc(group.expires_at) <= utc_now():
        raise HTTPException(status_code=409, detail="This group order is no longer open")
    if current_user:
        member = session.exec(select(GroupOrderMember).where(
            GroupOrderMember.group_order_id == group.id, GroupOrderMember.user_id == current_user.id,
        )).first()
        if member:
            return {"member_id": member.id, "message": "Already joined this group order"}
    member = GroupOrderMember(group_order_id=group.id, user_id=current_user.id if current_user else None, display_name=payload.display_name.strip())
    session.add(member)
    session.commit()
    session.refresh(member)
    return {"member_id": member.id, "message": "Joined group order"}


@router.post("/group-orders/{invite_code}/items", status_code=status.HTTP_201_CREATED)
def add_group_item(
    invite_code: str,
    payload: GroupItemCreate,
    member_id: int = Query(gt=0),
    session: Session = Depends(get_session),
):
    group = session.exec(select(GroupOrder).where(GroupOrder.invite_code == invite_code.upper())).first()
    member = session.get(GroupOrderMember, member_id)
    item = session.get(MenuItem, payload.menu_item_id)
    if not group or not member or member.group_order_id != group.id or group.status != "open":
        raise HTTPException(status_code=409, detail="This group order is not accepting items")
    if not item or item.restaurant_id != group.restaurant_id or not item.is_available:
        raise HTTPException(status_code=400, detail="Choose an available item from the group's restaurant")
    row = GroupOrderItem(group_order_id=group.id, member_id=member.id, menu_item_id=item.id, quantity=payload.quantity, notes=payload.notes)
    session.add(row)
    session.commit()
    return _group_payload(session, group)


@router.post("/group-orders/{invite_code}/transfer-to-cart")
def transfer_group_order_to_cart(
    invite_code: str,
    replace_cart: bool = False,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    group = session.exec(select(GroupOrder).where(GroupOrder.invite_code == invite_code.upper())).first()
    if not group or group.host_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the host can transfer this group order to checkout")
    if group.status != "open" or _as_utc(group.expires_at) <= utc_now():
        raise HTTPException(status_code=409, detail="This group order is no longer open")
    rows = session.exec(select(GroupOrderItem).where(GroupOrderItem.group_order_id == group.id)).all()
    if not rows:
        raise HTTPException(status_code=400, detail="Ask the group to add at least one dish first")
    existing = session.exec(select(CartItem).where(CartItem.customer_id == current_user.id)).all()
    has_other_restaurant = any(
        menu_item is not None and menu_item.restaurant_id != group.restaurant_id
        for row in existing
        for menu_item in [session.get(MenuItem, row.menu_item_id)]
    )
    if has_other_restaurant and not replace_cart:
        raise HTTPException(status_code=409, detail="Your cart has another restaurant. Set replace_cart=true to replace it.")
    if replace_cart:
        for row in existing:
            session.delete(row)
    for group_item in rows:
        cart = session.exec(select(CartItem).where(CartItem.customer_id == current_user.id, CartItem.menu_item_id == group_item.menu_item_id)).first()
        if cart:
            cart.quantity += group_item.quantity
            session.add(cart)
        else:
            session.add(CartItem(customer_id=current_user.id, menu_item_id=group_item.menu_item_id, quantity=group_item.quantity, created_at=utc_now(), updated_at=utc_now()))
    group.status = "ready_for_checkout"
    session.add(group)
    session.commit()
    return {"message": "Group items moved to the host's cart", "items_transferred": len(rows)}


def _rescue_payload(session: Session, offer: FoodRescueOffer) -> dict:
    restaurant = session.get(Restaurant, offer.restaurant_id)
    menu_item = session.get(MenuItem, offer.menu_item_id) if offer.menu_item_id else None
    return {
        "id": offer.id, "restaurant_id": offer.restaurant_id, "restaurant_name": restaurant.name if restaurant else "Restaurant",
        "title": offer.title, "description": offer.description, "original_price": offer.original_price,
        "rescue_price": offer.rescue_price, "savings": round(offer.original_price - offer.rescue_price, 2),
        "quantity_remaining": offer.quantity_remaining, "pickup_end": utc_isoformat(offer.pickup_end),
        "menu_item_id": offer.menu_item_id, "menu_item_name": menu_item.name if menu_item else None,
    }


@router.get("/rescue-offers")
def list_rescue_offers(session: Session = Depends(get_session)):
    now = utc_now()
    offers = session.exec(select(FoodRescueOffer).where(FoodRescueOffer.is_active.is_(True))).all()
    result = []
    for offer in offers:
        if offer.quantity_remaining <= 0 or _as_utc(offer.pickup_end) <= now:
            offer.is_active = False
            session.add(offer)
            continue
        result.append(_rescue_payload(session, offer))
    session.commit()
    return result


@router.post("/rescue-offers", status_code=status.HTTP_201_CREATED)
def create_rescue_offer(
    payload: RescueOfferCreate,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN])),
    session: Session = Depends(get_session),
):
    _get_owned_restaurant(session, payload.restaurant_id, current_user)
    if payload.rescue_price >= payload.original_price:
        raise HTTPException(status_code=400, detail="Rescue price must be lower than the original price")
    if payload.menu_item_id:
        item = session.get(MenuItem, payload.menu_item_id)
        if not item or item.restaurant_id != payload.restaurant_id:
            raise HTTPException(status_code=400, detail="Menu item must belong to this restaurant")
    offer = FoodRescueOffer(
        **payload.model_dump(exclude={"pickup_window_minutes"}),
        pickup_end=utc_now() + timedelta(minutes=payload.pickup_window_minutes),
    )
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return _rescue_payload(session, offer)


@router.post("/rescue-offers/{offer_id}/reserve")
def reserve_rescue_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    offer = session.get(FoodRescueOffer, offer_id)
    if not offer or not offer.is_active or offer.quantity_remaining <= 0 or _as_utc(offer.pickup_end) <= utc_now():
        raise HTTPException(status_code=409, detail="This rescue offer has ended")
    offer.quantity_remaining -= 1
    if offer.quantity_remaining == 0:
        offer.is_active = False
    session.add(offer)
    session.commit()
    return {"message": "Rescue meal reserved. Show this reservation at pickup.", "pickup_end": utc_isoformat(offer.pickup_end)}


@router.get("/orders/{order_id}/experience")
def get_order_experience(
    order_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    restaurant = session.get(Restaurant, order.restaurant_id)
    is_owner = order.customer_id == current_user.id
    is_staff = current_user.role in {UserRole.SUPER_ADMIN, UserRole.KITCHEN_STAFF} or (current_user.role == UserRole.RESTAURANT_ADMIN and restaurant and restaurant.owner_id == current_user.id)
    if not is_owner and not is_staff and order.delivery_partner_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this order")
    intelligence = _save_order_intelligence(session, order)
    elapsed = max(0, int((utc_now() - _as_utc(order.created_at)).total_seconds() / 60))
    prep_remaining = max(0, order.estimated_prep_minutes - elapsed)
    travel_minutes = max(5, order.estimated_delivery_minutes - order.estimated_prep_minutes)
    return {
        "order_id": order.id, "status": order.status.value,
        "eta_breakdown": {
            "kitchen_queue_minutes": max(0, len(_active_orders(session, order.restaurant_id)) * 3),
            "preparation_minutes_remaining": prep_remaining,
            "rider_assignment_minutes": 0 if order.delivery_partner_id else 5,
            "travel_minutes": travel_minutes,
            "estimated_total_minutes": max(0, prep_remaining + travel_minutes + (0 if order.delivery_partner_id else 5)),
        },
        "delay_risk": intelligence.delay_risk, "quality_risk": intelligence.quality_risk,
        "predicted_delay_minutes": intelligence.predicted_delay_minutes,
        "carbon_kg": intelligence.carbon_kg, "recommended_action": intelligence.recommended_action,
    }


@router.post("/orders/{order_id}/feedback", status_code=status.HTTP_201_CREATED)
def submit_delivery_feedback(
    order_id: int,
    payload: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = session.get(Order, order_id)
    if not order or order.customer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Your order was not found")
    if order.status != OrderStatus.DELIVERED:
        raise HTTPException(status_code=409, detail="Feedback is available after delivery")
    feedback = session.exec(select(PostDeliveryFeedback).where(PostDeliveryFeedback.order_id == order_id)).first()
    if feedback:
        raise HTTPException(status_code=409, detail="Feedback has already been submitted for this order")
    feedback = PostDeliveryFeedback(order_id=order_id, customer_id=current_user.id, **payload.model_dump())
    session.add(feedback)
    session.commit()
    return {"message": "Thank you. Your contextual feedback has been shared with the restaurant."}


@router.get("/food-memory")
def food_memory(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    orders = session.exec(select(Order).where(Order.customer_id == current_user.id).order_by(col(Order.created_at).desc())).all()
    dishes: dict[int, dict] = {}
    recent = []
    for order in orders:
        for line in _order_items(session, order.id):
            item = session.get(MenuItem, line.menu_item_id)
            dish = dishes.setdefault(line.menu_item_id, {"menu_item_id": line.menu_item_id, "name": line.item_name, "times_ordered": 0, "last_ordered": order.created_at, "is_available": bool(item and item.is_available)})
            dish["times_ordered"] += line.quantity
            if _as_utc(order.created_at) > _as_utc(dish["last_ordered"]):
                dish["last_ordered"] = order.created_at
        recent.append({"order_number": order.order_number, "created_at": utc_isoformat(order.created_at), "status": order.status.value})
    favorites = sorted(dishes.values(), key=lambda row: (row["times_ordered"], _as_utc(row["last_ordered"])), reverse=True)[:8]
    for dish in favorites:
        dish["last_ordered"] = utc_isoformat(dish["last_ordered"])
    return {"orders_count": len(orders), "favorite_dishes": favorites, "recent_orders": recent[:8]}


@router.get("/ops/restaurants/{restaurant_id}/kitchen-twin")
def kitchen_digital_twin(
    restaurant_id: int,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN, UserRole.KITCHEN_STAFF])),
    session: Session = Depends(get_session),
):
    _get_owned_restaurant(session, restaurant_id, current_user) if current_user.role != UserRole.KITCHEN_STAFF else None
    orders = _active_orders(session, restaurant_id)
    workload = sum(order.estimated_prep_minutes for order in orders if order.status != OrderStatus.OUT_FOR_DELIVERY)
    capacity = 6
    queue_pressure = round(min(100, len(orders) / capacity * 100))
    return {
        "restaurant_id": restaurant_id, "active_orders": len(orders), "parallel_station_capacity": capacity,
        "queue_pressure": queue_pressure, "estimated_workload_minutes": workload,
        "projected_clearance_minutes": max(0, round(workload / capacity)),
        "service_mode": "emergency" if queue_pressure >= 100 else "busy" if queue_pressure >= 67 else "normal",
        "recommendation": "Pause long-prep dishes and alert customers" if queue_pressure >= 100 else "Prioritize the oldest order" if queue_pressure >= 67 else "Capacity is healthy",
    }


@router.get("/ops/restaurants/{restaurant_id}/delay-alerts")
def order_delay_alerts(
    restaurant_id: int,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN, UserRole.KITCHEN_STAFF])),
    session: Session = Depends(get_session),
):
    _get_owned_restaurant(session, restaurant_id, current_user) if current_user.role != UserRole.KITCHEN_STAFF else None
    alerts = []
    for order in _active_orders(session, restaurant_id):
        risk = _order_risk(session, order)
        if risk["delay_risk"] >= 35 or risk["quality_risk"] >= 65:
            alerts.append({"order_id": order.id, "order_number": order.order_number, "status": order.status.value, **risk})
    return sorted(alerts, key=lambda alert: (alert["delay_risk"], alert["quality_risk"]), reverse=True)


@router.post("/ops/orders/{order_id}/dynamic-handoff")
def dynamic_delivery_handoff(
    order_id: int,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN, UserRole.KITCHEN_STAFF])),
    session: Session = Depends(get_session),
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    _get_owned_restaurant(session, order.restaurant_id, current_user) if current_user.role != UserRole.KITCHEN_STAFF else None
    if order.status not in {OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY}:
        raise HTTPException(status_code=409, detail="Only an active kitchen order can be reassigned")
    restaurant = session.get(Restaurant, order.restaurant_id)
    partner = assign_nearest_available_partner(session, order, restaurant.latitude, restaurant.longitude)
    if not partner:
        raise HTTPException(status_code=409, detail="No eligible delivery partner is currently available")
    previous = order.delivery_partner_id
    order.delivery_partner_id = partner.id
    session.add(order)
    intel = _save_order_intelligence(session, order)
    intel.handoff_count += 1
    intel.recommended_action = "Rider reassigned using current distance and workload"
    session.add(intel)
    session.commit()
    return {"message": "Delivery handoff updated", "previous_partner_id": previous, "new_partner_id": partner.id, "new_partner_name": partner.full_name}


@router.get("/ops/restaurants/{restaurant_id}/menu-engineering")
def menu_engineering(
    restaurant_id: int,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN])),
    session: Session = Depends(get_session),
):
    _get_owned_restaurant(session, restaurant_id, current_user)
    items = session.exec(select(MenuItem).where(MenuItem.restaurant_id == restaurant_id)).all()
    active = len(_active_orders(session, restaurant_id))
    output = []
    for item in items:
        demand = item.total_orders_count or 0
        action = "Maintain"
        reason = "Balanced demand and customer rating"
        if demand >= 120 and item.prep_time_minutes <= 20:
            action, reason = "Feature in today’s special", "High historical demand with fast preparation"
        elif item.rating < 3.8:
            action, reason = "Review recipe or presentation", "Rating is below the menu quality threshold"
        elif active >= 8 and item.prep_time_minutes >= 30:
            action, reason = "Temporarily de-prioritize", "Long preparation during a live kitchen rush"
        output.append({"menu_item_id": item.id, "name": item.name, "action": action, "reason": reason, "rating": item.rating, "historical_orders": demand})
    return sorted(output, key=lambda row: (row["action"] != "Feature in today’s special", -row["historical_orders"]))


@router.get("/ops/restaurants/{restaurant_id}/procurement")
def procurement_recommendations(
    restaurant_id: int,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN])),
    session: Session = Depends(get_session),
):
    _get_owned_restaurant(session, restaurant_id, current_user)
    inventory = get_inventory_and_waste_analysis(session, restaurant_id)
    recommendations = []
    for item in inventory["inventory_items"]:
        if item["is_low_stock"]:
            target = max(item["reorder_level"] * 2.5, item["reorder_level"] + 1)
            recommendations.append({"ingredient_id": item["id"], "ingredient": item["name"], "recommended_quantity": round(target - item["current_stock"], 2), "unit": item["unit"], "reason": "Below reorder threshold"})
        elif item["days_remaining"] is not None and item["days_remaining"] <= 2:
            recommendations.append({"ingredient_id": item["id"], "ingredient": item["name"], "recommended_quantity": 0, "unit": item["unit"], "reason": "Near expiry: promote dishes using this ingredient instead of buying more"})
    return {"recommendations": recommendations, "inventory_value": inventory["total_inventory_value"]}


@router.post("/ops/restaurants/{restaurant_id}/copilot")
def restaurant_operations_copilot(
    restaurant_id: int,
    payload: CopilotQuestion,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN])),
    session: Session = Depends(get_session),
):
    """A grounded, deterministic copilot; its answer names the live evidence used."""
    _get_owned_restaurant(session, restaurant_id, current_user)
    question = payload.question.casefold()
    twin = {"active_orders": len(_active_orders(session, restaurant_id))}
    inventory = get_inventory_and_waste_analysis(session, restaurant_id)
    if any(word in question for word in ("late", "delay", "slow")):
        alerts = [a for a in [ _order_risk(session, order) for order in _active_orders(session, restaurant_id)] if a["delay_risk"] >= 35]
        answer = f"{len(alerts)} active order(s) need delay monitoring. Start with the oldest pending or preparing order and publish a revised ETA when risk is high."
        evidence = {"active_orders": twin["active_orders"], "orders_at_risk": len(alerts)}
    elif any(word in question for word in ("waste", "expiry", "ingredient", "stock")):
        answer = f"There are {inventory['low_stock_alerts_count']} low-stock item(s) and {inventory['expiry_warnings_count']} near-expiry item(s). Reorder only low-stock staples; feature near-expiry ingredients in a time-boxed special."
        evidence = {"low_stock": inventory["low_stock_alerts_count"], "near_expiry": inventory["expiry_warnings_count"]}
    elif any(word in question for word in ("menu", "dish", "promote", "sell")):
        engineering = menu_engineering(restaurant_id, current_user, session)
        featured = [item["name"] for item in engineering if item["action"] == "Feature in today’s special"][:3]
        answer = "Promote " + (", ".join(featured) if featured else "your best-rated fast-prep dishes") + "; they balance demand with kitchen capacity."
        evidence = {"featured_candidates": featured, "active_orders": twin["active_orders"]}
    else:
        answer = f"The restaurant currently has {twin['active_orders']} active order(s), {inventory['low_stock_alerts_count']} low-stock item(s), and {inventory['expiry_warnings_count']} near-expiry item(s). Ask about delays, waste, stock, or menu performance for a focused recommendation."
        evidence = {"active_orders": twin["active_orders"], "low_stock": inventory["low_stock_alerts_count"], "near_expiry": inventory["expiry_warnings_count"]}
    return {"answer": answer, "evidence": evidence, "grounding": "Computed from this restaurant's live orders and inventory records."}
