"""Redaction of anything resembling an API key or account id, applied to every view."""

import re

from happy_toad.agent.transcript import redact as redact_account_ids

KEY_LIKE = re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_-]{16,}|\bBearer\s+[A-Za-z0-9._-]{16,}")


def redact_text(text: str) -> str:
    return KEY_LIKE.sub("[redacted]", redact_account_ids(text))


def redact_all(value):
    """The same structure with every string redacted."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {redact_text(k): redact_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_all(v) for v in value]
    return value
