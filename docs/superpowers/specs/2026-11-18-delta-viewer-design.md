# Delta: a new geeViz map viewer

Status: draft for approval, 2026-11-18. Approved mockup:
`docs/superpowers/specs/2026-11-18-delta-mockup.html` (a copy of the last
brainstorm screen; open it through any local web server, since the Google
Maps key rejects `file://`).

## Why

geeView, the map viewer `Map.view()` opens, is the lcms-viewer front end
bundled into geeViz. It works, and its look is recognizable, but it looks
dated, and its styling is spread through about 26,000 lines of jQuery where
templates, layout and Earth Engine logic are written together. Restyling it
in place is not practical: the Earth Engine code writes its own HTML with
hard-coded element ids.

Delta is a new viewer, chosen per script with `Map.setSkin("delta")`. The
current viewer stays frozen as `Map.setSkin("original")` and stays the
default until Delta reaches parity. The name: delta is the Greek letter for
change, and change over time is what geeViz users mostly look at.

Success is a viewer the maintainer would switch to for daily work: the same
mental model as today (layers, tools, tool output), a look that reads as a
current geospatial tool, light and dark themes, a usable phone layout, and
numbers identical to what geeViz's Python charting produces for the same
inputs.

## Goals

- Same paradigm as today: **layers** are self-contained; **tools** are tools,
  exactly one active at a time (or none); **tool output** lists results,
  one per visible layer the tool applies to.
- Every script that runs in the original runs unchanged in Delta. The Python
  side writes the same `runGeeViz.js`; only the page that loads it differs.
- Earth Engine work is as efficient as geeViz's Python charting library
  (`outputLib/charts.py`), whose reduction patterns Delta ports directly.
- Light and dark themes, following the operating system by default.
- Desktop and phone layouts from one page.

## Non-goals

- Changing lcms-viewer, its Forest Service release, or the original skin's
  bundle (`geeView/src/js/lcms-viewer.min.js`, `style.min.css`). They are
  frozen.
- LCMS-viewer modes other than geeViz (LCMS, MTBS, STORM, dashboards,
  tutorials). Delta serves `Map.view()` only.
- A JavaScript framework or a build step.
- Replacing Google Maps.

## Anti-goals (a failure even if it works)

- Any number in Delta that differs from `charts.py` (or from the original
  viewer, where charts.py has no equivalent) for the same layer, area, scale
  and units.
- Per-year or per-band round trips to Earth Engine where one stacked
  reduction does the job, or blocking `getInfo()` calls in the browser.
- A script that worked in the original failing silently in Delta. An
  unsupported call is announced, never dropped.
- Styling in JavaScript strings. Markup lives in templates and look lives in
  CSS tokens, so a restyle never touches logic again.

## Constraints

- Google Maps JavaScript API underneath, with the key geeView already loads.
  Street View must work.
- Libraries from CDNs with exact versions, as geeView does today: Bootstrap
  5.3.3, Tabler Icons webfont 3.19.0, SortableJS 1.15.2, d3 7.9.0, d3-sankey
  0.12.3, Plotly 2.27.0, the Earth Engine JS client geeView already loads.
- Plain ES modules; no bundler. geeViz ships the files as package data.
- US English, no em dashes, no decorative emoji in any UI copy.
- The local geeView server and the eeCreds proxy keep serving the page; Delta
  needs no new server endpoints.

## Approaches considered

- **A. New skin on the old engine.** Replace templates and CSS, keep
  `4map-manager.js`, `5chart-manager.js` and `area-charting.js`. Fastest
  start, but the engine injects its own markup (timelapse rows, legends,
  query output), so the old styling leaks through permanently.
- **B. Rewrite engine and UI from scratch** against the same `Map` contract.
  Cleanest, but it re-derives years of edge cases in tile loading, timelapse
  frames, query and charting.
- **C. New structure, ported logic (chosen).** New codebase with separate
  state, engine and UI layers. The UI is new. Earth Engine logic is ported
  function by function: charting and Sankey math from geeViz's
  `outputLib/charts.py` (the maintainer's requirement: take as much as
  possible from the charting library, because it is the efficient, tested
  version), and map behavior (tile layers, timelapses, query, select layers)
  from lcms-viewer, with every DOM write removed. Each port is checked
  against its source's output.

## Architecture

