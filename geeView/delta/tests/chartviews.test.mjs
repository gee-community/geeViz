// The pure halves of the chart renderers: the Plotly figure for a chart
// result (port of area-charting.js makeChart) and the d3-sankey graph for a
// Sankey result (port of charts.py D3_SANKEY_TEMPLATE, outer-column labels).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chartParams, lineResult, sankeyResult } from "../js/engine/areachart.js";
import { chartFigure, barData, quantile } from "../js/charts/plotly.js";
import { sankeyGraph, nodeLabelShown, linkTip } from "../js/charts/sankey.js";

const FIX = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "tests", "delta", "fixtures");
const load = (n) => JSON.parse(readFileSync(join(FIX, n), "utf-8"));
const LCMS = load("lcms_land_cover.json");
const NLCD = load("nlcd_2021.json");
const SANKEY = load("lcms_sankey.json");
const THEME = { ink: "#111", mute: "#666", faint: "#999", line: "#ddd", solid: "#fff", font: "Barlow", series: ["#00897b", "#e2602a"] };
const CTX = { units: "metric", showAs: "pct", areaLabel: "a", areaKey: "k", nominalScale: 30 };

function lcms(viz = {}) {
  const entry = { raw: LCMS.raw, objInfo: LCMS.objInfo, labels: LCMS.labels, isHistogram: true, sentinel: false, scale: 30 };
  return lineResult({ id: "l", name: "LCMS" }, chartParams({ kind: "ee", viz }), entry, CTX);
}

test("quantile: port of 1variables.js quantile", () => {
  assert.equal(quantile([1, 2, 3, 4], 0.5), 2.5);
  assert.equal(quantile([4, 1, 3], 0), 1);
  assert.equal(quantile([4, 1, 3], 1), 4);
});

test("chartFigure: a collection draws one line per class with gaps as null and class colors", () => {
  const r = lcms();
  const { traces, layout } = chartFigure(r, THEME, {}, {});
  assert.equal(traces.length, r.data.columns.length);
  traces.forEach((t, i) => {
    assert.deepEqual(t.x, LCMS.labels);
    assert.equal(t.mode, "lines+markers");
    assert.equal(t.type, undefined);
    assert.equal(t.y.length, r.data.rows.length);
    if (r.data.colors[i]) assert.equal(t.line.color, r.data.colors[i]);
  });
  assert.equal(layout.hovermode, "closest");
  assert.equal(layout.xaxis.showgrid, true);
  assert.equal(layout.yaxis.title.text, "% Area");
  assert.equal(layout.font.color, THEME.ink);
  assert.equal(layout.paper_bgcolor, "rgba(0,0,0,0)");
  // a gap stays a gap
  const gap = { ...r, data: { ...r.data, rows: r.data.rows.map((row, i) => (i === 1 ? { ...row, values: row.values.map(() => null) } : row)) } };
  assert.equal(chartFigure(gap, THEME, {}, {}).traces[0].y[1], null);
});

test("chartFigure: chartType, rangeSlider, hovermode, showGrid and yAxisLabel are honored", () => {
  const r = lcms({ areaChartParams: { chartType: "stacked-bar", rangeSlider: true, hovermode: "x unified", showGrid: false, yAxisLabel: "Share" } });
  const { traces, layout } = chartFigure(r, THEME, {}, {});
  assert.equal(traces[0].type, "bar");
  assert.equal(layout.barmode, "stack");
  assert.deepEqual(layout.xaxis.rangeslider, {});
  assert.equal(layout.hovermode, "x unified");
  assert.equal(layout.xaxis.showgrid, false);
  assert.equal(layout.yaxis.title.text, "Share");
  const sl = chartFigure(lcms({ areaChartParams: { chartType: "stacked-line" } }), THEME, {}, {});
  assert.equal(sl.traces[0].stackgroup, 0);
});

