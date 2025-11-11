"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal

class Booking(BaseModel):
    """
    Bookings collection schema
    Collection name: "booking"
    """
    offer_id: str
    offer_title: str
    duration: str
    zone: Literal['cannes', 'hors-cannes']
    date: str  # ISO date (YYYY-MM-DD)
    time: str  # HH:MM
    name: str
    phone: str
    notes: Optional[str] = None
    amount: float
    currency: Literal['EUR'] = 'EUR'
    status: Literal['pending', 'paid', 'confirmed', 'cancelled'] = 'pending'
    paypal_order_id: Optional[str] = None
    sms_confirmed: bool = False

class CancellationToken(BaseModel):
    """Cancellation tokens collection for secure links"""
    booking_id: str
    token: str