```
geeViz/geeView/delta.html page shell, beside the original index.html so
                          "./src/..." and "./delta/..." resolve the same way
                          for Map.view() and export_html; CDN tags, mount
                          points, no logic
geeViz/geeView/delta/
  js/compat.js            classic script: the globals runGeeViz.js uses
  css/tokens.css          color, type, spacing tokens; light, dark, system
  css/delta.css           components, styled only through tokens
  js/state.js             single store: layers, order, active tool, units,
                          show-as, pane widths, theme; emits change events;
                          mirrors the url parameters the original keeps
  js/api.js               the Map contract runGeeViz.js calls (addLayer,
                          addTimeLapse, addSelectLayer, setQuery*, turnOn*,
                          ...); validates and writes to state only
  js/engine/maps.js       Google Maps setup, overlays, z-order, Street View
  js/engine/tiles.js      EE map ids and tile overlays (ported, lcms-viewer)
  js/engine/timelapse.js  frame loading and playback (ported, lcms-viewer)
  js/engine/query.js      point query of visible layers (ported, lcms-viewer)
  js/engine/charts.js     reductions and parsing (ported, charts.py)
  js/engine/sankey.js     transition data (ported, charts.py)
  js/engine/measure.js    distance and area (geodesic, google.maps.geometry)
  js/ui/*.js              layer list, tools, output cards, timelapse block,
                          status bar, basemaps, mobile sheets; read state,
                          render templates, dispatch actions
  js/charts/*.js          Plotly line and bar charts; d3 Sankey ported from
                          outputLib/_templates.py D3_SANKEY_TEMPLATE
  templates/*.html        <template> elements the UI clones
```

Data flows one way: `api.js` and UI actions change `state`; the engine
reacts (adds overlays, runs reductions); results go back into `state`; the
UI renders. Engine modules never touch the DOM except the Google Maps div.

### Python side

- `Map.setSkin(name)` on the geeView mapper: `"original"` (default) or
  `"delta"`; any other value raises `ValueError` listing the valid names.
  Stored on the mapper like `setTitle`, and `Map.view()` opens
  `geeView/delta.html` instead of `geeView/index.html` when set.
- `runGeeViz.js` is unchanged, byte for byte, and the Python generator is
  not modified for Delta. The generated script reaches beyond `Map2`: the
  bare Google `map` object (`map.setZoom`), `synchronousCenterObject`,
  `areaChart.addLayer` and `areaChart.populateChartLayerSelect`,
  `showMessage` and `staticTemplates.loadingModal[mode]`, one jQuery call
  (`$('#close-modal-button').click()`), the globals `queryWindowMode`,
  `yLabel*` and `Map.turnOffLayersWhenTimeLapseIsOn`, a `localStorage`
  write, an `authProxyAPIURL` reassignment, and the global `runGeeViz()`
  the engine calls after Earth Engine initializes. Delta provides
  `js/compat.js`, a classic (non-module) script loaded before
  `runGeeViz.js`, that defines each of these as thin forwards into
  `api.js`, including a minimal `$` that supports only the selectors the
  generator emits and announces anything else. Delta reproduces every
  sign-in path the original supports (token mode, proxy mode, the tenant
  proxy address) and calls `runGeeViz()` at the same point.
- Delta's `api.js` implements every function the original's `Map2` object
  exposes. Calls Delta does not support yet
  (wind layers, Esri services, export, plots, feature views, until their
  stages land) show one notice in the output pane naming the call and
  suggesting `Map.setSkin("original")`, and are otherwise ignored.
- Settings that already exist keep working in Delta: `setTitle`,
  `setQueryCRS/Scale/Transform/Precision/DateFormat/BoxColor`,
  `setQueryWindowMode` (Delta always uses its output pane; an `infoWindow`
  request is honored on phones only, where the sheet would cover the map),
  `setCanReorderLayers`, `turnOnInspector` and the `turnOn*AreaCharting`
  calls (they pick the initially active tool), `turnOffAllLayers`,
  `turnOnAllLayers`, `setYLabel*`.
