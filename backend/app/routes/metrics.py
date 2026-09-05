from fastapi import APIRouter
from datetime import datetime
from app.services.supabase_client import supabase

router = APIRouter()

# Estimated per-action cost in INR — placeholders until real provider billing is wired in.
# Labeled clearly as estimated wherever surfaced to avoid implying real spend data.
ESTIMATED_COST_INR = {
    "sms": 0.20,
    "whatsapp": 0.50,
    "voice_call": 2.00,   # per minute, treated as a flat per-call estimate for now
    "auto_retry": 0.0,
    "none": 0.0,
}


@router.get("/metrics")
async def get_metrics():
    # Sweep expired pending promises to 'missed' status
    try:
        from app.services.promise_tracker import check_and_expire_promises
        check_and_expire_promises()
    except Exception as e:
        print(f"[Promise Tracker Sweep Warning] {e}")

    result = supabase.table("events").select(
        "id, recovery_channel, dispatch_status, outcome_status, created_at, recovered_at, llm_classified, failure_type"
    ).execute()

    events = result.data or []

    total_failures = len(events)

    # An action only "counts" as attempted contact if it was actually dispatched (not suppressed/pending/rejected)
    actioned_events = [e for e in events if e.get("dispatch_status") == "sent"]
    total_actioned = len(actioned_events)

    recovered_events = [e for e in events if e.get("outcome_status") == "recovered"]
    total_recovered = len(recovered_events)

    # --- Recovery rate ---
    recovery_rate = (total_recovered / total_failures * 100) if total_failures else 0.0

    # --- Contact rate: dispatched actions as a share of all failures ---
    contact_rate = (total_actioned / total_failures * 100) if total_failures else 0.0

    # --- Groq LLM fallback rate: share of processed events taking LLM path (success or flagged fallback) ---
    llm_events = [
        e for e in events
        if e.get("llm_classified") is True or e.get("failure_type") == "flagged_for_review"
    ]
    total_llm_classified = len(llm_events)
    llm_fallback_rate = (total_llm_classified / total_failures * 100) if total_failures else 0.0

    # --- Time-to-recovery: average minutes between created_at and recovered_at, recovered events only ---
    durations_minutes = []
    for e in recovered_events:
        created_at = e.get("created_at")
        recovered_at = e.get("recovered_at")
        if not created_at or not recovered_at:
            continue
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            recovered_dt = datetime.fromisoformat(recovered_at.replace("Z", "+00:00"))
            delta_minutes = (recovered_dt - created_dt).total_seconds() / 60
            durations_minutes.append(delta_minutes)
        except (ValueError, TypeError):
            continue

    avg_time_to_recovery_minutes = (
        sum(durations_minutes) / len(durations_minutes) if durations_minutes else None
    )

    # --- Cost-per-recovery: sum estimated cost of every dispatched action, divided by recovered count ---
    total_estimated_cost = sum(
        ESTIMATED_COST_INR.get(e.get("recovery_channel"), 0.0) for e in actioned_events
    )
    cost_per_recovery = (
        total_estimated_cost / total_recovered if total_recovered else None
    )

    return {
        "total_failures": total_failures,
        "total_actioned": total_actioned,
        "total_recovered": total_recovered,
        "total_llm_classified": total_llm_classified,
        "llm_fallback_rate_percent": round(llm_fallback_rate, 1),
        "recovery_rate_percent": round(recovery_rate, 1),
        "contact_rate_percent": round(contact_rate, 1),
        "avg_time_to_recovery_minutes": (
            round(avg_time_to_recovery_minutes, 1) if avg_time_to_recovery_minutes is not None else None
        ),
        "cost_per_recovery_inr": (
            round(cost_per_recovery, 2) if cost_per_recovery is not None else None
        ),
        "cost_basis": "estimated — simulated dispatcher, placeholder per-channel rates, not real provider billing",
    }