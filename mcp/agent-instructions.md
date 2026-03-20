# geeViz Agent Instructions

This project is **geeViz**, a Python package for Google Earth Engine visualization and analysis. You have access to a geeViz MCP server with tools that let you look things up and execute code -- use them instead of typical web search, foundational knowledge, and looking through code.


## Rules

1. **Always use the MCP tools before writing GEE and geeViz code.** Do not rely on your training data for function signatures, parameter names, or defaults. Look them up.
2. **Test your code with `run_code` before giving it to the user.** If it errors, fix it. The user should never be the first person to discover a bug.
   - *Note: `run_code` may run in a sandboxed or unsandboxed Python environment depending on server configuration. When sandboxed (remote/cloud deployment), `open()`, `os`, `sys`, `eval`, `exec`, and `fig.write_html()` are blocked. When unsandboxed (local/stdio, the default), full Python access is available. Either way, use the built-in `save_file(filename, content)` function (see "Saving files" section below) for portable file writes. geeViz, Earth Engine, numpy, pandas, plotly, and standard data libraries are always available.*
3. **When you don't know which module a function is in**, use `search_functions` to find it across all modules.
4. **When the user asks about a dataset**, use `inspect_asset` to get its real bands, date range, and CRS -- don't guess.
5. **When writing a workflow similar to an existing example**, use `list_examples` and `get_example` to read the real source first.
6. **Before writing raw `ee` code in `run_code`, check if geeViz already wraps it.** Use `search_functions` to find existing wrappers. geeViz has 16,000+ lines of tested wrapper code — don't reinvent it.
7. **Never write `reduceRegion` / `reduceRegions` / manual zonal stats.** Use `chartingLib.summarize_and_chart()` inside `run_code` — it auto-detects thematic vs continuous data, picks the right reducer, and generates charts. Convert results with `df.to_markdown()` and save charts with `save_file()`. See the charting examples below. The `extract_and_chart` MCP tool also wraps this function for simpler cases.


## Typical workflow

For a request like "do change detection near Bozeman":

1. `list_examples(filter="LANDTRENDR")` -- find relevant examples
2. `get_example("LANDTRENDRWrapper")` -- read the real source
3. `get_api_reference("changeDetectionLib", "simpleLANDTRENDR")` -- check the actual signature
4. `run_code(...)` -- build the code incrementally, testing each step
5. `view_map()` -- open the map when layers are ready
6. Tell the user the `script_path` from the `run_code` response -- they get a saved .py file

## Key geeViz patterns

- Import: `import geeViz.geeView as gv` -- this authenticates and/or initializes Earth Engine automatically if it isn't already
- The `run_code` namespace already has `ee`, `Map` (gv.Map), `gv`, `gil` (getImagesLib), `sal` (getSummaryAreasLib), `tl` (thumbLib), `rl` (reportLib), and `save_file`
- `Map.addLayer(image, vizParams, "name")` or `Map.addTimeLapse(imageCollection, vizParams, "name")` adds to the map; `Map.view()` opens it
- `Map.clearMap()` resets the map between experiments
- Study areas: `ee.Geometry.Point([lon, lat]).buffer(meters)` or `ee.Geometry.Polygon([...])`
- Visualization: `{"min": 0, "max": 1, "palette": "red,green,blue"}` or use built-in palettes

### Saving files from `run_code`

When sandboxed, `open()` and `fig.write_html()` are blocked. Use these instead (they work in both sandboxed and unsandboxed modes):

```python
# Save any chart (line, bar, Sankey) with consistent dark styling
import geeViz.chartingLib as cl
path = cl.save_chart_html(fig, "my_chart.html")               # line/bar charts
path = cl.save_chart_html(fig, "my_sankey.html", sankey=True)  # Sankey with gradients

# Save raw text/CSV content
path = save_file("results.csv", df.to_csv())
```

`cl.save_chart_html(fig, filename)` applies a dark Monokai theme matching the Sankey style and writes to `geeViz/mcp/generated_outputs/`. For non-chart files, `save_file(filename, content)` writes to the same directory. Prefer these functions over raw `open()` for portability across sandbox modes.

