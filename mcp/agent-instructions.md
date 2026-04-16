# geeViz MCP Instructions

**geeViz** is a Python package for Google Earth Engine visualization and analysis. Use MCP tools to look things up, then `run_code` to execute.

## Rules

1. **Look up before coding.** Use `search_functions`, `inspect_asset`, `examples` before writing code. Never guess signatures. `search_functions` results include full signatures — use those directly for straightforward calls. For full docstrings, use `search_functions(function_name="func_name")` — it finds the function across all modules and returns the complete documentation. You do NOT need to know the module name. **Before writing code that uses a dataset, call `inspect_asset` on it to get real band names and properties. Never guess band names.**
2. **Test with `run_code`.** The user should never be the first to discover a bug.
2b. **Only produce what the user asked for.** If the user asks for a sankey chart, produce a sankey chart — do NOT also generate filmstrips, thumbnails, or other outputs "just in case". If a chart fails, fix the error and retry — do NOT switch to a different output type.

   **Format selection rules** — pick the deliverable based on the wording the user actually used:
   - User asks "show me", "visualize", "display", "map", or doesn't specify a format → **interactive map only** (use `map_control`)
   - User says "PNG", "thumbnail", "image", "thumb", "picture" → **PNG only** (use `tl.generate_thumbs`)
   - User says "GIF", "animation" → **GIF only** (use `tl.generate_gif`)
   - User says "filmstrip" → **filmstrip only** (use `tl.generate_filmstrip`)
   - User says "chart", "graph", "sankey", "plot" → **chart only** (use `cl.summarize_and_chart` + `cl.save_chart_html`)
   - User says "report" → **report only** (use `rl.Report` + `report.generate`)
   - User explicitly asks for multiple (e.g. "show the map AND a thumbnail") → produce both, no more

   When in doubt about which format the user wants, default to the interactive map. Don't pile on extra deliverables to be helpful — extra outputs are noise, not value.

   **Always include a `title` argument** for charts (`cl.chart_*`, `cl.summarize_and_chart`) and for thumbs/GIFs/filmstrips (`tl.generate_thumbs`, `tl.generate_gif`, `tl.generate_filmstrip`). Titles drive both the on-image caption and the download filename. Make titles specific (area + dataset + time range): `title="LCMS Land Use — Salt Lake County, 2023"`.
3. **Never hardcode viz min/max.** Use this exact pattern for continuous data:
   ```python
   viz = tl.auto_viz(my_image, geometry=study_area)  # computes percentile stretch
   Map.addLayer(my_image, viz, 'Layer Name')
   ```
   If `auto_viz` fails (timeout on large area), increase scale: `tl.auto_viz(img, geometry=area, scale=5000)`.
   For S2 specifically: use `gil.vizParamsFalse10k` or `gil.vizParamsTrue10k` (pre-computed, no EE call).
   For thumbnails/filmstrips/reports of thematic data: omit `viz_params` — they auto-detect from class properties.
   For multi-band imagery (S2, Landsat): pass `viz_params` (e.g. `viz_params=gil.vizParamsFalse10k`) or `.select()` the 3 display bands first.
   **Never guess min/max. Never hardcode numbers like `{'min': 0, 'max': 3000}`.**
   **For thematic/categorical data — see rule 3b.**
3b. **ALWAYS use `{'autoViz': True, 'canAreaChart': True}` for thematic/categorical data — NEVER use `{'min': X, 'max': Y}` for it.** This is the single most common mistake. If the data represents classes (land cover, land use, change type, severity, classification), the viz params MUST include both `autoViz` and `canAreaChart`. Do NOT pass min, max, or palette for thematic data.
   ```python
   # CORRECT — autoViz + canAreaChart (always use both):
   Map.addLayer(data, {'autoViz': True, 'canAreaChart': True}, 'Name')
   # WRONG — never do this for thematic data:
   Map.addLayer(data, {'min': 10, 'max': 100}, 'Name')
   ```
   Datasets with built-in class properties (autoViz works directly): LCMS, MTBS, ESA WorldCover, Dynamic World, NLCD, MODIS Land Cover. If `inspect_asset` shows `*_class_values` in properties, use `autoViz: True` — do NOT set min/max.
