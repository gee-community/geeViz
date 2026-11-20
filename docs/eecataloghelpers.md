# eeCatalogHelpers

`geeViz.eeCatalogHelpers` provides offline-safe planning, Jsonnet, discovery,
table-metadata and raster helpers for building Earth Engine catalogs, plus a
lazy adapter that submits a planned image through `geeViz.assetManagerLib`.

```python
from geeViz import eeCatalogHelpers as ech
```

## Import safety

Importing `eeCatalogHelpers` (or any submodule) uses only the standard
library. It does **not** import or initialize `ee`, `geeViz.geeView`,
`geeViz.assetManagerLib` or `osgeo.gdal`, so planning and metadata generation
work offline. Only these calls need an external runtime:

| Call | Needs |
| --- | --- |
| `ech.convert_tif_to_cog`, `ech.confirm_cog`, `ech.validate_tif_for_ingest` | GDAL (`osgeo.gdal`, `gdal_translate`, `gdalinfo`), loaded at call time |
| `ech.ingest_planned_image` | Earth Engine credentials (imports `assetManagerLib` at call time) |
| `assetManagerLib.upload_tif` | `gcloud` CLI on `PATH` |
| `assetManagerLib` asset operations | Earth Engine credentials |

## Plan an image and preview the manifest

```python
from pathlib import Path
from geeViz import eeCatalogHelpers as ech

profiles = ech.load_band_profiles("bands.json")         # ordered tuple of BandProfile
bands = ech.build_planned_bands(
    profiles,
    source_paths={p.name: Path(f"/data/{p.name}.tif") for p in profiles},
    gcs_prefix="gs://my-bucket",
    nodata_values={},
    object_prefix="landfire/2024",
)
image = ech.PlannedImage(
    image_name="img", asset_id="projects/p/assets/cat/img",
    bands=bands, properties={"year": 2024},
)
ech.write_manifest_preview([image], "out/manifest_preview.json")
```

`BandProfile`, `PlannedBand` and `PlannedImage` are frozen dataclasses, and
`PlannedBand.as_ingest_entry()` is the canonical conversion to an ingestion
entry (`gcsURI`, `bandName`, `pyramidingPolicy`, `noDataValue`).

## Ingest

```python
ech.ingest_planned_image(image, overwrite=False)   # returns the startIngestion result
```

The adapter passes band entries in planned order, forwards `overwrite`, and
passes a **copy** of `image.properties`.

`assetManagerLib.ingestFromGCSImagesAsBands()` now validates input, never
modifies the caller's list or properties, and emits `tileset_id`,
`pyramiding_policy` and `missing_data`. It returns the `startIngestion`
result (including the task `id`), or `None` when the asset already exists and
`overwrite` is false. Input dictionaries still use the camel-case
`gcsURI`, `bandName`, `pyramidingPolicy` and `noDataValue` keys.

> Verified against the live Earth Engine API (2026-11-19): a one-band
> ingestion using `tileset_id`, `pyramiding_policy` and `missing_data` was
> accepted, finished with state `SUCCEEDED`, and produced a band with the
> requested `MODE` pyramiding policy.

## Strict GCS upload

```python
from geeViz import assetManagerLib as aml
aml.upload_tif("/data/a.tif", "gs://my-bucket/folder/a.tif", overwrite=False)
```

Requires an explicit `gs://bucket/object` destination and a local file, runs
`gcloud storage cp` without a shell, and raises with the exit code, stdout
and stderr on failure. With `overwrite=False` it first checks for the object
and raises `FileExistsError` instead of letting `gcloud` silently skip it. `uploadTifToGCS()` keeps its bucket-oriented,
non-raising behavior.

## Earth Engine asset promotion

`assetManagerLib` adds `ensure_asset_folder`, `ensure_asset_path`,
`ensure_parent_asset_path`, `get_asset`, `get_asset_if_exists`,
`normalize_asset_type`, `asset_basename`, `list_child_asset_basenames`,
`find_missing_collection_children`, `copy_asset`, `copy_collection` and
`promote_assets_to_catalog`.

```python
aml.promote_assets_to_catalog(
    "projects/p/assets/tmp/img", "projects/p/assets/catalog/img", overwrite=False
)
```

These raise instead of printing or exiting. `get_asset_if_exists` returns
`None` only for a genuine not-found response; permission, quota and network
errors raise `RuntimeError`. `copy_collection` validates an existing
destination is an ImageCollection, honors `overwrite` for children, and
raises one aggregated error for failed children.
