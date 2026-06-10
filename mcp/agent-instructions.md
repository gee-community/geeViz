# geeViz MCP Instructions

**geeViz** is a Python package for Google Earth Engine visualization and analysis. Use MCP tools to look things up, then `run_code` to execute.

---

## Core rules

1. **Look up before coding.** Use `search_geeviz` and `inspect_asset` before writing code. Never guess signatures, function names, method names, or band names. **If you find yourself typing a function name from memory (e.g. `sal.getUSNationalParks`, `gil.someThing`, `.rename` on a non-Image), STOP and call `search_geeviz(name="...")` first.** If the search returns 0 results, the function doesn't exist — find an alternative or tell the user; do not "try it anyway".
   - `search_geeviz(query="landsat")` — broad search across all modules
   - `search_geeviz(name="simpleMask")` — full signature and docstring
   - `search_geeviz(module="getImagesLib")` — list all members
   - `search_geeviz(module="examples")` — list example scripts; `name="GFSTimeLapse"` returns source
   - `inspect_asset(asset_id="...")` — real band names, dtypes, and class properties. **Always inspect a dataset before using it.**

2. **Test with `run_code`.** The user should never be the first to discover a bug. Validate before describing results.

3. **Use exact parameter names from search results.** If the signature shows `fps=`, use `fps=` — never substitute synonyms like `framesPerSecond=`. Wrong parameter names cause silent failures.

4. **Don't re-search the same function.** If you already searched and got results, use them. If 0 results, stop after at most 2 attempts (one `query=`, one `name=`) and tell the user the function doesn't exist.

5. **Max 2 retries, then restructure.** If `run_code` fails twice with the same error type (timeout, compute error, band mismatch), don't make a third attempt with minor tweaks. Restructure: coarser scale, smaller area, fewer time steps, or a different approach. For multi-year regional analyses, start at `scale=1000`+ and use `cl.summarize_and_chart()`.

6. **Produce ONLY what the user asked for.** If the user asks for a sankey chart, produce a sankey chart — do NOT also generate filmstrips, thumbnails, or other outputs "just in case". If a chart fails, fix the error and retry — do NOT switch to a different output type. Extra outputs are noise, not value.

7. **Always include a `title` argument** on every chart, thumb, GIF, and filmstrip. Titles drive on-image captions, download filenames, and downstream interpretation. Make them specific: `title="LCMS Land Use — Salt Lake County, 2023"`.

8. **Center the map on every new study area.** Whenever you start an analysis for a different region than the previous one, end your layer-adding `run_code` block with `Map.centerObject(study_area, zoom)` (or `Map.setCenter(lng, lat, zoom)`). The map viewer keeps the previous viewport across turns — if you don't recenter, users see Brazil when they asked about Iowa. **This is mandatory, not optional.** Pick a zoom that frames the area: country/large-state ~5, state ~7, county ~9, city ~11, neighborhood ~13.

9. **Ask before assuming on ambiguous locations.** If the user names a place that exists in many places (e.g. "Springfield" — exists in 40+ US states; "Portland" — OR vs ME; "Columbus" — OH vs GA vs IN; "Cambridge" — MA vs UK), ask which one BEFORE running any code. Same for ambiguous time spans ("recent" can mean days/months/years depending on context). One short clarifying question is cheaper than re-doing the wrong analysis.

10. **Honest failure beats endless retry.** If the same call fails 2–3 times with the same error, stop. Examples that should trigger a stop, not another retry:
    - "No data found" / empty FeatureCollection / 0 results from a name lookup → tell the user the lookup failed, ask for clarification (year, state, alternate name)
    - Same `EEException` ("Band pattern X did not match any bands", "Image.select: no match") on identical code → diagnose, don't re-run
    - Same `AttributeError` on the same function → that function doesn't exist; stop, search, or tell the user
    Never call the same tool with identical arguments more than twice. The result will not change.

11. **Empty image/feature counts → check the STUDY AREA first, not the date range.** If `run_code` reports `Found 0 images`, `0 features`, or `collection is empty` for a region/date range that *should* have data:
    - **DO NOT** retry with adjusted dates more than once. After 2 empty results in a row, the study area is far more likely to be the bug than the dates.
    - Diagnose the area immediately in a small `run_code`:
      ```python
      # FeatureCollection — is it actually populated?
      print("feature count:", area.size().getInfo())
      print("bounds:", area.geometry().bounds().getInfo())
      # Geometry — does it have non-zero area?
      print("area km²:", ee.Number(area.area()).divide(1e6).getInfo() if hasattr(area, "area") else "n/a")
      ```
    - If `size == 0` or bounds look like `[0,0,0,0]` / nonsensical extents, the area lookup is the bug. Fix it (try a different `sal.*` function, a different `name=` argument, or ask the user to clarify the region) BEFORE touching dates.
    - Known dataset coverage — don't loop dates inside these windows expecting nothing:
      - Sentinel-2: 2015-06 → present
      - Landsat 5: 1984 → 2012; Landsat 7: 1999 → present (SLC-off since 2003); Landsat 8: 2013-04 → present; Landsat 9: 2021-10 → present
      - MODIS: 2000 → present
      - LCMS: 1985 → 2023 (CONUS+SE Alaska)
    - If the date range IS valid for the dataset AND the area IS non-empty AND you still get 0 images, then it's a real "no acquisitions in this window" case — tell the user and suggest a wider window. Don't silently keep adjusting.

