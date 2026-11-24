# geoView Step 1: Earth Engine Optional, Plug-in Boundary — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delta starts and draws non-Earth Engine layers with no Earth Engine library or sign-in, loads Earth Engine only when a map has an Earth Engine layer, and dispatches each layer kind through a plug-in registry.

**Architecture:** A lazy Earth Engine loader (`engine/ee.js`) replaces the page's synchronous `ee_api_js` script tag; the four modules that captured `window.ee` at startup take a lazy reference instead. `js/plugins/` holds a registry keyed by layer `kind`; the layer engine and the Query tool call a kind's plug-in rather than branching inline. Earth Engine workload tags travel on the layer (geeViz writes them into the viz) instead of as top-level `ee.data` calls in the run script. This step draws the draw and query parts of the plug-in contract; the legend and chart parts join it in step 2, with the first plug-ins that need them (legends stay in `prepareViz`, area charts stay Earth Engine only until then).

**Tech Stack:** Vanilla ES modules, Google Maps JS API, Earth Engine JS API 0.1.384 (jsDelivr), node:test, pytest + Playwright (live).

**Spec:** `C:\RCR\georest\docs\superpowers\specs\2026-11-24-geoview-design.md` — this plan is release step 1 ("Make Earth Engine optional and draw the plug-in boundary, inside geeViz's Delta (no move yet). Delta's tests keep passing.") Steps 2-5 get their own plans.

## Global Constraints

- Work in the geeViz repo (`C:\RCR\geeVizBuilder\geeViz`), branch `master`; stage explicit paths only, never `git add -A`.
- Preserve each file's line endings (most Delta JS/CSS files are CRLF; `js/ui/layers.js` is mixed: edit it with an exact-string editor, not a normalize-and-rewrite script).
- US English; no em dashes in UI copy, docs or comments.
- The original skin (`Map.setSkin("original")`, `geeView/index.html`, `runGeeViz.js`) is unchanged in behavior and output.
- Earth Engine JS library URL stays pinned: `https://cdn.jsdelivr.net/gh/google/earthengine-api@0.1.384/javascript/build/ee_api_js.js`.
- Under an eeAuth proxy (`_EE_API_UPSTREAM` set) no workload tag is written into the page, as today.
- Run JS units with `node --test tests/*.test.mjs` from `geeView/delta`; live suites from the workspace root: `venv/Scripts/python.exe -m pytest geeViz/tests/delta -q` (needs the 8889 eeCreds proxy running).
- Mutation-check every test that guards new behavior (break the code, see the test fail, restore).

## Review Focus

1. A map whose only Earth Engine layers are `select`, `timelapse` or `areaChartOnly` kinds (no `ee` kind) still loads Earth Engine — Task 2 registry test.
2. A layer added after boot (agent or console calling `Map.addSerializedLayer`) on a page that had no Earth Engine layers loads Earth Engine then — Task 3 live test.
3. Earth Engine sign-in fails on a mixed map: non-EE layers draw, each EE layer row shows the error, and the page shows one notice, not one per layer — Task 4 live test.
4. The original skin's generated `runGeeViz.js` is byte-identical to before — Task 5 Python test.
5. An exported page (`export_html`, `accessToken` in the URL) still signs in with its token through the lazy loader — Task 1 unit test.

---

### Task 1: Lazy Earth Engine loader

**Files:**
- Modify: `geeView/delta/js/engine/ee.js`
- Test: `geeView/delta/tests/eeloader.test.mjs`

**Interfaces:**
- Produces:
  - `EE_SCRIPT_URL` (the pinned URL above).
  - `lazyEE`: a `Proxy` whose property reads return `globalThis.ee[prop]`, and throw `Error("Earth Engine is not loaded")` when `globalThis.ee` is undefined.
  - `createEELoader({ urlParams, proxyUrl, loadScript, init }) -> { ensure(): Promise<void>, isReady(): boolean, error(): string|null, whenReady(fn): void }`. `loadScript(url) -> Promise` defaults to inserting a `<script>`; `init(urlParams, proxyUrl) -> Promise` defaults to the existing `initEE`. `ensure()` is memoized: one script load, one init, every caller gets the same promise. On failure it rejects with `describeEEFailure(...)` text and `error()` returns it. `whenReady(fn)` runs `fn` now if ready, else after a successful init, in call order; never on failure.

