"""Image property and nodata resolution helpers."""

from __future__ import annotations

from typing import Any

__all__ = [
    "coerce_nodata_value",
    "resolve_lookup_value",
    "resolve_property_value",
    "build_image_properties",
]

_LOOKUP_VALUE_ALIASES = {
    "name": ("name", "version_name"),
    "version": ("version", "version_decimal"),
    "number": ("number", "version_integer"),
}



def coerce_nodata_value(value: Any) -> Any:
    """Normalize nodata values to native numeric types where possible."""
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        value = stripped

    if isinstance(value, float) and value.is_integer():
        return int(value)

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return value

    if numeric_value.is_integer():
        return int(numeric_value)
    return numeric_value


def resolve_lookup_value(record: dict[str, Any], value_key: str, default: Any = None) -> Any:
    """Resolve a value key with optional alias support from a lookup record."""
    candidate_keys = _LOOKUP_VALUE_ALIASES.get(value_key, (value_key,))
    for candidate_key in candidate_keys:
        if candidate_key in record:
            return record[candidate_key]
    return default


def resolve_property_value(spec: Any, context: dict[str, Any]) -> Any:
    """Resolve one property spec item using raw, callable, or lookup syntax."""
    if callable(spec):
        return spec(context)

    if isinstance(spec, str):
        return context.get(spec, spec)

    if isinstance(spec, dict):
        lookup = spec.get("lookup", {})
        lookup_key_name = spec.get("lookup_key")
        value_key = spec.get("value_key")
        default = spec.get("default")

        if not lookup_key_name or not value_key:
            raise ValueError(f"Invalid lookup spec: {spec}")

        lookup_key_value = context.get(lookup_key_name, lookup_key_name)
        record = lookup.get(str(lookup_key_value))
        if record is None:
            record = lookup.get(lookup_key_value)

        if isinstance(record, dict):
            return resolve_lookup_value(record, value_key, default)
        return default

    return spec


def build_image_properties(
    image_property_fields: list[str],
    image_property_lookups: dict[str, Any],
    image_context: dict[str, Any],
) -> dict[str, Any]:
    """Build image properties from declarative field and lookup mappings."""
    properties: dict[str, Any] = {}
    for field in image_property_fields:
        if field not in image_property_lookups:
            raise KeyError(f"No lookup defined for image property field: {field}")
        properties[field] = resolve_property_value(image_property_lookups[field], image_context)
    return properties
