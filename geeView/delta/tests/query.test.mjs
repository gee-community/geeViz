import { test } from "node:test";
import assert from "node:assert/strict";
import { smartToFixed, tokenSource } from "../js/util.js";
import {
  queryInputs,
  plotRadius,
  imageResult,
  seriesResult,
  tableResults,
  breakLabels,
  resultCsv,
  resultText,
  queryPoint,
  pickNameProperty,
  isInfoWindowMode,
} from "../js/engine/query.js";
import { defaultState } from "../js/state.js";

const PT = { lng: -111.527, lat: 40.504 };

test("smartToFixed: port of 1variables.js smartToFixed", () => {
  assert.equal(smartToFixed(5), 5);
  assert.equal(smartToFixed("abc"), "abc");
  assert.equal(smartToFixed(1.23456789), 1.235);
  // 16 decimals * 0.25 = 4 > 3
  assert.equal(smartToFixed(0.1234567890123456), 0.1235);
  assert.equal(smartToFixed(1.5, 0.25, 0), 1.5);
});

test("tokenSource: tokens from one source supersede each other only", () => {
  const a = tokenSource();
  const b = tokenSource();
  const a1 = a();
  const b1 = b();
  assert.equal(a1.isCurrent(), true);
  const a2 = a();
  assert.equal(a1.isCurrent(), false);
  assert.equal(a2.isCurrent(), true);
  assert.equal(b1.isCurrent(), true);
});

test("query defaults are the original's (1variables.js crs, transform, scale)", () => {
  const q = defaultState().query;
  assert.equal(q.crs, "EPSG:5070");
  assert.deepEqual(q.transform, [30, 0, -2361915.0, 0, -30, 3177735.0]);
  assert.equal(q.scale, null);
});

test("queryInputs: transform wins over scale; plotRadius follows them", () => {
  const t = [30, 0, -2361915.0, 0, -30, 3177735.0];
  assert.deepEqual(queryInputs({ crs: "EPSG:5070", scale: 30, transform: t }), { crs: "EPSG:5070", scale: null, crsTransform: t });
  assert.deepEqual(queryInputs({ crs: "EPSG:5070", scale: 120, transform: null }), { crs: "EPSG:5070", scale: 120, crsTransform: null });
  assert.equal(plotRadius({ scale: 120, transform: null }), 60);
  assert.equal(plotRadius({ scale: null, transform: t }), 15);
  assert.equal(plotRadius({ scale: null, transform: null }), 15);
});

const LC_VIZ = {
  bands: "Land_Cover",
  queryDict: { 1: "Trees", 3: "Shrubs & Trees Mix" },
  class_values: { Land_Cover: [1, 3] },
  class_palette: { Land_Cover: ["005e00", "008000"] },
};

test("imageResult: single band with a class dictionary gives the class name and color", () => {
  const r = imageResult({ id: "layer-2", name: "LC" }, LC_VIZ, { Land_Cover: 1 }, PT);
  assert.equal(r.kind, "value");
  assert.equal(r.layerId, "layer-2");
  assert.equal(r.title, "LC");
  assert.deepEqual(r.actions, ["copy"]);
  assert.equal(r.data.bands.length, 1);
  assert.deepEqual(r.data.bands[0], { band: "Land_Cover", value: 1, display: "1", label: "Trees", color: "#005e00" });
  assert.deepEqual(r.data.point, PT);
});

test("imageResult: floats are rounded for display only; null is no data", () => {
  const r = imageResult({ id: "l", name: "N" }, {}, { a: 0.1234567, b: null }, PT);
  assert.equal(r.data.bands[0].value, 0.1234567);
  assert.equal(r.data.bands[0].display, "0.123");
  assert.equal(r.data.bands[1].value, null);
  const none = imageResult({ id: "l", name: "N" }, {}, null, PT);
  assert.equal(none.data.bands.length, 0);
  assert.equal(none.meta, "No data");
});

