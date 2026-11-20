"""Persistent records used by the Smart Food Intelligence module.

These records intentionally supplement the core ordering tables instead of
changing them.  That lets existing deployments receive the new tables through
``SQLModel.metadata.create_all`` without a destructive schema migration.
"""

from datetime import datetime
from typing import ClassVar, Optional

from sqlmodel import Field, SQLModel

from app.models.common import utc_now


class PersonalizationProfile(SQLModel, table=True):
    __tablename__: ClassVar[str] = "personalization_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    health_goal: str = Field(default="balanced", max_length=80)
    current_mood: str = Field(default="neutral", max_length=80)
    preferred_language: str = Field(default="English", max_length=40)
    max_meal_budget: float = Field(default=0.0, ge=0)
    sustainability_priority: int = Field(default=1, ge=0, le=3)
    updated_at: datetime = Field(default_factory=utc_now)


class GroupOrder(SQLModel, table=True):
    __tablename__: ClassVar[str] = "group_orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    invite_code: str = Field(unique=True, index=True, max_length=16)
    host_user_id: int = Field(foreign_key="users.id", index=True)
    restaurant_id: int = Field(foreign_key="restaurants.id", index=True)
    delivery_address: str = Field(max_length=400)
    status: str = Field(default="open", index=True, max_length=24)
    expires_at: datetime
    created_at: datetime = Field(default_factory=utc_now)


class GroupOrderMember(SQLModel, table=True):
    __tablename__: ClassVar[str] = "group_order_members"

    id: Optional[int] = Field(default=None, primary_key=True)
    group_order_id: int = Field(foreign_key="group_orders.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    display_name: str = Field(max_length=100)
    joined_at: datetime = Field(default_factory=utc_now)


class GroupOrderItem(SQLModel, table=True):
    __tablename__: ClassVar[str] = "group_order_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    group_order_id: int = Field(foreign_key="group_orders.id", index=True)
    member_id: Optional[int] = Field(default=None, foreign_key="group_order_members.id", index=True)
    menu_item_id: int = Field(foreign_key="menu_items.id", index=True)
    quantity: int = Field(default=1, ge=1, le=100)
    notes: Optional[str] = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class FoodRescueOffer(SQLModel, table=True):
    __tablename__: ClassVar[str] = "food_rescue_offers"

    id: Optional[int] = Field(default=None, primary_key=True)
    restaurant_id: int = Field(foreign_key="restaurants.id", index=True)
    menu_item_id: Optional[int] = Field(default=None, foreign_key="menu_items.id", index=True)
    title: str = Field(max_length=150)
    description: str = Field(default="Fresh surplus food", max_length=500)
    original_price: float = Field(ge=0)
    rescue_price: float = Field(ge=0)
    quantity_remaining: int = Field(default=1, ge=0)
    pickup_end: datetime
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)


class OrderIntelligence(SQLModel, table=True):
    __tablename__: ClassVar[str] = "order_intelligence"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", unique=True, index=True)
    delay_risk: int = Field(default=0, ge=0, le=100)
    quality_risk: int = Field(default=0, ge=0, le=100)
    predicted_delay_minutes: int = Field(default=0, ge=0)
    carbon_kg: float = Field(default=0.0, ge=0)
    safety_summary: Optional[str] = Field(default=None, max_length=500)
    recommended_action: Optional[str] = Field(default=None, max_length=300)
    handoff_count: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=utc_now)


class PostDeliveryFeedback(SQLModel, table=True):
    __tablename__: ClassVar[str] = "post_delivery_feedback"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", unique=True, index=True)
    customer_id: int = Field(foreign_key="users.id", index=True)
    food_rating: int = Field(ge=1, le=5)
    delivery_rating: int = Field(ge=1, le=5)
    food_was_warm: Optional[bool] = None
    issue_type: Optional[str] = Field(default=None, max_length=80)
    comment: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utc_now)
