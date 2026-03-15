from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utils.database import get_db
from app.utils.auth import get_current_user
from app.schemas.cafe import CafeCreate, Cafe
from app.schemas.menu_item import MenuItemCreate, MenuItem
from app.models.cafe import Cafe as CafeModel
from app.models.menu_item import MenuItem as MenuItemModel
from app.models.user import User

router = APIRouter()

@router.post("/", response_model=Cafe)
def create_cafe(cafe: CafeCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "vendor":
        raise HTTPException(status_code=403, detail="Only vendors can create cafes")
    db_cafe = CafeModel(**cafe.dict(), vendor_id=current_user.id)
    db.add(db_cafe)
    db.commit()
    db.refresh(db_cafe)
    return db_cafe

@router.get("/", response_model=list[Cafe])
def get_cafes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    cafes = db.query(CafeModel).offset(skip).limit(limit).all()
    return cafes

@router.get("/{cafe_id}", response_model=Cafe)
def get_cafe(cafe_id: int, db: Session = Depends(get_db)):
    cafe = db.query(CafeModel).filter(CafeModel.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Cafe not found")
    return cafe

@router.post("/{cafe_id}/menu", response_model=MenuItem)
def add_menu_item(cafe_id: int, item: MenuItemCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cafe = db.query(CafeModel).filter(CafeModel.id == cafe_id).first()
    if not cafe or cafe.vendor_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    db_item = MenuItemModel(**item.dict(), cafe_id=cafe_id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item