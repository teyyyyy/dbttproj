from sqlalchemy import Column, Integer, String, Text, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.utils.database import Base

class Cafe(Base):
    __tablename__ = "cafes"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, index=True)
    description = Column(Text)
    address = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    operating_hours = Column(String)  # JSON string or text
    is_active = Column(Boolean, default=True)

    vendor = relationship("User")
    menu_items = relationship("MenuItem", back_populates="cafe")
    orders = relationship("Order", back_populates="cafe")
    favorited_by = relationship("Favorite", backref="cafe", cascade="all, delete-orphan")