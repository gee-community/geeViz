import { test } from "node:test";
import assert from "node:assert/strict";
import { elevationValue, ELEVATION_SCALE } from "../js/engine/maps.js";

test("elevation reads the mosaic at 30 m, not its 1 degree default", () => {
  const calls = [];
  const chain = new Proxy(function () {}, {
    get: (t, k) => (...a) => (calls.push([k, ...a]), chain),
  });
  const ee = { ImageCollection: (id) => (calls.push(["ImageCollection", id]), chain), Reducer: { first: () => "first" }, Geometry: { Point: (c) => ["pt", c] } };
  elevationValue(ee, -111.9, 40.76);
  const rr = calls.find((c) => c[0] === "reduceRegion");
  assert.deepEqual(rr, ["reduceRegion", "first", ["pt", [-111.9, 40.76]], 30]);
  assert.equal(ELEVATION_SCALE, 30);
});
