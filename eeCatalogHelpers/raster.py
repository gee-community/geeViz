"""Optional GDAL-backed raster helpers (GDAL is loaded only when called)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

__all__ = ["convert_tif_to_cog", "confirm_cog", "validate_tif_for_ingest"]


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