---

## Format selection — pick the deliverable based on the user's wording

| User says | Use | Save with |
|---|---|---|
| "show me", "visualize", "display", "map" (default) | `Map.addLayer` + `map_control(action="export")` | (auto-exported HTML) |
| "PNG", "thumbnail", "image", "thumb", "picture" | `tl.generate_thumbs(ee_obj, geometry, title=...)` | `save_file("name.png", result['bytes'], mode='wb')` |
| "GIF", "animation" | `tl.generate_gif(ic, geometry, title=...)` | `save_file("name.gif", result['bytes'], mode='wb')` |
| "filmstrip" | `tl.generate_filmstrip(ic, geometry, title=...)` | `save_file("name.png", result['bytes'], mode='wb')` |
| "chart", "graph", "plot", "sankey" | `cl.summarize_and_chart(...)` | `cl.save_chart_html(fig_or_html, "chart.html")` |
| "histogram", "distribution" | `cl.summarize_and_chart(img_or_ic, geom, chart_type="histogram")` — auto-routes to the histogram path; for finer binning add `reducer=ee.Reducer.histogram(maxBuckets=N)` | `cl.save_chart_html(result['chart'], "hist.html")` |
| "custom HTML dashboard", "branded Leaflet page", "embed EE in a custom UI" | `Map.addLayer(...)` for each layer as usual, then `map_control(action="export_layers_json", filename="my_dash.json")` to serialize them, then write your own HTML and `fetch(refresh_url)` to inject fresh tile URLs at page load | `save_file("dashboard.html", html_str)` |
| "report" | `rl.Report(title)` + `report.add_section(ee_obj, geom, ...)` | `save_file("report.html", report.generate(format="html"))` |

**Defaults when ambiguous:** interactive map; HTML for charts.

**Never add outputs the user didn't ask for.** If the user says "PNG" produce only a PNG. If they say "chart" produce only a chart. Suggesting a companion map is fine; producing one without asking is not.

---

## REPL namespace — already available, do NOT re-import or re-initialize

`ee`, `Map` (use directly — do NOT call `gv.Map()`), `gv`, `gil`, `sal`, `tl`, `rl`, `cl`, `gm` (googleMapsLib), `palettes` (geePalettes), `save_file`.

---

## Critical: self-contained `run_code` blocks

Each `run_code` call should be **self-contained** — define all variables it needs (study area, collections, composites, etc.) within that single call so the user can download it as a standalone script.

**When the user asks to change one thing, copy the previous working code and change ONLY that one thing.** Do not restructure, rename variables, change colors, switch approaches, or "improve" anything the user didn't ask about. "Fix the date format" means: take the exact code that just worked, find the date format parameter, change it, run it. Nothing else changes.

If you've lost the previous code (e.g. after many turns of context compaction), call `save_session(format="py")` or `env_info(action="namespace")` to recover — do NOT guess from memory.

---

## Critical: no `.getInfo()` inside loops

Each `.getInfo()` is a round-trip to the EE server — inside a loop this is extremely slow.

**Wrong:**
```python
for year in years:
    col = ee.ImageCollection(...).filter(...)
    if col.size().getInfo() > 0:  # BAD — getInfo in loop
        img = col.median()
```

**Right — pure server-side:**
```python
annual_images = []
for year in years:
    img = col.filter(ee.Filter.calendarRange(year, year, 'year')).median()
    img = img.set({'system:time_start': ee.Date.fromYMD(year, 7, 1).millis()})
    annual_images.append(img)  # No getInfo — pure server-side
ic = ee.ImageCollection.fromImages(annual_images)
```

**Batch unavoidable `.getInfo()` calls into one `ee.Dictionary`:**
```python
info = ee.Dictionary({
    'count': col.size(),
    'first_date': ee.Date(col.first().get('system:time_start')).format('YYYY-MM-dd'),
    'bands': col.first().bandNames(),
}).getInfo()
```

---

## Visualization

### Continuous data — always use `auto_viz`, never hardcode min/max
```python
viz = tl.auto_viz(my_image, geometry=study_area)  # computes percentile stretch
Map.addLayer(my_image, viz, 'Layer Name')
```
- If `auto_viz` times out on large areas, increase scale: `tl.auto_viz(img, geometry=area, scale=5000)`.
- For S2 imagery (0–10000 range): `gil.vizParamsFalse10k` / `gil.vizParamsTrue10k` (pre-computed, no EE call).
- For Landsat (0–1 range): `gil.vizParamsFalse` / `gil.vizParamsTrue` (no `10k` suffix).
- For multi-band imagery, either pass `viz_params=gil.vizParamsFalse10k` or `.select()` 3 display bands first.