- `export_html` (the agent's chat map and hosted maps) and `testView`
  honor the skin too, in the first release. `export_html` already serves
  the `geeView/` folder at `asset_base` and rewrites `./src/` paths to it;
  Delta's page uses the same relative layout (`./delta/...`, `./src/...`),
  so its modules load from the same mount with no inlining and no bundler.
  The auth bootstrap `export_html` injects (access token, project, auth
  proxy placeholders on `urlParams`) is read by Delta's `compat.js` the
  same way. The 25 MB page limit check is unchanged.
- Docs: `Map.setSkin` gets a docstring, an entry in the geeViz docs, and one
  example notebook cell.

## Earth Engine efficiency rules

These come from `charts.py` and are what the port must preserve.

- **One reduction per layer per area.** An ImageCollection is stacked into a
  single multi-band image (`prepare_for_reduction`: per-label mosaic when a
  label has several images, bands named `label----band`, `toBands()` then a
  rename to the known names) and reduced once with `reduceRegion`
  (`bestEffort: true`, `maxPixels: 1e13`, `tileScale: 4`, `crsTransform`
  winning over `scale` when both are set, as `reduce_region` does).
- **Thematic layers** reduce with `frequencyHistogram` and are parsed like
  `parse_thematic_results` (class names, values and palette from the
  `get_obj_info` conventions: `{band}_class_names`, `_class_values`,
  `_class_palette` properties). **Continuous layers** reduce with the same
  reducer the original uses (mean by default) and parse like
  `parse_continuous_results`.
- **Sankey** follows `prepare_sankey_data`: mode per period, a transition
  band per consecutive period pair encoding from and to class, all pairs
  stacked and reduced in a single `frequencyHistogram` `reduceRegion`. Flows
  under the minimum percentage are dropped from the diagram but kept in the
  transition table. The minimum is the layer's `sankeyMinPercentage`,
  defaulting to the original viewer's 0.5 (charts.py's 0.2 is its own
  default, not the viewer's).
- **Inputs come from the viewer, method from charts.py.** Scale, projection
  and grid are what the original viewer passes: the layer's own
  `crs`/`scale`/`transform` when set, otherwise EPSG:5070 on a snapped 30 m
  grid, coarsened when zoomed out exactly as `area-charting.js`
  `autoSetScale` does (2x per zoom level below 11, at most 64x), with
  `minZoomSpecifiedScale` honored. Users see the original's numbers, computed
  the charts.py way. Parity fixtures record these inputs explicitly.
- **Asynchronous only.** `evaluate()` with callbacks or promises; never
  `getInfo()` in the browser. Results for a given (layer, area, scale,
  units) are cached in state so redrawing, theme changes and units changes
  never re-query Earth Engine. Unit changes convert cached pixel counts.
- **Cancel stale work.** A new query point or a new area supersedes pending
  results for the old one; late results are discarded, not rendered.
- **Area units** convert from pixel counts exactly as `charts.py` does
  (hectares, acres; percentage of the area's valid pixels).
- **Which source is the reference for map behavior:** the geeViz-bundled
  `geeView/src/js/lcms-viewer.min.js` and its unminified counterpart in the
  lcms-viewer working tree, not lcms-viewer's `main`. The bundle carries
  geeViz-only fixes ("LOCAL PATCH tile legend v3", "LOCAL PATCH v2
  2026-09-01" close handlers, and the generator's "tile legend v2"); porting
  from `main` alone would bring those bugs back. Each ported function names
  the patch it carries.
- Ports keep the source's function names in comments (for example
  `// port of charts.py prepare_for_reduction`) so later fixes in charts.py
  can be carried over.

## Look

Lineage from the original: charcoal and warm brown neutrals, teal as the
primary accent, condensed uppercase section voice, the globe logo, the
bottom status bar.

- Tokens: dark `#141211` ground, panels `rgba(24,21,20,.86)` with a 14 px
  backdrop blur, ink `#ece8e4`, muted `#a39a93`, teal `#1fd1b4`, orange
  `#ff834c`. Light: ground `#ece8e4`, panels `rgba(250,248,246,.90)`, ink
  `#231d1b`, muted `#6f6259`, teal `#00897b`, orange `#e2602a`. Exact values
  are in the mockup's `:root` blocks.
- Teal marks what is on (layers, the active tool). Orange marks what moves
  or is being drawn (timelapse block and year, query pin, drawn area).
- Type: Barlow Semi Condensed for headings and tool labels, Barlow for body,
  JetBrains Mono for coordinates, years and values (tabular numerals).
- Icons: Tabler. Theme follows the system; the sun/moon button beside the
  title (desktop) or the logo menu (phone) overrides it for the session and
  persists the choice in local storage.

## Layout, desktop

The map fills the window. Both panes overlay it at full height, translucent,
so the map never resizes when a pane changes width.

### Left pane: title, search, layers

- Top: hamburger, logo, "geeViz Delta" (or the `setTitle` title), theme
  button. The hamburger hides the pane; a floating hamburger brings it back.
  Visibility is kept in the url (`showSidebar`), as the original does.
- Search row, one control: go to my location, the Places search box, and the
  previous and next view arrows (the original's view history).
- No "Layers" heading: the pane is the layer list.
- Default width is a third of the window (`clamp(300px, 33.333vw, 560px)`,
  the Bootstrap `col-lg-4` proportion). Drag the edge to resize; width is
  remembered per browser; double-click the edge to reset. Minimum 240 px,
  maximum half the window.

### Layer rows

Each row, left to right: round toggle (hollow off, filled teal on, aligned
under the logo column like the original's radio dots), name, loading
spinner while tiles load, opacity slider, legend toggle.

- Clicking the name also toggles the layer.
- Opacity slider sits on the name's line only when the name fits without
  being cut off; otherwise it drops below the name. Checked per row on
  every pane resize. Inline, it starts at a 64 px minimum and grows one
  pixel for every pixel the pane widens, stopping at 180 px
  (`clamp(64px, 100cqw - 250px, 180px)` of the row). Stacked under the
  name, the same rule runs from 110 px to 240 px. No percentage readout;
  the value is in the slider's tooltip. The track's filled part and the
  handle's center take the slider's own value as their opacity, so the
  control shows the setting.
- Legend toggle is a small swatch of the layer's own colors (up to four
  class colors, the color ramp for continuous layers, the outline for
  vectors) with a small chevron. The legend opens inside the row.
- Turning a layer off folds its legend and, for a timelapse, its whole
  control block, and pauses playback. Turning it back on restores the
  legend to the open or closed state it had.
- Timelapse rows keep every original control: year slider, speed slider
  (fps), back one frame, pause, play, forward one frame, reload failed
  tiles, cumulative mode, and the hidden stop and frame-visibility buttons
  the original exposes when needed. Large year readout. While a timelapse
  plays, the year also shows top center on the map.
- Reorder by dragging the layer name. As in the original, timelapses,
  vector layers and map services cannot be dragged and keep their index
  while other layers move around them; `setCanReorderLayers(False)`
  disables dragging. Dragging changes map z-order and is stored in the url
  (`layerOrders`), as the original does. Legends live in their rows, so they
  always follow the order with no separate legend sort.

### Right pane: tools above tool output

- Four tool buttons in one row: Distance, Area, Query, Chart area. One is
  active at a time. Clicking the active tool turns it off; with no tool on,
  the pane folds to a 64 px vertical strip of the four buttons.
- Units switch for every tool: Metric or Imperial (km, m, ha versus mi, ft,
  acres; elevation in the status bar follows it).
- Active tool's options under the buttons:
  - Distance, Area: one-line instructions.
  - Query: "Double-click the map to query every visible layer at that
    point" (tap on phones).
  - Chart area: "Area from" switch (Draw, Map view, Upload, Select), "Show
    as" switch (Hectares or Acres per the units switch, or % of area;
    percent is a display choice, not a unit), and a settings button for
    which layers to chart (including chart-only layers from
    `addAreaChartLayer`) and the Sankey transition periods. Select uses the
    layers from `addSelectLayer`.
- Output heading with where the result applies (coordinates or "Drawn area,
  412 ha"), jump chips when there are two or more results, then one card per
  result, each collapsible, each with its own actions (CSV, PNG, expand to a
  large modal; copy for single values).
- Chart area produces, per chartable visible layer: a line chart over time
  (a bar chart for a single image, as the original draws) and, for thematic
  time series with transition periods set, a Sankey card.
- `addAreaChartLayer` settings in the first release: `chartType` (`line`,
  `bar`, `stacked-line`, `stacked-bar`), `barChartMaxClasses`,
  `rangeSlider`, `hovermode`, `showGrid`, `chartLabelMaxWidth`,
  `chartLabelMaxLength`, `chartPrecision`, `chartDecimalProportion`,
  `palette`, `thematic`, `reducer`, `yAxisLabel`, `sankeyMinPercentage`,
  `minZoomSpecifiedScale`, with the original's defaults. All of them
  change only chart drawing or reducer choice, so they are cheap to carry;
  none is announced as unsupported.
- Query results always go to the output pane on desktop, including
  `addSelectLayer` selections and the query box (`setQueryBoxColor`,
  `setQueryCRS`). On phones, `setQueryWindowMode("infoWindow")` shows point
  query results in a Google info window; selections stay in the Tools sheet.

### Map chrome

- Zoom in and out, full screen, Street View (bottom right, beside the right
  pane), and basemap thumbnails: Satellite (Google hybrid), Map (roadmap),
  Dark (a styled Google map).
- Google's own map controls are off. The pegman cannot be used: Google only
  places it on the map's edges, which the panes cover. The Street View
  button shows Google's coverage layer; clicking a blue line opens the
  nearest panorama. Entering Street View hides every pane and control, as
  the original does; Google's exit button restores them.
- Thin teal loading line across the top of the map while tiles load.
- Status bar: active tool, cursor coordinates, elevation, zoom, number of
  layers loading.

## Layout, phones (760 px and narrower)

- Floating top bar: logo (opens a menu: Match phone, Light, Dark), go to my
  location, search, previous and next view.
- Bottom bar with two tabs, Layers and Tools. Each opens a bottom sheet
  (about 60% of the screen; tapping its top edge expands it to nearly full);
  only one sheet at a time.
- The basemap is a single thumbnail on the map that expands to the choices.
  Zoom buttons, status bar and resize grips are hidden.
- Opacity always sits under the layer name. Touch targets are enlarged.
- A playing timelapse shows a floating player (year, back, play/pause,
  forward) above the bottom bar when no sheet is open.

## Release stages

- **First release:** everything the Python `Map` object can emit, because
  the maintainer asked for a sweep of every Map method: all layer types
  (Earth Engine images, collections, vectors, GeoJSON, XYZ tiles, Esri
  image, map and feature services, which the generator already turns into
  those types), timelapses, select layers, area-chart-only layers, wind
  layers and wind timelapses, Query, Chart area (Draw, Map view, Upload,
  Select; line, bar and stacked charts; Sankey), Distance and Area, units,
  both themes, phone layout, Street View, Places search, view history,
  `export_html` and `testView`. `Map.setSkin("delta")` available; default
  stays `"original"`.
- JavaScript-only calls Python never emits (`addExport`, `addPlot`,
  `addFeatureView`, a direct `addREST`, `addMBSankey`) are announced as not
  available in Delta. Switching the default skin is a separate decision.

## Testing

- **Parity tests for the ports.** Pure functions (stacking band names,
  parsing histograms, unit conversion, Sankey link building) run under Node
  with fixtures recorded from `charts.py` on fixed inputs and must match
  exactly. Reductions that need Earth Engine run in one live suite, in the
  browser through Playwright with the page's own Earth Engine client,
  comparing Delta's numbers to `charts.py` for a fixed set of cases: LCMS land cover over a
  small polygon, NLCD single image, a continuous NDVI collection, one
  Sankey. Each must be mutation-checked (break the port, see the test fail).
  Running in the page means the client version under test is the one users
  get (`earthengine-api` 0.1.384 today).
- **Sweeps.** Every public method of the Python `Map` has a case that
  builds a map with it and checks its visible effect in Delta (a new method
  without a case fails the sweep), and every example in `geeViz/examples`
  that calls `Map.view()` runs under Delta with no page errors and the same
  layer count as Python added.
- **Contract test.** Every function name on the original `Map2` object
  exists on Delta's `api.js`, either implemented or announced as not yet
  supported; the test fails when the original gains a call Delta lacks.
- **Python.** `Map.setSkin` accepts the two names, rejects others, and
  `Map.view()` writes the same `runGeeViz.js` for both skins and opens the
  right page.
- **Browser checks** (headless Chrome) of the behaviors that broke during
  the mockup: name truncation decides inline opacity; turning a layer off
  folds legend and timelapse controls and back on restores them; pinned
  layers keep their index after a drag; the pane folds with no tool;
  Street View hides and restores the panes; theme follows the system.

## Left to the builder

- File boundaries inside `js/ui/` and `js/engine/` beyond the outline above.
- How state change events are wired (a small emitter is enough).
- Template mechanics (`<template>` cloning or tagged template literals that
  only build markup, never styles).
- Exact chart margins and tick density, within the mockup's look.
