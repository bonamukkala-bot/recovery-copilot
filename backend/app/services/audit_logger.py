from typing import Optional, Dict, Any
from app.services.supabase_client import supabase


def log_decision_event(
    event_id: str,
    stage: str,
    detail: str,
    old_status: Optional[str] = None,
    new_status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Append-only audit trail logging into the decision_log table.
    Wrapped in try/except so audit logging errors never block or crash business logic.
    """
    if not event_id:
        return

    try:
        record = {
            "event_id": event_id,
            "stage": stage,
            "detail": detail,
            "old_status": old_status,
            "new_status": new_status,
            "metadata": metadata or {}
        }
        supabase.table("decision_log").insert(record).execute()
    except Exception as e:
        print(f"[Audit Log Warning] Failed writing to decision_log for event_id={event_id} (stage={stage}): {e}")