- [ ] **Step 1: Write the failing tests** in `tests/eeloader.test.mjs`:
  - `ensure loads the script and signs in once, however many callers` — three concurrent `ensure()` calls; `loadScript` and `init` stubs each called exactly once; all three resolve; `isReady()` true.
  - `a failed sign-in rejects every caller with the described failure` — `init` rejects `new Error("invalid authentication credentials")` with `urlParams.accessToken = "x"`; each `ensure()` rejects with a message containing `"The access token looks invalid or expired"`; `error()` equals that message; `isReady()` false.
  - `whenReady runs queued functions in order after sign-in, and never on failure` — two queued fns record `[1, 2]` after success; with a failing init the record stays `[]`.
  - `an exported page signs in with its access token` — `ensure()` with `urlParams = { accessToken: "tok", projectID: "p" }` calls `init` with those `urlParams` (assert the object passed).
  - `lazyEE reads the global once loaded and says so before` — with `globalThis.ee` undefined, `lazyEE.Image` throws `/not loaded/`; after `globalThis.ee = { Image: 1 }`, `lazyEE.Image === 1`.
- [ ] **Step 2: Run** `node --test tests/eeloader.test.mjs` — expect FAIL (exports missing).
- [ ] **Step 3: Implement** the three exports in `js/engine/ee.js`; keep `initEE`, `hasAccessToken`, `projectIdFrom`, `describeEEFailure` as they are.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs` — expect all pass.
- [ ] **Step 5: Commit** `js/engine/ee.js`, `tests/eeloader.test.mjs`: "Delta: lazy Earth Engine loader".

### Task 2: Plug-in registry and the draw boundary

**Files:**
- Create: `geeView/delta/js/plugins/index.js`, `js/plugins/ee.js`, `js/plugins/tiles.js`, `js/plugins/geojson.js`
- Modify: `geeView/delta/js/engine/layers.js` (the `addLayer` draw branches, roughly lines 395-433, and `SKIP_KINDS` / `NOT_QUERYABLE` use)
- Test: `geeView/delta/tests/plugins.test.mjs`

**Interfaces:**
- Produces (`js/plugins/index.js`):
  - Plug-in shape: `{ kinds: string[], needsEE: boolean, draw(rec, item, ctx): void | Promise<void>, query?: (target, layer, point, qctx) => Promise<Result[]> }`.
  - `pluginFor(kind) -> Plugin` (throws `Error("No plug-in for layer kind: " + kind)`), `needsEE(layer) -> boolean`, `PLUGINS` (the list).
- Kinds and owners: `ee`, `select`, `timelapse`, `areaChartOnly` -> `plugins/ee.js` (`needsEE: true`); `tile`, `dynamic` -> `plugins/tiles.js`; `geojson` -> `plugins/geojson.js` (both `needsEE: false`).
- `ctx` (built once in `createLayerEngine`, passed to `draw`): `{ g, gmap, ee, store, tileOverlay, eeTileLayer, addGeoJson, addTimelapse, setLoading, sync, fail, patch, recs, groundOverlayUrl, tileBounds }` — the engine's existing internal functions, unchanged.
- `draw` bodies are the current `addLayer` branches moved verbatim: `tileMapService` and `dynamicMapService` to tiles.js, `geoJSONVector` to geojson.js, `geeVector`/tile EE types to ee.js. `areaChartOnly` keeps drawing nothing (today's `SKIP_KINDS`); timelapse keeps its own `addTimelapse` path, now reached through the ee plug-in.

- [ ] **Step 1: Write the failing tests** in `tests/plugins.test.mjs`:
  - `every kind the Map API makes has exactly one plug-in` — for each of `["ee","select","timelapse","areaChartOnly","tile","dynamic","geojson"]`, `pluginFor(k).kinds` includes `k`, and no kind appears in two plug-ins.
  - `needsEE: only Earth Engine kinds` — true for `ee`, `select`, `timelapse`, `areaChartOnly`; false for `tile`, `dynamic`, `geojson`.
  - `an unknown kind is an error, not a silent skip` — `pluginFor("nope")` throws `/No plug-in for layer kind: nope/`.
  - `the Map API's kinds match` — `createMapApi(createStore(...))` then `addLayer` with `{layerType:"geoJSONVector"}`, `{layerType:"dynamicMapService"}`, `{layerType:"tileMapService"}`, an EE-like item, `addSerializedTimeLapse`, `addSerializedSelectLayer`; each resulting layer's `kind` has a plug-in.
- [ ] **Step 2: Run** `node --test tests/plugins.test.mjs` — expect FAIL.
- [ ] **Step 3: Implement** the registry and move the branches; `addLayer` becomes `pluginFor(layer.kind).draw(r, item, ctx)` after `prepareViz`.
- [ ] **Step 4: Run** JS units, then `venv/Scripts/python.exe -m pytest geeViz/tests/delta/test_layers.py geeViz/tests/delta/test_vector_legend.py geeViz/tests/delta/test_timelapse.py -q` — expect pass (drawing unchanged).
- [ ] **Step 5: Commit** the plug-in files, `layers.js`, the test: "Delta: layer kinds draw through a plug-in registry".

