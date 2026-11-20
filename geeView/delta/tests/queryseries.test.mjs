import { test } from "node:test";
import assert from "node:assert/strict";
import { displayReducer, summarize, modeOf, seriesResult } from "../js/engine/query.js";
import { classSegments } from "../js/ui/output.js";

// as geeView.py serializes viz.reducer (ee.Reducer.X().serialize())
const ser = (name, args = {}) => JSON.stringify({ result: "0", values: { 0: { functionInvocationValue: { functionName: "Reducer." + name, arguments: args } } } });

test("the layer's display reducer is read from the serialized viz", () => {
  assert.equal(displayReducer({}), "lastNonNull"); // geeView's default
  assert.equal(displayReducer({ reducer: ser("mode") }), "mode");
  assert.equal(displayReducer({ reducer: ser("percentile", { percentiles: { constantValue: [50] } }) }), "percentile");
  assert.equal(displayReducer({ reducer: "not json" }), null);
});

test("the headline is the series reduced the way the map draws the layer", () => {
  const x = ["2000", "2001", "2002", "2003", "2004"];
  const y = [3, 1, 3, null, 1];
  assert.deepEqual(summarize("lastNonNull", x, y), { value: 1, x: "2004", how: "latest", reducer: "lastNonNull" });
  assert.deepEqual(summarize("firstNonNull", x, [null, 7, 1, 1, 1]), { value: 7, x: "2001", how: "first", reducer: "firstNonNull" });
  // mode over the years with data, not the latest
  assert.deepEqual(summarize("mode", x, [3, 1, 3, null, 1].map((v, i) => (i === 4 ? 3 : v))), { value: 3, x: "2000 to 2004", how: "most common", reducer: "mode" });
  assert.equal(summarize("mean", x, [1, 2, 3, null, 6]).value, 3);
  assert.equal(summarize("median", x, [1, 9, 3, null, 6]).value, 4.5);
  assert.equal(summarize("max", x, y).value, 3);
  // a reducer it cannot reproduce: the latest value, saying what the map shows
  assert.equal(summarize("percentile", x, y).how, "latest; the map shows percentile");
  assert.equal(summarize(null, x, y).how, "latest");
  assert.equal(summarize("mode", x, [null, null]), null);
});

test("mode: the most frequent value, a tie going to the smallest", () => {
  assert.equal(modeOf([5, 2, 5, 2, 9]), 2);
  assert.equal(modeOf([4, 4, 1]), 4);
});

test("a mode-drawn thematic layer headlines its most common class", () => {
  const viz = {
    reducer: ser("mode"),
    queryDict: { 1: "Trees", 3: "Shrubs" },
    class_values: { LC: [1, 3] },
    class_palette: { LC: ["005e00", "c8a000"] },
  };
  const out = { ids: ["a", "b", "c"], labels: ["2000", "2001", "2002"], bands: ["LC"], values: { a_LC: 1, b_LC: 1, c_LC: 3 }, hasTime: true };
  const r = seriesResult({ id: "l", name: "LC" }, viz, out, [0, 0]);
  assert.deepEqual(r.data.latest, { x: "2000 to 2002", band: "LC", value: 1, how: "most common", label: "Trees", color: "#005e00" });
});

test("thematic line segments take the class color of the year they start from", () => {
  const segs = classSegments(["a", "b", "c", "d", "e"], [1, 1, 3, null, 3], ["#0a0", "#0a0", "#cc0", null, "#cc0"], "#888");
  // a-b-c held in the first class, then nothing across the gap
  assert.equal(segs.length, 1);
  assert.deepEqual(segs[0].x, ["a", "b", "c"]);
  assert.equal(segs[0].line.color, "#0a0");
  assert.equal(segs[0].line.shape, "hv");
  const two = classSegments(["a", "b", "c"], [1, 3, 3], ["#0a0", "#cc0", "#cc0"], "#888");
  assert.deepEqual(two.map((s) => [s.line.color, s.x]), [["#0a0", ["a", "b"]], ["#cc0", ["b", "c"]]]);
  assert.ok(two.every((s) => s.hoverinfo === "skip" && s.showlegend === false));
});
