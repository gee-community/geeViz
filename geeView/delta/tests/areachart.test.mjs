// Chart area: which layers chart, with what settings, results rebuilt from
// the cache on unit changes (no Earth Engine), stale areas dropped, and the
// CSV export columns of the original viewer (area-charting.js makeChart).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createStore } from "../js/state.js";
import { createMapApi } from "../js/api.js";
import { parseReduction } from "../js/engine/charts.js";
import { buildSankeyFromHistogram } from "../js/engine/sankey.js";
import * as sankeyMod from "../js/engine/sankey.js";
import {
  DEFAULT_PERIODS,
  chartParams,
  chartJobs,
  areaFormatFor,
  hashString,
  lineResult,
  sankeyResult,
  chartCsv,
  validatePeriods,
  createAreaCharter,
} from "../js/engine/areachart.js";

const FIX = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "tests", "delta", "fixtures");
const load = (n) => JSON.parse(readFileSync(join(FIX, n), "utf-8"));
const LCMS = load("lcms_land_cover.json");
const NLCD = load("nlcd_2021.json");
const SANKEY = load("lcms_sankey.json");

function close(a, b, path = "") {
  if (typeof b === "number" && typeof a === "number") return assert.ok(Math.abs(a - b) <= 1e-9, `${path}: ${a} != ${b}`);
  assert.deepEqual(a, b, path);
}

function lcmsEntry(scale = 30) {
  return { raw: LCMS.raw, objInfo: LCMS.objInfo, labels: LCMS.labels, isHistogram: true, sentinel: false, scale };
}

test("chartParams: port of area-charting.js addLayer defaults", () => {
  const p = chartParams({ kind: "ee", viz: { canAreaChart: true } });
  assert.equal(p.line, true);
  assert.equal(p.sankey, false);
  assert.equal(p.chartType, "line");
  assert.equal(p.barChartMaxClasses, 20);
  assert.equal(p.rangeSlider, false);
  assert.equal(p.hovermode, "closest");
  assert.equal(p.showGrid, true);
  assert.equal(p.chartLabelMaxWidth, 40);
  assert.equal(p.chartLabelMaxLength, 100);
  assert.equal(p.sankeyMinPercentage, 0.5);
  assert.equal(p.minZoomSpecifiedScale, 11);
  assert.equal(p.dateFormat, "YYYY");
  // map layers read areaChartParams, chart-only layers their own params
  const q = chartParams({ kind: "ee", viz: { dateFormat: "YYYY-MM", areaChartParams: { line: true, sankey: true, sankeyMinPercentage: 0, chartType: "stacked-bar", palette: "ff0000,00ff00", yAxisLabel: "Y" } } });
  assert.equal(q.line, true);
  assert.equal(q.sankey, true);
  assert.equal(q.sankeyMinPercentage, 0, "0 is a value, not a default");
  assert.equal(q.chartType, "stacked-bar");
  assert.deepEqual(q.palette, ["ff0000", "00ff00"]);
  assert.equal(q.dateFormat, "YYYY-MM");
  assert.equal(q.yAxisLabel, "Y");
  const s = chartParams({ kind: "areaChartOnly", viz: { sankey: true } });
  assert.equal(s.sankey, true);
  assert.equal(s.line, false, "sankey only: line is off unless asked for (line || sankey == false)");
  const scaled = chartParams({ kind: "ee", viz: { areaChartParams: { scale: 100, crs: "EPSG:32612", minZoomSpecifiedScale: 9 } } });
  assert.equal(scaled.scale, 100);
  assert.equal(scaled.crs, "EPSG:32612");
  assert.equal(scaled.minZoomSpecifiedScale, 9);
});