### Task 3: Earth Engine layers wait for Earth Engine; nothing else does

**Files:**
- Modify: `js/engine/layers.js:66` (`deps.ee || window.ee` -> `deps.ee || lazyEE`), `js/engine/areachart.js:520`, `js/engine/areasources.js:107`, `js/engine/query.js:538` (same change), `js/engine/query.js` `queryPoint` (dispatch through `pluginFor(layer.kind).query`), `js/plugins/ee.js` (`query` = today's `queryOne`, exported from query.js as `queryEE`)
- Test: `geeView/delta/tests/query.test.mjs` (add), `tests/delta/test_ee_optional.py` (new, live)

**Interfaces:**
- Consumes: `createEELoader` (Task 1), `pluginFor`/`needsEE` (Task 2).
- `createLayerEngine(gmap, store, deps)` takes `deps.eeLoader`; in `addLayer`, when `needsEE(layer)`, `await deps.eeLoader.ensure()` before `prepareViz`; on rejection `fail(r, err.message)` and return. Non-EE layers never call `ensure()`.
- `queryPoint` skips a layer whose plug-in has no `query` (as `NOT_QUERYABLE` did); the ee plug-in's `query(target, layer, point, qctx)` has `queryOne`'s current signature and body.

- [ ] **Step 1: Write the failing tests:**
  - `query.test.mjs` — `queryPoint dispatches by kind: a geojson layer is skipped, an ee layer is queried` — LAYERS with one `kind:"geojson"` visible queryable layer and one `kind:"ee"`; result list holds only the ee layer's result; the fake ee saw one request.
  - `tests/delta/test_ee_optional.py::test_a_layer_added_later_loads_earth_engine` (live) — build a map with only a GeoJSON layer; record requests matching `ee_api_js`; assert none after load; then in the page call `Map.addSerializedLayer(<serialized ee.Image("USGS/SRTMGL1_003")>, {min:0,max:3000}, "SRTM", true)` (serialize in Python with `ee.Image(...).serialize()` and pass as a JSON string arg); wait for the SRTM row's `loading === false && error === null`; assert `ee_api_js` was requested exactly once.
- [ ] **Step 2: Run both** — expect FAIL.
- [ ] **Step 3: Implement** the four lazy captures, the `ensure()` gate in `addLayer`, and query dispatch.
- [ ] **Step 4: Run** JS units and `pytest geeViz/tests/delta/test_ee_optional.py geeViz/tests/delta/test_query.py geeViz/tests/delta/test_chart_area.py -q` — expect pass.
- [ ] **Step 5: Commit**: "Delta: Earth Engine layers wait for Earth Engine; other layers draw at once".

### Task 4: Boot without Earth Engine

**Files:**
- Modify: `geeView/delta.html` (remove the synchronous `ee_api_js` `<script>`), `js/main.js` (boot: run `runGeeViz()` right away; then `if (store.get().layers.some(needsEE)) loader.ensure()`; one notice on failure; `engine.setEEReady` from the loader), `js/engine/maps.js` (elevation reads `loader.isReady()` via `setEEReady`, unchanged API)
- Test: `tests/delta/test_ee_optional.py` (add)

**Interfaces:**
- Consumes: Tasks 1-3. `window.__delta.eeLoader` is the loader (tests read it). `delta.eeError` keeps meaning "Earth Engine sign-in failed" and is set only when a sign-in was attempted.

- [ ] **Step 1: Write the failing live tests:**
  - `test_a_map_without_earth_engine_never_loads_it` — map: one GeoJSON layer (`geoJSONVector`) and one `addTileLayer` (OpenTopoMap URL already used in `test_layers.py`); page loaded; both rows `loading False`, `error None`; zero requests matching `ee_api_js` or `/ee-api/`; `__delta.eeLoader.isReady() === false`; `page.delta_errors == []`.
  - `test_earth_engine_failing_spares_the_other_layers` — `setup` routes `**/ee-api/**` to `route.abort()`; map: SRTM (`ee.Image`) and a GeoJSON polygon; GeoJSON row `error None` and on the map (`__delta.engine.layers.stats(id).onMap`); SRTM row `error` is a non-empty string; `__delta.store.get().notices` has exactly one entry mentioning Earth Engine.
- [ ] **Step 2: Run** `pytest geeViz/tests/delta/test_ee_optional.py -q` — expect FAIL.
- [ ] **Step 3: Implement** the boot change and the page edit.
- [ ] **Step 4: Run** the whole Delta suite `pytest geeViz/tests/delta -q` and JS units — expect all pass (165 + new live; 245 + new JS).
- [ ] **Step 5: Commit** `delta.html`, `main.js`, `maps.js`, the test: "Delta: boots without Earth Engine, loads it for Earth Engine layers".

### Task 5: Workload tags travel with the layer

**Files:**
- Modify: `geeView.py` `_build_run_js` (Delta skin only: emit `Map.setDefaultWorkloadTag(<tag>)` instead of the top-level `ee.data.setDefaultWorkloadTag`/`resetWorkloadTag` calls, and put each layer's tag in its viz as `workloadTag` instead of emitting `ee.data.setWorkloadTag` before it; nothing emitted under `_EE_API_UPSTREAM`), `geeView/delta/js/api.js` (`setDefaultWorkloadTag(tag)` stores `eeWorkloadTag` in the store), `js/plugins/ee.js` (after `ensure()`: `ee.data.setDefaultWorkloadTag(store.get().eeWorkloadTag)` when set; around each layer's `getMap`/`evaluate` call: `ee.data.setWorkloadTag(viz.workloadTag)` then `ee.data.resetWorkloadTag()` when the viz has one)
- Test: `tests/test_delta_run_js.py` (new, offline), `geeView/delta/tests/api.test.mjs` (add)

**Interfaces:**
- Consumes: Task 1 `whenReady`, Task 2 ee plug-in.
- Produces: store key `eeWorkloadTag: string|null` (default `null` in `state.js`); viz key `workloadTag`.

- [ ] **Step 1: Write the failing tests:**
  - `test_delta_run_js.py::test_delta_run_script_has_no_top_level_ee_calls` — `m = gv.mapper(); m.setSkin("delta"); m.addLayer(<serializable stand-in or a real ee.Image>, {}, "x")`; with a workload tag set through `eeCreds.setWorkloadTag("wl_test")` (or by setting `idDict["workloadTag"]` directly on `m.idDictList[-1]`), `_EE_API_UPSTREAM` patched to `""`: `js = m._build_run_js()`; assert `"ee.data." not in js`; assert `'"workloadTag": "wl_test"'` appears in the layer's viz JSON; assert `"Map.setDefaultWorkloadTag("` appears once.
  - `test_original_run_script_is_unchanged` — same map with `setSkin("original")`: `js` equals the string the pre-change `_build_run_js` produced (capture it from `git show HEAD:geeView.py` in the test setup is overkill; instead assert it still contains `ee.data.setDefaultWorkloadTag(` and `ee.data.setWorkloadTag("wl_test")` exactly as today).
  - `test_nothing_under_a_proxy` — `_EE_API_UPSTREAM` patched to a URL: Delta js contains neither `wl_test` nor `setDefaultWorkloadTag`.
  - `api.test.mjs::setDefaultWorkloadTag stores the tag for the Earth Engine plug-in` — call it; `store.get().eeWorkloadTag === "geeviz__t"`.
- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest geeViz/tests/test_delta_run_js.py -q` and the JS units — expect FAIL.
- [ ] **Step 3: Implement** the Python branch on `self.skin == "delta"`, the API method, and the plug-in's tag handling.
- [ ] **Step 4: Run** the new tests, JS units, and `pytest geeViz/tests/delta/test_layers.py -q` — expect pass.
- [ ] **Step 5: Commit** `geeView.py`, `api.js`, `state.js`, `plugins/ee.js`, the tests: "Delta: Earth Engine workload tags travel with each layer".

### Task 6: Whole-branch check and release note

**Files:**
- Modify: `release-notes.md` (2026.11.2 Delta section: one bullet, "Maps without Earth Engine layers start without Earth Engine; Earth Engine loads when the first Earth Engine layer is added, and a sign-in failure leaves the other layers drawn.")

- [ ] **Step 1: Run** the full Delta live suite, JS units, and `venv/Scripts/python.exe -m pytest geeViz/tests/ geeViz/fsInsights/tests/ -q` from the workspace root — expect pass (note any pre-existing live failures with evidence, do not mask them).
- [ ] **Step 2: Mutation spot-checks** — (a) make `needsEE` return false for `select`: Task 2 test fails; (b) call `ensure()` for every layer: `test_a_map_without_earth_engine_never_loads_it` fails; (c) emit `ee.data.setWorkloadTag` again in the Delta branch: `test_delta_run_script_has_no_top_level_ee_calls` fails. Restore each.
- [ ] **Step 3: Commit** `release-notes.md`: "Release notes: Delta boots without Earth Engine".
