"""Table schema inference from CSV files."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import csv
from pathlib import Path
import re

from .jsonnet import JsonnetLiteral

__all__ = ["TABLE_FIELD_TYPES", "infer_table_field_type", "build_table_schema_from_csv"]

TABLE_FIELD_TYPES = frozenset({"int", "double", "string"})



# Plain decimal text only: Python's int()/float() also accept "1_000", "nan",
# "inf" and non-ASCII digits, none of which Earth Engine tables parse as numbers.
_INT_PATTERN = re.compile(r"[+-]?[0-9]+", re.ASCII)
_DOUBLE_PATTERN = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", re.ASCII)


def infer_table_field_type(values: Iterable[str]) -> str:
    """Infer a table field type from all populated CSV values."""
    populated = [value.strip() for value in values if value.strip()]
    if not populated:
        return "string"

    if all(_INT_PATTERN.fullmatch(value) for value in populated):
        return "int"
    if all(_DOUBLE_PATTERN.fullmatch(value) for value in populated):
        return "double"
    return "string"


def build_table_schema_from_csv(
    csv_path: Path,
    field_descriptions: Mapping[str, str],
    *,
    type_overrides: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    """Build a Jsonnet-ready ``gee:schema`` from a CSV table.

    Descriptions are required for every CSV field. Type overrides accept
    ``int``, ``double``, and ``string``; other fields are inferred from all
    populated CSV values.
    """
    overrides = dict(type_overrides or {})
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError(f"CSV table has no header: {csv_path}")
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError(f"CSV table has duplicate field names: {csv_path}")
        rows = list(reader)

    fields = set(fieldnames)
    missing_descriptions = [
        name for name in fieldnames if not field_descriptions.get(name, "").strip()
    ]
    if missing_descriptions:
        raise ValueError(
            "Missing table field descriptions: " + ", ".join(missing_descriptions)
        )

    unknown_descriptions = sorted(set(field_descriptions) - fields)
    if unknown_descriptions:
        raise ValueError(
            "Descriptions reference fields not present in the CSV: "
            + ", ".join(unknown_descriptions)
        )

    unknown_overrides = sorted(set(overrides) - fields)
    if unknown_overrides:
        raise ValueError(
            "Type overrides reference fields not present in the CSV: "
            + ", ".join(unknown_overrides)
        )
    invalid_types = sorted({
        field_type
        for field_type in overrides.values()
        if field_type not in TABLE_FIELD_TYPES
    })
    if invalid_types:
        raise ValueError(
            "Unsupported table field types: "
            + ", ".join(invalid_types)
            + "; expected int, double, or string"
        )

    schema: list[dict[str, object]] = []
    for name in fieldnames:
        field_type = overrides.get(
            name,
            infer_table_field_type(row.get(name, "") or "" for row in rows),
        )
        schema.append({
            "name": name,
            "description": field_descriptions[name].strip(),
            "type": JsonnetLiteral(f"ee_const.var_type.{field_type}"),
        })
    return schema
