// The map cursor has one owner, derived from the store.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../js/state.js";
import { createCursor, cursorFor } from "../js/engine/cursor.js";
import { sameLatLng, drawStyle, restyleShapes } from "../js/engine/drawing.js";

function fake() {
  const calls = [];
  return { calls, setOptions: (o) => calls.push(o.draggableCursor) , last: () => calls[calls.length - 1] };
}

test("cursorFor: crosshair for Distance, Area and Chart area Draw only", () => {
  assert.equal(cursorFor({ tool: "distance" }), "crosshair");
  assert.equal(cursorFor({ tool: "area" }), "crosshair");
  assert.equal(cursorFor({ tool: "chart", areaFrom: "draw" }), "crosshair");
  assert.equal(cursorFor({ tool: "chart", areaFrom: "view" }), null);
  assert.equal(cursorFor({ tool: "query" }), null);
  assert.equal(cursorFor({ tool: null, areaFrom: "draw" }), null);
});

test("switching Distance to Chart area (Draw) leaves the crosshair", () => {
  const store = createStore();
  const g = fake();
  createCursor(g, store);
  store.set({ tool: "distance" }, "t");
  assert.equal(g.last(), "crosshair");
  store.set({ tool: "chart", areaFrom: "draw" }, "t");
  assert.equal(g.last(), "crosshair"); // not wiped
  store.set({ areaFrom: "view" }, "t");
  assert.equal(g.last(), null);
  store.set({ areaFrom: "draw" }, "t");
  assert.equal(g.last(), "crosshair");
  store.set({ tool: "query" }, "t");
  assert.equal(g.last(), null);
});

test("drawing helpers", () => {
  const p = (lat, lng) => ({ lat: () => lat, lng: () => lng });
  assert.ok(sameLatLng(p(1, 2), p(1, 2)));
  assert.ok(!sameLatLng(p(1, 2), p(1, 2.1)));
  assert.ok(!sameLatLng(null, p(1, 2)));
  assert.equal(drawStyle("#abc").strokeColor, "#abc");
  const seen = [];
  restyleShapes([null, { setOptions: (o) => seen.push(o.strokeColor) }], "#123");
  assert.deepEqual(seen, ["#123"]);
});
