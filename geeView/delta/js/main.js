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
import { initEE, describeEEFailure } from "./engine/ee.js";
import { createLayerEngine } from "./engine/layers.js";
import { mountLayers } from "./ui/layers.js";
import { mountTimelapseHud } from "./ui/timelapse.js";
import { mountTools } from "./ui/tools.js";
import { mountOutput } from "./ui/output.js";
import { createQueryTool } from "./engine/query.js";
import { createAreaCharter } from "./engine/areachart.js";
import { createAreaSources } from "./engine/areasources.js";

const store = createStore();
store.set(initialShellState(store), "boot");

const shell = mountShell(store, { mapEl: document.getElementById("map") });
const status = mountStatus(store, document.getElementById("status"), document.getElementById("loadbar"));
// Timelapse controllers live in the layer engine, which starts after Google loads.
let layerEngine = null;
const timelapseOf = (id) => (layerEngine ? layerEngine.timelapse(id) : null);
const layersUI = mountLayers(store, document.getElementById("layers-mount"), { timelapse: timelapseOf });
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
  notify: (msg) => store.update((s) => ({ ...s, notices: [...s.notices, msg] }), "notice"),
});
const outputUI = mountOutput(store, {
  mountEl: document.getElementById("results-mount"),
  whereEl: document.getElementById("where"),
  chipsEl: document.getElementById("chips"),
  busyEl: document.getElementById("out-busy"),
  notify: notice,
  query: () => queryTool,
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
  try {
    const layers = createLayerEngine(engine.gmap, store);
    layerEngine = layers;
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
    const charter = createAreaCharter(store, { ee: window.ee, zoom: () => engine.gmap.getZoom(), notify: notice });
    engine.charter = charter;
    chartSources = createAreaSources(engine, store, charter, {
      notify: notice,
      query: () => queryTool,
      colors: () => ({ stroke: cssToken("--dz-orange", "#e2602a") }),
    });
    Object.assign(delta, { charter, chartSources });
    store.on("change:theme", () => setTimeout(() => chartSources.restyle(), 0));
  } catch (e) {
    notice("The chart area tool could not start: " + (e && e.message));
  }

  for (const [what, mount] of [
    ["map controls", () => mountMapControls(engine, shell, status)],
    ["search", () => mountSearch(engine, { notify: notice })],
  ]) {
    try {
      mount();
    } catch (e) {
      notice("The " + what + " could not start: " + (e && e.message));
    }
  }

  try {
    // authProxyAPIURL is compat.js's top-level `let`, which runGeeViz.js reassigns.
    await initEE(window.urlParams, () => authProxyAPIURL);
    engine.setEEReady(true);
  } catch (e) {
    delta.eeError = String(e && e.message ? e.message : e);
    notice(plainText(describeEEFailure(e, window.urlParams)));
  }

  if (!delta.eeError && typeof window.runGeeViz === "function") {
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
