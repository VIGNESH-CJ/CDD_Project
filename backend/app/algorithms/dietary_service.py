from typing import List, Dict, Any, Optional
import re
from sqlmodel import Session, select
from app.models.menu import MenuItem
from app.models.category import Category
from app.models.user import CustomerPreference

# Common allergen aliases & ingredient mappings
ALLERGEN_SYNONYMS: Dict[str, List[str]] = {
    "nut": ["nut", "nuts", "tree nut", "tree nuts", "peanut", "peanuts", "almond", "almonds", "cashew", "cashews", "walnut", "walnuts", "pistachio", "pistachios"],
    "nuts": ["nut", "nuts", "tree nut", "tree nuts", "peanut", "peanuts", "almond", "almonds", "cashew", "cashews", "walnut", "walnuts", "pistachio", "pistachios"],
    "peanut": ["peanut", "peanuts", "groundnut"],
    "peanuts": ["peanut", "peanuts", "groundnut"],
    "dairy": ["dairy", "milk", "butter", "cream", "cheese", "paneer", "curd", "yogurt", "ghee", "whey", "makkhan"],
    "milk": ["dairy", "milk", "butter", "cream", "cheese", "paneer", "curd", "yogurt", "ghee", "whey"],
    "gluten": ["gluten", "wheat", "maida", "flour", "atta", "barley", "rye", "bread", "crust", "pasta"],
    "wheat": ["wheat", "gluten", "maida", "flour", "atta"],
    "soy": ["soy", "soya", "edamame", "tofu", "soy sauce"],
    "egg": ["egg", "eggs", "mayonnaise", "albumen"],
    "eggs": ["egg", "eggs", "mayonnaise", "albumen"],
    "shellfish": ["shellfish", "prawn", "prawns", "shrimp", "crab", "lobster", "oyster", "clam"],
    "fish": ["fish", "salmon", "tuna"],
}

CUSTOMIZABLE_GARNISHES = ["cashew", "cashews", "almond", "almonds", "nuts", "butter", "cheese", "cream", "ghee"]

def normalize_allergy_terms(raw_allergens: Optional[str]) -> List[str]:
    """Parse comma/semicolon separated allergen strings into clean unique list."""
    if not raw_allergens:
        return []
    cleaned = []
    for term in re.split(r"[,;|]", raw_allergens):
        t = term.strip().casefold()
        if t and t not in {"none", "n/a", "no allergies", "nil", "nothing"}:
            cleaned.append(t)
    return list(dict.fromkeys(cleaned))

def detect_allergens_in_item(item: MenuItem, target_allergens: List[str]) -> List[str]:
    """Return all target allergens detected in the item's allergens and ingredients."""
    if not target_allergens:
        return []
    
    haystack = f"{item.allergens or ''} {item.ingredients or ''}".casefold()
    detected = []
    
    for allergen in target_allergens:
        synonyms = ALLERGEN_SYNONYMS.get(allergen, [allergen])
        for syn in synonyms:
            # Word boundary regex search
            pattern = rf"(?<![a-z0-9]){re.escape(syn)}(?![a-z0-9])"
            if re.search(pattern, haystack):
                detected.append(allergen)
                break
    return detected