**NEVER write `{'min': X, 'max': Y}` for continuous data.** Common bad patterns to avoid: `{'min': 0, 'max': 3000}`, `{'min': -20, 'max': 40, 'palette': [...]}`. Always `auto_viz`. If you want a specific palette, call `auto_viz` then override `viz['palette'] = [...]`.

### Thematic / categorical data — always `{'autoViz': True, 'canAreaChart': True}`
This is the **#1 mistake to avoid.** If data represents classes (land cover, change type, severity, classification), viz params MUST be:
```python
# CORRECT
Map.addLayer(data, {'autoViz': True, 'canAreaChart': True}, 'Name')
# WRONG — never for thematic data
Map.addLayer(data, {'min': 10, 'max': 100}, 'Name')
```
- Datasets that have class properties built-in: LCMS, MTBS, ESA WorldCover, Dynamic World, NLCD, MODIS Land Cover.
- Check with `inspect_asset`: if you see `*_class_values` in properties, use `autoViz`.
- If class properties are missing, set them with `.set({...})` before adding the layer. Charts will show raw numbers, viz will be grayscale, and sankey will fail without them.

### Thresholding
When you create a binary mask via `.gt()`, `.lt()`, etc., pick the pattern based on user intent:

**Case A — "show where X > Y" / "highlight areas above Z"** (most common). Use `.selfMask()` to show only matching pixels with a transparent background:
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
The `shouldUnmask: True` + `unmaskValue: 0` makes area-chart percentages relative to total area (not just the unmasked portion). For Python-side `cl.summarize_and_chart()` instead, use `include_masked_area=True`.

**Case B — "classify as A vs B"** (less common). Keep both 0 and 1 values, symbolize both classes:
```python
mask = ndvi.gt(0.3).rename('veg_mask')
mask = mask.set({
    'veg_mask_class_values':  [0, 1],
    'veg_mask_class_names':   ['Not Vegetation', 'Vegetation'],
    'veg_mask_class_palette': ['888888', '00aa00'],
})
Map.addLayer(mask, {'autoViz': True, 'canAreaChart': True}, 'Vegetation Mask')
```

Default to **Case A** when the user says "where X > Y" or "above/below". Use **B** only when they explicitly want both shown.

### MMU / sieve / clump-and-eliminate
Use this exact order — connected components → mask ≤ threshold → `.reproject()` at the very end:
```python
connected = image.connectedPixelCount(maxSize=256)
mmu_mask = connected.gte(min_pixels)  # e.g. 4-pixel MMU
result = image.updateMask(mmu_mask)
result = result.reproject(crs='EPSG:5070', scale=30)  # MUST be last
```
Never reproject BEFORE `connectedPixelCount` — that changes the pixel grid the connectivity analysis runs on. The final reproject locks native resolution across all zoom levels and prevents single-pixel artifacts.

---

## Study areas — always use `sal`

When the user mentions a county, state, forest, city, protected area, or any administrative unit, use `sal` directly. **Do NOT call `search_datasets` for boundary datasets.** Do NOT use manual `ee.FeatureCollection('TIGER/...')`. Do NOT use `.buffer()` (use `sal.simple_buffer()` instead).

The `area` parameter on all `sal` functions is **optional** — you can filter by name/abbreviation/region without a geometry.

Examples:
- `sal.simple_buffer(ee.Geometry.Point([lon, lat]), size=15000)` — buffer a point
- `sal.getUSCounties(state_abbr='MT')` — all Montana counties
- `sal.getUSCounties(state_abbr='UT', county_names='Salt Lake')` — specific county by name
- `sal.getUSStates(state_abbr='MT,ID,WY')` — multiple states
- `sal.getUSFSForests(forest_name='Lolo')` — a National Forest by name
- `sal.getUSFSForests(region='01')` — all forests in USFS Northern Region
- `sal.getUSFSDistricts(forest_name='Lolo', district_name='Missoula')` — specific district
- `sal.getAdminBoundaries(level=0)` — all countries
- `sal.getProtectedAreas(area)` — protected areas in a region
- `sal.getRoads(area)`, `sal.getBuildings(area)`

All string params accept comma-separated values (`'MT,ID'`) or lists (`['MT', 'ID']`).

---

## Image collections — filter, then operate

**Always `.filterBounds(study_area)` on ImageCollections before any operation** (`.addLayer`, `.addTimeLapse`, `.mosaic`, `.first`, `.median`, etc.). No exceptions.
- Tiled collections (LCMS, NLCD, MTBS) without `filterBounds` show wrong regions (often Alaska).
- Non-tiled collections (S2, Landsat) without `filterBounds` time out.

**Never use `.first()` to get a single image from a tiled or scene-based collection** — you'll get an arbitrary tile, not the area you want:
- **LCMS / NLCD / MTBS** (spatially tiled): always `.filterBounds(area).mosaic()`. If you need properties from the source image: `ee.Image(lcms_2023.copyProperties(ee.Image(lcms.first())))` (double `ee.Image()` wrap because `.first()` returns `ee.Element`).
- **S2 / Landsat** (per-scene, ~100–185 km tiles): `.first()` gives a tiny patch that won't cover most study areas. Use `superSimpleGetS2` / `getProcessedLandsatScenes` over a short date window (3–10 days), then `.median()` or `.mosaic()`. For "latest", narrow the date window — don't `.first()` after sort.

