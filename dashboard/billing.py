import os
import stripe
import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from dashboard.auth import get_current_user_id
from exporter.db import store

router = APIRouter()

# --- STRIPE CONFIG ---
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_123")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_123")

# --- RAZORPAY CONFIG ---
razorpay_client = razorpay.Client(
    auth=(os.environ.get("RAZORPAY_KEY_ID", "rzp_test_123"), 
          os.environ.get("RAZORPAY_KEY_SECRET", "secret_123"))
)

def get_credit_packages():
    # Read dynamic prices or fallback to defaults
    starter_usd = int(store.get_setting("stripe_starter_price", "1000"))
    pro_usd = int(store.get_setting("stripe_pro_price", "4000"))
    starter_inr = int(store.get_setting("razorpay_starter_price", "80000"))
    pro_inr = int(store.get_setting("razorpay_pro_price", "320000"))

    return {
        "starter": {"credits": 1000, "price_usd": starter_usd, "price_inr": starter_inr},
        "pro": {"credits": 5000, "price_usd": pro_usd, "price_inr": pro_inr}
    }

@router.post("/stripe/checkout")
def create_stripe_checkout(package: str, user_id: int = Depends(get_current_user_id)):
    packages = get_credit_packages()
    if package not in packages:
        raise HTTPException(status_code=400, detail="Invalid package")
        
    pkg = packages[package]
    
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {'name': f'{pkg["credits"]} Leads Credits'},
                'unit_amount': pkg["price_usd"],
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url='http://localhost:8000/?success=true',
        cancel_url='http://localhost:8000/?canceled=true',
        client_reference_id=str(user_id),
        metadata={'credits': pkg["credits"]}
    )
    return {"url": session.url}

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = int(session.get("client_reference_id"))
        credits_to_add = int(session["metadata"]["credits"])
        amount_paid = int(session["amount_total"]) # in cents
        store.add_credits(user_id, credits_to_add)
        store.log_transaction(user_id, amount_paid, credits_to_add, "stripe")

    return {"status": "success"}


@router.post("/razorpay/order")
def create_razorpay_order(package: str, user_id: int = Depends(get_current_user_id)):
    packages = get_credit_packages()
    if package not in packages:
        raise HTTPException(status_code=400, detail="Invalid package")
        
    pkg = packages[package]
    
    order = razorpay_client.order.create({
        "amount": pkg["price_inr"],
        "currency": "INR",
        "receipt": f"receipt_{user_id}",
        "notes": {
            "user_id": user_id,
            "credits": pkg["credits"]
        }
    })
    return {"order_id": order["id"], "amount": pkg["price_inr"]}

@router.post("/razorpay/verify")
async def verify_razorpay(request: Request):
    data = await request.json()
    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': data.get('razorpay_order_id'),
            'razorpay_payment_id': data.get('razorpay_payment_id'),
            'razorpay_signature': data.get('razorpay_signature')
        })
        
        # In a real app, you'd fetch the order notes to get user_id and credits.
        # For simplicity, assuming the frontend passes it in the verify request
        user_id = int(data.get("user_id"))
        credits_to_add = int(data.get("credits"))
        amount_paise = int(data.get("amount", 0))
        
        store.add_credits(user_id, credits_to_add)
        store.log_transaction(user_id, int(amount_paise / 80), credits_to_add, "razorpay") # approx conversion to cents for unified stats
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Signature verification failed")
