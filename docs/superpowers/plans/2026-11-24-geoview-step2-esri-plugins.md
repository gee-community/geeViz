# geoView Step 2: Esri, GeoJSON and XYZ Plug-ins, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delta draws, queries, legends and charts ArcGIS services in the browser, the way the ArcGIS JS API does (without it); GeoJSON layers become queryable; time-enabled services play as timelapses; and a map with no Earth Engine layers reads elevation from USGS 3DEP.

**Architecture:** A small ArcGIS REST client (`js/esri/`) does the requests, geometry conversion, legends, renderers, feature fetching, identify and charts. One plug-in (`js/plugins/esri.js`) maps five new layer kinds to it: `esri.feature`, `esri.map`, `esri.tile`, `esri.image`, `esri.timelapse`. The plug-in contract gains its last two parts, `legend` and `chart`; the area charter sends Earth Engine jobs to Earth Engine and every other job to its plug-in, so a map with no Earth Engine layers charts without loading Earth Engine. geeViz's `Map.addEsri*` write one `Map.addEsriLayer(...)` call for Delta and fetch nothing in Python. XYZ tiles keep today's `tile` plug-in unchanged: an XYZ service has nothing to query, and its legend comes from the viz as now.

**Tech Stack:** Vanilla ES modules, Google Maps JS API (canvas tile overlays), ArcGIS REST API (JSON over fetch), node:test with recorded responses, pytest + Playwright (live, with `page.route` replays and real network).

**Spec:** `C:\RCR\georest\docs\superpowers\specs\2026-11-24-geoview-design.md`, release step 2: "Add the Esri, GeoJSON and XYZ plug-ins, table row by table row, each with offline tests on recorded responses and live tests; then renderers, time-enabled timelapse, and area charts from `computeHistograms` and `outStatistics`." Step 1's plan (`2026-11-24-geoview-step1-ee-optional.md`) built the registry this plan extends.

## Global Constraints