4. **Never write `reduceRegion`/`reduceRegions`.** Use `cl.summarize_and_chart()` in `run_code`. **Never use matplotlib, seaborn, or any plotting library other than `cl` (outputLib.charts).** All charts must use `cl.summarize_and_chart()` and be saved with `cl.save_chart_png()` or `cl.save_chart_html()`.
5. **Use geeViz wrappers** — `search_functions` to find them. Don't reinvent satellite loading, indices, change detection, zonal stats, or study area boundaries. Use `sal` for all boundaries (counties, states, forests, districts, protected areas, roads, buildings).
6. **Thematic data MUST have class properties.** Before charting, visualizing, or adding any thematic/categorical dataset to a report, check if images have `<band>_class_values`, `<band>_class_names`, and `<band>_class_palette` properties. Without these, charts show raw numbers, viz is grayscale, and sankey diagrams fail. **How to check:** use `inspect_asset` and look for `*_class_values` in `image_property_names`. If missing, set them with `.map(lambda img: img.set({...}))`. Datasets like LCMS, MTBS have these built-in. Community datasets and 3rd-party products usually do NOT.
7. **Always save outputs to files** — never return raw image bytes or base64 HTML to the LLM. Use `save_file("name.png", result['bytes'], mode='wb')` for images/GIFs, `save_file("name.html", result['html'])` for HTML. `cl.save_chart_html(fig_or_html, "file.html")` for charts. All thumb/GIF/filmstrip functions return `result['bytes']` (the raw image data) and `result['format']` (`"png"` or `"gif"`). The `output_markdown` field auto-generates links for saved files.

7b. **Show DataFrames as markdown tables.** When you have a `pandas.DataFrame` (e.g. `result['df']` from `summarize_and_chart`, transition matrices from `result['matrix']`, zonal stats output) and the user wants to *see* the values, render it as a markdown table via `print(df.to_markdown())` — NOT `df.to_string()` and NOT `df.head()`. The chat UI renders markdown tables as proper HTML tables. Then paste the printed output into your reply verbatim. Example:
   ```python
   print(result['df'].to_markdown())
   ```
   For very wide tables (>10 columns), consider `print(df.iloc[:, :10].to_markdown())` and mention you truncated, or transpose with `df.T.to_markdown()` if rows are observations and columns are variables.
8. **Never paste `output_markdown` into your response.** The `output_markdown` field in `run_code` results contains local file paths that only work on the server — they will render as broken image links in the chat. Files are automatically displayed as artifacts or inline images by the environment. Just describe what was generated in words.
9. **Use `sal.simple_buffer()` instead of `.buffer()`** for study areas. `sal.simple_buffer(ee.Geometry.Point([lon, lat]), size=15000)` — never `ee.Geometry.Point().buffer()`.
10. **Use `sal` for ALL boundary/study areas — do NOT search for boundary datasets.** When the user mentions a county, state, forest, city, protected area, or any administrative unit, use `sal` directly in `run_code` — do NOT call `search_datasets` to find a boundary dataset. Examples: `sal.getUSCounties(point, state_abbr='UT')`, `sal.getUSStates(point)`, `sal.getUSFSForests(point)`, `sal.getAdminBoundaries(point, level=0)` (countries), `sal.getProtectedAreas(point)`. These are instant — no dataset search needed.

## REPL namespace — these are already available, do NOT re-import or re-initialize

`ee`, `Map` (use directly — do NOT call `gv.Map()`), `gv`, `gil`, `sal`, `tl`, `rl`, `cl`, `gm` (googleMapsLib), `palettes` (geePalettes), `save_file`.

## COMMON MISTAKES — avoid these

