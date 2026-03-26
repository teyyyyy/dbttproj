from collections import Counter, defaultdict
from calendar import monthrange
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
import re
from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app.routes import auth, cafes, orders, admin
from app.utils.database import engine, Base, get_db, SessionLocal
from app.models import User, Cafe, MenuItem, Order, OrderItem, Point, Review, Favorite
from app.utils.auth import get_current_user

# Create database tables
Base.metadata.create_all(bind=engine)

# Seed sample data
def seed_data(db: Session):
    def ensure_user(email: str, full_name: str, role: str):
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            existing_role_user = db.query(User).filter(User.role == role).first()
            user = User(
                email=email,
                hashed_password=existing_role_user.hashed_password if existing_role_user else "demo-password",
                full_name=full_name,
                role=role,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            updated = False
            if user.full_name != full_name:
                user.full_name = full_name
                updated = True
            if user.role != role:
                user.role = role
                updated = True
            if updated:
                db.commit()
                db.refresh(user)
        return user

    def ensure_cafe(vendor_id: int, name: str, description: str, address: str, latitude: float, longitude: float, operating_hours: str):
        cafe = db.query(Cafe).filter(Cafe.vendor_id == vendor_id, Cafe.name == name).first()
        if cafe is None:
            cafe = Cafe(
                vendor_id=vendor_id,
                name=name,
                description=description,
                address=address,
                latitude=latitude,
                longitude=longitude,
                operating_hours=operating_hours,
            )
            db.add(cafe)
            db.commit()
            db.refresh(cafe)
        else:
            updated = False
            for field, value in {
                "description": description,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
                "operating_hours": operating_hours,
            }.items():
                if getattr(cafe, field) != value:
                    setattr(cafe, field, value)
                    updated = True
            if updated:
                db.commit()
                db.refresh(cafe)
        return cafe

    def ensure_menu_item(cafe_id: int, name: str, description: str, price: float, category: str, is_available: bool = True):
        item = db.query(MenuItem).filter(MenuItem.cafe_id == cafe_id, MenuItem.name == name).first()
        if item is None:
            item = MenuItem(
                cafe_id=cafe_id,
                name=name,
                description=description,
                price=price,
                category=category,
                is_available=is_available,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
        return item

    def ensure_order(customer_id: int, cafe_id: int, delivery_address: str, notes: str, status: str, hours_ago: int, item_specs: list[tuple[str, int]]):
        existing = (
            db.query(Order)
            .filter(
                Order.customer_id == customer_id,
                Order.cafe_id == cafe_id,
                Order.notes == notes,
            )
            .first()
        )
        if existing is not None:
            return existing

        menu_lookup = {
            item.name: item
            for item in db.query(MenuItem).filter(MenuItem.cafe_id == cafe_id).all()
        }
        total_amount = 0.0
        order_items = []
        for item_name, quantity in item_specs:
            menu_item = menu_lookup[item_name]
            total_amount += menu_item.price * quantity
            order_items.append(
                OrderItem(
                    menu_item_id=menu_item.id,
                    quantity=quantity,
                    price=menu_item.price,
                )
            )

        order = Order(
            customer_id=customer_id,
            cafe_id=cafe_id,
            total_amount=total_amount,
            status=status,
            order_time=datetime.utcnow() - timedelta(hours=hours_ago),
            delivery_address=delivery_address,
            notes=notes,
        )
        db.add(order)
        db.flush()

        for order_item in order_items:
            order_item.order_id = order.id
            db.add(order_item)

        db.commit()
        db.refresh(order)
        return order

    def ensure_review(user_id: int, cafe_id: int, rating: float, comment: str):
        review = (
            db.query(Review)
            .filter(
                Review.user_id == user_id,
                Review.cafe_id == cafe_id,
                Review.comment == comment,
            )
            .first()
        )
        if review is None:
            review = Review(user_id=user_id, cafe_id=cafe_id, rating=rating, comment=comment)
            db.add(review)
            db.commit()
            db.refresh(review)
        return review

    # Seed demo users if not exists
    customer = ensure_user("customer@gmail.com", "Chloe Lim", "customer")
    vendor = ensure_user("vendor@gmail.com", "John Vendor", "vendor")
    pastry_vendor = ensure_user("mei@sunnyoven.com", "Mei Lin", "vendor")
    tea_vendor = ensure_user("daniel@leaflane.com", "Daniel Goh", "vendor")
    brunch_vendor = ensure_user("nora@brunchroom.com", "Nora Lee", "vendor")
    dessert_vendor = ensure_user("farah@moonwhisk.com", "Farah Aziz", "vendor")
    repeat_customer = ensure_user("amelia@gmail.com", "Aisha Noor", "customer")
    office_customer = ensure_user("raj@gmail.com", "Marcus Teo", "customer")
    family_customer = ensure_user("siti@gmail.com", "Priya Menon", "customer")

    cafe1 = ensure_cafe(
        vendor.id,
        "Cozy Corner Café",
        "A cozy spot for coffee, matcha drinks, and pastries.",
        "14 Eng Hoon Street, Singapore",
        1.2857,
        103.8321,
        "Mon-Fri 8AM-6PM",
    )
    cafe2 = ensure_cafe(
        vendor.id,
        "Brew & Bites",
        "Fresh brews, rice bowls, and comfort food for busy customers.",
        "87 Beach Road, Singapore",
        1.3012,
        103.8601,
        "Daily 7AM-8PM",
    )
    cafe3 = ensure_cafe(
        pastry_vendor.id,
        "Sunny Oven Studio",
        "Small-batch sourdough bakes, laminated pastries, and seasonal jam buns.",
        "18 Tiong Bahru Lane, Singapore",
        1.2866,
        103.8272,
        "Wed-Sun 8AM-4PM",
    )
    cafe4 = ensure_cafe(
        tea_vendor.id,
        "Leaf & Lane",
        "Modern tea bar serving hojicha lattes, milk tea, and light Japanese bites.",
        "72 Joo Chiat Road, Singapore",
        1.3142,
        103.9016,
        "Daily 11AM-9PM",
    )
    cafe5 = ensure_cafe(
        brunch_vendor.id,
        "Brunch Bureau",
        "All-day brunch plates, eggs, toasties, and cold brew for the neighborhood crowd.",
        "9 Everton Park, Singapore",
        1.2769,
        103.8398,
        "Tue-Sun 9AM-5PM",
    )
    cafe6 = ensure_cafe(
        dessert_vendor.id,
        "Moonwhisk Desserts",
        "Late-night desserts with tarts, brownies, soft-serve, and bottled drinks.",
        "33 Haji Lane, Singapore",
        1.3007,
        103.8599,
        "Thu-Tue 1PM-10PM",
    )
    cafe7 = ensure_cafe(
        tea_vendor.id,
        "Harbor Toast House",
        "Comfort breakfast sets, kopi, and hearty toast sandwiches for office pickups.",
        "101 Telok Ayer Street, Singapore",
        1.2822,
        103.8485,
        "Mon-Fri 7AM-3PM",
    )

    cozy_corner_items = [
        ("Espresso", "Strong and bold coffee.", 3.50, "drink", True),
        ("Cappuccino", "Espresso with steamed milk.", 4.00, "drink", True),
        ("Matcha Latte", "Ceremonial-grade matcha with creamy milk.", 5.50, "drink", True),
        ("Strawberry Matcha", "Layered strawberry puree with matcha milk.", 6.20, "drink", True),
        ("Yuzu Cold Brew", "Bright citrus cold brew for warm afternoons.", 5.80, "drink", True),
        ("Croissant", "Buttery, flaky pastry.", 2.50, "pastry", True),
        ("Kaya Butter Toast", "Toasted bread with kaya and butter.", 4.80, "food", True),
        ("Avocado Toast", "Toasted bread with avocado.", 7.00, "food", True),
        ("Burnt Cheesecake Slice", "Creamy cheesecake with caramelised top.", 6.50, "dessert", False),
    ]
    brew_bites_items = [
        ("Latte", "Smooth espresso with milk.", 4.50, "drink", True),
        ("Americano", "Espresso diluted with water.", 3.00, "drink", True),
        ("Iced Matcha Cloud", "Whipped cream topping over iced matcha.", 6.00, "drink", True),
        ("Club Sandwich", "Turkey, bacon, lettuce, tomato.", 9.50, "food", True),
        ("Miso Chicken Bowl", "Roasted chicken bowl with miso glaze.", 11.50, "food", True),
        ("Truffle Egg Mayo Sando", "Japanese milk bread with egg mayo.", 8.20, "food", True),
        ("Blueberry Muffin", "Blueberry muffin.", 3.00, "pastry", True),
        ("Chocolate Financier", "Almond cake with dark chocolate.", 4.20, "dessert", True),
    ]
    sunny_oven_items = [
        ("Pain Au Chocolat", "Flaky laminated pastry with dark chocolate batons.", 5.20, "pastry", True),
        ("Sea Salt Focaccia", "Rosemary focaccia with sea salt flakes.", 6.80, "food", True),
        ("Burnt Honey Kouign Amann", "Caramelised Breton pastry with buttery layers.", 5.80, "pastry", True),
        ("Iced White", "Double ristretto with cold milk over ice.", 5.00, "drink", True),
    ]
    leaf_lane_items = [
        ("Hojicha Latte", "Roasted tea latte with deep nutty notes.", 5.60, "drink", True),
        ("Genmaicha Yuzu Soda", "Sparkling yuzu with toasted rice tea.", 6.20, "drink", True),
        ("Tamago Sando", "Japanese egg sandwich on shokupan.", 7.50, "food", True),
        ("Mochi Waffle", "Crisp mochi waffle with kinako dusting.", 8.80, "dessert", True),
    ]
    brunch_bureau_items = [
        ("Truffle Scramble Toast", "Soft scrambled eggs with truffle on thick toast.", 12.50, "food", True),
        ("Chicken Avo Bagel", "Grilled chicken bagel with avocado spread.", 11.80, "food", True),
        ("Orange Cold Brew", "Cold brew brightened with orange tonic.", 6.00, "drink", True),
        ("Banana Walnut Loaf", "House-baked loaf served warm.", 5.40, "dessert", True),
    ]
    moonwhisk_items = [
        ("Pistachio Tart", "Buttery tart shell with pistachio cream.", 8.50, "dessert", True),
        ("Dark Chocolate Brownie", "Fudgy brownie with flaky sea salt.", 5.20, "dessert", True),
        ("Strawberry Milk", "Fresh strawberry milk in a bottled serve.", 4.80, "drink", True),
        ("Vanilla Soft Serve Cup", "Classic soft serve with cookie crumble.", 6.00, "dessert", True),
    ]
    harbor_toast_items = [
        ("Kopi C", "Traditional kopi with evaporated milk.", 2.20, "drink", True),
        ("Peanut Butter French Toast", "Sweet-savoury toast with peanut butter center.", 6.20, "food", True),
        ("Turkey Melt", "Toasted sandwich with turkey and cheddar.", 8.90, "food", True),
        ("Lemon Tea", "Brewed black tea with fresh lemon slices.", 3.20, "drink", True),
    ]

    for item_name, description, price, category, is_available in cozy_corner_items:
        ensure_menu_item(cafe1.id, item_name, description, price, category, is_available)

    for item_name, description, price, category, is_available in brew_bites_items:
        ensure_menu_item(cafe2.id, item_name, description, price, category, is_available)

    for item_name, description, price, category, is_available in sunny_oven_items:
        ensure_menu_item(cafe3.id, item_name, description, price, category, is_available)

    for item_name, description, price, category, is_available in leaf_lane_items:
        ensure_menu_item(cafe4.id, item_name, description, price, category, is_available)

    for item_name, description, price, category, is_available in brunch_bureau_items:
        ensure_menu_item(cafe5.id, item_name, description, price, category, is_available)

    for item_name, description, price, category, is_available in moonwhisk_items:
        ensure_menu_item(cafe6.id, item_name, description, price, category, is_available)

    for item_name, description, price, category, is_available in harbor_toast_items:
        ensure_menu_item(cafe7.id, item_name, description, price, category, is_available)

    demo_reviews = [
        (customer.id, cafe1.id, 5, "Love the matcha drinks here. The croissant was fresh too."),
        (repeat_customer.id, cafe1.id, 4, "Strawberry Matcha is super smooth and not too sweet."),
        (office_customer.id, cafe1.id, 5, "Coffee arrived hot and the kaya toast made a great breakfast."),
        (customer.id, cafe2.id, 4, "Reliable lunch option. The miso chicken bowl travels well."),
        (family_customer.id, cafe2.id, 5, "Club sandwich was generous and the iced matcha cloud was a hit."),
        (office_customer.id, cafe2.id, 4, "Fast delivery and good portion size for weekday orders."),
        (repeat_customer.id, cafe3.id, 5, "The kouign amann had amazing layers and stayed crisp even later in the day."),
        (customer.id, cafe4.id, 4, "Really liked the hojicha latte. It tastes roasted instead of overly sweet."),
        (family_customer.id, cafe5.id, 5, "Great brunch portions and the bagel arrived neatly packed."),
        (office_customer.id, cafe6.id, 4, "Desserts are rich without being too heavy. Nice for sharing."),
        (customer.id, cafe7.id, 4, "Solid breakfast stop with comforting kopi and toast options."),
    ]
    for user_id, cafe_id, rating, comment in demo_reviews:
        ensure_review(user_id, cafe_id, rating, comment)

    demo_orders = [
        (customer.id, cafe1.id, "18 Garden View", "Platform booking 001", "delivered", 4, [("Matcha Latte", 2), ("Croissant", 1)]),
        (repeat_customer.id, cafe1.id, "8 Maple Street", "Platform booking 002", "delivered", 10, [("Strawberry Matcha", 1), ("Kaya Butter Toast", 2)]),
        (office_customer.id, cafe2.id, "21 Office Park", "Platform booking 003", "ready", 20, [("Miso Chicken Bowl", 2), ("Latte", 2)]),
        (family_customer.id, cafe2.id, "50 River Drive", "Platform booking 004", "preparing", 28, [("Club Sandwich", 2), ("Iced Matcha Cloud", 1)]),
        (repeat_customer.id, cafe1.id, "8 Maple Street", "Platform booking 005", "confirmed", 35, [("Yuzu Cold Brew", 2), ("Avocado Toast", 1)]),
        (customer.id, cafe2.id, "18 Garden View", "Platform booking 006", "delivered", 49, [("Truffle Egg Mayo Sando", 1), ("Blueberry Muffin", 2)]),
        (office_customer.id, cafe1.id, "21 Office Park", "Platform booking 007", "delivered", 58, [("Espresso", 3), ("Burnt Cheesecake Slice", 1)]),
        (family_customer.id, cafe2.id, "50 River Drive", "Platform booking 008", "pending", 67, [("Americano", 2), ("Chocolate Financier", 2)]),
        (repeat_customer.id, cafe1.id, "8 Maple Street", "Platform booking 009", "delivered", 81, [("Matcha Latte", 1), ("Croissant", 2)]),
        (customer.id, cafe2.id, "18 Garden View", "Platform booking 010", "delivered", 96, [("Miso Chicken Bowl", 1), ("Latte", 1)]),
        (office_customer.id, cafe1.id, "21 Office Park", "Platform booking 011", "delivered", 118, [("Strawberry Matcha", 2), ("Kaya Butter Toast", 1)]),
        (family_customer.id, cafe2.id, "50 River Drive", "Platform booking 012", "delivered", 142, [("Club Sandwich", 1), ("Iced Matcha Cloud", 2)]),
    ]

    for customer_id, cafe_id, address, notes, status, hours_ago, item_specs in demo_orders:
        ensure_order(customer_id, cafe_id, address, notes, status, hours_ago, item_specs)

def cleanup_duplicate_cafes(db: Session):
    duplicate_groups = (
        db.query(
            func.lower(func.trim(Cafe.name)).label("normalized_name"),
            func.lower(func.trim(Cafe.address)).label("normalized_address"),
            func.count(Cafe.id).label("cafe_count"),
        )
        .group_by(
            func.lower(func.trim(Cafe.name)),
            func.lower(func.trim(Cafe.address)),
        )
        .having(func.count(Cafe.id) > 1)
        .all()
    )

    for group in duplicate_groups:
        cafes = (
            db.query(Cafe)
            .filter(
                func.lower(func.trim(Cafe.name)) == group.normalized_name,
                func.lower(func.trim(Cafe.address)) == group.normalized_address,
            )
            .order_by(Cafe.id.asc())
            .all()
        )
        canonical_cafe = cafes[0]

        for duplicate_cafe in cafes[1:]:
            duplicate_menu_items = (
                db.query(MenuItem)
                .filter(MenuItem.cafe_id == duplicate_cafe.id)
                .order_by(MenuItem.id.asc())
                .all()
            )
            for menu_item in duplicate_menu_items:
                canonical_item = (
                    db.query(MenuItem)
                    .filter(
                        MenuItem.cafe_id == canonical_cafe.id,
                        func.lower(func.trim(MenuItem.name)) == func.lower(func.trim(menu_item.name)),
                    )
                    .first()
                )
                if canonical_item:
                    db.query(OrderItem).filter(OrderItem.menu_item_id == menu_item.id).update(
                        {"menu_item_id": canonical_item.id},
                        synchronize_session=False,
                    )
                    canonical_item.is_available = canonical_item.is_available or menu_item.is_available
                    db.delete(menu_item)
                else:
                    menu_item.cafe_id = canonical_cafe.id

            db.flush()

            db.query(Order).filter(Order.cafe_id == duplicate_cafe.id).update(
                {"cafe_id": canonical_cafe.id},
                synchronize_session=False,
            )
            db.query(Review).filter(Review.cafe_id == duplicate_cafe.id).update(
                {"cafe_id": canonical_cafe.id},
                synchronize_session=False,
            )
            db.query(Cafe).filter(Cafe.id == duplicate_cafe.id).delete(synchronize_session=False)

    db.commit()


def cleanup_duplicate_cafes_by_name(db: Session):
    duplicate_groups = (
        db.query(
            func.lower(func.trim(Cafe.name)).label("normalized_name"),
            func.count(Cafe.id).label("cafe_count"),
        )
        .group_by(func.lower(func.trim(Cafe.name)))
        .having(func.count(Cafe.id) > 1)
        .all()
    )

    for group in duplicate_groups:
        cafes = (
            db.query(Cafe)
            .filter(func.lower(func.trim(Cafe.name)) == group.normalized_name)
            .order_by(Cafe.id.asc())
            .all()
        )
        canonical_cafe = cafes[0]

        for duplicate_cafe in cafes[1:]:
            canonical_cafe.description = duplicate_cafe.description or canonical_cafe.description
            canonical_cafe.address = duplicate_cafe.address or canonical_cafe.address
            canonical_cafe.latitude = duplicate_cafe.latitude or canonical_cafe.latitude
            canonical_cafe.longitude = duplicate_cafe.longitude or canonical_cafe.longitude
            canonical_cafe.operating_hours = duplicate_cafe.operating_hours or canonical_cafe.operating_hours

            duplicate_menu_items = (
                db.query(MenuItem)
                .filter(MenuItem.cafe_id == duplicate_cafe.id)
                .order_by(MenuItem.id.asc())
                .all()
            )
            for menu_item in duplicate_menu_items:
                canonical_item = (
                    db.query(MenuItem)
                    .filter(
                        MenuItem.cafe_id == canonical_cafe.id,
                        func.lower(func.trim(MenuItem.name)) == func.lower(func.trim(menu_item.name)),
                    )
                    .first()
                )
                if canonical_item:
                    db.query(OrderItem).filter(OrderItem.menu_item_id == menu_item.id).update(
                        {"menu_item_id": canonical_item.id},
                        synchronize_session=False,
                    )
                    canonical_item.is_available = canonical_item.is_available or menu_item.is_available
                    db.delete(menu_item)
                else:
                    menu_item.cafe_id = canonical_cafe.id

            db.flush()

            db.query(Order).filter(Order.cafe_id == duplicate_cafe.id).update(
                {"cafe_id": canonical_cafe.id},
                synchronize_session=False,
            )
            db.query(Review).filter(Review.cafe_id == duplicate_cafe.id).update(
                {"cafe_id": canonical_cafe.id},
                synchronize_session=False,
            )
            db.query(Cafe).filter(Cafe.id == duplicate_cafe.id).delete(synchronize_session=False)

    db.commit()


def repair_orphaned_menu_items(db: Session):
    orphaned_items = db.query(MenuItem).filter(MenuItem.cafe_id.is_(None)).all()
    for menu_item in orphaned_items:
        target_cafe_id = (
            db.query(Order.cafe_id)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .filter(OrderItem.menu_item_id == menu_item.id, Order.cafe_id.is_not(None))
            .order_by(Order.order_time.desc())
            .limit(1)
            .scalar()
        )
        if target_cafe_id is not None:
            menu_item.cafe_id = target_cafe_id

    db.commit()


def cleanup_duplicate_menu_items(db: Session):
    duplicate_groups = (
        db.query(
            MenuItem.cafe_id,
            func.lower(func.trim(MenuItem.name)).label("normalized_name"),
            func.count(MenuItem.id).label("item_count"),
        )
        .filter(MenuItem.cafe_id.is_not(None))
        .group_by(MenuItem.cafe_id, func.lower(func.trim(MenuItem.name)))
        .having(func.count(MenuItem.id) > 1)
        .all()
    )

    for group in duplicate_groups:
        items = (
            db.query(MenuItem)
            .filter(
                MenuItem.cafe_id == group.cafe_id,
                func.lower(func.trim(MenuItem.name)) == group.normalized_name,
            )
            .order_by(MenuItem.id.asc())
            .all()
        )
        canonical_item = items[0]
        for duplicate_item in items[1:]:
            db.query(OrderItem).filter(OrderItem.menu_item_id == duplicate_item.id).update(
                {"menu_item_id": canonical_item.id},
                synchronize_session=False,
            )
            canonical_item.is_available = canonical_item.is_available or duplicate_item.is_available
            db.delete(duplicate_item)

    db.commit()


def cleanup_duplicate_reviews(db: Session):
    duplicate_groups = (
        db.query(
            Review.user_id,
            Review.cafe_id,
            Review.rating,
            Review.comment,
            func.count(Review.id).label("review_count"),
        )
        .group_by(Review.user_id, Review.cafe_id, Review.rating, Review.comment)
        .having(func.count(Review.id) > 1)
        .all()
    )

    for group in duplicate_groups:
        reviews = (
            db.query(Review)
            .filter(
                Review.user_id == group.user_id,
                Review.cafe_id == group.cafe_id,
                Review.rating == group.rating,
                Review.comment == group.comment,
            )
            .order_by(Review.id.asc())
            .all()
        )
        for duplicate_review in reviews[1:]:
            db.delete(duplicate_review)

    db.commit()


def cleanup_legacy_demo_reviews(db: Session):
    legacy_comments = [
        "Amazing coffee!",
        "Great sandwiches.",
        "Amazing coffee and matcha selection!",
        "Great sandwiches and reliable delivery.",
    ]
    db.query(Review).filter(Review.comment.in_(legacy_comments)).delete(synchronize_session=False)
    db.commit()


def cleanup_legacy_demo_user_names(db: Session):
    rename_map = {
        "customer@example.com": "Nadia Wong",
        "customer@gmail.com": "Chloe Lim",
        "amelia@gmail.com": "Aisha Noor",
        "raj@gmail.com": "Marcus Teo",
        "siti@gmail.com": "Priya Menon",
    }
    for email, full_name in rename_map.items():
        user = db.query(User).filter(User.email == email).first()
        if user and user.full_name != full_name:
            user.full_name = full_name
    db.commit()


def build_order_analytics(orders: list[Order]):
    total_orders = len(orders)
    total_revenue = sum(order.total_amount for order in orders)
    average_order_value = total_revenue / total_orders if total_orders else 0.0
    status_counts = Counter(order.status for order in orders)
    completed_orders = sum(1 for order in orders if order.status in {"ready", "delivered"})

    cafe_counts = Counter(order.cafe.name for order in orders if order.cafe)
    top_cafe = cafe_counts.most_common(1)[0] if cafe_counts else None

    item_counts = Counter()
    for order in orders:
        for order_item in order.items:
            item_name = order_item.menu_item.name if order_item.menu_item else f"Item #{order_item.menu_item_id}"
            item_counts[item_name] += order_item.quantity

    return {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "average_order_value": average_order_value,
        "completed_orders": completed_orders,
        "completion_rate": round((completed_orders / total_orders) * 100) if total_orders else 0,
        "top_cafe": {"name": top_cafe[0], "orders": top_cafe[1]} if top_cafe else None,
        "top_items": [{"name": name, "quantity": quantity} for name, quantity in item_counts.most_common(5)],
        "status_counts": status_counts,
    }


def get_managed_cafe_for_vendor(db: Session, vendor_id: int):
    return (
        db.query(Cafe)
        .filter(Cafe.vendor_id == vendor_id)
        .order_by(Cafe.id.asc())
        .first()
    )


def get_visible_cafes_for_user(db: Session, current_user: Optional[User]):
    return db.query(Cafe).all()


def get_operating_hour_slots(operating_hours: Optional[str]) -> list[int]:
    if not operating_hours:
        return list(range(8, 21))

    hour_matches = re.findall(r"(\d{1,2})(?::?(\d{2}))?\s*(am|pm)?", operating_hours, flags=re.IGNORECASE)
    if len(hour_matches) < 2:
        return list(range(8, 21))

    def to_24_hour(hour_text: str, minute_text: str, meridiem: str) -> int:
        hour = int(hour_text)
        meridiem = meridiem.lower() if meridiem else ""
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        return hour

    opening_hour = to_24_hour(*hour_matches[0])
    closing_hour = to_24_hour(*hour_matches[1])

    if closing_hour <= opening_hour:
        return list(range(8, 21))

    return list(range(opening_hour, closing_hour + 1))

seed_data(SessionLocal())
cleanup_duplicate_cafes(SessionLocal())
cleanup_duplicate_cafes_by_name(SessionLocal())
repair_orphaned_menu_items(SessionLocal())
cleanup_duplicate_menu_items(SessionLocal())
cleanup_duplicate_reviews(SessionLocal())
cleanup_legacy_demo_reviews(SessionLocal())
cleanup_legacy_demo_user_names(SessionLocal())

app = FastAPI(title="Café Discovery Platform", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["cafe_image_url"] = lambda cafe_name: {
    "Cozy Corner Café": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=1200&q=80",
    "Brew & Bites": "https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&w=1200&q=80",
    "Sunny Oven Studio": "https://images.unsplash.com/photo-1517433670267-08bbd4be890f?auto=format&fit=crop&w=1200&q=80",
    "Leaf & Lane": "https://images.unsplash.com/photo-1521017432531-fbd92d768814?auto=format&fit=crop&w=1200&q=80",
    "Brunch Bureau": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?auto=format&fit=crop&w=1200&q=80",
    "Moonwhisk Desserts": "https://images.unsplash.com/photo-1481833761820-0509d3217039?auto=format&fit=crop&w=1200&q=80",
    "Harbor Toast House": "https://images.unsplash.com/photo-1453614512568-c4024d13c247?auto=format&fit=crop&w=1200&q=80",
}.get(cafe_name, "https://images.unsplash.com/photo-1445116572660-236099ec97a0?auto=format&fit=crop&w=1200&q=80")
templates.env.globals["menu_item_image_url"] = lambda item_name, category='food': {
    "Espresso": "https://images.unsplash.com/photo-1517701604599-bb29b565090c?auto=format&fit=crop&w=1200&q=80",
    "Cappuccino": "https://images.unsplash.com/photo-1461023058943-07fcbe16d735?auto=format&fit=crop&w=1200&q=80",
    "Matcha Latte": "https://images.unsplash.com/photo-1515823064-d6e0c04616a7?auto=format&fit=crop&w=1200&q=80",
    "Strawberry Matcha": "https://images.unsplash.com/photo-1499636136210-6f4ee915583e?auto=format&fit=crop&w=1200&q=80",
    "Yuzu Cold Brew": "https://images.unsplash.com/photo-1461023058943-07fcbe16d735?auto=format&fit=crop&w=1200&q=80",
    "Croissant": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=1200&q=80",
    "Kaya Butter Toast": "https://images.unsplash.com/photo-1484723091739-30a097e8f929?auto=format&fit=crop&w=1200&q=80",
    "Avocado Toast": "https://images.unsplash.com/photo-1541519227354-08fa5d50c44d?auto=format&fit=crop&w=1200&q=80",
    "Burnt Cheesecake Slice": "https://images.unsplash.com/photo-1533134242443-d4fd215305ad?auto=format&fit=crop&w=1200&q=80",
    "Latte": "https://images.unsplash.com/photo-1494314671902-399b18174975?auto=format&fit=crop&w=1200&q=80",
    "Americano": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=1200&q=80",
    "Iced Matcha Cloud": "https://images.unsplash.com/photo-1515823064-d6e0c04616a7?auto=format&fit=crop&w=1200&q=80",
    "Club Sandwich": "https://images.unsplash.com/photo-1528735602780-2552fd46c7af?auto=format&fit=crop&w=1200&q=80",
    "Miso Chicken Bowl": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=1200&q=80",
    "Truffle Egg Mayo Sando": "https://images.unsplash.com/photo-1553909489-cd47e0ef937f?auto=format&fit=crop&w=1200&q=80",
    "Blueberry Muffin": "https://images.unsplash.com/photo-1607958996333-41aef7caefaa?auto=format&fit=crop&w=1200&q=80",
    "Chocolate Financier": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?auto=format&fit=crop&w=1200&q=80",
}.get(
    item_name,
    {
        "drink": "https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&w=1200&q=80",
        "food": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=1200&q=80",
        "pastry": "https://images.unsplash.com/photo-1517433670267-08bbd4be890f?auto=format&fit=crop&w=1200&q=80",
        "dessert": "https://images.unsplash.com/photo-1488477181946-6428a0291777?auto=format&fit=crop&w=1200&q=80",
    }.get(category, "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=1200&q=80")
)

# Include routers
app.include_router(cafes.router, prefix="/api/cafes", tags=["Cafes"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])

def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    role = request.cookies.get("role", "customer")
    if role == "vendor":
        user = db.query(User).filter(User.role == "vendor").first()
    else:
        user = db.query(User).filter(User.role == "customer").first()
    return user


def group_menu_items(menu_items):
    grouped = defaultdict(list)
    for item in sorted(menu_items, key=lambda menu_item: (menu_item.category, menu_item.name)):
        grouped[item.category.capitalize()].append(item)
    return dict(grouped)


def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return 2 * radius_km * asin(sqrt(a))


def build_home_discovery_data(cafes: list[Cafe], db: Session):
    if not cafes:
        return [], [], [], []

    reference_lat = 1.2903
    reference_lon = 103.8519
    review_summary = {
        cafe_id: {"count": 0, "rating_total": 0.0}
        for cafe_id in [cafe.id for cafe in cafes]
    }

    for review in db.query(Review).filter(Review.cafe_id.in_(review_summary.keys())).all():
        review_summary[review.cafe_id]["count"] += 1
        review_summary[review.cafe_id]["rating_total"] += review.rating

    enriched_cafes = []
    for cafe in cafes:
        summary = review_summary.get(cafe.id, {"count": 0, "rating_total": 0.0})
        average_rating = (
            summary["rating_total"] / summary["count"]
            if summary["count"]
            else 0.0
        )
        distance_km = calculate_distance_km(reference_lat, reference_lon, cafe.latitude, cafe.longitude)
        enriched_cafes.append(
            {
                "id": cafe.id,
                "name": cafe.name,
                "description": cafe.description,
                "address": cafe.address,
                "operating_hours": cafe.operating_hours,
                "distance_km": round(distance_km, 1),
                "average_rating": round(average_rating, 1) if average_rating else None,
                "star_count": max(1, min(5, int(average_rating + 0.5))) if average_rating else 0,
                "review_count": summary["count"],
            }
        )

    nearby_cafes = sorted(enriched_cafes, key=lambda cafe: cafe["distance_km"])[:4]
    recommended_cafes = sorted(
        enriched_cafes,
        key=lambda cafe: (
            cafe["average_rating"] or 0,
            cafe["review_count"],
            -cafe["distance_km"],
        ),
        reverse=True,
    )[:3]

    map_points = []
    for cafe in cafes:
        map_points.append(
            {
                "id": cafe.id,
                "kind": "cafe",
                "name": cafe.name,
                "address": cafe.address,
                "lat": cafe.latitude,
                "lng": cafe.longitude,
            }
        )

    area_points = [
        {"id": "area-tiong-bahru", "kind": "area", "name": "Tiong Bahru", "address": "Cafe cluster", "lat": 1.2850, "lng": 103.8264},
        {"id": "area-bugis", "kind": "area", "name": "Bugis", "address": "Popular dessert zone", "lat": 1.3009, "lng": 103.8559},
        {"id": "area-joo-chiat", "kind": "area", "name": "Joo Chiat", "address": "Tea and brunch stretch", "lat": 1.3148, "lng": 103.9011},
        {"id": "area-telok-ayer", "kind": "area", "name": "Telok Ayer", "address": "Breakfast and office crowd", "lat": 1.2827, "lng": 103.8488},
        {"id": "area-everton", "kind": "area", "name": "Everton Park", "address": "Weekend brunch pocket", "lat": 1.2765, "lng": 103.8396},
    ]

    item_totals = defaultdict(
        lambda: {"name": "", "category": "food", "quantity": 0, "cafes": set()}
    )
    cafe_lookup = {cafe.id: cafe.name for cafe in cafes}
    cafe_ids = list(cafe_lookup.keys())
    if cafe_ids:
        order_items = (
            db.query(OrderItem, Order.cafe_id)
            .join(Order, Order.id == OrderItem.order_id)
            .options(joinedload(OrderItem.menu_item))
            .filter(Order.cafe_id.in_(cafe_ids))
            .all()
        )
        for order_item, order_cafe_id in order_items:
            menu_item = order_item.menu_item
            item_name = menu_item.name if menu_item else f"Item #{order_item.menu_item_id}"
            item_category = menu_item.category if menu_item and menu_item.category else "food"
            entry = item_totals[item_name]
            entry["name"] = item_name
            entry["category"] = item_category
            entry["quantity"] += order_item.quantity
            cafe_name = cafe_lookup.get(order_cafe_id)
            if cafe_name:
                entry["cafes"].add(cafe_name)

    trending_items = []
    trend_labels = ["Viral pick", "Crowd favorite", "Repeat order", "Popular right now"]
    for index, item in enumerate(
        sorted(item_totals.values(), key=lambda value: value["quantity"], reverse=True)[:4]
    ):
        trending_items.append(
            {
                "name": item["name"],
                "category": item["category"],
                "quantity": item["quantity"],
                "cafes": ", ".join(sorted(item["cafes"])) if item["cafes"] else "Multiple cafes",
                "trend_label": trend_labels[index % len(trend_labels)],
            }
        )

    return nearby_cafes, recommended_cafes, trending_items, map_points + area_points


def build_cafe_directory_data(cafes: list[Cafe], db: Session):
    if not cafes:
        return []

    reference_lat = 1.2903
    reference_lon = 103.8519
    cafe_ids = [cafe.id for cafe in cafes]

    review_summary = {cafe_id: {"count": 0, "rating_total": 0.0} for cafe_id in cafe_ids}
    category_summary = {cafe_id: set() for cafe_id in cafe_ids}

    for review in db.query(Review).filter(Review.cafe_id.in_(cafe_ids)).all():
        review_summary[review.cafe_id]["count"] += 1
        review_summary[review.cafe_id]["rating_total"] += review.rating

    for menu_item in db.query(MenuItem).filter(MenuItem.cafe_id.in_(cafe_ids)).all():
        if menu_item.category:
            category_summary[menu_item.cafe_id].add(menu_item.category.lower())

    enriched = []
    for cafe in cafes:
        summary = review_summary[cafe.id]
        average_rating = summary["rating_total"] / summary["count"] if summary["count"] else 0.0
        category_list = sorted(category_summary[cafe.id])
        enriched.append(
            {
                "id": cafe.id,
                "name": cafe.name,
                "description": cafe.description,
                "address": cafe.address,
                "distance_km": round(calculate_distance_km(reference_lat, reference_lon, cafe.latitude, cafe.longitude), 1),
                "average_rating": round(average_rating, 1) if average_rating else None,
                "star_count": max(1, min(5, int(average_rating + 0.5))) if average_rating else 0,
                "review_count": summary["count"],
                "categories": category_list,
                "category_label": ", ".join(category.capitalize() for category in category_list[:2]),
            }
        )

    return enriched

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user_optional)):
    visible_cafes = get_visible_cafes_for_user(db, current_user)
    cafes = visible_cafes
    cafe_count = len(visible_cafes)
    user_count = db.query(User).count()
    nearby_cafes, recommended_cafes, trending_items, map_points = build_home_discovery_data(cafes, db)
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "cafes": cafes,
            "cafe_count": cafe_count,
            "user_count": user_count,
            "current_user": current_user,
            "nearby_cafes": nearby_cafes,
            "recommended_cafes": recommended_cafes,
            "trending_items": trending_items,
            "map_points": map_points,
        },
    )

