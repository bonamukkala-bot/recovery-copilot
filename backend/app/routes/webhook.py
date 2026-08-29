from fastapi import APIRouter, Request, HTTPException, Header
import hmac
import hashlib
from datetime import datetime, timezone
from app.config import settings
from app.services.supabase_client import supabase
from app.services.classifier import classify_failure, classify_failure_llm
from app.services.decision_engine import decide_recovery_action
from app.services.dispatcher import dispatch
from app.services.hitl_gate import is_suppressed, check_approval_gate

router = APIRouter()


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify Razorpay webhook signature using HMAC-SHA256."""
    expected_signature = hmac.new(
        key=secret.encode(),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)


def handle_payment_failed(event_type: str, payment_entity: dict, payload: dict):
    """Existing failure pipeline: classify -> decide -> suppression/approval gate -> dispatch -> log."""
    failure_type = classify_failure(
        error_code=payment_entity.get("error_code"),
        error_description=payment_entity.get("error_description"),
        method=payment_entity.get("method")
    )

    llm_classified = False
    if failure_type is None:
        failure_type = classify_failure_llm(
            error_code=payment_entity.get("error_code"),
            error_description=payment_entity.get("error_description"),
            method=payment_entity.get("method")
        )
        llm_classified = failure_type is not None

    

    decision = decide_recovery_action(
        failure_type=failure_type,
        amount=payment_entity.get("amount")
    )

    channel = decision["channel"]
    reason = decision["reason"]
    amount = payment_entity.get("amount")

    # Identify the customer for suppression lookup — contact phone first, email fallback
    identifier = payment_entity.get("contact") or payment_entity.get("email")

    # --- Hard opt-out check: overrides everything, no exceptions ---
    if is_suppressed(identifier):
        channel = "none"
        reason = "Customer opted out — contact suppressed, no action taken"
        requires_approval = False
        approval_status = "not_required"
        dispatch_result = {
            "status": "suppressed",
            "message_body": None,
            "sent_at": None,
        }
    else:
        # --- HITL approval gate ---
        requires_approval, approval_status = check_approval_gate(channel, amount)

        if requires_approval:
            # Do NOT dispatch yet — action is held pending human sign-off
            dispatch_result = {
                "status": "pending_approval",
                "message_body": None,
                "sent_at": None,
            }
        else:
            dispatch_result = dispatch(
                channel=channel,
                order_id=payment_entity.get("order_id"),
                amount=amount
            )

    event_record = {
        "event_type": event_type,
        "payment_id": payment_entity.get("id"),
        "order_id": payment_entity.get("order_id"),
        "amount": amount,
        "currency": payment_entity.get("currency"),
        "status": payment_entity.get("status"),
        "error_code": payment_entity.get("error_code"),
        "error_description": payment_entity.get("error_description"),
        "method": payment_entity.get("method"),
        "failure_type": failure_type,
        "llm_classified": llm_classified,
        "recovery_channel": channel,
        "recovery_reason": reason,
        "dispatch_status": dispatch_result["status"],
        "dispatch_message": dispatch_result["message_body"],
        "dispatched_at": dispatch_result["sent_at"],
        "requires_approval": requires_approval,
        "approval_status": approval_status,
        "outcome_status": "pending",
        "raw_payload": payload
        
    }

    result = supabase.table("events").insert(event_record).execute()

    print(
        f"Saved event: {event_type} -> failure_type={failure_type}, "
        f"channel={channel}, dispatch={dispatch_result['status']}, "
        f"approval={approval_status}"
    )

    return {"status": "received", "event": event_type}


def handle_payment_captured(event_type: str, payment_entity: dict):
    """Outcome-tracking path: find the matching pending failure for this order_id and mark it recovered."""
    order_id = payment_entity.get("order_id")

    if not order_id:
        print("payment.captured received with no order_id — nothing to match, ignoring")
        return {"status": "ignored", "event": event_type, "reason": "missing order_id"}

    # Find the most recent still-pending failure event for this order
    existing = (
        supabase.table("events")
        .select("id")
        .eq("order_id", order_id)
        .eq("outcome_status", "pending")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    rows = existing.data or []

    if not rows:
        print(f"payment.captured for order_id={order_id} — no matching pending failure event found, ignoring")
        return {"status": "ignored", "event": event_type, "reason": "no matching pending event"}

    matched_id = rows[0]["id"]
    recovered_at = datetime.now(timezone.utc).isoformat()

    supabase.table("events").update({
        "outcome_status": "recovered",
        "recovered_at": recovered_at
    }).eq("id", matched_id).execute()

    print(f"Marked event {matched_id} (order_id={order_id}) as recovered at {recovered_at}")

    return {"status": "recovered", "event": event_type, "event_id": matched_id}


@router.post("/webhook/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None)
):
    body = await request.body()

    if not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing signature header")

    is_valid = verify_signature(
        body=body,
        signature=x_razorpay_signature,
        secret=settings.razorpay_webhook_secret
    )

    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("event")

    payment_entity = (
        payload.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )

    if event_type == "payment.failed":
        return handle_payment_failed(event_type, payment_entity, payload)

    if event_type == "payment.captured":
        return handle_payment_captured(event_type, payment_entity)

    print(f"Ignoring unhandled event_type: {event_type}")
    return {"status": "ignored", "event": event_type}