- **`Map = gv.Map()`** — WRONG. `Map` is already the singleton mapper object. Use `Map` directly.
- **`gv.Map()`** — WRONG. `mapper` is not callable. Just use `Map`.
- **Raw S2 band names (`B4`, `B3`, `B2`)** — WRONG. geeViz renames bands. Use `red`, `green`, `blue`, `nir`, `swir1`, `swir2`. Always.
- **`ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')`** — WRONG for most use cases. Use `gil.superSimpleGetS2(area, startDate, endDate)` which handles cloud masking and band renaming.
- **`ee.ImageCollection('LANDSAT/...')`** — WRONG. Use `gil.getProcessedLandsatScenes(area, startYear, endYear, startJulian, endJulian)` which handles cloud masking, band renaming, and harmonization across Landsat sensors.
- **Hardcoded min/max** (e.g. `{'min': 0, 'max': 3000}`, `{'min': 20, 'max': 80}`, `{'min': -20, 'max': 40, 'palette': [...]}`) — WRONG for any continuous data, including temperature, precipitation, wind, NDVI, anything. Use `viz = tl.auto_viz(img, geometry=area)` then `Map.addLayer(img, viz, 'name')`. For S2: use `gil.vizParamsFalse10k`. If auto_viz fails, increase `scale=5000`. If you want a specific palette, still call `auto_viz` then override `viz['palette'] = [...]`. **NEVER write `{'min': X, 'max': Y}` for continuous data.**
- **Mixing up S2 and Landsat viz params** — `gil.vizParamsFalse10k` and `gil.vizParamsTrue10k` are for S2 (values 0-10000). `getProcessedLandsatScenes` returns values scaled 0-1 — use `gil.vizParamsFalse` and `gil.vizParamsTrue` (no `10k` suffix) for Landsat. Using `10k` params on Landsat produces a black image.
- **`Map.clear()`** — WRONG. The method is `Map.clearMap()`. There is no `Map.clear()`.
- **Manual `reduceRegion` / `reduceRegions`** — WRONG. Use `result = cl.summarize_and_chart(ee_obj, geometry)` which handles the reducer, scale, and returns `{"df": DataFrame, "chart": Figure}`. This applies to point samples too — pass the point geometry directly.
- **Using matplotlib, seaborn, or any other charting library** — WRONG. **Always** use `cl.summarize_and_chart()` for generating charts and `cl.save_chart_png(fig, "chart.png")` or `cl.save_chart_html(fig, "chart.html")` for saving them. Never `import matplotlib`, never `plt.plot()`, never `plt.savefig()`. The `cl` module handles all charting — time series, area charts, donuts, bar, sankey — with proper theming and formatting.
- **`create_report()` as a Python function** — WRONG. Use `rl.Report(title)` in `run_code`, not the MCP tool as a Python call.
- **ALWAYS `.filterBounds(study_area)` on ImageCollections before ANY operation** — `.addLayer()`, `.addTimeLapse()`, `.mosaic()`, `.first()`, `.median()`, etc. Tiled collections (LCMS, NLCD, MTBS) will show wrong regions (Alaska) without it. Non-tiled collections (S2, Landsat) will timeout without it. **No exceptions.** The charting and thumbnail functions do this internally, but you must do it for `addLayer`/`addTimeLapse`.
- **Using `.first()` on tiled collections (LCMS, NLCD, MTBS)** — WRONG. These datasets are spatially tiled — `.first()` grabs an arbitrary tile (often Alaska, not your study area). ALWAYS `.filterBounds(study_area)` first, then `.mosaic()`. Example:
  ```python
  # WRONG — gets random tile (probably Alaska):
  lcms_2023 = lcms.filter(ee.Filter.eq('year', 2023)).first()
  # CORRECT — filter to study area, then mosaic:
  lcms_2023 = lcms.filter(ee.Filter.eq('year', 2023)).filterBounds(study_area).mosaic()
  lcms_2023 = ee.Image(lcms_2023.copyProperties(ee.Image(lcms.first())))
  ```