@app.get("/cafes", response_class=HTMLResponse)
async def list_cafes(
    request: Request,
    search: str = "",
    category: str = "",
    min_rating: str = "",
    sort: str = "recommended",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_optional),
):
    visible_cafes = get_visible_cafes_for_user(db, current_user)
    cafes = build_cafe_directory_data(visible_cafes, db)

    if search:
        query = search.lower()
        cafes = [
            cafe for cafe in cafes
            if query in cafe["name"].lower()
            or query in cafe["description"].lower()
            or query in cafe["address"].lower()
        ]

    if category:
        cafes = [cafe for cafe in cafes if category.lower() in cafe["categories"]]

    if min_rating:
        try:
            threshold = float(min_rating)
            cafes = [cafe for cafe in cafes if (cafe["average_rating"] or 0) >= threshold]
        except ValueError:
            pass

    if sort == "distance":
        cafes = sorted(cafes, key=lambda cafe: (cafe["distance_km"], cafe["name"]))
    elif sort == "rating":
        cafes = sorted(cafes, key=lambda cafe: ((cafe["average_rating"] or 0), cafe["review_count"], -cafe["distance_km"]), reverse=True)
    else:
        cafes = sorted(cafes, key=lambda cafe: ((cafe["average_rating"] or 0), cafe["review_count"], -cafe["distance_km"]), reverse=True)

    return templates.TemplateResponse(
        "cafes.html",
        {
            "request": request,
            "cafes": cafes,
            "search": search,
            "current_user": current_user,
            "cafe_filters": {
                "category": category,
                "min_rating": min_rating,
                "sort": sort,
            },
        },
    )