## Prefer geeViz wrappers over raw ee code

Before writing any `run_code` that does something manually, check if geeViz already has a function for it. Use `search_functions` to find wrappers. The table below covers the most common cases:

| Task | Don't write raw… | Use geeViz instead |
|---|---|---|
| **Satellite imagery** | `ee.ImageCollection('LANDSAT/...')` + manual filtering, cloud masking, compositing | `gil.getLandsatWrapper()`, `gil.superSimpleGets2()` (preferred most efficient method for getting cloud and cloud shadow masked S2 data) or `gil.getSentinel2Wrapper()`, or `gil.getLandsatAndSentinel2HybridWrapper()` — these handle band renaming, cloud/shadow masking, and annual compositing in one call |
| **Spectral indices** | Manual NDVI/NBR/NDMI band math (`nir.subtract(red).divide(...)`) | `gil.addIndices(img)` or `gil.simpleAddIndices(img)` — adds 20+ indices at once |
| **Change detection** | `ee.Algorithms.TemporalSegmentation.LandTrendr()` + manual array slicing | `changeDetectionLib.simpleLANDTRENDR()`, `changeDetectionLib.VERDETVertStack()`, `changeDetectionLib.ccdcChangeDetection()` |
| **Zonal stats & charting** | `reduceRegion` / `reduceRegions` + Plotly boilerplate | `chartingLib.summarize_and_chart()` in `run_code` (preferred), or `extract_and_chart` MCP tool |
| **Data conversion** | `.getInfo()` + JSON parsing for FeatureCollections | `gee2Pandas.robust_featureCollection_to_df()` |
| **Exports** | `ee.batch.Export.image.toAsset(...)` etc. | `export_to_asset` / `export_to_drive` / `export_to_cloud_storage` MCP tools, or `assetManagerLib.exportToAssetWrapper()` / `exportToDriveWrapper()` / `exportToCloudStorageWrapper()` in `run_code` |
| **Study/summary areas** | Manual `ee.FeatureCollection('TIGER/...')` loading + filtering | `sal.getAdminBoundaries(area, level=0|1|2|3|4)` for global admin boundaries (countries, states, counties, sub-districts, localities). Sources: `"geob"` (default, geoBoundaries v6), `"gaul"`, `"gaul2024"`, `"fieldmaps"`. Use `sal.getAdminNameProperty(level, source)` for the name column. Also: `sal.getUSCounties()`, `sal.getUSFSForests()`, `sal.getBuildings()`, `sal.getRoads()`, `sal.getProtectedAreas()`, etc. Use `search_functions(module="getSummaryAreasLib")` to see all available functions. |
| **Thumbnails** | Manual `ee.Image.getThumbURL()` + viz param construction | `tl.auto_viz(ee_obj)` auto-detects thematic/continuous viz params from image properties; `tl.get_thumb_url(ee_obj, geometry)` for PNG; `tl.generate_gif(collection, geometry, burn_in_date=True)` for animated GIF with date labels |
| **Reports** | Manual HTML/chart assembly | `rl.Report(title, theme="dark")` + `report.addSection(ee_obj, geometry, ...)` for each dataset; `report.generate(format="html"|"md"|"pdf")` produces themed reports with parallel EE data fetching, charts, tables, thumbnails, GIFs, and LLM narratives |

### Critical function signatures — always look these up first

**Never guess function signatures.** Use `get_api_reference` to check. Common pitfalls:

