import requests

URL = "http://127.0.0.1:8000/events"

response = requests.get(URL)
data = response.json()

events = data if isinstance(data, list) else data.get("events") or data.get("data") or []

target = "pay_test_outcome_001"
found = [e for e in events if e.get("payment_id") == target]

if not found:
    print(f"No event found with payment_id={target}")
    print(f"Total events returned: {len(events)}")
else:
    for e in found:
        print("id:", e.get("id"))
        print("payment_id:", e.get("payment_id"))
        print("amount:", e.get("amount"))
        print("requires_approval:", e.get("requires_approval"))
        print("approval_status:", e.get("approval_status"))
        print("dispatch_status:", e.get("dispatch_status"))
        print("dispatch_message:", e.get("dispatch_message"))
        print("recovery_channel:", e.get("recovery_channel"))
        print("recovery_reason:", e.get("recovery_reason"))
        print("outcome_status:", e.get("outcome_status"))
        print("recovered_at:", e.get("recovered_at"))
        print("created_at:", e.get("created_at"))
        print("-" * 40)
