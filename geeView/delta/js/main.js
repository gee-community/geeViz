// Delta entry point. Boots the store, the UI shell and the Map API.
//
// Real boot: Google map, Earth Engine, then the generated runGeeViz(), then
// the compat shim is installed with the real api and map so every call queued
// while the page loaded replays in order. `?delta-test=shell` boots a stub
// engine instead (no Google Maps, no Earth Engine) for the shell tests.
import { createStore } from "./state.js";
import { createMapApi } from "./api.js";
import { mountShell, initialShellState } from "./ui/shell.js";
import { mountStatus } from "./ui/status.js";
import { mountMapControls } from "./ui/mapctl.js";
import { mountSearch } from "./ui/search.js";
import { createMap, whenGoogleReady } from "./engine/maps.js";
import { createEELoader } from "./engine/ee.js";
import { createLayerEngine } from "./engine/layers.js";
import { mountLayers } from "./ui/layers.js";
import { mountTimelapseHud } from "./ui/timelapse.js";
import { mountTools } from "./ui/tools.js";
import { mountOutput } from "./ui/output.js";
import { createQueryTool } from "./engine/query.js";
import { createAreaCharter } from "./engine/areachart.js";
import { createAreaSources } from "./engine/areasources.js";
import { createMeasure } from "./engine/measure.js";
import { createCursor } from "./engine/cursor.js";
import { createWind } from "./engine/wind.js";

const store = createStore();
store.set(initialShellState(store), "boot");

const shell = mountShell(store, { mapEl: document.getElementById("map") });
const status = mountStatus(store, document.getElementById("status"), document.getElementById("loadbar"));
// Timelapse controllers live in the layer engine, which starts after Google loads.
let layerEngine = null;
const timelapseOf = (id) => (layerEngine ? layerEngine.timelapse(id) : null);
const layersUI = mountLayers(store, document.getElementById("layers-mount"), {
  timelapse: timelapseOf,
  // the row's failed-tiles button
  retryTiles: (id) => (layerEngine ? layerEngine.retryTiles(id) : 0),
});
const timelapseHud = mountTimelapseHud(store, timelapseOf, {
  badge: document.getElementById("yearbadge"),
  player: document.getElementById("mplayer"),
});

const notice = (msg) => store.update((s) => ({ ...s, notices: [...s.notices, msg] }), "notice");

// Right pane: tool options and output. The query tool starts with the map.
let queryTool = null;
let chartSources = null;
const toolsUI = mountTools(store, {
  optionsEl: document.getElementById("tool-options"),
  unitsEl: document.querySelector("#pane-right .units"),
  chart: () => chartSources,
  measure: () => window.__delta && window.__delta.measure,
  notify: (msg) => store.update((s) => ({ ...s, notices: [...s.notices, msg] }), "notice"),
});
const outputUI = mountOutput(store, {
  mountEl: document.getElementById("results-mount"),
  whereEl: document.getElementById("where"),
  chipsEl: document.getElementById("chips"),
  busyEl: document.getElementById("out-busy"),
  notify: notice,
  query: () => queryTool,
  measure: () => window.__delta && window.__delta.measure,
});
const cssToken = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

function plainText(html) {
  const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
  return (doc.body.textContent || "").trim();
}

