from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from pydantic import BaseModel
from typing import Optional
from app.utils.database import get_db
from app.utils.auth import get_current_user
from app.models.message import Message
from app.models.cafe import Cafe
from app.models.user import User

from fastapi import Request

def get_user_from_cookie(request: Request, db: Session = Depends(get_db)):
    role = request.cookies.get("role", "customer")
    if role == "vendor":
        return db.query(User).filter(User.role == "vendor").first()
    return db.query(User).filter(User.role == "customer").first()

router = APIRouter()

class MessageCreate(BaseModel):
    content: str
    customer_id: Optional[int] = None

@router.get("/{cafe_id}")
def get_chat_history(cafe_id: int, request: Request, customer_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(get_user_from_cookie)):
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Cafe not found")
        
    if current_user.role == "customer":
        target_customer_id = current_user.id
    else:
        if cafe.vendor_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
        if not customer_id:
            raise HTTPException(status_code=400, detail="Customer ID required for vendor")
        target_customer_id = customer_id
        
    messages = db.query(Message).filter(
        Message.cafe_id == cafe_id,
        or_(
            and_(Message.sender_id == target_customer_id, Message.receiver_id == cafe.vendor_id),
            and_(Message.sender_id == cafe.vendor_id, Message.receiver_id == target_customer_id)
        )
    ).order_by(Message.timestamp.asc()).all()
    
    # Mark received messages as read
    unreads = [msg for msg in messages if msg.receiver_id == current_user.id and not msg.is_read]
    for msg in unreads:
        msg.is_read = True
    if unreads:
        db.commit()
    
    result = []
    for msg in messages:
        result.append({
            "id": msg.id,
            "sender_id": msg.sender_id,
            "receiver_id": msg.receiver_id,
            "content": msg.content,
            "timestamp": msg.timestamp.strftime("%b %d, %I:%M %p"),
            "is_read": msg.is_read,
            "is_mine": msg.sender_id == current_user.id
        })
    return result

@router.post("/{cafe_id}")
def send_message(cafe_id: int, msg: MessageCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_user_from_cookie)):
    cafe = db.query(Cafe).filter(Cafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404)
        
    if current_user.role == "customer":
        receiver_id = cafe.vendor_id
    else:
        if cafe.vendor_id != current_user.id:
            raise HTTPException(status_code=403)
        receiver_id = msg.customer_id
        if not receiver_id:
            raise HTTPException(status_code=400, detail="Customer ID required")
            
    new_message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        cafe_id=cafe_id,
        content=msg.content
    )
    db.add(new_message)
    
    if current_user.role == "customer":
        auto_reply = Message(
            sender_id=cafe.vendor_id,
            receiver_id=current_user.id,
            cafe_id=cafe_id,
            content="Of course you can get it today! We will send you a message when it's ready. Let us know if you need anything else!"
        )
        db.add(auto_reply)
        
    db.commit()
    return {"status": "success"}
