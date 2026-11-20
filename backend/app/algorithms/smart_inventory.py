from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select
from app.models.menu import MenuItem, RecipeItem
from app.models.inventory import Ingredient, InventoryTransaction
from app.models.waste import FoodWasteRecord
from app.models.enums import InventoryAction
from app.models.common import utc_now, utc_isoformat

def deduct_inventory_for_order(
    session: Session,
    restaurant_id: int,
    order_id: int,
    order_items: List[Any]
) -> List[Dict[str, Any]]:
    """
    Smart Ingredient Inventory Automatic Deduction:
    Translates every ordered food item into its constituent ingredients via recipes,
    deducts exact quantities, updates transaction logs, and flags low stock.
    """
    alerts = []
    
    for item in order_items:
        menu_item_id = item.menu_item_id
        qty = item.quantity
        
        # Look up recipe items
        recipes = session.exec(
            select(RecipeItem).where(RecipeItem.menu_item_id == menu_item_id)
        ).all()
        
        for r in recipes:
            ingredient = session.exec(
                select(Ingredient).where(Ingredient.id == r.ingredient_id)
            ).first()
            
            if ingredient:
                if ingredient.id is None:
                    continue

                deduction_amount = r.quantity_required * qty
                ingredient.current_stock = max(0.0, round(ingredient.current_stock - deduction_amount, 2))
                ingredient.updated_at = utc_now()
                
                # Check low stock threshold
                if ingredient.current_stock <= ingredient.reorder_level:
                    ingredient.is_low_stock = True
                    alerts.append({
                        "ingredient_id": ingredient.id,
                        "name": ingredient.name,
                        "current_stock": ingredient.current_stock,
                        "unit": ingredient.unit,
                        "reorder_level": ingredient.reorder_level,
                        "status": "LOW_STOCK"
                    })
                else:
                    ingredient.is_low_stock = False

                session.add(ingredient)

                # Log transaction
                tx = InventoryTransaction(
                    ingredient_id=ingredient.id,
                    restaurant_id=restaurant_id,
                    action=InventoryAction.ORDER_DEDUCTION,
                    quantity_changed=-deduction_amount,
                    balance_after=ingredient.current_stock,
                    order_id=order_id,
                    notes=f"Auto-deducted for Order #{order_id} ({item.item_name} x{qty})",
                    created_at=utc_now()
                )
                session.add(tx)

    session.commit()
    return alerts

def get_inventory_and_waste_analysis(
    session: Session,
    restaurant_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Food Waste Reduction & Shelf-life Analysis:
    Monitors ingredients nearing expiry date (< 3 days),
    calculates potential waste financial risk, and suggests waste prevention actions.
    """
    today = date.today()

    ing_query = select(Ingredient)
    if restaurant_id:
        ing_query = ing_query.where(Ingredient.restaurant_id == restaurant_id)
    ingredients = session.exec(ing_query).all()

    low_stock_items = []
    expiry_warning_items = []
    inventory_items = []
    total_inventory_value = 0.0

    for ing in ingredients:
        total_inventory_value += ing.current_stock * ing.cost_per_unit
        days_remaining = (ing.expiry_date - today).days if ing.expiry_date else None
        inventory_items.append({
            "id": ing.id,
            "name": ing.name,
            "category": ing.category,
            "current_stock": ing.current_stock,
            "reorder_level": ing.reorder_level,
            "unit": ing.unit,
            "cost_per_unit": ing.cost_per_unit,
            "expiry_date": str(ing.expiry_date) if ing.expiry_date else None,
            "days_remaining": days_remaining,
            "is_expired": days_remaining is not None and days_remaining < 0,
            "is_low_stock": ing.current_stock <= ing.reorder_level,
        })
        
        if ing.current_stock <= ing.reorder_level:
            low_stock_items.append({
                "id": ing.id,
                "name": ing.name,
                "current_stock": ing.current_stock,
                "reorder_level": ing.reorder_level,
                "unit": ing.unit,
                "urgency": "CRITICAL" if ing.current_stock <= (ing.reorder_level * 0.5) else "WARNING",
                "recommended_order": round((ing.reorder_level * 2.5) - ing.current_stock, 1),
                "is_expired": days_remaining is not None and days_remaining < 0,
            })

        if days_remaining is not None:
            days_left = days_remaining
            if days_left <= 3:
                risk_amount = round(ing.current_stock * ing.cost_per_unit, 2)
                expiry_warning_items.append({
                    "id": ing.id,
                    "name": ing.name,
                    "current_stock": ing.current_stock,
                    "unit": ing.unit,
                    "expiry_date": str(ing.expiry_date),
                    "days_remaining": days_left,
                    "financial_risk": f"₹{risk_amount:.2f}",
                    "financial_risk_amount": risk_amount,
                    "ai_prevention_action": (
                        f"Suggest featuring dishes using {ing.name} in Today's Special Offers or Chef Specials."
                    )
                })

    # Fetch recorded waste
    waste_query = select(FoodWasteRecord)
    if restaurant_id:
        waste_query = waste_query.where(FoodWasteRecord.restaurant_id == restaurant_id)
    waste_records = session.exec(waste_query).all()

    total_waste_loss = sum(w.estimated_loss_amount for w in waste_records)

    return {
        "total_ingredients_monitored": len(ingredients),
        "total_inventory_value": round(total_inventory_value, 2),
        "inventory_items": inventory_items,
        "low_stock_alerts_count": len(low_stock_items),
        "low_stock_alerts": low_stock_items,
        "expiry_warnings_count": len(expiry_warning_items),
        "expiry_warnings": expiry_warning_items,
        "total_waste_loss_amount": round(total_waste_loss, 2),
        "waste_records_count": len(waste_records),
        "recent_waste_logs": [
            {
                "id": w.id,
                "ingredient": w.ingredient_name,
                "quantity": f"{w.quantity_wasted} {w.unit}",
                "reason": w.reason,
                "loss": f"₹{w.estimated_loss_amount:.2f}",
                "date": utc_isoformat(w.recorded_at)
            }
            for w in waste_records[-8:]
        ]
    }
