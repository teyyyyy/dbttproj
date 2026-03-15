from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class OrderItemBase(BaseModel):
    menu_item_id: int
    quantity: int

class OrderItem(OrderItemBase):
    id: int
    price: float

    class Config:
        from_attributes = True

class OrderBase(BaseModel):
    cafe_id: int
    delivery_address: str
    notes: Optional[str] = None
    items: List[OrderItemBase]

class OrderCreate(OrderBase):
    pass

class Order(OrderBase):
    id: int
    customer_id: int
    total_amount: float
    status: str
    order_time: datetime

    class Config:
        from_attributes = True