**Large collections (ECMWF, GFS, ERA5, WeatherNext, S2, Landsat):** always `.filterDate()` and `.filterBounds()` BEFORE `.sort()`, `.first()`, `.reduce()`, or `.size()`. For "latest" weather data, filter to the last 2–3 days first, THEN sort and `.first()`. Never sort an unfiltered global collection.

**`filterBounds` on CONUS-wide or many-feature geometries breaks getMapId.** When the agent passes a FeatureCollection with many polygons (e.g. `sal.getUSStates()` — all 50 states with full coastline detail) into `.filterBounds(...)`, EE inlines the full geometry into the computation description sent to the Maps API. The description blows past EE's size limit and `getMapId` returns `"Description length exceeds maximum."` The fix:
- For CONUS-scale views, use a **bounding box**: `study_area = ee.Geometry.BBox(-125, 24, -66, 50)` (or a coarser polygon).
- For already-CONUS-clipped assets (NLCD TCC, LCMS CONUS), skip `.filterBounds` entirely — the asset is already restricted to CONUS.
- For state/county-scale views, `sal.getUSCounties(...)` / `sal.getUSStates(state_abbr="UT")` returns a small FC that filterBounds happily.

---

## Charting — `cl` is canonical, other libraries are allowed with `cl.apply_theme`

**Deliverables (charts the user will see):** use `cl.summarize_and_chart(...)` — it's themed, exported via `save_chart_html`, and consistent with every other chart in this UI. This is the default. The result is a dict with `{"df": DataFrame, "chart": Figure or HTML}`.

**Exploration / one-off statistical plots** (correlograms, pairplots, KDEs, sanity checks before modeling): you may use `matplotlib`, `seaborn`, or `pandas.DataFrame.plot()` directly. To match the chat UI's theme, wrap the result:
```python
import seaborn as sns
fig = sns.heatmap(corr.values).get_figure()
fig = cl.apply_theme(fig)            # post-hoc: dispatches to mpl/plotly/seaborn themer
cl.save_chart_png(fig, "corr.png")   # saves into the artifact pipeline
```
…or wrap the whole block (recommended for matplotlib/seaborn — sets `rcParams` before plotting):
```python
with cl.theme():                     # uses the current default theme
    sns.heatmap(corr.values)
    plt.savefig(buf, format="png")
```
Both `apply_theme(chart)` and `theme()` accept an optional theme name (`"dark"`, `"light"`) and default to whatever the chat is using.

**Never write `reduceRegion` / `reduceRegions`** — `cl.summarize_and_chart()` handles the reducer, scale, and returns `{"df": DataFrame, "chart": Figure or HTML}`.

```python
result = cl.summarize_and_chart(ee_obj, geometry, scale=30)
cl.save_chart_html(result['chart'], 'chart.html')
```

**For sankey / transition charts**, pass the FULL ImageCollection — DO NOT manually extract years, build `from`/`to` images, or hand-roll transition matrices:
```python
# CORRECT — let cl handle it
result = cl.summarize_and_chart(
    lcms,                              # full IC, not pre-extracted years
    area,
    band_names='Land_Use',
    chart_type='sankey',
    transition_periods=[1990, 2005, 2024],  # flat list of years, NOT pairs
    scale=100,
)
cl.save_chart_html(result['chart'], 'sankey.html')
```
Returns `{"df": DataFrame, "chart": HTML string, "matrix": dict of from-class × to-class DataFrames per period}`. If the user wants transition numbers, present `result['matrix']` as markdown tables.

**Wrong pattern that causes spirals** (manual band selection, hand-rolled matrices) — you will hit `Band pattern 'to' did not match any bands. Available bands: [from]` errors:
```python
# WRONG
lcms_1990 = lcms.filter(...).mosaic().select('Land_Use').rename('from')
lcms_2024 = lcms.filter(...).mosaic().select('Land_Use').rename('to')
transition = lcms_1990.addBands(lcms_2024)
```

**Showing DataFrames:** When the user wants to *see* values from a `pandas.DataFrame` (`result['df']`, transition matrices, zonal stats), use `print(df.to_markdown())` — NOT `df.to_string()`, NOT `df.head()`. The chat UI renders markdown tables as proper HTML tables. Paste the printed output verbatim into your reply.

For transition matrices specifically:
```python
for period_key, mat in result['matrix'].items():
    print('### ' + period_key)
    print(mat.to_markdown())
    print()
```

---

## Map control

`Map.clearMap()` then `Map.addLayer(img, viz, "name")` in `run_code`, then call `map_control` as a separate tool call. In ADK chat use `action="export"`; in notebooks use `action="view"`. Default to `export` if the environment isn't specified.

**Layer validation is automatic.** Both `view` and `export` run `test_layers` internally first. If any layer fails, the response includes the errors and the map is NOT opened/exported. You do NOT need to call `test_layers` separately.

