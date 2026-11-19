"""Catalog artifact naming and writing."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

__all__ = ["catalog_filename", "write_text_artifacts"]


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