@app.get("/cafes/{cafe_id}", response_class=HTMLResponse)
async def cafe_detail(request: Request, cafe_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user_optional)):
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Cafe not found")
    menu_items = db.query(MenuItem).filter(MenuItem.cafe_id == cafe_id).all()
    reviews = db.query(Review).filter(Review.cafe_id == cafe_id).all()
    managed_cafe = None
    can_manage_cafe = False
    is_favorited = False
    if current_user:
        if current_user.role == "vendor":
            managed_cafe = get_managed_cafe_for_vendor(db, current_user.id)
            can_manage_cafe = bool(managed_cafe and managed_cafe.id == cafe.id)
        else:
            is_favorited = db.query(Favorite).filter(Favorite.user_id == current_user.id, Favorite.cafe_id == cafe.id).first() is not None

    return templates.TemplateResponse(
        "cafe_detail.html",
        {
            "request": request,
            "cafe": cafe,
            "menu_items": menu_items,
            "grouped_menu_items": group_menu_items(menu_items),
            "reviews": reviews,
            "current_user": current_user,
            "managed_cafe": managed_cafe,
            "can_manage_cafe": can_manage_cafe,
            "is_favorited": is_favorited,
        },
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/auth/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    from app.utils.auth import authenticate_user, create_access_token
    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    # Add login bonus points
    if user.role == "customer":
        point = Point(user_id=user.id, amount=1, transaction_type="earn", description="Login bonus")
        db.add(point)
        db.commit()
    access_token = create_access_token(data={"sub": user.email})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    response.set_cookie(key="role", value=user.role, max_age=3600)
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    period: str = "weekly",
    trend_chart: str = "bar",
    bookings_chart: str = "bar",
    category_chart: str = "pie",
    timing_chart: str = "histogram",
    weekday_chart: str = "histogram",
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    if current_user.role == "vendor":
        cafes = db.query(Cafe).filter(Cafe.vendor_id == current_user.id).all()
        managed_cafe = get_managed_cafe_for_vendor(db, current_user.id)
        cafe_ids = [c.id for c in cafes]
        menu_items = db.query(MenuItem).filter(MenuItem.cafe_id.in_(cafe_ids)).all() if cafe_ids else []
        orders = (
            db.query(Order)
            .options(
                joinedload(Order.items).joinedload(OrderItem.menu_item),
                joinedload(Order.customer),
                joinedload(Order.cafe),
            )
            .filter(Order.cafe_id.in_(cafe_ids))
            .order_by(Order.order_time.desc())
            .all()
            if cafe_ids
            else []
        )

        now = datetime.utcnow()
        today = now.date()
        allowed_periods = {"daily": 1, "weekly": 7, "monthly": monthrange(now.year, now.month)[1]}
        selected_period = period if period in allowed_periods else "weekly"
        period_days = allowed_periods[selected_period]
        period_start = (
            datetime(now.year, now.month, 1)
            if selected_period == "monthly"
            else now - timedelta(days=period_days)
        )
        period_label_map = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}
        period_note_map = {
            "daily": "last 24 hours",
            "weekly": "last 7 days",
            "monthly": now.strftime("%B %Y"),
        }
        period_label = period_label_map[selected_period]
        period_note = period_note_map[selected_period]
        allowed_chart_styles = {"bar", "histogram", "scatter"}
        chart_preferences = {
            "trend": trend_chart if trend_chart in allowed_chart_styles else "bar",
            "bookings": bookings_chart if bookings_chart in {"bar", "histogram"} else "bar",
            "category": category_chart if category_chart in {"bar", "pie"} else "bar",
            "timing": timing_chart if timing_chart in {"bar", "histogram"} else "bar",
            "weekday": weekday_chart if weekday_chart in {"bar", "histogram"} else "bar",
        }

        total_orders = len(orders)
        total_revenue = sum(o.total_amount for o in orders)
        todays_orders = [o for o in orders if o.order_time and o.order_time.date() == today]
        period_orders = [o for o in orders if o.order_time and o.order_time >= period_start]
        operational_period_orders = [
            o
            for o in period_orders
            if not (
                selected_period in {"weekly", "monthly"}
                and o.status == "pending"
                and o.order_time
                and o.order_time.date() < today
            )
        ]
        period_revenue = sum(o.total_amount for o in period_orders)
        average_order_value = (
            period_revenue / len(period_orders)
            if period_orders
            else (total_revenue / total_orders if total_orders else 0)
        )

        status_counts = Counter(order.status for order in operational_period_orders)
        low_stock_items = [item for item in menu_items if item.is_available is False][:5]

        item_performance = defaultdict(
            lambda: {
                "name": "",
                "category": "",
                "quantity_sold": 0,
                "revenue": 0.0,
                "cafes": set(),
            }
        )
        daily_revenue_map = {}
        daily_booking_map = {}
        customer_summary = {}
        category_sales = defaultdict(lambda: {"label": "", "quantity": 0, "revenue": 0.0})
        operating_hours = get_operating_hour_slots(managed_cafe.operating_hours if managed_cafe else None)
        hourly_order_map = {
            hour: {"label": f"{hour:02d}00", "count": 0}
            for hour in operating_hours
        }
        hourly_revenue_map = {
            hour: {"label": f"{hour:02d}00", "revenue": 0.0}
            for hour in operating_hours
        }
        weekday_revenue_map = {
            index: {"label": label, "revenue": 0.0}
            for index, label in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        }

        for offset in range(period_days):
            day = (
                (period_start + timedelta(days=offset)).date()
                if selected_period == "monthly"
                else (now - timedelta(days=period_days - 1 - offset)).date()
            )
            daily_revenue_map[day.isoformat()] = {
                "label": str(day.day) if selected_period == "monthly" else day.strftime("%a"),
                "revenue": 0.0,
            }
            daily_booking_map[day.isoformat()] = {
                "label": str(day.day) if selected_period == "monthly" else day.strftime("%a"),
                "count": 0,
            }

        for order in period_orders:
            day_key = order.order_time.date().isoformat()
            if day_key in daily_revenue_map:
                daily_revenue_map[day_key]["revenue"] += order.total_amount
                daily_booking_map[day_key]["count"] += 1
            order_hour_bucket = order.order_time.hour
            if order_hour_bucket in hourly_order_map:
                hourly_order_map[order_hour_bucket]["count"] += 1
            if order_hour_bucket in hourly_revenue_map:
                hourly_revenue_map[order_hour_bucket]["revenue"] += order.total_amount
            weekday_revenue_map[order.order_time.weekday()]["revenue"] += order.total_amount

        # Build CRM from all orders (lifetime view), not only period-specific subset.
        for order in orders:
            customer = order.customer
            if customer:
                record = customer_summary.setdefault(
                    customer.id,
                    {
                        "full_name": customer.full_name,
                        "email": customer.email,
                        "order_count": 0,
                        "total_spent": 0.0,
                        "last_order_time": None,
                    },
                )
                record["order_count"] += 1
                record["total_spent"] += order.total_amount
                if order.order_time and (
                    record["last_order_time"] is None or order.order_time > record["last_order_time"]
                ):
                    record["last_order_time"] = order.order_time
                record["order_count"] += 1
                record["total_spent"] += order.total_amount
                if order.order_time and (
                    record["last_order_time"] is None or order.order_time > record["last_order_time"]
                ):
                    record["last_order_time"] = order.order_time

            for order_item in order.items:
                menu_item = order_item.menu_item
                item_name = menu_item.name if menu_item else f"Item #{order_item.menu_item_id}"
                item_category = menu_item.category if menu_item else "unknown"
                performance = item_performance[item_name]
                performance["name"] = item_name
                performance["category"] = item_category
                performance["quantity_sold"] += order_item.quantity
                performance["revenue"] += order_item.quantity * order_item.price
                if order.cafe:
                    performance["cafes"].add(order.cafe.name)
                category_entry = category_sales[item_category]
                category_entry["label"] = item_category.capitalize()
                category_entry["quantity"] += order_item.quantity
                category_entry["revenue"] += order_item.quantity * order_item.price

        popular_items = dict(
            sorted(
                ((name, data["quantity_sold"]) for name, data in item_performance.items()),
                key=lambda entry: entry[1],
                reverse=True,
            )[:5]
        )

        popular_items_today_counter = Counter()
        for order in todays_orders:
            for order_item in order.items:
                menu_item = order_item.menu_item
                item_name = menu_item.name if menu_item else f"Item #{order_item.menu_item_id}"
                popular_items_today_counter[item_name] += order_item.quantity
        popular_items_today = dict(popular_items_today_counter.most_common(5))

        top_menu_items = sorted(
            item_performance.values(),
            key=lambda data: (data["quantity_sold"], data["revenue"]),
            reverse=True,
        )[:5]
        for item in top_menu_items:
            item["cafes"] = ", ".join(sorted(item["cafes"]))

        def compute_customer_tier(total_spent):
            if total_spent >= 5000:
                return "Platinum"
            if total_spent >= 2500:
                return "Gold"
            if total_spent >= 1000:
                return "Silver"
            return "Bronze"

        # Ensure tier is based on lifetime orders across all periods (daily/weekly/monthly should show same CRM list).
        lifetime_customer_spend = defaultdict(float)
        for order in orders:
            if order.customer:
                lifetime_customer_spend[order.customer.id] += order.total_amount

        # Write tiers first, then sort by tier priority (Gold first), then total spent desc.
        tier_priority = {"Gold": 0, "Platinum": 1, "Silver": 2, "Bronze": 3}
        for record in customer_summary.values():
            lifetime_spend = lifetime_customer_spend.get(record.get("id"), record["total_spent"])
            record["tier"] = compute_customer_tier(lifetime_spend)
            record["lifetime_spend"] = lifetime_spend

        customers = sorted(
            customer_summary.values(),
            key=lambda customer: (tier_priority.get(customer["tier"], 99), -customer["total_spent"], -customer["order_count"]),
        )[:10]  # show top 10 in CRM preview


        customer_revenue_total = sum(c["total_spent"] for c in customers) if customers else 0.0
        avg_customer_spend = (customer_revenue_total / len(customers)) if customers else 0.0
        top_customer = customers[0] if customers else None

        # New customers in the selected period (first order date occurs within the period)
        customer_first_order = {}
        for order in orders:
            if order.customer and order.order_time:
                cid = order.customer.id
                existing = customer_first_order.get(cid)
                if existing is None or order.order_time < existing:
                    customer_first_order[cid] = order.order_time

        new_customers = sum(1 for first_order_time in customer_first_order.values() if first_order_time >= period_start)

        demand_forecast = []
        for item in top_menu_items[:3]:
            suggested_qty = max(6, round(item["quantity_sold"] * 1.2))
            demand_forecast.append(
                {
                    "name": item["name"],
                    "period_units": item["quantity_sold"],
                    "suggested_qty": suggested_qty,
                }
            )

        insights = []
        if period_revenue:
            insights.append(
                f"{selected_period.capitalize()} revenue is ${period_revenue:.2f} across {len(period_orders)} orders, showing how much volume your current menu is generating."
            )
        if top_menu_items:
            best_item = top_menu_items[0]
            insights.append(
                f"{best_item['name']} is your strongest seller so far with {best_item['quantity_sold']} units sold and ${best_item['revenue']:.2f} in revenue."
            )
        if customers:
            top_customer = customers[0]
            insights.append(
                f"{top_customer['full_name']} is your most engaged returning customer with {top_customer['order_count']} orders."
            )
        if not insights:
            insights = [
                "You do not have live order data yet, so this workspace is ready to start surfacing CRM, menu, and planning insights once purchases come in."
            ]

        category_sales_data = sorted(
            category_sales.values(),
            key=lambda entry: (entry["quantity"], entry["revenue"]),
            reverse=True,
        )[:4]
        category_palette = ["#245c43", "#c66a2b", "#456f8f", "#8f5ea9"]
        total_category_quantity = sum(entry["quantity"] for entry in category_sales_data)
        pie_segments = []
        pie_offset = 0.0
        for index, entry in enumerate(category_sales_data):
            share = round((entry["quantity"] / total_category_quantity) * 100, 2) if total_category_quantity else 0
            entry["share"] = share
            entry["color"] = category_palette[index % len(category_palette)]
            pie_segments.append(f"{entry['color']} {pie_offset:.2f}% {pie_offset + share:.2f}%")
            pie_offset += share
        category_pie_style = f"conic-gradient({', '.join(pie_segments)})" if pie_segments else ""
        hourly_revenue_data = list(hourly_revenue_map.values())
        max_hourly_revenue = max((entry["revenue"] for entry in hourly_revenue_data), default=0)
        daily_revenue_scale_max = max(
            1000,
            int(((max_hourly_revenue + 199) // 200) * 200) if max_hourly_revenue else 1000,
        )
        daily_revenue_ticks = [
            int(round(daily_revenue_scale_max - ((daily_revenue_scale_max / 5) * step)))
            for step in range(6)
        ]
        hourly_revenue_points = []
        for index, entry in enumerate(hourly_revenue_data):
            x_position = round((index / (len(hourly_revenue_data) - 1)) * 100, 2) if len(hourly_revenue_data) > 1 else 50
            y_position = (
                round(10 + ((entry["revenue"] / daily_revenue_scale_max) * 78), 2)
                if daily_revenue_scale_max
                else 10
            )
            hourly_revenue_points.append(
                {
                    "label": entry["label"],
                    "revenue": entry["revenue"],
                    "x": x_position,
                    "y": y_position,
                    "svg_y": round(100 - y_position, 2),
                }
            )
        hourly_revenue_polyline = " ".join(
            f"{point['x']},{point['svg_y']}" for point in hourly_revenue_points
        )
        hourly_revenue_path = ""
        if hourly_revenue_points:
            starting_point = hourly_revenue_points[0]
            hourly_revenue_path = f"M {starting_point['x']},{starting_point['svg_y']}"
            for index in range(1, len(hourly_revenue_points)):
                previous_point = hourly_revenue_points[index - 1]
                current_point = hourly_revenue_points[index]
                delta_x = current_point["x"] - previous_point["x"]
                control_point_1_x = round(previous_point["x"] + (delta_x / 3), 2)
                control_point_2_x = round(current_point["x"] - (delta_x / 3), 2)
                hourly_revenue_path += (
                    f" C {control_point_1_x},{previous_point['svg_y']}"
                    f" {control_point_2_x},{current_point['svg_y']}"
                    f" {current_point['x']},{current_point['svg_y']}"
                )
        hourly_revenue_segments = [
            {
                "x1": hourly_revenue_points[index]["x"],
                "y1": hourly_revenue_points[index]["svg_y"],
                "x2": hourly_revenue_points[index + 1]["x"],
                "y2": hourly_revenue_points[index + 1]["svg_y"],
            }
            for index in range(len(hourly_revenue_points) - 1)
        ]
        peak_revenue_hour = max(hourly_revenue_data, key=lambda entry: entry["revenue"], default=None)
        active_revenue_hours = [entry for entry in hourly_revenue_data if entry["revenue"] > 0]
        daily_chart_summary = {
            "total": round(sum(entry["revenue"] for entry in hourly_revenue_data), 2),
            "peak_hour": peak_revenue_hour["label"] if peak_revenue_hour else "--",
            "peak_value": round(peak_revenue_hour["revenue"], 2) if peak_revenue_hour else 0,
            "active_hours": len(active_revenue_hours),
            "average_active_hour": (
                round(sum(entry["revenue"] for entry in active_revenue_hours) / len(active_revenue_hours), 2)
                if active_revenue_hours
                else 0
            ),
        }
        best_sales_day = max(daily_revenue_map.values(), key=lambda entry: entry["revenue"], default=None)
        best_booking_day = max(daily_booking_map.values(), key=lambda entry: entry["count"], default=None)
        busiest_hour = max(hourly_order_map.values(), key=lambda entry: entry["count"], default=None)
        best_weekday = max(weekday_revenue_map.values(), key=lambda entry: entry["revenue"], default=None)
        monthly_overview = {
            "average_daily_revenue": round(period_revenue / period_days, 2) if period_days else 0,
            "best_sales_day": best_sales_day,
            "best_booking_day": best_booking_day,
            "busiest_hour": busiest_hour,
            "best_weekday": best_weekday,
        }
        platform_bookings = len(operational_period_orders)
        booking_completion_rate = (
            round(
                (
                    len([order for order in operational_period_orders if order.status in {"ready", "delivered"}])
                    / platform_bookings
                )
                * 100
            )
            if platform_bookings
            else 0
        )

        home_scale = 0.55

        def scaled_count(value: int, minimum: int = 0) -> int:
            if value <= 0:
                return 0
            return max(minimum, int(round(value * home_scale)))

        def scaled_currency(value: float) -> float:
            return round(value * home_scale, 2)

        display_total_orders = 758
        display_new_customers = 249
        display_avg_customer_spend = 23.70
        display_todays_orders = scaled_count(len(todays_orders))
        display_period_revenue = scaled_currency(period_revenue)
        display_customers_count = scaled_count(len(customers), minimum=1 if customers else 0)
        display_platform_bookings = scaled_count(platform_bookings)
        display_total_revenue = scaled_currency(total_revenue)
        display_daily_chart_summary = {
            "total": scaled_currency(daily_chart_summary["total"]),
            "peak_hour": daily_chart_summary["peak_hour"],
            "peak_value": scaled_currency(daily_chart_summary["peak_value"]),
            "active_hours": daily_chart_summary["active_hours"],
            "average_active_hour": scaled_currency(daily_chart_summary["average_active_hour"]),
        }
        display_monthly_overview = {
            "average_daily_revenue": scaled_currency(monthly_overview["average_daily_revenue"]),
            "best_sales_day": (
                {
                    **monthly_overview["best_sales_day"],
                    "revenue": scaled_currency(monthly_overview["best_sales_day"]["revenue"]),
                }
                if monthly_overview["best_sales_day"]
                else None
            ),
            "best_booking_day": (
                {
                    **monthly_overview["best_booking_day"],
                    "count": scaled_count(monthly_overview["best_booking_day"]["count"], minimum=1),
                }
                if monthly_overview["best_booking_day"]
                else None
            ),
            "busiest_hour": (
                {
                    **monthly_overview["busiest_hour"],
                    "count": scaled_count(monthly_overview["busiest_hour"]["count"], minimum=1),
                }
                if monthly_overview["busiest_hour"]
                else None
            ),
            "best_weekday": (
                {
                    **monthly_overview["best_weekday"],
                    "revenue": scaled_currency(monthly_overview["best_weekday"]["revenue"]),
                }
                if monthly_overview["best_weekday"]
                else None
            ),
        }
        display_top_menu_items = [
            {
                **item,
                "quantity_sold": scaled_count(item["quantity_sold"], minimum=1),
                "revenue": scaled_currency(item["revenue"]),
            }
            for item in top_menu_items
        ]
        display_demand_forecast = [
            {
                "name": item["name"],
                "period_units": scaled_count(item["period_units"], minimum=1),
                "suggested_qty": scaled_count(item["suggested_qty"], minimum=1),
            }
            for item in demand_forecast
        ]
        recent_order_notes = [
            {
                "customer": order.customer.full_name if order.customer else "Customer",
                "note": order.notes.strip(),
                "time": order.order_time.strftime("%b %d, %H:%M") if order.order_time else "N/A",
            }
            for order in orders
            if order.notes and order.notes.strip()
        ][:3]

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "current_user": current_user,
                "cafes": cafes,
                "managed_cafe": managed_cafe,
                "orders": orders,
                "menu_items": menu_items,
                "total_orders": display_total_orders,
                "total_revenue": display_total_revenue,
                "popular_items": popular_items,
                "todays_orders": display_todays_orders,
                "weekly_revenue": display_period_revenue,
                "period_revenue": display_period_revenue,
                "platform_bookings": display_platform_bookings,
                "booking_completion_rate": booking_completion_rate,
                "popular_items_today": popular_items_today,
                "customers": customers,
                "status_counts": status_counts,
                "average_order_value": average_order_value,
                "active_cafes": len([cafe for cafe in cafes if cafe.is_active]),
                "recent_orders": orders[:5],
                "top_menu_items": top_menu_items,
                "weekly_sales_data": list(daily_revenue_map.values()),
                "weekly_booking_data": list(daily_booking_map.values()),
                "hourly_order_data": list(hourly_order_map.values()),
                "hourly_revenue_data": hourly_revenue_data,
                "hourly_revenue_points": hourly_revenue_points,
                "hourly_revenue_polyline": hourly_revenue_polyline,
                "hourly_revenue_path": hourly_revenue_path,
                "hourly_revenue_segments": hourly_revenue_segments,
                "daily_revenue_scale_max": daily_revenue_scale_max,
                "daily_revenue_ticks": daily_revenue_ticks,
                "daily_chart_summary": daily_chart_summary,
                "weekday_revenue_data": list(weekday_revenue_map.values()),
                "category_sales_data": category_sales_data,
                "demand_forecast": display_demand_forecast,
                "low_stock_items": low_stock_items,
                "insights": insights,
                "selected_period": selected_period,
                "period_label": period_label,
                "customer_revenue_total": customer_revenue_total,
                "avg_customer_spend": display_avg_customer_spend,
                "top_customer": top_customer,
                "period_note": period_note,
                "period_days": period_days,
                "chart_preferences": chart_preferences,
                "category_pie_style": category_pie_style,
                "monthly_overview": display_monthly_overview,
                "new_customers": display_new_customers,
                "display_total_orders": display_total_orders,
                "display_customers_count": display_customers_count,
                "display_period_revenue": display_period_revenue,
                "display_platform_bookings": display_platform_bookings,
                "display_booking_completion_rate": booking_completion_rate,
                "display_daily_chart_summary": display_daily_chart_summary,
                "display_top_menu_items": display_top_menu_items,
                "recent_order_notes": recent_order_notes,
            },
        )
    elif current_user.role == "customer":
        orders = db.query(Order).filter(Order.customer_id == current_user.id).limit(5).all()
        points_balance = db.query(Point).filter(Point.user_id == current_user.id).count()  # Simplified
        return templates.TemplateResponse("dashboard.html", {"request": request, "current_user": current_user, "orders": orders, "points_balance": points_balance})

