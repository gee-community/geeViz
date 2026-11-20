// The Map contract: every method of the original viewer's `mp` object, mapped
// to store changes. This is the single place that translates original call
// signatures into Delta state. Serialized EE items are kept as given; the
// engine deserializes them later.
//
// `engine` is an object of optional hooks (layerAdded, layerRemoved,
// setCenter, centerObject, synchronousCenterObject, showSpinner,
// hideSpinner, populateChartLayerSelect, ...). Missing hooks are ignored.

const UNSUPPORTED = ["addExport", "addPlot", "addFeatureView", "addREST", "addMBSankey", "addSelectLayerGroup"];

// Every layer type draws in the one tile stack (vectors and dynamic map
// services as tiles, a timelapse frame by frame), so any layer can be dragged.
// The original pinned vectors, dynamic services and timelapses, which it drew
// above the tile layers. Only Map.canReorderLayers = false pins them all.
function isPinned(layer, canReorder) {
  return !canReorder;
}

function kindFor(item, viz) {
  const t = viz && viz.layerType;
  if (t === "geoJSONVector") return "geojson";
  if (t === "dynamicMapService") return "dynamic";
  if (t === "tileMapService" || typeof item === "function") return "tile";
  return "ee";
}

function serialize(viz) {
  viz = viz || {};
  viz.serialized = true;
  return viz;
}

