import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, col

from app.database import get_session
from app.models.user import User
from app.models.restaurant import Restaurant
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem, OrderStatusHistory, Payment
from app.models.cart import CartItem
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus, UserRole
from app.models.common import utc_now, utc_isoformat
from app.schemas.order import OrderCreate, OrderStatusUpdate
from app.services.auth_service import get_current_user, require_role
from app.websocket.manager import manager
from app.algorithms.kitchen_priority import calculate_kitchen_priority_score
from app.algorithms.delivery_dispatch import haversine_distance_km
from app.services.geo_service import assign_nearest_available_partner, calculate_eta_minutes
from app.algorithms.smart_inventory import deduct_inventory_for_order
from app.services.access_control import get_restaurant_scope
from app.services.payment_service import verify_payment

router = APIRouter(prefix="/api/orders", tags=["Orders"])

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    order_in: OrderCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if not order_in.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one food item")

    restaurant = session.exec(
        select(Restaurant).where(Restaurant.id == order_in.restaurant_id)
    ).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    # 1. Calculate pricing
    subtotal = 0.0
    order_items_to_create = []
    max_prep_time = 15

    for item_input in order_in.items:
        menu_item = session.exec(
            select(MenuItem).where(MenuItem.id == item_input.menu_item_id)
        ).first()
        if not menu_item or not menu_item.is_available:
            raise HTTPException(
                status_code=400,
                detail=f"Item {item_input.menu_item_id} is unavailable"
            )
        if menu_item.restaurant_id != restaurant.id:
            raise HTTPException(
                status_code=400,
                detail="All order items must belong to the selected restaurant"
            )

        item_unit_price = menu_item.discount_price or menu_item.price
        line_total = item_unit_price * item_input.quantity
        subtotal += line_total
        max_prep_time = max(max_prep_time, menu_item.prep_time_minutes)

        order_items_to_create.append({
            "menu_item_id": menu_item.id,
            "item_name": menu_item.name,
            "quantity": item_input.quantity,
            "unit_price": item_unit_price,
            "total_price": line_total,
            "special_instructions": item_input.special_instructions
        })

    # Taxes & Discounts
    tax = round(subtotal * 0.05, 2)
    delivery_fee = 30.0

    discount = 0.0
    if order_in.coupon_code:
        coupon = order_in.coupon_code.strip().upper()
        if coupon == "AIFOODIE20" and subtotal >= 199:
            discount = min(round(subtotal * 0.20, 2), 100.0)
        elif coupon == "WELCOME50" and subtotal >= 149:
            discount = 50.0
        elif coupon == "FEAST10" and subtotal >= 299:
            discount = min(round(subtotal * 0.10, 2), 200.0)
        elif coupon == "DEMO100" and subtotal >= 300:
            discount = 100.0
        else:
            raise HTTPException(
                status_code=400,
                detail="Coupon is invalid or the order does not meet its minimum subtotal."
            )

    total_amount = max(0.0, round(subtotal + tax + delivery_fee - discount, 2))

    # Payment Status Verification (COD vs Sandbox Online)
    payment_status = PaymentStatus.PENDING
    transaction_id = None
    if order_in.payment_method == PaymentMethod.COD:
        payment_status = PaymentStatus.PENDING
        transaction_id = f"COD-{uuid.uuid4().hex[:8].upper()}"
    else:
        if not verify_payment(order_in.payment_reference):
            raise HTTPException(
                status_code=402,
                detail="Online payment has not been confirmed. Complete the checkout and retry.",
            )
        payment_status = PaymentStatus.SUCCESS
        transaction_id = order_in.payment_reference

    # 2. Assign Delivery Partner and calculate ETA
    assigned_driver_id = None
    
    distance_km = haversine_distance_km(
        restaurant.latitude,
        restaurant.longitude,
        order_in.delivery_latitude or 12.9716,
        order_in.delivery_longitude or 77.5946
    )
    eta_mins = calculate_eta_minutes(distance_km, max_prep_time)

    # 3. Create Order
    order_num = f"ORD-{utc_now().year}-{uuid.uuid4().hex[:6].upper()}"
    new_order = Order(
        order_number=order_num,
        customer_id=current_user.id,
        restaurant_id=restaurant.id,
        delivery_partner_id=assigned_driver_id,
        status=OrderStatus.PENDING,
        subtotal=round(subtotal, 2),
        delivery_fee=delivery_fee,
        tax=tax,
        discount=discount,
        total_amount=total_amount,
        coupon_code=order_in.coupon_code,
        payment_method=order_in.payment_method,
        payment_status=payment_status,
        transaction_id=transaction_id,
        delivery_address=order_in.delivery_address,
        delivery_latitude=order_in.delivery_latitude or 12.9716,
        delivery_longitude=order_in.delivery_longitude or 77.5946,
        customer_notes=order_in.customer_notes,
        estimated_prep_minutes=max_prep_time,
        estimated_delivery_minutes=eta_mins,
        priority_score=1.0,
        created_at=utc_now(),
        updated_at=utc_now()
    )
    session.add(new_order)
    session.commit()
    session.refresh(new_order)

    # 4. Save items & initial status history
    created_items = []
    for item_data in order_items_to_create:
        oi = OrderItem(
            order_id=new_order.id,
            menu_item_id=item_data["menu_item_id"],
            item_name=item_data["item_name"],
            quantity=item_data["quantity"],
            unit_price=item_data["unit_price"],
            total_price=item_data["total_price"],
            special_instructions=item_data["special_instructions"]
        )
        session.add(oi)
        created_items.append(oi)

    # Initial status history
    status_history = OrderStatusHistory(
        order_id=new_order.id,
        status=OrderStatus.PENDING,
        notes="Order placed by customer via AI Foodie",
        changed_by_role="customer",
        timestamp=utc_now()
    )
    session.add(status_history)

    # Payment log
    payment = Payment(
        order_id=new_order.id,
        payment_method=order_in.payment_method,
        amount=total_amount,
        status=payment_status,
        transaction_ref=transaction_id,
        gateway_response=(
            "Verified payment reference"
            if payment_status == PaymentStatus.SUCCESS
            else "Awaiting COD Collection"
        ),
        created_at=utc_now()
    )
    session.add(payment)

    # Calculate initial kitchen priority score
    new_order.priority_score = calculate_kitchen_priority_score(new_order, 0.0)
    session.add(new_order)

    # Deduct inventory stock automatically
    inventory_alerts = deduct_inventory_for_order(session, restaurant.id, new_order.id, created_items)

    # Clear customer cart
    cart_items = session.exec(select(CartItem).where(CartItem.customer_id == current_user.id)).all()
    for ci in cart_items:
        session.delete(ci)

    # Award loyalty points
    points_earned = int(total_amount // 20)
    current_user.loyalty_points += points_earned
    session.add(current_user)

    session.commit()
    session.refresh(new_order)

    # Broadcast real-time event through WebSocket
    ws_event = {
        "event": "NEW_ORDER",
        "order_id": new_order.id,
        "order_number": new_order.order_number,
        "restaurant_name": restaurant.name,
        "total_amount": new_order.total_amount,
        "status": new_order.status.value,
        "priority_score": new_order.priority_score,
        "items_count": len(created_items),
        "inventory_alerts": inventory_alerts
    }
    await manager.broadcast(
        ws_event,
        restaurant_id=restaurant.id,
        user_ids=[current_user.id, new_order.delivery_partner_id],
    )

    return {
        "success": True,
        "order_id": new_order.id,
        "order_number": new_order.order_number,
        "status": new_order.status.value,
        "total_amount": new_order.total_amount,
        "estimated_delivery_minutes": new_order.estimated_delivery_minutes,
        "points_earned": points_earned,
        "inventory_alerts": inventory_alerts
    }

@router.get("/my-orders")
def get_my_orders(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    orders = session.exec(
        select(Order)
        .where(Order.customer_id == current_user.id)
        .order_by(col(Order.created_at).desc())
    ).all()

    result = []
    for o in orders:
        items = session.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all()
        rest = session.exec(select(Restaurant).where(Restaurant.id == o.restaurant_id)).first()
        result.append({
            "id": o.id,
            "order_number": o.order_number,
            "restaurant_name": rest.name if rest else "AI Foodie Partner",
            "restaurant_image": rest.image_url if rest else "",
            "status": o.status.value,
            "total_amount": o.total_amount,
            "created_at": utc_isoformat(o.created_at),
            "items_count": len(items),
            "items_summary": ", ".join(f"{i.quantity}x {i.item_name}" for i in items[:3]),
            "delivery_address": o.delivery_address
        })
    return result

@router.get("/{order_id}")
def get_order_details(
    order_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    restaurant = session.exec(select(Restaurant).where(Restaurant.id == order.restaurant_id)).first()
    can_view = (
        order.customer_id == current_user.id
        or order.delivery_partner_id == current_user.id
        or current_user.role in (UserRole.KITCHEN_STAFF, UserRole.SUPER_ADMIN)
        or (
            current_user.role == UserRole.RESTAURANT_ADMIN
            and restaurant is not None
            and restaurant.owner_id == current_user.id
        )
    )
    if not can_view:
        raise HTTPException(status_code=403, detail="You do not have access to this order")

    items = session.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    history = session.exec(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order.id)
        .order_by(col(OrderStatusHistory.timestamp).asc())
    ).all()
    driver = session.exec(select(User).where(User.id == order.delivery_partner_id)).first() if order.delivery_partner_id else None

    return {
        "order": order,
        "items": items,
        "history": history,
        "restaurant": restaurant,
        "delivery_partner": {
            "name": driver.full_name if driver else "AI Express Delivery",
            "phone": driver.phone if driver else "+91 98765 12345"
        } if driver else None
    }

@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: int,
    status_update: OrderStatusUpdate,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN])),
    session: Session = Depends(get_session)
):
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    get_restaurant_scope(session, current_user, order.restaurant_id)
    allowed_transitions = {
        OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
        OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
        OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
        OrderStatus.READY: {OrderStatus.CANCELLED},
    }
    if status_update.status not in allowed_transitions.get(order.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change order from {order.status.value} to {status_update.status.value}",
        )

    order.status = status_update.status
    if status_update.status == OrderStatus.CONFIRMED and not order.delivery_partner_id:
        restaurant = session.get(Restaurant, order.restaurant_id)
        if restaurant:
            partner = assign_nearest_available_partner(session, order, restaurant.latitude, restaurant.longitude)
            if partner:
                order.delivery_partner_id = partner.id
    order.updated_at = utc_now()
    session.add(order)

    history = OrderStatusHistory(
        order_id=order.id,
        status=status_update.status,
        notes=status_update.notes or f"Status transitioned to {status_update.status.value}",
        changed_by_role=current_user.role.value,
        timestamp=utc_now()
    )
    session.add(history)
    session.commit()

    # Broadcast update across WebSockets
    await manager.broadcast(
        {
            "event": "ORDER_STATUS_CHANGED",
            "order_id": order.id,
            "order_number": order.order_number,
            "new_status": order.status.value,
            "notes": status_update.notes,
        },
        restaurant_id=order.restaurant_id,
        user_ids=[order.customer_id, order.delivery_partner_id],
    )

    return {"message": f"Order status updated to {order.status.value}"}

@router.post("/{order_id}/reorder")
def reorder_items(
    order_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    past_items = session.exec(select(OrderItem).where(OrderItem.order_id == order_id)).all()
    if not past_items:
        raise HTTPException(status_code=404, detail="Order items not found")

    past_order = session.get(Order, order_id)
    if not past_order or past_order.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only reorder your own orders")

    existing_cart = session.exec(select(CartItem).where(CartItem.customer_id == current_user.id)).all()
    for cart_item in existing_cart:
        cart_menu_item = session.get(MenuItem, cart_item.menu_item_id)
        if cart_menu_item and cart_menu_item.restaurant_id != past_order.restaurant_id:
            raise HTTPException(status_code=400, detail="Clear your cart before reordering from another restaurant")

    added_count = 0
    for pi in past_items:
        menu_item = session.exec(select(MenuItem).where(MenuItem.id == pi.menu_item_id)).first()
        if menu_item and menu_item.is_available:
            ci = CartItem(
                customer_id=current_user.id,
                menu_item_id=menu_item.id,
                quantity=pi.quantity,
                created_at=utc_now(),
                updated_at=utc_now()
            )
            session.add(ci)
            added_count += 1

    session.commit()
    return {"message": f"{added_count} items added to your cart for reordering!"}
