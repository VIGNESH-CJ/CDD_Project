from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, col

from app.database import get_session
from app.models.user import User
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.restaurant import Restaurant
from app.models.delivery import DeliveryProfile, DeliveryAssignment
from app.models.enums import OrderStatus, UserRole
from app.models.common import utc_now, utc_isoformat
from app.services.auth_service import require_role
from app.websocket.manager import manager
from app.algorithms.kitchen_priority import sort_kitchen_queue
from app.services.geo_service import assign_nearest_available_partner

router = APIRouter(prefix="/api/kitchen", tags=["Kitchen Display System"])

@router.get("/delivery-partners")
def get_kitchen_delivery_partners(
    current_user: User = Depends(require_role([
        UserRole.KITCHEN_STAFF,
        UserRole.RESTAURANT_ADMIN,
        UserRole.SUPER_ADMIN,
    ])),
    session: Session = Depends(get_session)
):
    """
    Returns available delivery partners so kitchen staff can choose
    which rider to hand over ready orders to.
    """
    partners = session.exec(
        select(User).where(User.role == UserRole.DELIVERY_PARTNER, User.is_active == True)
    ).all()

    results = []
    for p in partners:
        profile = session.exec(select(DeliveryProfile).where(DeliveryProfile.user_id == p.id)).first()
        active_orders = session.exec(
            select(Order).where(
                Order.delivery_partner_id == p.id,
                col(Order.status).in_([
                    OrderStatus.CONFIRMED,
                    OrderStatus.PREPARING,
                    OrderStatus.READY,
                    OrderStatus.OUT_FOR_DELIVERY,
                ])
            )
        ).all()
        results.append({
            "id": p.id,
            "full_name": p.full_name,
            "email": p.email,
            "phone": p.phone or "N/A",
            "vehicle_type": profile.vehicle_type if profile else "Motorcycle",
            "vehicle_number": profile.vehicle_number if profile else "N/A",
            "is_available": profile.is_available if profile else True,
            "rating": profile.rating if profile else 4.8,
            "active_orders_count": len(active_orders)
        })
    return results

@router.get("/queue")
def get_kitchen_queue(
    restaurant_id: Optional[int] = None,
    include_completed: bool = False,
    current_user: User = Depends(require_role([
        UserRole.KITCHEN_STAFF,
        UserRole.RESTAURANT_ADMIN,
        UserRole.SUPER_ADMIN,
    ])),
    session: Session = Depends(get_session)
):
    active_statuses = [
        OrderStatus.PENDING,
        OrderStatus.CONFIRMED,
        OrderStatus.PREPARING,
        OrderStatus.READY
    ]
    query_statuses = active_statuses + ([OrderStatus.DELIVERED] if include_completed else [])
    query = select(Order).where(col(Order.status).in_(query_statuses))
    if current_user.role == UserRole.RESTAURANT_ADMIN:
        managed_restaurants = session.exec(
            select(Restaurant.id).where(Restaurant.owner_id == current_user.id)
        ).all()
        if restaurant_id is not None and restaurant_id not in managed_restaurants:
            raise HTTPException(status_code=403, detail="You can only view orders for your own restaurants")
        if restaurant_id is not None:
            query = query.where(Order.restaurant_id == restaurant_id)
        else:
            query = query.where(col(Order.restaurant_id).in_(managed_restaurants))
    elif restaurant_id is not None:
        query = query.where(Order.restaurant_id == restaurant_id)

    orders = session.exec(query).all()
    if include_completed:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        orders = [
            order for order in orders
            if order.status != OrderStatus.DELIVERED
            or (order.updated_at.replace(tzinfo=timezone.utc) if order.updated_at.tzinfo is None else order.updated_at) >= cutoff
        ]
    ranked_list = sort_kitchen_queue(orders)

    formatted_queue = []
    for entry in ranked_list:
        o = entry["order"]
        items = session.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all()
        dp_user = session.get(User, o.delivery_partner_id) if o.delivery_partner_id else None
        
        formatted_queue.append({
            "order_id": o.id,
            "order_number": o.order_number,
            "status": o.status.value,
            "delivery_partner_id": o.delivery_partner_id,
            "delivery_partner_name": dp_user.full_name if dp_user else None,
            "priority_score": entry["priority_score"],
            "urgency": entry["urgency"],
            "badge_color": entry["badge_color"],
            "elapsed_minutes": entry["elapsed_minutes"],
            "is_delayed": entry["is_delayed"],
            "estimated_prep_minutes": o.estimated_prep_minutes,
            "items_count": len(items),
            "customer_notes": o.customer_notes,
            "items": [
                {
                    "item_name": item.item_name,
                    "quantity": item.quantity,
                    "special_instructions": item.special_instructions
                }
                for item in items
            ],
            "created_at": utc_isoformat(o.created_at)
        })

    return formatted_queue