export function createMapApi(store, engine = {}) {
  let counter = 0;
  const hook = (name, ...args) => {
    const fn = engine && engine[name];
    return typeof fn === "function" ? fn(...args) : undefined;
  };
  const patchQuery = (patch, reason) =>
    store.update((s) => ({ ...s, query: { ...s.query, ...patch } }), reason);
  const notice = (msg) => store.update((s) => ({ ...s, notices: [...s.notices, msg] }), "notice");
  const setTool = (tool, areaFrom, reason) =>
    store.set(areaFrom ? { tool, areaFrom } : { tool }, reason);
  const clearTool = (tool, reason) => {
    if (store.get().tool === tool) store.set({ tool: null }, reason);
  };

  function makeLayer(kind, item, viz, name, visible, extra = {}) {
    viz = viz || {};
    const layer = {
      id: "layer-" + ++counter,
      name: name == null ? "Layer " + counter : String(name),
      kind,
      item,
      viz,
      // port of 4map-manager.js addTimeLapseToMap: "Force time lapses to be
      // turned off on load to speed up loading" (visible = false).
      visible: kind === "timelapse" ? false : visible === undefined || visible === null ? true : !!visible,
      opacity: typeof viz.opacity === "number" ? viz.opacity : 1,
      legendOpen: false,
      pinned: false,
      loading: false,
      error: null,
      legend: null,
      timelapse: kind === "timelapse" ? {} : null,
      chartable: !!viz.canAreaChart,
      // port of 4map-manager.js addSelectLayerToMap: select layers set canQuery = false
      queryable: viz.canQuery !== false && kind !== "areaChartOnly" && kind !== "select",
      ...extra,
    };
    layer.pinned = isPinned(layer, store.get().canReorder);
    return layer;
  }

  function push(layer) {
    store.update(
      (s) => ({
        ...s,
        layers: [...s.layers, layer],
        order: layer.kind === "areaChartOnly" ? s.order : [layer.id, ...s.order],
      }),
      "addLayer"
    );
    hook("layerAdded", layer);
    return layer;
  }

  function repin() {
    store.update(
      (s) => ({ ...s, layers: s.layers.map((l) => ({ ...l, pinned: isPinned(l, s.canReorder) })) }),
      "repin"
    );
  }

  const api = {};

  api.addLayer = (item, viz, name, visible) => {
    viz = viz || {};
    push(makeLayer(kindFor(item, viz), item, viz, name, visible));
  };
  api.addSerializedLayer = (item, viz, name, visible) => {
    viz = serialize(viz);
    push(makeLayer(kindFor(item, viz), item, viz, name, visible));
  };
  api.addTimeLapse = (item, viz, name, visible) => {
    push(makeLayer("timelapse", item, viz || {}, name, visible));
  };
  api.addSerializedTimeLapse = (item, viz, name, visible) => {
    viz = serialize(viz);
    push(makeLayer("timelapse", item, viz, name, visible));
  };
  api.addSelectLayer = (item, viz, name, visible) => {
    api.selectLayerAdded = true;
    push(makeLayer("select", item, viz || {}, name, visible));
  };
  api.addSerializedSelectLayer = (item, viz, name, visible) => {
    viz = serialize(viz);
    api.selectLayerAdded = true;
    api.showSelectLayerAreaCharting();
    push(makeLayer("select", item, viz, name, visible));
  };
  api.selectLayerAdded = false;
  api.hideSelectLayerAreaCharting = () => hook("hideSelectLayerAreaCharting");
  api.showSelectLayerAreaCharting = () => hook("showSelectLayerAreaCharting");

  api.removeLayer = (layerId) => {
    const found = store.get().layers.find((l) => l.id === layerId || l.name === layerId);
    if (!found) return;
    store.update(
      (s) => ({
        ...s,
        layers: s.layers.filter((l) => l !== found),
        order: s.order.filter((id) => id !== found.id),
      }),
      "removeLayer"
    );
    hook("layerRemoved", found);
  };

  for (const name of UNSUPPORTED) {
    api[name] = () => notice(name + ' is not available in Delta yet. Use Map.setSkin("original") for this map.');
  }

  api.centerObject = (fc, async = true, callback) => hook("centerObject", fc, async, callback);
  api.synchronousCenterObject = (boundsInfo) => hook("synchronousCenterObject", boundsInfo);
  api.setCenter = (lng, lat, zoom) => hook("setCenter", lng, lat, zoom);
  api.setTitle = (title) => store.set({ title }, "setTitle");

  api.turnOnInspector = () => setTool("query", null, "turnOnInspector");
  api.turnOffInspector = () => clearTool("query", "turnOffInspector");
  api.turnOnAutoAreaCharting = () => setTool("chart", "view", "turnOnAutoAreaCharting");
  api.turnOffAutoAreaCharting = () => clearTool("chart", "turnOffAutoAreaCharting");
  api.turnOnUserDefinedAreaCharting = () => setTool("chart", "draw", "turnOnUserDefinedAreaCharting");
  api.turnOffUserDefinedAreaCharting = () => clearTool("chart", "turnOffUserDefinedAreaCharting");
  api.turnOnSelectionAreaCharting = () => setTool("chart", "select", "turnOnSelectionAreaCharting");
  api.turnOffSelectionAreaCharting = () => clearTool("chart", "turnOffSelectionAreaCharting");
  // port of 4map-manager.js turnOnTimeSeriesCharting: it toggles the Pixel
  // Tools time series tool, which is Delta's Query tool.
  api.turnOnTimeSeriesCharting = () => setTool("query", null, "turnOnTimeSeriesCharting");
  api.turnOffTimeSeriesCharting = () => clearTool("query", "turnOffTimeSeriesCharting");

  api.setQueryCRS = (crs) => patchQuery({ crs }, "setQueryCRS");
  api.setQueryScale = (scale) => patchQuery({ scale, transform: null }, "setQueryScale");
  api.setQueryTransform = (transform) => patchQuery({ transform, scale: null }, "setQueryTransform");
  api.setQueryPrecision = (chartPrecision = 3, chartDecimalProportion = 0.25) =>
    patchQuery({ precision: { chartPrecision, chartDecimalProportion } }, "setQueryPrecision");
  api.setQueryDateFormat = (dateFormat) => patchQuery({ dateFormat }, "setQueryDateFormat");
  api.setQueryBoxColor = (color) => {
    if (typeof color === "string" && /^[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(color)) color = "#" + color;
    patchQuery({ boxColor: color }, "setQueryBoxColor");
  };

  // Every layer in the layer list on or off (not select or area-chart-only layers).
  const setAllVisible = (visible, reason) =>
    store.update(
      (s) => ({ ...s, layers: s.layers.map((l) => (l.kind === "select" || l.kind === "areaChartOnly" ? l : { ...l, visible })) }),
      reason
    );
  api.turnOffAllLayers = () => setAllVisible(false, "turnOffAllLayers");
  api.turnOnAllLayers = () => setAllVisible(true, "turnOnAllLayers");

  api.showSpinner = () => hook("showSpinner");
  api.hideSpinner = () => hook("hideSpinner");

  // Properties the generated script assigns (Map.canReorderLayers = false;).
  Object.defineProperty(api, "canReorderLayers", {
    enumerable: true,
    get: () => store.get().canReorder,
    set: (v) => {
      store.set({ canReorder: !!v }, "canReorderLayers");
      repin();
    },
  });
  Object.defineProperty(api, "turnOffLayersWhenTimeLapseIsOn", {
    enumerable: true,
    get: () => store.get().turnOffLayersWhenTimeLapseIsOn,
    set: (v) => store.set({ turnOffLayersWhenTimeLapseIsOn: !!v }, "turnOffLayersWhenTimeLapseIsOn"),
  });

  // Bare globals the generated script assigns (queryWindowMode = "..."; yLabelMaxLength = 20).
  api.setGlobal = (name, value) => {
    if (name === "queryWindowMode") patchQuery({ windowMode: value }, "queryWindowMode");
    else if (/^yLabel/.test(name))
      store.update((s) => ({ ...s, chartSettings: { ...s.chartSettings, [name]: value } }), name);
  };

  // `areaChart` global: layers used only for area charting.
  api.areaChart = {
    addLayer: (item, viz, name, visible) => {
      viz = viz || {};
      push(makeLayer("areaChartOnly", item, viz, name, visible, { chartable: true }));
    },
    addSerializedLayer: (item, viz, name, visible) => {
      viz = serialize(viz);
      push(makeLayer("areaChartOnly", item, viz, name, visible, { chartable: true }));
    },
    populateChartLayerSelect: () => hook("populateChartLayerSelect"),
  };

  return api;
}