- Work in the geeViz repo (`C:\RCR\geeVizBuilder\geeViz`), branch `master` (the user's practice in step 1); stage explicit paths only, never `git add -A`.
- No ArcGIS JS API; Google Maps stays the map engine (spec non-goal). Emulate ArcGIS JS API behavior in our own code.
- Preserve each file's line endings (most Delta files are CRLF; `js/ui/layers.js` is mixed: edit it with the exact-string editor).
- US English; no em dashes and no decorative emoji in UI copy, docs or comments; never truncate outputs (no caps on what a result shows; a fetch cap is a draw limit and is said in the layer row).
- The original skin keeps esriLib's Python fetch, unchanged (spec: "Only the original skin ... keeps esriLib's Python fetch").
- A layer added with `token=` keeps today's esriLib path in this step: tokens must never reach the page (spec), and the `/proxy` that would hold them comes in step 3.
- A map with no Earth Engine layers never loads Earth Engine: not for drawing, query, legend, chart, timelapse or elevation.
- Query tolerance is Delta's: `POINT_TOLERANCE_PX = 8`, `LINE_TOLERANCE_PX = 5` (`js/engine/query.js`); polygons are hit when the click is inside.
- Recorded responses live in `geeView/delta/tests/fixtures/esri/`, written by `geeView/delta/tests/fixtures/esri/record.py` (real requests, saved as `<name>.json` with the request URL and params alongside). Tests never edit a fixture by hand.
- Live services used by the tests (all send CORS headers, checked 2026-11-24):
  - Dynamic map service: `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`
  - Cached tiles: `https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer`
  - Image service, time-enabled, classes: `https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_LCMS_AnnualChange_CONUS/ImageServer` (16 classes, values 1 to 16; `timeInfo` with no interval, so steps come from the catalog's `year`; `$<objectid>` raster references work)
  - Feature layers: `https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer/63` and `https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_States_Generalized_Boundaries/FeatureServer/0`
  - Elevation: `https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer` (`identify`, about 1 to 6 s)
- Run JS units with `node --test tests/*.test.mjs` from `geeView/delta`; Python units and live suites from the workspace root: `venv/Scripts/python.exe -m pytest geeViz/tests/test_delta_esri.py geeViz/tests/delta -q` (live needs the 8889 eeCreds proxy).
- Mutation-check every test that guards new behavior (break the code, see the test fail, restore).

## Review Focus

1. A service that answers HTTP 200 with `{"error": {...}}` (ArcGIS's way of failing), or that blocks cross-site requests: the layer row shows the service's own message, the map keeps working, and the Query tool shows a "Query failed" card for that layer only. Task 1 test (error body), Task 3 test (identify error card).
2. A feature layer over a dense area at a low zoom (thousands of features in view): the map stays responsive, the fetch stops at the cap, and the row says how many features are shown and that zooming in shows the rest. Task 5 test.
3. A request whose geometry is long enough to pass URL limits (an uploaded county outline for `computeHistograms` or `outStatistics`): it goes as a POST, not a failing GET. Task 1 test, Task 10 test.
4. A map with Esri layers and no Earth Engine layers, with Chart area on and auto charting: no `ee_api_js` request is made, and the Esri layers chart. Task 10 live test.
5. Pan and zoom while feature tiles or identify calls are in flight: a late answer for an old view neither draws on a reused tile canvas nor shows a stale query card. Task 5 test (canvas reuse), Task 3 test (stale token).

---

### Task 1: ArcGIS REST client

**Files:**
- Create: `geeView/delta/js/esri/rest.js`, `geeView/delta/tests/fixtures/esri/record.py`, fixtures `nfhl_info.json`, `nfhl_legend.json`, `topo_info.json`, `lcms_info.json`, `lcms_legend.json`, `lcms_catalog_years.json`, `mtbs63_info.json`, `states_info.json`, `error_body.json` (an invalid-layer query), `esri_geometries.json` (one of each Esri JSON geometry, from a real `f=json` query)
- Test: `geeView/delta/tests/esri_rest.test.mjs`

**Interfaces:**
- Produces:
  - `class EsriError extends Error` with `.code` (number) and `.details` (string[]); message is the service's `error.message` plus its details joined by "; ".
  - `esriRequest(url, params = {}, {fetch, signal, maxGet = 2000} = {}) -> Promise<object>`: adds `f=json` unless `params.f` is set; objects in params are JSON-encoded; GET when the full URL is at most `maxGet` characters, else POST with a form body; an HTTP error or an `{error}` body throws `EsriError`; a network failure that looks like CORS throws `EsriError` with message "This service does not allow requests from this page."
  - `serviceInfo(url, opts) -> Promise<object>`: `esriRequest(url)` cached per URL for the page's life.
  - `serviceKind(url, info) -> "esri.feature" | "esri.map" | "esri.tile" | "esri.image"`: a `.../FeatureServer/<n>` or `.../MapServer/<n>` URL is a feature layer; `ImageServer` is an image service (`esri.tile` only when `info.tileInfo` is Web Mercator, `info.singleFusedMapCache` or `cacheType`, and no rendering rule or time is asked: decided by the caller passing `{renderingRule, time}` as a third argument); a `MapServer` with `singleFusedMapCache` and a Web Mercator `tileInfo` (wkid 102100 or 3857) is `esri.tile`, else `esri.map`; a `FeatureServer` root becomes `<url>/0`.
  - `isWebMercator(sr) -> boolean` (wkid or latestWkid 102100 or 3857).
  - `toGeoJSON(esriGeometry) -> GeoJSON geometry | null`: point, multipoint, polyline (paths), polygon (rings: a clockwise ring starts a polygon, counterclockwise rings are its holes, as the Esri JSON spec says), envelope.
  - `toEsriPolygon(geojson) -> {rings, spatialReference: {wkid: 4326}}` for Polygon, MultiPolygon, Feature, FeatureCollection (all polygon parts in one geometry, outer rings clockwise).
  - `timeSteps(info, catalogYears = null) -> [{label, time: [startMs, endMs]}]`: from `timeInfo.timeExtent` and `timeInfo.defaultTimeInterval` plus `defaultTimeIntervalUnits` (esriTimeUnitsYears, Months, Weeks, Days, Hours); with no interval, from `catalogYears` (one step per year, Jan 1 to Dec 31 23:59:59.999 UTC); none when the service has no `timeInfo`.
  - `catalogYears(url, info, opts) -> Promise<number[] | null>`: for an image service with `timeInfo` and no interval, the distinct values of the first catalog field named `year` (else of `timeInfo.startTimeField`, as years), sorted, by `query` with `returnDistinctValues`.

- [ ] **Step 1: Record the fixtures.** Write `record.py` (stdlib `urllib` only; each fixture is `{"request": {"url", "params"}, "response": <json>}`) and run it: `venv/Scripts/python.exe geeViz/geeView/delta/tests/fixtures/esri/record.py`. Expected: the files above written, each `response` non-empty.
- [ ] **Step 2: Write the failing tests** in `esri_rest.test.mjs`, with a fake `fetch` that answers from fixtures:
  - `esriRequest` sends `f=json`, encodes an object param as JSON, and uses POST with a form body when the URL would pass `maxGet` (assert method and that the body holds the geometry).
  - `error_body.json` rejects with `EsriError`, `.code` 400, and the message containing the fixture's `error.message`.
  - a fetch that throws `TypeError("Failed to fetch")` rejects with the cross-site message.
  - `serviceKind`: NFHL is `esri.map`; World_Topo_Map is `esri.tile`; LCMS is `esri.image`; MTBS `/MapServer/63` and states `/FeatureServer/0` are `esri.feature`; `.../FeatureServer` becomes `/0`.
  - `toGeoJSON` on each geometry in `esri_geometries.json` gives the expected GeoJSON type; a polygon with one clockwise outer ring and one counterclockwise hole gives one Polygon with two rings; two clockwise rings give a MultiPolygon.
  - `toEsriPolygon` of a GeoJSON MultiPolygon gives rings whose outer rings are clockwise (signed area < 0 in lon/lat).
  - `timeSteps(lcms_info, [1985, 1986])` gives two steps labeled "1985" and "1986" with `time[0]` = `Date.UTC(1985,0,1)`; a `timeInfo` with `defaultTimeInterval: 1, defaultTimeIntervalUnits: "esriTimeUnitsYears"` and a 3-year extent gives 3 steps; no `timeInfo` gives `[]`.
- [ ] **Step 3: Run** `node --test tests/esri_rest.test.mjs`. Expected: FAIL (module missing).
- [ ] **Step 4: Implement** `js/esri/rest.js` with the signatures above.
- [ ] **Step 5: Run** `node --test tests/*.test.mjs`. Expected: all pass.
- [ ] **Step 6: Commit** `js/esri/rest.js`, the test, `record.py` and the fixtures: "Delta: ArcGIS REST client for the Esri plug-ins".

### Task 2: Esri plug-in drawing and service legends (map, tile, image)

**Files:**
- Create: `geeView/delta/js/plugins/esri.js`, `geeView/delta/js/esri/draw.js`, `geeView/delta/js/esri/legend.js`
- Modify: `js/plugins/index.js` (register), `js/engine/layers.js` (ctx gains `setLegend(rec, legend)`; `layerTypeOf` returns the kind for `esri.*`; the engine calls `plugin.legend(rec, ctx)` after `draw` when the plug-in has one and patches the result), `js/ui/legend.js` (`legendMarkup` and `swatchColors` for the two new legend types), `css/delta.css` (legend image rows and section titles)
- Test: `geeView/delta/tests/esri_draw.test.mjs`, `geeView/delta/tests/esri_legend.test.mjs`

**Interfaces:**
- Consumes: Task 1 `esriRequest`, `serviceInfo`, `serviceKind`, `isWebMercator`; layers.js ctx `tileOverlay(r, urlFor, extra)`, `tileBounds`, `setLoading`, `sync`, `fail`.
- Produces:
  - Plug-in contract, final form (document it in `js/plugins/index.js`): `{kinds, needsEE, start?, draw(rec, item, ctx), legend?(rec, ctx) -> Promise<legend|null>, query?(target, layer, point, qctx), chart?(layer, area, cctx) -> Promise<results[]>}`.
  - `esriPlugin` with `kinds: ["esri.feature", "esri.map", "esri.tile", "esri.image", "esri.timelapse"]`, `needsEE: false`. A layer's `item` is the service URL; its `viz` holds `esri` options: `{layers, renderingRule, mosaicRule, bandIds, time: [start, end] | null, where, outFields, bbox, maxFeatures, simplify, maxLayerMB}` (each optional).
  - `exportUrl(url, kind, esriOpts, bounds3857, size = 256) -> string` in `esri/draw.js`: MapServer `export` (`f=image`, `format=png32`, `transparent=true`, `layers`, `time`) or ImageServer `exportImage` (`f=image`, `format=jpgpng`, `renderingRule`, `mosaicRule`, `bandIds`, `time`, `interpolation=RSP_NearestNeighbor` when the service's legend is classes), with `bbox`, `bboxSR=3857`, `imageSR=3857`, `size=256,256`, `dpi=96`.
  - `tileUrl(url) -> (coord, zoom) => string`: `<url>/tile/{z}/{y}/{x}`.
  - `serviceLegend(url, info, esriOpts, opts) -> Promise<legend>`: from `<url>/legend` (with `renderingRule` for an image service). One sublayer: `{type: "images", title, items: [{label, src: "data:<contentType>;base64,<imageData>"}]}`; several: `{type: "sections", title, sections: [{title: layerName, items}]}`, sublayers outside the current `layers` choice left out. An image service legend whose labels are not numbers and that has `info.maxValues[0] - info.minValues[0] + 1` items gets `values: [min, ..., max]` in order (the LCMS case); numeric labels give their own values.
  - Legend types in `js/ui/legend.js`: `images` renders `<img class="lgimg" src>` plus label per item (`src` must start with `data:image/`; anything else is left out); `sections` renders each section's title then its items. `swatchColors` returns `{kind: "images", srcs: [first 4]}` for both.
- [ ] **Step 1: Write the failing tests.**
  - `esri_draw.test.mjs`: `exportUrl` for NFHL holds `/MapServer/export?`, `bboxSR=3857`, `size=256,256`, `transparent=true` and `layers=show:28` when given; for LCMS holds `/ImageServer/exportImage?` and `time=<start>,<end>` when given; `tileUrl` gives `.../tile/5/12/6` for `{x: 6, y: 12}` at zoom 5. The plug-in's `draw` for an `esri.map` layer calls `ctx.tileOverlay` and the overlay's URL function returns an `exportUrl` for the tile's bounds (fake ctx records the call).
  - `esri_legend.test.mjs`: `serviceLegend` on `nfhl_legend.json` gives `sections` with one section per sublayer and `data:image/png;base64,` sources; with `layers: "show:28"` only that sublayer remains; on `lcms_legend.json` gives 16 `images` items with `values` 1 to 16 and labels "Wind" to "Non-Processing Area Mask"; `legendMarkup` escapes labels and drops an item whose `src` is `javascript:...`.
- [ ] **Step 2: Run** `node --test tests/esri_draw.test.mjs tests/esri_legend.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** `esri/draw.js`, `esri/legend.js`, `plugins/esri.js` (`draw` for `esri.map`, `esri.tile`, `esri.image`; `esri.feature` arrives in Task 5), the registry entry, the ctx and engine changes, and the legend markup and CSS.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs`. Expected: all pass (plugins.test.mjs still finds every kind exactly once).
- [ ] **Step 5: Commit** "Delta: Esri map, tile and image services drawn in the browser, with service legends".

### Task 3: Identify for map, tile and image services

**Files:**
- Create: `geeView/delta/js/esri/identify.js`
- Modify: `js/plugins/esri.js` (`query`), `js/engine/layers.js` (`queryTarget` resolves `{type: kind, item: url, viz}` for `esri.*` kinds), `js/engine/query.js` (export `errorResult`; pass `qctx.view = {bounds, width, height}` from the map to plug-ins), fixtures `nfhl_identify.json`, `lcms_identify.json` (with `returnCatalogItems=true`), `topo_identify.json`
- Test: `geeView/delta/tests/esri_query.test.mjs`

**Interfaces:**
- Consumes: Task 1 `esriRequest`; Task 2 legend `values`; query.js `tableResults`, `imageResult`, `seriesResult`, `POINT_TOLERANCE_PX`.
- Produces:
  - `identifyMap(url, point, view, esriOpts, opts) -> Promise<results[]>`: `identify` with `geometry` (the point, wkid 4326), `geometryType=esriGeometryPoint`, `sr=4326`, `layers` (`visible:<ids>` from the layer's `show:` choice, else `visible`), `tolerance=POINT_TOLERANCE_PX`, `mapExtent` and `imageDisplay` (`<width>,<height>,96`) from `view`, `returnGeometry=false`, `time` when set. Results: one `tableResults` card per hit, meta "<sublayer name>: <display field value>"; none hit gives one card "No features here".
  - `identifyImage(url, point, esriOpts, legend, opts) -> Promise<results[]>`: `identify` with `returnPixelValues=true`, `returnCatalogItems` true only for a time-enabled service. A single value gives an `imageResult` whose band label is the class name and color from the legend `values`; "NoData" gives "No data". With catalog items and `properties.Values`, a `seriesResult` with x = the items' years (sorted), one series.
  - A tile service queries the MapServer behind the tiles (`identifyMap` on the service URL).
- [ ] **Step 1: Write the failing tests** (`esri_query.test.mjs`, fake fetch on the fixtures): NFHL identify request holds `tolerance=8`, `imageDisplay=800,600,96` for an 800 by 600 view and `layers=visible:28` for `show:28`; its results are `table` cards with the fixture's attribute names; LCMS identify gives a `series` result whose first x is the earliest catalog year and whose labels are class names; a service `{error}` gives one `errorResult` card ("Query failed") and does not reject; `queryPoint` with a token that goes stale before the identify answers resolves to `[]` and calls no `onResult`.
- [ ] **Step 2: Run** `node --test tests/esri_query.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** `esri/identify.js` and the plug-in `query`; thread `view` through `queryPoint`.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs`. Expected: all pass.
- [ ] **Step 5: Commit** "Delta: Query tool identifies ArcGIS map, tile and image services".

### Task 4: `Map.addEsriLayer` and geeViz's `addEsri*` for Delta

**Files:**
- Modify: `geeView/delta/js/api.js` (`addEsriLayer`), `geeView/delta/js/compat.js` (`MAP_METHODS` gains `"addEsriLayer"`), `geeView.py` (`addEsriImageService`, `addEsriMapService`, `addEsriFeatureService`, `addEsriService`, `addTimeLapse`, `_build_run_js`, `exportLayerJson`, `testLayers`)
- Test: `geeViz/tests/test_delta_esri.py` (new, no network), `geeView/delta/tests/api.test.mjs`, `geeViz/tests/delta/test_esri_layers.py` (new, live)

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces:
  - JS: `Map.addEsriLayer(url, viz, name, visible)`: kind = `viz.esriKind` when given, else `"esri.timelapse"` when `viz.timelapse`, else `"esri.map"` until the plug-in classifies it (the plug-in's `start` reads `serviceInfo` and patches `layer.kind` via `serviceKind` before drawing). Queryable; `chartable` when `viz.canAreaChart`.
  - Python, Delta skin: `addEsri*` record `{"_is_esri": True, "url", "esri": {...options}, "name", "visible", "viz"}` and fetch nothing. `_build_run_js` emits `try{Map.addEsriLayer(<url>,<viz>,<name>,<visible>);}catch(e){layerLoadErrorMessages.push(...)}`. Options: image `renderingRule`, `mosaicRule`, `bandIds`; map `layers`; feature `where`, `outFields`, `bbox` (list or "w,s,e,n"), `max_features` (to `maxFeatures`, default 2000 per view), `simplify` (`"auto"`, a number of meters, or False), `max_layer_mb` (to `maxLayerMB`); all: `time` (a year, an ISO date, a `(start, end)` pair, or `"all"` for a timelapse), `opacity`, `canAreaChart`, plus vector style keys in `viz_params` (`strokeColor`, `fillColor`, `fillOpacity`, `strokeWeight`) that override the service's renderer.
  - `Map.addTimeLapse(url_string, viz, name, visible)` with an ArcGIS URL records an Esri layer with `time="all"`.
  - Original skin, or `token=` given: today's esriLib path. When the skin changes to "original" after Esri layers were recorded, `_build_run_js` expands each `_is_esri` record through esriLib then (fetching at view time) and says so in a warning.
  - `testLayers` probes `<url>?f=json` for `_is_esri` records (as `_is_dynamic_esri`); `exportLayerJson` writes `{"esri": {"url", "kind", "options"}}` for them.
- [ ] **Step 1: Write the failing tests.**
  - `test_delta_esri.py`: on a Delta mapper with `urllib.request.urlopen` patched to raise, `addEsriMapService(NFHL, name="Flood")`, `addEsriImageService(LCMS, viz_params={"renderingRule": {"rasterFunction": "None"}}, time=2021)`, `addEsriFeatureService(MTBS63, where="year > 2020")` make no request and `_build_run_js()` contains three `Map.addEsriLayer(` calls with those URLs, `"renderingRule"`, `"where": "year > 2020"` and `"time"` as `[Date.UTC(2021,0,1) ms, end-of-2021 ms]`; with `token="x"` the esriLib function is called (patched) and the script holds no `"x"` from the Delta path; `setSkin("original")` after an add calls esriLib at build time; `addTimeLapse(LCMS)` gives `"timelapse": true` in the viz.
  - `api.test.mjs`: `addEsriLayer(LCMS, {timelapse: true})` makes a layer of kind `esri.timelapse` that starts off (like `timelapse`); `addEsriLayer(NFHL, {})` makes a queryable layer of kind `esri.map`.
  - `test_esri_layers.py` (live, real network): a Delta map of NFHL, World_Topo_Map and LCMS (time 2021) loads with no `ee_api_js` request; each row has no error and a legend (`images` or `sections`); the Query tool clicked over Fort Collins (-105.08, 40.58) gives a card for each layer, NFHL's `table` cards included; one `page.route` replay test answers NFHL `identify` with `error_body.json` and the NFHL card says "Query failed" while the LCMS card still arrives.
- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest geeViz/tests/test_delta_esri.py -q` and `node --test tests/api.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** the JS and Python changes.
- [ ] **Step 4: Run** the two unit suites, then `venv/Scripts/python.exe -m pytest geeViz/tests/delta/test_esri_layers.py -q`. Expected: all pass.
- [ ] **Step 5: Commit** "Delta: Map.addEsri* draw in the browser; Python fetches nothing".

### Task 5: Feature layers fetched for the view, and hit-test query (GeoJSON too)

**Files:**
- Create: `geeView/delta/js/esri/features.js`, `geeView/delta/js/engine/hittest.js`, fixtures `states_query_z4.json` (a tile query with `exceededTransferLimit`), `states_query_z4_page2.json`, `mtbs63_query.json`
- Modify: `js/engine/vectortiles.js` (`flatten` keeps `props` and `fid` per part; `createVectorTileOverlay` takes either `geojson` or `source: {partsFor(coord, zoom, signal) -> Promise<parts>}` and an optional `styleFor(part, zoom) -> style`; a canvas released or reused before its parts arrive is not drawn on), `js/plugins/esri.js` (`esri.feature` draw and query), `js/plugins/geojson.js` (`query`), `js/engine/layers.js` (`queryTarget` for `geojson` resolves `{type: "geojson", overlay}`; `NOT_QUERYABLE` loses `geoJSONVector`)
- Test: `geeView/delta/tests/esri_features.test.mjs`, `geeView/delta/tests/hittest.test.mjs`, live `geeViz/tests/delta/test_geojson_query.py`

**Interfaces:**
- Consumes: Task 1 `esriRequest`, `toGeoJSON`, `serviceInfo`; query.js `tableResults`, `POINT_TOLERANCE_PX`, `LINE_TOLERANCE_PX`.
- Produces:
  - `hitTest(parts, lngLat, zoom, {pointPx = 8, linePx = 5} = {}) -> part[]`: in Web Mercator pixels at `zoom`: a point within `pointPx` plus its marker radius, a line segment within `linePx`, a polygon containing the click (even-odd, holes excluded); one entry per feature (`fid`), topmost (last drawn) first.
  - `createFeatureSource(url, info, esriOpts, {fetch, onStatus}) -> {partsFor(coord, zoom, signal), loadedParts(), features(fids)}`: one `query` per map tile (envelope in 3857, `spatialRel=esriSpatialRelIntersects`, `outSR=4326`, `outFields` (default the display field and the renderer's fields), `where`, `maxAllowableOffset` = one pixel at the tile's zoom in degrees unless `simplify === false` or a number of meters, `geometryPrecision=6`, `f=geojson` when `info.supportedQueryFormats` lists geoJSON else `f=json` through `toGeoJSON`); pages with `resultOffset` while `exceededTransferLimit`, up to `maxFeatures` per tile, and stops fetching new tiles once the bytes received for the layer pass `maxLayerMB` (default 64) until cached tiles are dropped; tiles cached (least recently used, 512 tiles); nothing fetched outside the layer's `minScale`/`maxScale`. `onStatus({capped, shown, outOfScale})` lets the plug-in set the row's note: "Showing the first <n> features in view; zoom in for the rest." or "Zoom in to see this layer." (`layer.note`, shown under the row name as the error line is).
  - The `geojson` and `esri.feature` plug-ins' `query`: `hitTest` on the overlay's loaded parts, then `tableResults(layer, {features}, point, precision)`; `qctx.onVectors` gets the hit features as a FeatureCollection, as Earth Engine vectors do.
- [ ] **Step 1: Write the failing tests.**
  - `hittest.test.mjs`: a point 7 px away hits at `pointPx = 8` and misses 20 px away; a line 4 px away hits and 9 px misses; a click in a polygon's hole misses; two overlapping polygons give the later-drawn first; two parts of one MultiPolygon give one hit.
  - `esri_features.test.mjs`: the first tile query holds `maxAllowableOffset` near 360/(256·2^z) degrees, `outSR=4326` and `geometryPrecision=6`; an `exceededTransferLimit` answer makes a second request with `resultOffset` equal to the first page's count; with `maxFeatures: 3` paging stops at 3 and `onStatus` reports `capped: true, shown: 3`; with `maxLayerMB` below one fixture's size the next tile makes no request and `onStatus` reports `capped: true`; at a zoom outside `minScale` no request is made and `onStatus` reports `outOfScale: true`; a canvas released before its query resolves is not drawn on (fake canvas counts draw calls).
  - `test_geojson_query.py` (live): a Delta map with a GeoJSON point, line and polygon (no Earth Engine): the Query tool clicked 5 px from the point, 3 px from the line and inside the polygon gives one attribute table each with the feature's properties; no `ee_api_js` request.
- [ ] **Step 2: Run** `node --test tests/hittest.test.mjs tests/esri_features.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** `hittest.js`, `features.js`, the overlay `source` mode, both plug-in `query`s, and `layer.note` in the row (`js/ui/layers.js`, styled as the error line in muted color).
- [ ] **Step 4: Run** `node --test tests/*.test.mjs`, then `venv/Scripts/python.exe -m pytest geeViz/tests/delta/test_geojson_query.py geeViz/tests/delta/test_esri_layers.py -q`. Expected: all pass; add to `test_esri_layers.py` a live check that MTBS `/63` draws over Colorado and a Query click on the Cameron Peak fire returns its `fire_name`.
- [ ] **Step 5: Commit** "Delta: feature layers fetched for the view; GeoJSON and feature layers answer the Query tool".

### Task 6: Symbols and the simple, unique value and class breaks renderers, with visual variables

**Files:**
- Create: `geeView/delta/js/esri/symbols.js`, `geeView/delta/js/esri/renderers.js`, fixtures `drawinginfo_simple.json`, `drawinginfo_unique.json`, `drawinginfo_classbreaks.json`, `drawinginfo_visualvars.json` (from real services found by `record.py` through portal search; the `drawingInfo` of MTBS `/63` and states `/0` are two of them)
- Modify: `js/plugins/esri.js` (feature draw uses the renderer; `legend` from it), `js/engine/vectortiles.js` (draw a part with `styleFor`'s symbol through `symbols.js`), `js/ui/legend.js` (`symbols` legend type: items `{label, glyph}` drawn as the existing SVG glyphs, ramps for visual variables)
- Test: `geeView/delta/tests/renderers.test.mjs`

**Interfaces:**
- Consumes: Task 5 overlay `styleFor`; legend.js glyph SVG.
- Produces:
  - `drawSymbol(ctx2d, symbol, part, px)` in `symbols.js` for `esriSMS` (circle, square, diamond, cross, x, triangle; size in points to px as 4/3), `esriSLS` (solid, dash, dot, dashdot, longdash, shortdash, null), `esriSFS` (solid, null, horizontal, vertical, cross, diagonalcross, forwarddiagonal, backwarddiagonal hatches as canvas patterns), `esriPMS` and `esriPFS` (picture from `imageData`, loaded once per symbol). Esri colors `[r, g, b, a]` with `a` 0 to 255.
  - `rendererFor(drawingInfo, vizOverride) -> {styleFor(props, zoom) -> symbol, legend(title) -> legend, fields: string[], type}`: simple; uniqueValue (`field1` to `field3` joined by `fieldDelimiter`, `uniqueValueInfos`, `defaultSymbol` and `defaultLabel`); classBreaks (`field`, `normalizationField` / `normalizationType` esriNormalizeByField, esriNormalizeByLog, esriNormalizeByPercentOfTotal with `normalizationTotal`, `minValue`, `classBreakInfos` with `classMaxValue`); `visualVariables` colorInfo (interpolated `stops`), sizeInfo (`stops`, or `minDataValue`/`maxDataValue` with `minSize`/`maxSize`), transparencyInfo, rotationInfo (`rotationType` geographic or arithmetic). geeViz style keys in `vizOverride` replace the renderer with a simple one.
  - Legend type `symbols`: `{type: "symbols", title, items: [{label, glyph}], ramps: [{label, palette, labels}]}`; a simple renderer with one item shows inline in the row, as vector symbols do now (`isSymbolLegend` true for it).
- [ ] **Step 1: Write the failing tests** (`renderers.test.mjs`): unique value picks the info whose `value` equals the feature's field (and the default for others, labeled `defaultLabel`); class breaks puts 10 in the break with `classMaxValue` 10 and 10.5 in the next, and normalizes by field before; colorInfo halfway between two stops gives the mid color; sizeInfo at `minDataValue` gives `minSize`; a renderer legend has one item per info with its label and a glyph whose fill and stroke equal the symbol's colors; a viz override `{strokeColor: "ff0000"}` gives a simple renderer with that stroke; each fixture `drawingInfo` builds without throwing and every legend item has a label.
- [ ] **Step 2: Run** `node --test tests/renderers.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** `symbols.js`, `renderers.js`, and the wiring.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs`, then `venv/Scripts/python.exe -m pytest geeViz/tests/delta/test_esri_layers.py geeViz/tests/delta/test_vector_legend.py -q`. Expected: all pass.
- [ ] **Step 5: Commit** "Delta: ArcGIS renderers and symbols for feature layers, with their legends".

### Task 7: Heatmap, dot density, pie chart, and renderers we do not know

**Files:**
- Create: `geeView/delta/js/esri/surfaces.js`, fixtures `drawinginfo_heatmap.json`, `drawinginfo_dotdensity.json`, `drawinginfo_piechart.json` (real, found by `record.py`; if a type cannot be found on a public service, the fixture is the ArcGIS REST API documentation's example and its file says so)
- Modify: `js/esri/renderers.js` (dispatch), `js/engine/vectortiles.js` (a renderer may draw a whole tile: `drawTile(ctx2d, parts, tile)`)
- Test: `geeView/delta/tests/surfaces.test.mjs`

**Interfaces:**
- Consumes: Task 6 `rendererFor`, legend `symbols` and ramps.
- Produces:
  - heatmap: per tile, a kernel density grid from the points in the tile plus `blurRadius` px around it (Gaussian, sigma = `blurRadius`/3; weighted by `field` when set), colored by `colorStops` (`ratio` of the intensity between `minPixelIntensity` and `maxPixelIntensity`); neighbors' points are fetched with the tile (the source queries the tile envelope grown by `blurRadius` px). Legend: a ramp labeled "Low" and "High".
  - dotDensity: per polygon and per `attributes` entry, `floor(value / dotValueAt(zoom))` dots of `dotSize` px, placed by rejection sampling in the polygon with a generator seeded by `fid` and attribute index (the same dots on every redraw and tile); `dotValueAt(zoom) = dotValue * (scaleAt(zoom) / referenceScale)^2` when `referenceScale` is set, else `dotValue`. Legend: one dot glyph per attribute with its label, and "1 dot = <n>" for the current zoom.
  - pieChart: a pie of `size` px at each polygon's interior point (the largest ring's centroid, moved inside when it falls outside) or each point, one slice per `attributes` value (`othersCategory` when its share is below `threshold`), `holePercentage` for a donut, `outline`. Legend: one swatch per attribute.
  - An unknown `renderer.type`: draws with `defaultSymbol` (or the geometry's default symbol) and its legend says "Drawn with a default symbol: <type> renderers are not supported."
- [ ] **Step 1: Write the failing tests** (`surfaces.test.mjs`): `dotValueAt` doubles when the scale doubles twice over (zoom out by one level gives 4 times); the dot generator gives the same points for the same seed and none outside the polygon (100 draws); a polygon with value 1000 and dotValue 100 gets 10 dots; a heatmap grid peaks at the point's pixel and its color at `ratio` 1 is the last stop; a pie with values 3 and 1 gives slices of 270 and 90 degrees; `rendererFor({renderer: {type: "flowRenderer"}})` gives the default-symbol legend note; each fixture builds.
- [ ] **Step 2: Run** `node --test tests/surfaces.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** `surfaces.js` and the dispatch.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs`. Expected: all pass.
- [ ] **Step 5: Commit** "Delta: heatmap, dot density and pie chart renderers".

### Task 8: Time-enabled services as timelapses

**Files:**
- Create: `geeView/delta/js/esri/timelapse.js`
- Modify: `js/plugins/esri.js` (`start` for `esri.timelapse`: `ctx.addTimelapse(layer, esriFrameLoader)`), `js/engine/layers.js` (`addTimelapse(layer, loader)` passes the loader to `createTimelapse`; `setFrameUrl` accepts a URL template string or a `(coord, zoom) => url` function), `js/util.js` (`isTimelapse(layer)`: kind `timelapse` or `esri.timelapse`), and every `kind === "timelapse"` check (`api.js`, `layers.js`, `timelapse.js`, `ui/layers.js`, `ui/timelapse.js`) through `isTimelapse`
- Test: `geeView/delta/tests/esri_time.test.mjs`, live `geeViz/tests/delta/test_esri_time.py`

**Interfaces:**
- Consumes: Task 1 `timeSteps`, `catalogYears`; Task 2 `exportUrl`, `serviceLegend`; Task 3 `identifyImage`; timelapse.js loader contract `{prepare(), years(), frame(i)}` and `queryTarget`.
- Produces: `esriFrameLoader(engine, layer) -> {prepare() -> Promise<{legend}>, years() -> Promise<string[]>, frame(i) -> Promise<(coord, zoom) => url>, queryTarget() -> Promise<{type: "esri.image" | "esri.map", item, viz}>}`. A service with no `timeInfo` fails the layer: "<name> is not time-enabled, so it cannot play as a timelapse."
- [ ] **Step 1: Write the failing tests** (`esri_time.test.mjs`): the loader on `lcms_info.json` and `lcms_catalog_years.json` gives years "1985" to the last catalog year; `frame(0)`'s URL for a tile holds `time=<Date.UTC(1985,0,1)>,<end of 1985>`; a service without `timeInfo` rejects with the message above; `isTimelapse` is true for both kinds and the existing `timelapse.test.mjs` still passes.
- [ ] **Step 2: Run** `node --test tests/esri_time.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** the loader, the engine hooks and the `isTimelapse` sweep.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs`, then the live `test_esri_time.py`: `Map.addTimeLapse(LCMS)` with no Earth Engine layers turns on, loads its frames (play and step work as for Earth Engine timelapses), shows the 16-class legend, and a Query click gives the values over time; and `geeViz/tests/delta/test_timelapse.py`. Expected: all pass, no `ee_api_js` request in the Esri test.
- [ ] **Step 5: Commit** "Delta: time-enabled ArcGIS services play as timelapses".

### Task 9: Elevation without Earth Engine

**Files:**
- Modify: `geeView/delta/js/engine/maps.js` (`elevation3DEP`, and `elevationAt` and the mousemove throttle use it when Earth Engine is not ready)
- Test: `geeView/delta/tests/elevation.test.mjs`

**Interfaces:**
- Produces: `ELEVATION_3DEP_URL = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"`; `elevation3DEP(lng, lat, {fetch}) -> Promise<number | null>` (`identify` with the point, `returnGeometry=false`, `returnCatalogItems=false`; `"NoData"` or any failure gives `null`; meters rounded to the nearest meter). With Earth Engine ready, GLO-30 as now (global); without it, 3DEP (the United States; elsewhere the readout stays "-").
- [ ] **Step 1: Write the failing tests:** `elevation3DEP` on a recorded identify fixture (`3dep_identify.json`, Fort Collins) gives the fixture's value rounded; `"NoData"` gives null; a rejected fetch gives null.
- [ ] **Step 2: Run** `node --test tests/elevation.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** in `maps.js`.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs`; add to `test_esri_layers.py` a live check that moving the mouse over Colorado on the no-Earth-Engine map shows a number in the status bar's elevation within 15 s. Expected: all pass.
- [ ] **Step 5: Commit** "Delta: elevation from USGS 3DEP when a map has no Earth Engine".

### Task 10: Area charts from computeHistograms and outStatistics

**Files:**
- Create: `geeView/delta/js/esri/charts.js`, fixtures `lcms_histograms_2021.json`, `lcms_transition_2010_2021.json` (the `Arithmetic` rendering rule on two catalog items), `mtbs63_outstatistics.json`
- Modify: `js/engine/areasources.js` (every area also carries `geojson`: the drawn rings, the view's bounds, or the upload's features; Select areas keep Earth Engine only), `js/engine/areachart.js` (jobs split by plug-in: `needsEE` jobs as now; others call `pluginFor(kind).chart(layer, area, cctx)`; `ready()` is awaited only when an Earth Engine job exists; `keyOf` hashes `JSON.stringify(area.geojson)` when there is no Earth Engine job), `js/main.js` (charter and sources pass `geojson`), `js/plugins/esri.js` (`chart`)
- Test: `geeView/delta/tests/esri_charts.test.mjs`, `geeView/delta/tests/areachart.test.mjs`, live `geeViz/tests/delta/test_esri_charts.py`

**Interfaces:**
- Consumes: Task 1 `esriRequest`, `toEsriPolygon`, `timeSteps`, `catalogYears`; Task 2 legend `values`; areachart.js `lineResult`, `sankeyResult`, `areaFormatFor`; sankey.js `buildSankeyFromHistogram` (read its decode of transition values before building its input).
- Produces:
  - `imageChart(layer, area, cctx) -> Promise<results[]>`: `computeHistograms` with the area as an Esri polygon (POST when long), `pixelSize` `{x: s, y: s, spatialReference: info.spatialReference}` with `s = max(info.pixelSizeX, metersPerPixel at the current zoom)`, `renderingRule` and `mosaicRule` as drawn. Counts become an Earth Engine-shaped `entry` (`raw` keyed as `frequencyHistogram` output, `objInfo.classInfo` from the legend's values, names and colors, `isHistogram: true`, `scale` = the ground pixel size: `s * cos(latitude of the area's center)` for Web Mercator, else `s`) so `lineResult` formats it like an Earth Engine chart (units, percentages, colors). A class map is a class chart; a continuous one a histogram. With time (a timelapse, or `time: "all"`), one histogram per time step as a chart over time; for a class map, a Sankey between the chart periods (Delta's period editor), its transitions from one `computeHistograms` per period pair with rendering rule `Arithmetic(Arithmetic($a, K, times), $b, plus)` (`K = maxValue + 1`, `$a` and `$b` the catalog item ids for the two years), fed to `sankeyResult`.
  - `featureChart(layer, area, cctx) -> Promise<results[]>`: `query` with the area, `spatialRel=esriSpatialRelIntersects`, `groupByFieldsForStatistics` = the renderer's field (or `viz.chartField`), `outStatistics` count (or `viz.chartStatistic` "sum" of `viz.chartValueField`), as a bar chart with the renderer's class colors; no renderer field and no `chartField` gives one bar, the feature count. A dynamic map service charts each visible sublayer that has a unique value or class breaks renderer.
- [ ] **Step 1: Write the failing tests.**
  - `esri_charts.test.mjs`: the LCMS fixture histogram gives a chart whose columns are class names from the legend (no "0" class), whose colors are the legend colors, and whose hectares equal counts times `scale^2 / 10000`; a long area polygon goes as POST; the transition fixture gives Sankey links whose from-to counts match `floor(v / K)` and `v % K`; the outStatistics fixture gives one bar per group value with the renderer's colors.
  - `areachart.test.mjs`: a store with one `esri.image` layer and `chartArea` called with a geometry thunk that throws: `ready` is never called, the thunk is never called, and the plug-in `chart` gets `area.geojson`.
  - `test_esri_charts.py` (live): no-Earth-Engine map with LCMS (`canAreaChart`) and MTBS `/63`; Chart area on, draw a square near Fort Collins: a class chart and a feature count chart appear, and no `ee_api_js` request is made; with `addTimeLapse(LCMS, {"canAreaChart": True})` the chart is over time and a Sankey appears for the default periods.
- [ ] **Step 2: Run** `node --test tests/esri_charts.test.mjs tests/areachart.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** `esri/charts.js`, the charter split and the area `geojson`.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs`, then `venv/Scripts/python.exe -m pytest geeViz/tests/delta/test_esri_charts.py geeViz/tests/delta/test_chart_area.py -q`. Expected: all pass.
- [ ] **Step 5: Commit** "Delta: area charts for ArcGIS image and feature services".

### Task 11: Example, release notes, full suites

**Files:**
- Create: `examples/geoViewEsriExample.py` (FEMA NFHL, LCMS as a timelapse with charting, MTBS fires, a GeoJSON layer, no Earth Engine layers; a second map adding SRTM to show both together)
- Modify: `release-notes.md` (2026.11.2 Delta bullets: Esri services drawn, queried, legended and charted in the browser; renderers; time-enabled timelapses; GeoJSON query; 3DEP elevation; `Map.addEsri*` fetch nothing in Python on Delta)
- Test: none new.

- [ ] **Step 1: Run** the example with the venv python and open both maps. Expected: every layer draws with a legend; Query and Chart area answer on the Esri layers.
- [ ] **Step 2: Run** `node --test tests/*.test.mjs` (from `geeView/delta`), `venv/Scripts/python.exe -m pytest geeViz/tests/ geeViz/fsInsights/tests/ -q -m "not live"` and `venv/Scripts/python.exe -m pytest geeViz/tests/delta -q` (from the workspace root, output to a file). Expected: all pass (the known flaky `test_shell::test_real_drag_released_over_the_map` reruns clean on its own).
- [ ] **Step 3: Commit** the example and release notes: "Delta: Esri plug-ins example and release notes".

## Left to step 3

The JSON map document (and with it the `xyz` name for today's `tile` kind and GeoJSON by URL), the move to `georest.view`, georest's `Map`, the `/proxy` that holds tokens (until then a `token=` layer keeps the Python fetch), and `addSelectLayer` for GeoJSON and feature layers.
