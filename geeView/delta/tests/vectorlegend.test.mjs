// A vector layer's legend is its symbol: one glyph per geometry type it
// holds (point, line, polygon), drawn as the map draws it. A polygon with no
// fill has no fill in its swatch.
import { test } from "node:test";
import assert from "node:assert/strict";
import { geomKinds, splitAlpha, vectorGlyphs, isSymbolLegend } from "../js/ui/legend.js";
import { legendsToOpen } from "../js/ui/layers.js";
import { legendFor } from "../js/engine/viz.js";

test("geomKinds: GeoJSON and Earth Engine type names, in point, line, polygon order", () => {
  assert.deepEqual(geomKinds(["MultiPolygon", "Point", "Polygon"]), ["point", "polygon"]);
  assert.deepEqual(geomKinds(["LineString", "MultiLineString", "LinearRing"]), ["line"]);
  assert.deepEqual(geomKinds(["polygon", "point"]), ["point", "polygon"]); // vectortiles kinds
  assert.deepEqual(geomKinds(["GeometryCollection", null]), []);
  assert.deepEqual(geomKinds(undefined), []);
});

test("splitAlpha: 3, 4, 6 and 8 digit hex, and names", () => {
  assert.deepEqual(splitAlpha("#f00"), { color: "#ff0000", alpha: 1 });
  assert.deepEqual(splitAlpha("000A"), { color: "#000000", alpha: 170 / 255 });
  assert.deepEqual(splitAlpha("#00ff0080"), { color: "#00ff00", alpha: 128 / 255 });
  assert.deepEqual(splitAlpha("teal"), { color: "teal", alpha: 1 });
});

const outline = (over) => ({ type: "outline", label: "L", color: "#ff0000", fill: "#0000ff", fillOpacity: 0.2, weight: 3, strokeOpacity: 1, paint: "canvas", ...over });

test("a filled GeoJSON polygon fills its swatch; an unfilled one does not", () => {
  const [filled] = vectorGlyphs(outline({ geoms: ["polygon"] }));
  assert.equal(filled.geom, "polygon");
  assert.equal(filled.fill, "#0000ff");
  assert.equal(filled.fillOpacity, 0.2);
  assert.equal(filled.stroke, "#ff0000");
  const [hollow] = vectorGlyphs(outline({ geoms: ["polygon"], fillOpacity: 0 }));
  assert.equal(hollow.fill, null);
  assert.equal(hollow.stroke, "#ff0000");
});

test("Earth Engine painted outlines (the default) never fill", () => {
  const [g] = vectorGlyphs(outline({ geoms: ["polygon"], paint: "paint", fill: "#222222", fillOpacity: 0 }));
  assert.equal(g.fill, null);
  assert.equal(g.stroke, "#ff0000");
});

test("Earth Engine styleParams: fill and stroke carry their own alpha", () => {
  const [g] = vectorGlyphs(outline({ geoms: ["polygon"], paint: "style", color: "#00ff00FF", fill: "#0000ff80", fillOpacity: undefined }));
  assert.equal(g.fill, "#0000ff");
  assert.equal(g.fillOpacity, 128 / 255);
  assert.equal(g.stroke, "#00ff00");
  const [clear] = vectorGlyphs(outline({ geoms: ["polygon"], paint: "style", color: "#00ff00FF", fill: "#00000000" }));
  assert.equal(clear.fill, null);
});

test("lines have no fill; points are drawn as the map draws them", () => {
  const glyphs = vectorGlyphs(outline({ geoms: ["point", "line", "polygon"] }));
  assert.deepEqual(glyphs.map((g) => g.geom), ["point", "line", "polygon"]);
  const [pt, ln] = glyphs;
  assert.equal(ln.fill, null);
  // GeoJSON points: a dot in the stroke color with a white ring (vectortiles.js)
  assert.equal(pt.fill, "#ff0000");
  assert.equal(pt.stroke, "#ffffff");
  // painted Earth Engine points: a solid dot in the stroke color
  const [eePt] = vectorGlyphs(outline({ geoms: ["point"], paint: "paint" }));
  assert.equal(eePt.fill, "#ff0000");
  assert.equal(eePt.stroke, null);
});

