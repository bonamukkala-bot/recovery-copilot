import pytest
from app.services.decision_engine import decide_recovery_action, HIGH_VALUE_THRESHOLD


def test_card_declined_routes_to_sms():
    decision = decide_recovery_action(failure_type="card_declined", amount=25000)
    assert decision["channel"] == "sms"
    assert "Card declined" in decision["reason"]
    assert "alternate payment link" in decision["reason"]


def test_upi_collect_expired_routes_to_whatsapp():
    decision = decide_recovery_action(failure_type="upi_collect_expired", amount=50000)
    assert decision["channel"] == "whatsapp"
    assert "UPI collect request expired" in decision["reason"]
    assert "WhatsApp nudge" in decision["reason"]


def test_bank_timeout_routes_to_auto_retry():
    decision = decide_recovery_action(failure_type="bank_timeout", amount=75000)
    assert decision["channel"] == "auto_retry"
    assert "auto-retry" in decision["reason"]
    assert "Transient bank/network failure" in decision["reason"]


def test_flagged_for_review_routes_to_none():
    decision = decide_recovery_action(failure_type="flagged_for_review", amount=50000)
    assert decision["channel"] == "none"
    assert "flagged for human review" in decision["reason"]


def test_high_value_unclear_cause_escalates_to_voice_call():
    # HIGH_VALUE_THRESHOLD is 100000 paise (₹1000)
    amount = 150000  # ₹1500
    decision = decide_recovery_action(failure_type=None, amount=amount)
    assert decision["channel"] == "voice_call"
    assert "High-value failure" in decision["reason"]
    assert "Hinglish voice call" in decision["reason"]


def test_exact_high_value_threshold_escalates_to_voice_call():
    decision = decide_recovery_action(failure_type=None, amount=HIGH_VALUE_THRESHOLD)
    assert decision["channel"] == "voice_call"
    assert "High-value failure" in decision["reason"]


def test_low_value_unclear_cause_routes_to_none():
    amount = 50000  # ₹500 (< ₹1000)
    decision = decide_recovery_action(failure_type=None, amount=amount)
    assert decision["channel"] == "none"
    assert "below high-value threshold" in decision["reason"]


def test_none_amount_and_none_failure_type_routes_to_none():
    decision = decide_recovery_action(failure_type=None, amount=None)
    assert decision["channel"] == "none"
    assert "below high-value threshold" in decision["reason"]