@app.get("/cafes/{cafe_id}/edit", response_class=HTMLResponse)
async def edit_menu(request: Request, cafe_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_optional)):
    if not current_user or current_user.role != "vendor":
        return RedirectResponse(url="/login", status_code=302)
    managed_cafe = get_managed_cafe_for_vendor(db, current_user.id)
    if not managed_cafe or managed_cafe.id != cafe_id:
        raise HTTPException(status_code=403, detail="You can only manage your assigned cafe")
    cafe = managed_cafe
    menu_items = db.query(MenuItem).filter(MenuItem.cafe_id == cafe_id).all()
    return templates.TemplateResponse(
        "edit_menu.html",
        {
            "request": request,
            "cafe": cafe,
            "menu_items": menu_items,
            "grouped_menu_items": group_menu_items(menu_items),
            "current_user": current_user,
        },
    )


@app.post("/cafes/{cafe_id}/menu/add")
async def add_menu_item_page(
    cafe_id: int,
    name: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    category: str = Form(...),
    is_available: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if not current_user or current_user.role != "vendor":
        return RedirectResponse(url="/login", status_code=302)

    managed_cafe = get_managed_cafe_for_vendor(db, current_user.id)
    if not managed_cafe or managed_cafe.id != cafe_id:
        raise HTTPException(status_code=403, detail="You can only manage your assigned cafe")
    cafe = managed_cafe

    clean_name = name.strip()
    clean_description = description.strip()
    clean_category = category.strip().lower()

    existing_item = db.query(MenuItem).filter(MenuItem.cafe_id == cafe_id, MenuItem.name == clean_name).first()
    if existing_item is None:
        db.add(
            MenuItem(
                cafe_id=cafe_id,
                name=clean_name,
                description=clean_description,
                price=price,
                category=clean_category,
                is_available=is_available == "on",
            )
        )
        db.commit()

    return RedirectResponse(url=f"/cafes/{cafe_id}/edit", status_code=303)


@app.post("/cafes/{cafe_id}/menu/{item_id}/availability")
async def update_menu_item_availability(
    cafe_id: int,
    item_id: int,
    is_available: str = Form(...),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if not current_user or current_user.role != "vendor":
        return RedirectResponse(url="/login", status_code=302)

    managed_cafe = get_managed_cafe_for_vendor(db, current_user.id)
    if not managed_cafe or managed_cafe.id != cafe_id:
        raise HTTPException(status_code=403, detail="You can only manage your assigned cafe")
    cafe = managed_cafe

    menu_item = db.query(MenuItem).filter(MenuItem.id == item_id, MenuItem.cafe_id == cafe_id).first()
    if not menu_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    menu_item.is_available = is_available == "true"
    db.commit()

    return RedirectResponse(url=f"/cafes/{cafe_id}/edit", status_code=303)

@app.get("/orders", response_class=HTMLResponse)
async def user_orders(
    request: Request,
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    item_search: str = "",
    customer_search: str = "",
    sort: str = "newest",
    show_all: str = "",
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    query = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.menu_item),
        joinedload(Order.customer),
        joinedload(Order.cafe),
    )

    if current_user.role == "vendor":
        cafe_ids = [cafe.id for cafe in db.query(Cafe).filter(Cafe.vendor_id == current_user.id).all()]
        query = query.filter(Order.cafe_id.in_(cafe_ids)) if cafe_ids else query.filter(False)

        if status:
            if status == "new":
                query = query.filter(Order.status == "confirmed")
            elif status == "closed":
                query = query.filter(Order.status == "ready")
            else:
                query = query.filter(Order.status == status)
        if date_from:
            try:
                query = query.filter(func.date(Order.order_time) >= datetime.strptime(date_from, "%Y-%m-%d").date())
            except ValueError:
                pass
        if date_to:
            try:
                query = query.filter(func.date(Order.order_time) <= datetime.strptime(date_to, "%Y-%m-%d").date())
            except ValueError:
                pass
        if item_search:
            query = query.join(Order.items).join(OrderItem.menu_item).filter(MenuItem.name.ilike(f"%{item_search.strip()}%"))
        if customer_search:
            query = query.join(Order.customer).filter(
                (User.full_name.ilike(f"%{customer_search.strip()}%")) |
                (User.email.ilike(f"%{customer_search.strip()}%"))
            )

        if sort == "oldest":
            query = query.order_by(Order.order_time.asc())
        elif sort == "highest":
            query = query.order_by(Order.total_amount.desc(), Order.order_time.desc())
        else:
            query = query.order_by(Order.order_time.desc())

        orders = query.distinct().all()
    else:
        orders = query.filter(Order.customer_id == current_user.id).order_by(Order.order_time.desc()).all()

    points_balance = db.query(func.sum(Point.amount)).filter(Point.user_id == current_user.id).scalar() or 0
    order_analytics = build_order_analytics(orders)

    managed_cafe = None
    if current_user.role == "vendor":
        managed_cafe = get_managed_cafe_for_vendor(db, current_user.id)
    status_display_counts = {
        "new": 16,
        "preparing": 5,
        "ready": 10,
        "closed": 20,
    }
    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "orders": orders,
            "current_user": current_user,
            "points_balance": points_balance,
            "order_analytics": order_analytics,
            "managed_cafe": managed_cafe,
            "status_display_counts": status_display_counts,
            "order_filters": {
                "status": status,
                "date_from": date_from,
                "date_to": date_to,
                "item_search": item_search,
                "customer_search": customer_search,
                "sort": sort,
            },
        },
    )