**Custom HTML dashboards — `export_layers_json` keeps tiles fresh.**
When the user asks for a custom HTML page / branded dashboard / Leaflet UI that shows EE data:

- **Do NOT iframe the standard geeViz export.** Writing `<iframe src="my_map.html">` inside a custom page is NOT a custom dashboard — it just embeds the default geeViz UI in a frame and loses every reason the user asked for a custom page in the first place (branding, layout, integration with other widgets).
- **Do NOT bake `getMapId` URLs directly into the HTML.** Those URLs are signed mapids that expire in ~1 hour. The dashboard would go blank by tomorrow morning.

Instead, write a real Leaflet (or MapLibre) HTML page that fetches fresh tile URLs at page load:

1. Use `Map.addLayer(...)` for each layer as you normally would.
2. Call `map_control(action="export_layers_json", filename="dash.json")` to serialize the layers (and handle ImageCollection mosaic / vector styling / autoViz resolution automatically). Call this **once** per dashboard; do not retry if it succeeded.
3. The response includes `refresh_url` — copy that exact string into your custom HTML's JS so `fetch(refresh_url)` returns `{urls: {Name: "https://earthengine.../tiles/<z>/<x>/<y>", ...}}` (URLs in real responses use curly braces; angle brackets here are escaped for the prompt-parser).
4. Save the custom HTML via `save_file("dashboard.html", html_str)`. The HTML should contain `<script src="https://unpkg.com/leaflet.../leaflet.js"></script>`, a `<div id="map">`, your custom CSS for branding, and a `<script>` block that creates the Leaflet map and calls fetch on the refresh_url to add tile layers. No iframe.

Example skeleton (Leaflet — agent provides their own branding/layout):
```python
Map.clearMap()
Map.addLayer(biomass, viz_b, "Biomass")
Map.addLayer(canopy,  viz_c, "Canopy Height")
# ...
# Then via a separate map_control call:  export_layers_json filename=dash.json
# It returns {"refresh_url": "/api/dashboard/urls?session_id=...&file=dash.json", ...}
```

```html
<!-- Custom HTML the agent writes -->
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const map = L.map('map').setView([44.05, -121.31], 9);
  L.tileLayer('https://server.arcgisonline.com/.../World_Imagery/MapServer/tile/<z>/<y>/<x>').addTo(map);  // use curly braces around z/y/x in the real URL
  fetch("REFRESH_URL_HERE").then(r => r.json()).then(data => {
    for (const [name, url] of Object.entries(data.urls)) {
      L.tileLayer(url, {opacity: 0.8}).addTo(map);
    }
  });
</script>
```
Tiles re-mint on every page load. Files stay valid as long as the agent server is alive. Substitute the `REFRESH_URL_HERE` placeholder with the actual `refresh_url` from the `export_layers_json` response.

**`addTimeLapse` vs `addLayer` vs `addTileLayer`:**
- Use `Map.addTimeLapse(ic, viz, 'name')` for temporal change (slider with multiple frames). Accepts ONLY `ee.ImageCollection`. If the IC has more than ~40 images, do NOT use `addTimeLapse` — it's too slow. Use `Map.addLayer(ic, viz, 'name')` which reduces what's shown but retains all time steps for area/pixel charting.
- Use `Map.addLayer()` for everything else. Accepts `ee.Image`, `ee.ImageCollection`, `ee.Geometry`, `ee.Feature`, `ee.FeatureCollection`.
- Use `Map.addTileLayer(url_template, name)` to overlay an **external XYZ tile service** (third-party basemap, ArcGIS MapServer, partner tile endpoint) WITHOUT leaving geeViz for Leaflet. The URL must use the standard XYZ tile syntax — curly braces around the lowercase letters z, x, and y for the zoom and tile coordinates (see the `addTileLayer` docstring via `search_geeviz` for the literal form). Optional kwargs: `visible=True`, `opacity=1.0`, `max_zoom=20`. Example (angle brackets shown here for documentation only — substitute curly braces in the real URL):
  ```python
  Map.addTileLayer(
      "https://viz-assets.ctrees.org/sfi/basemaps/agb_100m/<z>/<x>/<y>.png",  # use curly braces in real URLs
      name="CTrees AGB (100m)",
      opacity=0.7,
  )
  ```
  Prefer this over generating Leaflet HTML for tile overlays — state persists across turns and the layer integrates with the geeViz layer list / opacity controls / area charting.

**Time-lapse date formatting** (non-annual data only):
- Hourly (GFS, ERA5): `{'dateFormat': 'YY-MM-dd HH', 'advanceInterval': 'hour', ...}`
- Daily: `{'dateFormat': 'YYYY-MM-dd', 'advanceInterval': 'day', ...}`
- Monthly: `{'dateFormat': 'YYYY-MM', 'advanceInterval': 'month', ...}`
- Annual (LCMS, NLCD — default): omit both.

For continuous data with units, add `'legendLabelLeftAfter': 'C'` etc. for unit labels.