- **`.buffer(5000)`** — Use `sal.simple_buffer(point, size=5000)` instead.
- **Adding layers without clearing** — ALWAYS run `Map.clearMap()` as the FIRST line of ANY `run_code` that adds layers. Old layers persist across calls and clutter the map. The only exception: the user explicitly says "add to the existing map".
- **Calling `Map.view()` inside `run_code`** — WRONG. Never put `Map.view()` inside `run_code`. Use `map_control(action="view")` as a separate tool call AFTER adding layers.
- **Using report tools when user asks for a PNG/thumbnail/image** — WRONG. If the user says "show me a png", "give me an image", "thumbnail", etc., use `tl.generate_thumbs(ee_obj, geometry)` in `run_code` and `save_file("name.png", result['bytes'], mode='wb')`. Do NOT use `create_report` / `add_report_section` / `generate_report` for simple image requests. Reports are for multi-section documents with narratives, not single images.
- **Thematic data with `{'min': X, 'max': Y}` instead of `{'autoViz': True, 'canAreaChart': True}`** — WRONG. `Map.addLayer(worldcover, {'min': 10, 'max': 100}, 'ESA WorldCover')` produces a meaningless continuous gradient. CORRECT: `Map.addLayer(worldcover, {'autoViz': True, 'canAreaChart': True}, 'ESA WorldCover')`. This applies to ALL categorical/thematic data: LCMS, NLCD, ESA WorldCover, MTBS, Dynamic World, MODIS LC, etc. **The ONLY correct viz for thematic data is `{'autoViz': True, 'canAreaChart': True}`.** Never pass min/max/palette for thematic layers.
- **Guessing band names** — WRONG. Before using any dataset in code, call `inspect_asset` to get actual band names. They vary across datasets/versions (e.g. MapBiomas: `classification_2000`, not `landcover`; MODIS: `LST_Day_1km`, not `temperature`). Don't assume from training data.
- **Linking to Google Maps for Street View** — WRONG. Use the `get_streetview` MCP tool to fetch and save actual Street View images. It returns saved JPGs with markdown references. Never just provide a Google Maps URL.
- **Manual `ee.FeatureCollection('TIGER/...')` for study areas** — WRONG. Use `sal` (getSummaryAreasLib): `sal.getUSCounties(area)`, `sal.getUSStates(area)`, `sal.getUSFSForests(area)`, `sal.getUSFSDistricts(area)`, `sal.getProtectedAreas(area)`, `sal.getRoads(area)`, `sal.getBuildings(area)`, `sal.getAdminBoundaries(area, level=0|1|2)`. These handle filtering and return clean FeatureCollections. Always use `sal` for boundaries.
- **Thresholding — pick the right pattern based on user intent.** When you create a binary mask via `.gt()`, `.lt()`, `.gte()`, `.lte()`, etc.:

  **Case A — User only wants to SEE pixels that meet the threshold** (e.g. "show areas where NDVI > 0.5", "map wildfires where severity > 3", "highlight forest loss above 50%"). Use `.selfMask()` to drop the 0 values from the map display, and symbolize only the `1` class with a single color. This produces a clean overlay with transparent background showing only the matching areas. **For area charting to correctly count the masked-out 0 values as "not meeting threshold" area, pass `areaChartParams` with `shouldUnmask: True` and `unmaskValue: 0`** — otherwise the chart will only show area for pixels that met the threshold, losing the total/denominator:
  ```python
  above = ndvi.gt(0.5).selfMask().rename('ndvi_above')
  above = above.set({
      'ndvi_above_class_values':  [0, 1],
      'ndvi_above_class_names':   ['NDVI <= 0.5', 'NDVI > 0.5'],
      'ndvi_above_class_palette': ['888888', '00aa00'],
  })
  Map.addLayer(above, {
      'autoViz': True,
      'canAreaChart': True,
      'areaChartParams': {'shouldUnmask': True, 'unmaskValue': 0},
  }, 'NDVI > 0.5')
  ```
  Note class_values/names/palette still include both `0` and `1` (so the legend/chart can label both), but `.selfMask()` keeps the 0s off the map. `shouldUnmask: True` tells the viewer to `.unmask(0)` before reducing for the area chart so the denominator is correct.

  **Case B — User wants to compare above vs. below** (e.g. "classify areas as vegetation vs. not vegetation"). Keep both 0 and 1 values and symbolize both classes:
  ```python
  mask = ndvi.gt(0.3).rename('veg_mask')
  mask = mask.set({
      'veg_mask_class_values':  [0, 1],
      'veg_mask_class_names':   ['Not Vegetation', 'Vegetation'],
      'veg_mask_class_palette': ['888888', '00aa00'],
  })
  Map.addLayer(mask, {'autoViz': True, 'canAreaChart': True}, 'Vegetation Mask')
  ```

  Default to **Case A** (`selfMask()` with single class) when the user phrases it as "where X > Y" or "above/below" — they usually want just the matching areas, not a gray backdrop. Use **Case B** only when the user explicitly wants both categories shown. Without class properties, the threshold renders as a grayscale 0/1 image with no legend — always set the properties.
