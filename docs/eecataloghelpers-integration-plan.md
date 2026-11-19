# Integration plan: merge `ee-catalog-helpers` features into geeViz

Date: 2026-11-18

## Objective

Add an import-safe `geeViz/eeCatalogHelpers/` package that owns the reusable catalog planning, Jsonnet, discovery, table metadata, and raster helper APIs from `ee-catalog-helpers`. Bridge `PlannedImage` to geeViz ingestion with a lazy adapter, and upstream the stronger GCS and Earth Engine runtime operations into `geeViz/assetManagerLib.py`.

This phase changes geeViz only. Existing `ee_catalog_helpers` implementations and downstream LANDFIRE callers remain unchanged until the new geeViz APIs have been validated.

## Design decisions

- The new component is the package directory `geeViz/eeCatalogHelpers/`, not a flat module.
- The package uses focused submodules and re-exports its supported public API from `geeViz/eeCatalogHelpers/__init__.py`.
- The package must remain safe to import in offline planning and metadata-generation workflows.
- Importing it must not initialize Earth Engine or eagerly import `geeViz.geeView`, `geeViz.assetManagerLib`, GDAL, or other runtime-heavy modules.
- Pure planning and metadata helpers belong in `eeCatalogHelpers`.
- Shared remote GCS and Earth Engine operations belong in `assetManagerLib`.
- `eeCatalogHelpers` contains only the lazy `PlannedImage` ingestion adapter, not duplicate implementations of remote operations.
- Existing helper contracts are preserved before broader API redesigns are considered.
- Existing camel-case geeViz APIs remain available during this phase.
- Changes to `ee_catalog_helpers`, LANDFIRE pipelines, TreeMap and Seed scripts, compatibility re-exports, and deprecation warnings are outside this phase.

## Compatibility contracts to preserve

The integration must preserve these contracts from `ee_catalog_helpers`:

- `BandProfile`, `PlannedBand`, and `PlannedImage` remain frozen dataclasses.
- `load_band_profiles()` and `build_planned_bands()` preserve source order and return tuples.
- `PlannedBand.as_ingest_entry()` remains the canonical conversion from a planned band to a geeViz ingestion entry.
- Ingestion entries retain the input keys:
  - `bandName`
  - `pyramidingPolicy`
  - `gcsURI`
  - `noDataValue`
- `join_gcs_uri()` validates a non-empty `gs://` prefix and preserves identifier text.
- Discovery remains recursive and callback-driven, including filtering, normalization, and duplicate resolution.
- Artifact output remains deterministic, UTF-8 encoded, and confined below the requested output directory.
- Optional Earth Engine and GDAL dependencies are loaded only when their runtime functions are called.
- Properties passed to geeViz ingestion are copied because the current implementation removes time fields from the supplied dictionary.

## Phase 1 — Establish behavioral contracts

### 1. Port pure-helper characterization tests

Add geeViz-side tests before moving implementations. Port or reproduce existing assertions for:

- deterministic ingestion-entry construction;
- ordered band-profile loading and planned-band construction;
- nodata coercion;
- GCS URI validation;
- recursive TIFF discovery;
- duplicate-band selection;
- safe catalog artifact paths;
- Jsonnet literals and rendering;
- image-property lookup and resolution;
- table schema inference;
- text normalization;
- RGB and hexadecimal color parsing; and
- import hygiene.

Preserve exception categories and externally useful diagnostics where downstream workflows may rely on them.

### 2. Characterize `ingestFromGCSImagesAsBands()`

Add focused mocked tests around `assetManagerLib.ingestFromGCSImagesAsBands()` for:

- a single string URI;
- lists of URI strings;
- lists of ingestion dictionaries;
- generated tileset and band manifest entries;
- overwrite and existing-asset behavior;
- `system:time_start` and `system:time_end` extraction;
- caller list and property immutability; and
- malformed or incomplete entries.

Verify the field names expected by `ee.data.startIngestion`. Continue accepting the established camel-case input dictionary keys while emitting the Earth Engine Python ingestion schema, expected to use `tileset_id`, `pyramiding_policy`, and `missing_data` within band entries.

