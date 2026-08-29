import requests

EVENT_ID = "52dbb468-3c09-4031-aed3-b0a19ba7866b"
URL = f"http://127.0.0.1:8000/events/{EVENT_ID}/reject"

response = requests.post(URL)
print("Status code:", response.status_code)
print("Response:", response.json())
