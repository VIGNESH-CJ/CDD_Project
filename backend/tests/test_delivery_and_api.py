from app.models.delivery import DeliveryProfile
from app.models.enums import OrderStatus, UserRole
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.user import CustomerPreference, User
from app.services.auth_service import create_access_token
from app.services.geo_service import assign_nearest_available_partner, calculate_eta_minutes, haversine_distance_km


def test_haversine_known_distance():
    # Bengaluru to Mysuru is approximately 128 km by great-circle distance.
    distance = haversine_distance_km(12.9716, 77.5946, 12.2958, 76.6394)
    assert 125 < distance < 130
    assert haversine_distance_km(0, 0, 0, 0) == 0


def test_eta_uses_25_kmh_and_five_minute_buffer():
    assert calculate_eta_minutes(25, 20) == 85
    assert calculate_eta_minutes(0, 10) == 15


def test_assigns_nearest_available_partner_with_no_active_orders(session):
    restaurant = Restaurant(name="Test Kitchen", description="Test", address="Bengaluru", image_url="https://example.test/r.png", latitude=12.97, longitude=77.59)
    near = User(email="near@test.local", hashed_password="x", full_name="Near Rider", role=UserRole.DELIVERY_PARTNER)
    far = User(email="far@test.local", hashed_password="x", full_name="Far Rider", role=UserRole.DELIVERY_PARTNER)
    busy = User(email="busy@test.local", hashed_password="x", full_name="Busy Rider", role=UserRole.DELIVERY_PARTNER)
    customer = User(email="customer@test.local", hashed_password="x", full_name="Customer", role=UserRole.CUSTOMER)
    for row in (restaurant, near, far, busy, customer): session.add(row)
    session.commit()
    for row in (restaurant, near, far, busy, customer): session.refresh(row)
    assert restaurant.id is not None
    assert near.id is not None and far.id is not None and busy.id is not None and customer.id is not None
    session.add_all([
        DeliveryProfile(user_id=near.id, current_latitude=12.971, current_longitude=77.591, is_available=True),
        DeliveryProfile(user_id=far.id, current_latitude=13.05, current_longitude=77.70, is_available=True),
        DeliveryProfile(user_id=busy.id, current_latitude=12.9701, current_longitude=77.5901, is_available=True),
    ])
    order = Order(order_number="ORD-TEST-1", customer_id=customer.id, restaurant_id=restaurant.id, delivery_partner_id=busy.id,
                  status=OrderStatus.OUT_FOR_DELIVERY, delivery_address="Bengaluru", delivery_latitude=12.99, delivery_longitude=77.61)
    new_order = Order(order_number="ORD-TEST-2", customer_id=customer.id, restaurant_id=restaurant.id,
                      status=OrderStatus.CONFIRMED, delivery_address="Bengaluru", delivery_latitude=12.99, delivery_longitude=77.61)
    session.add_all([order, new_order]); session.commit(); session.refresh(new_order)
    partner = assign_nearest_available_partner(session, new_order, restaurant.latitude, restaurant.longitude)
    assert partner is not None and partner.id == near.id


def test_single_available_partner_handles_an_additional_ready_order(session):
    restaurant = Restaurant(
        name="Small Kitchen",
        description="Test",
        address="Bengaluru",
        image_url="https://example.test/r.png",
        latitude=12.97,
        longitude=77.59,
    )
    rider = User(
        email="only-rider@test.local",
        hashed_password="x",
        full_name="Only Rider",
        role=UserRole.DELIVERY_PARTNER,
    )
    customer = User(
        email="handoff-customer@test.local",
        hashed_password="x",
        full_name="Customer",
        role=UserRole.CUSTOMER,
    )
    session.add_all([restaurant, rider, customer])
    session.commit()
    for row in (restaurant, rider, customer):
        session.refresh(row)

    session.add(
        DeliveryProfile(
            user_id=rider.id,
            current_latitude=12.971,
            current_longitude=77.591,
            is_available=True,
        )
    )
    first_order = Order(
        order_number="ORD-FIRST",
        customer_id=customer.id,
        restaurant_id=restaurant.id,
        delivery_partner_id=rider.id,
        status=OrderStatus.OUT_FOR_DELIVERY,
        delivery_address="Bengaluru",
    )
    second_order = Order(
        order_number="ORD-SECOND",
        customer_id=customer.id,
        restaurant_id=restaurant.id,
        status=OrderStatus.READY,
        delivery_address="Bengaluru",
    )
    session.add_all([first_order, second_order])
    session.commit()
    session.refresh(second_order)

    partner = assign_nearest_available_partner(
        session,
        second_order,
        restaurant.latitude,
        restaurant.longitude,
    )
    assert partner is not None
    assert partner.id == rider.id


