import sys
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
import random

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlmodel import Session, select
from app.database import engine, create_db_and_tables
from app.services.auth_service import get_password_hash
from app.models.enums import UserRole, OrderStatus, PaymentMethod, PaymentStatus, InventoryAction
from app.models.user import User, CustomerPreference, Address, Notification
from app.models.restaurant import Restaurant
from app.models.category import Category
from app.models.menu import MenuItem, RecipeItem
from app.models.inventory import Ingredient, InventoryTransaction
from app.models.order import Order, OrderItem, OrderStatusHistory, Payment
from app.models.review import Review, Favorite
from app.models.waste import FoodWasteRecord
from app.models.delivery import DeliveryProfile

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def run_seed():
    create_db_and_tables()
    with Session(engine) as session:
        # Check if already seeded
        existing_admin = session.exec(select(User).where(User.email == "admin@demo.com")).first()
        if existing_admin:
            print("Database already contains demo seed data. Skipping or re-verifying.")
            return

        print("Seeding AI Foodie database with realistic culinary data...")

        # 1. Seed Demo Users
        demo_password = get_password_hash("Demo@12345")

        users_data = [
            {
                "email": "customer@demo.com",
                "full_name": "Aarav Sharma (Customer)",
                "phone": "+91 98450 11223",
                "role": UserRole.CUSTOMER,
                "loyalty_points": 450
            },
            {
                "email": "admin@demo.com",
                "full_name": "Priya Nair (Restaurant Admin)",
                "phone": "+91 98450 22334",
                "role": UserRole.RESTAURANT_ADMIN,
                "loyalty_points": 0
            },
            {
                "email": "kitchen@demo.com",
                "full_name": "Chef Rajesh Verma (Kitchen Staff)",
                "phone": "+91 98450 33445",
                "role": UserRole.KITCHEN_STAFF,
                "loyalty_points": 0
            },
            {
                "email": "delivery@demo.com",
                "full_name": "Vikram Singh (Delivery Partner)",
                "phone": "+91 98450 44556",
                "role": UserRole.DELIVERY_PARTNER,
                "loyalty_points": 0
            },
            {
                "email": "delivery2@demo.com",
                "full_name": "Rahul Verma (Delivery Partner)",
                "phone": "+91 98450 77889",
                "role": UserRole.DELIVERY_PARTNER,
                "loyalty_points": 0
            },
            {
                "email": "superadmin@demo.com",
                "full_name": "Kavita Rao (Super Admin)",
                "phone": "+91 98450 55667",
                "role": UserRole.SUPER_ADMIN,
                "loyalty_points": 0
            }
        ]

        created_users = {}
        for u in users_data:
            user = User(
                email=u["email"],
                hashed_password=demo_password,
                full_name=u["full_name"],
                phone=u["phone"],
                role=u["role"],
                is_active=True,
                loyalty_points=u["loyalty_points"],
                created_at=now_utc() - timedelta(days=60)
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            created_users[u["email"]] = user

        # Customer Preferences & Address
        customer_user = created_users["customer@demo.com"]
        pref = CustomerPreference(
            user_id=customer_user.id,
            dietary_preference="Veg",
            allergy_info="None",
            spice_level="Medium",
            favorite_cuisine="South Indian"
        )
        session.add(pref)

        addr = Address(
            user_id=customer_user.id,
            label="Home",
            street_address="Flat 402, Green Glen Layout, Bellandur",
            city="Bangalore",
            postal_code="560103",
            landmark="Near Central Mall",
            latitude=12.9304,
            longitude=77.6784,
            is_default=True
        )
        session.add(addr)

        # Delivery Partner Profiles
        delivery_user = created_users["delivery@demo.com"]
        deliv_profile = DeliveryProfile(
            user_id=delivery_user.id,
            vehicle_type="Electric Scooter (Ather 450X)",
            vehicle_number="KA-05-EV-8899",
            current_latitude=12.9716,
            current_longitude=77.5946,
            is_available=True,
            total_deliveries=142,
            total_earnings=6390.0,
            rating=4.9
        )
        session.add(deliv_profile)

        delivery_user2 = created_users["delivery2@demo.com"]
        deliv_profile2 = DeliveryProfile(
            user_id=delivery_user2.id,
            vehicle_type="Motorcycle (Hero Splendor Plus)",
            vehicle_number="KA-05-AB-4321",
            current_latitude=12.9720,
            current_longitude=77.5950,
            is_available=True,
            total_deliveries=88,
            total_earnings=3960.0,
            rating=4.8
        )
        session.add(deliv_profile2)
        session.commit()

        # 2. Seed Categories
        categories_data = [
            {"name": "South Indian", "slug": "south-indian", "icon_emoji": "🥞", "display_order": 1},
            {"name": "North Indian", "slug": "north-indian", "icon_emoji": "🍛", "display_order": 2},
            {"name": "Pizza", "slug": "pizza", "icon_emoji": "🍕", "display_order": 3},
            {"name": "Burgers", "slug": "burgers", "icon_emoji": "🍔", "display_order": 4},
            {"name": "Biryani", "slug": "biryani", "icon_emoji": "🥘", "display_order": 5},
            {"name": "Chinese", "slug": "chinese", "icon_emoji": "🍜", "display_order": 6},
            {"name": "Breakfast", "slug": "breakfast", "icon_emoji": "☕", "display_order": 7},
            {"name": "Desserts", "slug": "desserts", "icon_emoji": "🍰", "display_order": 8},
            {"name": "Beverages", "slug": "beverages", "icon_emoji": "🥤", "display_order": 9},
            {"name": "Snacks", "slug": "snacks", "icon_emoji": "🍟", "display_order": 10}
        ]

        cat_map = {}
        for c in categories_data:
            cat = Category(**c)
            session.add(cat)
            session.commit()
            session.refresh(cat)
            cat_map[c["name"]] = cat

        # 3. Seed 4 Demo Restaurants
        restaurants_data = [
            {
                "name": "Spice Garden",
                "tagline": "Authentic South & North Indian Delicacies",
                "description": "Spice Garden brings you rich heritage recipes crafted with cold-pressed oils, freshly ground aromatic spices, and traditional stone-ground batters.",
                "cuisine_type": "South Indian, North Indian, Pure Veg",
                "address": "100 Feet Road, Indiranagar",
                "city": "Bangalore",
                "phone": "+91 98450 88771",
                "rating": 4.8,
                "total_reviews": 320,
                "image_url": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=800&auto=format&fit=crop&q=80",
                "banner_url": "https://images.unsplash.com/photo-1589301760014-d929f3979dbc?w=1200&auto=format&fit=crop&q=80",
                "is_pure_veg": True,
                "delivery_time_mins": 25,
                "cost_for_two": 300.0,
                "latitude": 12.9784,
                "longitude": 77.6408,
                "owner_id": created_users["admin@demo.com"].id
            },
            {
                "name": "Pizza Palace",
                "tagline": "Wood-Fired Crusts & Melted Mozzarella",
                "description": "Hand-stretched sourdough pizzas baked in authentic wood-fired ovens with imported San Marzano tomato sauce and fresh basil.",
                "cuisine_type": "Italian, Pizza, Fast Food",
                "address": "5th Block, Koramangala",
                "city": "Bangalore",
                "phone": "+91 98450 88772",
                "rating": 4.6,
                "total_reviews": 245,
                "image_url": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=800&auto=format&fit=crop&q=80",
                "banner_url": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=1200&auto=format&fit=crop&q=80",
                "is_pure_veg": False,
                "delivery_time_mins": 30,
                "cost_for_two": 450.0,
                "latitude": 12.9352,
                "longitude": 77.6245,
                "owner_id": created_users["admin@demo.com"].id
            },
            {
                "name": "Burger Hub",
                "tagline": "Gourmet Smashed Patties & Thick Shakes",
                "description": "Juicy artisan burgers served in toasted brioche buns, accompanied by signature peri-peri spiced dips and creamy shakes.",
                "cuisine_type": "Burgers, American, Fast Food",
                "address": "Sector 4, HSR Layout",
                "city": "Bangalore",
                "phone": "+91 98450 88773",
                "rating": 4.5,
                "total_reviews": 190,
                "image_url": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=800&auto=format&fit=crop&q=80",
                "banner_url": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=1200&auto=format&fit=crop&q=80",
                "is_pure_veg": False,
                "delivery_time_mins": 20,
                "cost_for_two": 350.0,
                "latitude": 12.9116,
                "longitude": 77.6389,
                "owner_id": created_users["admin@demo.com"].id
            },
            {
                "name": "Royal Kitchen",
                "tagline": "Royal Dum Biryanis & Tandoori Delights",
                "description": "Rich Mughlai gravies, slow-cooked Hyderabadi Dum Biryani, and smokey charcoal tandoor platters prepared by master ustads.",
                "cuisine_type": "Biryani, North Indian, Mughlai",
                "address": "ITPL Main Road, Whitefield",
                "city": "Bangalore",
                "phone": "+91 98450 88774",
                "rating": 4.7,
                "total_reviews": 410,
                "image_url": "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?w=800&auto=format&fit=crop&q=80",
                "banner_url": "https://images.unsplash.com/photo-1589302168068-964664d93dc0?w=1200&auto=format&fit=crop&q=80",
                "is_pure_veg": False,
                "delivery_time_mins": 35,
                "cost_for_two": 500.0,
                "latitude": 12.9868,
                "longitude": 77.7378,
                "owner_id": created_users["admin@demo.com"].id
            }
        ]

        rest_map = {}
        for r in restaurants_data:
            rest = Restaurant(**r)
            session.add(rest)
            session.commit()
            session.refresh(rest)
            rest_map[r["name"]] = rest

        # 4. Seed Food Items (Exact menus from Section 5 + extras)
        food_items_data = [
            # Restaurant 1: Spice Garden
            {
                "restaurant_name": "Spice Garden",
                "category_name": "South Indian",
                "name": "Masala Dosa",
                "description": "Crisp golden crepe filled with spiced potato masala, served with coconut chutney and piping hot drumstick sambar.",
                "price": 80.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 10,
                "ingredients": "Fermented rice batter, potato masala, ghee, mustard seeds, curry leaves",
                "allergens": "None",
                "image_url": "https://images.unsplash.com/photo-1668236543090-82eba5ee5976?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.9,
                "dietary_tags": "Vegetarian, Jain Available"
            },
            {
                "restaurant_name": "Spice Garden",
                "category_name": "South Indian",
                "name": "Idli Vada",
                "description": "Two melt-in-mouth steamed rice cakes and one crunchy medu vada served with freshly grated coconut chutney and tomato rasam.",
                "price": 60.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 8,
                "ingredients": "Rice, urad dal, curry leaves, peppercorns, cumin",
                "allergens": "None",
                "image_url": "https://images.unsplash.com/photo-1589301760014-d929f3979dbc?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": True,
                "rating": 4.7,
                "dietary_tags": "Vegetarian, Vegan, Gluten-Free"
            },
            {
                "restaurant_name": "Spice Garden",
                "category_name": "North Indian",
                "name": "Paneer Butter Masala",
                "description": "Tender cubes of fresh cottage cheese simmered in a luscious cashew, tomato, and butter gravy with aromatic kasuri methi.",
                "price": 220.0,
                "discount_price": 199.0,
                "is_veg": True,
                "prep_time_minutes": 18,
                "ingredients": "Fresh paneer, ripe tomatoes, butter, cashew paste, fresh cream, garam masala",
                "allergens": "Dairy, Tree Nuts",
                "image_url": "https://images.unsplash.com/photo-1631452180519-c014fe946bc7?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.8,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Spice Garden",
                "category_name": "Biryani",
                "name": "Veg Biryani",
                "description": "Long-grain aged basmati rice layered with garden-fresh veggies, mint leaves, saffron, and aromatic whole spices.",
                "price": 160.0,
                "discount_price": 149.0,
                "is_veg": True,
                "prep_time_minutes": 20,
                "ingredients": "Basmati rice, carrots, beans, peas, cauliflower, saffron, fried onions, mint",
                "allergens": "Dairy",
                "image_url": "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.6,
                "dietary_tags": "Vegetarian, Jain Available"
            },
            {
                "restaurant_name": "Spice Garden",
                "category_name": "North Indian",
                "name": "Butter Naan",
                "description": "Fluffy, pillowy Indian flatbread baked in tandoor and brushed generously with salted butter.",
                "price": 45.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 6,
                "ingredients": "Refined flour, yogurt, butter, milk, nigella seeds",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1601050690597-df0568f70950?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": False,
                "rating": 4.5,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Spice Garden",
                "category_name": "Chinese",
                "name": "Gobi Manchurian",
                "description": "Crispy cauliflower florets tossed in a wok with garlic, ginger, spring onions, and spicy dark soya glaze.",
                "price": 140.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 14,
                "ingredients": "Cauliflower, corn flour, soy sauce, green chilli sauce, scallions",
                "allergens": "Soy, Gluten",
                "image_url": "https://images.unsplash.com/photo-1569058242253-92a9c755a0ec?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": False,
                "rating": 4.6,
                "dietary_tags": "Vegetarian, Vegan"
            },
            {
                "restaurant_name": "Spice Garden",
                "category_name": "Chinese",
                "name": "Veg Fried Rice",
                "description": "Fragrant stir-fried basmati rice tossed with shredded bell peppers, carrots, spring onions, and light soya sauce.",
                "price": 130.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 12,
                "ingredients": "Basmati rice, bell peppers, carrots, scallions, sesame oil, soy sauce",
                "allergens": "Soy",
                "image_url": "https://images.unsplash.com/photo-1603133872878-684f208fb84b?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": False,
                "rating": 4.4,
                "dietary_tags": "Vegetarian, Vegan"
            },
            {
                "restaurant_name": "Spice Garden",
                "category_name": "South Indian",
                "name": "South Indian Meals",
                "description": "Full traditional thali: Steamed rice, sambar, rasam, kootu, poriyal, curd, papad, pickle, and payasam dessert.",
                "price": 120.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 10,
                "ingredients": "Rice, toor dal, seasonal vegetables, coconut, curd, ghee, spices",
                "allergens": "Dairy",
                "image_url": "https://images.unsplash.com/photo-1610057099443-fde8c4d50f91?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.9,
                "dietary_tags": "Vegetarian"
            },

            # Restaurant 2: Pizza Palace
            {
                "restaurant_name": "Pizza Palace",
                "category_name": "Pizza",
                "name": "Margherita Pizza",
                "description": "Classic Italian masterpiece with Italian plum tomato sauce, fresh mozzarella Fior di Latte, and aromatic fresh basil leaves.",
                "price": 149.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 15,
                "ingredients": "Sourdough crust, San Marzano tomatoes, fresh mozzarella, extra virgin olive oil, basil",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1574071318508-1cdbab80d002?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.7,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Pizza Palace",
                "category_name": "Pizza",
                "name": "Farmhouse Pizza",
                "description": "Loaded with crisp bell peppers, sweet corn kernels, button mushrooms, ripe red onions, and melted mozzarella.",
                "price": 249.0,
                "discount_price": 229.0,
                "is_veg": True,
                "prep_time_minutes": 18,
                "ingredients": "Pizza dough, tomato sauce, mozzarella, bell peppers, corn, mushrooms, red onions",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.8,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Pizza Palace",
                "category_name": "Pizza",
                "name": "Paneer Pizza",
                "description": "Indian fusion delight topped with spicy marinated tandoori paneer cubes, roasted capsicum, and melted cheddar.",
                "price": 229.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 16,
                "ingredients": "Pizza crust, tandoori paneer, mozzarella, capsicum, onion, tandoori sauce",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": True,
                "rating": 4.6,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Pizza Palace",
                "category_name": "Pizza",
                "name": "Veg Supreme Pizza",
                "description": "The ultimate veggie fiesta with black olives, jalapeños, red paprika, mushrooms, baby corn, and mozzarella cheese.",
                "price": 299.0,
                "discount_price": 269.0,
                "is_veg": True,
                "prep_time_minutes": 20,
                "ingredients": "Crust, black olives, pickled jalapenos, red paprika, mushrooms, mozzarella",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1534308983496-4fabb1a015ee?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": False,
                "rating": 4.7,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Pizza Palace",
                "category_name": "Snacks",
                "name": "Garlic Bread",
                "description": "Warm artisanal baguettes infused with crushed garlic butter, fresh parsley, and melted cheese dip on the side.",
                "price": 99.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 10,
                "ingredients": "French bread, butter, minced garlic, oregano, parsley",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1619535860434-ba1d8fa12536?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.8,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Pizza Palace",
                "category_name": "Pizza",
                "name": "Cheese Burst Pizza",
                "description": "Crust filled to the brim with warm molten liquid cheese that bursts with flavor in every single bite.",
                "price": 279.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 20,
                "ingredients": "Double layered dough, cheddar cheese spread, mozzarella, oregano seasoning",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1593560708920-61dd98c46a4e?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": False,
                "rating": 4.5,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Pizza Palace",
                "category_name": "Snacks",
                "name": "French Fries",
                "description": "Golden crispy potato batons fried to perfection and seasoned with Himalayan pink salt.",
                "price": 89.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 8,
                "ingredients": "Potatoes, sunflower oil, salt",
                "allergens": "None",
                "image_url": "https://images.unsplash.com/photo-1576107232684-1279f3908594?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": False,
                "rating": 4.5,
                "dietary_tags": "Vegetarian, Vegan, Gluten-Free"
            },
            {
                "restaurant_name": "Pizza Palace",
                "category_name": "Desserts",
                "name": "Chocolate Brownie",
                "description": "Warm, fudgy Belgian dark chocolate brownie topped with chocolate fudge sauce and roasted walnut bits.",
                "price": 99.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 5,
                "ingredients": "Dark chocolate, cocoa butter, sugar, flour, walnuts",
                "allergens": "Gluten, Dairy, Tree Nuts",
                "image_url": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.9,
                "dietary_tags": "Vegetarian"
            },

            # Restaurant 3: Burger Hub
            {
                "restaurant_name": "Burger Hub",
                "category_name": "Burgers",
                "name": "Classic Veg Burger",
                "description": "Seasoned crispy vegetable patty topped with crunchy iceberg lettuce, ripe tomato slice, and creamy mayo in a toasted sesame bun.",
                "price": 99.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 10,
                "ingredients": "Potato and peas patty, sesame bun, lettuce, tomato, eggless mayo",
                "allergens": "Gluten",
                "image_url": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.6,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Burger Hub",
                "category_name": "Burgers",
                "name": "Cheese Burger",
                "description": "Double melted American cheddar draped over a seasoned crispy patty with tangy gherkins and smoky BBQ sauce.",
                "price": 129.0,
                "discount_price": 119.0,
                "is_veg": True,
                "prep_time_minutes": 12,
                "ingredients": "Veggie patty, brioche bun, cheddar cheese slice, pickles, smoky burger sauce",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": False,
                "rating": 4.7,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Burger Hub",
                "category_name": "Burgers",
                "name": "Paneer Burger",
                "description": "Thick slice of marinated grilled paneer steak coated in crispy crumb, layered with spicy chipotle slaw.",
                "price": 149.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 14,
                "ingredients": "Fresh paneer slab, breadcrumbs, chipotle sauce, purple cabbage slaw, bun",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1520072959219-c595dc870360?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": True,
                "rating": 4.8,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Burger Hub",
                "category_name": "Burgers",
                "name": "Crispy Veg Burger",
                "description": "Extra crunchy patty packed with sweet corn, carrots, and potatoes, topped with mustard relish.",
                "price": 119.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 10,
                "ingredients": "Corn and potato patty, mustard sauce, onion rings, brioche bun",
                "allergens": "Gluten",
                "image_url": "https://images.unsplash.com/photo-1572802419224-296b0aeee0d9?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": False,
                "rating": 4.4,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Burger Hub",
                "category_name": "Snacks",
                "name": "Peri Peri Fries",
                "description": "Crispy golden skin-on fries tossed in hot and zesty African bird's eye peri-peri seasoning.",
                "price": 99.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 8,
                "ingredients": "Potatoes, peri peri spice mix, garlic powder, paprika, salt",
                "allergens": "None",
                "image_url": "https://images.unsplash.com/photo-1585109649139-366815a0d713?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.8,
                "dietary_tags": "Vegetarian, Vegan, Gluten-Free"
            },
            {
                "restaurant_name": "Burger Hub",
                "category_name": "Snacks",
                "name": "Veg Wrap",
                "description": "Toasted whole-wheat tortilla rolled with crispy veg fingers, shredded lettuce, mint mayo, and tangy onions.",
                "price": 129.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 10,
                "ingredients": "Tortilla flatbread, vegetable fingers, pickled onion, mint sauce",
                "allergens": "Gluten",
                "image_url": "https://images.unsplash.com/photo-1626700051175-6818013e1d4f?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": False,
                "rating": 4.5,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Burger Hub",
                "category_name": "Snacks",
                "name": "Club Sandwich",
                "description": "Triple-decker toasted sourdough sandwich layered with sliced cucumber, tomato, cheese slice, and seasoned potato filling.",
                "price": 139.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 12,
                "ingredients": "Sourdough bread, cheese slice, butter, green chutney, tomato, cucumber",
                "allergens": "Gluten, Dairy",
                "image_url": "https://images.unsplash.com/photo-1528735602780-2552fd46c7af?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": True,
                "rating": 4.6,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Burger Hub",
                "category_name": "Beverages",
                "name": "Chocolate Shake",
                "description": "Thick milkshake blended with creamy whole milk, rich Belgian dark chocolate ice cream, and chocolate syrup drizzle.",
                "price": 119.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 5,
                "ingredients": "Whole milk, chocolate ice cream, cocoa powder, chocolate syrup",
                "allergens": "Dairy",
                "image_url": "https://images.unsplash.com/photo-1572490122747-3968b75cc699?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.9,
                "dietary_tags": "Vegetarian"
            },

            # Restaurant 4: Royal Kitchen
            {
                "restaurant_name": "Royal Kitchen",
                "category_name": "Biryani",
                "name": "Chicken Biryani",
                "description": "Royal Hyderabadi Dum Biryani with succulent chicken pieces marinated in yogurt and saffron, slow-cooked under sealed dough.",
                "price": 199.0,
                "discount_price": 189.0,
                "is_veg": False,
                "prep_time_minutes": 25,
                "ingredients": "Tender chicken, basmati rice, saffron, fried onions, desi ghee, star anise, cardamom",
                "allergens": "Dairy",
                "image_url": "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.9,
                "dietary_tags": "Halal"
            },
            {
                "restaurant_name": "Royal Kitchen",
                "category_name": "North Indian",
                "name": "Butter Chicken",
                "description": "Classic Murgh Makhani: Charcoal-grilled boneless tandoori chicken cooked in velvety tomato, butter, and cream gravy.",
                "price": 249.0,
                "discount_price": 229.0,
                "is_veg": False,
                "prep_time_minutes": 22,
                "ingredients": "Boneless chicken, butter, heavy cream, tomato puree, cashew nut paste, kasuri methi",
                "allergens": "Dairy, Tree Nuts",
                "image_url": "https://images.unsplash.com/photo-1603894584373-5ac82b2ae398?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.8,
                "dietary_tags": "Halal"
            },
            {
                "restaurant_name": "Royal Kitchen",
                "category_name": "Chinese",
                "name": "Chicken Fried Rice",
                "description": "Wok-tossed long grain rice with shredded tender chicken breast, scrambled eggs, scallions, and light pepper.",
                "price": 179.0,
                "discount_price": None,
                "is_veg": False,
                "prep_time_minutes": 15,
                "ingredients": "Basmati rice, chicken breast, egg, green onions, soy sauce, sesame oil",
                "allergens": "Eggs, Soy",
                "image_url": "https://images.unsplash.com/photo-1603133872878-684f208fb84b?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": False,
                "rating": 4.6,
                "dietary_tags": "Non-Veg"
            },
            {
                "restaurant_name": "Royal Kitchen",
                "category_name": "North Indian",
                "name": "Egg Curry",
                "description": "Two golden-fried farm boiled eggs immersed in a robust onion-tomato gravy with freshly ground aromatic spices.",
                "price": 120.0,
                "discount_price": None,
                "is_veg": False,
                "prep_time_minutes": 14,
                "ingredients": "Boiled eggs, onion gravy, tomatoes, coriander seeds, turmeric, ginger",
                "allergens": "Eggs",
                "image_url": "https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": False,
                "rating": 4.5,
                "dietary_tags": "Non-Veg"
            },
            {
                "restaurant_name": "Royal Kitchen",
                "category_name": "North Indian",
                "name": "Paneer Tikka",
                "description": "Succulent cubes of fresh cottage cheese, capsicum, and onions marinated in spiced hung curd and skewered in clay tandoor.",
                "price": 189.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 15,
                "ingredients": "Paneer cubes, hung yogurt, mustard oil, carom seeds, bell peppers, chaat masala",
                "allergens": "Dairy",
                "image_url": "https://images.unsplash.com/photo-1599488615731-7e5c2823ff28?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.7,
                "dietary_tags": "Vegetarian, Gluten-Free"
            },
            {
                "restaurant_name": "Royal Kitchen",
                "category_name": "North Indian",
                "name": "Dal Makhani",
                "description": "Black lentils and red kidney beans simmered overnight on low flame with cultured butter, cream, and ginger juliennes.",
                "price": 149.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 12,
                "ingredients": "Whole urad dal, rajma, white butter, fresh cream, tomato puree",
                "allergens": "Dairy",
                "image_url": "https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.9,
                "dietary_tags": "Vegetarian"
            },
            {
                "restaurant_name": "Royal Kitchen",
                "category_name": "North Indian",
                "name": "Jeera Rice",
                "description": "Fragrant aged basmati rice tempered with golden cumin seeds and pure desi cow ghee.",
                "price": 99.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 8,
                "ingredients": "Basmati rice, cumin seeds, desi ghee, coriander",
                "allergens": "Dairy",
                "image_url": "https://images.unsplash.com/photo-1512058564366-18510be2db19?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": False,
                "is_recommended": False,
                "rating": 4.4,
                "dietary_tags": "Vegetarian, Gluten-Free"
            },
            {
                "restaurant_name": "Royal Kitchen",
                "category_name": "Desserts",
                "name": "Gulab Jamun",
                "description": "Two warm, soft milk-solid dumplings steeped in cardamom and saffron infused rose sugar syrup.",
                "price": 60.0,
                "discount_price": None,
                "is_veg": True,
                "prep_time_minutes": 4,
                "ingredients": "Khoya milk solids, refined flour, cardamom syrup, rose water, pistachio garnish",
                "allergens": "Dairy, Gluten, Tree Nuts",
                "image_url": "https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=600&auto=format&fit=crop&q=80",
                "is_bestseller": True,
                "is_recommended": True,
                "rating": 4.9,
                "dietary_tags": "Vegetarian"
            }
        ]

        created_menu_items = []
        for item_info in food_items_data:
            rest_obj = rest_map.get(item_info["restaurant_name"])
            cat_obj = cat_map.get(item_info["category_name"])
            
            menu_item = MenuItem(
                restaurant_id=rest_obj.id,
                category_id=cat_obj.id,
                name=item_info["name"],
                description=item_info["description"],
                image_url=item_info["image_url"],
                price=item_info["price"],
                discount_price=item_info["discount_price"],
                is_veg=item_info["is_veg"],
                prep_time_minutes=item_info["prep_time_minutes"],
                ingredients=item_info["ingredients"],
                allergens=item_info["allergens"],
                is_available=True,
                rating=item_info["rating"],
                total_ratings=random.randint(25, 120),
                total_orders_count=random.randint(40, 260),
                is_bestseller=item_info["is_bestseller"],
                is_recommended=item_info["is_recommended"],
                dietary_tags=item_info["dietary_tags"],
                created_at=now_utc() - timedelta(days=45)
            )
            session.add(menu_item)
            session.commit()
            session.refresh(menu_item)
            created_menu_items.append(menu_item)

        # 5. Seed Inventory Ingredients (15+ items across restaurants)
        today = date.today()
        ingredients_seed = [
            # For Spice Garden
            {"restaurant_id": rest_map["Spice Garden"].id, "name": "Dosa Batter (Fermented)", "category": "Grain", "unit": "kg", "current_stock": 25.0, "reorder_level": 8.0, "cost_per_unit": 40.0, "expiry_date": today + timedelta(days=2)},
            {"restaurant_id": rest_map["Spice Garden"].id, "name": "Fresh Paneer", "category": "Dairy", "unit": "kg", "current_stock": 4.5, "reorder_level": 5.0, "cost_per_unit": 320.0, "expiry_date": today + timedelta(days=3)},
            {"restaurant_id": rest_map["Spice Garden"].id, "name": "Desi Ghee", "category": "Dairy", "unit": "kg", "current_stock": 18.0, "reorder_level": 4.0, "cost_per_unit": 550.0, "expiry_date": today + timedelta(days=90)},
            {"restaurant_id": rest_map["Spice Garden"].id, "name": "Basmati Rice (Aged)", "category": "Grain", "unit": "kg", "current_stock": 60.0, "reorder_level": 15.0, "cost_per_unit": 85.0, "expiry_date": today + timedelta(days=180)},
            {"restaurant_id": rest_map["Spice Garden"].id, "name": "Fresh Cauliflower", "category": "Produce", "unit": "kg", "current_stock": 3.0, "reorder_level": 5.0, "cost_per_unit": 35.0, "expiry_date": today + timedelta(days=2)},
            {"restaurant_id": rest_map["Spice Garden"].id, "name": "Cashew Nuts (Raw)", "category": "Spices", "unit": "kg", "current_stock": 2.0, "reorder_level": 3.0, "cost_per_unit": 800.0, "expiry_date": today + timedelta(days=60)},
            
            # For Pizza Palace
            {"restaurant_id": rest_map["Pizza Palace"].id, "name": "Mozzarella Cheese", "category": "Dairy", "unit": "kg", "current_stock": 3.8, "reorder_level": 6.0, "cost_per_unit": 450.0, "expiry_date": today + timedelta(days=5)},
            {"restaurant_id": rest_map["Pizza Palace"].id, "name": "San Marzano Pizza Sauce", "category": "Produce", "unit": "kg", "current_stock": 15.0, "reorder_level": 5.0, "cost_per_unit": 120.0, "expiry_date": today + timedelta(days=30)},
            {"restaurant_id": rest_map["Pizza Palace"].id, "name": "Sourdough Flour", "category": "Bakery", "unit": "kg", "current_stock": 40.0, "reorder_level": 10.0, "cost_per_unit": 65.0, "expiry_date": today + timedelta(days=90)},
            {"restaurant_id": rest_map["Pizza Palace"].id, "name": "Fresh Button Mushrooms", "category": "Produce", "unit": "kg", "current_stock": 1.5, "reorder_level": 3.0, "cost_per_unit": 180.0, "expiry_date": today + timedelta(days=1)},

            # For Burger Hub
            {"restaurant_id": rest_map["Burger Hub"].id, "name": "Sesame Brioche Buns", "category": "Bakery", "unit": "pcs", "current_stock": 85.0, "reorder_level": 30.0, "cost_per_unit": 12.0, "expiry_date": today + timedelta(days=4)},
            {"restaurant_id": rest_map["Burger Hub"].id, "name": "Crispy Veg Patties", "category": "Produce", "unit": "pcs", "current_stock": 12.0, "reorder_level": 25.0, "cost_per_unit": 28.0, "expiry_date": today + timedelta(days=20)},
            {"restaurant_id": rest_map["Burger Hub"].id, "name": "Belgian Chocolate Ice Cream", "category": "Dairy", "unit": "kg", "current_stock": 8.0, "reorder_level": 3.0, "cost_per_unit": 350.0, "expiry_date": today + timedelta(days=45)},

            # For Royal Kitchen
            {"restaurant_id": rest_map["Royal Kitchen"].id, "name": "Fresh Farm Chicken", "category": "Meat", "unit": "kg", "current_stock": 20.0, "reorder_level": 8.0, "cost_per_unit": 190.0, "expiry_date": today + timedelta(days=2)},
            {"restaurant_id": rest_map["Royal Kitchen"].id, "name": "Kashmir Saffron Threads", "category": "Spices", "unit": "grams", "current_stock": 15.0, "reorder_level": 5.0, "cost_per_unit": 280.0, "expiry_date": today + timedelta(days=365)},
            {"restaurant_id": rest_map["Royal Kitchen"].id, "name": "Black Urad Dal", "category": "Grain", "unit": "kg", "current_stock": 35.0, "reorder_level": 10.0, "cost_per_unit": 110.0, "expiry_date": today + timedelta(days=120)},
        ]

        created_ingredients = {}
        for ing_data in ingredients_seed:
            is_low = ing_data["current_stock"] <= ing_data["reorder_level"]
            ing = Ingredient(**ing_data, is_low_stock=is_low, updated_at=now_utc())
            session.add(ing)
            session.commit()
            session.refresh(ing)
            created_ingredients[ing.name] = ing

        # 6. Seed Recipe Items (linking menu items to ingredients)
        item_by_name = {m.name: m for m in created_menu_items}
        recipe_links = [
            ("Masala Dosa", "Dosa Batter (Fermented)", 0.25),
            ("Masala Dosa", "Desi Ghee", 0.03),
            ("Paneer Butter Masala", "Fresh Paneer", 0.20),
            ("Paneer Butter Masala", "Cashew Nuts (Raw)", 0.04),
            ("Gobi Manchurian", "Fresh Cauliflower", 0.25),
            ("Veg Biryani", "Basmati Rice (Aged)", 0.20),
            ("Margherita Pizza", "Sourdough Flour", 0.22),
            ("Margherita Pizza", "San Marzano Pizza Sauce", 0.08),
            ("Margherita Pizza", "Mozzarella Cheese", 0.12),
            ("Farmhouse Pizza", "Fresh Button Mushrooms", 0.08),
            ("Farmhouse Pizza", "Mozzarella Cheese", 0.12),
            ("Classic Veg Burger", "Sesame Brioche Buns", 1.0),
            ("Classic Veg Burger", "Crispy Veg Patties", 1.0),
            ("Chocolate Shake", "Belgian Chocolate Ice Cream", 0.15),
            ("Chicken Biryani", "Fresh Farm Chicken", 0.25),
            ("Chicken Biryani", "Basmati Rice (Aged)", 0.20),
            ("Butter Chicken", "Fresh Farm Chicken", 0.25),
            ("Dal Makhani", "Black Urad Dal", 0.15)
        ]

        for item_name, ing_name, qty in recipe_links:
            if item_name in item_by_name and ing_name in created_ingredients:
                r_item = RecipeItem(
                    menu_item_id=item_by_name[item_name].id,
                    ingredient_id=created_ingredients[ing_name].id,
                    quantity_required=qty
                )
                session.add(r_item)
        session.commit()

        # 7. Seed Historical Orders (20+ realistic orders for Scikit-learn training & Chart.js analytics)
        print("Generating historical orders and training dataset...")
        spice_rest = rest_map["Spice Garden"]
        pizza_rest = rest_map["Pizza Palace"]
        burger_rest = rest_map["Burger Hub"]
        royal_rest = rest_map["Royal Kitchen"]

        historical_orders_spec = [
            (spice_rest, "Masala Dosa", 2, OrderStatus.DELIVERED, 10, 13),
            (spice_rest, "Veg Biryani", 1, OrderStatus.DELIVERED, 10, 20),
            (pizza_rest, "Margherita Pizza", 2, OrderStatus.DELIVERED, 9, 19),
            (pizza_rest, "Farmhouse Pizza", 1, OrderStatus.DELIVERED, 9, 21),
            (burger_rest, "Classic Veg Burger", 2, OrderStatus.DELIVERED, 8, 14),
            (burger_rest, "Peri Peri Fries", 2, OrderStatus.DELIVERED, 8, 18),
            (royal_rest, "Chicken Biryani", 2, OrderStatus.DELIVERED, 7, 13),
            (royal_rest, "Butter Chicken", 1, OrderStatus.DELIVERED, 7, 20),
            (spice_rest, "Paneer Butter Masala", 1, OrderStatus.DELIVERED, 6, 20),
            (spice_rest, "South Indian Meals", 2, OrderStatus.DELIVERED, 6, 13),
            (pizza_rest, "Cheese Burst Pizza", 1, OrderStatus.DELIVERED, 5, 20),
            (burger_rest, "Paneer Burger", 2, OrderStatus.DELIVERED, 5, 19),
            (royal_rest, "Dal Makhani", 2, OrderStatus.DELIVERED, 4, 13),
            (royal_rest, "Chicken Biryani", 3, OrderStatus.DELIVERED, 4, 21),
            (spice_rest, "Masala Dosa", 3, OrderStatus.DELIVERED, 3, 9),
            (spice_rest, "Gobi Manchurian", 2, OrderStatus.DELIVERED, 3, 19),
            (pizza_rest, "Farmhouse Pizza", 2, OrderStatus.DELIVERED, 2, 20),
            (burger_rest, "Chocolate Shake", 2, OrderStatus.DELIVERED, 2, 16),
            (royal_rest, "Butter Chicken", 2, OrderStatus.DELIVERED, 1, 20),
            (spice_rest, "Paneer Butter Masala", 2, OrderStatus.DELIVERED, 1, 13),
        ]

        for idx, (rest, item_name, qty, st, days_ago, hour) in enumerate(historical_orders_spec):
            item = item_by_name.get(item_name)
            subtotal = (item.discount_price or item.price) * qty
            tax = round(subtotal * 0.05, 2)
            deliv_fee = 30.0
            total = subtotal + tax + deliv_fee
            created_time = now_utc() - timedelta(days=days_ago)
            created_time = created_time.replace(hour=hour, minute=random.randint(5, 50))

            order = Order(
                order_number=f"ORD-2026-H{100 + idx}",
                customer_id=customer_user.id,
                restaurant_id=rest.id,
                delivery_partner_id=delivery_user.id,
                status=st,
                subtotal=subtotal,
                tax=tax,
                delivery_fee=deliv_fee,
                discount=0.0,
                total_amount=total,
                payment_method=PaymentMethod.ONLINE if idx % 2 == 0 else PaymentMethod.COD,
                payment_status=PaymentStatus.SUCCESS,
                transaction_id=f"TXN-HIST-{1000 + idx}",
                delivery_address="Flat 402, Green Glen Layout, Bellandur, Bangalore",
                estimated_prep_minutes=item.prep_time_minutes,
                estimated_delivery_minutes=35,
                priority_score=1.0,
                created_at=created_time,
                updated_at=created_time + timedelta(minutes=35)
            )
            session.add(order)
            session.commit()
            session.refresh(order)

            oi = OrderItem(
                order_id=order.id,
                menu_item_id=item.id,
                item_name=item.name,
                quantity=qty,
                unit_price=item.discount_price or item.price,
                total_price=subtotal
            )
            session.add(oi)

            sh = OrderStatusHistory(
                order_id=order.id,
                status=OrderStatus.DELIVERED,
                notes="Delivered successfully",
                changed_by_role="delivery_partner",
                timestamp=created_time + timedelta(minutes=35)
            )
            session.add(sh)
            session.commit()

        # 8. Seed 5 Active Orders in different workflow stages
        active_orders_spec = [
            (spice_rest, "Masala Dosa", 2, OrderStatus.PENDING, 4, 32.5),
            (spice_rest, "Paneer Butter Masala", 1, OrderStatus.CONFIRMED, 12, 45.0),
            (pizza_rest, "Farmhouse Pizza", 1, OrderStatus.PREPARING, 18, 55.0),
            (burger_rest, "Classic Veg Burger", 2, OrderStatus.READY, 22, 65.0),
            (royal_rest, "Chicken Biryani", 1, OrderStatus.OUT_FOR_DELIVERY, 28, 75.0),
        ]

        for idx, (rest, item_name, qty, st, mins_ago, p_score) in enumerate(active_orders_spec):
            item = item_by_name.get(item_name)
            subtotal = (item.discount_price or item.price) * qty
            tax = round(subtotal * 0.05, 2)
            total = subtotal + tax + 30.0
            order_time = now_utc() - timedelta(minutes=mins_ago)

            active_order = Order(
                order_number=f"ORD-2026-LIVE{idx + 1}",
                customer_id=customer_user.id,
                restaurant_id=rest.id,
                delivery_partner_id=delivery_user.id if st in [OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY] else None,
                status=st,
                subtotal=subtotal,
                tax=tax,
                delivery_fee=30.0,
                discount=0.0,
                total_amount=total,
                payment_method=PaymentMethod.ONLINE if idx % 2 == 0 else PaymentMethod.COD,
                payment_status=PaymentStatus.SUCCESS if idx % 2 == 0 else PaymentStatus.PENDING,
                transaction_id=f"LIVE-PAY-{200 + idx}",
                delivery_address="Flat 402, Green Glen Layout, Bellandur, Bangalore",
                customer_notes="Please ring bell twice and leave package at door.",
                estimated_prep_minutes=item.prep_time_minutes,
                estimated_delivery_minutes=30,
                priority_score=p_score,
                created_at=order_time,
                updated_at=order_time
            )
            session.add(active_order)
            session.commit()
            session.refresh(active_order)

            oi = OrderItem(
                order_id=active_order.id,
                menu_item_id=item.id,
                item_name=item.name,
                quantity=qty,
                unit_price=item.discount_price or item.price,
                total_price=subtotal
            )
            session.add(oi)

            sh = OrderStatusHistory(
                order_id=active_order.id,
                status=st,
                notes=f"Order is currently {st.value}",
                changed_by_role="system",
                timestamp=order_time
            )
            session.add(sh)
            session.commit()

        # 9. Seed Food Waste Records
        waste_samples = [
            (spice_rest, "Fresh Cauliflower", 1.5, "kg", "Over-prepared", 52.5, "Optimize weekend prep batches using ML demand forecast"),
            (pizza_rest, "Fresh Button Mushrooms", 0.8, "kg", "Near-expiry disposal", 144.0, "Feature mushrooms in daily special discount combo"),
            (burger_rest, "Sesame Brioche Buns", 6.0, "pcs", "Stale / Bakery shelf life", 72.0, "Adjust daily bun order quantity using Scikit-learn trend"),
            (royal_rest, "Fresh Farm Chicken", 1.2, "kg", "Preparation trim loss", 228.0, "Standardize butchering yield protocol")
        ]

        for rest, ing_name, qty, unit, reason, loss, action in waste_samples:
            w_rec = FoodWasteRecord(
                restaurant_id=rest.id,
                ingredient_name=ing_name,
                quantity_wasted=qty,
                unit=unit,
                reason=reason,
                estimated_loss_amount=loss,
                prevention_recommendation=action,
                recorded_at=now_utc() - timedelta(days=random.randint(1, 5))
            )
            session.add(w_rec)

        # 10. Seed Customer Reviews and Favorites
        reviews_data = [
            ("Spice Garden", "Masala Dosa", 5.0, "Outstanding crispiness! The coconut chutney and sambar are authentically South Indian. Highly recommended!"),
            ("Spice Garden", "Paneer Butter Masala", 5.0, "Super creamy gravy with melt in mouth paneer. Perfect with butter naan."),
            ("Pizza Palace", "Farmhouse Pizza", 4.5, "Fresh crunchy toppings and genuine wood-fired flavor. Fast delivery too!"),
            ("Burger Hub", "Classic Veg Burger", 4.5, "Crispy patty and delicious mayo. Great value for ₹99."),
            ("Royal Kitchen", "Chicken Biryani", 5.0, "Aromatic long grain rice and tender succulent meat. Best dum biryani in Bangalore.")
        ]

        for r_name, item_name, rating_val, comment in reviews_data:
            r_obj = rest_map.get(r_name)
            item_obj = item_by_name.get(item_name)
            rev = Review(
                customer_id=customer_user.id,
                restaurant_id=r_obj.id,
                menu_item_id=item_obj.id if item_obj else None,
                rating=rating_val,
                comment=comment,
                customer_name="Aarav Sharma",
                created_at=now_utc() - timedelta(days=random.randint(1, 8))
            )
            session.add(rev)

        # Favorites
        fav1 = Favorite(customer_id=customer_user.id, restaurant_id=spice_rest.id, created_at=now_utc())
        fav2 = Favorite(customer_id=customer_user.id, menu_item_id=item_by_name["Masala Dosa"].id, created_at=now_utc())
        fav3 = Favorite(customer_id=customer_user.id, menu_item_id=item_by_name["Paneer Butter Masala"].id, created_at=now_utc())
        session.add(fav1)
        session.add(fav2)
        session.add(fav3)

        session.commit()
        print("AI Foodie seed data successfully populated!")

if __name__ == "__main__":
    run_seed()
