from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"))
    cafe_id = Column(Integer, ForeignKey("cafes.id"))
    total_amount = Column(Float)
    status = Column(String, default="pending")  # pending, confirmed, preparing, ready, delivered
    order_time = Column(DateTime(timezone=True), server_default=func.now())
    delivery_address = Column(Text)
    notes = Column(Text, nullable=True)

    customer = relationship("User")
    cafe = relationship("Cafe", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"))
    quantity = Column(Integer)
    price = Column(Float)  # price at time of order

    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem")