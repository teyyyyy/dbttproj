from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.utils.database import Base

class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    cafe_id = Column(Integer, ForeignKey("cafes.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