test("imageResult: an RGB-visualized query keeps only the main band (port of makeQueryTable)", () => {
  const r = imageResult({ id: "l", name: "N" }, {}, { NBR: 0.5, "viz-red": 1, "viz-green": 2, "viz-blue": 3 }, PT);
  assert.deepEqual(r.data.bands.map((b) => b.band), ["NBR"]);
});

test("seriesResult: values are matched to images by name, not position", () => {
  const out = {
    ids: ["y1985", "y1986", "y1987"],
    labels: ["1985-06-01", "1986-06-01", "1987-06-01"],
    bands: ["Land_Cover"],
    // y1986 has no value (masked), keys arrive unordered
    values: { y1987_Land_Cover: 3, y1985_Land_Cover: 1, y1986_Land_Cover: null },
    hasTime: true,
  };
  const r = seriesResult({ id: "l", name: "LC" }, LC_VIZ, out, PT);
  assert.equal(r.kind, "series");
  assert.deepEqual(r.actions, ["csv", "png", "expand"]);
  assert.deepEqual(r.data.x, out.labels);
  assert.equal(r.data.xLabel, "Time");
  assert.equal(r.data.series.length, 1);
  assert.deepEqual(r.data.series[0].y, [1, null, 3]);
  assert.deepEqual(r.data.series[0].labels, ["Trees", null, "Shrubs & Trees Mix"]);
  assert.equal(r.meta, "1985-06-01 to 1987-06-01");
  assert.deepEqual(r.data.latest, { x: "1987-06-01", band: "Land_Cover", value: 3, label: "Shrubs & Trees Mix", color: "#008000" });
});

test("seriesResult: no images gives an empty series card", () => {
  const r = seriesResult({ id: "l", name: "LC" }, {}, { ids: [], labels: [], bands: [], values: {}, hasTime: false }, PT);
  assert.equal(r.data.series.length, 0);
  assert.equal(r.meta, "No data");
});

test("tableResults: one table per feature; none gives one empty table", () => {
  const fc = { features: [{ id: "0", properties: { name: "A", Acres: 12345.678 } }, { id: "1", properties: { name: "B" } }] };
  const rs = tableResults({ id: "v", name: "V" }, fc, PT);
  assert.equal(rs.length, 2);
  assert.equal(rs[0].kind, "table");
  assert.deepEqual(rs[0].data.rows[0], ["name", "A"]);
  assert.deepEqual(rs[0].data.rows[1], ["Acres", "12,345.678"]);
  assert.notEqual(rs[0].id, rs[1].id);
  const empty = tableResults({ id: "v", name: "V" }, { features: [] }, PT);
  assert.equal(empty.length, 1);
  assert.deepEqual(empty[0].data.rows, []);
});

test("breakLabels: port of the time series y label breaking", () => {
  const out = breakLabels(["Grass/Forb/Herb & Trees Mix"], { yLabelMaxLength: 30, yLabelBreakLength: 10, yLabelMaxLines: 5 });
  assert.deepEqual(out, ["Grass/Forb<br>/Herb & Tr<br>ees Mix"]);
  const capped = breakLabels(["abcdefghijklmnopqrstuvwxyz"], { yLabelMaxLength: 30, yLabelBreakLength: 10, yLabelMaxLines: 2 });
  assert.deepEqual(capped, ["abcdefghij<br>klmnopqrst"]);
});

test("resultCsv and resultText", () => {
  const s = seriesResult(
    { id: "l", name: "LC" },
    LC_VIZ,
    { ids: ["a", "b"], labels: ["2001", "2002"], bands: ["Land_Cover"], values: { a_Land_Cover: 1, b_Land_Cover: 3 }, hasTime: true },
    PT
  );
  assert.equal(resultCsv(s), "Time,Land_Cover\n2001,1\n2002,3\n");
  const v = imageResult({ id: "l", name: "LC" }, LC_VIZ, { Land_Cover: 1 }, PT);
  assert.equal(resultText(v), "LC: Trees (1)");
  const t = tableResults({ id: "v", name: "V" }, { features: [{ id: "0", properties: { n: 'a,"b"' } }] }, PT)[0];
  assert.equal(resultCsv(t), 'Property,Value\nn,"a,""b"""\n');
});

