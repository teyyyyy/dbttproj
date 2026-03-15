from pydantic import BaseModel
from typing import Optional

class CafeBase(BaseModel):
    name: str
    description: str
    address: str
    latitude: float
    longitude: float
    operating_hours: str

class CafeCreate(CafeBase):
    pass

class Cafe(CafeBase):
    id: int
    vendor_id: int
    is_active: bool

    class Config:
        from_attributes = True