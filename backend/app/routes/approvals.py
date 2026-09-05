from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.services.supabase_client import supabase
from app.services.dispatcher import dispatch
from app.services.hitl_gate import suppress_customer
from app.services.audit_logger import log_decision_event
from app.utils.auth import verify_admin_api_key

router = APIRouter()


@router.post("/events/{event_id}/approve", dependencies=[Depends(verify_admin_api_key)])
async def approve_event(event_id: str):
    """Human approves a pending high-value action — dispatch fires now."""
    result = supabase.table("events").select("*").eq("id", event_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    event = result.data[0]

    if event["approval_status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Event is not pending approval (current status: {event['approval_status']})"
        )

    # --- Atomic state machine guard before dispatch ---
    claim_res = (
        supabase.table("events")
        .update({"outcome_status": "processing"})
        .eq("id", event_id)
        .eq("outcome_status", "pending")
        .execute()
    )

    if not claim_res.data or len(claim_res.data) == 0:
        return {
            "status": "ignored",
            "event_id": event_id,
            "reason": "Event is already being processed or was already resolved"
        }

    log_decision_event(
        event_id=event_id,
        stage="claim",
        detail="Operator claimed pending event for approval dispatch",
        old_status="pending",
        new_status="processing"
    )

    raw = event.get("raw_payload") or {}
    payment_entity = (
        raw.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )
    contact = payment_entity.get("contact") or payment_entity.get("email")

    try:
        dispatch_result = dispatch(
            channel=event["recovery_channel"],
            order_id=event["order_id"],
            amount=event["amount"],
            contact=contact,
            event_id=event_id
        )

        update = {
            "approval_status": "approved",
            "outcome_status": "dispatched",
            "dispatch_status": dispatch_result["status"],
            "dispatch_message": dispatch_result["message_body"],
            "dispatched_at": dispatch_result["sent_at"],
        }

        supabase.table("events").update(update).eq("id", event_id).execute()
        dispatch_detail = dispatch_result.get("message_body") or dispatch_result["status"]
        print(f"[DISPATCH] event_id={event_id} status={dispatch_result['status']} detail={dispatch_detail}")

        log_decision_event(
            event_id=event_id,
            stage="approval",
            detail=f"Operator approved event. Dispatch outcome: {dispatch_result['status']} — {dispatch_detail}",
            old_status="processing",
            new_status="dispatched",
            metadata={
                "dispatch_status": dispatch_result["status"],
                "provider_ref": dispatch_result.get("provider_ref"),
                "channel": event["recovery_channel"]
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
            stage="approval",
            detail=f"Operator approved event, but dispatch failed: {e}",
            old_status="processing",
            new_status="failed",
            metadata={"error": str(e)}
        )
        raise

    return {"status": "approved", "event_id": event_id, "dispatch": dispatch_result}


@router.post("/events/{event_id}/reject", dependencies=[Depends(verify_admin_api_key)])
async def reject_event(event_id: str):
    """Human rejects a pending action — no dispatch happens, ever."""
    result = supabase.table("events").select("*").eq("id", event_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")

    event = result.data[0]

    if event["approval_status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Event is not pending approval (current status: {event['approval_status']})"
        )

    supabase.table("events").update({
        "approval_status": "rejected",
        "dispatch_status": "rejected",
    }).eq("id", event_id).execute()

    log_decision_event(
        event_id=event_id,
        stage="rejection",
        detail="Operator rejected pending action — dispatch permanently prevented",
        old_status="pending",
        new_status="rejected"
    )

    return {"status": "rejected", "event_id": event_id}


class OptOutRequest(BaseModel):
    identifier: str
    reason: str = "Customer requested no further contact"


@router.post("/opt-out")
async def opt_out(request: OptOutRequest):
    """Permanently suppress a customer identifier. No override — matches PRD's hard opt-out rule."""
    suppress_customer(identifier=request.identifier, reason=request.reason)
    return {"status": "suppressed", "identifier": request.identifier}