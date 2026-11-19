"""Offline-safe planning and metadata helpers for Earth Engine catalogs.

Only standard-library modules are imported at load time. Raster operations
require GDAL at call time; ingestion lazily imports geeViz.assetManagerLib.
The ingestion adapter still depends on the legacy asset manager's runtime
behavior pending the integration plan's ingestion-hardening step.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
import csv
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any


__all__ = [
    "clean_text",
    "normalize_for_matching",
    "choose_preferred_column",
    "value_to_int",
    "color_from_row",
    "JsonnetLiteral",
    "is_jsonnet_identifier",
    "render_jsonnet_value",
    "replace_unit_literals",
    "render_jsonnet_catalog_blocks",
    "render_jsonnet_table_blocks",
    "coerce_nodata_value",
    "resolve_lookup_value",
    "resolve_property_value",
    "build_image_properties",
    "build_ingest_entry",
    "BandProfile",
    "PlannedBand",
    "PlannedImage",
    "load_band_profiles",
    "join_gcs_uri",
    "build_planned_bands",
    "write_manifest_preview",
    "build_image_dict",
    "catalog_filename",
    "write_text_artifacts",
    "TABLE_FIELD_TYPES",
    "infer_table_field_type",
    "build_table_schema_from_csv",
    "convert_tif_to_cog",
    "confirm_cog",
    "validate_tif_for_ingest",
    "ingest_planned_image",
]

_DEFAULT_NULL_TOKENS = {"NA", "N/A", "NONE", "NULL", ""}
_RGB_COLUMN_ALIASES = (("R", "RED"), ("G", "GREEN"), ("B", "BLUE"))
_LOOKUP_VALUE_ALIASES = {
    "name": ("name", "version_name"),
    "version": ("version", "version_decimal"),
    "number": ("number", "version_integer"),
}
TABLE_FIELD_TYPES = frozenset({"int", "double", "string"})


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
    except ValueError:
        return None


def color_from_row(row: Mapping[str, Any]) -> str:
    """Parse '#RRGGBB' or RGB triplets from a row and return uppercase hex."""
    hex_value = normalize_for_matching(None if row.get("HEX") is None else str(row.get("HEX")))
    if hex_value:
        color = hex_value.lstrip("#").upper()
        if len(color) == 6:
            return f"#{color}"

    channels: list[int] = []
    for aliases in _RGB_COLUMN_ALIASES:
        raw_value = next((row.get(alias) for alias in aliases if row.get(alias) is not None), None)
        if raw_value is None:
            raise ValueError("Could not determine color from source CSV row.")
        try:
            channel = int(float(str(raw_value)))
        except ValueError as exc:
            raise ValueError(f"Invalid RGB color value: {raw_value!r}") from exc
        channels.append(channel)

    if not all(0 <= component <= 255 for component in channels):
        raise ValueError(f"RGB color out of range: {tuple(channels)}")

    r, g, b = channels
    return f"#{r:02X}{g:02X}{b:02X}"


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


def build_ingest_entry(
    band_name: str,
    pyramiding_policy: str,
    gcs_uri: str,
    nodata_value: Any,
) -> dict[str, Any]:
    """Build one normalized geeViz multi-image ingest entry."""
    return {
        "bandName": band_name,
        "pyramidingPolicy": pyramiding_policy,
        "gcsURI": gcs_uri,
        "noDataValue": coerce_nodata_value(nodata_value),
    }


@dataclass(frozen=True)
class BandProfile:
    """Metadata contract for one band in a multi-band image."""

    name: str
    source_suffix: str
    source_location: str
    pyramiding_policy: str
    valid_min: float
    valid_max: float
    data_type: str
    conversion: str
    source_valid_values: tuple[float, ...] | None
    value_map: Mapping[float, int] | None
    description: str


@dataclass(frozen=True)
class PlannedBand:
    """One local source raster and its planned ingest settings."""

    profile: BandProfile
    source_path: Path
    gcs_uri: str
    nodata_value: int | float | None

    def as_ingest_entry(self) -> dict[str, Any]:
        return build_ingest_entry(
            band_name=self.profile.name,
            pyramiding_policy=self.profile.pyramiding_policy,
            gcs_uri=self.gcs_uri,
            nodata_value=self.nodata_value,
        )


@dataclass(frozen=True)
class PlannedImage:
    """A deterministic Earth Engine image ingest plan."""

    image_name: str
    asset_id: str
    bands: tuple[PlannedBand, ...]
    properties: Mapping[str, Any]

    def as_preview(self) -> dict[str, Any]:
        return {
            "image_name": self.image_name,
            "asset_id": self.asset_id,
            "bands": [
                {"source_path": str(band.source_path), **band.as_ingest_entry()}
                for band in self.bands
            ],
            "properties": dict(self.properties),
        }


def load_band_profiles(path: str | Path) -> tuple[BandProfile, ...]:
    """Load and validate an ordered JSON band-profile list."""
    profile_path = Path(path)
    with profile_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    records = payload.get("bands") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError(f"Band profile must contain a non-empty 'bands' list: {profile_path}")

    profiles: list[BandProfile] = []
    names: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise TypeError(f"Band profile at index {index} is not an object")
        required = {
            "name", "source_suffix", "source_location", "pyramiding_policy",
            "valid_min", "valid_max", "data_type", "conversion", "description",
        }
        missing = sorted(required - record.keys())
        if missing:
            raise ValueError(f"Band profile at index {index} is missing: {missing}")

        name = str(record["name"]).strip()
        if not name or name in names:
            raise ValueError(f"Band names must be non-empty and unique; found {name!r}")
        names.add(name)

        policy = str(record["pyramiding_policy"]).strip().upper()
        if policy not in {"MEAN", "MODE", "MIN", "MAX", "SAMPLE"}:
            raise ValueError(f"Unsupported pyramiding policy {policy!r} for {name}")

        valid_min = float(record["valid_min"])
        valid_max = float(record["valid_max"])
        if valid_min > valid_max:
            raise ValueError(f"Invalid value range for {name}: {valid_min} > {valid_max}")

        source_location = str(record["source_location"]).strip()
        if source_location not in {"root", "single"}:
            raise ValueError(f"Unsupported source_location {source_location!r} for {name}")

        profiles.append(
            BandProfile(
                name=name,
                source_suffix=str(record["source_suffix"]),
                source_location=source_location,
                pyramiding_policy=policy,
                valid_min=valid_min,
                valid_max=valid_max,
                data_type=str(record["data_type"]),
                conversion=str(record["conversion"]),
                source_valid_values=(
                    tuple(float(value) for value in record["source_valid_values"])
                    if "source_valid_values" in record
                    else None
                ),
                value_map=(
                    {float(key): int(value) for key, value in record["value_map"].items()}
                    if "value_map" in record
                    else None
                ),
                description=str(record["description"]),
            )
        )
    return tuple(profiles)


def join_gcs_uri(prefix: str, object_name: str) -> str:
    """Join a gs:// prefix and object name without changing identifier text."""
    normalized = prefix.strip().rstrip("/")
    if not normalized.startswith("gs://") or normalized == "gs://":
        raise ValueError(f"Expected a non-empty gs:// prefix, received: {prefix!r}")
    return f"{normalized}/{object_name.lstrip('/')}"