test("pickNameProperty: selectLayerNameProperty, else the last name-like property, else the id", () => {
  assert.equal(pickNameProperty({ selectLayerNameProperty: "nm" }, { nm: "x", NAME: "y" }), "nm");
  assert.equal(pickNameProperty({}, { FORESTNAME: "x", other: 1, PARKNAME: "p" }), "PARKNAME");
  assert.equal(pickNameProperty({}, { other: 1 }), null);
});

test("isInfoWindowMode accepts the original's spellings", () => {
  assert.equal(isInfoWindowMode("infoWindow"), true);
  assert.equal(isInfoWindowMode("sidePane"), false);
  assert.equal(isInfoWindowMode("sidepane"), false);
});

// A fake Earth Engine with controllable evaluate() callbacks: enough for the image path.
function fakeEE() {
  const pending = [];
  const calls = [];
  const ee = {
    Geometry: { Point: (c) => ({ point: c, buffer: () => ({ bounds: () => ({}) }) }) },
    Reducer: { first: () => "first" },
    Image: (img) => ({
      reduceRegion: (...args) => {
        calls.push({ img, args });
        return { evaluate: (cb) => pending.push({ img, cb }) };
      },
    }),
  };
  return { ee, pending, calls };
}

function fakeEngine(targets) {
  return { layers: { queryTarget: (id) => Promise.resolve(targets[id] || null) } };
}

const LAYERS = [
  { id: "a", name: "A", visible: true, queryable: true, kind: "ee" },
  { id: "b", name: "B", visible: true, queryable: true, kind: "ee" },
  { id: "c", name: "C", visible: false, queryable: true, kind: "ee" },
  { id: "d", name: "D", visible: true, queryable: false, kind: "ee" },
];
const TARGETS = {
  a: { type: "geeImage", item: "imgA", viz: {} },
  b: { type: "geeImage", item: "imgB", viz: {} },
  c: { type: "geeImage", item: "imgC", viz: {} },
  d: { type: "geeImage", item: "imgD", viz: {} },
};
const flush = () => new Promise((r) => setTimeout(r, 0));

test("queryPoint: one reduceRegion per visible queryable layer, all issued before any returns", async () => {
  const { ee, pending, calls } = fakeEE();
  const tokens = tokenSource();
  const q = defaultState().query;
  const p = queryPoint(fakeEngine(TARGETS), LAYERS, PT, q, { ee, token: tokens() });
  await flush();
  assert.deepEqual(calls.map((c) => c.img), ["imgA", "imgB"]);
  // reducer, point, scale, crs, crsTransform, bestEffort, maxPixels, tileScale
  const args = calls[0].args;
  assert.equal(args[0], "first");
  assert.deepEqual(args[1].point, [PT.lng, PT.lat]);
  assert.equal(args[2], null);
  assert.equal(args[3], "EPSG:5070");
  assert.deepEqual(args[4], q.transform);
  assert.deepEqual(args.slice(5), [true, 1e13, 4]);
  pending[1].cb({ v: 2 });
  pending[0].cb({ v: 1 });
  const results = await p;
  assert.deepEqual(results.map((r) => r.layerId), ["a", "b"]);
  assert.deepEqual(results.map((r) => r.data.bands[0].value), [1, 2]);
});

