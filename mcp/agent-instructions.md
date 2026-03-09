# geeViz Agent Instructions

This project is **geeViz**, a Python package for Google Earth Engine visualization and analysis. You have access to a geeViz MCP server with tools that let you look things up and execute code -- use them instead of typical web search, foundational knowledge, and looking through code.

Copy this file (or its contents) into your editor's agent instructions file to get the best results from your AI assistant. See the section at the bottom for where each editor expects its instructions.

## Rules

1. **Always use the MCP tools before writing GEE and geeViz code.** Do not rely on your training data for function signatures, parameter names, or defaults. Look them up.
2. **Test your code with `run_code` before giving it to the user.** If it errors, fix it. The user should never be the first person to discover a bug.
3. **When you don't know which module a function is in**, use `search_functions` to find it across all modules.
4. **When the user asks about a dataset**, use `inspect_asset` to get its real bands, date range, and CRS -- don't guess.
5. **When writing a workflow similar to an existing example**, use `list_examples` and `get_example` to read the real source first.
6. **Before writing raw `ee` code in `run_code`, check if geeViz already wraps it.** Use `search_functions` to find existing wrappers. geeViz has 16,000+ lines of tested wrapper code — don't reinvent it.
7. **Never write `reduceRegion` / `reduceRegions` / manual zonal stats.** Use the `extract_and_chart` MCP tool for data extraction and charting -- it returns both a structured data table (JSON records) and an interactive chart (HTML). If you need more control, use `chartingLib.summarize_and_chart()` inside `run_code` (see pattern below). Always present both the data table and chart to the user.


## Typical workflow

For a request like "do change detection near Bozeman":

1. `list_examples(filter="LANDTRENDR")` -- find relevant examples
2. `get_example("LANDTRENDRWrapper")` -- read the real source
3. `get_api_reference("changeDetectionLib", "simpleLANDTRENDR")` -- check the actual signature
4. `run_code(...)` -- build the code incrementally, testing each step
5. `view_map()` -- open the map when layers are ready
6. Tell the user the `script_path` from the `run_code` response -- they get a saved .py file

## Key geeViz patterns

- Import: `import geeViz.geeView as gv` -- this initializes Earth Engine automatically
- The `run_code` namespace already has `ee`, `Map` (gv.Map), `gv`, and `gil` (getImagesLib)
- `Map.addLayer(image, vizParams, "name")` adds to the map; `Map.view()` opens it
- `Map.clearMap()` resets the map between experiments
- Study areas: `ee.Geometry.Point([lon, lat]).buffer(meters)` or `ee.Geometry.Polygon([...])`
- Visualization: `{"min": 0, "max": 1, "palette": "red,green,blue"}` or use built-in palettes

## Prefer geeViz wrappers over raw ee code

Before writing any `run_code` that does something manually, check if geeViz already has a function for it. Use `search_functions` to find wrappers. The table below covers the most common cases:

| Task | Don't write raw… | Use geeViz instead |
|---|---|---|
| **Satellite imagery** | `ee.ImageCollection('LANDSAT/...')` + manual filtering, cloud masking, compositing | `gil.getLandsatWrapper()`, `gil.getSentinel2Wrapper()`, or `gil.getLandsatAndSentinel2HybridWrapper()` — these handle band renaming, cloud/shadow masking, and annual compositing in one call |
| **Spectral indices** | Manual NDVI/NBR/NDMI band math (`nir.subtract(red).divide(...)`) | `gil.addIndices(img)` or `gil.simpleAddIndices(img)` — adds 20+ indices at once |
| **Change detection** | `ee.Algorithms.TemporalSegmentation.LandTrendr()` + manual array slicing | `changeDetectionLib.simpleLANDTRENDR()`, `changeDetectionLib.VERDETVertStack()`, `changeDetectionLib.simpleCCDCPrediction()` |
| **Zonal stats & charting** | `reduceRegion` / `reduceRegions` + Plotly boilerplate | `extract_and_chart` MCP tool, or `chartingLib.summarize_and_chart()` in `run_code` |
| **Data conversion** | `.getInfo()` + JSON parsing for FeatureCollections | `gee2Pandas.robust_featureCollection_to_df()` |
| **Exports** | `ee.batch.Export.image.toAsset(...)` etc. | `export_to_asset` / `export_to_drive` / `export_to_cloud_storage` MCP tools, or `assetManagerLib.exportToAssetWrapper()` / `exportToDriveWrapper()` / `exportToCloudStorageWrapper()` in `run_code` |

