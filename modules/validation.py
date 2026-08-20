"""Centralized validation and normalization for user-provided messages."""

from dataclasses import dataclass
import unicodedata


MIN_MESSAGE_LENGTH = 3
MAX_MESSAGE_LENGTH = 500
LENGTH_WARNING_THRESHOLD = 400


@dataclass(frozen=True)
class ValidationResult:
    """Normalized message and validation metadata."""

    valid: bool
    value: str
    error: str | None = None
    is_length_warning: bool = False


def normalize_user_message(message: str) -> str:
    """Normalize Unicode, remove control characters, and trim whitespace."""
    normalized = unicodedata.normalize("NFC", message)
    normalized = "".join(
        character
        for character in normalized
        if ord(character) >= 32 or character in "\n\t"
    )
    return normalized.strip()


def validate_user_message(message: str) -> ValidationResult:
    """Validate a Telegram text message after command/mention cleanup."""
    normalized = normalize_user_message(message)

    if not normalized:
        return ValidationResult(False, normalized, "empty")
    if len(normalized) < MIN_MESSAGE_LENGTH:
        return ValidationResult(False, normalized, "too_short")
    if len(normalized) > MAX_MESSAGE_LENGTH:
        return ValidationResult(False, normalized, "too_long")

    return ValidationResult(
        True,
        normalized,
        is_length_warning=len(normalized) > LENGTH_WARNING_THRESHOLD,
    )
