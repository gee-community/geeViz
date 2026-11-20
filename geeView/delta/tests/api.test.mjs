import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createStore } from "../js/state.js";
import { createMapApi } from "../js/api.js";

const COMPAT = fs.readFileSync(new URL("../js/compat.js", import.meta.url), "utf8");

// Hand-written copy of what geeView._build_run_js emits (replaced by generated
// fixtures in Task 8).
const RUN_JS = `try{authProxyAPIURL=window.location.origin+'/ee-api/t/x';}catch(e){}var layerLoadErrorMessages=[];showMessage('Loading',staticTemplates.loadingModal[mode]);function runGeeViz(){try{ee.data.setDefaultWorkloadTag("");}catch(e){}try{ee.data.resetWorkloadTag();}catch(e){}try{ee.data.resetWorkloadTag();}catch(e){}Map.addSerializedLayer({"result":"0","values":{"0":{"functionInvocationValue":{"functionName":"Image.load"}}}},{"min":0,"max":1,"canAreaChart":true},"Layer A",true);try{ee.data.resetWorkloadTag();}catch(e){}Map.addSerializedTimeLapse({"result":"0","values":{}},{"min":0,"max":1,"layerType":"ImageCollection"},"Time A",false);Map.addSerializedSelectLayer({"result":"0","values":{}},{"strokeColor":"00F"},"Select A",false);areaChart.addLayer({"result":"0","values":{}},{"sankey":true},"Chart A",true);try{ee.data.resetWorkloadTag();}catch(e){}if(layerLoadErrorMessages.length>0){showMessage("Map.addLayer Error List",layerLoadErrorMessages.join("<br>"));};setTimeout(function(){if(layerLoadErrorMessages.length===0){$('#close-modal-button').click();}}, 2500);Map.setCenter(-111,41,10);map.setZoom(9);synchronousCenterObject({"type":"Polygon","coordinates":[]});Map.turnOnInspector();Map.setQueryScale(30);Map.setTitle("x");areaChart.populateChartLayerSelect();yLabelMaxLength = 20;Map.canReorderLayers = false;;queryWindowMode = "sidePane";Map.turnOffLayersWhenTimeLapseIsOn = false;localStorage['showToolTipModal-geeViz']=false;};`;

