// ArcGIS heatmap, dot density and pie chart renderers drawn by Delta
// (js/esri/surfaces.js), on recorded drawingInfo.
import { test } from "node:test";
import assert from "node:assert/strict";
import { response } from "./esrifake.mjs";
import { heatGrid, heatColor, dotValueAt, dotsIn, pieSlices, interiorPoint } from "../js/esri/surfaces.js";
import { rendererFor } from "../js/esri/renderers.js";
import { scaleAt } from "../js/esri/features.js";
import { legendMarkup } from "../js/ui/legend.js";
import { flatten } from "../js/engine/vectortiles.js";

const di = (n) => response(n).drawingInfo;
const SQUARE = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]];

test("dot value follows the scale from the reference scale", () => {
  const r = { dotValue: 100, referenceScale: scaleAt(10) };
  assert.equal(dotValueAt(r, 10), 100);
  assert.ok(Math.abs(dotValueAt(r, 9) - 400) < 1e-6, "one zoom out: scale doubles, dots stand for 4 times as much");
  assert.equal(dotValueAt({ dotValue: 50 }, 3), 50, "no reference scale: fixed");
});

test("dots: as many as the value buys, inside the polygon, the same every time", () => {
  const a = dotsIn(SQUARE, 1000 / 100, 42);
  assert.equal(a.length, 10);
  assert.deepEqual(dotsIn(SQUARE, 10, 42), a);
  assert.notDeepEqual(dotsIn(SQUARE, 10, 43), a);
  // an L shape: none land in the cut-out corner
  const L = [[[0, 0], [10, 0], [10, 5], [5, 5], [5, 10], [0, 10], [0, 0]]];
  const many = dotsIn(L, 100, 7);
  assert.equal(many.length, 100);
  many.forEach(([x, y]) => assert.ok(!(x > 5 && y > 5), `${x},${y} is outside`));
});

test("heatmap: the density peaks at the point, colored by the last stop at the top", () => {
  const g = heatGrid([[50, 60, 1]], 128, 10);
  let max = -1;
  let at = -1;
  g.forEach((v, i) => {
    if (v > max) {
      max = v;
      at = i;
    }
  });
  assert.equal(at, 60 * 128 + 50);
  assert.ok(g[60 * 128 + 70] < g[60 * 128 + 55]);
  const stops = di("drawinginfo_heatmap").renderer.colorStops;
  assert.deepEqual(heatColor(1, stops), [255, 255, 0, 255]);
  assert.equal(heatColor(0, stops)[3], 0, "nothing below the first stops");
});

test("pie: slices by value, others below the threshold", () => {
  const s = pieSlices([3, 1], ["#a00", "#0a0"]);
  assert.deepEqual(s.map((x) => Math.round(x.end - x.start)), [270, 90]);
  const o = pieSlices([90, 9, 1], ["#a", "#b", "#c"], { threshold: 0.05, othersColor: "#ccc" });
  assert.equal(o.length, 3);
  assert.equal(o[2].color, "#ccc");
  assert.deepEqual(pieSlices([0, 0], ["#a", "#b"]), []);
});

test("a pie sits inside its polygon", () => {
  const [x, y] = interiorPoint(SQUARE);
  assert.ok(Math.abs(x - 5) < 1e-9 && Math.abs(y - 5) < 1e-9);
  // a C shape: its centroid is in the gap; the point is moved inside
  const C = [[[0, 0], [10, 0], [10, 2], [2, 2], [2, 8], [10, 8], [10, 10], [0, 10], [0, 0]]];
  const [cx, cy] = interiorPoint(C);
  assert.ok(cx < 2 || cy < 2 || cy > 8, `${cx},${cy}`);
});

