from typing import Optional
from app.services.supabase_client import supabase

# Actions above this amount (in paise) require human approval before dispatch
APPROVAL_THRESHOLD = 200000  # ₹2000


def is_suppressed(identifier: Optional[str]) -> bool:
    """Check if a customer/order identifier has opted out permanently."""
    if not identifier:
        return False

    result = (
        supabase.table("suppressed_customers")
        .select("id")
        .eq("identifier", identifier)
        .execute()
    )
    return len(result.data) > 0


def suppress_customer(identifier: str, reason: str = "Customer requested no further contact"):
    """Permanently suppress a customer — no override allowed."""
    supabase.table("suppressed_customers").insert({
        "identifier": identifier,
        "reason": reason
    }).execute()


def check_approval_gate(channel: str, amount: Optional[int]) -> tuple[bool, str]:
    """
    Returns (requires_approval, approval_status).
    High-value voice calls and any action above threshold need human sign-off.
    """
    amount = amount or 0

    if channel == "none":
        return False, "not_required"

    if amount >= APPROVAL_THRESHOLD:
        return True, "pending"

    return False, "not_required"