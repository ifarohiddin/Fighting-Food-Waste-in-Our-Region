from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional
import sqlite3
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta
import os

# FastAPI ilovasini yaratamiz
app = FastAPI(title="SurplusSaver API")

# JWT sozlamalari
SECRET_KEY = "your-secret-key"  # Haqiqiy loyihada maxfiy kalit ishlatiladi
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Parolni shifrlash uchun
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 autentifikatsiyasi
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Ma'lumotlar bazasini sozlash
def init_db():
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('shop', 'customer', 'admin', 'superadmin'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER,
        description TEXT,
        original_price REAL,
        discounted_price REAL,
        quantity INTEGER,
        pickup_time TEXT,
        status TEXT DEFAULT 'available',
        FOREIGN KEY (shop_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        bag_id INTEGER,
        order_time TEXT,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY (customer_id) REFERENCES users(id),
        FOREIGN KEY (bag_id) REFERENCES bags(id)
    )''')
    conn.commit()
    conn.close()

# Pydantic modellar
class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str

class User(BaseModel):
    id: int
    username: str
    email: str
    role: str

class Token(BaseModel):
    access_token: str
    token_type: str

class BagCreate(BaseModel):
    description: str
    original_price: float
    discounted_price: float
    quantity: int
    pickup_time: str

class OrderCreate(BaseModel):
    bag_id: int

# Foydalanuvchi autentifikatsiyasi uchun yordamchi funksiyalar
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("SELECT id, username, email, role FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    conn.close()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return User(id=user[0], username=user[1], email=user[2], role=user[3])

# 1. Foydalanuvchi registratsiyasi
@app.post("/users/register", response_model=User)
async def register_user(user: UserCreate):
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    try:
        hashed_password = get_password_hash(user.password)
        c.execute("INSERT INTO users (username, email, hashed_password, role) VALUES (?, ?, ?, ?)",
                  (user.username, user.email, hashed_password, user.role))
        conn.commit()
        c.execute("SELECT id, username, email, role FROM users WHERE email = ?", (user.email,))
        new_user = c.fetchone()
        return User(id=new_user[0], username=new_user[1], email=new_user[2], role=new_user[3])
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()

# 2. Foydalanuvchi kirishi
@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("SELECT id, username, email, hashed_password, role FROM users WHERE email = ?", (form_data.username,))
    user = c.fetchone()
    conn.close()
    if not user or not verify_password(form_data.password, user[3]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user[2]}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# 3. Super Admin tomonidan Admin yaratish
@app.post("/superadmin/admins", response_model=User)
async def create_admin(user: UserCreate, current_user: User = Depends(get_current_user)):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized")
    user.role = "admin"
    return await register_user(user)

# 4. Do‘konlar uchun Surprise Bag ro‘yxatga kiritish
@app.post("/shops/{shop_id}/bags")
async def create_bag(shop_id: int, bag: BagCreate, current_user: User = Depends(get_current_user)):
    if current_user.role != "shop" or current_user.id != shop_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("INSERT INTO bags (shop_id, description, original_price, discounted_price, quantity, pickup_time) VALUES (?, ?, ?, ?, ?, ?)",
              (shop_id, bag.description, bag.original_price, bag.discounted_price, bag.quantity, bag.pickup_time))
    conn.commit()
    conn.close()
    return {"message": "Bag created successfully"}

# 5. Surprise Bag’larni ko‘rish
@app.get("/bags")
async def get_bags():
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("SELECT * FROM bags WHERE status = 'available'")
    bags = c.fetchall()
    conn.close()
    return [{"id": b[0], "shop_id": b[1], "description": b[2], "original_price": b[3], "discounted_price": b[4], "quantity": b[5], "pickup_time": b[6]} for b in bags]

# 6. Surprise Bag’ni sotib olish
@app.post("/customers/{customer_id}/buy/{bag_id}")
async def buy_bag(customer_id: int, bag_id: int, current_user: User = Depends(get_current_user)):
    if current_user.role != "customer" or current_user.id != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("SELECT quantity, status FROM bags WHERE id = ?", (bag_id,))
    bag = c.fetchone()
    if not bag or bag[1] != "available" or bag[0] <= 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Bag not available")
    c.execute("UPDATE bags SET quantity = quantity - 1 WHERE id = ?", (bag_id,))
    c.execute("INSERT INTO orders (customer_id, bag_id, order_time) VALUES (?, ?, ?)",
              (customer_id, bag_id, datetime.utcnow().isoformat()))
    if bag[0] == 1:
        c.execute("UPDATE bags SET status = 'sold' WHERE id = ?", (bag_id,))
    conn.commit()
    conn.close()
    return {"message": "Bag purchased successfully"}

# 7. Mijozning buyurtmalarini ko‘rish
@app.get("/customers/{customer_id}/orders")
async def get_orders(customer_id: int, current_user: User = Depends(get_current_user)):
    if current_user.role != "customer" or current_user.id != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE customer_id = ?", (customer_id,))
    orders = c.fetchall()
    conn.close()
    return [{"id": o[0], "bag_id": o[2], "order_time": o[3], "status": o[4]} for o in orders]

# 8. Surprise Bag’ni olib ketishni tasdiqlash
@app.post("/bags/{bag_id}/pickup")
async def confirm_pickup(bag_id: int, current_user: User = Depends(get_current_user)):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Not authorized")
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("UPDATE orders SET status = 'picked_up' WHERE bag_id = ? AND customer_id = ?", (bag_id, current_user.id))
    if c.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Order not found or not yours")
    conn.commit()
    conn.close()
    return {"message": "Pickup confirmed"}

# 9. Do‘konning ro‘yxatga kiritilgan sumkalarini ko‘rish
@app.get("/shops/{shop_id}/bags")
async def get_shop_bags(shop_id: int, current_user: User = Depends(get_current_user)):
    if current_user.role != "shop" or current_user.id != shop_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("SELECT * FROM bags WHERE shop_id = ?", (shop_id,))
    bags = c.fetchall()
    conn.close()
    return [{"id": b[0], "description": b[2], "original_price": b[3], "discounted_price": b[4], "quantity": b[5], "pickup_time": b[6], "status": b[7]} for b in bags]

# 10. Admin tomonidan foydalanuvchilarni boshqarish
@app.get("/admin/users")
async def get_users(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("SELECT id, username, email, role FROM users")
    users = c.fetchall()
    conn.close()
    return [{"id": u[0], "username": u[1], "email": u[2], "role": u[3]} for u in users]

@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, current_user: User = Depends(get_current_user)):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    if c.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.commit()
    conn.close()
    return {"message": "User deleted"}

# 11. Foydalanuvchi profilini yangilash
@app.patch("/users/me")
async def update_profile(username: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None, current_user: User = Depends(get_current_user)):
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    updates = []
    values = []
    if username:
        updates.append("username = ?")
        values.append(username)
    if email:
        updates.append("email = ?")
        values.append(email)
    if password:
        updates.append("hashed_password = ?")
        values.append(get_password_hash(password))
    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No updates provided")
    values.append(current_user.id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
    c.execute(query, values)
    conn.commit()
    c.execute("SELECT id, username, email, role FROM users WHERE id = ?", (current_user.id,))
    updated_user = c.fetchone()
    conn.close()
    return User(id=updated_user[0], username=updated_user[1], email=updated_user[2], role=updated_user[3])

# 12. Super Admin tomonidan do‘konlarni tasdiqlash
@app.patch("/superadmin/shops/{shop_id}/approve")
async def approve_shop(shop_id: int, current_user: User = Depends(get_current_user)):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized")
    conn = sqlite3.connect("surplus_saver.db")
    c = conn.cursor()
    c.execute("UPDATE users SET role = 'shop' WHERE id = ? AND role = 'customer'", (shop_id,))
    if c.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Shop not found or already approved")
    conn.commit()
    conn.close()
    return {"message": "Shop approved"}

# Ilovani ishga tushirishda DB-ni sozlash
if __name__ == "__main__":
    init_db()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)