def check_dietary_compliance(item: MenuItem, dietary_pref: str) -> tuple[bool, str]:
    """
    Check if item satisfies dietary preference.
    Returns (is_compliant, reason_if_not).
    """
    pref = dietary_pref.strip().casefold()
    if not pref or pref in {"any", "all", "no preference", "none"}:
        return True, ""
    
    tags = (item.dietary_tags or "").casefold().replace("-", " ")
    ingredients = (item.ingredients or "").casefold()

    if pref in {"veg", "vegetarian"}:
        if not item.is_veg:
            return False, "Contains non-vegetarian ingredients"
        return True, ""

    if pref == "vegan":
        if not item.is_veg:
            return False, "Contains meat/poultry"
        dairy_hits = [w for w in ["milk", "dairy", "butter", "cream", "cheese", "paneer", "ghee", "honey", "curd"] if re.search(rf"(?<![a-z0-9]){w}(?![a-z0-9])", ingredients)]
        if dairy_hits:
            return False, f"Contains animal by-products ({', '.join(dairy_hits)})"
        if "vegan" not in tags and "plant" not in tags:
            return False, "Not certified vegan"
        return True, ""

    if pref == "jain":
        if not item.is_veg:
            return False, "Non-vegetarian"
        root_veg = [w for w in ["onion", "garlic", "potato", "carrot", "radish", "ginger"] if re.search(rf"(?<![a-z0-9]){w}(?![a-z0-9])", ingredients)]
        if root_veg:
            return False, f"Contains root vegetables ({', '.join(root_veg)})"
        if "jain" not in tags:
            return False, "Not certified Jain preparation"
        return True, ""

    if pref in {"gluten-free", "gluten free"}:
        gluten_hits = [w for w in ["wheat", "gluten", "maida", "flour", "atta"] if re.search(rf"(?<![a-z0-9]){w}(?![a-z0-9])", ingredients) or re.search(rf"(?<![a-z0-9]){w}(?![a-z0-9])", (item.allergens or "").casefold())]
        if gluten_hits:
            return False, f"Contains gluten ({', '.join(gluten_hits)})"
        return True, ""

    if pref in {"dairy-free", "dairy free"}:
        dairy_hits = [w for w in ["milk", "dairy", "butter", "cream", "cheese", "paneer", "ghee", "curd"] if re.search(rf"(?<![a-z0-9]){w}(?![a-z0-9])", ingredients) or re.search(rf"(?<![a-z0-9]){w}(?![a-z0-9])", (item.allergens or "").casefold())]
        if dairy_hits:
            return False, f"Contains dairy ({', '.join(dairy_hits)})"
        return True, ""

    return True, ""

def analyze_dish_dietary_safety(
    item: MenuItem,
    dietary_pref: str,
    target_allergens: List[str]
) -> Dict[str, Any]:
    """
    Classify a dish into Suitable 🟢, Customizable 🟡, or Unsuitable 🔴.
    """
    is_diet_ok, diet_reason = check_dietary_compliance(item, dietary_pref)
    detected_allergens = detect_allergens_in_item(item, target_allergens)
    
    # 1. Unsuitable conditions:
    if not is_diet_ok:
        return {
            "status": "unsuitable",
            "badge": "🔴 Unsuitable",
            "is_safe": False,
            "reason": diet_reason,
            "detected_allergens": detected_allergens,
            "can_customize": False,
            "customization_note": None
        }

    # 2. If target allergens were found:
    if detected_allergens:
        # Check if the allergen is just an optional garnish/sauce that can be omitted
        ingredients_lower = (item.ingredients or "").casefold()
        can_omit = all(
            any(g in ingredients_lower for g in CUSTOMIZABLE_GARNISHES)
            for allergen in detected_allergens
            if allergen in {"nut", "nuts", "dairy", "milk"}
        )
        
        # If the item name itself is Paneer or Peanut or Chicken, cannot omit
        dish_name_lower = item.name.casefold()
        if any(a in dish_name_lower for a in ["paneer", "cheese", "peanut", "egg", "fish", "chicken"]):
            can_omit = False

        if can_omit:
            return {
                "status": "customizable",
                "badge": "🟡 Customizable",
                "is_safe": True,
                "reason": f"Contains {', '.join(detected_allergens)} as topping or dressing",
                "detected_allergens": detected_allergens,
                "can_customize": True,
                "customization_note": f"Request kitchen staff to omit {', '.join(detected_allergens)} during preparation"
            }
        else:
            return {
                "status": "unsuitable",
                "badge": "🔴 Unsuitable",
                "is_safe": False,
                "reason": f"Contains specified allergen(s): {', '.join(detected_allergens)}",
                "detected_allergens": detected_allergens,
                "can_customize": False,
                "customization_note": None
            }

    # 3. Fully suitable
    return {
        "status": "suitable",
        "badge": "🟢 Suitable",
        "is_safe": True,
        "reason": "Meets dietary requirements and free from specified allergens",
        "detected_allergens": [],
        "can_customize": False,
        "customization_note": None
    }

