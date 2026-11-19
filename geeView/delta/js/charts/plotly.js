// Area charts with Plotly: one line per class over time, or bars for a
// single image. Port of lcms-viewer area-charting.js makeChart, themed from
// the CSS tokens (the original's fixed background and fonts are dropped).
// Class names are text: escaped before Plotly's own line breaks go in.
import { smartToFixed } from "../util.js";
import { downloadUrl } from "./theme.js";

// port of 1variables.js quantile
export function quantile(arr, q) {
  const sorted = arr.slice().sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  if (sorted[base + 1] !== undefined) return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
  return sorted[base];
}

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// port of makeChart's name.slice(0, chartLabelMaxLength).chunk(chartLabelMaxWidth).join("<br>")
function chunks(name, maxLength, maxWidth) {
  const s = String(name).slice(0, maxLength);
  return s.match(new RegExp(".{1," + Math.max(1, maxWidth) + "}", "g")) || [""];
}
export function plotName(name, maxLength = 100, maxWidth = 40) {
  return chunks(name, maxLength, maxWidth).map(esc).join("<br>");
}

const roundFor = (prec) => (v) => (v === null || v === undefined ? null : smartToFixed(v, prec.chartDecimalProportion, prec.chartPrecision));

// port of makeChart's single-image branch: the top barChartMaxClasses
// classes, bars laid out horizontally when labels are long.
export function barData(r) {
  const d = r.data;
  const st = d.settings;
  const round = roundFor(d.precision || {});
  const values = d.rows.length ? d.rows[0].values : [];
  let z = d.columns.map((c, i) => [chunks(c, st.chartLabelMaxLength, st.chartLabelMaxWidth).join("<br>"), values[i], d.colors[i], c]);
  if (z.length > st.barChartMaxClasses) {
    const pctlCut = 1 - st.barChartMaxClasses / z.length;
    const min = quantile(values.map((v) => (v === null ? 0 : v)), pctlCut);
    z = z.filter((row) => row[1] > min);
  }
  const maxLabelLen = Math.max(0, ...z.map((row) => row[0].length));
  const orientation = maxLabelLen > z.length || maxLabelLen > 6 ? "h" : "v";
  return {
    names: z.map((row) => plotName(row[3], st.chartLabelMaxLength, st.chartLabelMaxWidth)),
    rawNames: z.map((row) => row[3]),
    values: z.map((row) => round(row[1])),
    colors: z.map((row) => row[2]),
    orientation,
  };
}

const fill = (colors, theme) => colors.map((c, i) => c || theme.series[i % theme.series.length]);

// The Plotly figure for a chart result. chartSettings: the yLabel* globals.
export function chartFigure(r, theme, chartSettings = {}, opts = {}) {
  const d = r.data;
  const st = d.settings;
  const round = roundFor(d.precision || {});
  const fontSize = chartSettings.yLabelFontSize || 10;
  const tick = { size: fontSize, color: theme.mute };
  const axisTitle = (text) => ({ text: text || "", font: { size: 11, color: theme.mute } });
  const axis = { showgrid: st.showGrid, gridcolor: theme.line, zerolinecolor: theme.line, linecolor: theme.line, tickfont: tick, automargin: true };
  let traces;
  let xTitle;
  let yTitle;
  if (d.isCollection) {
    const colors = fill(d.colors, theme);
    const stack = st.chartType.indexOf("stack") > -1;
    const bar = st.chartType.indexOf("bar") > -1;
    const x = d.rows.map((row) => row.x);
    traces = d.columns.map((c, i) => ({
      x,
      y: d.rows.map((row) => round(row.values[i])),
      stackgroup: stack ? 0 : undefined,
      type: bar ? "bar" : undefined,
      mode: "lines+markers",
      name: plotName(c, st.chartLabelMaxLength, st.chartLabelMaxWidth),
      hovertemplate: "%{x}<br>%{fullData.name}: %{y}<extra></extra>",
      line: { color: colors[i], width: 1.5 },
      marker: { color: colors[i], size: 4 },
    }));
    xTitle = d.xLabel;
    yTitle = d.yLabel;
  } else {
    const b = barData(r);
    const h = b.orientation === "h";
    traces = [
      {
        type: "bar",
        orientation: b.orientation,
        x: h ? b.values : b.names,
        y: h ? b.names : b.values,
        name: esc(d.layerName),
        marker: { color: fill(b.colors, theme) },
        hovertemplate: (h ? "%{y}: %{x}" : "%{x}: %{y}") + "<extra></extra>",
      },
    ];
    xTitle = h ? d.yLabel : d.xLabel;
    yTitle = h ? d.xLabel : d.yLabel;
  }
  const layout = {
    hovermode: st.hovermode,
    barmode: st.chartType.indexOf("stack") > -1 ? "stack" : undefined,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: theme.font, color: theme.ink, size: 11 },
    hoverlabel: { bgcolor: theme.solid, bordercolor: theme.line, font: { color: theme.ink, family: theme.font } },
    showlegend: false,
    margin: { l: 44, r: 10, t: 8, b: 40, pad: 2 },
    height: opts.big ? 520 : 240,
    xaxis: { ...axis, tickangle: d.isCollection ? 45 : "auto", rangeslider: st.rangeSlider ? {} : null, title: axisTitle(xTitle) },
    yaxis: { ...axis, title: axisTitle(yTitle) },
  };
  return { traces, layout, config: { displayModeBar: false, responsive: true, scrollZoom: false } };
}

// The legend under a chart: a swatch and the class name (text) per series.
function legendEl(r, theme) {
  const d = r.data;
  const names = d.isCollection ? d.columns : barData(r).rawNames;
  const colors = fill(d.isCollection ? d.colors : barData(r).colors, theme);
  const box = document.createElement("div");
  box.className = "legend-mini";
  names.forEach((n, i) => {
    const s = document.createElement("span");
    const sw = document.createElement("i");
    sw.style.background = colors[i];
    s.append(sw, document.createTextNode(String(n)));
    box.appendChild(s);
  });
  return box;
}

// Draw a chart result into el: the Plotly chart and its legend.
export function renderChart(el, r, theme, chartSettings = {}, opts = {}) {
  if (!window.Plotly) return null;
  let plotEl = el.querySelector(".achart-plot");
  if (!plotEl) {
    plotEl = document.createElement("div");
    plotEl.className = "achart-plot";
    el.replaceChildren(plotEl);
  }
  const { traces, layout, config } = chartFigure(r, theme, chartSettings, opts);
  window.Plotly.react(plotEl, traces, layout, config);
  const old = el.querySelector(".legend-mini");
  const leg = legendEl(r, theme);
  if (old) old.replaceWith(leg);
  else el.appendChild(leg);
  return plotEl;
}

// Save a chart as PNG (Plotly toImage), on the theme's solid background.
export async function chartPng(el, filename, theme) {
  const plotEl = el && (el.classList.contains("achart-plot") ? el : el.querySelector(".achart-plot"));
  if (!window.Plotly || !plotEl || !plotEl.data) return null;
  const width = 900;
  const height = 600;
  const layout = { ...plotEl.layout, paper_bgcolor: theme.solid, plot_bgcolor: theme.solid, width, height };
  const url = await window.Plotly.toImage({ data: plotEl.data, layout }, { format: "png", width, height });
  downloadUrl(url, filename + ".png");
  return url;
}
