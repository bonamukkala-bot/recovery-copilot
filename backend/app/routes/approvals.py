from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.supabase_client import supabase
from app.services.dispatcher import dispatch
from app.services.hitl_gate import suppress_customer

router = APIRouter()


@router.post("/events/{event_id}/approve")
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

    dispatch_result = dispatch(
        channel=event["recovery_channel"],
        order_id=event["order_id"],
        amount=event["amount"]
    )

    update = {
        "approval_status": "approved",
        "dispatch_status": dispatch_result["status"],
        "dispatch_message": dispatch_result["message_body"],
        "dispatched_at": dispatch_result["sent_at"],
    }

    supabase.table("events").update(update).eq("id", event_id).execute()

    return {"status": "approved", "event_id": event_id, "dispatch": dispatch_result}


@router.post("/events/{event_id}/reject")
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

    return {"status": "rejected", "event_id": event_id}


class OptOutRequest(BaseModel):
    identifier: str
    reason: str = "Customer requested no further contact"


@router.post("/opt-out")
async def opt_out(request: OptOutRequest):
    """Permanently suppress a customer identifier. No override — matches PRD's hard opt-out rule."""
    suppress_customer(identifier=request.identifier, reason=request.reason)
    return {"status": "suppressed", "identifier": request.identifier}