#### Phase 1 characterization notes

- Tests live in `geeViz/tests/test_ee_catalog_helpers.py` and `geeViz/tests/test_asset_manager_catalog_helpers.py`. No production implementations change in steps 1 and 2.
- Pure-helper cases run against `ee_catalog_helpers` when that optional source baseline is importable. The same cases target the local `geeViz.eeCatalogHelpers` package automatically once step 3 adds it; until then those target cases explicitly skip.
- Runtime tests load the local `assetManagerLib.py` with fake `ee` and `geeViz.geeView` modules. Strict expected failures track caller-list mutation, caller-property mutation, planned field-name normalization, and missing input validation until step 8. Remove the corresponding markers when those contracts are implemented.
- Schema verification: the [REST ImageManifest reference](https://developers.google.com/earth-engine/reference/rest/v1/ImageManifest#TilesetBand) and the official Earth Engine Python CLI use `tilesetId`, `pyramidingPolicy`, and `missingData`. The inspected Python client's `startIngestion()` forwards band keys without translating them. Therefore, the snake-case spellings above are this plan's intended normalization, not an established requirement of the Python client; current camel-case policy output is not itself evidence of an invalid manifest. Confirm snake-case acceptance in the disposable live-ingestion check before calling the normalized schema production-ready.
- Manifest-preview characterization preserves native text-file newline handling; artifact text written by `write_text_artifacts()` retains its explicit UTF-8/LF contract.

## Phase 2 — Add the `eeCatalogHelpers` package

### 3. Create the package and pure-helper submodules

Create `geeViz/eeCatalogHelpers/` with focused submodules. Define an explicit `__all__` in `geeViz/eeCatalogHelpers/__init__.py` and re-export the supported APIs so `from geeViz import eeCatalogHelpers as ech` remains the primary entry point.

#### Text and parsing

Implement in `text.py` and `parsing.py`:

- `clean_text`
- `normalize_for_matching`
- `choose_preferred_column`
- `value_to_int`
- `color_from_row`

#### Jsonnet rendering

Implement in `jsonnet.py`:

- `JsonnetLiteral`
- `is_jsonnet_identifier`
- `render_jsonnet_value`
- `replace_unit_literals`
- `render_jsonnet_catalog_blocks`
- `render_jsonnet_table_blocks`

#### Properties

Implement in `properties.py`:

- `coerce_nodata_value`
- `resolve_lookup_value`
- `resolve_property_value`
- `build_image_properties`

#### Ingestion planning

Implement in `ingest.py`:

- `build_ingest_entry`
- `BandProfile`
- `PlannedBand`
- `PlannedImage`
- `load_band_profiles`
- `join_gcs_uri`
- `build_planned_bands`
- `write_manifest_preview`

#### Discovery, catalog artifacts, and table metadata

Implement in `discovery.py`, `catalog.py`, and `table_metadata.py`, respectively:

- `build_image_dict`
- `catalog_filename`
- `write_text_artifacts`
- `TABLE_FIELD_TYPES`
- `infer_table_field_type`
- `build_table_schema_from_csv`

Every package module must use only standard-library imports at module load time. `__init__.py` must not weaken this boundary through eager runtime-heavy imports.

### 4. Add optional raster helpers

Add these helpers to `geeViz/eeCatalogHelpers/raster.py` and re-export them from the package root:

- `convert_tif_to_cog`
- `confirm_cog`
- `validate_tif_for_ingest`

Preserve:

- atomic replacement through a temporary partial output;
- cleanup of partial files after failures;
- normalization of legacy `"-co NAME=VALUE"` options into subprocess arguments;
- lazy loading of `osgeo.gdal`; and
- first- and last-pixel readability checks.

Update dependency errors to refer to geeViz rather than `ee-catalog-helpers`. Do not make GDAL a mandatory geeViz import dependency. Keep the current return contracts in this phase; changing `convert_tif_to_cog()` to return an output path should be considered separately.

### 5. Add the planned-image runtime adapter

Add `ingest_planned_image(image, overwrite=False)` to `geeViz/eeCatalogHelpers/ingest.py` and re-export it from the package root.

The adapter must:

1. Import `geeViz.assetManagerLib` inside the function.
2. Convert bands exclusively through `PlannedBand.as_ingest_entry()`.
3. Preserve planned-band order.
4. Call `ingestFromGCSImagesAsBands()` with the entries followed by `image.asset_id`.
5. Forward `overwrite` unchanged.
6. Pass `properties=dict(image.properties)`.
7. Return the result of `ingestFromGCSImagesAsBands()`.

Tests must prove exact argument order, band order, overwrite forwarding, property copying, and absence of eager runtime imports.

## Phase 3 — Harden geeViz runtime APIs

This phase can proceed in parallel with the pure-package work after the characterization tests exist.

### 6. Add strict GCS upload behavior

Add a snake-case `upload_tif(local_tif, gcs_uri, overwrite=False)` API to `geeViz/assetManagerLib.py` using the stronger behavior from `ee_catalog_helpers.gcs.upload_tif()`:

- require an explicit destination object URI;
- validate that the local source is a file;
- validate the `gs://` destination;
- discover `gcloud`, `gcloud.cmd`, or `gcloud.exe` on `PATH`;
- execute an argument list without a shell;
- capture standard output and standard error;
- check the process return code; and
- raise actionable exceptions on failure.

Keep `uploadTifToGCS()` available for backward compatibility. Route it through the strict implementation only where its existing bucket-oriented destination semantics can be preserved without changing current callers.

### 7. Add modern Earth Engine asset operations

Add the following exception-preserving APIs to `geeViz/assetManagerLib.py`:

- `ensure_asset_folder`
- `ensure_asset_path`
- `ensure_parent_asset_path`
- `get_asset`
- `get_asset_if_exists`
- `normalize_asset_type`
- `asset_basename`
- `list_child_asset_basenames`
- `find_missing_collection_children`
- `copy_asset`
- `copy_collection`
- `promote_assets_to_catalog`

Implementation requirements:

- Use modern `ee.data.getAsset()`, `listAssets()`, `createAsset()`, and `copyAsset()` operations.
- Validate `projects/<project>/assets/...` paths where folder traversal is required.
- Validate response types rather than assuming dictionaries or asset lists.
- Treat a genuine not-found response differently from authorization, quota, network, and transient errors.
- Validate existing destination collection types.
- Expose explicit overwrite behavior for collection children.
- Aggregate child-copy failures and raise one actionable error.
- Avoid `print`-and-continue and `sys.exit()` behavior in the new APIs.
- Preserve legacy functions such as `ee_asset_exists()`, `create_asset()`, and `batchCopy()` during this phase.

### 8. Harden multi-image ingestion

Update `ingestFromGCSImagesAsBands()` without changing its public name or accepted input-entry contract:

- normalize input into a new list rather than modifying caller lists;
- copy `properties` before extracting date fields;
- validate required GCS URIs and optional band values;
- emit the verified Earth Engine manifest field names;
- preserve accepted `bandName`, `pyramidingPolicy`, `gcsURI`, and `noDataValue` keys;
- preserve overwrite and existing-asset behavior; and
- return a useful task identifier or underlying submission result if this can be added without breaking callers.

Completion of this step is required before treating `ingest_planned_image()` as production-ready, but it does not block delivery of the pure helpers.

## Phase 4 — Documentation and release readiness

### 9. Document the new APIs

Update the geeViz README or add a focused adjacent guide covering:

- `from geeViz import eeCatalogHelpers as ech`;
- band-profile loading and deterministic plan construction;
- manifest preview generation;
- `ingest_planned_image()`;
- optional GDAL requirements;
- strict `upload_tif()` usage;
- modern Earth Engine asset promotion; and
- the import-safety boundary.

State clearly that importing `eeCatalogHelpers` is offline-safe, while raster, ingestion, upload, and asset-management calls require their corresponding external runtimes.

### 10. Add release notes

Add a geeViz release-note entry describing:

- the new `eeCatalogHelpers` package;
- its public API surface;
- non-mutating ingestion inputs;
- normalized manifest fields;
- optional runtime requirements; and
- continued availability of legacy camel-case asset-manager methods.

Do not deprecate `ee_catalog_helpers` in this phase because migration of downstream packages and scripts is outside scope.

## Expected files

### New geeViz files

- `geeViz/eeCatalogHelpers/__init__.py`
- `geeViz/eeCatalogHelpers/catalog.py`
- `geeViz/eeCatalogHelpers/discovery.py`
- `geeViz/eeCatalogHelpers/ingest.py`
- `geeViz/eeCatalogHelpers/jsonnet.py`
- `geeViz/eeCatalogHelpers/parsing.py`
- `geeViz/eeCatalogHelpers/properties.py`
- `geeViz/eeCatalogHelpers/raster.py`
- `geeViz/eeCatalogHelpers/table_metadata.py`
- `geeViz/eeCatalogHelpers/text.py`
- `geeViz/tests/test_ee_catalog_helpers.py`
- `geeViz/tests/test_asset_manager_catalog_helpers.py`

### Existing geeViz files to update

- `geeViz/assetManagerLib.py`
- `geeViz/README.md`
- `geeViz/release-notes.md`

### Source implementations used for parity

- `ee-catalog-helpers/ee_catalog_helpers/core/ingest.py`
- `ee-catalog-helpers/ee_catalog_helpers/core/jsonnet.py`
- `ee-catalog-helpers/ee_catalog_helpers/core/parsing.py`
- `ee-catalog-helpers/ee_catalog_helpers/core/properties.py`
- `ee-catalog-helpers/ee_catalog_helpers/core/text.py`
- `ee-catalog-helpers/ee_catalog_helpers/catalog.py`
- `ee-catalog-helpers/ee_catalog_helpers/discovery.py`
- `ee-catalog-helpers/ee_catalog_helpers/table_metadata.py`
- `ee-catalog-helpers/ee_catalog_helpers/raster.py`
- `ee-catalog-helpers/ee_catalog_helpers/gcs.py`
- `ee-catalog-helpers/ee_catalog_helpers/earth_engine.py`

## Verification checklist

1. Run the two new focused geeViz test modules offline, with EE, GCS, GDAL, and subprocess interactions mocked.
2. Import `geeViz.eeCatalogHelpers` and each public helper submodule in a clean subprocess and assert that `ee`, `geeViz.geeView`, `geeViz.assetManagerLib`, and `osgeo.gdal` are absent from `sys.modules`.
3. Run parity tests using representative fixtures from the existing `ee-catalog-helpers` suite. Assert identical values and text for ingestion plans, Jsonnet blocks, discovery dictionaries, table schemas, artifact filenames, and artifact contents.
4. Mock `ee.data.startIngestion()` and assert the complete manifest, copied properties, date mapping, task ID, and overwrite flag. Confirm that the original entries and properties remain unchanged.
5. Mock Earth Engine asset responses and failures to cover folder recursion, malformed responses, non-not-found errors, destination collection type validation, sorted missing children, child overwrite behavior, aggregated copy failures, and image, table, and collection promotion.
6. Mock Windows and POSIX `gcloud` discovery and subprocess success and failure. Verify exact arguments and actionable diagnostics. Test `uploadTifToGCS()` compatibility separately.
7. Mock `gdal_translate`, `gdalinfo`, and `osgeo.gdal` for COG conversion cleanup and edge-pixel reads. Ensure no partial output remains after failure.
8. Run the complete geeViz test suite to identify import-time, legacy asset-manager, and packaging regressions.
9. If credentials are available, perform one sandbox Earth Engine ingestion using a disposable asset to validate manifest field spellings against the live API, then delete the asset.

## Later migration phase, intentionally deferred

After the geeViz implementation has passed parity, integration, and live sandbox validation, a separate plan should:

1. Convert `ee_catalog_helpers` into compatibility imports or wrappers around `eeCatalogHelpers` and the hardened `assetManagerLib` APIs.
2. Migrate LANDFIRE, Seed, and TreeMap callers.
3. Add transition warnings and migration documentation.
4. Remove duplicate implementations only after downstream callers have adopted geeViz paths.
