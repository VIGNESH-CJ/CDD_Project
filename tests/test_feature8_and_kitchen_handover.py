import pytest
from sqlmodel import Session, select
from app.database import engine
from app.models.user import User, CustomerPreference
from app.models.order import Order
from app.models.enums import OrderStatus, UserRole
from app.models.delivery import DeliveryProfile, DeliveryAssignment
from app.algorithms.dietary_service import (
    get_dietary_and_allergy_menu,
    normalize_allergy_terms,
    detect_allergens_in_item,
    check_dietary_compliance,
    analyze_dish_dietary_safety
)

def test_two_delivery_partners_exist():
    with Session(engine) as session:
        partners = session.exec(select(User).where(User.role == UserRole.DELIVERY_PARTNER)).all()
        assert len(partners) >= 2, f"Expected at least 2 delivery partners, found {len(partners)}"
        emails = [p.email for p in partners]
        assert "delivery@demo.com" in emails
        assert "delivery2@demo.com" in emails
        print(f"Verified {len(partners)} delivery partners: {emails}")

def test_delivery_profiles_configured():
    with Session(engine) as session:
        partners = session.exec(select(User).where(User.role == UserRole.DELIVERY_PARTNER)).all()
        for p in partners:
            prof = session.exec(select(DeliveryProfile).where(DeliveryProfile.user_id == p.id)).first()
            assert prof is not None, f"Missing delivery profile for {p.email}"
            assert prof.vehicle_type, f"Missing vehicle type for {p.email}"
            assert prof.vehicle_number, f"Missing vehicle number for {p.email}"
            print(f"Partner {p.full_name}: {prof.vehicle_type} ({prof.vehicle_number})")

def test_dietary_service_allergen_normalization():
    raw = "Peanuts, Dairy; Gluten, None, N/A"
    terms = normalize_allergy_terms(raw)
    assert "peanuts" in terms
    assert "dairy" in terms
    assert "gluten" in terms
    assert "none" not in terms
    assert "n/a" not in terms

def test_smart_dietary_menu_engine():
    with Session(engine) as session:
        # Test Veg + Dairy & Peanuts allergy
        result = get_dietary_and_allergy_menu(
            session=session,
            restaurant_id=1,
            dietary_preference="Veg",
            allergens="dairy, peanuts"
        )
        assert "summary" in result
        assert "suitable" in result
        assert "customizable" in result
        assert "unsuitable" in result
        
        # Verify unsuitable items have alternatives attached
        for item in result["unsuitable"]:
            assert "suggested_alternatives" in item
            assert "detected_allergens" in item
            print(f"Unsuitable item: {item['name']} -> Detected: {item['detected_allergens']} -> Alternatives: {[a['name'] for a in item['suggested_alternatives']]}")

def test_customer_preference_crud():
    with Session(engine) as session:
        cust = session.exec(select(User).where(User.email == "customer@demo.com")).first()
        assert cust is not None
        pref = session.exec(select(CustomerPreference).where(CustomerPreference.user_id == cust.id)).first()
        assert pref is not None
        
        # Test update preference
        pref.dietary_preference = "Vegan"
        pref.allergy_info = "Peanuts, Dairy"
        session.add(pref)
        session.commit()
        session.refresh(pref)
        
        assert pref.dietary_preference == "Vegan"
        assert "Dairy" in pref.allergy_info

        # Reset back to Veg
        pref.dietary_preference = "Veg"
        pref.allergy_info = "None"
        session.add(pref)
        session.commit()

if __name__ == "__main__":
    test_two_delivery_partners_exist()
    test_delivery_profiles_configured()
    test_dietary_service_allergen_normalization()
    test_smart_dietary_menu_engine()
    test_customer_preference_crud()
    print("\nALL FEATURE 8 & MULTI-RIDER TESTS PASSED SUCCESSFULLY!")
