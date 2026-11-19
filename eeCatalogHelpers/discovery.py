"""Recursive TIFF discovery."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .ingest import build_ingest_entry, join_gcs_uri

__all__ = ["build_image_dict"]


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
