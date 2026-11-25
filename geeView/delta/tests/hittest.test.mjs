// Click-to-query on vectors drawn in the browser (GeoJSON and feature
// layers): what a click hits, in screen pixels at the zoom.
import { test } from "node:test";
import assert from "node:assert/strict";
import { hitTest } from "../js/engine/hittest.js";
import { flatten } from "../js/engine/vectortiles.js";

const Z = 12;
const PX = 360 / (256 * Math.pow(2, Z)); // degrees of longitude per pixel at Z
const at = (lng, lat, dxPx = 0) => ({ lng: lng + dxPx * PX, lat });
const fc = (...features) => ({ type: "FeatureCollection", features });
const feat = (id, geometry, properties = {}) => ({ type: "Feature", id, geometry, properties });

test("flatten keeps each part's feature: properties, id and geometry", () => {
  const g = { type: "MultiPolygon", coordinates: [[[[0, 0], [1, 0], [1, 1], [0, 0]]], [[[2, 2], [3, 2], [3, 3], [2, 2]]]] };
  const parts = flatten(fc(feat(7, g, { a: 1 })));
  assert.equal(parts.length, 2);
  parts.forEach((p) => {
    assert.equal(p.fid, 7);
    assert.deepEqual(p.props, { a: 1 });
    assert.equal(p.geom, g);
  });
  // features with no id are numbered in order
  const two = flatten(fc(feat(undefined, { type: "Point", coordinates: [0, 0] }), feat(undefined, { type: "Point", coordinates: [1, 1] })));
  assert.notEqual(two[0].fid, two[1].fid);
});

test("a point hits within 8 pixels plus its marker", () => {
  const parts = flatten(fc(feat(1, { type: "Point", coordinates: [-105, 40] })));
  assert.equal(hitTest(parts, at(-105, 40, 7), Z).length, 1);
  assert.equal(hitTest(parts, at(-105, 40, 11), Z).length, 1, "8 px plus the 4 px marker");
  assert.equal(hitTest(parts, at(-105, 40, 20), Z).length, 0);
});

test("a line hits within 5 pixels", () => {
  const parts = flatten(fc(feat(1, { type: "LineString", coordinates: [[-105, 39.9], [-105, 40.1]] })));
  assert.equal(hitTest(parts, at(-105, 40, 4), Z).length, 1);
  assert.equal(hitTest(parts, at(-105, 40, 9), Z).length, 0);
});

test("a polygon hits inside, not in its hole", () => {
  const outer = [[-105.1, 39.9], [-104.9, 39.9], [-104.9, 40.1], [-105.1, 40.1], [-105.1, 39.9]];
  const hole = [[-105.02, 39.98], [-104.98, 39.98], [-104.98, 40.02], [-105.02, 40.02], [-105.02, 39.98]];
  const parts = flatten(fc(feat(1, { type: "Polygon", coordinates: [outer, hole] })));
  assert.equal(hitTest(parts, at(-105.05, 40), Z).length, 1);
  assert.equal(hitTest(parts, at(-105, 40), Z).length, 0, "in the hole");
  assert.equal(hitTest(parts, at(-105.2, 40), Z).length, 0);
});

test("overlapping polygons: the one drawn last first; one hit per feature", () => {
  const sq = (d) => [[-105.1 + d, 39.9], [-104.9 + d, 39.9], [-104.9 + d, 40.1], [-105.1 + d, 40.1], [-105.1 + d, 39.9]];
  const parts = flatten(fc(feat("a", { type: "Polygon", coordinates: [sq(0)] }), feat("b", { type: "Polygon", coordinates: [sq(0.05)] })));
  assert.deepEqual(hitTest(parts, at(-105, 40), Z).map((p) => p.fid), ["b", "a"]);
  const multi = flatten(fc(feat("m", { type: "MultiPolygon", coordinates: [[sq(0)], [sq(0.01)]] })));
  assert.equal(hitTest(multi, at(-105, 40), Z).length, 1);
});
