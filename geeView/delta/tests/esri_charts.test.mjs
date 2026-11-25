// Chart area on ArcGIS services (js/esri/charts.js): class areas from an
// image service's computeHistograms, class transitions for a Sankey, and
// feature counts from outStatistics, on recorded answers.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeFetch, fixture, response } from "./esrifake.mjs";
import { imageChart, featureChart, histogramCounts } from "../js/esri/charts.js";
import { chartParams } from "../js/engine/areachart.js";

const LCMS = fixture("lcms_info").request.url;
const MTBS63 = fixture("mtbs63_info").request.url;
const SQUARE = { type: "Polygon", coordinates: [[[-105.7, 40.55], [-105.6, 40.55], [-105.6, 40.65], [-105.7, 40.65], [-105.7, 40.55]]] };
const COLORS = ["#3d4551", "#f39268", "#d54309", "#00a398", "#1b1716", "#ff0000", "#00ff00", "#0000ff", "#ff00ff", "#00ffff", "#ffff00", "#888888", "#123456", "#654321", "#abcdef", "#fedcba"];
const LEGEND = {
  type: "images",
  items: response("lcms_legend").layers[0].legend.map((it, i) => ({ label: it.label, src: "data:image/png;base64,", value: i + 1, color: COLORS[i] })),
};
const CTX = { units: "metric", showAs: "area", areaLabel: "Square", areaKey: "k", precision: null };

test("histogramCounts: one count per value, empty bins dropped", () => {
  const h = response("lcms_histograms_2021").histograms[0];
  const c = histogramCounts(h, true);
  assert.equal(c["15"], h.counts[15]);
  assert.equal(c["0"], undefined);
  assert.equal(Object.keys(c).length, h.counts.filter(Boolean).length);
});

test("class areas from computeHistograms, named and colored by the legend", async () => {
  const fetch = fakeFetch([[LCMS, "lcms_info"], [LCMS + "/computeHistograms", "lcms_histograms_2021"]]);
  const layer = { id: "l", name: "LCMS 2021", kind: "esri.image", item: LCMS, legend: LEGEND, viz: { esri: { time: [1609459200000, 1640995199999] } } };
  const entry = await imageChart(layer, { geojson: SQUARE }, { fetch, zoom: 12, kind: "line", params: chartParams(layer) });
  const p = fetch.calls.find((c) => c.base.endsWith("/computeHistograms")).params;
  assert.equal(p.time, "1609459200000,1640995199999");
  assert.equal(p.geometryType, "esriGeometryPolygon");
  const px = JSON.parse(p.pixelSize);
  assert.equal(px.x, 38.21851414258813, "one map pixel at zoom 12, in Web Mercator meters (above the service's 30)");
  const [r] = entry.results(CTX);
  assert.equal(r.kind, "chart");
  const h = response("lcms_histograms_2021").histograms[0];
  const names = r.data.columns;
  assert.ok(names.includes("Stable") && names.includes("Vegetation Growth") && !names.includes("0"), names.join(","));
  assert.equal(r.data.colors[names.indexOf("Stable")], COLORS[14]);
  // hectares: counts times the ground pixel area
  const ground = px.x * Math.cos(((40.55 + 40.65) / 2) * (Math.PI / 180));
  const stable = r.data.rows[0].values[names.indexOf("Stable")];
  assert.ok(Math.abs(stable - (h.counts[15] * ground * ground) / 10000) <= 1, `${stable}`);
});

test("a long area goes as a POST", async () => {
  const fetch = fakeFetch([[LCMS, "lcms_info"], [LCMS + "/computeHistograms", "lcms_histograms_2021"]]);
  const ring = Array.from({ length: 300 }, (_, i) => [-105.7 + 0.1 * Math.cos((i / 300) * 2 * Math.PI), 40.6 + 0.05 * Math.sin((i / 300) * 2 * Math.PI)]);
  ring.push(ring[0]);
  const layer = { id: "l", name: "L", kind: "esri.image", item: LCMS, legend: LEGEND, viz: {} };
  await imageChart(layer, { geojson: { type: "Polygon", coordinates: [ring] } }, { fetch, zoom: 12, kind: "line", params: chartParams(layer) });
  assert.equal(fetch.calls.find((c) => c.base.endsWith("/computeHistograms")).method, "POST");
});

