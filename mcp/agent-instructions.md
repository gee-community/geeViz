# geeViz MCP Instructions

**geeViz** is a Python package for Google Earth Engine visualization and analysis. Use MCP tools to look things up, then `run_code` to execute.

## Rules

1. **Look up before coding.** Use `get_api_reference`, `search_functions`, `inspect_asset`, `examples` before writing code. Never guess signatures.
2. **Test with `run_code`.** The user should never be the first to discover a bug.
3. **Never hardcode viz min/max for continuous data.** Use `tl.auto_viz(image, geometry=area)` to compute stretches, pass result to `Map.addLayer()`. For thematic data (LCMS, NLCD, MTBS), use `{'autoViz': True}`. For thumbnails/filmstrips/reports, omit `viz_params` — they auto-detect.
4. **Never write `reduceRegion`/`reduceRegions`.** Use `cl.summarize_and_chart()` in `run_code`.
5. **Use geeViz wrappers** — `search_functions` to find them. Don't reinvent satellite loading, indices, change detection, or zonal stats.
6. **Custom thematic bands** must have `{band}_class_values`, `{band}_class_names`, `{band}_class_palette` set on each image via `.set()`.
7. **`save_file(filename, content)`** for all file writes (works in sandbox and local). `cl.save_chart_html(fig_or_html, "file.html")` for charts.

## REPL namespace

`run_code` has: `ee`, `Map` (gv.Map), `gv`, `gil` (getImagesLib), `sal` (getSummaryAreasLib), `tl` (outputLib.thumbs), `rl` (outputLib.reports), `cl` (outputLib.charts), `save_file`.

## Key patterns

- `Map.addLayer(img, vizParams, "name")` / `Map.addTimeLapse(ic, vizParams, "name")` / `Map.view()`
- `Map.clearMap()` between experiments
- Viz for continuous: `viz = tl.auto_viz(img, geometry=area)` then `Map.addLayer(img, viz, 'name')`
- Viz for thematic when images with ``{band}_class_values``, ``{band}_class_names`` and
    ``{band}_class_palette`` properties: `Map.addLayer(lcms, {'autoViz': True, 'canAreaChart': True}, 'LCMS')`
- Palette-only (single band, no min/max): `tl.auto_viz(img, geometry=area)` then override `viz['palette'] = [...]`
- Charting: `df, fig = cl.summarize_and_chart(ee_obj, geometry, scale=30)` — auto-detects thematic vs continuous
- Sankey: `df, html, matrices = cl.summarize_and_chart(ic, geom, chart_type='sankey', transition_periods=[y1,y2,y3])` — returns D3 HTML string. Save: `cl.save_chart_html(html, "f.html")`. Notebook: `display(HTML(cl.sankey_iframe(html)))`
- Thumbnails: `tl.generate_thumbs(ee_obj, geometry)` / `tl.generate_filmstrip(ic, geometry)` / `tl.generate_gif(ic, geometry)` — all auto-detect viz
- Reports: `rl.Report(title, theme="dark")` → `report.add_section(ee_obj, geometry, title)` → `report.generate(format="html")`
- Geocoding: `gm.geocode("place")` or `search_places` MCP tool. Study areas: `sal.getUSCounties()`, `sal.getUSFSForests()`, `sal.getProtectedAreas()`, etc.
- EDW: `from geeViz.edwLib import search_services, query_features` in `run_code`

## Critical signatures — look up with `get_api_reference`

- `gil.getLandsatWrapper(studyArea, startYear, endYear, startJulian, endJulian)` — Julian days required. Returns dict, composites at `['processedComposites']`.
- `gil.superSimpleGetS2(studyArea, startDate, endDate)` — **preferred** for S2. Returns ee.ImageCollection of cloud-masked scenes. Composite with `.median()`. Do NOT use `getSentinel2Wrapper` unless you need medoid compositing or TDOM.
- `cl.summarize_and_chart(ee_obj, geometry)` — pass ImageCollection directly (auto-mosaics tiled data). `date_format="YYYY-MM"` for sub-annual. `feature_label` for per-feature subplots.
- Band names: `blue`, `green`, `red`, `nir`, `swir1`, `swir2` (never raw sensor IDs). Indices: `NDVI`, `NBR`, `NDMI`, `NDSI` via `gil.simpleAddIndices()`. No `NDWI` — it's `NDMI`.

## Pitfalls

- **Tiled collections (LCMS, NLCD):** Never `.first()` — pass full IC or `.filterBounds().mosaic().copyProperties(ic.first())`.
- **MTBS:** Band name changed 2023+. Always `.select([0], ['Severity'])`.
- **Annual NLCD:** Use `projects/sat-io/open-datasets/USGS/ANNUAL_NLCD/LANDCOVER` (40 years) not official releases (8 snapshots). Band is `b1` — rename and set class properties manually.
- **`fc.first()` returns `ee.Element`**, not `ee.Feature`. Wrap: `ee.Feature(fc.first()).geometry()`.
- **Drought:** `GRIDMET/DROUGHT` for PDSI/SPI/EDDI, not `IDAHO_EPSCOR/GRIDMET`.
- **Hansen:** Latest is `UMD/hansen/global_forest_change_2024_v1_12`.
- **Never call `fig.show()`** in MCP — opens browser, useless to agents.
- **`.getInfo()` timeout:** 2-minute limit. Use coarser scale, smaller region, or `inspect_asset` with filters.

## Tools (22)

**Lookup:** `inspect_asset`, `get_api_reference`, `search_functions`, `examples`, `search_datasets`, `get_catalog_info`, `get_reference_data`, `env_info`
**Execution:** `run_code`, `save_session`
**Map:** `map_control` (view|layers|clear)
**Assets/Tasks:** `list_assets`, `track_tasks`, `cancel_tasks`, `manage_asset`, `export_image`
**Google Maps:** `get_streetview`, `search_places`
**Reports:** `create_report`, `add_report_section`, `generate_report`, `get_report_status`, `clear_report`
