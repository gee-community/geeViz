# Delta Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Delta, a second geeViz map viewer selected with `Map.setSkin("delta")`, that runs every script the original viewer runs, with the approved look, and with Earth Engine charting ported from `outputLib/charts.py`.

**Architecture:** A page `geeView/delta.html` beside the original `index.html` loads CDN libraries, the Earth Engine JS client, a classic `compat.js` that defines every global the unchanged `runGeeViz.js` calls, then ES modules split into state, engine (EE and Google Maps, no DOM) and UI (templates and CSS tokens, no EE). Python only gains `setSkin` and picks the page.

**Tech Stack:** Vanilla ES modules, Bootstrap 5.3.3 (CSS only), Tabler Icons webfont 3.19.0, SortableJS 1.15.2, d3 7.9.0, d3-sankey 0.12.3, Plotly 2.27.0, Google Maps JS API (key and `libraries=places,geometry`), `earthengine-api@0.1.384` browser build; Node 24 `node --test` for pure-JS units; pytest + Playwright (Chromium) for browser and live Earth Engine tests.

**Spec:** `docs/superpowers/specs/2026-11-18-delta-viewer-design.md` (mockup: `docs/superpowers/specs/2026-11-18-delta-mockup.html`). Read both before any task.

## Global Constraints

- The original viewer is frozen: no edits to `geeView/index.html`, `geeView/src/**`, or the `lcms-viewer` repo.
- `runGeeViz.js` and `geeView._build_run_js` are not changed for Delta. Both skins receive byte-identical run scripts.
- Port sources: Earth Engine charting and Sankey from `geeViz/outputLib/charts.py`; map behavior from the lcms-viewer working tree at `C:\RCR\geeVizBuilder\lcms-viewer\src` (it is the unminified source of the bundled `lcms-viewer.min.js`, including its LOCAL PATCH blocks). Each ported function carries a comment `// port of <file> <function>`.
- No `getInfo()` in the browser; `evaluate()` only. One `reduceRegion` per layer per area (stacked bands). `bestEffort: true`, `maxPixels: 1e13`, `tileScale: 4`; `crsTransform` wins over `scale`.
- Chart-area inputs: layer's own crs/scale/transform, else `EPSG:5070`, transform `[30,0,-2361915.0,0,-30,3177735.0]`, coarsened 2x per zoom level below 11, at most 64x, honoring `minZoomSpecifiedScale`. `sankeyMinPercentage` default 0.5.
- Markup only in `<template>` elements or builder functions that emit markup without inline styles; all color, type and spacing through tokens in `css/tokens.css`. Token values are the mockup's `:root` blocks verbatim.
- CDN URLs with exact versions (Tech Stack). No bundler, no npm runtime dependencies.
- US English; no em dashes; no decorative emoji in UI copy.
- `window.__delta = {store, api, engine}` is exposed for tests.
- Repo rules: stage explicit paths only (never `git add -A`); run geeViz Python tests from `C:\RCR\geeVizBuilder` (`python -m pytest geeViz/tests/...`); mutation-check every test that guards a port (break the code, see it fail, restore).

## Review Focus

