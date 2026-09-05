from datetime import datetime, timezone, timedelta
from typing import Optional
from app.config import settings
from app.services.supabase_client import supabase


def create_promise(
    order_id: Optional[str],
    amount: Optional[int],
    event_id: Optional[str] = None,
    phone: Optional[str] = None,
    window_hours: Optional[int] = None
) -> Optional[dict]:
    """
    Creates a new promise record with status='pending' after a successful dispatch.
    promised_by is set to (now + window_hours) where window_hours defaults to PROMISE_WINDOW_HOURS.
    """
    if not order_id:
        return None

    hours = window_hours or getattr(settings, "promise_window_hours", 24)
    now = datetime.now(timezone.utc)
    promised_by = now + timedelta(hours=hours)

    promise_payload = {
        "event_id": event_id,
        "order_id": order_id,
        "phone": phone,
        "promised_amount": amount,
        "promised_by": promised_by.isoformat(),
        "created_at": now.isoformat(),
        "status": "pending",
        "resolved_at": None,
    }

    try:
        res = supabase.table("promises").insert(promise_payload).execute()
        data = res.data[0] if res.data else None
        print(f"[Promise Tracker] Created pending promise for order_id={order_id}, promised_by={promised_by.isoformat()}")
        return data
    except Exception as e:
        print(f"[Promise Tracker Warning] Failed creating promise for order_id={order_id}: {e}")
        return None


def resolve_promise_on_capture(order_id: str) -> Optional[dict]:
    """
    Called when payment.captured arrives:
    Looks up any pending promise for that order_id.
    If found and arrived before promised_by, marks status='kept', resolved_at=now.
    """
    if not order_id:
        return None

    try:
        res = (
            supabase.table("promises")
            .select("*")
            .eq("order_id", order_id)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None

        promise = rows[0]
        promised_by_str = promise.get("promised_by")
        now = datetime.now(timezone.utc)

        is_kept = True
        if promised_by_str:
            try:
                promised_by_dt = datetime.fromisoformat(promised_by_str.replace("Z", "+00:00"))
                is_kept = now <= promised_by_dt
            except Exception:
                is_kept = True

        if is_kept:
            resolved_at = now.isoformat()
            update_res = (
                supabase.table("promises")
                .update({
                    "status": "kept",
                    "resolved_at": resolved_at
                })
                .eq("id", promise["id"])
                .execute()
            )
            print(f"[Promise Tracker] Marked promise {promise['id']} for order_id={order_id} as 'kept' at {resolved_at}")
            return update_res.data[0] if update_res.data else promise
        else:
            # Payment arrived after the promised_by deadline window
            resolved_at = now.isoformat()
            update_res = (
                supabase.table("promises")
                .update({
                    "status": "missed",
                    "resolved_at": resolved_at
                })
                .eq("id", promise["id"])
                .execute()
            )
            print(f"[Promise Tracker] Payment for order_id={order_id} arrived after promised_by deadline — marked 'missed'")
            return update_res.data[0] if update_res.data else promise

    except Exception as e:
        print(f"[Promise Tracker Warning] Failed resolving promise for order_id={order_id}: {e}")
        return None


def check_and_expire_promises() -> int:
    """
    Sweeps for any pending promises whose promised_by deadline has passed without payment,
    updating status to 'missed'.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        res = (
            supabase.table("promises")
            .select("id, order_id")
            .eq("status", "pending")
            .lt("promised_by", now_iso)
            .execute()
        )
        expired_rows = res.data or []
        if not expired_rows:
            return 0

        for row in expired_rows:
            supabase.table("promises").update({
                "status": "missed",
                "resolved_at": now_iso
            }).eq("id", row["id"]).execute()

        print(f"[Promise Tracker] Marked {len(expired_rows)} expired promises as 'missed'")
        return len(expired_rows)
    except Exception as e:
        print(f"[Promise Tracker Warning] Failed expiring promises: {e}")
        return 0
