from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utils.database import get_db
from app.utils.auth import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/stats")
def get_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    # Placeholder for stats
    vendor_count = db.query(User).filter(User.role == "vendor").count()
    customer_count = db.query(User).filter(User.role == "customer").count()
    return {"vendors": vendor_count, "customers": customer_count}