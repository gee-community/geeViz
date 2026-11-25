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

// Elevation from the AWS open terrain tiles (Terrarium PNGs): global and
// fast, one tile fetched for every point inside it.
import { terrariumMeters, terrainPixel, createTerrainElevation } from "../js/engine/maps.js";

test("Terrarium pixels decode to meters", () => {
  assert.equal(terrariumMeters(128, 0, 0), 0);
  assert.equal(terrariumMeters(133, 243, 128), 1523.5);
});

test("a point's terrain tile and pixel", () => {
  const p = terrainPixel(-105.08, 40.58, 12);
  assert.deepEqual([p.x, p.y, p.z], [852, 1542, 12]);
  assert.ok(p.px >= 0 && p.px < 256 && p.py >= 0 && p.py < 256);
});

test("one tile load answers every point in it; a failed tile is no elevation", async () => {
  const loads = [];
  const px = new Uint8ClampedArray(256 * 256 * 4).fill(0);
  for (let i = 0; i < px.length; i += 4) {
    px[i] = 133;
    px[i + 1] = 243;
    px[i + 2] = 128;
    px[i + 3] = 255;
  }
  const elev = createTerrainElevation({ loadPixels: (z, x, y) => (loads.push(`${z}/${x}/${y}`), Promise.resolve(px)) });
  assert.equal(await elev(-105.08, 40.57, 12), 1524);
  assert.equal(await elev(-105.0805, 40.5705, 12), 1524);
  assert.deepEqual(loads, ["12/852/1542"]);
  // deeper than the tiles go: the deepest zoom
  await elev(-105.08, 40.58, 20);
  assert.equal(loads[1].split("/")[0], "14");
  const failing = createTerrainElevation({ loadPixels: () => Promise.reject(new Error("offline")) });
  assert.equal(await failing(0, 0, 10), null);
});