### Standard band names

geeViz renames raw sensor bands to a common vocabulary. **Always use these names**, never raw sensor band IDs (e.g., `SR_B4`):

- **Common to all sensors:** `blue`, `green`, `red`, `nir`, `swir1`, `swir2`
- **Landsat only:** `temp` (thermal)
- **Sentinel-2 only:** `cb` (coastal/aerosol), `re1`, `re2`, `re3` (red edge), `nir2` (narrow NIR), `waterVapor`

Derived indices added by `addIndices` (exhaustive ration and normalized difference of optical bands) or `simpleAddIndices` (you should use this in most instance. It adds common indices such as `NDVI`, `NBR`, `NDMI`, `NDSI`, and many more) — use `get_api_reference("getImagesLib", "addIndices")`  or `get_api_reference("getImagesLib", "simpleAddIndices")` to see the full list.

## Available MCP tools (30)

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
- `extract_and_chart` -- extract values and chart ee.Image or ee.ImageCollection over a point/region. Auto-detects thematic vs continuous data, supports bar, time series, Sankey, and grouped bar charts. Wraps `geeViz.chartingLib`. For simple point sampling, use with lon/lat and buffer_meters=0.

> **Critical -- data extraction workflow:**
> **Never** write manual `reduceRegion` / `reduceRegions` code. Always use one of these two approaches:
>
> **Preferred: `extract_and_chart` MCP tool** -- one call, returns structured JSON with both data and chart:
> - `summary` key: list of row-dicts (the extracted data table) -- show this to the user and use it for analysis
> - `chart_html` key: self-contained interactive Plotly HTML -- show this to the user
> - `columns`, `row_count`, `chart_type` keys: metadata for your own use
>
> **Fallback: `chartingLib.summarize_and_chart()` in `run_code`** -- use when you need more control (custom reducers, multi-feature extraction, post-processing). **Important:** do NOT use `fig.show()` (opens a browser, useless to agents). Instead, serialize results so `run_code` returns them:

```python
import geeViz.chartingLib as cl
import json

df, fig = cl.summarize_and_chart(
    image_or_collection,   # ee.Image → bar chart, ee.ImageCollection → time series
    study_area,            # ee.Geometry or ee.Feature
    band_names=['nir', 'red', 'green'],  # standardized names
    scale=30,
)

# Get the data table back as structured JSON (agent can read and summarize)
table = df.reset_index().to_dict(orient="records")

# Get the chart as embeddable HTML (agent can show to user)
chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

# Return both -- run_code captures the last expression
json.dumps({"table": table, "chart_html": chart_html})
```

> For Sankey diagrams, `summarize_and_chart` returns a 3-tuple: `(sankey_df, fig, matrix_df)`.
>
> Always present **both** the data table and the chart to the user -- the table lets them see exact values, the chart gives visual context.

> **Charting + Map integration:**
> When you create a chart **and** add the same data to the map, always set `'canAreaChart': True` in the `Map.addLayer()` vizParams. This enables interactive area charting in the geeView map viewer -- users can draw or select areas and see charts update live. Also call `Map.turnOnAutoAreaCharting()` before `Map.view()` to auto-chart on pan/zoom.
>
> ```python
> # After extract_and_chart or chartingLib charting, add the layer with area charting enabled:
> Map.addLayer(image, {'min': 0, 'max': 1, 'canAreaChart': True}, 'My Layer')
> Map.turnOnAutoAreaCharting()
> Map.view()
> ```
>
> For thematic data with `autoViz`, include both:
> ```python
> Map.addLayer(lcms, {'autoViz': True, 'canAreaChart': True, 'areaChartParams': {'line': True, 'sankey': True}}, 'LCMS')
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

### Converting EE FeatureCollections to Pandas Dataframe
- `run_code('import geeViz.gee2Pandas as g2p;g2p.robust_featureCollection_to_df(someEEFeatureCollection)` -- Use this to convert any large featureCollection object to a Pandas dataframe. This is especially useful for large featureCollections. 

> **Warning:** Any server-to-client operation that uses `.getInfo()` will time out after two minutes.

## Where to put this file

Each editor looks for agent instructions in a different place:

- **VS Code / GitHub Copilot**: `.github/copilot-instructions.md`
- **Cursor**: `.cursorrules` or Cursor Settings > Rules
- **Claude Code**: `CLAUDE.md` in the project root
- **Windsurf**: `.windsurfrules`

Copy the contents of this file into the appropriate location for your editor.
