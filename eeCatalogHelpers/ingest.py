"""Ingestion planning dataclasses and the lazy planned-image adapter."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .properties import coerce_nodata_value

__all__ = [
    "build_ingest_entry",
    "BandProfile",
    "PlannedBand",
    "PlannedImage",
    "load_band_profiles",
    "join_gcs_uri",
    "build_planned_bands",
    "write_manifest_preview",
    "ingest_planned_image",
]


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
