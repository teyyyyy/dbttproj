from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.routes import auth, cafes, orders, admin
from app.utils.database import engine, Base, get_db, SessionLocal
from app.models import User, Cafe, MenuItem, Order, OrderItem, Point, Review
from app.utils.auth import get_password_hash, get_current_user

# Create database tables
Base.metadata.create_all(bind=engine)

# Seed sample data
def seed_data(db: Session):
    # Seed demo users if not exists
    if db.query(User).filter(User.email == "customer@gmail.com").first() is None:
        customer = User(email="customer@gmail.com", hashed_password=get_password_hash("customer"), full_name="Jane Customer", role="customer")
        db.add(customer)
        db.commit()
        db.refresh(customer)
    if db.query(User).filter(User.email == "vendor@gmail.com").first() is None:
        vendor = User(email="vendor@gmail.com", hashed_password=get_password_hash("vendor"), full_name="John Vendor", role="vendor")
        db.add(vendor)
        db.commit()
        db.refresh(vendor)

    if db.query(Cafe).count() == 0:
        vendor = db.query(User).filter(User.email == "vendor@gmail.com").first()
        if vendor:
            # Create cafés
            cafe1 = Cafe(vendor_id=vendor.id, name="Cozy Corner Café", description="A cozy spot for coffee and pastries.", address="123 Main St, City", latitude=40.7128, longitude=-74.0060, operating_hours="Mon-Fri 8AM-6PM")
            cafe2 = Cafe(vendor_id=vendor.id, name="Brew & Bites", description="Fresh brews and delicious bites.", address="456 Oak Ave, City", latitude=40.7589, longitude=-73.9851, operating_hours="Daily 7AM-8PM")
            db.add(cafe1)
            db.add(cafe2)
            db.commit()
            db.refresh(cafe1)
            db.refresh(cafe2)

            # Create menu items
            items = [
                MenuItem(cafe_id=cafe1.id, name="Espresso", description="Strong and bold coffee.", price=3.50, category="drink"),
                MenuItem(cafe_id=cafe1.id, name="Cappuccino", description="Espresso with steamed milk.", price=4.00, category="drink"),
                MenuItem(cafe_id=cafe1.id, name="Croissant", description="Buttery, flaky pastry.", price=2.50, category="food"),
                MenuItem(cafe_id=cafe1.id, name="Avocado Toast", description="Toasted bread with avocado.", price=7.00, category="food"),
                MenuItem(cafe_id=cafe2.id, name="Latte", description="Smooth espresso with milk.", price=4.50, category="drink"),
                MenuItem(cafe_id=cafe2.id, name="Americano", description="Espresso diluted with water.", price=3.00, category="drink"),
                MenuItem(cafe_id=cafe2.id, name="Club Sandwich", description="Turkey, bacon, lettuce, tomato.", price=9.50, category="food"),
                MenuItem(cafe_id=cafe2.id, name="Muffin", description="Blueberry muffin.", price=3.00, category="food"),
            ]
            for item in items:
                db.add(item)
            db.commit()

        # Create reviews
        review1 = Review(user_id=customer.id, cafe_id=cafe1.id, rating=5, comment="Amazing coffee!")
        review2 = Review(user_id=customer.id, cafe_id=cafe2.id, rating=4, comment="Great sandwiches.")
        db.add(review1)
        db.add(review2)
        db.commit()

seed_data(SessionLocal())

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
    return templates.TemplateResponse("cafe_detail.html", {"request": request, "cafe": cafe, "menu_items": menu_items, "reviews": reviews, "current_user": current_user})

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
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    if current_user.role == "vendor":
        cafes = db.query(Cafe).filter(Cafe.vendor_id == current_user.id).all()
        orders = db.query(Order).filter(Order.cafe_id.in_([c.id for c in cafes])).all()
        # Analytics
        total_orders = len(orders)
        total_revenue = sum(o.total_amount for o in orders)
        todays_orders = total_orders  # Simulate
        weekly_revenue = total_revenue  # Simulate
        popular_items = {}  # Placeholder
        popular_items_today = popular_items  # Simulate
        # CRM: customers
        customer_ids = set(o.customer_id for o in orders)
        customers = []
        for cid in customer_ids:
            customer = db.query(User).filter(User.id == cid).first()
            if customer:
                order_count = len([o for o in orders if o.customer_id == cid])
                customer.order_count = order_count
                customers.append(customer)
        return templates.TemplateResponse("dashboard.html", {"request": request, "current_user": current_user, "cafes": cafes, "orders": orders, "total_orders": total_orders, "total_revenue": total_revenue, "popular_items": popular_items, "todays_orders": todays_orders, "weekly_revenue": weekly_revenue, "popular_items_today": popular_items_today, "customers": customers})
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
    return templates.TemplateResponse("edit_menu.html", {"request": request, "cafe": cafe, "menu_items": menu_items, "current_user": current_user})

@app.get("/orders", response_class=HTMLResponse)
async def user_orders(request: Request, current_user: User = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    from sqlalchemy.orm import joinedload
    orders = db.query(Order).options(joinedload(Order.items).joinedload(OrderItem.menu_item)).filter(Order.customer_id == current_user.id).all()
    points_balance = db.query(func.sum(Point.amount)).filter(Point.user_id == current_user.id).scalar() or 0
    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders, "current_user": current_user, "points_balance": points_balance})

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
    return response