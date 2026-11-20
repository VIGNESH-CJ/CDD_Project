from typing import Optional, List
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.schemas.ai import ChatRequest, ChatResponse
from app.algorithms.recommendations import get_personalized_recommendations
from app.algorithms.food_assistant import process_food_chat
from app.algorithms.demand_prediction import train_and_predict_demand
from app.algorithms.smart_inventory import get_inventory_and_waste_analysis
from app.algorithms.dietary_service import get_dietary_and_allergy_menu
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import get_optional_user, require_role
from app.services.access_control import get_restaurant_scope

router = APIRouter(prefix="/api/ai", tags=["Artificial Intelligence & ML"])

@router.get("/recommendations")
def get_recommendations(
    user_id: Optional[int] = None,
    restaurant_id: Optional[int] = None,
    limit: int = 6,
    current_user: Optional[User] = Depends(get_optional_user),
    session: Session = Depends(get_session)
):
    """
    Feature 1: AI personalized food recommendations using order history, ratings and preferences.
    """
    effective_user_id = (
        current_user.id
        if current_user and current_user.role == UserRole.CUSTOMER
        else None
    )
    items = get_personalized_recommendations(
        session,
        user_id=effective_user_id,
        restaurant_id=restaurant_id,
        limit=max(1, min(limit, 50)),
    )
    return items

@router.post("/chat", response_model=ChatResponse)
def chat_with_food_assistant(
    req: ChatRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    session: Session = Depends(get_session)
):
    """
    Feature 2: AI conversational food assistant that queries the real menu database
    and assists customers with ordering and queries.
    """
    result = process_food_chat(
        session=session,
        message=req.message,
        # Never trust a caller-supplied user_id for private order lookups.
        user_id=current_user.id if current_user and current_user.role == UserRole.CUSTOMER else None,
        restaurant_id=req.restaurant_id,
        conversation_history=req.conversation_history
    )
    return ChatResponse(**result)

@router.get("/demand-forecast")
def get_demand_forecast(
    restaurant_id: Optional[int] = None,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN])),
    session: Session = Depends(get_session)
):
    """
    Feature 3: Food demand prediction using historical orders and Scikit-learn.
    """
    restaurant_scope = get_restaurant_scope(session, current_user, restaurant_id)
    if restaurant_scope is None:
        return train_and_predict_demand(session, restaurant_id=restaurant_id)
    return [
        item
        for owned_restaurant_id in restaurant_scope
        for item in train_and_predict_demand(session, restaurant_id=owned_restaurant_id)
    ]

@router.get("/smart-inventory")
def get_smart_inventory(
    restaurant_id: Optional[int] = None,
    current_user: User = Depends(require_role([UserRole.RESTAURANT_ADMIN, UserRole.SUPER_ADMIN])),
    session: Session = Depends(get_session)
):
    """
    Feature 4 & 10: Smart ingredient inventory, automatic stock alerts, and food waste reduction analysis.
    """
    restaurant_scope = get_restaurant_scope(session, current_user, restaurant_id)
    if restaurant_scope is None:
        return get_inventory_and_waste_analysis(session, restaurant_id=restaurant_id)

    reports = [
        get_inventory_and_waste_analysis(session, restaurant_id=owned_restaurant_id)
        for owned_restaurant_id in restaurant_scope
    ]
    return {
        "total_ingredients_monitored": sum(report["total_ingredients_monitored"] for report in reports),
        "total_inventory_value": round(sum(report["total_inventory_value"] for report in reports), 2),
        "inventory_items": [item for report in reports for item in report.get("inventory_items", [])],
        "low_stock_alerts_count": sum(report["low_stock_alerts_count"] for report in reports),
        "low_stock_alerts": [item for report in reports for item in report["low_stock_alerts"]],
        "expiry_warnings_count": sum(report["expiry_warnings_count"] for report in reports),
        "expiry_warnings": [item for report in reports for item in report["expiry_warnings"]],
        "total_waste_loss_amount": round(sum(report["total_waste_loss_amount"] for report in reports), 2),
        "waste_records_count": sum(report["waste_records_count"] for report in reports),
        "recent_waste_logs": [item for report in reports for item in report["recent_waste_logs"]][-8:],
    }

@router.get("/dietary-menu")
def get_dietary_menu(
    restaurant_id: Optional[int] = None,
    dietary_preference: Optional[str] = None,
    allergens: Optional[str] = None,
    current_user: Optional[User] = Depends(get_optional_user),
    session: Session = Depends(get_session)
):
    """
    Feature 8: Smart Food Allergy and Dietary Recommendation System
    Filters dishes based on dietary requirements, identifies dishes containing
    specified allergens, and suggests suitable alternative dishes.
    """
    user_id = current_user.id if current_user and current_user.role == UserRole.CUSTOMER else None
    return get_dietary_and_allergy_menu(
        session=session,
        restaurant_id=restaurant_id,
        dietary_preference=dietary_preference,
        allergens=allergens,
        user_id=user_id
    )
