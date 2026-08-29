from typing import Optional
from groq import Groq
from app.config import settings

# Maps Razorpay error_code -> our internal failure_type
RULE_BASED_MAPPING = {
    "BAD_REQUEST_ERROR": "card_declined",
    "GATEWAY_ERROR": "bank_timeout",
    "SERVER_ERROR": "bank_timeout",
    "SYSTEM_ERROR": "bank_timeout",
}

# Error descriptions that hint at specific failure types,
# used when error_code alone isn't specific enough
DESCRIPTION_KEYWORDS = {
    "insufficient funds": "card_declined",
    "expired": "upi_collect_expired",
    "timeout": "bank_timeout",
    "declined by bank": "card_declined",
    "network": "bank_timeout",
}

# The only failure types our decision engine actually knows how to act on
VALID_FAILURE_TYPES = {
    "card_declined",
    "upi_collect_expired",
    "bank_timeout",
    "checkout_abandonment",
}

_groq_client: Optional[Groq] = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


def classify_failure(
    error_code: Optional[str],
    error_description: Optional[str],
    method: Optional[str]
) -> Optional[str]:
    """
    Rule-based classification. Returns a failure_type string,
    or None if no rule matches (meaning: fall through to LLM).
    """
    description_lower = (error_description or "").lower()

    for keyword, failure_type in DESCRIPTION_KEYWORDS.items():
        if keyword in description_lower:
            return failure_type

    if error_code and error_code in RULE_BASED_MAPPING:
        return RULE_BASED_MAPPING[error_code]

    if method == "upi":
        return "upi_collect_expired"

    return None

def classify_failure_llm(
    error_code: Optional[str],
    error_description: Optional[str],
    method: Optional[str]
) -> Optional[str]:
    """
    LLM fallback classification — only called when rule-based classification
    returns None. Uses Groq's Llama 3.3 70B per the PRD's stated stack.
    Returns None (not a guess) if the LLM also can't confidently classify.
    """
    print(f"DEBUG - groq_api_key loaded: '{settings.groq_api_key[:10]}...' (length: {len(settings.groq_api_key)})")

    if not settings.groq_api_key:
        return None


    prompt = f"""You are classifying a failed Razorpay payment into exactly one category.

Categories (respond with ONLY the exact category name, nothing else):
- card_declined
- upi_collect_expired
- bank_timeout
- checkout_abandonment
- unknown (use this if none of the above genuinely fit)

Payment failure details:
- error_code: {error_code or "not provided"}
- error_description: {error_description or "not provided"}
- payment_method: {method or "not provided"}

Respond with only the category name."""

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=200,
            reasoning_effort="low",
        )
        result = response.choices[0].message.content.strip().lower()
        print(f"DEBUG - LLM raw response: '{result}'")

        if result in VALID_FAILURE_TYPES:
            return result
        return None

    except Exception as e:
        print(f"LLM classification failed: {e}")
        return None