- **Using `tl.get_thumb_url()` or `ee.Image.getThumbURL()` for thumbnails** — WRONG. These produce bare EE images with no basemap, no legend, no scalebar, no cartographic context. Use `tl.generate_thumbs(ee_obj, geometry)` instead — it composites the EE data over a basemap with legend, scalebar, north arrow, and inset map. For GIFs use `tl.generate_gif(ic, geometry)`. For filmstrips use `tl.generate_filmstrip(ic, geometry)`. Save the result with `save_file("name.png", result['bytes'], mode='wb')`.
- **Missing titles on charts and thumbs** — WRONG. Always pass a `title` argument when generating charts (`cl.chart_donut`, `cl.chart_bar`, `cl.chart_time_series`, etc.) and thumbnails/GIFs/filmstrips (`tl.generate_thumbs`, `tl.generate_gif`, `tl.generate_filmstrip`, `tl.generate_map_chart_gif`). Titles are required for:
  - **User context** — a chart labeled "Land Use Change — Salt Lake City (1985–2023)" is self-describing; one without a title is not.
  - **Download filenames** — Plotly's "Download as PNG" button uses the chart title for the filename (e.g. title "LCMS Donut" → `LCMS_Donut.png`). Without a title, downloads default to `newplot.png`.
  - **Thumbnail captions** — `generate_thumbs` and `generate_gif` overlay the title on the output image as a caption band.

  Make titles specific to the analysis — include the area name, dataset, and time range where relevant. Example:
  ```python
  fig = cl.chart_donut(df, title="LCMS Land Use — Salt Lake County, 2023")
  cl.save_chart_html(fig, "slc_lcms_donut.html")
  thumb = tl.generate_thumbs(img, area, title="S2 False Color — Morgantown, WV (2023)")
  save_file("morgantown_s2.png", thumb['bytes'], mode='wb')
  ```

## Key patterns

