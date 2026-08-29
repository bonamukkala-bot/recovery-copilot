import hmac
import hashlib
import json
import requests

WEBHOOK_SECRET = "test_secret_12345"
URL = "http://127.0.0.1:8000/webhook/razorpay"

payload = {
    "event": "payment.failed",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_llm_case_001",
                "order_id": "order_llm_case_001",
                "amount": 60000,
                "currency": "INR",
                "status": "failed",
                "error_code": "PAYMENT_ERROR",
                "error_description": "The customer's bank rejected the transaction citing a temporary hold on international transactions",
                "method": "card"
            }
        }
    }
}

body = json.dumps(payload).encode()
signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
headers = {"Content-Type": "application/json", "X-Razorpay-Signature": signature}

response = requests.post(URL, data=body, headers=headers)
print("Status code:", response.status_code)
print("Response:", response.json())