import hmac
import hashlib
import json
import random
import time
import requests

WEBHOOK_SECRET = "test_secret_12345"
URL = "http://127.0.0.1:8000/webhook/razorpay"

# Realistic failure scenarios, matching the PRD's failure-type table
SCENARIOS = [
    {
        "error_code": "BAD_REQUEST_ERROR",
        "error_description": "Payment failed due to insufficient funds",
        "method": "card",
        "weight": 6,
    },
    {
        "error_code": "GATEWAY_ERROR",
        "error_description": "UPI collect request expired before approval",
        "method": "upi",
        "weight": 5,
    },
    {
        "error_code": "SERVER_ERROR",
        "error_description": "Payment failed due to a network timeout",
        "method": "netbanking",
        "weight": 4,
    },
    {
        "error_code": "BAD_REQUEST_ERROR",
        "error_description": "Card declined by bank — risk rule triggered",
        "method": "card",
        "weight": 4,
    },
    {
        "error_code": None,
        "error_description": "Payment authorization failed",
        "method": "upi",
        "weight": 3,
    },
]

# Weighted pool so common failure types appear more often, like real traffic
POOL = []
for s in SCENARIOS:
    POOL.extend([s] * s["weight"])


def build_payload(index: int) -> dict:
    scenario = random.choice(POOL)
    amount = random.choice([25000, 50000, 75000, 120000, 150000, 250000])  # paise

    return {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_batch_{index:03d}",
                    "order_id": f"order_batch_{index:03d}",
                    "amount": amount,
                    "currency": "INR",
                    "status": "failed",
                    "error_code": scenario["error_code"],
                    "error_description": scenario["error_description"],
                    "method": scenario["method"],
                }
            }
        }
    }


def send_event(payload: dict) -> int:
    body = json.dumps(payload).encode()
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
    return response.status_code


def main(count: int = 55):
    success = 0
    failed = 0

    for i in range(1, count + 1):
        payload = build_payload(i)
        status = send_event(payload)

        if status == 200:
            success += 1
            print(f"[{i}/{count}] OK - {payload['payload']['payment']['entity']['error_description'][:40]}")
        else:
            failed += 1
            print(f"[{i}/{count}] FAILED (status {status})")

        time.sleep(0.15)  # small delay so it doesn't hammer Supabase

    print(f"\nDone. {success} succeeded, {failed} failed out of {count}.")


if __name__ == "__main__":
    main()