- `Map.clearMap()` then `Map.addLayer(img, viz, "name")` in `run_code`, then `map_control(action="export", filename="...")` (chat) or `map_control(action="view")` (notebook) as a **separate tool call** (never `Map.view()` inside `run_code`). The chat/web environment will tell you which action to use; default to `export` if the environment isn't specified.
- **Test before showing the map:** (1) `run_code` — add layers; (2) `map_control(action="test_layers")` — inspect results, fix any layer errors and repeat step 1 until all pass; (3) only after test passes, render the map via `map_control(action="export", filename="...")` (chat / web UI) or `map_control(action="view")` (notebooks / scripts). `test_layers` is fast (~1-2s) — it calls `getMapId()` on all layers in parallel to validate bands, viz params, and computations without launching a browser. **Always run `test_layers` before `export` or `view`** and silently fix any errors it surfaces — never tell the user a test was run.
- **When to use `addTimeLapse` vs `addLayer`:** Use `Map.addTimeLapse(ic, viz, 'name')` when the user wants to see temporal change (before/after, seasonal, multi-year) — it ONLY accepts `ee.ImageCollection`. **Always `.filterBounds(area)` tiled collections before adding as a time lapse.** Use `Map.addLayer()` for everything else — it accepts `ee.Image`, `ee.ImageCollection`, `ee.Geometry`, `ee.Feature`, and `ee.FeatureCollection`. `addTimeLapse` adds a time slider to the map UI. **If the ImageCollection has more than ~40 images, do NOT use `addTimeLapse`** — it will be too slow. Use `Map.addLayer(ic, viz, 'name')` instead, which reduces what's displayed on the map but retains all time steps for area and pixel charting.
- **S2 composite:** `s2 = gil.superSimpleGetS2(area, '2023-06-01', '2023-09-30').median()` then `Map.addLayer(s2, gil.vizParamsFalse10k, 'S2 False Color')` — S2 values are 0-10000, use `10k` viz params.
- **S2 true color:** `Map.addLayer(s2, gil.vizParamsTrue10k, 'S2 True Color')`
- **Landsat composite:** use `gil.vizParamsFalse` and `gil.vizParamsTrue` (no `10k` suffix) — Landsat values are 0-1.
- **Continuous auto-viz:** `viz = tl.auto_viz(img, geometry=area)` then `Map.addLayer(img, viz, 'name')`. If timeout, try `scale=5000`. Pass an `ee.Image`, not `ee.ImageCollection` — reduce first with `.median()` or `.first()`.
- **Thematic with properties:** `Map.addLayer(lcms, {'autoViz': True, 'canAreaChart': True}, 'LCMS')`
- **Time lapse:** `Map.addTimeLapse(image_collection, viz, 'Layer Name')` — adds an interactive time slider to the map. Use this instead of `addLayer` when the user wants to see change over time. Works with any ImageCollection that has `system:time_start`.
- **Area charting:** Add `'canAreaChart': True` to viz params to enable area charting in the interactive map. Works with both `addLayer` and `addTimeLapse`. When enabled, users can draw a polygon on the map and see area summaries.
- **Charting:** `result = cl.summarize_and_chart(ee_obj, geometry, scale=30)` — returns `{"df": DataFrame, "chart": Figure}`. Access with `result['df']`, `result['chart']`. Save with `cl.save_chart_png(result['chart'], 'chart.png')`.
- **Sankey:** `result = cl.summarize_and_chart(ic, geom, band_names='Land_Use', chart_type='sankey', transition_periods=[1990, 2005, 2024], scale=100)` then `cl.save_chart_html(result['chart'], 'sankey.html')`. Returns `{"df": DataFrame, "chart": str (D3 HTML), "matrix": dict}`. `transition_periods` is a **flat list of years** (e.g. `[1990, 2005, 2024]`), NOT nested pairs. The IC must have `system:time_start`. For NLCD/LCMS, pass the full collection — do NOT manually extract individual years.

  **When the user asks for transition matrices**, `result['matrix']` is a dict keyed by `"YYYY → YYYY"` (e.g. `"1990 → 2000"`) with pandas DataFrames as values — each DataFrame is a full from-class × to-class transition matrix (rows = source class, columns = destination class, values = area). Present them as actual matrices in your response, formatted as **markdown tables** using `df.to_markdown()` so the chat UI renders them as real tables. Example loop (no f-strings — agent-instructions don't support braces in code):

  ```python
  for period_key, mat in result['matrix'].items():
      print('### ' + period_key)
      print(mat.to_markdown())
      print()
  ```

  Then in your reply to the user, paste the printed output verbatim — the chat UI parses markdown tables and renders them properly. Do NOT use `.to_string()` (produces fixed-width plain text that doesn't render as a table). Do NOT just list "from / to" cells — the whole point is the full cross-tabulation.
- **Sankey + companion map:** When generating a sankey, ALWAYS also add a companion time lapse to the map with interactive sankey charting enabled. Use `addTimeLapse` with `areaChartParams` set to enable sankey in the viewer. The viewer's `sankeyTransitionPeriods` takes **each year paired with itself**: `[[1985,1985],[1990,1990],[2024,2024]]` — use `[[y, y] for y in years]`. Do NOT use consecutive pairs like `[[1985,1990],[1990,2024]]` — that is WRONG. Full pattern:
  ```python
  years = [1985, 2000, 2024]
  # 1. Generate the sankey chart PNG
  result = cl.summarize_and_chart(lcms, area, band_names='Land_Use',
      chart_type='sankey', transition_periods=years, scale=100)
  cl.save_chart_png(result['chart'], 'sankey.png')
  # 2. Add companion time lapse with interactive sankey
  Map.clearMap()
  lcms_subset = lcms.filter(ee.Filter.inList('year', years)).filterBounds(area).select('Land_Use')
  Map.addTimeLapse(lcms_subset, {
      'autoViz': True, 'canAreaChart': True,
      'areaChartParams': {'sankey': True,
          'sankeyTransitionPeriods': [[y, y] for y in years]}
  }, 'Land Use Time Lapse')
  Map.centerObject(area)
  ```
- **Thumbnails:** `result = tl.generate_thumbs(ee_obj, geometry)` then `save_file("name.png", result['bytes'], mode='wb')` — single image or multi-feature grid. Works with `ee.Image`, `ee.ImageCollection`, `ee.Feature`, `ee.FeatureCollection`. Returns dict with `bytes` (PNG) and `format` ("png").
- **Filmstrip (side-by-side grid):** `result = tl.generate_filmstrip(ic, geometry)` then `save_file("name.png", result['bytes'], mode='wb')` — requires `ee.ImageCollection`. Single PNG with one cell per time step in a grid (default 3 columns). Use when comparing multiple years/dates side by side (e.g. "show me 1990, 2000, 2010, 2020 land cover"). Returns dict with `bytes` (PNG) and `format` ("png").
- **Animated GIF:** `result = tl.generate_gif(ic, geometry)` then `save_file("name.gif", result['bytes'], mode='wb')` — requires `ee.ImageCollection`. Animated GIF cycling through time steps. Use for animation or time-lapse. Returns dict with `bytes` (GIF) and `format` ("gif").
- **Map + chart GIF:** `result = tl.generate_map_chart_gif(ic, geometry, band_name='Land_Cover', basemap='esri-satellite', title='Title')` then `save_file("name.gif", result['bytes'], mode='wb')` — requires `ee.ImageCollection`. Animated GIF with map frames above cumulative line charts. Returns dict with `bytes` (GIF) and `format` ("gif"). Can be slow for many frames.
- **Reports:** `report = rl.Report(title, theme="dark")` → `report.add_section(ee_obj, geometry, title)` → `report.generate(format="html", output_path="report.html")`
- **Study areas:** `sal.simple_buffer(ee.Geometry.Point([lon,lat]), size=15000)` or `sal.getUSCounties(point)`, `sal.getUSFSForests(point)`, etc. The first argument (`area`) is always **required** — pass a point or geometry.
- **Geocoding:** `gm.geocode("place")` or `search_places` MCP tool
- **Street View:** Use the `get_streetview` MCP tool — it fetches actual images, saves them to files, and returns markdown. Do NOT just link to Google Maps. For more control in `run_code`: `gm.streetview_image(lon, lat, heading=0)`, `gm.streetview_panorama()`, `gm.interpret_image()`
- **Places/Elevation/Air Quality:** `gm.search_places("coffee", lat=40.7, lon=-111.9)`, `gm.get_elevation(lon, lat)`, `gm.get_air_quality(lon, lat)`, `gm.get_solar_insights(lon, lat)`
- **Palettes:** `palettes` is in namespace. Collections: `palettes.cmocean`, `palettes.matplotlib`, `palettes.colorbrewer`, `palettes.crameri`, `palettes.kovesi`, `palettes.niccoli`, `palettes.misc`. Each is a dict of named palettes with numbered variants. Example: `palettes.cmocean['Thermal'][7]` returns a 7-color thermal palette list.
- **EDW:** `from geeViz.edwLib import search_services, query_features` in `run_code`

## Critical signatures — look up with `search_functions(function_name="...")`

- `gil.getProcessedLandsatScenes(studyArea, startYear, endYear, startJulian, endJulian)` — Julian days required. Returns processed Landsat scenes with cloud masking and band renaming.
- `gil.superSimpleGetS2(studyArea, startDate, endDate)` — **preferred** for S2. Returns ee.ImageCollection with geeViz band names (`red`, `green`, `blue`, `nir`, `swir1`, `swir2`). Values 0-10000.
- `cl.summarize_and_chart(ee_obj, geometry)` — pass ImageCollection directly (auto-mosaics tiled data). `date_format="YYYY-MM"` for sub-annual. `feature_label` for per-feature subplots.

## Pitfalls

- **Tiled collections (LCMS, NLCD):** Never `.first()` — pass full IC or `.filterBounds(area).mosaic()`. If you need properties: `ee.Image(img.copyProperties(ee.Image(ic.first())))` — note the double `ee.Image()` wrap because `ic.first()` returns `ee.Element`, not `ee.Image`.
- **MTBS:** Band name changed 2023+. Always `.select([0], ['Severity'])`.
- **Annual NLCD:** Use `projects/sat-io/open-datasets/USGS/ANNUAL_NLCD/LANDCOVER` (40 years). Band is `b1` — rename and set class properties manually.
- **`fc.first()` returns `ee.Element`**, not `ee.Feature`. Wrap: `ee.Feature(fc.first()).geometry()`.
- **Drought:** `GRIDMET/DROUGHT` for PDSI/SPI/EDDI, not `IDAHO_EPSCOR/GRIDMET`.
- **GIF fps:** Never set `fps` higher than 2 for `generate_gif`, `generate_map_chart_gif`, or `generate_filmstrip`. Default is 2. Higher values make frames flash too fast to read.
- **Never call `fig.show()`** in MCP — opens browser, useless to agents.
- **`.getInfo()` timeout:** 2-minute limit. Use coarser scale or smaller region.
- **Large collections (ECMWF, GFS, S2, Landsat):** Always `.filterDate()` and `.filterBounds()` BEFORE `.sort()`, `.first()`, `.reduce()`, or `.size()`. Sorting/reducing an unfiltered global collection will timeout.
- **Thematic data without class properties:** #1 cause of bad outputs. Charts show raw numbers, viz is grayscale. Use `inspect_asset` to check, then `.set()` to add properties.

## Tools (21)

**Lookup:** `search_functions` (search, list, or get full docs with `function_name=`), `inspect_asset`, `examples`, `search_datasets`, `get_reference_data`, `env_info` (supports action="reload" to hot-reload modules)
**Execution:** `run_code`, `save_session`
**Map:** `map_control` (view|layers|layer_names|clear|test_layers|test_view) — `test_layers` is a fast quality gate (~1-2s): calls `getMapId()` on all layers in parallel. Always call it BEFORE `view`, fix any layer errors, then `view` only when clean. `test_view` is a slow browser-based screenshot with full JS console capture — use only when you need a visual check.
**Assets/Tasks:** `list_assets`, `track_tasks`, `cancel_tasks`, `manage_asset`, `export_image`
**Google Maps:** `get_streetview`, `search_places`
**Reports:** `create_report`, `add_report_section`, `generate_report`, `get_report_status`, `clear_report`
