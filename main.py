from collections import Counter, defaultdict
from datetime import datetime, timedelta
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
from app.models import User, Cafe, MenuItem, Order, OrderItem, Point, Review
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

    # Seed demo users if not exists
    customer = ensure_user("customer@gmail.com", "Jane Customer", "customer")
    vendor = ensure_user("vendor@gmail.com", "John Vendor", "vendor")
    repeat_customer = ensure_user("amelia@gmail.com", "Amelia Tan", "customer")
    office_customer = ensure_user("raj@gmail.com", "Raj Kumar", "customer")
    family_customer = ensure_user("siti@gmail.com", "Siti Rahman", "customer")

    cafe1 = ensure_cafe(
        vendor.id,
        "Cozy Corner Café",
        "A cozy spot for coffee, matcha drinks, and pastries.",
        "123 Main St, City",
        40.7128,
        -74.0060,
        "Mon-Fri 8AM-6PM",
    )
    cafe2 = ensure_cafe(
        vendor.id,
        "Brew & Bites",
        "Fresh brews, rice bowls, and comfort food for busy customers.",
        "456 Oak Ave, City",
        40.7589,
        -73.9851,
        "Daily 7AM-8PM",
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

    for item_name, description, price, category, is_available in cozy_corner_items:
        ensure_menu_item(cafe1.id, item_name, description, price, category, is_available)

    for item_name, description, price, category, is_available in brew_bites_items:
        ensure_menu_item(cafe2.id, item_name, description, price, category, is_available)

    if db.query(Review).filter(Review.user_id == customer.id, Review.cafe_id == cafe1.id).first() is None:
        db.add(Review(user_id=customer.id, cafe_id=cafe1.id, rating=5, comment="Amazing coffee and matcha selection!"))
    if db.query(Review).filter(Review.user_id == customer.id, Review.cafe_id == cafe2.id).first() is None:
        db.add(Review(user_id=customer.id, cafe_id=cafe2.id, rating=4, comment="Great sandwiches and reliable delivery."))
    db.commit()

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

seed_data(SessionLocal())
cleanup_duplicate_cafes(SessionLocal())
repair_orphaned_menu_items(SessionLocal())
cleanup_duplicate_menu_items(SessionLocal())

app = FastAPI(title="Café Discovery Platform", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

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

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user_optional)):
    cafes = db.query(Cafe).limit(6).all()
    cafe_count = db.query(Cafe).count()
    user_count = db.query(User).count()
    return templates.TemplateResponse("home.html", {"request": request, "cafes": cafes, "cafe_count": cafe_count, "user_count": user_count, "current_user": current_user})

@app.get("/cafes", response_class=HTMLResponse)
async def list_cafes(request: Request, search: str = "", db: Session = Depends(get_db), current_user = Depends(get_current_user_optional)):
    query = db.query(Cafe)
    if search:
        query = query.filter(Cafe.name.contains(search))
    cafes = query.all()
    return templates.TemplateResponse("cafes.html", {"request": request, "cafes": cafes, "search": search, "current_user": current_user})