test("chartJobs: visible chartable map layers and chosen chart-only layers, in list order", () => {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addLayer({}, { canAreaChart: true, areaChartParams: { line: true, sankey: true } }, "A", true);
  api.addLayer({}, { canAreaChart: true }, "B", false);
  api.addLayer({}, {}, "C", true);
  api.addTimeLapse({}, { canAreaChart: true }, "T", true);
  api.areaChart.addLayer({}, { line: true }, "Only on", true);
  api.areaChart.addLayer({}, { sankey: true }, "Only off", false);
  let s = store.get();
  const ids = Object.fromEntries(s.layers.map((l) => [l.name, l.id]));
  // timelapses start off; turn T on
  store.update((st) => ({ ...st, layers: st.layers.map((l) => (l.name === "T" ? { ...l, visible: true } : l)) }));
  s = store.get();
  const jobs = chartJobs(s).map((j) => [j.layer.name, j.kind]);
  // list order is top first: T, then A; then chart-only layers chosen by default (shouldChart = visible)
  assert.deepEqual(jobs, [["T", "line"], ["A", "line"], ["A", "sankey"], ["Only on", "line"]]);
  // settings: choose the other chart-only layer, leave A out
  store.set({ chartChoices: { [ids["Only off"]]: true, [ids.A]: false } });
  assert.deepEqual(chartJobs(store.get()).map((j) => [j.layer.name, j.kind]), [["T", "line"], ["Only on", "line"], ["Only off", "sankey"]]);
});

test("areaFormatFor: Show as and units pick the charts.py area format", () => {
  assert.equal(areaFormatFor("metric", "area"), "Hectares");
  assert.equal(areaFormatFor("imperial", "area"), "Acres");
  assert.equal(areaFormatFor("metric", "pct"), "Percentage");
  assert.equal(areaFormatFor("imperial", "pct"), "Percentage");
});