**Area charting:** Add `'canAreaChart': True` to viz params to enable polygon area summaries in the viewer. Works with both `addLayer` and `addTimeLapse`.

**Map.clearMap() — always first.** Run `Map.clearMap()` as the FIRST line of ANY `run_code` that adds layers. Old layers persist across calls otherwise. Only exception: user explicitly says "add to the existing map".

**Center the map — always last.** End every layer-adding `run_code` block with `Map.centerObject(study_area, zoom)`. The viewport DOES NOT auto-pan to your data — without an explicit center, users will see whatever region the previous query landed on (Brazil, Nevada, etc.) instead of the area they just asked about.
```python
Map.clearMap()
Map.addLayer(data, viz, 'Data')
Map.addLayer(study_area, {'strokeColor': '00F', 'layerType': 'geeVector'}, 'Study Area')
Map.centerObject(study_area, 9)   # ← REQUIRED for every new region
```
Pick zoom by extent: country/large-state ~5, state ~7, county ~9, city ~11, neighborhood ~13. For points, use `Map.setCenter(lon, lat, zoom)` instead. Skip only if the user explicitly said "keep the current view".

**Study area layer order — last (before centering).** If you're adding a study-area boundary, add it LAST so it renders on top of data layers, then center on it:
```python
Map.addLayer(data, viz, 'Data')
Map.addLayer(study_area, {'strokeColor': '00F', 'layerType': 'geeVector'}, 'Study Area')
Map.centerObject(study_area, 9)
```

---

## Visual inspection (`view_output`, `preview`)

Only call `view_output` or `map_control(action="preview")` when the user **explicitly asks** to look at / describe / interpret / compare a visual output, or when you need to debug a clearly failed visual (blank, wrong area).

Generating a thumbnail / chart / map does **not** require viewing it afterward. The user can see it themselves.

**`view_output` only handles raster images** (PNG / GIF / JPEG / WebP) — it does NOT work on HTML files. For HTML maps use `map_control(action="preview")`. For HTML charts already in memory, describe from `result['df']` / `result['matrix']` rather than re-rendering as PNG.

---

## Common output formats

### Thumbnails — `tl.generate_thumbs`
```python
result = tl.generate_thumbs(ee_obj, geometry, title="...")
save_file("name.png", result['bytes'], mode='wb')
```
Single image or multi-feature grid. Works with `ee.Image`, `ee.ImageCollection`, `ee.Feature`, `ee.FeatureCollection`. Returns `{'bytes': PNG, 'format': 'png'}`.

**Do NOT use `tl.get_thumb_url()` or `ee.Image.getThumbURL()`** — those produce bare EE tiles with no basemap, legend, scalebar, or cartographic context.

### Filmstrip — `tl.generate_filmstrip(ic, geometry, title=...)`
Side-by-side grid of time-step frames. Returns `{'bytes': PNG, 'format': 'png'}`. Use for "show me 1990, 2000, 2010, 2020 land cover" side-by-side comparisons.

### Animated GIF — `tl.generate_gif(ic, geometry, title=...)`
Cycles through time steps. Returns `{'bytes': GIF, 'format': 'gif'}`. Use for animation / time-lapse.

### Map + chart GIF — `tl.generate_map_chart_gif(ic, geometry, band_name='Land_Cover', basemap='esri-satellite', title='...')`
Animated GIF with map frames above cumulative line charts. Can be slow for many frames.

### Sankey (already covered in Charting section above)

### Reports — `rl.Report`
```python
report = rl.Report(title, theme="dark")
report.add_section(ee_obj, geometry, title="Section", prompt="Optional narrative guidance")
html = report.generate(format="html")
save_file("report.html", html)
```

`add_section` signature: `add_section(ee_obj, geometry, title="Section", prompt=None, generate_table=True, generate_chart=True, thumb_format="png", chart_types=None, **kwargs)`. **There is NO `description` parameter.** Use `prompt="..."` to guide the narrative.

**Reports are for geospatial analysis only.** Each section requires a real `ee_obj` over a real study area. Do NOT use `rl.Report` for "explain yourself" / "make a presentation about how you work" / non-geospatial questions — answer those in chat. Don't invent `ee.Image(1)` placeholders to feed Report; the result will have errored sections.

**Decide explicitly per section what content makes sense — the defaults bundle table + chart + thumb together, which is wrong for many outputs.** Before adding a section, ask: *would a chart of this image actually tell the user anything?* If not, set `generate_chart=False`. Same for `generate_table=False` and `thumb_format=None`. The wrong choice clutters the report with two-bar histograms and identical "1.0" tables.

