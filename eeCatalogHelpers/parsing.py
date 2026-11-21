"""Header, integer, and color parsing helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .text import normalize_for_matching

__all__ = ["choose_preferred_column", "value_to_int", "color_from_row"]

_RGB_COLUMN_ALIASES = (("R", "RED"), ("G", "GREEN"), ("B", "BLUE"))



def choose_preferred_column(
    header: Sequence[str], preferred_candidates: Sequence[str]
) -> str | None:
    """Return the first preferred candidate present in a header list."""
    header_lookup = {column.upper(): column for column in header}
    for candidate in preferred_candidates:
        if candidate.upper() in header_lookup:
            return header_lookup[candidate.upper()]
    return None


def value_to_int(value: Any) -> int | None:
    """Convert text-like numeric values into ints, returning None when unavailable."""
    text = normalize_for_matching(None if value is None else str(value))
    if not text:
        return None
    try:
        return int(float(text))
    except (ValueError, OverflowError):
        return None


def color_from_row(row: Mapping[str, Any]) -> str:
    """Parse '#RRGGBB' or RGB triplets from a row and return uppercase hex."""
    hex_value = normalize_for_matching(None if row.get("HEX") is None else str(row.get("HEX")))
    if hex_value:
        color = hex_value.lstrip("#").upper()
        if re.fullmatch(r"[0-9A-F]{6}", color):
            return f"#{color}"

    channels: list[int] = []
    for aliases in _RGB_COLUMN_ALIASES:
        raw_value = next((row.get(alias) for alias in aliases if row.get(alias) is not None), None)
        if raw_value is None:
            raise ValueError("Could not determine color from source CSV row.")
        try:
            channel = int(float(str(raw_value)))
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid RGB color value: {raw_value!r}") from exc
        channels.append(channel)

    if not all(0 <= component <= 255 for component in channels):
        raise ValueError(f"RGB color out of range: {tuple(channels)}")

    r, g, b = channels
    return f"#{r:02X}{g:02X}{b:02X}"