def get_dietary_and_allergy_menu(
    session: Session,
    restaurant_id: Optional[int] = None,
    dietary_preference: Optional[str] = None,
    allergens: Optional[str] = None,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Feature 8 Main Engine:
    Processes all menu items against customer dietary preference and declared allergens.
    Categorizes into suitable, customizable, and unsuitable with smart alternative dish suggestions.
    """
    # Auto-populate from user preference if omitted
    if user_id and (not dietary_preference or not allergens):
        pref = session.exec(select(CustomerPreference).where(CustomerPreference.user_id == user_id)).first()
        if pref:
            if not dietary_preference:
                dietary_preference = pref.dietary_preference
            if not allergens:
                allergens = pref.allergy_info

    active_dietary = (dietary_preference or "Any").strip()
    active_allergens = normalize_allergy_terms(allergens)

    # Fetch menu items
    query = select(MenuItem).where(MenuItem.is_available == True)
    if restaurant_id:
        query = query.where(MenuItem.restaurant_id == restaurant_id)
    items = session.exec(query).all()

    # Pre-analyze all dishes
    analyzed_items = []
    suitable_dishes = []
    customizable_dishes = []
    unsuitable_dishes = []

    for item in items:
        cat = session.get(Category, item.category_id) if item.category_id else None
        analysis = analyze_dish_dietary_safety(item, active_dietary, active_allergens)
        
        dish_data = {
            "id": item.id,
            "restaurant_id": item.restaurant_id,
            "category_id": item.category_id,
            "category_name": cat.name if cat else "General",
            "name": item.name,
            "description": item.description,
            "image_url": item.image_url,
            "price": item.price,
            "discount_price": item.discount_price,
            "is_veg": item.is_veg,
            "spice_level": item.spice_level,
            "ingredients": item.ingredients,
            "allergens": item.allergens,
            "dietary_tags": item.dietary_tags,
            "rating": item.rating,
            "is_bestseller": item.is_bestseller,
            "suitability_status": analysis["status"],
            "suitability_badge": analysis["badge"],
            "is_safe": analysis["is_safe"],
            "reason": analysis["reason"],
            "detected_allergens": analysis["detected_allergens"],
            "can_customize": analysis["can_customize"],
            "customization_note": analysis["customization_note"],
            "suggested_alternatives": []
        }

        if analysis["status"] == "suitable":
            suitable_dishes.append(dish_data)
        elif analysis["status"] == "customizable":
            customizable_dishes.append(dish_data)
        else:
            unsuitable_dishes.append(dish_data)
        
        analyzed_items.append(dish_data)

    # Find safe alternatives for unsuitable dishes
    for bad_dish in unsuitable_dishes:
        # 1. First priority: safe dishes from the same category and same restaurant
        same_cat = [d for d in suitable_dishes if d["restaurant_id"] == bad_dish["restaurant_id"] and d["category_id"] == bad_dish["category_id"]]
        # 2. Second priority: safe dishes from the same restaurant in other categories
        other_cat = [d for d in suitable_dishes if d["restaurant_id"] == bad_dish["restaurant_id"] and d["category_id"] != bad_dish["category_id"]]
        # 3. Third priority: customizable dishes in the same category
        custom_cat = [d for d in customizable_dishes if d["restaurant_id"] == bad_dish["restaurant_id"] and d["category_id"] == bad_dish["category_id"]]
        
        alternatives = same_cat[:2]
        if len(alternatives) < 2:
            alternatives.extend(other_cat[:2 - len(alternatives)])
        if len(alternatives) < 2:
            alternatives.extend(custom_cat[:2 - len(alternatives)])

        bad_dish["suggested_alternatives"] = [
            {
                "id": alt["id"],
                "name": alt["name"],
                "price": alt["price"],
                "discount_price": alt["discount_price"],
                "image_url": alt["image_url"],
                "is_veg": alt["is_veg"],
                "rating": alt["rating"],
                "category_name": alt["category_name"],
                "reason": f"Safe alternative free of {', '.join(bad_dish['detected_allergens'])}" if bad_dish['detected_allergens'] else "Safe alternative matching your dietary preferences"
            }
            for alt in alternatives
        ]

    return {
        "customer_preferences": {
            "dietary_preference": active_dietary,
            "allergy_info": ", ".join(active_allergens) if active_allergens else "None"
        },
        "summary": {
            "total_dishes": len(items),
            "suitable_count": len(suitable_dishes),
            "customizable_count": len(customizable_dishes),
            "unsuitable_count": len(unsuitable_dishes)
        },
        "suitable": suitable_dishes,
        "customizable": customizable_dishes,
        "unsuitable": unsuitable_dishes,
        "all_dishes": analyzed_items
    }