@app.get("/cafes/{cafe_id}", response_class=HTMLResponse)
async def cafe_detail(request: Request, cafe_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user_optional)):
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Cafe not found")
    menu_items = db.query(MenuItem).filter(MenuItem.cafe_id == cafe_id).all()
    reviews = db.query(Review).filter(Review.cafe_id == cafe_id).all()
    return templates.TemplateResponse(
        "cafe_detail.html",
        {
            "request": request,
            "cafe": cafe,
            "menu_items": menu_items,
            "grouped_menu_items": group_menu_items(menu_items),
            "reviews": reviews,
            "current_user": current_user,
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
async def dashboard(request: Request, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    if current_user.role == "vendor":
        cafes = db.query(Cafe).filter(Cafe.vendor_id == current_user.id).all()
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
        week_ago = now - timedelta(days=7)

        total_orders = len(orders)
        total_revenue = sum(o.total_amount for o in orders)
        todays_orders = [o for o in orders if o.order_time and o.order_time.date() == today]
        weekly_orders = [o for o in orders if o.order_time and o.order_time >= week_ago]
        weekly_revenue = sum(o.total_amount for o in weekly_orders)
        average_order_value = total_revenue / total_orders if total_orders else 0

        status_counts = Counter(order.status for order in orders)
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

        for offset in range(6, -1, -1):
            day = (now - timedelta(days=offset)).date()
            daily_revenue_map[day.isoformat()] = {
                "label": day.strftime("%a"),
                "revenue": 0.0,
            }
            daily_booking_map[day.isoformat()] = {
                "label": day.strftime("%a"),
                "count": 0,
            }

        for order in orders:
            if order.order_time and order.order_time >= week_ago:
                day_key = order.order_time.date().isoformat()
                if day_key in daily_revenue_map:
                    daily_revenue_map[day_key]["revenue"] += order.total_amount
                    daily_booking_map[day_key]["count"] += 1

            customer = order.customer
            if customer:
                record = customer_summary.setdefault(
                    customer.id,
                    {
                        "full_name": customer.full_name,
                        "email": customer.email,
                        "order_count": 0,
                        "total_spent": 0.0,
                        "last_order_time": order.order_time,
                    },
                )
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

        customers = sorted(
            customer_summary.values(),
            key=lambda customer: (customer["order_count"], customer["total_spent"]),
            reverse=True,
        )[:6]

        demand_forecast = []
        for item in top_menu_items[:3]:
            suggested_qty = max(6, round(item["quantity_sold"] * 1.2))
            demand_forecast.append(
                {
                    "name": item["name"],
                    "weekly_units": item["quantity_sold"],
                    "suggested_qty": suggested_qty,
                }
            )

        insights = []
        if weekly_revenue:
            insights.append(
                f"Weekly revenue is ${weekly_revenue:.2f} across {len(weekly_orders)} orders, showing how much volume your current menu is generating."
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
        platform_bookings = len(weekly_orders)
        booking_completion_rate = (
            round(
                (
                    len([order for order in weekly_orders if order.status in {"ready", "delivered"}])
                    / platform_bookings
                )
                * 100
            )
            if platform_bookings
            else 0
        )

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "current_user": current_user,
                "cafes": cafes,
                "orders": orders,
                "menu_items": menu_items,
                "total_orders": total_orders,
                "total_revenue": total_revenue,
                "popular_items": popular_items,
                "todays_orders": len(todays_orders),
                "weekly_revenue": weekly_revenue,
                "platform_bookings": platform_bookings,
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
                "category_sales_data": category_sales_data,
                "demand_forecast": demand_forecast,
                "low_stock_items": low_stock_items,
                "insights": insights,
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
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id, Cafe.vendor_id == current_user.id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Cafe not found")
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

    cafe = db.query(Cafe).filter(Cafe.id == cafe_id, Cafe.vendor_id == current_user.id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Cafe not found")

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

@app.get("/orders", response_class=HTMLResponse)
async def user_orders(request: Request, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    query = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.menu_item),
        joinedload(Order.customer),
        joinedload(Order.cafe),
    )

    if current_user.role == "vendor":
        cafe_ids = [cafe.id for cafe in db.query(Cafe).filter(Cafe.vendor_id == current_user.id).all()]
        orders = query.filter(Order.cafe_id.in_(cafe_ids)).order_by(Order.order_time.desc()).all() if cafe_ids else []
    else:
        orders = query.filter(Order.customer_id == current_user.id).order_by(Order.order_time.desc()).all()

    points_balance = db.query(func.sum(Point.amount)).filter(Point.user_id == current_user.id).scalar() or 0
    order_analytics = build_order_analytics(orders)
    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "orders": orders,
            "current_user": current_user,
            "points_balance": points_balance,
            "order_analytics": order_analytics,
        },
    )

@app.post("/checkout")
async def checkout(request: Request, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    data = await request.json()
    cafe_id = data['cafe_id']
    items = data['items']  # list of {id: menu_item_id, quantity}
    delivery_address = data.get('delivery_address', 'Default Address')
    
    total = 0.0
    order_items = []
    for item in items:
        menu_item = db.query(MenuItem).filter(MenuItem.id == item['id']).first()
        if not menu_item:
            raise HTTPException(status_code=404, detail="Menu item not found")
        price = menu_item.price
        total += price * item['quantity']
        order_items.append(OrderItem(menu_item_id=item['id'], quantity=item['quantity'], price=price))
    
    order = Order(customer_id=current_user.id, cafe_id=cafe_id, total_amount=total, delivery_address=delivery_address)
    db.add(order)
    db.flush()
    for oi in order_items:
        oi.order_id = order.id
        db.add(oi)
    
    # Award points: $1 = 1 point
    points_earned = int(total)
    if points_earned > 0:
        point = Point(user_id=current_user.id, amount=points_earned, transaction_type="earn", description=f"Earned from order #{order.id}")
        db.add(point)
    
    db.commit()
    return {"message": "Order placed", "order_id": order.id}

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
    return RedirectResponse(url="/loyalty", status_code=302)  # Redirect to loyalty instead

@app.get("/loyalty", response_class=HTMLResponse)
async def loyalty(request: Request, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user or current_user.role != 'customer':
        return RedirectResponse(url="/login", status_code=302)
    points = db.query(Point).filter(Point.user_id == current_user.id).order_by(Point.created_at.desc()).all()
    points_balance = sum(p.amount for p in points)
    return templates.TemplateResponse("loyalty.html", {"request": request, "points": points, "points_balance": points_balance, "current_user": current_user})

@app.get("/logout", response_class=HTMLResponse)
async def logout():
    # Clear the role cookie
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("role")
    response.delete_cookie("access_token")
    return response