test("a dashed or dotted styleParams line is dashed in the swatch, points never", () => {
  const glyphs = vectorGlyphs(outline({ geoms: ["point", "line", "polygon"], paint: "style", lineType: "dashed", fill: "#00000000" }));
  assert.deepEqual(glyphs.map((g) => g.dash), [null, "dashed", "dashed"]);
  assert.deepEqual(vectorGlyphs(outline({ geoms: ["line"], paint: "style", lineType: "dotted" }))[0].dash, "dotted");
  assert.equal(vectorGlyphs(outline({ geoms: ["line"], lineType: "dashed" }))[0].dash, null); // GeoJSON lines draw solid
});

test("no stroke weight, no stroke", () => {
  const [g] = vectorGlyphs(outline({ geoms: ["polygon"], weight: 0 }));
  assert.equal(g.stroke, null);
  assert.equal(g.fill, "#0000ff");
});

test("before the geometry type is known, a vector shows a polygon", () => {
  assert.deepEqual(vectorGlyphs(outline({})).map((g) => g.geom), ["polygon"]);
});

test("a vector's symbol legend never opens: there is nothing more to show", () => {
  const vec = legendFor({ layerType: "geeVector", strokeColor: "#f00", addToClassLegend: true }, "Roads");
  assert.ok(isSymbolLegend(vec));
  const layers = [{ id: "v", visible: true, legend: vec, legendOpen: false }];
  assert.deepEqual(legendsToOpen(layers, new Set()), []);
  // a class legend still opens
  const classes = legendFor({ layerType: "geeImage", classLegendDict: { A: "f00" } }, "C");
  assert.ok(!isSymbolLegend(classes));
  assert.deepEqual(legendsToOpen([{ id: "c", visible: true, legend: classes, legendOpen: false }], new Set()), ["c"]);
});

test("legendFor says how the vector is painted", () => {
  assert.equal(legendFor({ layerType: "geeVector", strokeColor: "#f00", addToClassLegend: true }, "a").paint, "canvas");
  assert.equal(legendFor({ layerType: "geoJSONVector", strokeColor: "#f00", addToClassLegend: true }, "a").paint, "canvas");
  assert.equal(legendFor({ layerType: "geeVectorImage", strokeColor: "#f00", addToClassLegend: true }, "a").paint, "paint");
  assert.equal(legendFor({ layerType: "geeVectorImage", strokeColor: "#f00", styleParams: {}, addToClassLegend: true }, "a").paint, "style");
});

test("query radius: points and lines get a few screen pixels, polygons keep plotRadius", async () => {
  const { vectorQueryRadius, POINT_TOLERANCE_PX, LINE_TOLERANCE_PX } = await import("../js/engine/query.js");
  const mpp = (lat, z) => (156543.03392 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, z);
  const q = { scale: 30 };
  assert.equal(vectorQueryRadius(q, ["polygon"], 40, 10), 15);
  assert.equal(vectorQueryRadius(q, null, 40, 10), 15); // types not known yet
  assert.ok(Math.abs(vectorQueryRadius(q, ["point"], 40, 10) - POINT_TOLERANCE_PX * mpp(40, 10)) < 1e-6);
  assert.ok(Math.abs(vectorQueryRadius(q, ["line", "polygon"], 40, 10) - LINE_TOLERANCE_PX * mpp(40, 10)) < 1e-6);
  // zoomed far in, a few pixels is less than plotRadius: plotRadius wins
  assert.equal(vectorQueryRadius(q, ["point"], 40, 21), 15);
  assert.equal(vectorQueryRadius(q, ["point"], 40, undefined), 15);
});
