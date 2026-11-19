// Parity of delta/js/engine/charts.js with geeViz/outputLib/charts.py.
// Fixtures come from geeViz/tests/delta/make_fixtures.py, which runs
// charts.py's own functions on recorded raw reduction dicts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  SPLIT_STR,
  AREA_FORMAT_DICT,
  truncateClassName,
  normalizeClassProp,
  pyRound,
  pySum,
  stackBandNames,
  objInfoFromProps,
  parseThematicResults,
  parseContinuousResults,
  convertPixelArea,
  autoScale,
  stripSentinelColumns,
} from "../js/engine/charts.js";

const FIX = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "tests", "delta", "fixtures");
const load = (n) => JSON.parse(readFileSync(join(FIX, n), "utf-8"));
const all = readdirSync(FIX).filter((f) => f.endsWith(".json")).map((f) => [f, load(f)]);
const thematic = all.filter(([, f]) => f.kind === "thematic");
const continuous = all.filter(([, f]) => f.kind === "continuous");

// Deep equality with numbers compared to 1e-9.
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

test("constants match charts.py", () => {
  assert.equal(SPLIT_STR, "----");
  assert.deepEqual(AREA_FORMAT_DICT.Hectares, { mult: 0.09, label: "ha", places: 0, scale: 30 });
  assert.deepEqual(AREA_FORMAT_DICT.Acres, { mult: 0.222395, label: "Acres", places: 0, scale: 30 });
  assert.deepEqual(AREA_FORMAT_DICT.Percentage, { mult: null, label: "% Area", places: 2, scale: 30 });
  assert.deepEqual(AREA_FORMAT_DICT.Pixels, { mult: 1.0, label: "Pixels", places: 0, scale: 30 });
});

test("pyRound equals Python round() (half-even on the exact binary value)", () => {
  const { round } = load("pyfuncs.json");
  assert.ok(round.length > 1000);
  for (const [x, n, want] of round) assert.equal(pyRound(x, n), want, `round(${x}, ${n})`);
});

test("pySum equals Python sum() (Neumaier-compensated floats, plain ints)", () => {
  const { sum } = load("pyfuncs.json");
  for (const [vals, want] of sum) assert.equal(pySum(vals), want, JSON.stringify(vals));
});

test("truncateClassName equals charts.truncate_class_name", () => {
  for (const [n, m, want] of load("pyfuncs.json").truncate) assert.equal(truncateClassName(n, m), want, `${n} ${m}`);
});

test("normalizeClassProp equals charts._normalize_class_prop", () => {
  for (const [v, asInt, want] of load("pyfuncs.json").normalize) assert.deepEqual(normalizeClassProp(v, asInt), want, JSON.stringify(v));
});

test("objInfoFromProps equals charts.get_obj_info for recorded image properties", () => {
  for (const [name, fx] of all.filter(([, f]) => f.props)) {
    const got = objInfoFromProps(fx.props, fx.objInfo.bandNames, fx.objInfo.objType, fx.objInfo.size);
    assert.deepEqual(got, fx.objInfo, name);
  }
});

test("stackBandNames is label-major, band-minor like prepare_for_reduction", () => {
  for (const [name, fx] of [...thematic, ...continuous].filter(([, f]) => f.labels && f.labels.length)) {
    assert.deepEqual(stackBandNames(fx.labels, fx.objInfo.bandNames), fx.stackBandNames, name);
  }
  assert.deepEqual(stackBandNames(["2020", "2021"], ["a", "b"]), ["2020----a", "2020----b", "2021----a", "2021----b"]);
});

// Delta charts a label whose histogram is missing, null or empty as a gap
// (null) in that band's columns; charts.py's fillna(0) makes it 0. Apply
// exactly that difference to charts.py's output; everything else is
// charts.py's.
function withGaps(want, fx) {
  const out = structuredClone(want);
  const bands = fx.objInfo.bandNames;
  const multi = bands.length > 1;
  const labels = fx.labels.length ? fx.labels : [null];
  labels.forEach((x, ri) => {
    for (const bn of bands) {
      const h = fx.raw[x === null ? bn : `${x}----${bn}`];
      if (h && Object.keys(h).length) continue;
      out.columns.forEach((c, ci) => {
        if (multi && !c.startsWith(`${bn}----`)) return;
        assert.equal(out.rows[ri].values[ci], 0, `charts.py fills ${x} ${c} with 0`);
        out.rows[ri].values[ci] = null;
      });
    }
  });
  return out;
}

for (const [name, fx] of thematic) {
  test(`parseThematicResults matches charts.parse_thematic_results: ${name}`, () => {
    for (const [key, want] of Object.entries(fx.expected)) {
      const [af, scale] = key.split("@");
      const got = stripSentinelColumns(parseThematicResults(fx.raw, fx.objInfo, fx.labels, af, Number(scale)));
      close(got, withGaps(want, fx), `${name} ${key}`);
    }
  });
}

