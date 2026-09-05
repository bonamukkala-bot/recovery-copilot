import hmac
import hashlib
import json
import requests

WEBHOOK_SECRET = "test_secret_12345"  # Match your .env value
URL = "http://127.0.0.1:8000/webhook/razorpay"

# Valid HMAC signature, but malformed payload (missing required 'id' inside payment.entity)
malformed_payload = {
    "event": "payment.failed",
    "payload": {
        "payment": {
            "entity": {
                "order_id": "order_test_malformed_001",
                "amount": 50000,
                "currency": "INR",
                "method": "card"
                # 'id' is missing intentionally!
            }
        }
    }
}

body = json.dumps(malformed_payload).encode()
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
print("Response:", json.dumps(response.json(), indent=2))
