import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from math import radians, sin, cos, sqrt, atan2
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from models import User, UserUpdate, Bag, Review
from database import get_db, User as UserModel, Bag as BagModel, Order as OrderModel, Review as ReviewModel, init_db, pwd_context
from auth import get_current_user, check_role, create_access_token, create_refresh_token
from tasks import send_notification

app = FastAPI(title="SurplusSaver API")

# CORS sozlamalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371  # Earth radius in km
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

@app.get("/")
def root():
    return {"message": "Welcome to SurplusSaver API! Visit /docs for API documentation."}

# User-related endpoints
@app.post("/users/register")
def register(user: User, db: Session = Depends(get_db)):
    if db.query(UserModel).filter_by(email=user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = pwd_context.hash(user.password)
    db_user = UserModel(name=user.name, email=user.email, password=hashed_password, role=user.role, lat=user.lat, lon=user.lon)
    db.add(db_user)
    db.commit()
    return {"id": db_user.id}

@app.post("/users/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserModel).filter_by(email=form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token({"sub": user.id})
    refresh_token = create_refresh_token({"sub": user.id})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@app.get("/users/me")
def get_user(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(UserModel).filter_by(id=current_user["id"]).first()
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "lat": user.lat,
        "lon": user.lon,
        "approved": user.approved
    }

@app.patch("/users/me")
def update_user(update: UserUpdate, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(UserModel).filter_by(id=current_user["id"]).first()
    if update.name:
        user.name = update.name
    if update.password:
        user.password = pwd_context.hash(update.password)
    if update.lat is not None:
        user.lat = update.lat
    if update.lon is not None:
        user.lon = update.lon
    db.commit()
    return {"message": "Profile updated"}

@app.post("/users/notifications/subscribe")
def subscribe_notifications(device_token: str, current_user: dict = Depends(get_current_user)):
    send_notification.delay(current_user["id"], "Subscribed to notifications")
    return {"message": "Subscribed"}

# Shop-related endpoints
@app.post("/shops/{shop_id}/bags")
def create_bag(shop_id: str, bag: Bag, current_user: dict = Depends(check_role(["shop"])), db: Session = Depends(get_db)):
    if current_user["id"] != shop_id:
        raise HTTPException(status_code=403, detail="Not your shop")
    db_bag = BagModel(shop_id=shop_id, **bag.dict())
    db.add(db_bag)
    db.commit()
    return {"id": db_bag.id}

@app.get("/shops/{shop_id}/bags")
def get_shop_bags(shop_id: str, status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(BagModel).filter(BagModel.shop_id == shop_id)
    if status:
        query = query.filter(BagModel.status == status)
    bags = query.all()
    return [{"id": b.id, "description": b.description, "price": b.price, "quantity": b.quantity, "status": b.status} for b in bags]

@app.patch("/shops/{shop_id}/bags/{bag_id}")
def update_bag(shop_id: str, bag_id: str, bag: Bag, current_user: dict = Depends(check_role(["shop"])), db: Session = Depends(get_db)):
    if current_user["id"] != shop_id:
        raise HTTPException(status_code=403, detail="Not your shop")
    db_bag = db.query(BagModel).filter_by(id=bag_id, shop_id=shop_id).first()
    if not db_bag:
        raise HTTPException(status_code=404, detail="Bag not found")
    db_bag.description = bag.description
    db_bag.price = bag.price
    db_bag.quantity = bag.quantity
    db_bag.pickup_start = bag.pickup_start
    db_bag.pickup_end = bag.pickup_end
    db_bag.category = bag.category
    db.commit()
    return {"message": "Bag updated"}

@app.delete("/shops/{shop_id}/bags/{bag_id}")
def delete_bag(shop_id: str, bag_id: str, current_user: dict = Depends(check_role(["shop"])), db: Session = Depends(get_db)):
    if current_user["id"] != shop_id:
        raise HTTPException(status_code=403, detail="Not your shop")
    db_bag = db.query(BagModel).filter_by(id=bag_id, shop_id=shop_id, status="available").first()
    if not db_bag:
        raise HTTPException(status_code=404, detail="Bag not found or already sold")
    db.delete(db_bag)
    db.commit()
    return {"message": "Bag deleted"}

@app.get("/shops/{shop_id}/reviews")
def get_reviews(shop_id: str, db: Session = Depends(get_db)):
    reviews = db.query(ReviewModel).filter_by(shop_id=shop_id).all()
    return [{"id": r.id, "rating": r.rating, "comment": r.comment} for r in reviews]

# Bag-related endpoints
@app.get("/bags")
def browse_bags(lat: Optional[float] = None, lon: Optional[float] = None, radius: Optional[float] = None, 
                category: Optional[str] = None, sort_by: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(BagModel).filter(BagModel.status == "available")
    if category:
        query = query.filter(BagModel.category == category)
    bags = query.all()
    
    result = []
    for bag in bags:
        shop = db.query(UserModel).filter_by(id=bag.shop_id).first()
        distance = haversine(lat, lon, shop.lat, shop.lon) if lat and lon else None
        if radius and distance and distance > radius:
            continue
        result.append({"id": bag.id, "shop_id": bag.shop_id, "description": bag.description, 
                       "price": bag.price, "quantity": bag.quantity, "distance": distance})
    
    if sort_by == "price":
        result.sort(key=lambda x: x["price"])
    elif sort_by == "distance" and lat and lon:
        result.sort(key=lambda x: x["distance"])
    
    return result

@app.post("/bags/{bag_id}/pickup")
def confirm_pickup(bag_id: str, code: str, current_user: dict = Depends(check_role(["customer", "shop"])), db: Session = Depends(get_db)):
    order = db.query(OrderModel).filter_by(bag_id=bag_id, status="pending").first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or already picked up")
    if code != "1234":  # Hozircha oddiy kod, keyin dinamik qilinadi
        raise HTTPException(status_code=400, detail="Invalid pickup code")
    order.status = "picked_up"
    db.commit()
    send_notification.delay(order.customer_id, f"Bag {bag_id} picked up")
    return {"message": "Pickup confirmed"}

@app.get("/bags/{bag_id}/status")
def get_bag_status(bag_id: str, db: Session = Depends(get_db)):
    bag = db.query(BagModel).filter_by(id=bag_id).first()
    if not bag:
        raise HTTPException(status_code=404, detail="Bag not found")
    return {"status": bag.status}

# Customer-related endpoints
@app.post("/customers/{customer_id}/buy/{bag_id}")
def buy_bag(customer_id: str, bag_id: str, current_user: dict = Depends(check_role(["customer"])), db: Session = Depends(get_db)):
    if current_user["id"] != customer_id:
        raise HTTPException(status_code=403, detail="Not your account")
    bag = db.query(BagModel).filter_by(id=bag_id, status="available").first()
    if not bag or bag.quantity <= 0:
        raise HTTPException(status_code=404, detail="Bag not available")
    order = OrderModel(customer_id=customer_id, bag_id=bag_id)
    bag.quantity -= 1
    if bag.quantity == 0:
        bag.status = "sold"
    db.add(order)
    db.commit()
    send_notification.delay(customer_id, f"Order {order.id} placed for bag {bag_id}")
    return {"order_id": order.id}

@app.get("/customers/{customer_id}/orders")
def get_orders(customer_id: str, status: Optional[str] = None, current_user: dict = Depends(check_role(["customer"])), db: Session = Depends(get_db)):
    if current_user["id"] != customer_id:
        raise HTTPException(status_code=403, detail="Not your account")
    query = db.query(OrderModel).filter_by(customer_id=customer_id)
    if status:
        query = query.filter_by(status=status)
    orders = query.all()
    return [{"id": o.id, "bag_id": o.bag_id, "status": o.status} for o in orders]

@app.post("/customers/{customer_id}/orders/{order_id}/cancel")
def cancel_order(customer_id: str, order_id: str, current_user: dict = Depends(check_role(["customer"])), db: Session = Depends(get_db)):
    if current_user["id"] != customer_id:
        raise HTTPException(status_code=403, detail="Not your account")
    order = db.query(OrderModel).filter_by(id=order_id, customer_id=customer_id, status="pending").first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or not cancellable")
    order.status = "cancelled"
    bag = db.query(BagModel).filter_by(id=order.bag_id).first()
    bag.quantity += 1
    db.commit()
    return {"message": "Order cancelled"}

@app.post("/customers/{customer_id}/reviews/{shop_id}")
def submit_review(customer_id: str, shop_id: str, review: Review, current_user: dict = Depends(check_role(["customer"])), db: Session = Depends(get_db)):
    if current_user["id"] != customer_id:
        raise HTTPException(status_code=403, detail="Not your account")
    review_id = str(uuid.uuid4())
    db_review = ReviewModel(id=review_id, customer_id=customer_id, shop_id=shop_id, rating=review.rating, comment=review.comment)
    db.add(db_review)
    db.commit()
    return {"id": review_id}

# Admin-related endpoints
@app.post("/superadmin/admins")
def create_admin(user: User, current_user: dict = Depends(check_role(["admin"])), db: Session = Depends(get_db)):
    if current_user["id"] != "admin1":
        raise HTTPException(status_code=403, detail="Only superadmin can create admins")
    user_id = str(uuid.uuid4())
    hashed_password = pwd_context.hash(user.password)
    db_user = UserModel(id=user_id, name=user.name, email=user.email, password=hashed_password, role="admin", lat=user.lat, lon=user.lon, approved=1)
    db.add(db_user)
    db.commit()
    return {"id": user_id}

@app.get("/admin/users")
def list_users(role: Optional[str] = None, current_user: dict = Depends(check_role(["admin"])), db: Session = Depends(get_db)):
    query = db.query(UserModel)
    if role:
        query = query.filter_by(role=role)
    users = query.all()
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role} for u in users]

@app.delete("/admin/users/{user_id}")
def delete_user(user_id: str, current_user: dict = Depends(check_role(["admin"])), db: Session = Depends(get_db)):
    user = db.query(UserModel).filter_by(id=user_id).first()
    if not user or user.role == "admin":
        raise HTTPException(status_code=404, detail="User not found or admin")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

@app.patch("/superadmin/shops/{shop_id}/approve")
def approve_shop(shop_id: str, current_user: dict = Depends(check_role(["admin"])), db: Session = Depends(get_db)):
    if current_user["id"] != "admin1":
        raise HTTPException(status_code=403, detail="Only superadmin can approve shops")
    shop = db.query(UserModel).filter_by(id=shop_id, role="shop").first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    shop.approved = 1
    db.commit()
    return {"message": "Shop approved"}

@app.get("/admin/statistics")
def get_statistics(current_user: dict = Depends(check_role(["admin"])), db: Session = Depends(get_db)):
    bags_sold = db.query(BagModel).filter_by(status="sold").count()
    co2_saved = bags_sold * 2.5  # Approx 2.5kg CO2 per bag saved
    return {"bags_sold": bags_sold, "co2_saved_kg": co2_saved}