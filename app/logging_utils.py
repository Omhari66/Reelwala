"""Logging utilities for privacy compliance and phone masking."""

import logging
import re

PHONE_REGEX = re.compile(r"(\+?\d{1,4})?(\d{3,10})(\d{4})\b")
API_KEY_REGEX = re.compile(r"(AIza[0-9A-Za-z\-_]{35}|(?:sk-[A-Za-z0-9]{20,}))")


def mask_phone(phone: str | None) -> str:
    """Mask phone number keeping country code and last 4 digits (e.g. +91******3210)."""
    if not phone:
        return ""
    clean = phone.strip()
    if len(clean) <= 4:
        return "*" * len(clean)

    # If starts with +, keep + and country code digits (1-3)
    if clean.startswith("+"):
        prefix = clean[:3]
        suffix = clean[-4:]
        stars = "*" * (len(clean) - len(prefix) - len(suffix))
        return f"{prefix}{stars}{suffix}"

    suffix = clean[-4:]
    stars = "*" * (len(clean) - len(suffix))
    return f"{stars}{suffix}"


def mask_sensitive_text(text: str) -> str:
    """Mask any phone numbers and API keys in freeform log text."""
    # Mask API keys first
    masked = API_KEY_REGEX.sub("[REDACTED_KEY]", text)

    # Mask phone numbers
    def _sub_phone(match: re.Match) -> str:
        prefix = match.group(1) or ""
        mid = match.group(2)
        suffix = match.group(3)
        return f"{prefix}{'*' * len(mid)}{suffix}"

    return PHONE_REGEX.sub(_sub_phone, masked)


class SensitiveDataFilter(logging.Filter):
    """Logging filter that masks phone numbers and API keys from all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_sensitive_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (mask_sensitive_text(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    mask_sensitive_text(a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True

