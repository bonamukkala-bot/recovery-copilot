from datetime import datetime, timezone, timedelta
from typing import Optional, TypedDict
import uuid
from app.config import settings
from app.services.supabase_client import supabase
from app.services.hitl_gate import is_suppressed


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
    "voice_call": "Namaste! Hum Razorpay Recovery Copilot se bol rahe hain. Aapka order {order_id} ke liye Rs.{amount} payment complete nahi ho paya tha. Kya aap abhi payment retry karna chahte hain?",
}

# In-memory session counter for voice call safety circuit-breaker
_session_voice_calls_count = 0


def reset_voice_call_session_count():
    """Reset session counter for tests and demo environments."""
    global _session_voice_calls_count
    _session_voice_calls_count = 0


def _is_frequency_capped(contact: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Check if this customer identifier (phone/email) was already contacted
    within the last CONTACT_COOLDOWN_MINUTES.
    Returns (is_capped, last_contacted_timestamp).
    """
    if not contact:
        return False, None

    cooldown_minutes = getattr(settings, "contact_cooldown_minutes", 20)
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    cutoff_iso = cutoff_time.isoformat()

    try:
        res = (
            supabase.table("events")
            .select("id, dispatched_at, raw_payload")
            .eq("dispatch_status", "sent")
            .gte("dispatched_at", cutoff_iso)
            .order("dispatched_at", desc=True)
            .execute()
        )

        rows = res.data or []
        for row in rows:
            raw = row.get("raw_payload") or {}
            payment_entity = (
                raw.get("payload", {})
                .get("payment", {})
                .get("entity", {})
            )
            prior_contact = payment_entity.get("contact") or payment_entity.get("email")
            if prior_contact and str(prior_contact).strip() == str(contact).strip():
                return True, row.get("dispatched_at")

    except Exception as e:
        print(f"[Dispatcher Frequency Cap Warning] Failed checking past dispatches: {e}")

    return False, None


def send_sms(phone: Optional[str], message: str) -> DispatchResult:
    """
    Dispatches SMS to recipient.
    In 'mock' mode: logs simulation without network call and returns simulated success.
    In 'live' mode: connects to real SMS provider API (Twilio/Exotel/etc.).
    """
    mode = getattr(settings, "dispatch_mode", "mock").lower()
    phone_display = phone or "unknown"

    if mode == "mock":
        print(f"[MOCK DISPATCH] Would send SMS to {phone_display}: {message}")
        return {
            "status": "sent",
            "message_body": message,
            "provider_ref": f"mock_sms_{uuid.uuid4().hex[:12]}",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
    elif mode == "live":
        # Live SMS provider integration stub (e.g. Twilio / Exotel / Gupshup)
        # When provider credentials (e.g. TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)
        # are configured, perform real provider HTTP request here.
        raise NotImplementedError("Live SMS provider credentials not yet configured.")
    else:
        raise ValueError(f"Unsupported DISPATCH_MODE: {mode}")


def send_whatsapp(phone: Optional[str], message: str) -> DispatchResult:
    """
    Dispatches WhatsApp message to recipient.
    In 'mock' mode: logs simulation without network call and returns simulated success.
    In 'live' mode: connects to Meta WhatsApp Cloud API.
    """
    mode = getattr(settings, "dispatch_mode", "mock").lower()
    phone_display = phone or "unknown"

    if mode == "mock":
        print(f"[MOCK DISPATCH] Would send WhatsApp to {phone_display}: {message}")
        return {
            "status": "sent",
            "message_body": message,
            "provider_ref": f"mock_wa_{uuid.uuid4().hex[:12]}",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
    elif mode == "live":
        # Live Meta WhatsApp Cloud API stub (POST https://graph.facebook.com/v19.0/{phone_number_id}/messages)
        # When WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID are configured, perform real API request here.
        raise NotImplementedError("Live Meta WhatsApp Cloud API credentials not yet configured.")
    else:
        raise ValueError(f"Unsupported DISPATCH_MODE: {mode}")


def send_voice_call(
    phone: Optional[str],
    script: str,
    order_id: Optional[str] = None,
    amount: Optional[int] = None
) -> DispatchResult:
    """
    Dispatches outbound AI Voice Call (Bolna AI + Sarvam + GPT-4o-mini).
    In 'mock' mode: logs simulated call, respects session budget cap, and simulates a call outcome.
    In 'live' mode: connects to Bolna AI agent API.
    """
    global _session_voice_calls_count
    phone_display = phone or "unknown"
    max_voice_calls = getattr(settings, "max_voice_calls_per_session", 20)

    # Voice call budget cap check (circuit-breaker)
    if _session_voice_calls_count >= max_voice_calls:
        print(
            f"voice call budget cap reached — skipping voice dispatch for {phone_display} "
            f"(session count: {_session_voice_calls_count}/{max_voice_calls})"
        )
        return {
            "status": "skipped_budget_cap",
            "message_body": f"Skipped: session voice call budget cap ({max_voice_calls}) reached",
            "provider_ref": None,
            "sent_at": None,
        }

    mode = getattr(settings, "dispatch_mode", "mock").lower()

    if mode == "mock":
        _session_voice_calls_count += 1
        print(f"[MOCK VOICE CALL] Would call {phone_display} via Bolna AI. Script: {script}")

        # Deterministic simulation with priority on answered_promised_to_pay for reliable demo flow.
        # Supports test suffixes in order_id (e.g., '_noanswer' or '_declined') if explicitly requested.
        outcome = "answered_promised_to_pay"
        if order_id and "_noanswer" in order_id.lower():
            outcome = "no_answer"
        elif order_id and "_declined" in order_id.lower():
            outcome = "answered_declined"

        print(
            f"[MOCK VOICE CALL OUTCOME] Call to {phone_display} -> {outcome} "
            f"(session calls: {_session_voice_calls_count}/{max_voice_calls})"
        )

        if outcome == "answered_promised_to_pay":
            return {
                "status": "sent",
                "message_body": f"Voice Call (Bolna AI): {outcome} | Script: {script}",
                "provider_ref": f"mock_bolna_{uuid.uuid4().hex[:12]}",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        elif outcome == "no_answer":
            return {
                "status": "call_no_answer",
                "message_body": f"Voice Call (Bolna AI): customer did not answer | Script: {script}",
                "provider_ref": f"mock_bolna_{uuid.uuid4().hex[:12]}",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            return {
                "status": "call_declined",
                "message_body": f"Voice Call (Bolna AI): customer declined payment | Script: {script}",
                "provider_ref": f"mock_bolna_{uuid.uuid4().hex[:12]}",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }

    elif mode == "live":
        # LIVE STUB:
        # Requires:
        # 1. BOLNA_API_KEY for Agent Execution & Webhook callbacks
        # 2. SARVAM_API_KEY for Indian Accent / Hinglish TTS & ASR
        # 3. OPENAI_API_KEY (GPT-4o-mini) for conversational reasoning & intent extraction
        # Workflow: POST https://api.bolna.dev/agent/call with customer phone, prompt, & webhook URL.
        raise NotImplementedError("Live Bolna AI + Sarvam + GPT-4o-mini credentials not yet configured.")
    else:
        raise ValueError(f"Unsupported DISPATCH_MODE: {mode}")


def dispatch(
    channel: str,
    order_id: Optional[str],
    amount: Optional[int],
    contact: Optional[str] = None,
    event_id: Optional[str] = None
) -> DispatchResult:
    """
    Simulated dispatch with contact frequency capping, opt-out suppression gate,
    and channel execution routing.
    """
    rupees = (amount or 0) / 100

    if channel == "none" or channel not in MESSAGE_TEMPLATES:
        return {
            "status": "skipped",
            "message_body": None,
            "provider_ref": None,
            "sent_at": None
        }

    # Frequency cap check before firing dispatch (Step 5)
    if contact:
        is_capped, last_contacted_at = _is_frequency_capped(contact)
        if is_capped:
            print(f"contact frequency cap hit — skipping dispatch for {contact}, last contacted at {last_contacted_at}")
            return {
                "status": "skipped_frequency_cap",
                "message_body": f"Skipped: customer contacted within {settings.contact_cooldown_minutes}m cooldown (at {last_contacted_at})",
                "provider_ref": None,
                "sent_at": None
            }

    # Final suppression / opt-out gate before sending (Step 6)
    if contact and is_suppressed(contact):
        print(f"customer is suppressed/opted-out — dispatch blocked at final gate for {contact}")
        return {
            "status": "skipped_suppressed",
            "message_body": f"Skipped: customer {contact} is suppressed/opted-out",
            "provider_ref": None,
            "sent_at": None
        }

    message_body = MESSAGE_TEMPLATES[channel].format(
        amount=f"{rupees:.2f}",
        order_id=order_id or "unknown"
    )

    if channel == "sms":
        dispatch_result = send_sms(phone=contact, message=message_body)
    elif channel == "whatsapp":
        dispatch_result = send_whatsapp(phone=contact, message=message_body)
    elif channel == "voice_call":
        dispatch_result = send_voice_call(
            phone=contact,
            script=message_body,
            order_id=order_id,
            amount=amount
        )
    else:
        mode = getattr(settings, "dispatch_mode", "mock").lower()
        if mode == "mock":
            print(f"[MOCK DISPATCH] Would dispatch {channel} to {contact or 'system'}: {message_body}")
            dispatch_result = {
                "status": "sent",
                "message_body": message_body,
                "provider_ref": f"mock_{channel}_{uuid.uuid4().hex[:12]}",
                "sent_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            dispatch_result = {
                "status": "sent",
                "message_body": message_body,
                "provider_ref": f"sim_{uuid.uuid4().hex[:12]}",
                "sent_at": datetime.now(timezone.utc).isoformat()
            }

    # Track promise-to-pay on successful dispatch (Step 15)
    if dispatch_result.get("status") == "sent" and order_id:
        try:
            from app.services.promise_tracker import create_promise
            create_promise(
                order_id=order_id,
                amount=amount,
                event_id=event_id,
                phone=contact
            )
        except Exception as p_err:
            print(f"[Promise Tracker Warning] Failed tracking promise for order_id={order_id}: {p_err}")

    return dispatch_result