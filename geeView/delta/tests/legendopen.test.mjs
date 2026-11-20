import { test } from "node:test";
import assert from "node:assert/strict";
import { legendsToOpen } from "../js/ui/layers.js";
import { legendFor } from "../js/engine/viz.js";

const ramp = legendFor({ min: 0, max: 1, palette: "000,fff" }, "R");
const classes = legendFor({ classLegendDict: { Forest: "0a0", Water: "00f" } }, "C");
const lay = (id, p) => ({ id, visible: true, legendOpen: false, legend: ramp, ...p });

test("a layer's legend opens the first time it is on with a legend", () => {
  const seen = new Set();
  assert.deepEqual(legendsToOpen([lay("a"), lay("b", { legend: classes })], seen), ["a", "b"]);
  // once only: a legend the user then closes stays closed
  assert.deepEqual(legendsToOpen([lay("a"), lay("b", { legend: classes })], seen), []);
});

test("addToLegend: false means no legend, so nothing opens", () => {
  const none = legendFor({ min: 0, max: 1, palette: "000,fff", addToLegend: false }, "N");
  assert.equal(none, null);
  assert.deepEqual(legendsToOpen([lay("n", { legend: none })], new Set()), []);
  // an empty class legend has nothing to show either
  assert.deepEqual(legendsToOpen([lay("e", { legend: legendFor({ classLegendDict: {} }, "E") })], new Set()), []);
});

test("waits for the layer to be on and for its legend to arrive", () => {
  const seen = new Set();
  assert.deepEqual(legendsToOpen([lay("a", { visible: false })], seen), []);
  assert.deepEqual(legendsToOpen([lay("a", { legend: null })], seen), []);
  assert.deepEqual(legendsToOpen([lay("a")], seen), ["a"]);
});

test("a layer whose legend the user already handled is left alone", () => {
  assert.deepEqual(legendsToOpen([lay("a")], new Set(["a"])), []);
  const seen = new Set();
  assert.deepEqual(legendsToOpen([lay("a", { legendOpen: true })], seen), []);
  assert.ok(seen.has("a"));
});