async function boot() {
  const delta = (window.__delta = { store, shell, status, layersUI, timelapseHud, toolsUI, outputUI, ready: false, eeError: null });
  try {
    await whenGoogleReady();
  } catch (e) {
    delta.api = createMapApi(store, {});
    notice(String(e.message));
    delta.ready = true;
    return;
  }
  let engine;
  try {
    engine = createMap(document.getElementById("map"), store);
  } catch (e) {
    delta.api = createMapApi(store, {});
    notice("The map could not start: " + (e && e.message));
    delta.ready = true;
    return;
  }
  // Earth Engine loads only for a map with Earth Engine layers: the first one
  // added asks for it (engine/layers.js). Whoever asks first, the result sets
  // the map's Earth Engine state, and a failure is reported once.
  // authProxyAPIURL is compat.js's top-level `let`, which runGeeViz.js reassigns.
  const eeLoader = createEELoader({ urlParams: window.urlParams, proxyUrl: () => authProxyAPIURL });
  const firstEnsure = eeLoader.ensure;
  let eeAsked = false;
  eeLoader.ensure = () => {
    const attempt = firstEnsure();
    if (!eeAsked) {
      eeAsked = true;
      attempt.then(
        () => {
          // geeViz's tag for this map replaces the viewer's own default
          const tag = store.get().eeWorkloadTag;
          if (tag !== null) window.ee.data.setDefaultWorkloadTag(tag);
          engine.setEEReady(true);
        },
        (e) => {
          delta.eeError = String(e && e.message ? e.message : e);
          notice("Earth Engine could not start, so its layers are not shown. " + plainText(delta.eeError));
        }
      );
    }
    return attempt;
  };
  delta.eeLoader = eeLoader;
  try {
    const layers = createLayerEngine(engine.gmap, store, { labels: () => engine.labelsOverlay(), eeLoader });
    layerEngine = layers;
    // A basemap switch swaps the labels overlay's style.
    engine.onBasemap(() => layers.sync());
    // The labels toggle adds or removes the overlay above every layer.
    engine.onLabels(() => layers.sync());
    Object.assign(engine, {
      layers,
      layerAdded: (layer) => layers.addLayerToMap(layer),
      layerRemoved: (layer) => layers.removeLayer(layer),
    });
  } catch (e) {
    notice("The layer engine could not start: " + (e && e.message));
  }
  const api = createMapApi(store, engine);
  Object.assign(delta, { api, engine });
  try {
    const phone = matchMedia("(max-width: 760px)");
    queryTool = createQueryTool(engine, store, {
      isPhone: () => phone.matches,
      notify: notice,
      colors: () => ({ pin: cssToken("--dz-orange", "#e2602a"), pinEdge: cssToken("--dz-on-accent", "#fff"), selection: cssToken("--dz-orange", "#e2602a") }),
    });
    delta.query = queryTool;
    store.on("change:theme", () => setTimeout(() => queryTool.restyle(), 0));
  } catch (e) {
    notice("The query tool could not start: " + (e && e.message));
  }
  try {
    // Chart area: the charter computes and caches, the sources supply areas.
    // Earth Engine loads on demand: charting waits for it rather than failing
    const eeReady = () => (eeLoader.isReady() ? null : eeLoader.ensure());
    const charter = createAreaCharter(store, { ready: eeReady, zoom: () => engine.gmap.getZoom(), notify: notice });
    engine.charter = charter;
    chartSources = createAreaSources(engine, store, charter, {
      ready: eeReady,
      notify: notice,
      query: () => queryTool,
      // uploads are converted by the geeViz server behind this page (compat.js's authProxyAPIURL)
      proxyBase: () => authProxyAPIURL,
      colors: () => ({ stroke: cssToken("--dz-orange", "#e2602a") }),
    });
    Object.assign(delta, { charter, chartSources });
    store.on("change:theme", () => setTimeout(() => chartSources.restyle(), 0));
  } catch (e) {
    notice("The chart area tool could not start: " + (e && e.message));
  }

  try {
    const measure = createMeasure(engine, store, {
      notify: notice,
      colors: () => ({ stroke: cssToken("--dz-orange", "#e2602a") }),
    });
    delta.measure = measure;
    delta.cursor = createCursor(engine.gmap, store);
    store.on("change:theme", () => setTimeout(() => measure.restyle(), 0));
  } catch (e) {
    notice("The distance and area tools could not start: " + (e && e.message));
  }

  for (const [what, mount] of [
    ["map controls", () => mountMapControls(engine, shell, status, notice)],
    ["search", () => mountSearch(engine, { notify: notice })],
  ]) {
    try {
      mount();
    } catch (e) {
      notice("The " + what + " could not start: " + (e && e.message));
    }
  }

  // The map script runs at once: its layers that need Earth Engine wait for it.
  if (typeof window.runGeeViz === "function") {
    try {
      window.runGeeViz();
    } catch (e) {
      notice("The map script failed: " + (e && e.message));
    }
  }

  window.__deltaCompat.install({
    Map: api,
    map: engine.gmap,
    areaChart: api.areaChart,
    synchronousCenterObject: engine.synchronousCenterObject,
    globals: (name, value) => api.setGlobal(name, value),
    showMessage: (title, html) => {
      const text = plainText(html);
      if (text || (title && title !== "Loading")) notice(title ? title + (text ? ": " + text : "") : text);
    },
    closeLoading: () => {},
    notify: notice,
  });
  // View history starts once the map has fully loaded: the map script's calls
  // replayed (install above), every visible layer's first load done and the
  // map at rest. Where the script and its layers settle (centerObject resolves
  // later) is the first view, not a step back.
  startHistoryWhenLoaded(engine, store);
  // Wind layers: wind-particles.js reads the Google map as window.map. Set
  // only now, so calls the map script made while loading stay queued and
  // replay in order.
  if (layerEngine) {
    try {
      window.map = engine.gmap;
      delta.wind = createWind(layerEngine, window.__deltaCompat.layerObj, {
        particleOpacity: (id) => {
          const l = store.get().layers.find((x) => x.id === id);
          return l ? l.particleOpacity : undefined;
        },
      });
      // The particle slider is state only the wind adapter reads.
      store.on("change:layers", () => delta.wind.update());
    } catch (e) {
      notice("Wind layers could not start: " + (e && e.message));
    }
  }
  layersUI.restoreOrder();
  delta.ready = true;
}

if (new URLSearchParams(location.search).get("delta-test") === "shell") {
  // The stub engine has no hooks: every engine call is ignored.
  const engine = {};
  const api = createMapApi(store, engine);
  window.__delta = { store, api, engine, shell, status, layersUI, toolsUI, outputUI, ready: true };
} else {
  boot();
}

// Polls until no visible layer is loading and the map has not moved for a
// moment, then starts the view history (after 60 s it starts regardless).
function startHistoryWhenLoaded(engine, store, { rest = 400, cap = 60000 } = {}) {
  const t0 = Date.now();
  let lastMove = Date.now();
  const g = window.google.maps;
  const moved = g.event.addListener(engine.gmap, "bounds_changed", () => (lastMove = Date.now()));
  const tick = () => {
    const busy = store.get().layers.some((l) => l.visible && l.loading);
    const still = Date.now() - lastMove >= rest;
    if ((!busy && still) || Date.now() - t0 > cap) {
      g.event.removeListener(moved);
      engine.startHistory();
      return;
    }
    setTimeout(tick, 150);
  };
  tick();
}