test("class transitions between two periods, for a Sankey", async () => {
  const fetch = fakeFetch([
    [LCMS, "lcms_info"],
    [(r) => r.base === LCMS + "/query" && /1990/.test(r.params.where || ""), "lcms_catalog_1990"],
    [(r) => r.base === LCMS + "/query" && /1998/.test(r.params.where || ""), "lcms_catalog_1998"],
    [LCMS + "/computeHistograms", "lcms_transition_1990_1998"],
  ]);
  const layer = { id: "l", name: "LCMS", kind: "esri.timelapse", item: LCMS, legend: LEGEND, viz: { timelapse: true, areaChartParams: { sankey: true } } };
  const entry = await imageChart(layer, { geojson: SQUARE }, { fetch, zoom: 12, kind: "sankey", params: chartParams(layer), periods: [[1990, 1990], [1998, 1998]] });
  const rr = JSON.parse(fetch.calls.find((c) => c.base.endsWith("/computeHistograms")).params.renderingRule);
  assert.equal(rr.rasterFunctionArguments.Raster2, "$54");
  assert.equal(rr.rasterFunctionArguments.Raster.rasterFunctionArguments.Raster, "$46");
  assert.equal(rr.rasterFunctionArguments.Raster.rasterFunctionArguments.Raster2, 17);
  const [s] = entry.results(CTX);
  assert.equal(s.kind, "sankey");
  // every link is a from class and a to class decoded from v = from * 17 + to
  const h = response("lcms_transition_1990_1998").histograms[0];
  let biggest = 0;
  h.counts.forEach((n, i) => n > h.counts[biggest] && (biggest = i));
  const v = Math.round(h.min + 0.5 + biggest);
  const from = LEGEND.items[Math.floor(v / 17) - 1].label;
  const to = LEGEND.items[(v % 17) - 1].label;
  assert.ok(s.data.links.some((l) => l.source_name === `1990 ${from}` && l.target_name === `1998 ${to}`), JSON.stringify(s.data.links.slice(0, 3)));
  // and the direction: the biggest change between two different classes
  let change = -1;
  h.counts.forEach((c, i) => {
    const val = Math.round(h.min + 0.5 + i);
    const f = Math.floor(val / 17);
    const t = val % 17;
    const back = Math.round(t * 17 + f - h.min - 0.5);
    if (f !== t && c > 0 && c !== (h.counts[back] || 0) && (change < 0 || c > h.counts[change])) change = i;
  });
  const cv = Math.round(h.min + 0.5 + change);
  const m = s.data.matrix["1990 → 1998"];
  const fi = Math.floor(cv / 17) - 1;
  const ti = (cv % 17) - 1;
  const back = m.values[ti][m.columns.indexOf(LEGEND.items[fi].label)];
  const fwd = m.values[fi][m.columns.indexOf(LEGEND.items[ti].label)];
  assert.ok(fwd > back, `${LEGEND.items[fi].label} to ${LEGEND.items[ti].label}: ${fwd} vs back ${back}`);
});

test("features counted by a field within the area, colored as drawn", async () => {
  const fetch = fakeFetch([[MTBS63, "mtbs63_info"], [MTBS63 + "/query", "mtbs63_outstatistics"]]);
  const layer = { id: "f", name: "Fires", kind: "esri.feature", item: MTBS63, viz: { chartField: "fire_type", esri: { where: "year >= 2018" } } };
  const entry = await featureChart(layer, { geojson: SQUARE }, { fetch, kind: "line", params: chartParams(layer) });
  const p = fetch.calls.find((c) => c.base === MTBS63 + "/query").params;
  assert.equal(p.groupByFieldsForStatistics, "fire_type");
  assert.deepEqual(JSON.parse(p.outStatistics)[0].statisticType, "count");
  assert.equal(p.where, "year >= 2018");
  const [r] = entry.results(CTX);
  const groups = response("mtbs63_outstatistics").features.map((f) => f.attributes.fire_type);
  assert.deepEqual(r.data.columns.slice().sort(), groups.slice().sort());
  const want = response("mtbs63_outstatistics").features.find((f) => f.attributes.fire_type === r.data.columns[0]).attributes.v;
  assert.equal(r.data.rows[0].values[0], want);
  assert.equal(r.data.yLabel, "Features");
});

test("a timelapse's histograms go a few at a time, and a refused one is asked again", async () => {
  let inFlight = 0;
  let most = 0;
  let refused = false;
  const fetch = fakeFetch([
    [LCMS, "lcms_info"],
    [LCMS + "/query", "lcms_catalog_years"],
    [
      LCMS + "/computeHistograms",
      () => {
        if (!refused) {
          refused = true;
          return new TypeError("Failed to fetch");
        }
        return response("lcms_histograms_2021");
      },
    ],
  ]);
  const slow = async (url, init) => {
    inFlight++;
    most = Math.max(most, inFlight);
    await new Promise((r) => setTimeout(r, 2));
    try {
      return await fetch(url, init);
    } finally {
      inFlight--;
    }
  };
  slow.calls = fetch.calls;
  const layer = { id: "l", name: "LCMS", kind: "esri.timelapse", item: LCMS, legend: LEGEND, viz: { timelapse: true } };
  const entry = await imageChart(layer, { geojson: SQUARE }, { fetch: slow, zoom: 12, kind: "line", params: chartParams(layer), retryDelay: 1 });
  const [r] = entry.results(CTX);
  const years = response("lcms_catalog_years").features.length;
  assert.equal(r.data.rows.length, years);
  assert.ok(most <= 5, `at most 4 histograms (plus metadata) at once, saw ${most}`);
  assert.equal(fetch.calls.filter((c) => c.base.endsWith("/computeHistograms")).length, years + 1);
});

test("charting before the layer's legend has arrived still names the classes", async () => {
  const { esriPlugin } = await import("../js/plugins/esri.js");
  const fetch = fakeFetch([[LCMS, "lcms_info"], [LCMS + "/legend", "lcms_legend"], [LCMS + "/computeHistograms", "lcms_histograms_2021"]]);
  const layer = { id: "l", name: "LCMS 2021", kind: "esri.image", item: LCMS, legend: null, viz: { esri: { time: [1609459200000, 1640995199999] } } };
  const entry = await esriPlugin.chart(layer, { geojson: SQUARE }, { fetch, zoom: 12, kind: "line", params: chartParams(layer) });
  const [r] = entry.results(CTX);
  assert.ok(r.data.columns.includes("Stable"), r.data.columns.join(","));
});