| Output type | thumb | chart | table | Why |
|---|---|---|---|---|
| Thresholded / binary mask (e.g. `ndvi.gt(0.5)`) | `"png"` | `False` | `True` | A chart of a binary image is two bars — meaningless. Table gives the area % cleanly. |
| Classified categorical image (LCMS, NLCD, land cover) | `"png"` | `True` | `True` | Bar/donut of class areas is the headline number. |
| Continuous index (NDVI, NBR, elevation) | `"png"` | `True` (histogram) or `False` | `True` | A distribution chart helps; for a single composite it's often noise. Default `chart_types=["histogram"]` when wanted. |
| Time series (`ImageCollection` over time) | `"gif"` or `"filmstrip"` | `True` (line+markers) | `True` | The animated thumb shows change; the line chart quantifies it. |
| Vector / FeatureCollection summary | `None` | `True` (bar) | `True` | Static thumb of polygons is rarely useful; the chart compares feature attributes. |
| Single scalar value (one number) | `None` | `False` | `True` | One number — table is enough. |

**Thresholded outputs need `.unmask(0)` before going into a report section.** Unlike `Map.addLayer` (where `.selfMask()` is preferred for the live viewer), a Report's PNG thumbnail is static — a self-masked binary makes the thumb mostly transparent and shows only the matching pixels with no surrounding context. Unmask to 0 so the thumb shows the entire study area with above-threshold pixels highlighted against a visible background:

```python
above = ndvi.gt(0.5).unmask(0).rename('ndvi_above')
above = above.set({
    'ndvi_above_class_values':  [0, 1],
    'ndvi_above_class_names':   ['NDVI <= 0.5', 'NDVI > 0.5'],
    'ndvi_above_class_palette': ['888888', '00aa00'],
})
report.add_section(above, study_area, title="Vegetation above 0.5 NDVI",
                   generate_chart=False)  # binary -> chart is noise
```

The same pattern applies to MMU-filtered outputs, change-detection masks, and any `.gt/.lt/.eq` result: `.unmask(0)` for reports, `.selfMask()` for the live map.

**`output_path=` is forbidden on `report.generate()`** — it writes to CWD where the artifact pipeline can't see. Always get the HTML string back and route through `save_file()`.

**Thumbnail errors with `Description length exceeds maximum`** are the same issue as the dashboard `getMapId` failure — a too-complex EE expression chain, typically from `.filterBounds(...)` over a many-polygon FeatureCollection like `sal.getUSStates()`. For CONUS-scale reports, use `ee.Geometry.BBox(-125, 24, -66, 50)` as the geometry (or skip `filterBounds` entirely on already-CONUS-clipped assets like NLCD TCC, LCMS CONUS). Section-level errors render in the output but the thumbnail itself goes blank.

### Output file rules
- Always route binary content through `save_file("name.ext", bytes_or_str, mode='wb' if binary else 'w')`.
- Never return raw image bytes or base64 HTML to the LLM as a tool result.
- The `output_markdown` field in `run_code` responses auto-generates artifact links — the chat UI renders them. Do not paste those links into your reply.

---

## Pitfalls & common mistakes

### Map / Map object
- **`Map = gv.Map()` or `gv.Map()`** — wrong. `Map` is already in the namespace as a session-scoped singleton. Use `Map` directly.
- **`Map.clear()`** — wrong. The method is `Map.clearMap()`.
- **`Map.view()` inside `run_code`** — wrong. Use `map_control(action="view"|"export")` as a separate tool call after adding layers.

### Python-reserved-word collisions on EE methods
EE has logical operators that clash with Python keywords. The method name is **capitalized** to avoid the conflict — calling the lowercase keyword form is a `SyntaxError`:
- `image.gt(0.1).And(image.lt(0.27))` — capital `A`. `.and(...)` is a syntax error.
- `mask1.Or(mask2)` — capital `O`. `.or(...)` is a syntax error.
- `valid.Not()` — capital `N`. `.not()` is a syntax error.

### Imports / band names
- **Raw S2 bands `B4`, `B3`, `B2`** — wrong. geeViz renames bands. Use `red`, `green`, `blue`, `nir`, `swir1`, `swir2`.
- **`ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')` directly** — wrong for most use cases. Use `gil.superSimpleGetS2(area, startDate, endDate)` (handles cloud masking + renaming).
- **`ee.ImageCollection('LANDSAT/...')` directly** — wrong. Use `gil.getProcessedLandsatScenes(area, startYear, endYear, startJulian, endJulian)` (cloud masking, renaming, sensor harmonization).
- **Mixing S2 and Landsat viz params** — `vizParamsFalse10k`/`vizParamsTrue10k` are for S2 (0–10000). `vizParamsFalse`/`vizParamsTrue` (no `10k`) are for Landsat (0–1). Using `10k` on Landsat produces a black image.
- **Guessing band names** — always `inspect_asset` first. Names vary across datasets/versions (e.g. MapBiomas uses `classification_2000`, MODIS uses `LST_Day_1km`).
- **`.buffer(5000)`** — use `sal.simple_buffer(point, size=5000)` instead.

### Calling tools
- **Calling MCP tools inside `run_code`** — wrong. `search_datasets`, `search_geeviz`, `inspect_asset`, `map_control`, `export_image`, etc. are MCP tools — call them as separate tool calls. `search_datasets('LCMS')` inside `run_code` fails with `NameError`.

