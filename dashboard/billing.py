import os
import stripe
import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from dashboard.auth import get_current_user_id
from exporter.db import store

router = APIRouter()

# Keys are read from DB at request time so admin changes take effect immediately
def get_stripe_client():
    key = store.get_setting("stripe_secret_key", "") or os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Stripe not configured. Add keys in Admin Panel.")
    stripe.api_key = key
    return stripe

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_123")

def get_razorpay_client():
    key_id     = store.get_setting("razorpay_key_id", "")     or os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = store.get_setting("razorpay_key_secret", "") or os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        raise HTTPException(status_code=503, detail="Razorpay not configured. Add keys in Admin Panel.")
    return razorpay.Client(auth=(key_id, key_secret))

def get_credit_packages():
    starter_usd = int(store.get_setting("stripe_starter_price",   "1000")   or "1000")
    pro_usd     = int(store.get_setting("stripe_pro_price",       "4000")   or "4000")
    starter_inr = int(store.get_setting("razorpay_starter_price", "80000")  or "80000")
    pro_inr     = int(store.get_setting("razorpay_pro_price",     "320000") or "320000")
    starter_credits = int((store.get_setting("starter_credits", "1000") or "1000").replace(",", ""))
    pro_credits     = int((store.get_setting("pro_credits",     "5000") or "5000").replace(",", ""))
    return {
        "starter": {"credits": starter_credits, "price_usd": starter_usd, "price_inr": starter_inr},
        "pro":     {"credits": pro_credits,     "price_usd": pro_usd,     "price_inr": pro_inr},
    }

@router.post("/stripe/checkout")
def create_stripe_checkout(package: str, user_id: int = Depends(get_current_user_id)):
    stripe_client = get_stripe_client()
    packages = get_credit_packages()
    if package not in packages:
        raise HTTPException(status_code=400, detail="Invalid package")
    pkg = packages[package]
    base_url = store.get_setting("app_url", "https://gram.grafty.pro") or "https://gram.grafty.pro"
    session = stripe_client.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price_data": {"currency": "usd", "product_data": {"name": f'{pkg["credits"]:,} Leads Credits'}, "unit_amount": pkg["price_usd"]}, "quantity": 1}],
        mode="payment",
        success_url=f"{base_url}/app?success=true",
        cancel_url=f"{base_url}/app?canceled=true",
        client_reference_id=str(user_id),
        metadata={"credits": str(pkg["credits"])}
    )
    return {"url": session.url}

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = int(session.get("client_reference_id"))
        credits_to_add = int(session["metadata"]["credits"])
        amount_paid = int(session["amount_total"])
        store.add_credits(user_id, credits_to_add)
        store.log_transaction(user_id, amount_paid, credits_to_add, "stripe")
    return {"status": "success"}

@router.post("/razorpay/order")
def create_razorpay_order(package: str, user_id: int = Depends(get_current_user_id)):
    rzp = get_razorpay_client()
    packages = get_credit_packages()
    if package not in packages:
        raise HTTPException(status_code=400, detail="Invalid package")
    pkg = packages[package]
    order = rzp.order.create({
        "amount": pkg["price_inr"],
        "currency": "INR",
        "receipt": f"receipt_{user_id}",
        "notes": {"user_id": str(user_id), "credits": str(pkg["credits"])}
    })
    key_id = store.get_setting("razorpay_key_id", "") or os.environ.get("RAZORPAY_KEY_ID", "")
    return {"order_id": order["id"], "amount": pkg["price_inr"], "key_id": key_id, "credits": pkg["credits"]}

@router.post("/razorpay/verify")
async def verify_razorpay(request: Request):
    data = await request.json()
    try:
        rzp = get_razorpay_client()
        rzp.utility.verify_payment_signature({
            "razorpay_order_id":   data.get("razorpay_order_id"),
            "razorpay_payment_id": data.get("razorpay_payment_id"),
            "razorpay_signature":  data.get("razorpay_signature"),
        })
        user_id        = int(data.get("user_id"))
        credits_to_add = int(data.get("credits"))
        amount_paise   = int(data.get("amount", 0))
        store.add_credits(user_id, credits_to_add)
        store.log_transaction(user_id, int(amount_paise / 80), credits_to_add, "razorpay")
        return {"status": "success"}
    except Exception:
        raise HTTPException(status_code=400, detail="Signature verification failed")
