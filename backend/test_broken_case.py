import hmac
import hashlib
import json
import requests

WEBHOOK_SECRET = "test_secret_12345"
URL = "http://127.0.0.1:8000/webhook/razorpay"

# Deliberately malformed/ambiguous — no error_code, no error_description,
# an unusual method. Nothing in classifier.py's rules will match this.
broken_payload = {
    "event": "payment.failed",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_broken_case_001",
                "order_id": "order_broken_case_001",
                "amount": 45000,
                "currency": "INR",
                "status": "failed",
                "error_code": None,
                "error_description": None,
                "method": "wallet"
            }
        }
    }
}

body = json.dumps(broken_payload).encode()

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