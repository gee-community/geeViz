import { test } from "node:test";
import assert from "node:assert/strict";
import {
  prepareViz,
  legendFor,
  normalizeClassProp,
  getLookupDicts,
  createColorCycle,
  normVecStyle,
} from "../js/engine/viz.js";
import { legendMarkup, swatchColors, restorePinned, orderFromStored } from "../js/ui/legend.js";

// LCMS 2025-11 stores its class properties as comma-separated strings.
const LCMS_INFO = {
  layerType: "ImageCollection",
  bandNames: ["Land_Cover"],
  Land_Cover_class_names: "Trees,Tall Shrubs & Trees Mix (AK Only),Shrubs & Trees Mix",
  Land_Cover_class_values: "1,2,3",
  Land_Cover_class_palette: "004e2b,009344,61bb46",
};

test("autoViz with class properties gives a class legend", async () => {
  const { viz, legend } = await prepareViz(null, { autoViz: true, layerType: "geeImageCollection", eeObjInfo: LCMS_INFO }, { name: "LCMS" });
  assert.deepEqual(legend, {
    type: "classes",
    title: "LCMS",
    items: [
      { label: "1- Trees", color: "#004e2b" },
      { label: "2- Tall Shrubs & Trees Mix (AK Only)", color: "#009344" },
      { label: "3- Shrubs & Trees Mix", color: "#61bb46" },
    ],
  });
  assert.equal(viz.bands, "Land_Cover");
  assert.deepEqual(viz.queryDict, { 1: "Trees", 2: "Tall Shrubs & Trees Mix (AK Only)", 3: "Shrubs & Trees Mix" });
});

test("autoViz evaluates a server-side object info once, asynchronously", async () => {
  let calls = 0;
  const evaluateInfo = async () => {
    calls++;
    return LCMS_INFO;
  };
  const { legend } = await prepareViz({}, { autoViz: true, layerType: "geeImage" }, { name: "x", evaluateInfo });
  assert.equal(calls, 1);
  assert.equal(legend.items.length, 3);
});

test("includeClassValues false drops the values from the labels", async () => {
  const { legend } = await prepareViz(null, { autoViz: true, includeClassValues: false, layerType: "geeImage", eeObjInfo: LCMS_INFO }, { name: "x" });
  assert.equal(legend.items[0].label, "Trees");
});

test("normalizeClassProp splits on commas not followed by a space", () => {
  assert.deepEqual(normalizeClassProp("a,b, c,d", false), ["a", "b, c", "d"]);
  assert.deepEqual(normalizeClassProp("1,2,x", true), [1, 2, "x"]);
  assert.deepEqual(normalizeClassProp([1, 2], true), [1, 2]);
});

test("getLookupDicts falls back to empty dicts when metadata is missing", () => {
  assert.deepEqual(getLookupDicts("b", {}, {}, {}), { classLegendDict: {}, queryDict: {} });
});

test("min, max and palette give a ramp legend", async () => {
  const { legend } = await prepareViz(null, { layerType: "geeImage", min: 0, max: 3000, palette: "000,FFF" }, { name: "SRTM" });
  assert.deepEqual(legend, { type: "ramp", title: "SRTM", min: 0, max: 3000, palette: ["#000", "#FFF"], labels: ["0", "3000"] });
});

test("a ramp with no palette is black to white and no min/max reads min/max", () => {
  const legend = legendFor({ layerType: "geeImage" }, "x");
  assert.deepEqual(legend.palette, ["#000", "#FFF"]);
  assert.deepEqual(legend.labels, ["min", "max"]);
});

test("a one-color palette is doubled; legend labels honor left/right text", () => {
  const legend = legendFor({ layerType: "geeImage", min: 1, max: 9, palette: ["#123456"], legendLabelLeftAfter: "m", legendLabelRight: "up to" }, "x");
  assert.deepEqual(legend.palette, ["#123456", "#123456"]);
  assert.deepEqual(legend.labels, ["1 m", "up to 9"]);
});

test("a three-band image has no legend", () => {
  assert.equal(legendFor({ layerType: "geeImage", bands: ["r", "g", "b"], min: 0, max: 1 }, "x"), null);
});

test("a vector viz with strokeColor gives an outline legend", async () => {
  const { viz, legend } = await prepareViz(null, { layerType: "geeVector", strokeColor: "ff834c" }, { name: "Boundary" });
  assert.equal(viz.strokeColor, "#ff834c");
  assert.equal(viz.fillColor, "#222222");
  assert.equal(viz.fillOpacity, 0.2);
  assert.equal(viz.strokeWeight, 3);
  assert.equal(viz.opacityRatio, 5);
  assert.deepEqual(legend, { type: "outline", title: "Boundary", label: "Boundary", color: "#ff834c", fill: "#222222", fillOpacity: 0.2, weight: 3 });
});

