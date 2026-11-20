from datetime import date, datetime, timedelta, timezone

from app.models.restaurant import Restaurant
from app.models.category import Category
from app.models.menu import MenuItem, RecipeItem
from app.models.inventory import Ingredient, InventoryTransaction
from app.models.user import User
from app.models.delivery import DeliveryProfile
from app.models.order import Order, OrderItem
from app.models.waste import FoodWasteRecord
from app.models.enums import UserRole, OrderStatus
from app.models.common import utc_isoformat
from app.algorithms.kitchen_priority import calculate_kitchen_priority_score
from app.services.auth_service import create_access_token
from sqlmodel import select


def test_utc_isoformat_marks_database_naive_timestamps_as_utc():
    value = datetime(2026, 11, 19, 12, 30)
    assert utc_isoformat(value) == "2026-11-19T12:30:00+00:00"
    aware = datetime(2026, 11, 19, 12, 30, tzinfo=timezone.utc)
    assert utc_isoformat(aware) == "2026-11-19T12:30:00+00:00"


def test_order_placement_inventory_deduction_and_priority(client, session, auth_headers, kitchen_headers, delivery_headers):
    # Setup database
    cust = User(email="customer@demo.com", hashed_password="pw", full_name="Customer", role=UserRole.CUSTOMER)
    session.add(cust)
    driver = User(email="delivery@demo.com", hashed_password="pw", full_name="Driver", role=UserRole.DELIVERY_PARTNER)
    session.add(driver)
    kitchen_staff = User(email="kitchen@demo.com", hashed_password="pw", full_name="Kitchen", role=UserRole.KITCHEN_STAFF)
    session.add(kitchen_staff)

    rest = Restaurant(name="Spice Garden", description="Desc", address="Indiranagar", image_url="http://img.jpg")
    session.add(rest)
    session.commit()
    session.refresh(rest)
    assert rest.id is not None
    session.refresh(driver)
    session.add(DeliveryProfile(user_id=driver.id, current_latitude=12.9716, current_longitude=77.5946, is_available=True))
    session.commit()

    cat = Category(name="South Indian", slug="south-indian")
    session.add(cat)
    session.commit()
    session.refresh(cat)
    assert cat.id is not None

    menu_item = MenuItem(
        restaurant_id=rest.id, category_id=cat.id,
        name="Masala Dosa", description="Dosa", price=80.0,
        prep_time_minutes=15, is_veg=True, image_url="http://dosa.jpg"
    )
    session.add(menu_item)
    session.commit()
    session.refresh(menu_item)
    assert menu_item.id is not None

    # Ingredient with low stock threshold
    ingredient = Ingredient(
        restaurant_id=rest.id, name="Dosa Batter",
        current_stock=10.0, reorder_level=5.0, cost_per_unit=40.0
    )
    session.add(ingredient)
    session.commit()
    session.refresh(ingredient)
    assert ingredient.id is not None

    recipe = RecipeItem(
        menu_item_id=menu_item.id,
        ingredient_id=ingredient.id,
        quantity_required=1.0  # 1kg per serving
    )
    session.add(recipe)
    session.commit()

    # Place an order for 6 Dosas -> Should deduct 6kg -> remaining 4kg <= reorder_level (5.0) -> triggers low stock!
    order_payload = {
        "restaurant_id": rest.id,
        "items": [{"menu_item_id": menu_item.id, "quantity": 6}],
        "delivery_address": "Koramangala, Bangalore",
        "payment_method": "cod"
    }

    order_res = client.post("/api/orders", json=order_payload, headers=auth_headers)
    assert order_res.status_code == 201
    order_data = order_res.json()
    assert order_data["success"] is True
    assert order_data["order_number"].startswith(f"ORD-{datetime.now(timezone.utc).year}-")
    assert "order_id" in order_data
    assert len(order_data["inventory_alerts"]) > 0
    assert order_data["inventory_alerts"][0]["status"] == "LOW_STOCK"

    # Verify updated ingredient stock in database
    session.refresh(ingredient)
    assert ingredient.current_stock == 4.0
    assert ingredient.is_low_stock is True

    # Test Kitchen Queue
    assert client.get("/api/kitchen/queue").status_code == 401
    assert client.get("/api/kitchen/queue", headers=auth_headers).status_code == 403
    k_res = client.get("/api/kitchen/queue", headers=kitchen_headers)
    assert k_res.status_code == 200
    queue = k_res.json()
    assert len(queue) >= 1
    assert queue[0]["order_id"] == order_data["order_id"]
    assert "priority_score" in queue[0]
    assert queue[0]["created_at"].endswith("+00:00")
    my_orders = client.get("/api/orders/my-orders", headers=auth_headers).json()
    assert my_orders[0]["created_at"].endswith("+00:00")

    # Test Kitchen Action: Accept -> Preparing -> Ready
    action_url = f"/api/kitchen/orders/{order_data['order_id']}/action"
    assert client.post(f"{action_url}?action=accept").status_code == 401
    action_res = client.post(f"{action_url}?action=accept", headers=kitchen_headers)
    assert action_res.status_code == 200
    assert action_res.json()["new_status"] == "confirmed"
    order = session.get(Order, order_data["order_id"])
    assert order is not None and order.delivery_partner_id == driver.id
    premature_pickup = client.post(
        f"/api/delivery/orders/{order_data['order_id']}/action?action=picked_up",
        headers=delivery_headers,
    )
    assert premature_pickup.status_code == 409
    premature_delivery = client.post(
        f"/api/delivery/orders/{order_data['order_id']}/action?action=delivered",
        headers=delivery_headers,
    )
    assert premature_delivery.status_code == 409

    prepare_res = client.post(f"{action_url}?action=prepare", headers=kitchen_headers)
    assert prepare_res.status_code == 200
    ready_res = client.post(f"{action_url}?action=ready", headers=kitchen_headers)
    assert ready_res.status_code == 200
    handover_res = client.post(f"{action_url}?action=complete", headers=kitchen_headers)
    assert handover_res.status_code == 200
    assert handover_res.json()["new_status"] == OrderStatus.OUT_FOR_DELIVERY.value

    delivered_res = client.post(
        f"/api/delivery/orders/{order_data['order_id']}/action?action=delivered",
        headers=delivery_headers,
    )
    assert delivered_res.status_code == 200
    repeated_delivery = client.post(
        f"/api/delivery/orders/{order_data['order_id']}/action?action=delivered",
        headers=delivery_headers,
    )
    assert repeated_delivery.status_code == 409
    completed_queue = client.get("/api/kitchen/queue?include_completed=true", headers=kitchen_headers)
    assert completed_queue.status_code == 200
    assert any(item["status"] == "delivered" for item in completed_queue.json())

    invalid_repeat = client.post(f"{action_url}?action=accept", headers=kitchen_headers)
    assert invalid_repeat.status_code == 409


