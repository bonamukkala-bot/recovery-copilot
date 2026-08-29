import requests

EVENT_ID = "c72c5f3c-dedb-475a-bc59-d5b8e5a3ed0b"
URL = f"http://127.0.0.1:8000/events/{EVENT_ID}/approve"

response = requests.post(URL)
print("Status code:", response.status_code)
print("Response:", response.json())
