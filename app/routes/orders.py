from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utils.database import get_db
from app.utils.auth import get_current_user
from app.schemas.order import OrderCreate, Order
from app.models.order import Order as OrderModel, OrderItem as OrderItemModel
from app.models.menu_item import MenuItem
from app.models.user import User

router = APIRouter()

@router.post("/", response_model=Order)
def create_order(order: OrderCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Calculate total
    total = 0
    order_items = []
    for item in order.items:
        menu_item = db.query(MenuItem).filter(MenuItem.id == item.menu_item_id).first()
        if not menu_item or not menu_item.is_available:
            raise HTTPException(status_code=400, detail="Invalid menu item")
        total += menu_item.price * item.quantity
        order_items.append(OrderItemModel(menu_item_id=item.menu_item_id, quantity=item.quantity, price=menu_item.price))

    db_order = OrderModel(
        customer_id=current_user.id,
        cafe_id=order.cafe_id,
        total_amount=total,
        delivery_address=order.delivery_address,
        notes=order.notes,
        status="preparing"
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    for item in order_items:
        item.order_id = db_order.id
        db.add(item)
    db.commit()

    return db_order

@router.get("/", response_model=list[Order])
def get_orders(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role == "customer":
        orders = db.query(OrderModel).filter(OrderModel.customer_id == current_user.id).all()
    elif current_user.role == "vendor":
        # Get orders for cafes owned by vendor
        from app.models.cafe import Cafe
        cafe_ids = [c.id for c in db.query(Cafe).filter(Cafe.vendor_id == current_user.id).all()]
        orders = db.query(OrderModel).filter(OrderModel.cafe_id.in_(cafe_ids)).all()
    else:
        orders = db.query(OrderModel).all()
    return orders
