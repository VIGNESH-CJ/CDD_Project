from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus

class OrderItemInput(BaseModel):
    menu_item_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100)
    special_instructions: Optional[str] = Field(default=None, max_length=200)

class OrderCreate(BaseModel):
    restaurant_id: int = Field(gt=0)
    items: List[OrderItemInput] = Field(min_length=1, max_length=100)
    delivery_address: str = Field(min_length=1, max_length=400)
    coupon_code: Optional[str] = None
    payment_method: PaymentMethod = PaymentMethod.COD
    payment_reference: Optional[str] = Field(default=None, max_length=255)
    customer_notes: Optional[str] = None
    delivery_latitude: Optional[float] = Field(default=12.9716, ge=-90, le=90)
    delivery_longitude: Optional[float] = Field(default=77.5946, ge=-180, le=180)

class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    notes: Optional[str] = None

class CartItemAdd(BaseModel):
    menu_item_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=100)
    replace_cart: bool = False

class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=100)

class CouponApply(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    subtotal: float = Field(ge=0)
