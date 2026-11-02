"""Intent detection for conversation commands and messages."""

import re

CONFIRMATION_WORDS = {
    "ok",
    "okay",
    "yes",
    "haan",
    "ha",
    "approve",
    "done",
    "theek hai",
    "theek",
    "👍",
    "sahi hai",
    "y",
}

CANCEL_WORDS = {
    "cancel",
    "band karo",
    "rehne do",
    "stop",
}

COMMANDS = {
    "help",
    "menu",
    "status",
    "cancel",
    "restart",
}


def normalize_text(text: str) -> str:
    """Normalize input text by lowercasing and stripping whitespace and punctuation."""
    cleaned = text.strip().lower()
    return re.sub(r"[^\w\s\u0900-\u097F👍]", "", cleaned)


def is_confirmation(text: str) -> bool:
    """Check if the text represents an affirmative confirmation."""
    norm = normalize_text(text)
    if norm in CONFIRMATION_WORDS:
        return True
    return any(w in norm.split() for w in ["yes", "ok", "okay", "haan", "approve", "done", "👍"])


def is_cancellation(text: str) -> bool:
    """Check if the text represents a cancellation."""
    norm = normalize_text(text)
    if norm in CANCEL_WORDS:
        return True
    return any(w in norm.split() for w in ["cancel", "stop"])


def detect_command(text: str) -> str | None:
    """Detect if input matches a global command."""
    norm = normalize_text(text)
    tokens = norm.split()
    if not tokens:
        return None
    # Exact or first token match if single command
    first = tokens[0]
    if first in COMMANDS:
        return first
    if norm in COMMANDS:
        return norm
    return None