def test_online_payment_requires_confirmed_checkout(client, session, auth_headers):
    customer = session.exec(select(User).where(User.email == "customer@demo.com")).first()
    if customer is None:
        customer = User(email="customer@demo.com", hashed_password="pw", full_name="Customer", role=UserRole.CUSTOMER)
        session.add(customer)
        session.commit()

    checkout = client.post(
        "/api/payments/checkout",
        json={"amount": 250},
        headers=auth_headers,
    )
    assert checkout.status_code == 200
    payment = checkout.json()
    assert payment["provider"] == "sandbox"
    assert payment["reference"].startswith("sandbox_")

    restaurant = Restaurant(
        name="Payment Kitchen",
        description="Test",
        address="Bengaluru",
        image_url="https://example.test/kitchen.png",
    )
    session.add(restaurant)
    session.commit()
    session.refresh(restaurant)
    category = Category(name="Meals", slug="payment-meals")
    session.add(category)
    session.commit()
    session.refresh(category)
    item = MenuItem(
        restaurant_id=restaurant.id,
        category_id=category.id,
        name="Payment Thali",
        description="Test meal",
        image_url="https://example.test/thali.png",
        price=250,
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    unpaid_payload = {
        "restaurant_id": restaurant.id,
        "items": [{"menu_item_id": item.id, "quantity": 1}],
        "delivery_address": "Bengaluru",
        "payment_method": "online",
        "payment_reference": "forged_reference",
    }
    unpaid = client.post("/api/orders", json=unpaid_payload, headers=auth_headers)
    assert unpaid.status_code == 402

    paid_payload = {**unpaid_payload, "payment_reference": payment["reference"]}
    paid = client.post("/api/orders", json=paid_payload, headers=auth_headers)
    assert paid.status_code == 201
    assert paid.json()["success"] is True


def test_food_waste_log_deducts_stock_and_records_loss(client, session):
    admin = User(
        email="waste-admin@test.local",
        hashed_password="pw",
        full_name="Waste Admin",
        role=UserRole.RESTAURANT_ADMIN,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)

    restaurant = Restaurant(
        name="Waste Kitchen",
        description="Test",
        address="Bengaluru",
        image_url="https://example.test/waste.png",
        owner_id=admin.id,
    )
    session.add(restaurant)
    session.commit()
    session.refresh(restaurant)

    ingredient = Ingredient(
        restaurant_id=restaurant.id,
        name="Paneer",
        current_stock=10,
        reorder_level=3,
        cost_per_unit=25,
        expiry_date=None,
    )
    session.add(ingredient)
    session.commit()
    session.refresh(ingredient)

    token = create_access_token({"sub": admin.email, "role": UserRole.RESTAURANT_ADMIN.value})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/admin/waste/log",
        json={
            "ingredient_id": ingredient.id,
            "quantity_wasted": 2.5,
            "reason": "Expired",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["remaining_stock"] == 7.5
    assert data["estimated_loss_amount"] == 62.5

    session.refresh(ingredient)
    assert ingredient.current_stock == 7.5
    record = session.exec(
        select(FoodWasteRecord).where(FoodWasteRecord.ingredient_id == ingredient.id)
    ).first()
    assert record is not None
    assert record.quantity_wasted == 2.5

    inventory = client.get(
        f"/api/admin/inventory?restaurant_id={restaurant.id}",
        headers=headers,
    )
    assert inventory.status_code == 200
    assert inventory.json()["waste_records_count"] >= 1
    assert any(item["name"] == "Paneer" for item in inventory.json()["inventory_items"])


def test_admin_can_add_ingredient_and_remove_expired_stock(client, session):
    admin = User(
        email="inventory-admin@test.local",
        hashed_password="pw",
        full_name="Inventory Admin",
        role=UserRole.RESTAURANT_ADMIN,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    restaurant = Restaurant(
        name="Inventory Kitchen",
        description="Test",
        address="Bengaluru",
        image_url="https://example.test/inventory.png",
        owner_id=admin.id,
    )
    session.add(restaurant)
    session.commit()
    session.refresh(restaurant)
    token = create_access_token({"sub": admin.email, "role": UserRole.RESTAURANT_ADMIN.value})
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/admin/inventory",
        headers=headers,
        json={
            "restaurant_id": restaurant.id,
            "name": "Fresh Paneer",
            "category": "Dairy",
            "unit": "kg",
            "current_stock": 4,
            "reorder_level": 1,
            "cost_per_unit": 30,
            "expiry_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    assert created.status_code == 201
    ingredient_id = created.json()["id"]
    assert session.exec(
        select(InventoryTransaction).where(InventoryTransaction.ingredient_id == ingredient_id)
    ).first() is not None

    inventory = client.get(
        f"/api/admin/inventory?restaurant_id={restaurant.id}",
        headers=headers,
    ).json()
    expired_item = next(item for item in inventory["inventory_items"] if item["id"] == ingredient_id)
    assert expired_item["is_expired"] is True
    assert expired_item["days_remaining"] == -1

    restocked = client.post(
        f"/api/admin/inventory/restock?ingredient_id={ingredient_id}&quantity_to_add=2",
        headers=headers,
    )
    assert restocked.status_code == 409

    removed = client.post(
        "/api/admin/waste/log",
        headers=headers,
        json={"ingredient_id": ingredient_id, "quantity_wasted": 4, "reason": "Expired"},
    )
    assert removed.status_code == 200
    assert removed.json()["remaining_stock"] == 0
    assert "do not serve expired" in removed.json()["prevention_recommendation"].lower()

    outsider = User(
        email="other-inventory-admin@test.local",
        hashed_password="pw",
        full_name="Other Admin",
        role=UserRole.RESTAURANT_ADMIN,
    )
    session.add(outsider)
    session.commit()
    session.refresh(outsider)
    outsider_token = create_access_token(
        {"sub": outsider.email, "role": UserRole.RESTAURANT_ADMIN.value}
    )
    forbidden = client.post(
        "/api/admin/inventory",
        headers={"Authorization": f"Bearer {outsider_token}"},
        json={
            "restaurant_id": restaurant.id,
            "name": "Unauthorized Ingredient",
        },
    )
    assert forbidden.status_code == 403


def test_sales_performance_reports_best_and_least_selling(client, session, admin_headers):
    admin = User(email="analytics-admin@test.local", hashed_password="pw", full_name="Admin", role=UserRole.RESTAURANT_ADMIN)
    customer = User(email="analytics-customer@test.local", hashed_password="pw", full_name="Customer", role=UserRole.CUSTOMER)
    restaurant = Restaurant(name="Analytics Kitchen", description="Test", address="Bengaluru", image_url="https://example.test/r.png")
    session.add_all([admin, customer, restaurant])
    session.commit()
    session.refresh(admin)
    session.refresh(customer)
    session.refresh(restaurant)
    restaurant.owner_id = admin.id
    category = Category(name="Analytics", slug="analytics")
    session.add_all([restaurant, category])
    session.commit()
    session.refresh(category)
    popular = MenuItem(restaurant_id=restaurant.id, category_id=category.id, name="Popular Dish", description="Test", image_url="https://example.test/p.png", price=100)
    rare = MenuItem(restaurant_id=restaurant.id, category_id=category.id, name="Rare Dish", description="Test", image_url="https://example.test/r.png", price=100)
    session.add_all([popular, rare])
    session.commit()
    session.refresh(popular)
    session.refresh(rare)

    order = Order(order_number="AN-001", customer_id=customer.id, restaurant_id=restaurant.id, status=OrderStatus.DELIVERED, delivery_address="Bengaluru")
    session.add(order)
    session.commit()
    session.refresh(order)
    session.add(OrderItem(order_id=order.id, menu_item_id=popular.id, item_name="Popular Dish", quantity=5, unit_price=100, total_price=500))
    session.commit()

    response = client.get(
        f"/api/admin/analytics/sales-performance?restaurant_id={restaurant.id}",
        headers={"Authorization": f"Bearer {create_access_token({'sub': admin.email})}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["best_selling"][0]["name"] == "Popular Dish"
    assert data["best_selling"][0]["order_count"] == 5
    assert {item["name"] for item in data["least_selling"]} >= {"Popular Dish", "Rare Dish"}


def test_restaurant_admin_kitchen_access_is_limited_to_owned_restaurants(client, session, admin_headers):
    admin = User(email="admin@demo.com", hashed_password="pw", full_name="Admin", role=UserRole.RESTAURANT_ADMIN)
    other_owner = User(email="other-admin@test.com", hashed_password="pw", full_name="Other Admin", role=UserRole.RESTAURANT_ADMIN)
    customer = User(email="customer@test.com", hashed_password="pw", full_name="Customer", role=UserRole.CUSTOMER)
    session.add_all([admin, other_owner, customer])
    session.commit()
    session.refresh(admin)
    session.refresh(other_owner)
    session.refresh(customer)

    other_restaurant = Restaurant(
        name="Other Restaurant", description="Desc", address="Bengaluru",
        image_url="https://example.test/restaurant.png", owner_id=other_owner.id,
    )
    session.add(other_restaurant)
    session.commit()
    session.refresh(other_restaurant)

    foreign_order = Order(
        order_number="ORD-FOREIGN", customer_id=customer.id, restaurant_id=other_restaurant.id,
        delivery_address="Bengaluru",
    )
    session.add(foreign_order)
    session.commit()
    session.refresh(foreign_order)

    queue_response = client.get(
        f"/api/kitchen/queue?restaurant_id={other_restaurant.id}", headers=admin_headers
    )
    action_response = client.post(
        f"/api/kitchen/orders/{foreign_order.id}/action?action=accept", headers=admin_headers
    )
    assert queue_response.status_code == 403
    assert action_response.status_code == 403

    unscoped_stats = client.get("/api/admin/dashboard-stats", headers=admin_headers)
    foreign_stats = client.get(
        f"/api/admin/dashboard-stats?restaurant_id={other_restaurant.id}", headers=admin_headers
    )
    foreign_status = client.patch(
        f"/api/orders/{foreign_order.id}/status",
        json={"status": "confirmed"},
        headers=admin_headers,
    )
    assert unscoped_stats.status_code == 200
    assert unscoped_stats.json()["total_orders"] == 0
    assert foreign_stats.status_code == 403
    assert foreign_status.status_code == 403