- **`gil.getLandsatWrapper(studyArea, startYear, endYear, startJulian, endJulian, ...)`** — `startJulian` and `endJulian` (day of year, 1–365) are **required**. Use `startJulian=1, endJulian=365` for full year, or `152, 273` for summer.
- **`gil.getSentinel2Wrapper(studyArea, startYear, endYear, startJulian, endJulian, ...)`** — same as above.
- **`cdl.simpleLANDTRENDR(ts, startYear, endYear, ...)`** — the first argument `ts` is an **ee.ImageCollection** (time series), NOT a study area. Get composites first with `getLandsatWrapper(...)['processedComposites']`, then pass that to `simpleLANDTRENDR`.
- **`cdl.VERDETVertStack(ts, indexName, ...)`** — `indexName` (e.g. `'NBR'`, `'NDVI'`) is the **required 2nd argument**. Do NOT pass year numbers as the 2nd/3rd args.
- **CCDC is a two-step process:** (1) Run `ee.Algorithms.TemporalSegmentation.Ccdc(collection=scenes, ...)` to get a raw CCDC output image, (2) then `cdl.ccdcChangeDetection(ccdcImg, bandName)` to extract change years/magnitudes. See the `CCDCWrapper` and `CCDCViz` examples. `simpleCCDCPrediction` takes a CCDC *result* image (not composites) — always check the example first.
- **`getLandsatWrapper` returns a dict** — the composites are under `['processedComposites']`, NOT `['composites']`.
- **`cl.summarize_and_chart(ee_obj, geometry, ...)`** — works with both `ee.Image` and `ee.ImageCollection`. Prefer passing the **ImageCollection** rather than converting to a single Image — `summarize_and_chart` auto-filters with `filterBounds` and auto-mosaics per time step internally. For example, with LCMS (which is spatially tiled), do NOT call `.first()` or `.mosaic()` — just pass the filtered ImageCollection directly.
- **`summarize_and_chart` with `feature_label` + `ee.ImageCollection`** — produces **per-feature time series subplots** (one subplot per feature). Returns `(dict, Figure)` where `dict` is `{feature_name: DataFrame}`. Each DataFrame has index = time labels, columns = class/band names. The Figure has one subplot row per feature. For `ee.Image` + `feature_label`, it still produces a grouped bar chart returning `(DataFrame, Figure)`.
- **`summarize_and_chart` `date_format` parameter** — defaults to `"YYYY"` which groups by year. For **sub-annual data** (monthly composites), you MUST pass `date_format="YYYY-MM"` or the months will collapse into a single year value.

### Standard band names

geeViz renames raw sensor bands to a common vocabulary. **Always use these names**, never raw sensor band IDs (e.g., `SR_B4`):

- **Common to all sensors:** `blue`, `green`, `red`, `nir`, `swir1`, `swir2`
- **Landsat only:** `temp` (thermal)
- **Sentinel-2 only:** `cb` (coastal/aerosol), `re1`, `re2`, `re3` (red edge), `nir2` (narrow NIR), `waterVapor`

Derived indices added by `addIndices` (exhaustive ratio and normalized difference of optical bands) or `simpleAddIndices` (preferred in most cases). `simpleAddIndices` adds: `NDVI`, `NBR`, `NDMI`, `NDSI`, and more — use `get_api_reference("getImagesLib", "simpleAddIndices")` to see the full list.

> **NDWI does NOT exist** in geeViz Landsat composites. The water-related index is called **`NDMI`** (nir − swir1) / (nir + swir1). Some literature calls this NDWI or LSWI — in geeViz it is always `NDMI`. If you need McFeeters NDWI (green − nir) / (green + nir), compute it manually.

### Common dataset pitfalls

