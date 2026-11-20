import { test } from "node:test";
import assert from "node:assert/strict";
import { worldPx, tileBounds, flatten, effectiveStyle, createVectorTileOverlay } from "../js/engine/vectortiles.js";

test("Web Mercator pixels and tile bounds agree", () => {
  assert.deepEqual(worldPx(-180, 0, 0).map(Math.round), [0, 128]);
  assert.deepEqual(worldPx(0, 0, 1).map(Math.round), [256, 256]);
  const b = tileBounds(0, 0, 1);
  assert.equal(b.west, -180);
  assert.equal(b.east, 0);
  assert.ok(Math.abs(b.north - 85.0511) < 1e-3 && Math.abs(b.south) < 1e-9);
  const [x, y] = worldPx(b.east, b.south, 1);
  assert.deepEqual([Math.round(x), Math.round(y)], [256, 256]);
});

test("GeoJSON flattens to drawable parts with bounds", () => {
  const fc = {
    type: "FeatureCollection",
    features: [
      { type: "Feature", geometry: { type: "Polygon", coordinates: [[[0, 0], [2, 0], [2, 1], [0, 0]]] } },
      { type: "Feature", geometry: { type: "MultiPolygon", coordinates: [[[[5, 5], [6, 5], [6, 6], [5, 5]]], [[[8, 8], [9, 8], [9, 9], [8, 8]]]] } },
      { type: "Feature", geometry: { type: "LineString", coordinates: [[-1, -1], [1, 3]] } },
      { type: "Feature", geometry: { type: "GeometryCollection", geometries: [{ type: "Point", coordinates: [4, 4] }] } },
      { type: "Feature", geometry: null },
    ],
  };
  const parts = flatten(fc);
  assert.deepEqual(parts.map((p) => p.kind), ["polygon", "polygon", "polygon", "line", "point"]);
  assert.deepEqual(parts[0].bbox, [0, 0, 2, 1]);
  assert.deepEqual(parts[3].bbox, [-1, -1, 1, 3]);
  assert.equal(flatten({ type: "Point", coordinates: [1, 2] }).length, 1);
});

test("the opacity slider: stroke at the opacity, fill at its ratio, as the original", () => {
  const st = { strokeColor: "#f00", strokeOpacity: 1, fillOpacity: 0.3 };
  assert.deepEqual(effectiveStyle(st, 1, false), st);
  assert.deepEqual(effectiveStyle(st, 0.5, true, 2), { ...st, strokeOpacity: 0.5, fillOpacity: 0.25 });
});

// a canvas that records what is drawn
function fakeDoc() {
  const ops = [];
  const ctx = new Proxy({}, {
    get: (t, k) => (k in t ? t[k] : (...a) => ops.push([k, ...a])),
    set: (t, k, v) => ((t[k] = v), ops.push(["set", k, v]), true),
  });
  return { ops, createElement: () => ({ style: {}, getContext: () => ctx }) };
}
const google = { Size: function (w, h) { this.width = w; this.height = h; } };

test("a tile draws only the features that touch it, and redraws on opacity", () => {
  const geojson = { type: "Polygon", coordinates: [[[-100, 38], [-98, 38], [-98, 40], [-100, 38]]] };
  const o = createVectorTileOverlay({ google, geojson, style: { strokeColor: "#f00", strokeWeight: 2, strokeOpacity: 1, fillOpacity: 0.2, fillColor: "#0f0" }, dpr: 1 });
  // zoom 4: the polygon is in tile x=3, y=6
  const hit = fakeDoc();
  o.getTile({ x: 3, y: 6 }, 4, hit);
  assert.ok(hit.ops.some((op) => op[0] === "fill"), "fills the polygon");
  assert.ok(hit.ops.some((op) => op[0] === "stroke"));
  const miss = fakeDoc();
  o.getTile({ x: 12, y: 6 }, 4, miss);
  assert.ok(!miss.ops.some((op) => op[0] === "fill" || op[0] === "stroke"), "nothing in a far tile");
  assert.deepEqual(o.stats(), { total: 2, loaded: 2, failed: 0 });
  const before = hit.ops.length;
  o.setOpacity(0.5);
  assert.ok(hit.ops.length > before, "redrawn");
  assert.equal(o.style().strokeOpacity, 0.5);
  assert.equal(o.getOpacity(), 0.5);
});
