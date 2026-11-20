import { test } from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../js/state.js";

test("default state has the documented top-level keys", () => {
  const s = createStore().get();
  for (const k of ["layers", "order", "tool", "units", "showAs", "areaFrom", "results", "notices", "theme", "panes", "query", "chartSettings", "canReorder", "title", "turnOffLayersWhenTimeLapseIsOn"]) {
    assert.ok(k in s, k);
  }
  assert.equal(s.tool, null);
  assert.equal(s.units, "metric");
});

test("set emits change once and change:<key> only for changed keys", () => {
  const store = createStore();
  const events = [];
  store.on("change", (st, reason) => events.push(["change", reason]));
  store.on("change:units", () => events.push(["units"]));
  store.on("change:tool", () => events.push(["tool"]));
  store.set({ units: "imperial" }, "u");
  assert.equal(events.filter((e) => e[0] === "change").length, 1);
  assert.equal(events.filter((e) => e[0] === "units").length, 1);
  assert.equal(events.filter((e) => e[0] === "tool").length, 0);
  events.length = 0;
  store.set({ units: "imperial" }, "same");
  assert.equal(events.filter((e) => e[0] === "units").length, 0);
});

test("update and unsubscribe", () => {
  const store = createStore();
  let n = 0;
  const off = store.on("change:title", () => n++);
  store.update((s) => ({ ...s, title: "a" }), "t");
  assert.equal(store.get().title, "a");
  off();
  store.set({ title: "b" }, "t");
  assert.equal(n, 1);
});