test("queryPoint: results for a superseded token are dropped", async () => {
  const { ee, pending } = fakeEE();
  const tokens = tokenSource();
  const seen = [];
  const first = queryPoint(fakeEngine(TARGETS), LAYERS.slice(0, 1), PT, defaultState().query, {
    ee,
    token: tokens(),
    onResult: (r) => seen.push(["first", r.layerId]),
  });
  await flush();
  const second = queryPoint(fakeEngine(TARGETS), LAYERS.slice(1, 2), { lng: 1, lat: 2 }, defaultState().query, {
    ee,
    token: tokens(),
    onResult: (r) => seen.push(["second", r.layerId]),
  });
  await flush();
  pending[1].cb({ v: 2 });
  pending[0].cb({ v: 1 }); // the first query answers last
  assert.deepEqual(await first, []);
  assert.deepEqual((await second).map((r) => r.layerId), ["b"]);
  assert.deepEqual(seen, [["second", "b"]]);
});

// ---- review fixes ----
import { queryableLayers, buildSelection } from "../js/engine/query.js";
import { createMapApi } from "../js/api.js";
import { createStore } from "../js/state.js";

test("select layers are not queryable (port of addSelectLayerToMap canQuery = false)", () => {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addSelectLayer({}, {}, "S", true);
  api.addSerializedSelectLayer({}, {}, "S2", true);
  api.addLayer({}, {}, "I", true);
  assert.deepEqual(store.get().layers.map((l) => l.queryable), [false, false, true]);
});

test("queryableLayers drops select layers even when marked queryable", () => {
  const ls = [
    { id: "s", kind: "select", visible: true, queryable: true },
    { id: "i", kind: "ee", visible: true, queryable: true },
  ];
  assert.deepEqual(queryableLayers(ls).map((l) => l.id), ["i"]);
});

test("seriesResult: the tick format follows the resolved date format", () => {
  const out = { ids: ["a"], labels: ["2020-01-01 10:00"], bands: ["b"], values: { a_b: 1 }, hasTime: true };
  assert.equal(seriesResult({ id: "l", name: "L" }, {}, out, PT, null, "YYYY-MM-dd HH:mm").data.xTickDateFormat, "%Y-%m-%d\n%H:%M");
  assert.equal(seriesResult({ id: "l", name: "L" }, {}, out, PT, null, "YYYY").data.xTickDateFormat, null);
  assert.equal(seriesResult({ id: "l", name: "L" }, { queryDateFormat: "HH:mm" }, out, PT, null).data.xTickDateFormat, "%Y-%m-%d\n%H:%M");
});

test("buildSelection: one selection per click, names joined, fire years, original's layer name", () => {
  const feats = [
    { id: "2", properties: { nm: "Elk & Deer", yr: 2001, dz_area_m2: 10 } },
    { id: "1", properties: { nm: "Bear", yr: 2003, dz_area_m2: 5 } },
    { id: "3", properties: { yr: 2004 } },
  ];
  const viz = { selectLayerNameProperty: "nm", selectLayerIgnitionYearProperty: "yr" };
  const s = buildSelection({ id: "L", name: "Units" }, viz, feats);
  assert.deepEqual(s.ids, ["2", "1", "3"]);
  assert.deepEqual(s.names, ["Elk & Deer", "Bear"]);
  assert.deepEqual(s.years, [2001, 2003, 2004]);
  assert.equal(s.name, "Elk & Deer-Bear");
  assert.equal(s.label, "Selected Units Elk - Deer-Bear");
  assert.equal(s.areaM2, 15);
  assert.equal(s.key, buildSelection({ id: "L", name: "Units" }, viz, feats.slice().reverse()).key);
  assert.equal(buildSelection({ id: "L", name: "Units" }, {}, [{ id: "9", properties: { a: 1 } }]).name, "9");
  assert.equal(buildSelection({ id: "L", name: "Units" }, { selectLayerNameProperty: "nm" }, [{ id: "9", properties: {} }]), null);
  assert.equal(buildSelection({ id: "L", name: "Units" }, {}, [{ id: "9", properties: {} }]).years, null);
});