- **Tiled ImageCollections (LCMS, NLCD, etc.):** Many datasets store multiple spatial tiles per time step. **Never use `.first()` on these** — it grabs one tile that may not cover your study area. Instead, pass the entire `ImageCollection` to `summarize_and_chart` (it auto-mosaics internally), or use `.filterBounds(geometry).mosaic().copyProperties(ic.first())` if you need a single `ee.Image`.
- **Drought indices (PDSI, SPI, SPEI, EDDI):** Use `GRIDMET/DROUGHT`, NOT `IDAHO_EPSCOR/GRIDMET`. The base GRIDMET collection has weather variables (temp, precip); drought indices are in the separate `GRIDMET/DROUGHT` collection.
- **MTBS burn severity mosaics:** The 2023 and 2024 images in `USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1` have a different band name than earlier years. **Always select by index and rename:** `.select([0], ['Severity'])` to ensure a consistent band name across all years.
- **Hansen forest change:** The latest version is `UMD/hansen/global_forest_change_2024_v1_12`. Older versions (2023_v1_11, etc.) show deprecation warnings.
- **NLCD — always use Annual NLCD by default:** When a user asks for NLCD land cover, **always use the Annual NLCD** (`projects/sat-io/open-datasets/USGS/ANNUAL_NLCD/LANDCOVER`) instead of the official releases (`USGS/NLCD_RELEASES/2021_REL/NLCD`). Annual NLCD has 40 annual images (1985-2024) vs. only ~8 snapshot years in the official releases. The band is named `b1` and has no class properties — you must rename it and set properties manually:
  ```python
  nlcd_lc = ee.ImageCollection('projects/sat-io/open-datasets/USGS/ANNUAL_NLCD/LANDCOVER')
  nlcd_viz_props = {
      'LC_class_values': [11,12,21,22,23,24,31,41,42,43,52,71,81,82,90,95],
      'LC_class_palette': ['466b9f','d1def8','dec5c5','d99282','eb0000','ab0000','b3ac9f','68ab5f','1c5f2c','b5c58f','ccb879','dfdfc2','dcd939','ab6c28','b8d9eb','6c9fb8'],
      'LC_class_names': ['Open Water','Perennial Ice/Snow','Developed, Open Space','Developed, Low Intensity','Developed, Medium Intensity','Developed, High Intensity','Barren Land','Deciduous Forest','Evergreen Forest','Mixed Forest','Shrub/Scrub','Grassland/Herbaceous','Pasture/Hay','Cultivated Crops','Woody Wetlands','Emergent Herbaceous Wetlands'],
  }
  nlcd_lc = nlcd_lc.map(lambda img: img.rename('LC').set(nlcd_viz_props))
  ```
  **Do NOT remap** NLCD values to sequential integers (0, 1, 2, ...). The `*_class_values` property tells the charting/viz system how to map the original values (11, 12, 21, ...) to the correct colors and names. Remapping breaks this mapping.

  Only use the official NLCD releases if the user specifically asks for a particular NLCD release version (e.g. "2021 NLCD release"). Other Annual NLCD products: impervious surface (`FRACTIONAL_IMPERVIOUS_SURFACE`), impervious descriptor (`IMPERVIOUS_DESCRIPTOR`), land cover change (`LANDCOVER_CHANGE`), spectral change DOY (`SPECTRAL_CHANGE_DOY`). See the `Annual_NLCD_Viewer_Notebook` example.
- **Building footprints:** Google Open Buildings (`GOOGLE/Research/open-buildings/v3/polygons`) covers Africa, South/Southeast Asia. For US buildings, Microsoft Buildings are at `projects/sat-io/open-datasets/MSBuildings/` but access may vary.

## Available MCP tools (33)

### Code Execution
- `run_code` -- execute Python in a persistent REPL (like Jupyter)
- `save_session` -- save run_code history to a .py file (format="py") or Jupyter notebook (format="ipynb")

### Map Control
- `view_map` -- open the geeView map, returns URL
- `get_map_layers` -- see what's on the map
- `clear_map` -- reset the map

### API Introspection
- `get_api_reference` -- look up function signature + docstring
- `search_functions` -- search/list functions across geeViz modules (query, module, or both)
- `get_reference_data` -- look up reference dicts (band mappings, viz params, collection IDs, change directions, projections, test areas, etc.)

### Asset & Task Management
- `inspect_asset` -- get GEE asset metadata (bands, CRS, dates, properties); for ImageCollections, supports optional date/region filters and returns image count, date range, per-band details
- `list_assets` -- list assets in a folder
- `track_tasks` -- check EE task status
- `cancel_tasks` -- cancel running/ready tasks (all or by name filter)

### Export
- `export_to_asset` -- export an ee.Image to a GEE asset (supports overwrite, pyramiding policy)
- `export_to_drive` -- export an ee.Image to Google Drive
- `export_to_cloud_storage` -- export an ee.Image to Google Cloud Storage

### Zonal Summary & Charting
- `extract_and_chart` -- extract values and chart ee.Image or ee.ImageCollection over a point or region. Pass `lon`/`lat` for a point (defaults to `ee.Reducer.first()`) or `geometry_var` for polygons/features. Auto-detects thematic vs continuous data, supports bar, time series, Sankey (thematic only), and grouped bar charts. Wraps `geeViz.chartingLib`.

