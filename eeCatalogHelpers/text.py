"""Text normalization helpers."""

from __future__ import annotations

import re

__all__ = ["clean_text", "normalize_for_matching"]

_DEFAULT_NULL_TOKENS = {"NA", "N/A", "NONE", "NULL", ""}



def clean_text(value: str | None) -> str:
    """Normalize BOM/whitespace and return an empty string for nulls."""
    if value is None:
        return ""
    text = value.replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_matching(value: str | None, null_tokens: set[str] | None = None) -> str:
    """Normalize text and collapse common null-like tokens to empty strings."""
    tokens = _DEFAULT_NULL_TOKENS if null_tokens is None else null_tokens
    normalized_tokens = {token.upper() for token in tokens}
    text = clean_text(value)
    if text.upper() in normalized_tokens:
        return ""
    return text
