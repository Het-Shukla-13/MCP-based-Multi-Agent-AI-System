"""Mask personal data before anything is stored in metrics/traces."""

import re
from typing import Any

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
MAX_VALUE_CHARS = 120
DROP_KEYS = {"user_id", "conversation_id", "token", "access_token", "refresh_token", "password"}


def redact_text(value: str) -> str:
    value = EMAIL.sub("[email]", value)
    value = PHONE.sub("[phone]", value)
    return value if len(value) <= MAX_VALUE_CHARS else value[:MAX_VALUE_CHARS] + "…"


def redact_args(args: Any) -> Any:
    """Recursively mask strings, drop identity/secret keys, keep structure for debugging."""
    if isinstance(args, dict):
        return {k: redact_args(v) for k, v in args.items() if k not in DROP_KEYS}
    if isinstance(args, list):
        return [redact_args(v) for v in args[:20]]
    if isinstance(args, str):
        return redact_text(args)
    return args