> **Critical -- data extraction workflow:**
> **Never** write manual `reduceRegion` / `reduceRegions` code. Use `chartingLib.summarize_and_chart()` in `run_code` for all charting — it handles thematic detection, reducer selection, and chart generation automatically. The `extract_and_chart` MCP tool wraps this same function but `run_code` gives you more control. **Never call `fig.show()`** (opens a browser, useless to agents).
>
> `summarize_and_chart` returns:
> - **Non-Sankey:** `(df, fig)` — a pandas DataFrame and a Plotly Figure
> - **Sankey:** `(sankey_df, fig, matrix_dict)` — flow table, figure, and dict of per-period transition matrices
>
> Always convert results to markdown tables and save charts to HTML files so the user can see them:
> - `df.to_markdown()` → markdown table to show in chat
> - `fig.to_image(format="png")` → PNG bytes for inline display
> - `cl.save_chart_html(fig, "chart.html")` → dark-themed interactive chart file
> - `cl.save_chart_html(fig, "sankey.html", sankey=True)` → gradient Sankey chart

#### Example: Sankey land use transition chart

For a request like *"Chart land use transition between 1990, 2000, and 2024 using LCMS in Salt Lake County"*:

```python
import geeViz.chartingLib as cl

# 1. Define study area from TIGER counties
counties = ee.FeatureCollection("TIGER/2018/Counties")
slc = counties.filter(ee.Filter.And(
    ee.Filter.eq('NAME', 'Salt Lake'),
    ee.Filter.eq('STATEFP', '49')
))
study_area = slc.geometry()

# 2. Load LCMS
lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")

# 3. Chart transitions — summarize_and_chart handles everything
df, fig, matrix_dict = cl.summarize_and_chart(
    lcms,
    study_area,
    sankey=True,
    transition_periods=[1990, 2000, 2024],
    sankey_band_name='Land_Use',
    scale=30,
)

# 4. Save results — use cl.save_chart_html(), NEVER open() or fig.write_html()
md_table = df.to_markdown()
for label, mdf in matrix_dict.items():
    print(f"\n{label}")
    print(mdf.to_markdown())
# save_chart_html with sankey=True applies gradient-colored links automatically
cl.save_chart_html(fig, "land_use_transitions.html", sankey=True)
```

#### Example: Time series of continuous data

For a request like *"Show NDVI trend near Yellowstone from 2000 to 2024"*:

```python
import geeViz.chartingLib as cl

study_area = ee.Geometry.Point([-110.5, 44.6]).buffer(5000)

# 1. Get Landsat composites with indices
# NOTE: getLandsatWrapper requires startJulian and endJulian (day of year)
composites = gil.getLandsatWrapper(
    study_area,
    2000, 2024,
    startJulian=152, endJulian=273  # June 1 – Sep 30
)['processedComposites']

# 2. Chart — auto-detects continuous data, uses ee.Reducer.mean()
df, fig = cl.summarize_and_chart(
    composites,
    study_area,
    band_names=['NDVI'],
    scale=30,
)

md_table = df.to_markdown()
cl.save_chart_html(fig, "ndvi_trend.html")
```

#### Example: Bar chart of land cover at a point

For a request like *"What is the land cover breakdown near Denver?"*:

```python
import geeViz.chartingLib as cl

# Use Annual NLCD (preferred over official NLCD releases)
nlcd_lc = ee.ImageCollection('projects/sat-io/open-datasets/USGS/ANNUAL_NLCD/LANDCOVER')
nlcd_viz_props = {
    'LC_class_values': [11,12,21,22,23,24,31,41,42,43,52,71,81,82,90,95],
    'LC_class_palette': ['466b9f','d1def8','dec5c5','d99282','eb0000','ab0000','b3ac9f','68ab5f','1c5f2c','b5c58f','ccb879','dfdfc2','dcd939','ab6c28','b8d9eb','6c9fb8'],
    'LC_class_names': ['Open Water','Perennial Ice/Snow','Developed, Open Space','Developed, Low Intensity','Developed, Medium Intensity','Developed, High Intensity','Barren Land','Deciduous Forest','Evergreen Forest','Mixed Forest','Shrub/Scrub','Grassland/Herbaceous','Pasture/Hay','Cultivated Crops','Woody Wetlands','Emergent Herbaceous Wetlands'],
}
nlcd_lc = nlcd_lc.map(lambda img: img.rename('LC').set(nlcd_viz_props))
point = ee.Geometry.Point([-104.99, 39.74])

# Latest year as bar chart
df, fig = cl.summarize_and_chart(
    nlcd_lc.filter(ee.Filter.calendarRange(2024, 2024, 'year')),
    point,
    reducer=ee.Reducer.first(),
    scale=30,
)

md_table = df.to_markdown()
cl.save_chart_html(fig, "land_cover_denver.html")
```

