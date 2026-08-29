import hmac
import hashlib
import json
import requests

WEBHOOK_SECRET = "test_secret_12345"
URL = "http://127.0.0.1:8000/webhook/razorpay"

sample_payload = {
    "event": "payment.captured",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_test_outcome_001_retry",
                "order_id": "order_test_outcome_001",
                "amount": 50000,
                "currency": "INR",
                "status": "captured",
                "method": "upi"
            }
        }
    }
}

body = json.dumps(sample_payload).encode()
signature = hmac.new(key=WEBHOOK_SECRET.encode(), msg=body, digestmod=hashlib.sha256).hexdigest()
headers = {"Content-Type": "application/json", "X-Razorpay-Signature": signature}

response = requests.post(URL, data=body, headers=headers)
print("Status code:", response.status_code)
print("Response:", response.json())