for (const [name, fx] of continuous) {
  test(`parseContinuousResults matches charts.parse_continuous_results: ${name}`, () => {
    close(parseContinuousResults(fx.raw, fx.objInfo, fx.labels), fx.expected, name);
  });
}

test("recorded summarize_and_chart output equals the parse of its raw dict", () => {
  for (const [name, fx] of [...thematic, ...continuous].filter(([, f]) => f.summarize)) {
    const got = fx.kind === "thematic"
      ? stripSentinelColumns(parseThematicResults(fx.raw, fx.objInfo, fx.labels, "Percentage", 30))
      : parseContinuousResults(fx.raw, fx.objInfo, fx.labels);
    close(got, fx.summarize, name);
  }
});

test("parseThematic keeps missing labels as null", () => {
  const fx = load("missing_year.json");
  const got = parseThematicResults(fx.raw, fx.objInfo, fx.labels, "Percentage", 30);
  assert.deepEqual(got.columns, ["Trees", "Shrubs", "Barren"]);
  assert.deepEqual(got.rows.map((r) => r.x), ["2002", "2003", "2004", "2005"]);
  assert.deepEqual(got.rows[1].values, [null, null, null]);
  // later years are not shifted into 2003's slot
  assert.deepEqual(got.rows[2].values, [50, 30.12, 19.88]);
  // a class absent from a year that has data is 0, not a gap
  assert.deepEqual(got.rows[3].values, [53.33, 46.67, 0]);
  // a null histogram (all masked) is a gap too
  const raw2 = { ...fx.raw, "2004----Land_Cover": null };
  assert.deepEqual(parseThematicResults(raw2, fx.objInfo, fx.labels, "Hectares", 30).rows[2].values, [null, null, null]);
});

test("convertPixelArea converts counts as charts.py does", () => {
  assert.equal(convertPixelArea(1000, 30, "Hectares"), 90);
  assert.equal(convertPixelArea(1000, 60, "Hectares"), 360);
  assert.equal(convertPixelArea(1000, 30, "Acres"), 222);
  assert.equal(convertPixelArea(123.5, 30, "Pixels"), 123.5);
  assert.equal(convertPixelArea(25, 30, "Percentage", 200), 12.5);
  assert.equal(convertPixelArea(1, 30, "Percentage", 3), 33.33);
});

test("autoScale: port of area-charting.js autoSetScale", () => {
  const T = [30, 0, -2361915.0, 0, -30, 3177735.0];
  // at or above minZoomSpecifiedScale nothing changes
  assert.deepEqual(autoScale(11, 30, 11), { scale: 30, transform: null, scaleMult: 1, nominalScale: 30 });
  assert.deepEqual(autoScale(14, 30, 11), { scale: 30, transform: null, scaleMult: 1, nominalScale: 30 });
  // 2x per zoom level below
  assert.equal(autoScale(10, 30, 11).scale, 60);
  assert.equal(autoScale(8, 30, 11).scale, 240);
  // at most 64x
  assert.equal(autoScale(2, 30, 11).scale, 30 * 64);
  assert.equal(autoScale(2, 30, 11).scaleMult, 64);
  // minZoomSpecifiedScale honored
  assert.equal(autoScale(8, 30, 9).scale, 60);
  // the default minimum zoom is 11
  assert.equal(autoScale(9, 30).scale, 120);
  // with a transform, the transform is scaled and scale becomes null; input not mutated
  const r = autoScale(9, null, 11, 64, T);
  assert.deepEqual(r, { scale: null, transform: [120, 0, -2361915.0, 0, -120, 3177735.0], scaleMult: 4, nominalScale: 120 });
  assert.equal(T[0], 30);
});

// Source checks run on code with comments removed: the modules' comments
// mention getInfo and reduceRegion while explaining what they avoid.
const ENGINE = join(dirname(fileURLToPath(import.meta.url)), "..", "js", "engine");
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

test("stripComments removes line and block comments, keeps code", () => {
  const s = stripComments("a(); // getInfo()\n/* reduceRegion */ b('http://x');\n");
  assert.ok(!s.includes("getInfo") && !s.includes("reduceRegion"));
  assert.ok(s.includes("a();") && s.includes("b('http://x');"));
});

test("no getInfo, and one reduceRegion call site shared by charts and Sankey", () => {
  const charts = stripComments(readFileSync(join(ENGINE, "charts.js"), "utf-8"));
  const sankey = stripComments(readFileSync(join(ENGINE, "sankey.js"), "utf-8"));
  for (const src of [charts, sankey]) assert.ok(!/getInfo/.test(src));
  assert.equal(charts.match(/\.reduceRegion\(/g).length, 1);
  assert.equal(sankey.match(/\.reduceRegion\(/g), null);
  // prepareSankeyData reduces every period pair in one reduceArea call
  assert.equal(sankey.match(/reduceArea\(/g).length, 1);
  assert.ok(charts.includes("bestEffort: true, maxPixels: 1e13"));
});
