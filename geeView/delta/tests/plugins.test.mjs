// Every layer kind is drawn (and queried) by one plug-in. Earth Engine is one
// plug-in among others, and says which kinds need Earth Engine loaded.
import { test } from "node:test";
import assert from "node:assert/strict";
import { pluginFor, needsEE, PLUGINS } from "../js/plugins/index.js";
import { createMapApi } from "../js/api.js";
import { createStore } from "../js/state.js";

const KINDS = ["ee", "select", "timelapse", "areaChartOnly", "tile", "dynamic", "geojson"];

test("every kind the Map API makes has exactly one plug-in", () => {
  for (const k of KINDS) {
    assert.ok(pluginFor(k).kinds.includes(k), k);
    assert.equal(PLUGINS.filter((p) => p.kinds.includes(k)).length, 1, k);
  }
});

test("needsEE: only Earth Engine kinds", () => {
  for (const k of ["ee", "select", "timelapse", "areaChartOnly"]) assert.equal(needsEE({ kind: k }), true, k);
  for (const k of ["tile", "dynamic", "geojson"]) assert.equal(needsEE({ kind: k }), false, k);
});

test("an unknown kind is an error, not a silent skip", () => {
  assert.throws(() => pluginFor("nope"), /No plug-in for layer kind: nope/);
});

test("the Map API's kinds match", () => {
  const store = createStore();
  const api = createMapApi(store);
  api.addLayer({ type: "FeatureCollection", features: [] }, { layerType: "geoJSONVector" }, "g");
  api.addLayer([{ baseURL: "a", minZoom: 0, ending: "" }, { baseURL: "a", minZoom: 9, ending: "" }], { layerType: "dynamicMapService" }, "d");
  api.addLayer((c, z) => "u", { layerType: "tileMapService" }, "t");
  api.addSerializedLayer({ type: "Invocation" }, { layerType: "geeImage" }, "e", true);
  api.addSerializedTimeLapse({ type: "Invocation" }, {}, "tl", true);
  api.addSerializedSelectLayer({ type: "Invocation" }, {}, "s", true);
  const kinds = store.get().layers.map((l) => l.kind);
  assert.deepEqual(kinds.slice().sort(), ["dynamic", "ee", "geojson", "select", "tile", "timelapse"]);
  kinds.forEach((k) => assert.ok(pluginFor(k)));
});
