"""Jsonnet literal rendering helpers."""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = [
    "JsonnetLiteral",
    "is_jsonnet_identifier",
    "render_jsonnet_value",
    "replace_unit_literals",
    "render_jsonnet_catalog_blocks",
    "render_jsonnet_table_blocks",
]


class JsonnetLiteral:
    """Wrapper for raw Jsonnet expressions that must not be quoted."""

    def __init__(self, expression: str):
        self.expression = expression


def is_jsonnet_identifier(key: str) -> bool:
    """Return True when a key can be written unquoted in Jsonnet."""
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key))


def render_jsonnet_value(value: Any, indent: int = 0, indent_step: int = 2) -> str:
    """Render Python values to formatted Jsonnet text."""
    if isinstance(value, JsonnetLiteral):
        return value.expression

    if value is None or isinstance(value, (bool, int, float, str)):
        return json.dumps(value)

    if isinstance(value, list):
        if not value:
            return "[]"
        next_indent = indent + indent_step
        items = [
            " " * next_indent
            + render_jsonnet_value(item, indent=next_indent, indent_step=indent_step)
            + ","
            for item in value
        ]
        return "[\n" + "\n".join(items) + "\n" + " " * indent + "]"

    if isinstance(value, dict):
        if not value:
            return "{}"
        next_indent = indent + indent_step
        lines: list[str] = []
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(
                    f"Jsonnet object keys must be strings. Found key type: {type(k).__name__}"
                )
            key_text = k if is_jsonnet_identifier(k) else json.dumps(k)
            rendered_v = render_jsonnet_value(v, indent=next_indent, indent_step=indent_step)
            lines.append(" " * next_indent + f"{key_text}: {rendered_v},")
        return "{\n" + "\n".join(lines) + "\n" + " " * indent + "}"

    raise TypeError(f"Unsupported value type for jsonnet rendering: {type(value).__name__}")


def replace_unit_literals(value: Any) -> Any:
    """Convert known units expressions (for example 'units.percent') to literals."""
    if isinstance(value, dict):
        converted: dict[str, Any] = {}
        for k, v in value.items():
            if k == "gee:units" and isinstance(v, str) and v.startswith("units."):
                converted[k] = JsonnetLiteral(v)
            else:
                converted[k] = replace_unit_literals(v)
        return converted

    if isinstance(value, list):
        return [replace_unit_literals(v) for v in value]

    return value


def render_jsonnet_catalog_blocks(
    eo_bands: list[dict[str, Any]],
    gee_visualizations: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Render Jsonnet-ready blocks for Earth Engine catalog metadata."""
    rendered: dict[str, str] = {
        "eo_bands": render_jsonnet_value(replace_unit_literals(eo_bands))
    }
    if gee_visualizations is not None:
        rendered["gee_visualizations"] = render_jsonnet_value(
            replace_unit_literals(gee_visualizations)
        )
    return rendered


def render_jsonnet_table_blocks(
    gee_schema: list[dict[str, Any]],
    gee_visualizations: list[dict[str, Any]] | None = None,
    feature_view_ingestion_params: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Render Jsonnet blocks used by Earth Engine table catalog entries."""
    rendered = {
        "gee_schema": render_jsonnet_value(replace_unit_literals(gee_schema)),
    }
    if gee_visualizations is not None:
        rendered["gee_visualizations"] = render_jsonnet_value(
            replace_unit_literals(gee_visualizations)
        )
    if feature_view_ingestion_params is not None:
        rendered["feature_view_ingestion_params"] = render_jsonnet_value(
            feature_view_ingestion_params
        )
    return rendered
