from pydantic import BaseModel
from datetime import datetime

class PointBase(BaseModel):
    amount: float
    transaction_type: str
    description: str

class Point(PointBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True