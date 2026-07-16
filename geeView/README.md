# geeViz.geeView — interactive browser-based Earth Engine map viewer

The HTML / JS / CSS bundle that `Map.view()` serves to the browser. This directory is *not* the Python code — that lives in `geeViz/geeView.py`, one level up. This is the static frontend the Python side hands off to the browser.

## Layout

```
geeView/
├── index.html            ← main viewer page. Always served as-is.
├── foliumView.html       ← legacy Folium fallback (rarely used).
└── src/
    ├── gee/
    │   ├── gee-libraries/       ← JS ports of geeViz helper libs.
    │   │   ├── getImagesLib.js
    │   │   └── changeDetectionLib.js
    │   └── gee-run/
    │       └── runGeeViz.js     ← per-session script Python generates.
    ├── js/
    │   ├── lcms-viewer.min.js   ← the viewer engine (map, layers, chart UI).
    │   ├── load.min.js
    │   └── gena-gee-palettes.js ← Gennadiy Donchyts' palette collection.
    ├── styles/
    │   └── style.min.css        ← viewer styling.
    └── assets/                  ← icons, background images, favicon.
```

## Serving model

Everything under `geeView/` is *static*. Python only ever writes ONE thing here at runtime: **the per-session `src/gee/gee-run/runGeeViz.js`** that carries the layer list, viz params, map commands, and the tenant-pinning snippet for the current call. Everything else is shipped as-is.

`Map.view()` (in `../geeView.py`) does two things:

1. Writes the current session's `runGeeViz.js` to `src/gee/gee-run/`.
2. Opens `http://127.0.0.1:<port>/geeView/?v=<cache-buster>` in the browser (or in a notebook iframe).

The `<port>` is whatever the eeAuth proxy is running on — same-origin with `/ee-api/*` for the auth-injecting reverse proxy, so the browser makes no cross-origin requests.

## How the JS boots

Reading `index.html` top-to-bottom is the quickest way to see what loads. In order:

1. **`lcms-viewer.min.js`** — the viewer engine. Parses `?v=…` and any other query-string params into a global `urlParams` object, initializes the map div, creates the layer sidebar, sets up chart panels.
2. **Per-session `runGeeViz.js`** — everything Python needed to send over. Sets `authProxyAPIURL` to the tenant-scoped proxy URL (see [`../eeAuth/README.md`](../eeAuth/README.md) → "How Map.view() pins each browser tab"), defines a `runGeeViz()` function that calls `Map.addLayer(...)` / `Map.centerObject(...)` / etc. once Earth Engine finishes initializing.
3. **`ee.initialize(authProxyAPIURL, geeAPIURL, ...)`** — the Earth Engine JS SDK is pointed at the local proxy (proxy mode) or straight at `earthengine.googleapis.com` with an injected bearer (direct-token mode). See [`../eeAuth/README.md`](../eeAuth/README.md) → "Inside the page" for the two modes.
4. **`runGeeViz()` fires** on init success and populates the map.

## Auth model

**No credentials ever live in this bundle.** In proxy mode (the default for `Map.view()`), the JS side uses an *anonymous* EE client that routes every REST call through the local eeAuth proxy, which injects the SA bearer server-side. In direct-token mode (used by the standalone-HTML export path), Python injects a fresh short-lived token per response — expires in ~1 hour.

For the full trust model, tenant routing, and how the proxy talks to Google, see the dedicated [`../eeAuth/README.md`](../eeAuth/README.md) or the [Earth Engine Authentication doc page](https://geeviz.org/ee_auth.html).

## Interactive features

Everything is done by `lcms-viewer.min.js` — no build step required, no frameworks. Features:

- **Layer sidebar** with per-layer visibility, opacity, and reorder.
- **Pixel query** — click any pixel to get per-band values across every visible layer.
- **Area charting** — draw a polygon (or use a preloaded region) and get zonal statistics as time series / bar / donut / Sankey (D3).
- **Legend rendering** — auto-generated from `bandName_class_values` / `bandName_class_names` / `bandName_class_palette` image properties.
- **Split-screen comparison** — two synchronized maps for before/after inspection.
- **Time-lapse playback** — for `ee.ImageCollection` layers added via `Map.addTimeLapse`.
- **Export** — save the current view as PNG or share as a URL.

## Modifying the frontend

Rebuilds are not required — the JS is shipped unminified enough to be readable (`lcms-viewer.min.js` is technically minified but is what ships). If you want to modify the viewer:

1. Edit `src/js/lcms-viewer.min.js` directly, or write new code as separate `<script>` includes in `index.html`.
2. Reload the browser tab — geeViz's dev HTTP server always sends `Cache-Control: no-store`, so refreshes always pick up your changes.

The Python side never needs a rebuild; only Python edits require a `pip install -e .` (or an already-editable install).

## Related packages

- **`geeViz.geeView`** (parent Python module) — `Map`, `mapper`, `addLayer`, `view`, etc. The Python API you actually call.
- **`geeViz.eeAuth`** — the multi-tenant auth proxy. See [`../eeAuth/README.md`](../eeAuth/README.md).
- **`geeViz.outputLib`** — the same auto-viz logic in a headless pipeline (charts, thumbnails, reports). See [`../outputLib/README.md`](../outputLib/README.md).