def build_planned_bands(
    profiles: Iterable[BandProfile],
    source_paths: Mapping[str, Path],
    gcs_prefix: str,
    nodata_values: Mapping[str, Any],
    object_prefix: str = "",
) -> tuple[PlannedBand, ...]:
    """Build ordered manifest bands from explicit source paths."""
    ordered_profiles = tuple(profiles)
    expected = {profile.name for profile in ordered_profiles}
    supplied = set(source_paths)
    if supplied != expected:
        raise ValueError(
            "Source band set does not match profile. "
            f"Missing={sorted(expected - supplied)}, unexpected={sorted(supplied - expected)}"
        )

    planned: list[PlannedBand] = []
    for profile in ordered_profiles:
        source_path = Path(source_paths[profile.name])
        object_name = f"{object_prefix.strip('/')}/{source_path.name}".lstrip("/")
        planned.append(
            PlannedBand(
                profile=profile,
                source_path=source_path,
                gcs_uri=join_gcs_uri(gcs_prefix, object_name),
                nodata_value=coerce_nodata_value(nodata_values.get(profile.name)),
            )
        )
    return tuple(planned)


def write_manifest_preview(images: Iterable[PlannedImage], path: str | Path) -> None:
    """Write deterministic, human-reviewable ingest plans."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [image.as_preview() for image in images]
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def build_image_dict(
    image_folder: str | Path,
    name_format: str,
    pyramiding_policies: Mapping[str, Any],
    nodata_values: Mapping[str, Any],
    gcs_prefix: str,
    normalize_attribute_name: Callable[[str], str] | None = None,
    include_attribute: Callable[[str], bool] | None = None,
    resolve_duplicate_band: Callable[[str, Path, Path], Path | None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Discover matching TIFFs recursively and build geeViz ingest entries.

    ``name_format`` must contain an ``{attribute}`` placeholder. Dataset-owned
    normalization and filtering rules can be supplied as callbacks.
    """
    folder = Path(image_folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Image folder does not exist: {folder}")
    if "{attribute}" not in name_format:
        raise ValueError("name_format must include the '{attribute}' placeholder")

    prefix, suffix = name_format.split("{attribute}", 1)
    matched_paths = sorted(folder.rglob(f"{prefix}*{suffix}"))
    if not matched_paths:
        raise ValueError(f"No TIFFs found using pattern '{prefix}*{suffix}' under '{folder}'")

    image_dict: dict[str, dict[str, Any]] = {}
    seen_bands: dict[str, Path] = {}
    for image_path in matched_paths:
        if image_path.suffix.lower() != ".tif":
            continue
        image_name = image_path.name
        if not image_name.startswith(prefix) or not image_name.endswith(suffix):
            continue
        attribute = (
            image_name[len(prefix) : len(image_name) - len(suffix)]
            if suffix
            else image_name[len(prefix) :]
        )
        if not attribute:
            raise ValueError(f"Could not infer attribute from image name: {image_name}")
        if include_attribute is not None and not include_attribute(attribute):
            continue

        band_name = normalize_attribute_name(attribute) if normalize_attribute_name else attribute
        if not band_name:
            raise ValueError(f"Attribute normalizer returned an empty band name for: {attribute}")
        if band_name in seen_bands:
            first_path = seen_bands[band_name]
            preferred_path = (
                resolve_duplicate_band(band_name, first_path, image_path)
                if resolve_duplicate_band is not None
                else None
            )
            if preferred_path not in (first_path, image_path):
                raise ValueError(
                    "Multiple input TIFFs resolved to the same band name.\n"
                    f"Band: {band_name}\nFirst file: {first_path}\nSecond file: {image_path}"
                )
            if preferred_path == first_path:
                continue
            del image_dict[str(first_path)]
        if band_name not in pyramiding_policies:
            raise KeyError(
                f"No pyramiding policy found for attribute: {band_name} "
                f"(source attribute: {attribute})"
            )

        seen_bands[band_name] = image_path
        image_dict[str(image_path)] = build_ingest_entry(
            band_name=band_name,
            pyramiding_policy=pyramiding_policies[band_name],
            gcs_uri=join_gcs_uri(gcs_prefix, image_name),
            nodata_value=nodata_values.get(band_name),
        )

    if not image_dict:
        raise ValueError(f"Files matched the pattern but no TIFFs were accepted under '{folder}'")
    return image_dict


def catalog_filename(asset_id: str, suffix: str = ".jsonnet") -> str:
    """Return the standard catalog filename for an Earth Engine asset ID."""
    normalized = asset_id.strip().strip("/")
    if not normalized:
        raise ValueError("Earth Engine asset ID must not be empty")
    if not suffix.startswith("."):
        raise ValueError(f"Catalog filename suffix must start with '.': {suffix!r}")
    return normalized.replace("/", "_") + suffix


def write_text_artifacts(
    output_dir: Path,
    artifacts: Mapping[Path | str, str],
) -> list[Path]:
    """Write a deterministic set of UTF-8 text artifacts below output_dir."""
    output_root = output_dir.resolve()
    written: list[Path] = []
    for relative_path, content in artifacts.items():
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(
                f"Artifact path must be relative and remain below the output directory: {relative}"
            )
        destination = (output_root / relative).resolve()
        if not destination.is_relative_to(output_root):
            raise ValueError(f"Artifact path escapes output directory: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")
        written.append(destination)
    return written


def infer_table_field_type(values: Iterable[str]) -> str:
    """Infer a table field type from all populated CSV values."""
    populated = [value.strip() for value in values if value.strip()]
    if not populated:
        return "string"

    try:
        for value in populated:
            int(value)
    except ValueError:
        pass
    else:
        return "int"

    try:
        for value in populated:
            float(value)
    except ValueError:
        return "string"
    return "double"


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


def convert_tif_to_cog(
    local_tif: str | Path,
    cog_path: str | Path | None = None,
    overwrite: bool = True,
    options: list[str] | None = None,
) -> None:
    """Convert a GeoTIFF using gdal_translate and atomically replace its output."""
    tif_path = Path(local_tif)
    output_path = tif_path.with_suffix(".cog.tif") if cog_path is None else Path(cog_path)
    if output_path.exists() and not overwrite:
        return

    if options is None:
        options = [
            "-co", "COMPRESS=LZW",
            "-co", "TILED=YES",
            "-co", "BIGTIFF=IF_SAFER",
        ]
    elif not isinstance(options, list):
        raise ValueError("options must be a list of GDAL creation options")

    normalized_options: list[str] = []
    for option in options:
        if not isinstance(option, str):
            raise ValueError("options entries must be strings")
        stripped = option.strip()
        if stripped.startswith("-co "):
            # Legacy callers supplied each creation option as one string.
            _, value = stripped.split(None, 1)
            normalized_options.extend(["-co", value])
        else:
            normalized_options.append(stripped)

    partial_path = output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")
    cmd = ["gdal_translate", *normalized_options, str(tif_path), str(partial_path)]
    partial_path.unlink(missing_ok=True)
    try:
        subprocess.run(cmd, check=True)
        os.replace(partial_path, output_path)
    finally:
        partial_path.unlink(missing_ok=True)


def confirm_cog(local_tif: str | Path) -> bool:
    """Check gdalinfo output for the COG layout marker."""
    result = subprocess.run(
        ["gdalinfo", str(Path(local_tif))], capture_output=True, text=True
    )
    return "COG" in result.stdout


def validate_tif_for_ingest(local_tif: str | Path) -> None:
    """Fail fast when a TIFF cannot be opened and sampled by optional GDAL."""
    tif_path = Path(local_tif)
    if not tif_path.exists():
        raise FileNotFoundError(f"Input TIFF does not exist: {tif_path}")
    try:
        from osgeo import gdal
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "GDAL Python bindings are required for raster validation in geeViz. "
            "Install the GDAL Python bindings using a platform-compatible GDAL build."
        ) from exc

    gdal.UseExceptions()
    dataset = None
    try:
        dataset = gdal.Open(str(tif_path), gdal.GA_ReadOnly)
        if dataset is None:
            raise RuntimeError("GDAL returned null dataset")
        band = dataset.GetRasterBand(1)
        if band is None:
            raise RuntimeError("No raster band found in dataset")
        band.ReadAsArray(0, 0, 1, 1)
        band.ReadAsArray(max(dataset.RasterXSize - 1, 0), max(dataset.RasterYSize - 1, 0), 1, 1)
    except RuntimeError as exc:
        raise RuntimeError(
            "Input TIFF failed GDAL readability checks and cannot be ingested safely.\n"
            f"File: {tif_path}\nReason: {exc}"
        ) from exc
    finally:
        dataset = None


def ingest_planned_image(image: PlannedImage, overwrite: bool = False) -> Any:
    """Lazily submit ordered bands; requires the geeViz Earth Engine runtime.

    This copies properties because the legacy ingestion implementation removes
    time fields from its input dictionary. Production readiness still depends
    on the integration plan's asset-manager ingestion hardening.
    """
    from geeViz import assetManagerLib

    return assetManagerLib.ingestFromGCSImagesAsBands(
        [band.as_ingest_entry() for band in image.bands],
        image.asset_id,
        overwrite=overwrite,
        properties=dict(image.properties),
    )
