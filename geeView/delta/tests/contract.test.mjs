import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createStore } from "../js/state.js";
import { createMapApi } from "../js/api.js";

const SRC = new URL("../../../../lcms-viewer/src/js/4map-manager.js", import.meta.url);

function originalMethodNames() {
  const text = fs.readFileSync(SRC, "utf8");
  const start = text.indexOf("function mp()");
  assert.ok(start > 0, "function mp() found");
  const end = text.indexOf("const Map2 = new mp()", start);
  const body = text.slice(start, end);
  const names = new Set();
  for (const m of body.matchAll(/this\.([A-Za-z_$][\w$]*)\s*=\s*function/g)) names.add(m[1]);
  return [...names];
}

test("MapApi implements every method on the original mp object", { skip: !fs.existsSync(SRC) && "lcms-viewer checkout not found beside geeViz; skipping contract check" }, () => {
  const names = originalMethodNames();
  assert.ok(names.length > 30, "extracted " + names.length);
  const api = createMapApi(createStore(), {});
  for (const n of names) assert.equal(typeof api[n], "function", n);
  assert.equal(typeof api.turnOffLayersWhenTimeLapseIsOn, "boolean");
  assert.equal(typeof api.canReorderLayers, "boolean");
});
