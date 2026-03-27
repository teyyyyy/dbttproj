from sqlalchemy import Column, Integer, String, Text, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.utils.database import Base

class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    cafe_id = Column(Integer, ForeignKey("cafes.id"))
    name = Column(String, index=True)
    description = Column(Text)
    price = Column(Float)
    category = Column(String)  # e.g., drink, food
    is_available = Column(Boolean, default=True)
    image_url = Column(String, nullable=True)

    cafe = relationship("Cafe", back_populates="menu_items")
    cost = Column(Float, default=0.0, nullable=False)