test("chartFigure: names are text (escaped), cut at chartLabelMaxLength and broken at chartLabelMaxWidth", () => {
  const r = lcms({ areaChartParams: { chartLabelMaxWidth: 4, chartLabelMaxLength: 8 } });
  const named = { ...r, data: { ...r.data, columns: ["<b>Trees</b> & more", ...r.data.columns.slice(1)] } };
  const { traces } = chartFigure(named, THEME, {}, {});
  assert.equal(traces[0].name, "&lt;b&gt;T<br>rees");
});

test("chartFigure: a single image is a bar chart, top barChartMaxClasses classes", () => {
  const entry = { raw: NLCD.raw, objInfo: NLCD.objInfo, labels: [], isHistogram: true, sentinel: false, scale: 30 };
  const r = lineResult({ id: "n", name: "NLCD" }, chartParams({ kind: "ee", viz: { areaChartParams: { barChartMaxClasses: 3 } } }), entry, CTX);
  const { traces, layout } = chartFigure(r, THEME, {}, {});
  assert.equal(traces.length, 1);
  assert.equal(traces[0].type, "bar");
  const b = barData(r);
  const vals = r.data.rows[0].values;
  const min = quantile(vals.slice(), 1 - 3 / vals.length);
  assert.equal(b.names.length, vals.filter((v) => v > min).length);
  assert.ok(b.names.length <= 3);
  // long class names lay the bars out horizontally (port of makeChart)
  assert.equal(b.orientation, "h");
  assert.equal(traces[0].orientation, "h");
  assert.equal(layout.xaxis.title.text, "% Area");
});

test("chartFigure: yLabelFontSize from chart settings sizes the tick labels", () => {
  const { layout } = chartFigure(lcms(), THEME, { yLabelFontSize: 14 }, {});
  assert.equal(layout.yaxis.tickfont.size, 14);
  assert.equal(layout.xaxis.tickfont.size, 14);
});

test("sankeyGraph: nodes per period and class that carry flow, links re-indexed, colors kept", () => {
  const entry = { raw: SANKEY.raw, objInfo: SANKEY.objInfo, band: SANKEY.band, periods: SANKEY.periods, scale: 30 };
  const r = sankeyResult({ id: "s", name: "LCMS" }, chartParams({ kind: "ee", viz: { sankey: true } }), entry, CTX);
  const g = sankeyGraph(r);
  assert.equal(g.links.length, r.data.links.length);
  assert.deepEqual(g.columns, ["2016-2018", "2020-2022"]);
  const used = new Set(r.data.links.flatMap((l) => [l.source, l.target]));
  assert.equal(g.nodes.length, used.size);
  g.links.forEach((l, i) => {
    const src = r.data.links[i];
    assert.equal(g.nodes[l.source].color, src.source_color);
    assert.equal(g.nodes[l.target].color, src.target_color);
    assert.equal(l.sourceColor, src.source_color);
    assert.equal(l.targetColor, src.target_color);
    assert.equal(l.value, src.value);
    assert.equal(g.nodes[l.source].period, "2016-2018");
    assert.equal(g.nodes[l.target].period, "2020-2022");
    assert.equal(src.source_name, "2016-2018 " + g.nodes[l.source].name);
  });
});

test("sankey labels: outer columns only", () => {
  const cols = 3;
  assert.equal(nodeLabelShown({ col: 0, y0: 0, y1: 20 }, cols), true);
  assert.equal(nodeLabelShown({ col: 1, y0: 0, y1: 20 }, cols), false);
  assert.equal(nodeLabelShown({ col: 2, y0: 0, y1: 20 }, cols), true);
  assert.equal(nodeLabelShown({ col: 2, y0: 0, y1: 4 }, cols), false, "too thin to label");
});

test("linkTip: source, target and value with the unit", () => {
  const t = linkTip({ source: { name: "Trees", period: "2016-2018" }, target: { name: "Shrubs", period: "2020-2022" }, value: 12.5 }, "%");
  assert.deepEqual(t, ["Trees (2016-2018) → Shrubs (2020-2022)", "12.5 %"]);
});