test("lineResult: numbers are charts.py's for each format, rebuilt from the cached reduction", () => {
  const layer = { id: "layer-1", name: "LCMS" };
  const params = chartParams({ kind: "ee", viz: {} });
  for (const fmt of ["Percentage", "Hectares", "Acres"]) {
    const [units, showAs] = fmt === "Percentage" ? ["metric", "pct"] : fmt === "Hectares" ? ["metric", "area"] : ["imperial", "area"];
    const r = lineResult(layer, params, lcmsEntry(30), { units, showAs, areaLabel: "Map view", areaKey: "k", nominalScale: 30 });
    const exp = parseReduction(LCMS.raw, LCMS.objInfo, LCMS.labels, { isHistogram: true, sentinel: false, areaFormat: fmt, scale: 30 });
    assert.equal(r.kind, "chart");
    assert.equal(r.layerId, "layer-1");
    assert.equal(r.title, "LCMS over time");
    assert.deepEqual(r.actions, ["csv", "png", "expand"]);
    assert.equal(r.data.areaFormat, fmt);
    assert.deepEqual(r.data.columns, exp.columns);
    close(r.data.rows, exp.rows, fmt);
    // charts.py expected values for this fixture
    close(r.data.rows, LCMS.expected[fmt + "@30"].rows, fmt + " vs charts.py");
  }
  const r = lineResult(layer, params, lcmsEntry(30), { units: "metric", showAs: "area", areaLabel: "Map view", areaKey: "k", nominalScale: 30 });
  assert.equal(r.data.isCollection, true);
  assert.equal(r.data.chartType, "line");
  assert.equal(r.data.xLabel, "Year");
  assert.equal(r.data.yLabel, "ha");
  assert.equal(r.data.nominalScale, 30);
  // colors are the class palette, by column
  const info = LCMS.objInfo.classInfo.Land_Cover;
  r.data.columns.forEach((c, i) => {
    const k = info.classNames.indexOf(c);
    assert.equal(r.data.colors[i], k > -1 ? "#" + String(info.classPalette[k]).replace(/^#/, "") : null, c);
  });
  assert.match(r.meta, /2015-2023/);
  assert.match(r.meta, /30 m/);
});

test("lineResult: a single image charts as bars, whatever chartType says", () => {
  const params = chartParams({ kind: "ee", viz: { areaChartParams: { chartType: "line" } } });
  const entry = { raw: NLCD.raw, objInfo: NLCD.objInfo, labels: [], isHistogram: true, sentinel: false, scale: 30 };
  const r = lineResult({ id: "n", name: "NLCD" }, params, entry, { units: "metric", showAs: "pct", areaLabel: "a", areaKey: "k", nominalScale: 30 });
  assert.equal(r.data.isCollection, false);
  assert.equal(r.data.chartType, "bar");
  assert.equal(r.data.yLabel, "% Area");
  close(r.data.rows, NLCD.expected["Percentage@30"].rows);
});

test("lineResult: continuous layers keep the reducer's label and ignore units", () => {
  const params = chartParams({ kind: "ee", viz: {} });
  const objInfo = { objType: "ImageCollection", bandNames: ["NDVI"], isThematic: false, classInfo: {}, size: 2 };
  const entry = { raw: { "2019----NDVI": 0.5, "2020----NDVI": null }, objInfo, labels: ["2019", "2020"], isHistogram: false, sentinel: false, scale: 30, reducerLabel: "Mean" };
  const a = lineResult({ id: "x", name: "NDVI" }, params, entry, { units: "metric", showAs: "area", areaLabel: "a", areaKey: "k", nominalScale: 30 });
  const b = lineResult({ id: "x", name: "NDVI" }, params, entry, { units: "imperial", showAs: "pct", areaLabel: "a", areaKey: "k", nominalScale: 30 });
  assert.deepEqual(a.data.rows, [{ x: "2019", values: [0.5] }, { x: "2020", values: [null] }]);
  assert.deepEqual(b.data.rows, a.data.rows);
  assert.equal(a.data.yLabel, "Mean");
});

test("sankeyResult: links and matrix are charts.py's for the format, rebuilt from the cached reduction", () => {
  const params = chartParams({ kind: "ee", viz: { areaChartParams: { sankey: true } } });
  const entry = { raw: SANKEY.raw, objInfo: SANKEY.objInfo, band: SANKEY.band, periods: SANKEY.periods, scale: 30 };
  for (const [units, showAs, fmt] of [["metric", "pct", "Percentage"], ["metric", "area", "Hectares"], ["imperial", "area", "Acres"]]) {
    const r = sankeyResult({ id: "s", name: "LCMS" }, params, entry, { units, showAs, areaLabel: "a", areaKey: "k", nominalScale: 30 });
    const exp = buildSankeyFromHistogram(SANKEY.raw, SANKEY.objInfo.classInfo, SANKEY.periods, fmt, 30, 0.5, SANKEY.band);
    assert.equal(r.kind, "sankey");
    assert.deepEqual(r.actions, ["csv", "png", "expand"]);
    assert.deepEqual(r.data.links, exp.links);
    assert.deepEqual(r.data.matrix, exp.matrix);
    assert.equal(r.data.areaFormat, fmt);
  }
});

test("chartCsv: port of makeChart's csv table (collections: Year then sanitized class columns)", () => {
  const params = chartParams({ kind: "ee", viz: {} });
  const r = lineResult({ id: "l", name: "LCMS" }, params, lcmsEntry(30), { units: "metric", showAs: "pct", areaLabel: "a", areaKey: "k", nominalScale: 30 });
  const lines = chartCsv(r).trim().split("\n");
  assert.equal(lines[0], ["Year"].concat(r.data.columns.map((c) => c.replace(/[^A-Za-z0-9 -]/g, "-"))).join(","));
  assert.equal(lines.length, 1 + r.data.rows.length);
  assert.equal(lines[1].split(",")[0], "2015");
  // a gap is an empty cell, never 0
  const gap = { ...r, data: { ...r.data, rows: [{ x: "2003", values: r.data.columns.map(() => null) }] } };
  assert.equal(chartCsv(gap).trim().split("\n")[1], "2003" + ",".repeat(r.data.columns.length));
});

test("chartCsv: a single image is Class Name, y label rows (transposed)", () => {
  const params = chartParams({ kind: "ee", viz: {} });
  const entry = { raw: NLCD.raw, objInfo: NLCD.objInfo, labels: [], isHistogram: true, sentinel: false, scale: 30 };
  const r = lineResult({ id: "n", name: "NLCD" }, params, entry, { units: "metric", showAs: "pct", areaLabel: "a", areaKey: "k", nominalScale: 30 });
  const lines = chartCsv(r).trim().split("\n");
  assert.equal(lines[0], "Class Name,% Area");
  assert.equal(lines.length, 1 + r.data.columns.length);
  assert.equal(lines[1].split(",")[0], r.data.columns[0].replace(/[^A-Za-z0-9 -]/g, "-"));
});

test("chartCsv: Sankey blocks per transition, port of chartArea's outCSV", () => {
  const params = chartParams({ kind: "ee", viz: { areaChartParams: { sankey: true } } });
  const entry = { raw: SANKEY.raw, objInfo: SANKEY.objInfo, band: SANKEY.band, periods: SANKEY.periods, scale: 30 };
  const r = sankeyResult({ id: "s", name: "LCMS" }, params, entry, { units: "metric", showAs: "pct", areaLabel: "a", areaKey: "k", nominalScale: 30 });
  const lines = chartCsv(r).split("\n");
  const names = SANKEY.objInfo.classInfo.Land_Cover.classNames;
  const san = (s) => s.replace(/[^A-Za-z0-9 -]/g, "-");
  assert.equal(lines[0], [""].concat(names.map((n) => `${san(n)} 2020-2022 `)).join(","));
  assert.equal(lines[1].split(",")[0], `${san(names[0])} 2016-2018`);
  const m = r.data.matrix["2016-2018 → 2020-2022"];
  assert.deepEqual(lines[1].split(",").slice(1).map(Number), m.values[0]);
  assert.equal(lines[1 + names.length], "");
});

test("validatePeriods: port of getTransitionRowData checks", () => {
  assert.deepEqual(validatePeriods(DEFAULT_PERIODS).periods, [[1985, 1987], [2022, 2024]]);
  assert.deepEqual(validatePeriods([[2000, 2002]]).errors, ["No year pairs provided. Please add at least two rows of years."]);
  assert.ok(validatePeriods([[2000, NaN], [2005, 2006]]).errors.some((e) => /blank/.test(e)));
  assert.ok(validatePeriods([[2002, 2000], [2005, 2006]]).errors.some((e) => /greater than the last/.test(e)));
  assert.ok(validatePeriods([[2000, 2005], [2005, 2006]]).errors.some((e) => /overlap/.test(e)));
  assert.equal(validatePeriods([[2000, 2005], [2005, 2006]]).periods, null);
});

test("hashString is stable and distinguishes inputs", () => {
  assert.equal(hashString("abc"), hashString("abc"));
  assert.notEqual(hashString("abc"), hashString("abd"));
});

// ---- the charter, with Earth Engine replaced by counting fakes ----

function deferred() {
  let resolve;
  const p = new Promise((r) => (resolve = r));
  return { p, resolve };
}

function setup({ hold = false } = {}) {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addLayer({ tag: "lcms" }, { canAreaChart: true, areaChartParams: { line: true, sankey: true, sankeyTransitionPeriods: SANKEY.periods } }, "LCMS", true);
  api.addLayer({ tag: "nlcd" }, { canAreaChart: true }, "NLCD", true);
  const calls = { line: [], sankey: [] };
  const pending = [];
  const fake = {
    line: (obj, params, geometry, inputs) => {
      calls.line.push({ obj, geometry, inputs });
      const v = obj.tag === "lcms" ? lcmsEntry(inputs.nominalScale) : { raw: NLCD.raw, objInfo: NLCD.objInfo, labels: [], isHistogram: true, sentinel: false, scale: inputs.nominalScale };
      if (!hold) return Promise.resolve(v);
      const d = deferred();
      pending.push(() => d.resolve(v));
      return d.p;
    },
    sankey: (obj, params, geometry, inputs, periods) => {
      calls.sankey.push({ obj, geometry, inputs, periods });
      const v = { raw: SANKEY.raw, objInfo: SANKEY.objInfo, band: SANKEY.band, periods, scale: inputs.nominalScale };
      if (!hold) return Promise.resolve(v);
      const d = deferred();
      pending.push(() => d.resolve(v));
      return d.p;
    },
  };
  let zoom = 12;
  const charter = createAreaCharter(store, {
    compute: fake,
    item: (layer) => layer.item,
    zoom: () => zoom,
    key: (g) => "g:" + g.id,
  });
  store.set({ tool: "chart", areaFrom: "view" });
  return { store, api, charter, calls, pending, setZoom: (z) => (zoom = z) };
}

test("charter: one result per job, inputs from areaChartInputs at the map zoom", async () => {
  const { store, charter, calls } = setup();
  await charter.chartArea({ id: "A" }, "Map view (a)");
  const rs = store.get().results;
  assert.deepEqual(rs.map((r) => [r.title, r.kind]), [["NLCD", "chart"], ["LCMS over time", "chart"], ["LCMS transitions", "sankey"]]);
  assert.equal(calls.line.length, 2);
  assert.equal(calls.sankey.length, 1);
  assert.deepEqual(calls.line[0].inputs.transform, [30, 0, -2361915.0, 0, -30, 3177735.0]);
  assert.equal(calls.line[0].inputs.crs, "EPSG:5070");
  assert.equal(calls.line[0].inputs.nominalScale, 30);
  assert.deepEqual(calls.sankey[0].periods, SANKEY.periods);
  assert.equal(store.get().charting, false);
  assert.equal(store.get().where, "Map view (a)");
});

test("charter: zoomed out coarsens the grid (wiring of areaChartInputs)", async () => {
  const { charter, calls, setZoom } = setup();
  setZoom(9);
  await charter.chartArea({ id: "A" }, "a");
  assert.equal(calls.line[0].inputs.nominalScale, 120);
  assert.deepEqual(calls.line[0].inputs.transform.slice(0, 1), [120]);
});

test("charter: units and Show as changes re-render from the cache with no Earth Engine call", async () => {
  const { store, charter, calls } = setup();
  await charter.chartArea({ id: "A" }, "a");
  const before = store.get().results;
  const n = calls.line.length + calls.sankey.length;
  store.set({ units: "imperial" });
  store.set({ showAs: "pct" });
  store.set({ showAs: "area" });
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(calls.line.length + calls.sankey.length, n, "no new reductions");
  const after = store.get().results;
  assert.equal(after.length, before.length);
  const lc = after.find((r) => r.title === "LCMS over time" && r.kind === "chart");
  assert.equal(lc.data.areaFormat, "Acres");
  close(lc.data.rows, LCMS.expected["Acres@30"].rows);
  const sk = after.find((r) => r.kind === "sankey");
  assert.equal(sk.data.areaFormat, "Acres");
});

test("charter: the same area at the same scale is not reduced twice; a new zoom is", async () => {
  const { charter, calls, setZoom } = setup();
  await charter.chartArea({ id: "A" }, "a");
  await charter.chartArea({ id: "A" }, "a");
  assert.equal(calls.line.length, 2);
  setZoom(8);
  await charter.chartArea({ id: "A" }, "a");
  assert.equal(calls.line.length, 4);
});

test("charter: stale chart results are dropped", async () => {
  const { store, charter, pending } = setup({ hold: true });
  const first = charter.chartArea({ id: "A" }, "first");
  const second = charter.chartArea({ id: "B" }, "second");
  // the second area's answers arrive first, then the first area's
  pending.slice(3).forEach((f) => f());
  await second;
  pending.slice(0, 3).forEach((f) => f());
  await first;
  const rs = store.get().results;
  assert.equal(rs.length, 3);
  assert.ok(rs.every((r) => r.data.areaKey === "g:B"), rs.map((r) => r.data.areaKey).join());
  assert.equal(store.get().where, "second");
  assert.equal(store.get().charting, false);
});

test("charter: a failed layer notifies and the others still chart", async () => {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addLayer({ tag: "bad" }, { canAreaChart: true }, "Bad", true);
  api.addLayer({ tag: "nlcd" }, { canAreaChart: true }, "NLCD", true);
  const notes = [];
  const charter = createAreaCharter(store, {
    compute: {
      line: (obj) => (obj.tag === "bad" ? Promise.reject(new Error("boom")) : Promise.resolve({ raw: NLCD.raw, objInfo: NLCD.objInfo, labels: [], isHistogram: true, sentinel: false, scale: 30 })),
      sankey: () => Promise.reject(new Error("no")),
    },
    item: (l) => l.item,
    zoom: () => 12,
    key: (g) => g.id,
    notify: (m) => notes.push(m),
  });
  store.set({ tool: "chart" });
  await charter.chartArea({ id: "A" }, "a");
  assert.deepEqual(store.get().results.map((r) => r.title), ["NLCD"]);
  assert.equal(notes.length, 1);
  assert.match(notes[0], /Bad/);
  assert.match(notes[0], /boom/);
});

test("charter: invalid transition periods skip the Sankey with the original's message", async () => {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addLayer({ tag: "lcms" }, { canAreaChart: true, areaChartParams: { sankey: true } }, "LCMS", true);
  const notes = [];
  let sankeys = 0;
  const charter = createAreaCharter(store, {
    compute: { line: () => Promise.resolve(lcmsEntry()), sankey: () => (sankeys++, Promise.resolve({})) },
    item: (l) => l.item,
    zoom: () => 12,
    key: (g) => g.id,
    notify: (m) => notes.push(m),
  });
  store.set({ tool: "chart", chartPeriods: [[2000, 2010], [2005, 2012]] });
  await charter.chartArea({ id: "A" }, "a");
  assert.equal(sankeys, 0);
  assert.ok(notes.some((n) => /overlap/.test(n)), notes.join("|"));
});

test("sankey module exports what the charter uses", () => {
  assert.equal(typeof sankeyMod.sankeyForCollection, "function");
});

// ---- coordinator rulings: class dictionaries, shouldUnmask, per-band Sankey, auto periods ----
import { classProps, defaultPeriods, yearRange, insertPeriod, removePeriod, currentDefaults } from "../js/engine/areachart.js";

test("chartParams: class dictionaries given with the layer, and their bands", () => {
  const viz = { class_names: { lc: ["A", "B"] }, class_values: { lc: [1, 2] }, class_palette: { lc: ["ff0000", "00ff00"] } };
  const p = chartParams({ kind: "ee", viz: { ...viz, areaChartParams: {} } });
  assert.deepEqual(p.classDicts.names, viz.class_names);
  assert.deepEqual(p.bandNames, ["lc"], "port of addLayer: the bands are the class dictionary's keys");
  assert.deepEqual(classProps(p.classDicts), { lc_class_names: ["A", "B"], lc_class_values: [1, 2], lc_class_palette: ["ff0000", "00ff00"] });
  const only = chartParams({ kind: "areaChartOnly", viz: { class_names: { b: "x,y" }, class_values: { b: "3,4" } } });
  assert.deepEqual(classProps(only.classDicts), { b_class_names: ["x", "y"], b_class_values: ["3", "4"] });
  assert.equal(chartParams({ kind: "ee", viz: {} }).classDicts, null);
});

test("chartParams: shouldUnmask and unmaskValue (port of addLayer)", () => {
  assert.deepEqual([chartParams({ kind: "ee", viz: {} }).shouldUnmask, chartParams({ kind: "ee", viz: {} }).unmaskValue], [false, 0]);
  const p = chartParams({ kind: "ee", viz: { areaChartParams: { shouldUnmask: true, unmaskValue: 99 } } });
  assert.deepEqual([p.shouldUnmask, p.unmaskValue], [true, 99]);
});

test("defaultPeriods: single years at the ends of the range; given periods clipped, outside ones dropped", () => {
  assert.deepEqual(defaultPeriods([2015, 2023]), [[2015, 2015], [2023, 2023]]);
  assert.equal(defaultPeriods(null), null);
  assert.deepEqual(defaultPeriods([2015, 2023], [[1990, 2016], [2018, 2019], [2022, 2030]]), [[2015, 2016], [2018, 2019], [2022, 2023]]);
  assert.deepEqual(defaultPeriods([2015, 2023], [[1990, 1995], [2018, 2019], [2022, 2030]]), [[2018, 2019], [2022, 2023]], "entirely outside: dropped");
  assert.deepEqual(defaultPeriods([2015, 2023], [[1990, 1995], [2030, 2031]]), [[2015, 2015], [2023, 2023]], "fewer than two left: the ends");
});

const sk = (id, extra = {}) => ({ id, kind: "ee", chartable: true, visible: true, viz: { areaChartParams: { sankey: true, ...extra } } });
test("yearRange: visible Sankey layers' years, else every Sankey layer's; currentDefaults never leaves it", () => {
  const s = { layers: [sk("a"), { ...sk("b"), visible: false }, { id: "c", kind: "ee", chartable: true, visible: true, viz: {} }], order: ["a", "b", "c"], chartYears: { a: [2015, 2023], b: [1985, 2024], c: [1900, 2100] } };
  assert.deepEqual(yearRange(s), [2015, 2023]);
  assert.deepEqual(currentDefaults(s), [[2015, 2015], [2023, 2023]]);
  const off = { ...s, layers: s.layers.map((l) => ({ ...l, visible: false })) };
  assert.deepEqual(yearRange(off), [1985, 2024], "none visible: every Sankey layer");
  assert.equal(yearRange({ ...s, chartYears: {} }), null);
  assert.deepEqual(currentDefaults({ ...s, chartPeriodsGiven: [[2010, 2016], [2020, 2025]] }), [[2015, 2016], [2020, 2023]]);
  const own = { ...s, layers: [sk("a", { sankeyTransitionPeriods: [[2016, 2017], [2019, 2020]] })] };
  assert.deepEqual(currentDefaults(own), [[2016, 2017], [2019, 2020]], "the run script's periods");
});

test("insertPeriod: in the middle of the largest gap, at its midpoint year", () => {
  assert.deepEqual(insertPeriod([[2015, 2015], [2023, 2023]], [2015, 2023]), { rows: [[2015, 2015], [2019, 2019], [2023, 2023]], index: 1 });
  // largest gap wins
  assert.deepEqual(insertPeriod([[2015, 2015], [2017, 2017], [2023, 2023]], [2015, 2023]).rows, [[2015, 2015], [2017, 2017], [2020, 2020], [2023, 2023]]);
  // ties: the middle-most gap
  assert.deepEqual(insertPeriod([[2000, 2000], [2004, 2004], [2008, 2008], [2012, 2012], [2016, 2016]], [2000, 2016]).index, 2);
  // a one-year gap: the year between
  assert.deepEqual(insertPeriod([[2015, 2015], [2017, 2017]], [2015, 2017]).rows[1], [2016, 2016]);
  // no free year: inserted anyway, validation reports the overlap
  const r = insertPeriod([[2015, 2015], [2016, 2016]], [2015, 2016]);
  assert.equal(r.rows.length, 3);
  assert.ok(validatePeriods(r.rows, [2015, 2016]).errors.some((e) => /overlap/.test(e)));
  // never outside the range
  r.rows.forEach((row) => row.forEach((y) => assert.ok(y >= 2015 && y <= 2016)));
  assert.deepEqual(insertPeriod([[2015, 2015]], [2015, 2023]).rows, [[2015, 2015], [2023, 2023]]);
});

test("removePeriod: port of removeLastTransitionRow (second to last; the last with fewer than three)", () => {
  assert.deepEqual(removePeriod([[1, 1], [2, 2], [3, 3]]), [[1, 1], [3, 3]]);
  assert.deepEqual(removePeriod([[1, 1], [3, 3]]), [[1, 1]]);
});

test("validatePeriods: the year range check and the original's texts", () => {
  const v = validatePeriods([[2014, 2014], [2023, 2023]], [2015, 2023]);
  assert.deepEqual(v.errors, ["Found years outside the available year range. Please ensure all years are >= 2015 and <= 2023."]);
  assert.deepEqual(validatePeriods([[2015, 2015], [2023, 2023]], [2015, 2023]).periods, [[2015, 2015], [2023, 2023]]);
  assert.ok(validatePeriods([[2019, 2019], [2019, 2019]]).errors.some((e) => /overlap/.test(e)), "single years must strictly increase");
});

test("charter: one Sankey card per band, and default periods from the layers' years", async () => {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addLayer({ tag: "lcms" }, { canAreaChart: true, areaChartParams: { sankey: true } }, "LCMS", true);
  const seen = [];
  const objInfo = { ...SANKEY.objInfo, bandNames: ["Land_Cover", "Land_Use"], classInfo: { Land_Cover: SANKEY.objInfo.classInfo.Land_Cover, Land_Use: SANKEY.objInfo.classInfo.Land_Cover } };
  let yearsCalls = 0;
  const charter = createAreaCharter(store, {
    compute: {
      line: () => Promise.reject(new Error("no line")),
      sankey: (obj, params, g, inputs, periods) => {
        seen.push(periods);
        return Promise.resolve({ objInfo, periods, scale: 30, bands: [{ band: "Land_Cover", raw: SANKEY.raw }, { band: "Land_Use", raw: SANKEY.raw }] });
      },
      years: () => (yearsCalls++, Promise.resolve([2016, 2022])),
    },
    item: (l) => l.item,
    zoom: () => 12,
    key: (g) => g.id,
  });
  store.set({ tool: "chart" });
  await charter.chartArea({ id: "A" }, "a");
  assert.deepEqual(store.get().chartPeriods, [[2016, 2016], [2022, 2022]]);
  assert.deepEqual(seen[0], [[2016, 2016], [2022, 2022]]);
  const rs = store.get().results;
  assert.deepEqual(rs.map((r) => [r.kind, r.data.band]), [["sankey", "Land_Cover"], ["sankey", "Land_Use"]]);
  assert.equal(new Set(rs.map((r) => r.id)).size, 2);
  // years are read once per layer; periods the user applied are not replaced
  store.set({ chartPeriods: [[2017, 2018], [2020, 2021]], chartPeriodsUser: true });
  await charter.chartArea({ id: "B" }, "b");
  assert.equal(yearsCalls, 1);
  assert.deepEqual(seen[1], [[2017, 2018], [2020, 2021]]);
});

// ---- review fixes: type precedence, result reuse, bounded cache ----
import { eeTypeOf, eeCompute } from "../js/engine/areachart.js";

test("eeTypeOf: the layer's declared type wins over instanceof; a vector still cannot chart", async () => {
  class Image {}
  class ImageCollection {}
  class FeatureCollection {}
  const fakeEE = { Image, ImageCollection, FeatureCollection, Geometry: class {}, Feature: class {} };
  const filtered = new FeatureCollection(); // a deserialized collection.filter() is typed FeatureCollection
  assert.equal(eeTypeOf(fakeEE, filtered, "geeImageCollection"), "ImageCollection");
  assert.equal(eeTypeOf(fakeEE, filtered, "ImageCollection"), "ImageCollection");
  assert.equal(eeTypeOf(fakeEE, new Image(), "geeImage"), "Image");
  assert.equal(eeTypeOf(fakeEE, filtered, "geeVectorImage"), "FeatureCollection");
  await assert.rejects(eeCompute(fakeEE).line(filtered, { layerType: "geeVectorImage" }, null, {}), /Cannot chart ee object type FeatureCollection/);
});

test("charter: results already published are reused as each new one arrives", async () => {
  const { store, charter, pending } = setup({ hold: true });
  const run = charter.chartArea({ id: "A" }, "a");
  pending[0]();
  await new Promise((r) => setTimeout(r, 0));
  const first = store.get().results[0];
  pending[1]();
  pending[2]();
  await run;
  assert.equal(store.get().results.find((r) => r.id === first.id), first, "same object: the card is not rebuilt");
  store.set({ units: "imperial" });
  assert.notEqual(store.get().results.find((r) => r.id === first.id), first, "a units change builds new results");
});

test("charter: the reduction cache keeps at most cacheMax entries", async () => {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addLayer({ tag: "nlcd" }, { canAreaChart: true }, "NLCD", true);
  let calls = 0;
  const charter = createAreaCharter(store, {
    compute: { line: () => (calls++, Promise.resolve({ raw: NLCD.raw, objInfo: NLCD.objInfo, labels: [], isHistogram: true, sentinel: false, scale: 30 })) },
    item: (l) => l.item,
    zoom: () => 12,
    key: (g) => g.id,
    cacheMax: 3,
  });
  store.set({ tool: "chart" });
  for (const id of ["A", "B", "C", "D"]) await charter.chartArea({ id }, id);
  assert.equal(charter.cacheSize(), 3);
  await charter.chartArea({ id: "D" }, "D");
  assert.equal(calls, 4, "recent areas are still cached");
  await charter.chartArea({ id: "A" }, "A");
  assert.equal(calls, 5, "the least recently used area was dropped");
});