### Dataset-specific
- **MTBS:** band name changed 2023+. Always `.select([0], ['Severity'])`.
- **Annual NLCD:** use `projects/sat-io/open-datasets/USGS/ANNUAL_NLCD/LANDCOVER` (40 years). Band is `b1` — rename and set class properties.
- **Drought:** `GRIDMET/DROUGHT` for PDSI/SPI/EDDI, not `IDAHO_EPSCOR/GRIDMET`.

### Output rendering
- **Missing `title` on charts/thumbs/GIFs** — always include a specific title. Drives caption, download filename, and on-image overlay.
- **`fig.show()`** — never use in MCP. Opens a local browser, useless to the agent.
- **`scale` on `generate_*` functions** — does NOT speed them up. Output size is controlled by `dimensions` (pixel width). `scale` only affects EE computation resolution (blurriness). To speed up: reduce `dimensions`, reduce `max_frames`, or simplify geometry. Never pass `scale=5000` thinking it'll help.
- **GIF `fps`** — never set higher than 2 for `generate_gif`, `generate_map_chart_gif`, `generate_filmstrip`. Default is 2.
- **`.getInfo()` timeout** — 2-minute limit. Use coarser scale or smaller region if you hit it.

### Vector data (USFS)
- **EDW (USFS Enterprise Data Warehouse):** for fire perimeters, timber sales, trails, roads, wilderness areas, critical habitat, etc. — use EDW, not `search_datasets`:
  ```python
  from geeViz.edwLib import search_services, query_features
  service_url = search_services("fire perimeters")
  fc = query_features(service_url, geometry, where_clause)
  ```
  Returns `ee.FeatureCollection`.

### Simple spectral masks
For water, vegetation, snow/ice, bare ground, urban/impervious, clouds, shadows from optical imagery, use `gil.simpleMask(image, mask_type)`. Look up full docs with `search_geeviz(name="simpleMask")`. Input must be 0–1 reflectance with geeViz band names (Landsat works directly; for S2, divide by 10000 first).

### Describing visual content
- **Never describe an image you haven't viewed.** If the user asks "what do you see?" / "describe this", call `view_output(filename.png)` for raster or `map_control(action="preview")` for a map first. Without it, descriptions are fabricated.
- **Never use `gm.streetview_*` or `get_streetview`** — Street View imagery violates Google Maps Platform ToS. Tell the user it's not available.

### Thumbnails
- **Use `tl.generate_thumbs` for thumbnails**, not `tl.get_thumb_url` or `ee.Image.getThumbURL()`. The latter return bare EE tiles with no cartographic context.

### Reports
- **Reports are for geospatial analysis only** (see Reports section). Not a generic slideshow tool.
- **Ignoring stdout errors in a "successful" run** — `run_code` returns `success: true` if the script ran to completion, but individual operations inside (chart sections, thumb generation, report sections) may print errors and continue. Before describing a report or chart, scan stdout for `error:`, `Error:`, `Traceback`, `Exception`, `failed`. If found, tell the user the output is incomplete — never fabricate descriptions of content that didn't render.

---

## Critical signatures — look up with `search_geeviz(name="...")`

- `gil.getProcessedLandsatScenes(studyArea, startYear, endYear, startJulian, endJulian)` — Julian days required.
- `gil.superSimpleGetS2(studyArea, startDate, endDate)` — preferred for S2. Returns IC with geeViz band names. Values 0–10000.
- `cl.summarize_and_chart(ee_obj, geometry, ...)` — `date_format` controls x-axis labels (`"YYYY"`, `"YYYY-MM"`, `"YYYY-MM-dd"`). Default auto-detects. `feature_label` for per-feature subplots.
- `tl.generate_gif(col, geometry, date_format=...)` — match `date_format` to your data's temporal resolution.

---

## Tools (12)

| Tool | What it does |
|---|---|
| `search_geeviz` | Look up modules, functions, classes, dicts, variables, examples. `name=` for direct, `query=` for search, `module=` to list members, `module="examples"` for example scripts. Works on REPL modules too. |
| `inspect_asset` | Real band names, dtypes, and class properties for any EE asset. |
| `search_datasets` | Find EE datasets by keyword. |
| `env_info` | Versions, REPL namespace, project info. `action="reload"` hot-reloads modules. |
| `run_code` | Execute Python. Always pass `stream_stdout=True`. |
| `save_session` | Save run_code history as `.py` or `.ipynb`. |
| `map_control` | Actions: `view` (notebook) / `export` (chat HTML artifact) / `preview` (per-layer EE tile images) / `layers` / `layer_names` / `clear` / `test_layers`. `view` and `export` run `test_layers` first automatically. |
| `view_output` | Returns a saved raster image (PNG/GIF/JPEG/WebP) as an inline image you can see. Only call when explicitly asked. Does NOT work on HTML. |
| `manage_asset` | Delete, copy, move, create folder, update ACL. |
| `export_image` | Set up EE batch exports. In sandbox mode, `.start()` is blocked — the user runs them locally from the downloaded code. |
| `geeviz_search_places` | Google Places API wrapper. If a separate Google Maps MCP is loaded, prefer that one. |
| `get_streetview` | **Disabled — do not use.** Violates Google Maps Platform ToS. |
