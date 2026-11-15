"""Patterns for API keys and account ids, and the redaction of error text (SPEC, M4 part A)."""

import re

ACCOUNT_ID = re.compile(r"\buser_[A-Za-z0-9]{16,}\b")  # not the key "user_id"
KEY_LIKE = re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_-]{16,}|\bBearer\s+[A-Za-z0-9._-]{16,}")
ERROR_LIMIT = 500  # characters of an error kept in transcripts and bake-off JSON


def redact_error(text: str) -> str:
    """Keys and account ids replaced, then cut to ERROR_LIMIT characters."""
    return KEY_LIKE.sub("[redacted]", ACCOUNT_ID.sub("[redacted]", text))[:ERROR_LIMIT]
