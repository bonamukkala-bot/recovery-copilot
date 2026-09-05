from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from typing import Optional
import hmac
import hashlib
import json
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.config import settings
from app.services.supabase_client import supabase
from app.services.classifier import classify_failure, classify_failure_llm
from app.services.decision_engine import decide_recovery_action
from app.services.dispatcher import dispatch
from app.services.hitl_gate import is_suppressed, check_approval_gate
from app.services.audit_logger import log_decision_event

router = APIRouter()


class PaymentEntity(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Razorpay payment ID (e.g. pay_123456)")
    order_id: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = "INR"
    status: Optional[str] = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    method: Optional[str] = None
    contact: Optional[str] = None
    email: Optional[str] = None


class PaymentContainer(BaseModel):
    model_config = ConfigDict(extra="allow")

    entity: PaymentEntity


class WebhookPayloadContainer(BaseModel):
    model_config = ConfigDict(extra="allow")

    payment: PaymentContainer


class RazorpayPaymentWebhook(BaseModel):
    model_config = ConfigDict(extra="allow")

    event: str
    payload: WebhookPayloadContainer


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify Razorpay webhook signature using HMAC-SHA256."""
    expected_signature = hmac.new(
        key=secret.encode(),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)


def process_payment_failed_background(
    event_id: str,
    event_type: str,
    payment_entity: dict,
    payload: dict
):
    """
    Background worker: classify -> decide -> suppression/approval gate -> dispatch -> log.
    Runs asynchronously after the HTTP 200 response is returned to Razorpay.
    """
    payment_id = payment_entity.get("id")

    try:
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
            llm_classified = failure_type is not None and failure_type != "flagged_for_review"
            classify_path = "llm_fallback" if failure_type == "flagged_for_review" else "llm"
        else:
            classify_path = "rule"

        print(f"[CLASSIFY] payment_id={payment_id} path={classify_path} result={failure_type}")
        log_decision_event(
            event_id=event_id,
            stage="classification",
            detail=f"Classified as '{failure_type}' via {classify_path} path",
            metadata={"failure_type": failure_type, "path": classify_path, "llm_classified": llm_classified}
        )

        decision = decide_recovery_action(
            failure_type=failure_type,
            amount=payment_entity.get("amount")
        )

        channel = decision["channel"]
        reason = decision["reason"]
        amount = payment_entity.get("amount")

        print(f"[DECISION] payment_id={payment_id} channel={channel} reason={reason}")

        # Identify the customer for suppression lookup — contact phone first, email fallback
        identifier = payment_entity.get("contact") or payment_entity.get("email")

        # --- Hard opt-out check: overrides everything, no exceptions ---
        if is_suppressed(identifier):
            channel = "none"
            reason = "Customer opted out — contact suppressed, no action taken"
            requires_approval = False
            approval_status = "not_required"
            dispatch_status = "suppressed"
            outcome_status = "suppressed"
        elif failure_type == "flagged_for_review":
            requires_approval = True
            approval_status = "pending"
            dispatch_status = "pending_approval"
            outcome_status = "pending"
        else:
            # --- HITL approval gate ---
            requires_approval, approval_status = check_approval_gate(channel, amount)

            if requires_approval:
                dispatch_status = "pending_approval"
                outcome_status = "pending"
            elif channel == "none":
                dispatch_status = "skipped"
                outcome_status = "pending"
            else:
                dispatch_status = "pending"
                outcome_status = "pending"

        # Update event record with classification, decision, and gate results
        supabase.table("events").update({
            "failure_type": failure_type,
            "llm_classified": llm_classified,
            "recovery_channel": channel,
            "recovery_reason": reason,
            "dispatch_status": dispatch_status,
            "requires_approval": requires_approval,
            "approval_status": approval_status,
            "outcome_status": outcome_status,
        }).eq("id", event_id).execute()

        log_decision_event(
            event_id=event_id,
            stage="decision",
            detail=f"Decided recovery channel '{channel}': {reason}",
            old_status="pending",
            new_status=outcome_status,
            metadata={
                "channel": channel,
                "reason": reason,
                "requires_approval": requires_approval,
                "approval_status": approval_status,
                "dispatch_status": dispatch_status
            }
        )

        # --- Atomic state machine guard before dispatch ---
        if not requires_approval and not is_suppressed(identifier) and channel != "none" and event_id:
            # Atomic transition: pending -> processing ONLY if still pending
            claim_res = (
                supabase.table("events")
                .update({"outcome_status": "processing"})
                .eq("id", event_id)
                .eq("outcome_status", "pending")
                .execute()
            )

            # If zero rows affected, another concurrent worker or process already claimed this event
            if not claim_res.data or len(claim_res.data) == 0:
                print(f"event already being processed, skipping duplicate dispatch for event_id={event_id}")
                return

            log_decision_event(
                event_id=event_id,
                stage="claim",
                detail="Claimed event for processing (atomic race guard passed)",
                old_status="pending",
                new_status="processing"
            )

            try:
                dispatch_result = dispatch(
                    channel=channel,
                    order_id=payment_entity.get("order_id"),
                    amount=amount,
                    contact=identifier,
                    event_id=event_id
                )
                supabase.table("events").update({
                    "outcome_status": "dispatched",
                    "dispatch_status": dispatch_result["status"],
                    "dispatch_message": dispatch_result["message_body"],
                    "dispatched_at": dispatch_result["sent_at"],
                }).eq("id", event_id).execute()
                dispatch_status = dispatch_result["status"]
                dispatch_detail = dispatch_result.get("message_body") or dispatch_status
                print(f"[DISPATCH] event_id={event_id} status={dispatch_status} detail={dispatch_detail}")

                log_decision_event(
                    event_id=event_id,
                    stage="dispatch",
                    detail=f"Dispatch outcome: {dispatch_status} — {dispatch_detail}",
                    old_status="processing",
                    new_status="dispatched",
                    metadata={
                        "dispatch_status": dispatch_status,
                        "provider_ref": dispatch_result.get("provider_ref"),
                        "channel": channel
                    }
                )
            except Exception as e:
                supabase.table("events").update({
                    "outcome_status": "failed",
                    "dispatch_status": "failed",
                }).eq("id", event_id).execute()
                print(f"[DISPATCH] event_id={event_id} status=failed detail={e}")
                log_decision_event(
                    event_id=event_id,
                    stage="dispatch",
                    detail=f"Dispatch error: {e}",
                    old_status="processing",
                    new_status="failed",
                    metadata={"error": str(e)}
                )
                raise

        print(
            f"Saved event: {event_type} -> failure_type={failure_type}, "
            f"channel={channel}, dispatch={dispatch_status}, "
            f"approval={approval_status}"
        )

    except Exception as e:
        print(f"[BACKGROUND TASK ERROR] Failed processing event_id={event_id}: {e}")
        if event_id:
            try:
                supabase.table("events").update({
                    "outcome_status": "failed",
                    "dispatch_status": "failed",
                }).eq("id", event_id).execute()
                log_decision_event(
                    event_id=event_id,
                    stage="error",
                    detail=f"Unhandled background processing error: {e}",
                    new_status="failed",
                    metadata={"error": str(e)}
                )
            except Exception as update_err:
                print(f"[BACKGROUND TASK ERROR] Failed updating status to failed for event_id={event_id}: {update_err}")


def handle_payment_failed(
    event_type: str,
    payment_entity: dict,
    payload: dict,
    background_tasks: BackgroundTasks
):
    """
    Synchronous ingress for payment.failed:
    1. Check idempotency.
    2. Synchronously insert initial row with outcome_status='pending'.
    3. Schedule background worker for classify -> decide -> dispatch.
    4. Return HTTP response immediately.
    """
    payment_id = payment_entity.get("id")

    # --- Idempotency check: prevent duplicate event ingestion & dispatches ---
    if payment_id:
        existing = (
            supabase.table("events")
            .select("id")
            .eq("payment_id", payment_id)
            .eq("event_type", event_type)
            .limit(1)
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            print(f"duplicate webhook ignored for payment_id={payment_id}, event_type={event_type}")
            return {"status": "ignored", "event": event_type, "reason": "duplicate webhook"}

    amount = payment_entity.get("amount")

    # Insert raw event record synchronously so row exists immediately
    event_record = {
        "event_type": event_type,
        "payment_id": payment_id,
        "order_id": payment_entity.get("order_id"),
        "amount": amount,
        "currency": payment_entity.get("currency"),
        "status": payment_entity.get("status"),
        "error_code": payment_entity.get("error_code"),
        "error_description": payment_entity.get("error_description"),
        "method": payment_entity.get("method"),
        "failure_type": None,
        "llm_classified": False,
        "recovery_channel": None,
        "recovery_reason": None,
        "dispatch_status": "pending",
        "dispatch_message": None,
        "dispatched_at": None,
        "requires_approval": False,
        "approval_status": "not_required",
        "outcome_status": "pending",
        "raw_payload": payload
    }

    try:
        insert_res = supabase.table("events").insert(event_record).execute()
    except Exception as e:
        error_msg = str(e).lower()
        if "duplicate" in error_msg or "unique" in error_msg or "23505" in error_msg:
            print(f"duplicate webhook ignored (DB constraint) for payment_id={payment_id}, event_type={event_type}")
            return {"status": "ignored", "event": event_type, "reason": "duplicate webhook"}
        raise

    event_id = insert_res.data[0]["id"] if insert_res.data else None

    # Append audit trail for raw ingestion
    log_decision_event(
        event_id=event_id,
        stage="ingestion",
        detail=f"Webhook {event_type} received for payment_id={payment_id}",
        old_status=None,
        new_status="pending",
        metadata={"payment_id": payment_id, "amount": amount, "method": payment_entity.get("method")}
    )

    # Schedule background processing task
    background_tasks.add_task(
        process_payment_failed_background,
        event_id=event_id,
        event_type=event_type,
        payment_entity=payment_entity,
        payload=payload
    )

    return {"status": "received", "event": event_type, "event_id": event_id}


def handle_payment_captured(
    event_type: str,
    payment_entity: dict,
    background_tasks: BackgroundTasks
):
    """
    Outcome-tracking path for payment.captured:
    Schedules matching & updating the active failure event in the background.
    """
    order_id = payment_entity.get("order_id")

    if not order_id:
        print("payment.captured received with no order_id — nothing to match, ignoring")
        return {"status": "ignored", "event": event_type, "reason": "missing order_id"}

    def _process_captured():
        try:
            # Find the most recent still-active failure event for this order (pending, processing, or dispatched)
            existing = (
                supabase.table("events")
                .select("id")
                .eq("order_id", order_id)
                .in_("outcome_status", ["pending", "processing", "dispatched"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            rows = existing.data or []

            if not rows:
                print(f"payment.captured for order_id={order_id} — no matching pending failure event found, ignoring")
            else:
                matched_id = rows[0]["id"]
                recovered_at = datetime.now(timezone.utc).isoformat()

                supabase.table("events").update({
                    "outcome_status": "recovered",
                    "recovered_at": recovered_at
                }).eq("id", matched_id).execute()

                print(f"Marked event {matched_id} (order_id={order_id}) as recovered at {recovered_at}")
                log_decision_event(
                    event_id=matched_id,
                    stage="recovery",
                    detail=f"Payment captured for order_id={order_id}, failure resolved",
                    new_status="recovered",
                    metadata={"order_id": order_id, "recovered_at": recovered_at}
                )

            # Look up and resolve any pending promise for this order_id (Step 15)
            try:
                from app.services.promise_tracker import resolve_promise_on_capture
                resolve_promise_on_capture(order_id=order_id)
            except Exception as pe:
                print(f"[Promise Tracker Warning] Failed resolving promise for order_id={order_id}: {pe}")
        except Exception as e:
            print(f"[BACKGROUND TASK ERROR] Failed handling payment.captured for order_id={order_id}: {e}")

    background_tasks.add_task(_process_captured)
    return {"status": "received", "event": event_type, "order_id": order_id}


@router.post("/webhook/razorpay")
async def razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
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

    try:
        raw_json = json.loads(body)
    except Exception as e:
        print(f"[WEBHOOK VALIDATION ERROR] Invalid JSON body: {e}")
        raise HTTPException(status_code=422, detail=f"Invalid JSON payload: {e}")

    if not isinstance(raw_json, dict) or "event" not in raw_json:
        print("[WEBHOOK VALIDATION ERROR] Payload must be a JSON object containing an 'event' field")
        raise HTTPException(status_code=422, detail="Missing 'event' field in webhook payload")

    event_type = raw_json.get("event")

    if event_type in ("payment.failed", "payment.captured"):
        try:
            validated_event = RazorpayPaymentWebhook.model_validate(raw_json)
        except ValidationError as e:
            print(f"[WEBHOOK VALIDATION ERROR] event={event_type} schema validation failed: {e}")
            raise HTTPException(
                status_code=422,
                detail={"error": "Webhook payload validation failed", "details": e.errors(include_url=False)}
            )

        payment_entity = validated_event.payload.payment.entity.model_dump()

        if event_type == "payment.failed":
            return handle_payment_failed(event_type, payment_entity, raw_json, background_tasks)

        if event_type == "payment.captured":
            return handle_payment_captured(event_type, payment_entity, background_tasks)

    print(f"Ignoring unhandled event_type: {event_type}")
    return {"status": "ignored", "event": event_type}