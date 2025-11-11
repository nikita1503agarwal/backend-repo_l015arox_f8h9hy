import os
import secrets
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson.objectid import ObjectId

from database import db, create_document
from schemas import Booking, CancellationToken

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Massage Booking API"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

# --- Booking Models for API ---
class CreateBookingRequest(BaseModel):
    offerId: str
    offerTitle: str
    duration: str
    zone: str
    date: str
    time: str
    name: str
    phone: str
    notes: Optional[str] = None
    amount: float
    currency: str = 'EUR'
    paypalOrderId: Optional[str] = None

class BookingResponse(BaseModel):
    id: str
    status: str
    smsSent: bool
    paypalOrderId: Optional[str] = None
    cancelUrl: Optional[str] = None
    modifyUrl: Optional[str] = None
    token: Optional[str] = None

# --- Helpers ---
BASE_URL = os.getenv("BACKEND_PUBLIC_URL", "")

def _public_link(path: str) -> Optional[str]:
    return f"{BASE_URL.rstrip('/')}{path}" if BASE_URL else None

# --- Endpoints ---
@app.post("/api/bookings", response_model=BookingResponse)
async def create_booking(payload: CreateBookingRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    doc = Booking(
        offer_id=payload.offerId,
        offer_title=payload.offerTitle,
        duration=payload.duration,
        zone=payload.zone,
        date=payload.date,
        time=payload.time,
        name=payload.name,
        phone=payload.phone,
        notes=payload.notes,
        amount=payload.amount,
        currency=payload.currency,
        status='confirmed' if payload.paypalOrderId else 'pending',
        paypal_order_id=payload.paypalOrderId,
    )

    booking_id = create_document('booking', doc)

    # create cancellation token
    token = secrets.token_urlsafe(24)
    create_document('cancellationtoken', CancellationToken(booking_id=str(booking_id), token=token))

    cancel_url = _public_link(f"/api/bookings/{booking_id}/cancel?token={token}")
    modify_url = _public_link(f"/api/bookings/{booking_id}/modify?token={token}")

    # Optional SMS sending via Twilio if credentials available
    sms_sent = False
    try:
        from twilio.rest import Client
        tw_sid = os.getenv('TWILIO_ACCOUNT_SID')
        tw_token = os.getenv('TWILIO_AUTH_TOKEN')
        tw_from = os.getenv('TWILIO_FROM_NUMBER')
        if tw_sid and tw_token and tw_from:
            client = Client(tw_sid, tw_token)
            text = (
                f"Confirmation Massage Cannes\n"
                f"{doc.name}, votre réservation est en statut {doc.status}.\n"
                f"Formule: {doc.offer_title} ({doc.duration})\n"
                f"Date: {doc.date} {doc.time}\n"
                f"Zone: {'Cannes' if doc.zone=='cannes' else 'Hors Cannes'}\n"
                f"Montant: {doc.amount} {doc.currency}\n"
                f"Annuler: {cancel_url or '—'}\n"
                f"Modifier: {modify_url or '—'}\n"
                + (f"PayPal: {doc.paypal_order_id}\n" if doc.paypal_order_id else "")
            )
            client.messages.create(to=doc.phone, from_=tw_from, body=text)
            sms_sent = True
    except Exception:
        sms_sent = False

    return BookingResponse(
        id=str(booking_id),
        status=doc.status,
        smsSent=sms_sent,
        paypalOrderId=doc.paypal_order_id,
        cancelUrl=cancel_url,
        modifyUrl=modify_url,
        token=token,
    )

@app.post("/api/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: str, token: str = Query("")):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    tok = db['cancellationtoken'].find_one({"booking_id": booking_id, "token": token})
    if not tok:
        raise HTTPException(status_code=403, detail="Invalid token")
    res = db['booking'].update_one({"_id": ObjectId(booking_id)}, {"$set": {"status": "cancelled", "updated_at": datetime.utcnow()}})
    return {"ok": True, "modified": res.modified_count}

@app.post("/api/bookings/{booking_id}/modify")
async def modify_booking(booking_id: str, token: str = Query(""), date: Optional[str] = None, time: Optional[str] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    tok = db['cancellationtoken'].find_one({"booking_id": booking_id, "token": token})
    if not tok:
        raise HTTPException(status_code=403, detail="Invalid token")
    updates = {}
    if date:
        updates['date'] = date
    if time:
        updates['time'] = time
    if not updates:
        raise HTTPException(status_code=400, detail="No changes provided")
    updates['updated_at'] = datetime.utcnow()
    res = db['booking'].update_one({"_id": ObjectId(booking_id)}, {"$set": updates})
    return {"ok": True, "modified": res.modified_count}

@app.delete("/api/bookings/{booking_id}")
async def delete_booking(booking_id: str, token: str = Query("")):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    tok = db['cancellationtoken'].find_one({"booking_id": booking_id, "token": token})
    if not tok:
        raise HTTPException(status_code=403, detail="Invalid token")
    res1 = db['booking'].delete_one({"_id": ObjectId(booking_id)})
    db['cancellationtoken'].delete_many({"booking_id": booking_id})
    return {"ok": True, "deleted": res1.deleted_count}