function makeContext(search = "") {
  const timers = [];
  const ctx = {
    console,
    setTimeout: (fn) => timers.push(fn),
    localStorage: { setItem() {} },
    location: { search, origin: "http://localhost" },
    document: { title: "" },
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(COMPAT, ctx);
  return { ctx, timers };
}

function installApi(ctx, store, engine = {}) {
  const api = createMapApi(store, engine);
  const sink = { messages: [], closed: 0 };
  ctx.__deltaCompat.install({
    Map: api,
    areaChart: api.areaChart,
    synchronousCenterObject: api.synchronousCenterObject,
    map: { setZoom(z) { sink.zoom = z; } },
    globals: (n, v) => api.setGlobal(n, v),
    showMessage: (t, h) => sink.messages.push([t, h]),
    closeLoading: () => sink.closed++,
    notify: (m) => store.update((s) => ({ ...s, notices: [...s.notices, m] }), "notice"),
  });
  return { api, sink };
}

test("recorded Python call sequence replays into the store", () => {
  const { ctx, timers } = makeContext("?a=1");
  vm.runInContext(RUN_JS, ctx);
  const store = createStore();
  const { sink } = installApi(ctx, store);
  vm.runInContext("runGeeViz()", ctx);
  timers.forEach((f) => f());
  const s = store.get();
  assert.equal(s.layers.filter((l) => l.kind !== "areaChartOnly").length, 3);
  assert.deepEqual(s.layers.map((l) => l.name), ["Layer A", "Time A", "Select A", "Chart A"]);
  assert.deepEqual(s.layers.map((l) => l.kind), ["ee", "timelapse", "select", "areaChartOnly"]);
  assert.equal(s.layers[1].pinned, true);
  assert.equal(s.tool, "query");
  assert.equal(s.query.scale, 30);
  assert.equal(s.title, "x");
  assert.equal(s.canReorder, false);
  assert.equal(s.turnOffLayersWhenTimeLapseIsOn, false);
  assert.equal(s.query.windowMode, "sidePane");
  assert.equal(s.chartSettings.yLabelMaxLength, 20);
  assert.equal(sink.zoom, 9);
  assert.equal(sink.closed, 1);
  assert.deepEqual(s.notices, []);
});

test("calls made after install go straight to the api", () => {
  const { ctx } = makeContext();
  const store = createStore();
  installApi(ctx, store);
  vm.runInContext('Map.addLayer({}, {}, "Late", true)', ctx);
  assert.equal(store.get().layers.length, 1);
});

test("urlParams preserves bootstrap values and parses the query string", () => {
  const ctx = { console, setTimeout() {}, location: { search: "?a=1&b=two" }, document: {}, localStorage: {}, urlParams: { b: "keep", c: 3 } };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(COMPAT, ctx);
  assert.equal(ctx.urlParams.a, "1");
  assert.equal(ctx.urlParams.b, "keep");
  assert.equal(ctx.urlParams.c, 3);
});

test("other jQuery selectors announce", () => {
  const { ctx } = makeContext();
  const store = createStore();
  installApi(ctx, store);
  vm.runInContext("$('#something').show()", ctx);
  assert.equal(store.get().notices.length, 1);
});

test("wind-particles.js lookups of a wind layer's panel elements find nothing, quietly", () => {
  const { ctx } = makeContext();
  const store = createStore();
  installApi(ctx, store);
  // compat.js's layerObj is the lexical binding wind-particles.js reads.
  assert.equal(vm.runInContext("layerObj === __deltaCompat.layerObj", ctx), true);
  vm.runInContext("layerObj['layer-1'] = {viz: {}}; layerObj['layer-2-frame-0'] = {viz: {timeLapseID: 'layer-2'}};", ctx);
  vm.runInContext(
    "$('#layer-1-spinner2').show(); $('#layer-1-layer-container').css('background', 'x');" +
      "if ($('#layer-2-class-container').find('li').first().length !== 0) throw new Error('not empty');" +
      "if ($('#layer-2-opacity-slider').length !== 0) throw new Error('not empty');" +
      "$().empty();",
    ctx
  );
  assert.equal(store.get().notices.length, 0);
  // Anything else still announces.
  vm.runInContext("$('#layer-3-spinner2').show()", ctx);
  assert.equal(store.get().notices.length, 1);
});

test("unsupported calls announce", () => {
  const { ctx } = makeContext();
  const store = createStore();
  installApi(ctx, store);
  vm.runInContext("Map.addPlot([0,0])", ctx);
  const n = store.get().notices;
  assert.equal(n.length, 1);
  assert.ok(n[0].includes("addPlot"));
  assert.equal(n[0], 'addPlot is not available in Delta yet. Use Map.setSkin("original") for this map.');
});

test("canReorder false pins every layer, including later ones", () => {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addLayer({}, {}, "A", true);
  api.canReorderLayers = false;
  api.addLayer({}, {}, "B", true);
  assert.ok(store.get().layers.every((l) => l.pinned));
});

test("removeLayer, query setters and engine hooks", () => {
  const calls = [];
  const store = createStore();
  const api = createMapApi(store, { setCenter: (...a) => calls.push(["setCenter", a]) });
  api.addLayer({}, { layerType: "geeVector" }, "V", true);
  // vectors draw in the tile stack, so they move with the list like any layer
  assert.equal(store.get().layers[0].pinned, false);
  const id = store.get().layers[0].id;
  assert.deepEqual(store.get().order, [id]);
  api.removeLayer(id);
  assert.equal(store.get().layers.length, 0);
  assert.deepEqual(store.get().order, []);
  api.setQueryTransform([30, 0, 0, 0, -30, 0]);
  assert.equal(store.get().query.scale, null);
  api.setQueryScale(10);
  assert.equal(store.get().query.transform, null);
  api.turnOnUserDefinedAreaCharting();
  assert.equal(store.get().tool, "chart");
  assert.equal(store.get().areaFrom, "draw");
  api.turnOffUserDefinedAreaCharting();
  assert.equal(store.get().tool, null);
  // port of 4map-manager.js turnOnTimeSeriesCharting: the Pixel Tools time
  // series tool is Delta's Query tool, not Chart area
  api.turnOnTimeSeriesCharting();
  assert.equal(store.get().tool, "query");
  api.turnOffTimeSeriesCharting();
  assert.equal(store.get().tool, null);
  api.turnOnAutoAreaCharting();
  assert.deepEqual([store.get().tool, store.get().areaFrom], ["chart", "view"]);
  api.turnOffTimeSeriesCharting();
  assert.equal(store.get().tool, "chart", "turning off time series leaves Chart area alone");
  api.turnOnSelectionAreaCharting();
  assert.deepEqual([store.get().tool, store.get().areaFrom], ["chart", "select"]);
  api.turnOffAutoAreaCharting();
  assert.equal(store.get().tool, null);
  api.setCenter(-111, 41, 10);
  assert.deepEqual(calls, [["setCenter", [-111, 41, 10]]]);
});

test("native Map constructor survives, before and after install", () => {
  const { ctx } = makeContext();
  assert.equal(vm.runInContext("new Map([[1,2]]).get(1)", ctx), 2);
  assert.equal(vm.runInContext("typeof Map.addLayer", ctx), "function");
  installApi(ctx, createStore());
  assert.equal(vm.runInContext("new Map([[1,2]]).get(1)", ctx), 2);
});

test("Map.addLayer queues before install and forwards after", () => {
  const { ctx } = makeContext();
  vm.runInContext('Map.addLayer({}, {}, "Early", true)', ctx);
  const store = createStore();
  installApi(ctx, store);
  assert.deepEqual(store.get().layers.map((l) => l.name), ["Early"]);
  vm.runInContext('Map.addLayer({}, {}, "Late", true)', ctx);
  assert.deepEqual(store.get().layers.map((l) => l.name), ["Early", "Late"]);
});

test("data properties set before install reach the store", () => {
  const { ctx } = makeContext();
  vm.runInContext("Map.turnOffLayersWhenTimeLapseIsOn = false; Map.canReorderLayers = false;", ctx);
  assert.equal(vm.runInContext("Map.turnOffLayersWhenTimeLapseIsOn", ctx), false);
  assert.equal(vm.runInContext("typeof Map.canReorderLayers", ctx), "boolean");
  const store = createStore();
  installApi(ctx, store);
  assert.equal(store.get().turnOffLayersWhenTimeLapseIsOn, false);
  assert.equal(store.get().canReorder, false);
  vm.runInContext("Map.turnOffLayersWhenTimeLapseIsOn = true", ctx);
  assert.equal(store.get().turnOffLayersWhenTimeLapseIsOn, true);
  assert.equal(vm.runInContext("Map.turnOffLayersWhenTimeLapseIsOn", ctx), true);
});

test("a failing queued call announces and does not abort replay", () => {
  const { ctx } = makeContext();
  vm.runInContext('map.noSuchThing(); Map.addLayer({}, {}, "After", true)', ctx);
  const store = createStore();
  const api = createMapApi(store, {});
  ctx.__deltaCompat.install({
    Map: api,
    map: {},
    notify: (m) => store.update((s) => ({ ...s, notices: [...s.notices, m] }), "notice"),
  });
  assert.equal(store.get().layers.length, 1);
  assert.equal(store.get().notices.length, 1);
  assert.ok(store.get().notices[0].includes("noSuchThing"));
});

test("compat defines a static for every original Map method", { skip: !fs.existsSync(new URL("../../../../lcms-viewer/src/js/4map-manager.js", import.meta.url)) && "lcms-viewer checkout not found" }, () => {
  const text = fs.readFileSync(new URL("../../../../lcms-viewer/src/js/4map-manager.js", import.meta.url), "utf8");
  const body = text.slice(text.indexOf("function mp()"), text.indexOf("const Map2 = new mp()"));
  const { ctx } = makeContext();
  for (const m of body.matchAll(/this\.([A-Za-z_$][\w$]*)\s*=\s*function/g)) {
    assert.equal(vm.runInContext("typeof Map." + m[1], ctx), "function", m[1]);
  }
});

test("timelapses start off whatever visible says (4map-manager.js addTimeLapseToMap visible = false)", () => {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addTimeLapse({}, {}, "T1", true);
  api.addSerializedTimeLapse({}, {}, "T2", true);
  api.addTimeLapse({}, {}, "T3");
  api.addLayer({}, {}, "L", true);
  const vis = Object.fromEntries(store.get().layers.map((l) => [l.name, l.visible]));
  assert.deepEqual(vis, { T1: false, T2: false, T3: false, L: true });
});
