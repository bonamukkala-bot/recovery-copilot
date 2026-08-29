from datetime import datetime, timezone
from typing import Optional, TypedDict
import uuid


class DispatchResult(TypedDict):
    status: str
    message_body: Optional[str]
    provider_ref: Optional[str]
    sent_at: Optional[str]


# Per-channel message templates. {amount} is rupees (already converted from paise).
MESSAGE_TEMPLATES = {
    "sms": "Your payment of Rs.{amount} could not be completed. Retry here: https://pay.example.com/r/{order_id}",
    "whatsapp": "Hi! Your UPI request for Rs.{amount} expired. Tap to pay again: https://pay.example.com/r/{order_id}",
    "auto_retry": "We're automatically retrying your payment of Rs.{amount}. You'll get a confirmation shortly.",
    "voice_call": "Outbound Hinglish call queued for Rs.{amount} order — confirming intent to retry payment.",
}


def dispatch(
    channel: str,
    order_id: Optional[str],
    amount: Optional[int]
) -> DispatchResult:
    """
    Simulated dispatch — no real SMS/WhatsApp/voice provider wired up yet.
    Shaped like a real provider response so it's a drop-in swap later
    (e.g. Meta Cloud API, Twilio, Bolna AI).
    """
    rupees = (amount or 0) / 100

    if channel == "none" or channel not in MESSAGE_TEMPLATES:
        return {
            "status": "skipped",
            "message_body": None,
            "provider_ref": None,
            "sent_at": None
        }

    message_body = MESSAGE_TEMPLATES[channel].format(
        amount=f"{rupees:.2f}",
        order_id=order_id or "unknown"
    )

    return {
        "status": "sent",
        "message_body": message_body,
        "provider_ref": f"sim_{uuid.uuid4().hex[:12]}",
        "sent_at": datetime.now(timezone.utc).isoformat()
    }