"""Razorpay REST boundary. Credentials are read only from environment settings."""
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Payment


def _api(path, method="GET", body=None):
    key, secret = settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET
    if not key or not secret:
        raise ValidationError("Online payments are not configured. Contact the site administrator.")
    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("https://api.razorpay.com/v1/" + path, data=data, method=method,
                                 headers={"Authorization": "Basic " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        raise ValidationError("The payment gateway could not complete the request. Please retry.") from exc


def create_gateway_order(payment):
    response = _api("orders", "POST", {"amount": int(payment.amount * 100), "currency": payment.currency,
                                         "receipt": str(payment.booking.reference)[:40],
                                         "notes": {"booking": str(payment.booking.reference)}})
    if response.get("amount") != int(payment.amount * 100) or response.get("currency") != payment.currency or not response.get("id"):
        raise ValidationError("The payment gateway returned an order that does not match this booking.")
    payment.gateway_order_id = response["id"]
    payment.status = Payment.Status.PENDING
    payment.save(update_fields=["gateway_order_id", "status", "updated_at"])
    return payment


def verify_checkout(payment, gateway_order_id, gateway_payment_id, signature):
    secret = settings.RAZORPAY_KEY_SECRET
    if payment.status == Payment.Status.REFUNDED:
        raise ValidationError("This payment has already been refunded.")
    if not payment.gateway_order_id or not hmac.compare_digest(payment.gateway_order_id, gateway_order_id):
        raise ValidationError("The payment order does not match this booking.")
    signed = f"{gateway_order_id}|{gateway_payment_id}".encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        if payment.status != Payment.Status.SUCCEEDED:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
        raise ValidationError("Payment verification failed.")
    transaction = _api(f"payments/{gateway_payment_id}")
    if transaction.get("order_id") != payment.gateway_order_id or transaction.get("amount") != int(payment.amount * 100) or transaction.get("currency") != payment.currency:
        raise ValidationError("The gateway payment does not match the expected booking amount.")
    if transaction.get("status") != "captured":
        raise ValidationError("The gateway has not confirmed a captured payment yet.")
    payment.gateway_payment_id = gateway_payment_id
    payment.status = Payment.Status.SUCCEEDED
    payment.verified_at = timezone.now()
    payment.save(update_fields=["gateway_payment_id", "status", "verified_at", "updated_at"])
    from .notifications import notify_booking
    notify_booking(payment.booking, f"payment-{gateway_payment_id}", "Payment confirmed for your booking.", payment.booking.customer)
    notify_booking(payment.booking, f"payment-provider-{gateway_payment_id}", "A customer payment was confirmed.", payment.booking.service.provider.user)
    return payment
