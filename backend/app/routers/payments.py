from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.payment_service import create_checkout_session


router = APIRouter(prefix="/api/payments", tags=["Payments"])


class CheckoutRequest(BaseModel):
    amount: float = Field(gt=0)


@router.post("/checkout")
def create_payment_checkout(
    request: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    return create_checkout_session(request.amount, current_user.email)
