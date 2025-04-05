import os
from sqlalchemy import create_engine, Column, String, Float, Integer, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext
import uuid

# SQLite bilan ishlash uchun DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///surplus_saver.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    lat = Column(Float)
    lon = Column(Float)
    approved = Column(Integer, default=0)

class Bag(Base):
    __tablename__ = "bags"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    shop_id = Column(String, ForeignKey("users.id"), nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    pickup_start = Column(String, nullable=False)
    pickup_end = Column(String, nullable=False)
    category = Column(String, nullable=False)
    status = Column(String, default="available")

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("users.id"), nullable=False)
    bag_id = Column(String, ForeignKey("bags.id"), nullable=False)
    status = Column(String, default="pending")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("users.id"), nullable=False)
    shop_id = Column(String, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text)

def init_db():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        # Sample data
        if not db.query(User).filter_by(email="admin@example.com").first():
            admin = User(
                id="admin1", name="Admin", email="admin@example.com",
                password=pwd_context.hash("adminpass"), role="admin", lat=0, lon=0, approved=1
            )
            db.add(admin)
            db.commit()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()