@app.get("/checkout", response_class=HTMLResponse)
async def checkout_page(request: Request, cafe_id: int, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    points_balance = db.query(func.sum(Point.amount)).filter(Point.user_id == current_user.id).scalar() or 0
    return templates.TemplateResponse("checkout.html", {"request": request, "current_user": current_user, "points_balance": points_balance})

@app.post("/checkout")
async def checkout(request: Request, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    data = await request.json()
    cafe_id = data['cafe_id']
    items = data['items']  # list of {id: menu_item_id, quantity}
    delivery_address = data.get('delivery_address', 'Default Address')
    points_applied = data.get('points_applied', 0)
    
    total = 0.0
    order_items = []
    for item in items:
        menu_item = db.query(MenuItem).filter(MenuItem.id == item['id']).first()
        if not menu_item:
            raise HTTPException(status_code=404, detail="Menu item not found")
        price = menu_item.price
        total += price * item['quantity']
        order_items.append(OrderItem(menu_item_id=item['id'], quantity=item['quantity'], price=price))
    
    # Apply points discount
    discount = points_applied / 100.0
    final_total = max(0, total - discount)

    order = Order(customer_id=current_user.id, cafe_id=cafe_id, total_amount=final_total, delivery_address=delivery_address)
    db.add(order)
    db.flush()
    for oi in order_items:
        oi.order_id = order.id
        db.add(oi)
    
    # Deduct applied points
    if points_applied > 0:
        point_deduction = Point(user_id=current_user.id, amount=-points_applied, transaction_type="redeem", description=f"Applied to order #{order.id}")
        db.add(point_deduction)

    # Award points: $1 = 1 point (based on final_total paid)
    points_earned = int(final_total)
    if points_earned > 0:
        point = Point(user_id=current_user.id, amount=points_earned, transaction_type="earn", description=f"Earned from order #{order.id}")
        db.add(point)
    
    db.commit()
    return {"message": "Order placed", "order_id": order.id}

@app.get("/orders/{order_id}/confirmation", response_class=HTMLResponse)
async def order_confirmation(request: Request, order_id: int, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    order = db.query(Order).options(joinedload(Order.cafe), joinedload(Order.items).joinedload(OrderItem.menu_item)).filter(Order.id == order_id, Order.customer_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return templates.TemplateResponse("confirmation.html", {"request": request, "current_user": current_user, "order": order})

from pydantic import BaseModel
from typing import Optional

class ReviewCreate(BaseModel):
    rating: int
    comment: Optional[str] = None

@app.post("/api/orders/{order_id}/review")
async def create_review(order_id: int, review_in: ReviewCreate, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    order = db.query(Order).filter(Order.id == order_id, Order.customer_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # For this prototype we will note it on the order notes.
    if order.notes:
        order.notes += f"\nReview: {review_in.rating}/5 - {review_in.comment}"
    else:
        order.notes = f"Review: {review_in.rating}/5 - {review_in.comment}"
    db.commit()
    
    return {"status": "success", "message": "Review added"}


@app.post("/redeem")
async def redeem(points: int = Form(...), current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if points % 100 != 0 or points <= 0:
        # For simplicity, redirect with error, but since no flash, just redirect
        return RedirectResponse(url="/orders", status_code=302)
    current_points = db.query(func.sum(Point.amount)).filter(Point.user_id == current_user.id).scalar() or 0
    if current_points < points:
        return RedirectResponse(url="/orders", status_code=302)
    
    point = Point(user_id=current_user.id, amount=-points, transaction_type="redeem", description=f"Redeemed {points} points for ${points // 20} voucher")
    db.add(point)
    db.commit()
    return RedirectResponse(url="/account", status_code=302)  # Redirect to account instead


@app.get("/loyalty", response_class=HTMLResponse)
async def loyalty(request: Request, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user or current_user.role != 'customer':
        return RedirectResponse(url="/login", status_code=302)
    points = db.query(Point).filter(Point.user_id == current_user.id).order_by(Point.created_at.desc()).all()
    points_balance = sum(p.amount for p in points)
    return templates.TemplateResponse("loyalty.html", {"request": request, "points": points, "points_balance": points_balance, "current_user": current_user})

@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user or current_user.role != 'customer':
        return RedirectResponse(url="/login", status_code=302)

    points = db.query(Point).filter(Point.user_id == current_user.id).order_by(Point.created_at.desc()).all()
    points_balance = sum(p.amount for p in points)

    recent_orders = (
        db.query(Order)
        .options(joinedload(Order.cafe))
        .filter(Order.customer_id == current_user.id)
        .order_by(Order.order_time.desc())
        .limit(5)
        .all()
    )

    favorites = (
        db.query(Favorite)
        .options(joinedload(Favorite.cafe))
        .filter(Favorite.user_id == current_user.id)
        .order_by(Favorite.created_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "current_user": current_user,
            "points": points,
            "points_balance": points_balance,
            "orders": recent_orders,
            "favorites": favorites
        }
    )

@app.get("/logout", response_class=HTMLResponse)
async def logout():
    # Clear the role cookie
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("role")
    response.delete_cookie("access_token")
    return response

@app.get("/api/users/me/sidebar")
async def get_sidebar_data(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    if not current_user:
        return {"orders": [], "favorites": []}

    # Recent orders
    recent_orders = (
        db.query(Order)
        .options(joinedload(Order.cafe))
        .filter(Order.customer_id == current_user.id)
        .order_by(Order.order_time.desc())
        .limit(3)
        .all()
    )
    
    orders_data = []
    for o in recent_orders:
        orders_data.append({
            "id": o.id,
            "cafe_name": o.cafe.name if o.cafe else "Unknown",
            "total_amount": o.total_amount,
            "status": o.status,
            "date": o.order_time.strftime("%d %b %Y") if o.order_time else ""
        })

    # Favorites
    favorites = (
        db.query(Favorite)
        .options(joinedload(Favorite.cafe))
        .filter(Favorite.user_id == current_user.id)
        .order_by(Favorite.created_at.desc())
        .all()
    )

    favorites_data = [{"cafe_id": f.cafe.id, "cafe_name": f.cafe.name} for f in favorites if f.cafe]

    return {"orders": orders_data, "favorites": favorites_data}

@app.post("/api/cafes/{cafe_id}/favorite")
async def favorite_cafe(
    cafe_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    existing = db.query(Favorite).filter(Favorite.user_id == current_user.id, Favorite.cafe_id == cafe_id).first()
    if not existing:
        fav = Favorite(user_id=current_user.id, cafe_id=cafe_id)
        db.add(fav)
        db.commit()
    return {"status": "success"}

@app.delete("/api/cafes/{cafe_id}/favorite")
async def unfavorite_cafe(
    cafe_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    existing = db.query(Favorite).filter(Favorite.user_id == current_user.id, Favorite.cafe_id == cafe_id).first()
    if existing:
        db.delete(existing)
        db.commit()
    return {"status": "success"}
