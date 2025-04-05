from pydantic import BaseModel
from typing import Optional

class User(BaseModel):
    name: str
    email: str
    password: str
    role: str
    lat: float
    lon: float

class UserUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

class Bag(BaseModel):
    description: str
    price: float
    quantity: int
    pickup_start: str
    pickup_end: str
    category: str

class Review(BaseModel):
    rating: int
    comment: str