// Parity of delta/js/engine/sankey.js with charts.py prepare_sankey_data.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  SANKEY_MIN_PERCENTAGE,
  formatPeriod,
  ensureHexColor,
  transitionBandNames,
  buildSankeyFromHistogram,
} from "../js/engine/sankey.js";

const FIX = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "tests", "delta", "fixtures");
const load = (n) => JSON.parse(readFileSync(join(FIX, n), "utf-8"));

function close(actual, expected, path = "") {
  if (typeof expected === "number" && typeof actual === "number") {
    assert.ok(Math.abs(actual - expected) <= 1e-9, `${path}: ${actual} != ${expected}`);
    return;
  }
  if (expected === null || typeof expected !== "object") {
    assert.equal(actual, expected, path);
    return;
  }
  assert.equal(Array.isArray(actual), Array.isArray(expected), `${path}: array mismatch`);
  const ek = Object.keys(expected);
  assert.deepEqual(Object.keys(actual ?? {}), ek, `${path}: keys`);
  for (const k of ek) close(actual[k], expected[k], `${path}.${k}`);
}

const classInfoFor = (fx) => {
  const ci = fx.classInfoPy[fx.band];
  return { classValues: ci.class_values, classNames: ci.class_names, classPalette: ci.class_palette };
};

test("the viewer's default minimum percentage is 0.5", () => {
  assert.equal(SANKEY_MIN_PERCENTAGE, 0.5);
});

test("formatPeriod and ensureHexColor match charts.py", () => {
  assert.equal(formatPeriod([1985, 1987]), "1985-1987");
  assert.equal(formatPeriod([1990, 1990]), "1990");
  assert.equal(formatPeriod(2023), "2023");
  assert.equal(ensureHexColor("abc123"), "#abc123");
  assert.equal(ensureHexColor("#abc123"), "#abc123");
  assert.equal(ensureHexColor(null), null);
});

test("transitionBandNames: one band per consecutive period pair", () => {
  assert.deepEqual(transitionBandNames([[2016, 2018], [2020, 2022], 2023]), ["2016-2018---2020-2022", "2020-2022---2023"]);
});

for (const name of ["sankey_synthetic.json", "lcms_sankey.json"]) {
  test(`buildSankeyFromHistogram matches prepare_sankey_data: ${name}`, () => {
    const fx = load(name);
    for (const [key, want] of Object.entries(fx.expected)) {
      const [af, mp] = key.split("@");
      const got = buildSankeyFromHistogram(fx.raw, classInfoFor(fx), fx.periods, af, fx.scale, Number(mp));
      close(got, want, `${name} ${key}`);
    }
  });
}

test("recorded summarize_and_chart sankey equals the build from its raw dict", () => {
  const fx = load("lcms_sankey.json");
  close(buildSankeyFromHistogram(fx.raw, classInfoFor(fx), fx.periods, "Percentage", 30, 0.5), fx.summarize, "lcms");
});

test("flows below the minimum percentage leave the links but stay in the matrix", () => {
  const fx = load("sankey_synthetic.json");
  const ci = classInfoFor(fx);
  const at05 = buildSankeyFromHistogram(fx.raw, ci, fx.periods, "Percentage", 30, 0.5);
  const at0 = buildSankeyFromHistogram(fx.raw, ci, fx.periods, "Percentage", 30, 0);
  // Trees -> Shrubs is 3 of 1004 pixels (0.2988%): under 0.5, over 0
  const isTreesShrubs = (l) => l.source_name === "2016-2018 Trees" && l.target_name === "2020-2022 Shrubs";
  assert.equal(at05.links.filter(isTreesShrubs).length, 0);
  assert.equal(at0.links.filter(isTreesShrubs).length, 1);
  const m = at05.matrix["2016-2018 → 2020-2022"];
  assert.deepEqual(m.index, ["Trees", "Shrubs", "Barren"]);
  assert.deepEqual(m.columns, ["Trees", "Shrubs", "Barren"]);
  assert.equal(m.values[0][1], 0.3);
  // a flow of exactly the minimum is kept (charts.py compares with >=)
  const isShrubsBarren = (l) => l.source_name === "2020-2022 Shrubs" && l.target_name === "2023 Barren";
  assert.equal(at05.links.filter(isShrubsBarren).length, 1);
  assert.equal(at05.links.find(isShrubsBarren).value, 0.5);
  // a value outside the class list (9) is skipped in both
  assert.ok(at0.links.every((l) => !l.source_name.endsWith(" 9")));
  // default minimum is the viewer's 0.5
  close(buildSankeyFromHistogram(fx.raw, ci, fx.periods, "Percentage", 30), at05, "default");
});

test("a multi-band class info dict is read for the Sankey band, like charts.py", () => {
  const fx = load("sankey_synthetic.json");
  const lc = classInfoFor(fx);
  const other = { classValues: [1, 2, 3], classNames: ["A", "B", "C"], classPalette: ["111111", "222222", "333333"] };
  const want = buildSankeyFromHistogram(fx.raw, lc, fx.periods, "Percentage", 30, 0.5);
  close(buildSankeyFromHistogram(fx.raw, { Change: other, Land_Cover: lc }, fx.periods, "Percentage", 30, 0.5, "Land_Cover"), want, "by band");
  // an unknown band falls back to the first band's info
  close(buildSankeyFromHistogram(fx.raw, { Land_Cover: lc, Change: other }, fx.periods, "Percentage", 30, 0.5, "Nope"), want, "fallback");
});