def test_recommendations_filter_allergies_and_dietary_preference(client, session):
    from app.models.category import Category
    from app.models.menu import MenuItem
    user = User(email="veg@test.local", hashed_password="x", full_name="Veg Customer", role=UserRole.CUSTOMER)
    restaurant = Restaurant(name="Safe Kitchen", description="Test", address="Bengaluru", image_url="https://example.test/r.png")
    session.add_all([user, restaurant]); session.commit(); session.refresh(user); session.refresh(restaurant)
    assert user.id is not None and restaurant.id is not None
    category = Category(name="Meals", slug="test-meals"); session.add(category); session.commit(); session.refresh(category)
    assert category.id is not None
    session.add(CustomerPreference(user_id=user.id, dietary_preference="Veg", allergy_info="Peanut"))
    session.add_all([
        MenuItem(restaurant_id=restaurant.id, category_id=category.id, name="Safe Dosa", description="Plain", image_url="https://example.test/d.png", ingredients="rice", allergens="None", is_veg=True),
        MenuItem(restaurant_id=restaurant.id, category_id=category.id, name="Peanut Curry", description="Peanut", image_url="https://example.test/p.png", ingredients="peanut", allergens="Peanut", is_veg=True),
        MenuItem(restaurant_id=restaurant.id, category_id=category.id, name="Chicken Curry", description="Chicken", image_url="https://example.test/c.png", ingredients="chicken", allergens="None", is_veg=False),
    ]); session.commit()
    token = create_access_token({"sub": user.email})
    response = client.get(
        f"/api/ai/recommendations?user_id={user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert "Safe Dosa" in names
    assert "Peanut Curry" not in names
    assert "Chicken Curry" not in names


def test_jwt_protected_order_route(client, session):
    user = User(email="auth@test.local", hashed_password="x", full_name="Auth User", role=UserRole.CUSTOMER)
    session.add(user); session.commit()
    token = create_access_token({"sub": user.email, "role": "customer"})
    response = client.get("/api/orders/my-orders", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == []
    assert client.get("/api/orders/my-orders").status_code == 401


def test_eta_route_requires_authenticated_order_owner(client, session):
    customer = User(email="eta@test.local", hashed_password="x", full_name="ETA Customer", role=UserRole.CUSTOMER)
    restaurant = Restaurant(name="ETA Kitchen", description="Test", address="Bengaluru", image_url="https://example.test/r.png", latitude=12.97, longitude=77.59)
    session.add_all([customer, restaurant]); session.commit(); session.refresh(customer); session.refresh(restaurant)
    assert customer.id is not None and restaurant.id is not None
    order = Order(order_number="ORD-ETA", customer_id=customer.id, restaurant_id=restaurant.id, status=OrderStatus.CONFIRMED,
                  delivery_address="Bengaluru", delivery_latitude=12.97, delivery_longitude=77.59, estimated_prep_minutes=20)
    session.add(order); session.commit(); session.refresh(order)
    assert order.id is not None
    token = create_access_token({"sub": customer.email})
    result = client.get(f"/api/delivery/orders/{order.id}/eta", headers={"Authorization": f"Bearer {token}"})
    assert result.status_code == 200
    assert result.json()["eta_minutes"] == 25