- A script that adds the same layer name twice, or 40+ layers: both rows appear, order matches the original, z-order follows the list. Test in Task 5 (`test_duplicate_names_and_many_layers`).
- A timelapse toggled off while its frames are still loading: the choice is recorded and applied when loading finishes (the original's `timelapse-toggle.js` behavior). Test in Task 6 (`toggle during load`).
- A Chart-area polygon over a region with no data for some years: missing labels chart as gaps, never as zero, and never shift later years. Test in Task 8 (`parseThematic keeps missing labels as null`).
- Query or chart results that arrive after the user clicked elsewhere: discarded, not rendered. Test in Task 7 (`stale query results are dropped`) and Task 9 (`stale chart results are dropped`).
- A layer name containing quotes, `<`, or `</script>`: rendered as text, never markup. Test in Task 5 (`names render as text`).

## File Structure

```
geeViz/geeView.py                         + setSkin(), skin-aware view/export_html/testView
geeViz/geeView/delta.html                 page shell
geeViz/geeView/delta/css/tokens.css       light, dark, system tokens
geeViz/geeView/delta/css/delta.css        components
geeViz/geeView/delta/js/compat.js         classic script: runGeeViz globals, $ shim
geeViz/geeView/delta/js/main.js           boot: store, map, ee init, ui, runGeeViz()
geeViz/geeView/delta/js/state.js          store
geeViz/geeView/delta/js/api.js            Map contract
geeViz/geeView/delta/js/util.js           escapeText, units, debounce, request tokens
geeViz/geeView/delta/js/engine/ee.js      EE auth and init (port eeInit)
geeViz/geeView/delta/js/engine/maps.js    Google map, basemaps, view history, Street View, search
geeViz/geeView/delta/js/engine/viz.js     viz preparation and legends (port autoViz paths)
geeViz/geeView/delta/js/engine/layers.js  all layer types, z-order, opacity
geeViz/geeView/delta/js/engine/timelapse.js
geeViz/geeView/delta/js/engine/query.js
geeViz/geeView/delta/js/engine/charts.js  pure + EE ports of charts.py
geeViz/geeView/delta/js/engine/sankey.js
geeViz/geeView/delta/js/engine/measure.js
geeViz/geeView/delta/js/engine/wind.js    adapter that runs the wind particle renderer
geeViz/geeView/delta/js/ui/shell.js       panes, resize, hamburger, theme, phone sheets, SV hide
geeViz/geeView/delta/js/ui/layers.js      layer rows, legend, opacity fit, reorder
geeViz/geeView/delta/js/ui/timelapse.js   timelapse block, map year, phone player
geeViz/geeView/delta/js/ui/tools.js       tool strip, units, tool options
geeViz/geeView/delta/js/ui/output.js      result cards, chips, actions
geeViz/geeView/delta/js/ui/status.js      status bar, loading line
geeViz/geeView/delta/js/charts/plotly.js  line/bar/stacked charts
geeViz/geeView/delta/js/charts/sankey.js  d3 Sankey (port D3_SANKEY_TEMPLATE)
geeViz/geeView/delta/tests/*.test.mjs     node --test units
geeViz/tests/test_delta_skin.py           Python side
geeViz/tests/delta/conftest.py            Playwright + live map fixtures
geeViz/tests/delta/make_fixtures.py       records charts.py outputs to JSON
geeViz/tests/delta/fixtures/*.json
geeViz/tests/delta/test_*.py              browser and live tests per task
setup.py (geeVizBuilder root)             package_data for geeView/delta.html and geeView/delta/**
```

Test commands used throughout:
- Units: `node --test geeViz/geeView/delta/tests/` (from `C:\RCR\geeVizBuilder`)
- Python: `python -m pytest geeViz/tests/test_delta_skin.py -q`
- Browser/live: `python -m pytest geeViz/tests/delta -q -m "not live"` and `-m live` (live needs Earth Engine credentials; the conftest skips with a clear reason when none are available)

---

### Task 1: Python skin selection and the page shell

**Files:**
- Modify: `geeViz/geeView.py` (mapper `__init__`, new `setSkin`, `view`, `export_html`, `testView`; module-level `template`)
- Create: `geeViz/geeView/delta.html`, `geeViz/geeView/delta/js/compat.js` (stub: defines `window.__deltaCompat = true`), `geeViz/geeView/delta/js/main.js` (stub: logs "delta boot")
- Modify: `C:\RCR\geeVizBuilder\setup.py` package_data
- Test: `geeViz/tests/test_delta_skin.py`

**Interfaces:**
- Produces: `Map.setSkin(name: str) -> None`; `Map.skin: str`; module constants `SKINS = ("original", "delta")`, `delta_template` path; default skin from env `GEEVIZ_SKIN` if it names a valid skin, else `"original"`. `view()`, `export_html()`, `testView()` read `self.skin` to pick `index.html` or `delta.html`; everything else (run JS, token, auth bootstrap, max_bytes) unchanged.
- Page contract for later tasks: `delta.html` loads, in order: Google Maps (`libraries=places,geometry`, same key line as `index.html` so export's key rewrite regex still matches), EE client 0.1.384 (same URL and integrity as `index.html`), Plotly 2.27.0, d3 7.9.0, d3-sankey 0.12.3, SortableJS 1.15.2, Bootstrap 5.3.3 CSS, Tabler Icons 3.19.0 CSS, Google Fonts (Barlow, Barlow Semi Condensed, JetBrains Mono), `./delta/css/tokens.css`, `./delta/css/delta.css`, `./delta/js/compat.js`, `./src/gee/gee-run/runGeeViz.js` (the exact tag string `index.html` uses, so export_html's replace matches), then `<script type="module" src="./delta/js/main.js">`. Mount points: `#map`, `#pane-left`, `#pane-right`, `#status`, `#mtop`, `#mtabs`, and a `<template>` container `#tpl`.

- [ ] **Step 1: Write failing tests** in `test_delta_skin.py`:
  - `test_default_skin_is_original` (no env) asserts `Map.skin == "original"`.
  - `test_env_selects_delta` sets `GEEVIZ_SKIN=delta` on a fresh mapper (`gv.mapper()`) and asserts `"delta"`; `GEEVIZ_SKIN=bogus` gives `"original"`.
  - `test_setSkin_rejects_unknown` asserts `ValueError` whose message contains `"original"` and `"delta"`.
  - `test_export_html_uses_delta_page`: `setSkin("delta")`, add `ee.Image(1)`, `export_html(tmp)`; the file contains `delta/js/main.js` under `asset_base` and the same `runGeeViz` inline script as an `original` export of the same map (compare the text between `<script>` holding `function runGeeViz(` and its `</script>`).
  - `test_run_js_identical_across_skins`: `_build_run_js()` output equal for both skins.
  - `test_delta_page_tags_match_original`: the EE client tag, Maps key line and runGeeViz tag strings in `delta.html` are byte-equal to those in `index.html`.
- [ ] **Step 2:** Run `python -m pytest geeViz/tests/test_delta_skin.py -q`; expect failures (`setSkin` missing).
- [ ] **Step 3:** Implement `setSkin`, the env default, and template selection; write `delta.html` and the two stubs.
- [ ] **Step 4:** Tests pass; also run `python -m pytest geeViz/tests/ -q -k "view or export"` to confirm no regression in the original path.
- [ ] **Step 5:** Commit `geeView.py`, `geeView/delta.html`, `geeView/delta/js/compat.js`, `geeView/delta/js/main.js`, `tests/test_delta_skin.py` (geeViz repo) and `setup.py` (geeVizBuilder repo, separate commit).

### Task 2: Store, Map contract and compat globals

**Files:**
- Create: `delta/js/state.js`, `delta/js/api.js`, `delta/js/util.js`; replace stub `delta/js/compat.js`
- Test: `delta/tests/state.test.mjs`, `delta/tests/api.test.mjs`, `delta/tests/contract.test.mjs`, `delta/tests/util.test.mjs`

**Interfaces:**
- Produces `createStore(initial) -> {get(): State, set(patch: object, reason: string): void, update(fn: (State)=>State, reason): void, on(event: string, fn): () => void}`; events: `"change"` with `(state, reason)`, plus `"change:<key>"` per top-level key changed.
- State shape (top-level keys): `layers` (array of Layer), `order` (layer ids, top first), `tool` (`null|"distance"|"area"|"query"|"chart"`), `units` (`"metric"|"imperial"`), `showAs` (`"area"|"pct"`), `areaFrom` (`"draw"|"view"|"upload"|"select"`), `results` (array of Result), `notices` (array of strings), `theme` (`"system"|"light"|"dark"`), `panes` (`{left:{visible:boolean,width:number|null}, right:{width:number|null}}`), `query` (`{crs,scale,transform,precision,dateFormat,boxColor,windowMode}`), `chartSettings` (`{yLabelMaxLength,yLabelBreakLength,yLabelMaxLines,yLabelFontSize}`), `canReorder` (boolean), `title` (string|null), `turnOffLayersWhenTimeLapseIsOn` (boolean).
- Layer: `{id, name, kind: "ee"|"geojson"|"tile"|"dynamic"|"timelapse"|"select"|"areaChartOnly", item, viz, visible, opacity, legendOpen, pinned, loading, error, legend, timelapse, chartable, queryable}`; `pinned` true for timelapse, geeVector, geoJSONVector, dynamicMapService, and when `canReorder` is false.
- `createMapApi(store, engine) -> MapApi`. MapApi implements every method name on the original `mp` object in `lcms-viewer/src/js/4map-manager.js` (`addLayer` through `hideSpinner`, plus the `turnOffLayersWhenTimeLapseIsOn` property). Methods Python can emit write to the store and call the engine; JS-only methods Python never emits (`addExport`, `addPlot`, `addFeatureView`, `addREST` called directly, `addMBSankey`) push a notice `"<name> is not available in Delta yet. Use Map.setSkin(\"original\") for this map."`.
- compat.js (classic script, loaded before runGeeViz.js) defines on `window`: `Map` (a queue proxy recording calls until `main.js` installs the real MapApi, then replays them in order), `map` (proxy whose `setZoom` etc. forward once the Google map exists), `areaChart` (`addLayer`, `addSerializedLayer`, `populateChartLayerSelect`), `synchronousCenterObject`, `showMessage(title, html)`, `staticTemplates = {loadingModal: {geeViz: ""}}`, `mode = "geeViz"`, `queryWindowMode`, `yLabelMaxLength`, `yLabelBreakLength`, `yLabelMaxLines`, `yLabelFontSize`, `urlParams` (parsed from the query string, preserving any values export_html's bootstrap sets), `authProxyAPIURL` declared with top-level `let` so the generator's reassignment works, and `$` supporting only `$('#close-modal-button').click()` (closes the loading notice); any other selector pushes a notice.
- util.js: `escapeText(s) -> string`, `formatLength(meters, units) -> string`, `formatArea(m2, units, showAs, totalM2) -> string`, `requestToken() -> {id, isCurrent(): boolean}` (a newer token makes older ones not current).

- [ ] **Step 1:** Tests:
  - `contract.test.mjs` reads `lcms-viewer/src/js/4map-manager.js`, extracts `this.<name> = function` inside `function mp()` with a regex, and asserts every name is a function on `createMapApi(createStore(), fakeEngine)`.
  - `api.test.mjs`: a recorded Python call sequence (fixture string from `make_fixtures.py` in Task 8, for now a hand-written copy of a `_build_run_js` output for: one `addSerializedLayer`, one `addSerializedTimeLapse`, one `addSerializedSelectLayer`, `areaChart.addLayer`, `Map.setCenter`, `map.setZoom(9)`, `Map.turnOnInspector()`, `Map.setQueryScale(30)`, `Map.setTitle("x")`) is evaluated in a `vm` context with compat.js; after installing the api, the store has 3 layers in call order, `tool === "query"`, `query.scale === 30`, `title === "x"`, and no notices.
  - `api.test.mjs` `unsupported calls announce`: `Map.addPlot([0,0])` adds exactly one notice naming `addPlot`.
  - `util.test.mjs`: `formatLength(4820,"metric") === "4.82 km"`, `formatLength(4820,"imperial") === "3.00 mi"`, `formatArea(4120000,"metric","area") === "412 ha"`, `formatArea(4120000,"imperial","area") === "1,018 acres"`, `formatArea(1030000,"metric","pct",4120000) === "25.0%"`; `escapeText('<b>"x"</b>')` contains no `<`.
  - `state.test.mjs`: `set` emits `change` once and `change:units` only when units changed.
- [ ] **Step 2:** `node --test geeViz/geeView/delta/tests/` fails.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Tests pass; mutation-check the contract test by deleting one method from api.js.
- [ ] **Step 5:** Commit.

### Task 3: Shell, tokens and layout

**Files:**
- Create: `delta/css/tokens.css`, `delta/css/delta.css`, `delta/js/ui/shell.js`, `delta/js/ui/status.js`; templates inside `delta.html`
- Modify: `delta/js/main.js` (boot UI with a stub engine when `?delta-test=shell`)
- Test: `geeViz/tests/delta/conftest.py`, `geeViz/tests/delta/test_shell.py`

**Interfaces:**
- Consumes: store (Task 2).
- Produces: `mountShell(store, {mapEl}) -> {setStreetView(on: boolean): void}`; DOM ids `#pane-left`, `#pane-right`, `.grip[data-side]`, `#hamburger`, `#hamburger-float`, `#theme-btn`, `#mtabs [data-m]`, `#mmenu [data-t]`; CSS custom properties `--lw`, `--rw` on `:root`; localStorage keys `delta-left`, `delta-right`, `delta-theme` (each access in try/catch).
- conftest fixtures: `delta_page(url_params) -> playwright Page` serving `geeView/` over a local `http.server` on a free port bound to 127.0.0.1; `live_map(build: callable) -> Page` that builds a `gv.mapper()`, sets skin delta, `view(open_browser=False)`, opens the URL, waits for `window.__delta` and no pending tile loads (or 60 s), collects console errors and page errors into `page.delta_errors`.

Behavior (from the spec's Layout sections): default left width `clamp(300px,33.333vw,560px)`; min 240, max 50% of window; double-click grip resets; right pane 330 px, folded to 64 px when `tool === null`; Street View hides panes, controls, status, phone bars; theme follows `prefers-color-scheme` when `theme === "system"`; phones at `max-width:760px` per spec (top bar, two tabs Layers and Tools, sheets, logo menu with Match phone, Light, Dark).

- [ ] **Step 1:** Tests in `test_shell.py` (use `delta_page({"delta-test":"shell"})`):
  - `test_left_default_is_a_third`: viewport 1500 wide, `#pane-left` width 500 ± 1.
  - `test_resize_and_reset`: drag grip to 420, reload, width 420; double-click grip, width back to 500.
  - `test_hamburger_hides_and_shows` and the url keeps `showSidebar=false`.
  - `test_right_pane_folds_without_tool`: set `tool=null` via `__delta.store`, width 64.
  - `test_streetview_hides_everything`: `setStreetView(true)` hides `#pane-left`, `#pane-right`, `#status`; false restores.
  - `test_theme_follows_system`: emulate dark color scheme, `data-bs-theme="dark"`; light likewise; explicit choice persists across reload.
  - `test_phone_layout`: viewport 390x844, `#mtabs` has exactly two buttons with text `Layers` and `Tools`; tapping Layers adds class `m-layers` to body; tapping again removes it.
- [ ] **Step 2:** Fail. **Step 3:** Implement. **Step 4:** Pass. **Step 5:** Commit.

### Task 4: Google map, Earth Engine init, basemaps, search, history, Street View

**Files:**
- Create: `delta/js/engine/maps.js`, `delta/js/engine/ee.js`
- Modify: `main.js` (real boot), `compat.js` (`map` proxy binding)
- Test: `geeViz/tests/delta/test_map_engine.py`

**Interfaces:**
- `createMap(el, store) -> MapEngine` with `gmap`, `setBasemap("satellite"|"map"|"dark")` (Google `hybrid`, `roadmap`, a StyledMapType named `dark` from the mockup's `darkStyle`), `setCenter(lng, lat, zoom)`, `centerObject(boundsInfo)` (same argument `synchronousCenterObject` receives from Python), `back()`, `forward()` (view history: port the original's `backView/forwardView` stack semantics), `streetViewPick(on: boolean)`, `onStreetView(fn)`, `elevationAt(latLng) -> Promise<number|null>` (port of the original's elevation lookup used by the status bar).
- `initEE(urlParams) -> Promise<void>`: port of `eeInit` and its success callback from `lcms-viewer/src/js` (token mode when `urlParams.accessToken` is set and not `"None"`, proxy mode via `authProxyAPIURL` otherwise, tenant prefix honored because compat's `authProxyAPIURL` is the same binding), then sets the default workload tag exactly as the original does, then resolves. `main.js` calls `window.runGeeViz()` after it resolves, then replays compat's queued calls.
- Search: Google Places `SearchBox` on the search input, plus coordinate parsing (`"lat, lng"` and `"lng, lat"` with sign rules from the original's search handler).

- [ ] **Step 1:** Tests (`live_map` with `Map.setCenter(-111.6, 40.6, 11)` and no layers):
  - `test_ee_initialized`: `await page.evaluate("ee.data.getAuthToken() !== null || !!authProxyAPIURL")` true and `delta_errors` empty.
  - `test_set_center_and_zoom`: map center within 1e-4 and zoom 11.
  - `test_view_history`: pan twice, `back()` returns to the previous center, `forward()` returns.
  - `test_basemaps`: each basemap button sets `gmap.getMapTypeId()` to `hybrid`, `roadmap`, `dark`.
  - `test_street_view_round_trip`: `streetViewPick(true)`, click the map at a point known to have coverage (40.7608,-111.8910), panorama becomes visible and the shell hides panes; exit restores panes.
  - `test_search_coordinates`: typing `40.5, -111.9` and Enter centers there.
- [ ] **Step 2–5:** fail, implement, pass, commit.

### Task 5: Layers: every type, legends, opacity, order

**Files:**
- Create: `delta/js/engine/viz.js`, `delta/js/engine/layers.js`, `delta/js/ui/layers.js`
- Test: `delta/tests/viz.test.mjs`, `geeViz/tests/delta/test_layers.py`

**Interfaces:**
- `prepareViz(eeObject, viz) -> Promise<{viz, legend}>`: port of `addToMap`'s viz handling in `4map-manager.js` (lines around 1445-1800: autoViz from `<band>_class_names/_class_values/_class_palette`, reducer for collections, `layerType` defaulting, `isTimeLapse`, vector styling, GENA palettes via `gena-gee-palettes.js` loaded as in the original). `legend` is `{type:"classes", items:[{label,color}]}` or `{type:"ramp", min, max, palette, labels}` or `{type:"outline", color, label}`, matching what the original legend shows for the same viz (`legend` from viz wins).
- `addLayerToMap(engine, layer) -> Promise<void>` for `layerType` `geeImage`, `geeImageCollection`, `geeVectorImage`, `geeVector`, `geoJSONVector`, `tileMapService`, `dynamicMapService` (ports of each branch, including LOCAL PATCH tile legend v2/v3 and the dynamic map service ground overlay), `setLayerVisible(id, bool)`, `setLayerOpacity(id, 0..1)`, `applyOrder(order)` (Google `overlayMapTypes` index order equals list order; geojson Data layers' zIndex likewise), tile loading counts feeding `layer.loading`.
- UI per spec "Layer rows": round toggle, name (click toggles; drag handle), spinner, opacity slider (inline only if the name is not truncated; `clamp(64px, 100cqw - 250px, 180px)` inline; stacked `clamp(110px, 100cqw - 120px, 240px)` on its own line; no percentage, value in `title`; `--a` drives fill and thumb center), legend swatch toggle (up to 4 class colors, ramp gradient, or outline), legend inside row, off folds legend and restores prior open state; SortableJS with handle `.lname`, filter `.pinned`, pinned layers restored to their indices after a drop; order stored in `urlParams.layerOrders` as the original does; `setCanReorderLayers(false)` disables Sortable.
- `turnOffAllLayers()`, `turnOnAllLayers()` act on all rows.

- [ ] **Step 1:** Tests:
  - `viz.test.mjs`: fixture vizzes (LCMS Land_Cover with class properties, a min/max/palette viz, a vector viz with `strokeColor`) produce the legend objects above; `escapeText` applied to labels.
  - `test_layers.py` (`live_map` building, in order: `ee.Image("USGS/SRTMGL1_003")` min 0 max 3000; LCMS 2025-11 Land_Cover with `autoViz`; an `ee.FeatureCollection` of 3 polygons default (geeVectorImage); the same with `layerType: "geeVector"`; a small GeoJSON dict (geoJSONVector); `Map.addLayer` of an XYZ tile URL (tileMapService through the generator); one dynamic Esri map service through `addEsriMapService` against a public MapServer the existing esriLib tests use):
    - `test_all_types_render`: 7 rows, each reaches `loading === false` with no `error`, `delta_errors` empty, at least one tile or feature request per raster/vector layer.
    - `test_order_matches_original`: row order equals the order the original page shows for the same script (run the same build with skin original and read `#layer-list` names) and z-order equals row order.
    - `test_name_click_toggles`, `test_off_folds_legend_and_restores`.
    - `test_opacity_inline_only_when_fits`: at left widths 260, 300, 340, 400, 480 no `.lname` has `scrollWidth > clientWidth + 1` while inline; stacked rows have the slider below the name (its top greater than the name's bottom).
    - `test_slider_grows_then_caps`: inline slider width 64 at narrow, grows by the same pixels as the pane between 340 and 420 (±2), 180 at 480 and 560.
    - `test_drag_reorder_keeps_pinned`: drag a raster above another; z-order changes; the pinned geoJSON layer keeps its index.
    - `test_duplicate_names_and_many_layers`: 45 layers including two named "A"; 45 rows, both "A" rows present, order preserved.
    - `test_names_render_as_text`: layer named `</script><b>x</b>"` shows that literal text and adds no `<b>` element.
- [ ] **Step 2–5:** fail, implement, pass (mutation-check `applyOrder` and the fit check), commit.

### Task 6: Timelapses

**Files:**
- Create: `delta/js/engine/timelapse.js`, `delta/js/ui/timelapse.js`
- Test: `geeViz/tests/delta/test_timelapse.py`

**Interfaces:**
- Port of `addTimeLapseToMap` and its helpers in `4map-manager.js` (frame layers per year, `years` lookup, loading tracking, play/pause/stop, back/forward one frame, speed in fps, cumulative mode, refresh tiles via the original's jitter, frame visibility toggle, `turnOffLayersWhenTimeLapseIsOn`), and the behavior of `geeView/src/js/timelapse-toggle.js` (toggle usable while loading; the choice applies when loading completes).
- `createTimelapse(engine, layer) -> {setFrame(index), play(fps), pause(), stop(), step(delta), setCumulative(bool), refresh(), setVisible(bool)}`; state lives in `layer.timelapse = {years, frame, playing, fps, cumulative, loaded}`.
- UI per spec: block inside the row, year readout, year and speed sliders, buttons; map year badge while playing; phone floating player; off folds the block and pauses.

- [ ] **Step 1:** Tests (`live_map` with `Map.addTimeLapse` of LCMS Land_Cover 2015-2023 autoViz and a continuous NDVI collection 2018-2020):
  - `test_frames_and_years`: years `[2015..2023]`, nine frame overlays.
  - `test_play_pause_step_speed`: play advances frames at about the set fps (2 fps advances 3-5 frames in 2 s); pause stops; step ±1 wraps.
  - `test_cumulative`: cumulative shows frames up to the current year.
  - `test_off_folds_and_pauses` and on restores the legend state.
  - `test_toggle_during_load`: turn off before `loaded`; after load completes the layer is off and no frame overlay is visible.
  - `test_turn_off_layers_when_timelapse_on`: with the Python setting true, turning a timelapse on turns other layers off.
- [ ] **Step 2–5.**

### Task 7: Query tool and select layers

**Files:**
- Create: `delta/js/engine/query.js`, `delta/js/ui/output.js`, `delta/js/ui/tools.js` (tool strip, units switch, tool options; this task wires Query, later tasks add the others)
- Test: `geeViz/tests/delta/test_query.py`

**Interfaces:**
- `queryPoint(engine, layers, latLng, store.query) -> Promise<Result[]>`: port of the original's double-click query for every visible queryable layer (images, collections as time series, vectors with their properties, select layers), honoring `crs`, `scale`, `transform`, `precision`, `dateFormat`, and drawing the query box with `boxColor`. One `reduceRegion` per layer, issued in parallel, `evaluate()` only. Each call carries a `requestToken`; results for a superseded token are dropped.
- Result: `{id, layerId, title, meta, kind: "value"|"series"|"table", data, actions: ["csv"|"png"|"expand"|"copy"]}`.
- Select layers (`addSelectLayer`): clicking a feature selects it (port of the original's selection list), selections listed in output and usable by Chart area's Select source.
- Phones: `windowMode === "infoWindow"` renders point results in a Google InfoWindow; desktop always uses the output pane.
- Tools UI per spec: four buttons, one active, clicking the active one sets `tool=null`; `turnOnInspector` makes Query active.

- [ ] **Step 1:** Tests (`live_map` with SRTM, LCMS Land_Cover collection autoViz, a select layer of 3 polygons with `selectLayerNameProperty`):
  - `test_query_values_match_python`: double-click (-111.527, 40.504): SRTM value equals `ee.Image(...).reduceRegion(first, point, 30).getInfo()` from Python; LCMS series has 2023 class "Trees" (value 1) matching Python.
  - `test_query_respects_scale_and_crs` (after `setQueryScale(120)` value equals Python at 120).
  - `test_stale_query_results_are_dropped`: two double-clicks 50 ms apart; only the second point's cards remain.
  - `test_select_layer_selection` lists the chosen polygon's name.
  - `test_tool_toggle_off_folds_pane`.
- [ ] **Step 2–5.**

### Task 8: charts.py ports (pure functions and reductions)

**Files:**
- Create: `delta/js/engine/charts.js`, `delta/js/engine/sankey.js`, `geeViz/tests/delta/make_fixtures.py`, `geeViz/tests/delta/fixtures/*.json`
- Test: `delta/tests/charts.test.mjs`, `delta/tests/sankey.test.mjs`, `geeViz/tests/delta/test_charts_parity.py` (live)

**Interfaces (ports, same names in camelCase, `SPLIT_STR = "----"`):**
- Pure: `truncateClassName(name, max=30)`, `stackBandNames(labels, bands) -> string[]`, `parseThematicResults(raw, objInfo, labels, areaFormat, scale) -> {columns, rows}`, `parseContinuousResults(raw, objInfo, labels) -> {columns, rows}`, `convertPixelArea(count, scale, areaFormat)`, `autoScale(zoom, baseScale, minZoomSpecifiedScale)`, `buildSankeyFromHistogram(hist, classInfo, periods, areaFormat, scale, minPercentage) -> {links, matrix}`.
- EE (return Promises, use `evaluate`): `getObjInfo(eeObj, bandNames)`, `prepareForReduction(eeObj, objInfo, xAxisProperty, dateFormat) -> {image, bandNames, labels}` (mosaic per label when counts > 1; `toBands()` then rename to known names; date format sanitized as charts.py does), `reduceArea(image, geometry, reducer, {scale, crs, transform, tileScale:4})`, `prepareSankeyData(ic, band, periods, classInfo, geometry, opts)` (all period pairs stacked, one reduction).
- `make_fixtures.py` runs charts.py functions on recorded raw reduction dicts (stored in the fixture too) so pure-function tests need no Earth Engine; and records `summarize_and_chart` numeric outputs for the four live cases.

- [ ] **Step 1:** Tests:
  - `charts.test.mjs`: for each fixture, JS pure output deep-equals charts.py output (numbers to 1e-9). Includes `parseThematic keeps missing labels as null`: raw dict missing year 2003 gives null for 2003 and correct values for 2004 onward.
  - `sankey.test.mjs`: fixture histogram gives charts.py's links and matrix; flows below 0.5% removed from links, present in matrix.
  - `test_charts_parity.py` (live, in the browser via `page.evaluate` importing `./delta/js/engine/charts.js`): LCMS Land_Cover 2015-2023 over a fixed 3 km polygon near (-111.6, 40.6); NLCD 2021 single image; NDVI collection mean; one Sankey 2016-2018 → 2020-2022. Each JS result equals charts.py's for the same inputs (`scale=30`, `crs=EPSG:5070`, transform above), percentages to 1e-6.
- [ ] **Step 2:** Fail. **Step 3:** Implement. **Step 4:** Pass; mutation-check `stackBandNames` ordering, the missing-label handling, and the min-percentage filter. **Step 5:** Commit.

### Task 9: Chart area tool, charts and Sankey

**Files:**
- Create: `delta/js/charts/plotly.js`, `delta/js/charts/sankey.js`
- Modify: `delta/js/ui/tools.js`, `delta/js/ui/output.js`
- Test: `geeViz/tests/delta/test_chart_area.py`

**Interfaces:**
- `chartArea(engine, store, geometry, sourceLabel) -> Promise<void>`: for each visible chartable layer (and `areaChartOnly` layers chosen in settings), computes with Task 8 ports and the Global Constraints inputs, writes Results (`kind:"chart"`, `kind:"sankey"`), caches by `(layerId, geometryHash, scale)`; unit and Show-as changes re-render from cache with no Earth Engine call; a new area's token supersedes older work.
- Area sources: Draw (Google drawing via polygon clicks, double-click to finish, as the original), Map view (current bounds), Upload (shapefile zip, GeoJSON, KML as the original's upload accepts), Select (from Task 7 selections). `turnOnAutoAreaCharting`, `turnOnUserDefinedAreaCharting`, `turnOnSelectionAreaCharting` set tool and source.
- `addAreaChartLayer` settings per spec list, with the original's defaults; single images chart as bars.
- `renderChart(el, result, theme, chartSettings)` (Plotly, themed from tokens, `yLabel*` honored); `renderSankey(el, result, theme)` (port of `D3_SANKEY_TEMPLATE`: gradient links, halo labels, outer-column labels only, tooltips; drawn at the card's width).
- Actions: CSV (columns as the original's CSV export), PNG (Plotly `toImage`; Sankey via SVG serialization), Expand (modal).

- [ ] **Step 1:** Tests (`live_map` with LCMS `canAreaChart` + `areaChartParams: {line: true, sankey: true}` and transition periods, NLCD single image `canAreaChart`):
  - `test_chart_numbers_equal_python`: Map view source over a fixed bounds; card data equals charts.py `summarize_and_chart` for the same geometry and inputs.
  - `test_units_and_show_as_rerender_without_ee`: count Earth Engine network requests; switching Imperial and % of area adds zero.
  - `test_single_image_is_bar`, `test_sankey_card_renders` (SVG has links with gradients; tooltip on hover shows source, target and value).
  - `test_stale_chart_results_are_dropped`.
  - `test_upload_geojson_source` charts the uploaded polygon.
  - `test_csv_and_png_actions` produce non-empty downloads.
- [ ] **Step 2–5.**

### Task 10: Distance and Area tools

**Files:** Create `delta/js/engine/measure.js`; modify `ui/tools.js`, `ui/output.js`. Test: `delta/tests/measure.test.mjs`, `geeViz/tests/delta/test_measure.py`.

**Interfaces:** `distanceMeters(path: LatLng[]) -> number`, `areaSquareMeters(path) -> number`, `perimeterMeters(path) -> number` via `google.maps.geometry.spherical` (unit tests stub the spherical functions with a geodesic implementation and compare to known distances: Salt Lake City to Provo 61.8 km ± 0.5).

- [ ] Steps: tests (`formatLength`/`formatArea` through the tools; browser test draws a 3-point line and a 5-point polygon, output text matches the formatted values in both unit systems); fail; implement; pass; commit.

### Task 11: Wind layers

**Files:** Create `delta/js/engine/wind.js`. Test: `geeViz/tests/delta/test_wind.py`.

**Interfaces:** Delta loads `./src/js/wind-particles.js` unchanged. `wind.js` provides the globals it reads (`map` as the Google map, a `layerObj` lexical binding in compat.js holding Delta's layer records with `viz`, `getTileUrl`, and visibility) so its adoption of `windParticles` layers works; `addWindLayer` and `addWindTimeLapse` go through the normal layer and timelapse paths.

- [ ] Steps: tests (`live_map` with `Map.addWindLayer` from the GFS example in `examples/GFSTimeLapse.py` and one `addWindTimeLapse`: the particle canvas exists and draws non-empty pixels within 20 s; toggling the layer off clears it); fail; implement; pass; commit.

### Task 12: export_html, testView and the agent path

**Files:** Modify `geeViz/geeView.py` only if Task 1 missed a path. Test: `geeViz/tests/delta/test_export.py`.

- [ ] Steps: tests: `export_html` with skin delta served under `/geeView/static` by a test server that also substitutes the token placeholders (as the agent does) loads with no errors and draws an `ee.Image` layer; `testView()` with skin delta returns a screenshot path and no tile errors; page size under the limit for a 10-layer map. Fail, fix, pass, commit.

### Task 13: Sweeps: every Map method and every example

**Files:** Create `geeViz/tests/delta/test_method_sweep.py`, `geeViz/tests/delta/test_examples_sweep.py`, `geeViz/tests/delta/method_cases.py`.

**Interfaces:**
- `method_cases.py`: `CASES: dict[str, callable(Map) -> None]`, one entry per public method of `gv.mapper` (every attribute not starting with `_` that is callable), each building a minimal map that exercises the method, plus `EXPECT: dict[str, callable(Page) -> None]` asserting the method's visible effect in Delta (for example `setQueryScale` → `__delta.store.get().query.scale`; `clearMapLayers` → zero rows; `setTitle` → title text; `centerObject` → bounds contain the object). Methods that only act in Python (`exportLayerJson`, `testLayers`, `previewMap`, `clearMapCommands`, `setAuthMode`, `refresh`) are listed in `PYTHON_ONLY` with a one-line reason and asserted to emit no new JS.
- `test_method_sweep.py`: fails if any public method has neither a case nor a `PYTHON_ONLY` entry (so new methods force a case); for each case, builds the map with skin delta, loads it, asserts `delta_errors` empty, no notices, and the `EXPECT` check; then runs the same build with skin original and asserts the original page also loads (a baseline, so a broken case is distinguished from a Delta bug).
- `test_examples_sweep.py`: for each `geeViz/examples/*.py` that calls `Map.view()` (detected by source scan), runs it with `runpy` in a subprocess with `GEEVIZ_SKIN=delta` and `Map.view` patched to `open_browser=False` and to write the URL to a temp file; loads the URL; asserts no page errors, no notices, the row count equals `len(Map.idDictList)` excluding area-chart-only layers, and saves a screenshot to `tests/delta/screenshots/<example>.png`. Examples that need credentials or data the environment lacks are skipped with the reason printed, never silently.

- [ ] Steps: write the sweeps; run them; every failure becomes a fix in the owning module (Tasks 2-12) with its own regression test added to that task's test file; rerun until both sweeps pass; commit sweeps and screenshots list (screenshots themselves gitignored).

### Task 14: Docs

**Files:** Modify `geeViz/geeView.py` docstring for `setSkin`; add a section to `geeVizDocs` (separate repo) describing skins; add `.superpowers/` to `geeViz/.gitignore`.

- [ ] Steps: docstring with example; docs page; run `python -m pytest geeViz/tests/test_delta_skin.py -q`; commit in each repo with explicit paths.
