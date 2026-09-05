import pytest
from app.services.classifier import classify_failure


def test_card_declined_via_keyword_insufficient_funds():
    result = classify_failure(
        error_code="BAD_REQUEST_ERROR",
        error_description="Payment failed due to insufficient funds",
        method="card"
    )
    assert result == "card_declined"


def test_card_declined_via_keyword_declined_by_bank():
    result = classify_failure(
        error_code="BAD_REQUEST_ERROR",
        error_description="Card declined by bank — risk rule triggered",
        method="card"
    )
    assert result == "card_declined"


def test_card_declined_via_bad_request_error_code():
    result = classify_failure(
        error_code="BAD_REQUEST_ERROR",
        error_description=None,
        method="card"
    )
    assert result == "card_declined"


def test_bank_timeout_via_keyword_timeout():
    result = classify_failure(
        error_code="SERVER_ERROR",
        error_description="Payment failed due to a network timeout",
        method="netbanking"
    )
    assert result == "bank_timeout"


def test_bank_timeout_via_keyword_network():
    result = classify_failure(
        error_code=None,
        error_description="Network connectivity issue",
        method="card"
    )
    assert result == "bank_timeout"


def test_bank_timeout_via_gateway_error_code():
    result = classify_failure(
        error_code="GATEWAY_ERROR",
        error_description="Something went wrong",
        method="netbanking"
    )
    assert result == "bank_timeout"


def test_bank_timeout_via_server_error_code():
    result = classify_failure(
        error_code="SERVER_ERROR",
        error_description=None,
        method=None
    )
    assert result == "bank_timeout"


def test_bank_timeout_via_system_error_code():
    result = classify_failure(
        error_code="SYSTEM_ERROR",
        error_description=None,
        method=None
    )
    assert result == "bank_timeout"


def test_upi_collect_expired_via_keyword():
    result = classify_failure(
        error_code="GATEWAY_ERROR",
        error_description="UPI collect request expired before approval",
        method="upi"
    )
    assert result == "upi_collect_expired"


def test_upi_collect_expired_via_method_fallback():
    result = classify_failure(
        error_code=None,
        error_description="Payment authorization failed",
        method="upi"
    )
    assert result == "upi_collect_expired"


def test_unclassified_returns_none_for_llm_fallback():
    result = classify_failure(
        error_code="UNKNOWN_ERROR",
        error_description="Custom user cancellation at redirect page",
        method="netbanking"
    )
    assert result is None


def test_empty_inputs_returns_none():
    result = classify_failure(
        error_code=None,
        error_description=None,
        method=None
    )
    assert result is None