> **Charting + Map integration:**
> When you also add data to the map, set `'canAreaChart': True` in vizParams and call `Map.turnOnAutoAreaCharting()` before `Map.view()`:
> ```python
> Map.addLayer(lcms, {'autoViz': True, 'canAreaChart': True, 'areaChartParams': {'line': True, 'sankey': True}}, 'LCMS')
> Map.turnOnAutoAreaCharting()
> Map.view()
> ```


### Asset Operations
- `delete_asset` -- delete a single GEE asset
- `copy_asset` -- copy a GEE asset to a new location
- `move_asset` -- move a GEE asset (copy + delete source)
- `create_folder` -- create a GEE folder or ImageCollection (recursive)
- `update_acl` -- update permissions on a GEE asset

### Dataset Discovery
- `search_datasets` -- search the GEE dataset catalog by keyword
- `get_catalog_info` -- get detailed STAC metadata for a GEE dataset
- `get_thumbnail` -- get a PNG thumbnail of an ee.Image or filmstrip

### Example Discovery
- `list_examples` -- list available geeViz example scripts (40+)
- `get_example` -- read the full source of an example

### Environment
- `get_version_info` -- check geeViz, EE, and Python versions
- `get_namespace` -- see what variables exist in the REPL
- `get_project_info` -- check which EE project is active
- `geocode` -- geocode a place name to coordinates / GEE boundary polygons

### USFS Enterprise Data Warehouse (EDW)
- `search_edw` -- search ~215 USFS EDW services by keyword (fire, ownership, vegetation, roads, trails, wilderness, etc.)
- `get_edw_service_info` -- get layers, fields, geometry type, and extent for an EDW service or layer
- `query_edw_features` -- query features from an EDW layer with spatial (bbox or GeoJSON) and attribute (SQL WHERE) filters; returns GeoJSON FeatureCollection

> **EDW workflow:** The USFS Enterprise Data Warehouse at https://data.fs.usda.gov/geodata/edw/ hosts authoritative Forest Service geospatial data via ArcGIS REST services.
>
> 1. `search_edw("fire")` → find services matching a keyword
> 2. `get_edw_service_info("EDW_MTBS_01")` → see available layers
> 3. `get_edw_service_info("EDW_MTBS_01", layer_id=63)` → see fields and geometry type
> 4. `query_edw_features("EDW_MTBS_01", 63, bbox="-111.5,44,-109.5,45.5", where="YEAR>=2020")` → get GeoJSON features
>
> The returned GeoJSON can be loaded into Earth Engine with `ee.FeatureCollection(geojson)` in `run_code` for further analysis.

### Converting EE FeatureCollections to Pandas Dataframe
- `run_code('import geeViz.gee2Pandas as g2p;g2p.robust_featureCollection_to_df(someEEFeatureCollection)` -- Use this to convert any large featureCollection object to a Pandas dataframe. This is especially useful for large featureCollections since it'll handle the 5000 feature limit by breaking the featureCollection up and merging the output back together. 

> **Warning:** Any server-to-client operation that uses `.getInfo()` will time out after two minutes.

## Where to put this file

Each editor looks for agent instructions in a different place:

- **VS Code / GitHub Copilot**: `.github/copilot-instructions.md`
- **Cursor**: `.cursorrules` or Cursor Settings > Rules
- **Claude Code**: `CLAUDE.md` in the project root
- **Windsurf**: `.windsurfrules`

Copy the contents of this file into the appropriate location for your editor.