test("a default vector image takes the next color of the original's list", async () => {
  const nextColor = createColorCycle();
  const a = await prepareViz(null, { layerType: "geeVectorImage" }, { name: "a", nextColor });
  const b = await prepareViz(null, { layerType: "geeVectorImage" }, { name: "b", nextColor });
  assert.equal(a.viz.strokeColor, "#e6194b");
  assert.equal(b.viz.strokeColor, "#3cb44b");
  assert.equal(a.viz.fillOpacity, 0);
  assert.equal(a.viz.strokeWeight, 2);
  assert.equal(a.legend.type, "outline");
});

test("geoJSONVector cannot be queried", async () => {
  const { viz } = await prepareViz({}, { layerType: "geoJSONVector" }, { name: "g" });
  assert.equal(viz.canQuery, false);
});

test("a classLegendDict on a tile layer (tile legend v2) gives classes", () => {
  const legend = legendFor({ layerType: "tileMapService", classLegendDict: { Water: "00b6f0", Snow: "#e4f5fd" } }, "t");
  assert.deepEqual(legend.items, [
    { label: "Water", color: "#00b6f0" },
    { label: "Snow", color: "#e4f5fd" },
  ]);
});

test("tile and dynamic services with no legend information have no legend", () => {
  assert.equal(legendFor({ layerType: "tileMapService" }, "t"), null);
  assert.equal(legendFor({ layerType: "dynamicMapService" }, "d"), null);
});

test("a Delta legend object in the viz wins", () => {
  const own = { type: "outline", color: "#f00", label: "Mine" };
  assert.deepEqual(legendFor({ layerType: "geeImage", min: 0, max: 1, legend: own }, "x"), own);
});

test("normVecStyle adds # and the bundle's defaults", () => {
  assert.deepEqual(normVecStyle({ color: "00F", fillColor: "red" }), {
    strokeColor: "#00F",
    fillColor: "red",
    strokeWeight: 3,
    strokeOpacity: 1,
    fillOpacity: 0,
  });
});

test("legendMarkup escapes labels and titles", () => {
  const html = legendMarkup({ type: "classes", items: [{ label: '</script><b>x</b>"', color: "#fff" }] });
  assert.ok(!html.includes("<b>"));
  assert.ok(html.includes("&lt;/script&gt;&lt;b&gt;x&lt;/b&gt;&quot;"));
  const ramp = legendMarkup({ type: "ramp", palette: ["#000"], labels: ["<i>", "1"] });
  assert.ok(!ramp.includes("<i>"));
  const outline = legendMarkup({ type: "outline", color: "#f00", label: "<u>a</u>" });
  assert.ok(outline.includes("&lt;u&gt;"));
});

test("legendMarkup never writes inline styles", () => {
  const html = legendMarkup({ type: "classes", items: [{ label: "a", color: "#fff" }] }) + legendMarkup({ type: "ramp", palette: ["#000", "#fff"], labels: ["0", "1"] });
  assert.ok(!/style=/.test(html));
});

test("swatchColors: up to four class colors, the ramp, or the outline", () => {
  const items = ["#1", "#2", "#3", "#4", "#5"].map((c) => ({ label: c, color: c }));
  assert.deepEqual(swatchColors({ type: "classes", items }), { kind: "classes", colors: ["#1", "#2", "#3", "#4"] });
  assert.deepEqual(swatchColors({ type: "ramp", palette: ["#000", "#fff"] }), { kind: "ramp", colors: ["#000", "#fff"] });
  assert.deepEqual(swatchColors({ type: "outline", color: "#f00" }), { kind: "outline", colors: ["#f00"] });
  assert.equal(swatchColors(null), null);
});

test("restorePinned keeps pinned layers at their index whichever way others move", () => {
  // P pinned at 0; B dragged to the top lands above P, P goes back to 0.
  assert.deepEqual(restorePinned(["B", "P", "A"], [[0, "P"]]), ["P", "B", "A"]);
  // P pinned at 2; A dragged below P, P goes back to 2.
  assert.deepEqual(restorePinned(["B", "P", "A"], [[2, "P"]]), ["B", "A", "P"]);
  // Two pinned layers.
  assert.deepEqual(restorePinned(["C", "P", "A", "Q", "B"], [[0, "P"], [4, "Q"]]), ["P", "C", "A", "B", "Q"]);
});

test("orderFromStored reorders only the stored layers among their own slots", () => {
  // current top-first; stored is bottom-up as the original's urlParams.layerOrders
  assert.deepEqual(orderFromStored(["d", "c", "b", "a"], ["c", "a", "b", "zzz"]), ["d", "b", "a", "c"]);
  assert.deepEqual(orderFromStored(["b", "a"], null), ["b", "a"]);
});
