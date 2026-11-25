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

// Without Earth Engine, elevation comes from USGS 3DEP (identify).
import { fakeFetch, response } from "./esrifake.mjs";
import { elevation3DEP, ELEVATION_3DEP_URL } from "../js/engine/maps.js";

test("3DEP elevation at a point, in whole meters", async () => {
  const fetch = fakeFetch([[ELEVATION_3DEP_URL + "/identify", "3dep_identify"]]);
  const m = await elevation3DEP(-105.08, 40.58, { fetch });
  assert.equal(m, Math.round(Number(response("3dep_identify").value)));
  const p = fetch.calls[0].params;
  assert.deepEqual(JSON.parse(p.geometry), { x: -105.08, y: 40.58, spatialReference: { wkid: 4326 } });
  assert.equal(p.returnCatalogItems, "false");
  assert.equal(p.returnGeometry, "false");
});

test("3DEP: NoData or a failure is no elevation", async () => {
  assert.equal(await elevation3DEP(0, 0, { fetch: fakeFetch([[() => true, { value: "NoData" }]]) }), null);
  assert.equal(await elevation3DEP(0, 0, { fetch: fakeFetch([[() => true, () => new TypeError("Failed to fetch")]]) }), null);
  assert.equal(await elevation3DEP(0, 0, { fetch: fakeFetch([[() => true, "error_body"]]) }), null);
});
