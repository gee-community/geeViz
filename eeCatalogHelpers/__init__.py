"""Offline-safe planning and metadata helpers for Earth Engine catalogs.

Only standard-library modules are imported at load time. Raster operations
require GDAL at call time; ingestion lazily imports geeViz.assetManagerLib.
"""

from .text import (
    clean_text,
    normalize_for_matching,
)
from .parsing import (
    choose_preferred_column,
    value_to_int,
    color_from_row,
)
from .jsonnet import (
    JsonnetLiteral,
    is_jsonnet_identifier,
    render_jsonnet_value,
    replace_unit_literals,
    render_jsonnet_catalog_blocks,
    render_jsonnet_table_blocks,
)
from .properties import (
    coerce_nodata_value,
    resolve_lookup_value,
    resolve_property_value,
    build_image_properties,
)
from .ingest import (
    build_ingest_entry,
    BandProfile,
    PlannedBand,
    PlannedImage,
    load_band_profiles,
    join_gcs_uri,
    build_planned_bands,
    write_manifest_preview,
    ingest_planned_image,
)
from .discovery import (
    build_image_dict,
)
from .catalog import (
    catalog_filename,
    write_text_artifacts,
)
from .table_metadata import (
    TABLE_FIELD_TYPES,
    infer_table_field_type,
    build_table_schema_from_csv,
)
from .raster import (
    convert_tif_to_cog,
    confirm_cog,
    validate_tif_for_ingest,
)

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
    "ingest_planned_image",
    "build_image_dict",
    "catalog_filename",
    "write_text_artifacts",
    "TABLE_FIELD_TYPES",
    "infer_table_field_type",
    "build_table_schema_from_csv",
    "convert_tif_to_cog",
    "confirm_cog",
    "validate_tif_for_ingest",
]