test("the recorded renderers build, draw whole tiles, and have legends", () => {
  const heat = rendererFor(di("drawinginfo_heatmap"), null, "esriGeometryPoint");
  assert.equal(heat.type, "heatmap");
  assert.equal(typeof heat.drawTile, "function");
  const hl = heat.legend("Heat");
  assert.deepEqual(hl.ramps[0].labels, ["Sparse", "Dense"]);
  assert.ok(legendMarkup(hl).includes('data-r="0"'));
  assert.equal(heat.padPx, 30);

  const dots = rendererFor(di("drawinginfo_dotdensity"), null, "esriGeometryPolygon");
  assert.equal(dots.type, "dotDensity");
  assert.deepEqual(dots.fields, ["Sheet0__Population"]);
  const dl = dots.legend("People", 8);
  assert.equal(dl.items[0].label, "Population");
  assert.equal(dl.items[0].glyph.fill, "#730000");
  assert.equal(dl.caption, "1 dot = 20,000");
  assert.ok(legendMarkup(dl).includes("1 dot = 20,000"));

  const pie = rendererFor(di("drawinginfo_piechart"), null, "esriGeometryPoint");
  assert.equal(pie.type, "pieChart");
  assert.deepEqual(pie.legend("Crops").items.map((i) => i.label), ["Crops_on_Arable", "Garden_Vines", "Trees"]);
});

test("a renderer type Delta does not know draws with the default symbol and says so", () => {
  const r = rendererFor({ renderer: { type: "flowRenderer" } }, null, "esriGeometryPolygon");
  assert.ok(r.styleFor({}).symbol);
  assert.match(r.legend("x").note, /flowRenderer renderers are not supported/);
});

test("fractional dots round by a seeded draw, so many small polygons keep their total", async () => {
  const { dotCount } = await import("../js/esri/surfaces.js");
  assert.equal(dotCount(10, 1), 10);
  assert.ok([0, 1].includes(dotCount(0.5, 9)));
  assert.equal(dotCount(0.3, 5), dotCount(0.3, 5), "the same for the same seed");
  let n = 0;
  for (let s = 0; s < 2000; s++) n += dotCount(0.3, s * 7919 + 1);
  assert.ok(n > 520 && n < 680, String(n));
});

test("a layer's drawingInfo transparency is its opacity; a heatmap fetches more points per tile", () => {
  const heat = rendererFor(di("drawinginfo_heatmap"), null, "esriGeometryPoint");
  assert.ok(Math.abs(heat.alpha - 0.78) < 1e-9);
  assert.equal(heat.maxFeatures, 20000);
  assert.equal(rendererFor(di("drawinginfo_dotdensity"), null, "esriGeometryPolygon").alpha, 1);
  assert.equal(rendererFor({ renderer: { type: "simple" }, transparency: 50 }).alpha, 0.5);
});

test("dot density draws only a tile's own dots: zoomed in, a big polygon stays fast", () => {
  const ring = Array.from({ length: 500 }, (_, k) => [Math.cos((k / 500) * 2 * Math.PI), Math.sin((k / 500) * 2 * Math.PI)]);
  ring.push(ring[0]);
  const fc = { type: "FeatureCollection", features: [{ type: "Feature", id: 1, properties: { v: 1e6 }, geometry: { type: "Polygon", coordinates: [ring] } }] };
  const r = rendererFor({ renderer: { type: "dotDensity", attributes: [{ field: "v", color: [0, 0, 0, 255] }], dotValue: 1000, dotSize: 1, referenceScale: scaleAt(10) } }, null, "esriGeometryPolygon");
  let rects = 0;
  const ctx = new Proxy({}, { get: (t, k) => (k === "fillRect" ? () => rects++ : t[k] !== undefined ? t[k] : () => {}), set: (t, k, v) => ((t[k] = v), true) });
  const z = 14;
  const n = 1 << z;
  const coord = { x: Math.floor(((0.1 + 180) / 360) * n), y: Math.floor(n / 2) - 6 };
  const parts = flatten(fc);
  const t0 = Date.now();
  r.drawTile(ctx, parts, { coord, zoom: z, px: () => [0, 0], opacity: 1 });
  const ms = Date.now() - t0;
  assert.ok(ms < 300, `${ms} ms`);
  // about the polygon's dots times the tile's share of its area
  const tileDeg = 360 / n;
  const expect = (1e6 / dotValueAt({ dotValue: 1000, referenceScale: scaleAt(10) }, z)) * ((tileDeg * tileDeg) / Math.PI);
  assert.ok(rects > expect * 0.3 && rects < expect * 3, `${rects} dots, about ${expect.toFixed(1)} expected`);
});
