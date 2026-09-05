from typing import Optional, TypedDict


class RecoveryDecision(TypedDict):
    channel: str
    reason: str


# Order value threshold (in paise) above which we consider "high value"
HIGH_VALUE_THRESHOLD = 100000  # ₹1000


def decide_recovery_action(
    failure_type: Optional[str],
    amount: Optional[int]
) -> RecoveryDecision:
    """
    Deterministic policy: failure_type + amount -> recovery channel.
    Always returns a decision with a human-readable reason,
    even for the 'do nothing yet' case.
    """
    amount = amount or 0

    if failure_type == "card_declined":
        return {
            "channel": "sms",
            "reason": "Card declined — sending SMS with alternate payment link"
        }

    if failure_type == "upi_collect_expired":
        return {
            "channel": "whatsapp",
            "reason": "UPI collect request expired — sending WhatsApp nudge with fresh collect request"
        }

    if failure_type == "bank_timeout":
        return {
            "channel": "auto_retry",
            "reason": "Transient bank/network failure — auto-retry with SMS confirmation, no call needed"
        }

    if failure_type == "flagged_for_review":
        return {
            "channel": "none",
            "reason": "LLM classification failed or ambiguous — flagged for human review"
        }

    if amount >= HIGH_VALUE_THRESHOLD:
        return {
            "channel": "voice_call",
            "reason": f"High-value failure (₹{amount / 100:.2f}) with unclear cause — escalating to Hinglish voice call"
        }

    return {
        "channel": "none",
        "reason": "Failure type unclassified and below high-value threshold — no automated action, flagged for review"
    }