@router.post("/orders/{order_id}/action")
async def update_kitchen_order_status(
    order_id: int,
    action: str,
    delivery_partner_id: Optional[int] = None,
    current_user: User = Depends(require_role([
        UserRole.KITCHEN_STAFF,
        UserRole.RESTAURANT_ADMIN,
        UserRole.SUPER_ADMIN,
    ])),
    session: Session = Depends(get_session)
):
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if current_user.role == UserRole.RESTAURANT_ADMIN:
        restaurant = session.get(Restaurant, order.restaurant_id)
        if not restaurant or restaurant.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only update orders for your own restaurants")

    action_map = {
        "accept": (OrderStatus.PENDING, OrderStatus.CONFIRMED),
        "prepare": (OrderStatus.CONFIRMED, OrderStatus.PREPARING),
        "ready": (OrderStatus.PREPARING, OrderStatus.READY),
        "complete": (OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY),
    }

    transition = action_map.get(action.lower())
    if not transition:
        raise HTTPException(status_code=400, detail=f"Invalid kitchen action '{action}'")
    expected_status, target_status = transition
    if order.status != expected_status:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot apply '{action}' while order is {order.status.value}",
        )

    # Validate custom chosen delivery partner if provided by kitchen staff
    if delivery_partner_id is not None:
        partner_user = session.get(User, delivery_partner_id)
        if not partner_user or partner_user.role != UserRole.DELIVERY_PARTNER or not partner_user.is_active:
            raise HTTPException(status_code=400, detail="Invalid delivery partner selected")
        order.delivery_partner_id = delivery_partner_id

    # Confirmation through the kitchen dashboard must use the same dispatch
    # policy as the general order status endpoint if no partner is assigned yet.
    if action.lower() == "accept" and not order.delivery_partner_id:
        restaurant = session.get(Restaurant, order.restaurant_id)
        if restaurant:
            partner = assign_nearest_available_partner(session, order, restaurant.latitude, restaurant.longitude)
            if partner:
                order.delivery_partner_id = partner.id

    # Do not send a ready order out for delivery without a rider. Retry
    # assignment here in case nobody was available when the order was accepted.
    if action.lower() == "complete" and not order.delivery_partner_id:
        restaurant = session.get(Restaurant, order.restaurant_id)
        partner = assign_nearest_available_partner(
            session, order, restaurant.latitude, restaurant.longitude
        ) if restaurant else None
        if not partner:
            raise HTTPException(status_code=409, detail="No available delivery partner for this order")
        order.delivery_partner_id = partner.id

    # When handing over to delivery partner, track the delivery assignment
    if target_status == OrderStatus.OUT_FOR_DELIVERY and order.delivery_partner_id:
        assignment = session.exec(select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)).first()
        if not assignment:
            assignment = DeliveryAssignment(
                order_id=order.id,
                delivery_partner_id=order.delivery_partner_id,
                assigned_at=utc_now(),
                picked_up_at=utc_now()
            )
            session.add(assignment)
        else:
            assignment.delivery_partner_id = order.delivery_partner_id
            if not assignment.picked_up_at:
                assignment.picked_up_at = utc_now()
            session.add(assignment)

    order.status = target_status
    order.updated_at = utc_now()
    session.add(order)

    history = OrderStatusHistory(
        order_id=order_id,
        status=target_status,
        notes=f"Kitchen updated order to {target_status.value} (Handed over to Rider #{order.delivery_partner_id})",
        changed_by_role=current_user.role.value,
        timestamp=utc_now()
    )
    session.add(history)
    session.commit()

    await manager.broadcast(
        {
            "event": "KITCHEN_ORDER_UPDATED",
            "order_id": order.id,
            "order_number": order.order_number,
            "new_status": target_status.value,
            "action": action,
        },
        restaurant_id=order.restaurant_id,
        user_ids=[order.customer_id, order.delivery_partner_id],
    )

    return {
        "message": f"Order #{order.order_number} is now marked as {target_status.value}",
        "new_status": target_status.value
    }
