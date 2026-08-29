import hmac
import hashlib
import json
import requests

WEBHOOK_SECRET = "test_secret_12345"  # must match your .env value
URL = "http://127.0.0.1:8000/webhook/razorpay"

sample_payload = {
    "event": "payment.failed",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_test123456789",
                "order_id": "order_test987654321",
                "amount": 50000,
                "currency": "INR",
                "status": "failed",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Payment failed due to insufficient funds",
                "method": "upi"
            }
        }
    }
}

body = json.dumps(sample_payload).encode()

signature = hmac.new(
    key=WEBHOOK_SECRET.encode(),
    msg=body,
    digestmod=hashlib.sha256
).hexdigest()

headers = {
    "Content-Type": "application/json",
    "X-Razorpay-Signature": signature
}

response = requests.post(URL, data=body, headers=headers)
print("Status code:", response.status_code)
print("Response:", response.json())