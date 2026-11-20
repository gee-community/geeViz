// Right pane output: heading with where the result applies, jump chips when
// there are two or more results, one collapsible card per result with its
// own actions, and the list of selected features. Ported from the approved
// mockup's renderResults and card(); the time series chart is a port of
// 5chart-manager.js makeQueryTable (Plotly, lines and markers, class names
// as y tick labels). Names, labels and values are set as text.
import { formatArea, smartToFixed } from "../util.js";
import { breakLabels, resultCsv, resultText, isInfoWindowMode } from "../engine/query.js";
import { chartCsv } from "../engine/areachart.js";
import { chartTheme } from "../charts/theme.js";
import { renderChart, chartPng } from "../charts/plotly.js";
import { renderSankey, sankeyPng } from "../charts/sankey.js";

const ACTIONS = {
  copy: { icon: "ti-copy", title: "Copy" },
  csv: { icon: "ti-file-spreadsheet", title: "Download CSV" },
  png: { icon: "ti-photo-down", title: "Save PNG" },
  expand: { icon: "ti-arrows-maximize", title: "Expand" },
  clear: { icon: "ti-trash", title: "Clear" },
};

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}

function iconButton(icon, title, act) {
  const b = el("button", "ib");
  b.type = "button";
  b.title = title;
  b.setAttribute("aria-label", title);
  if (act) b.dataset.act = act;
  b.appendChild(el("i", "ti " + icon));
  return b;
}

function swatch(color) {
  const s = el("span", "sw");
  s.style.background = color;
  return s;
}

const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---- chart (Plotly) ----
function chartFigure(r, settings, big) {
  const d = r.data;
  const prec = d.precision || {};
  const round = (v) => (v === null ? null : smartToFixed(v, prec.chartDecimalProportion ?? 0.25, prec.chartPrecision ?? 3));
  const ink = token("--dz-ink");
  const mute = token("--dz-mute");
  const line = token("--dz-line");
  const fontSize = settings.yLabelFontSize || 10;
  const traces = [];
  d.series.forEach((s) => {
    const name = (String(s.name).slice(0, 50).match(/.{1,15}/g) || [s.name]).join("<br>");
    const y = s.y.map(round);
    const base = {
      x: d.x,
      y,
      customdata: s.labels.map((l) => (l === null ? "" : l)),
      hovertemplate: s.labels.some((l) => l !== null) ? "%{x}<br>%{customdata} (%{y})<extra></extra>" : "%{x}<br>%{y}<extra></extra>",
      name,
    };
    if (!s.classColors) {
      traces.push({ ...base, mode: "lines+markers", line: { color: s.color || undefined, width: 1 }, marker: { size: 6 } });
      return;
    }
    // Thematic: each point in its class's color, and the line held as a step in
    // the class of the year it starts from, so the line's color is the class.
    traces.push(...classSegments(d.x, y, s.classColors, mute));
    traces.push({ ...base, mode: "markers", marker: { size: 7, color: s.classColors.map((c) => c || mute), line: { width: 1, color: token("--dz-solid") } } });
  });
  let yaxis = { tickfont: { size: fontSize, color: mute }, gridcolor: line, zerolinecolor: line, automargin: true, title: d.yLabel ? { text: d.yLabel, font: { size: 12 } } : undefined };
  if (d.queryDict && d.series.length) {
    // Only the values present get a label; the rest of the range stays blank (as the original).
    const ys = d.series[0].y.filter((v) => v !== null);
    if (ys.length) {
      const lo = Math.min(...ys);
      const hi = Math.max(...ys);
      const vals = [];
      for (let v = lo; v <= hi; v++) vals.push(v);
      const labels = vals.map((v) => (ys.indexOf(v) === -1 ? " " : d.queryDict[v] !== undefined ? String(d.queryDict[v]) : String(v)));
      yaxis = { ...yaxis, tickmode: "array", tickvals: vals, ticktext: breakLabels(labels, settings) };
    }
  }
  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: token("--dz-font-body"), color: ink, size: 11 },
    margin: { l: 40, r: 8, t: 8, b: 40, pad: 0 },
    height: big ? 520 : 220,
    showlegend: d.series.length > 1,
    legend: { font: { size: fontSize } },
    xaxis: { tickangle: 45, tickformat: d.xTickDateFormat || undefined, tickfont: { size: fontSize, color: mute }, gridcolor: line, automargin: true },
    yaxis,
  };
  return { traces, layout };
}

// Step-line traces for a thematic series: one trace per run of points that
// share a class color, each held level until the next point (hv), drawn under
// the markers, without hover or legend entries.
export function classSegments(x, y, colors, fallback) {
  const out = [];
  let run = null;
  for (let i = 0; i < y.length - 1; i++) {
    if (y[i] === null || y[i + 1] === null) {
      run = null;
      continue;
    }
    const c = colors[i] || fallback;
    if (!run || run.color !== c || run.end !== i) {
      run = { color: c, xs: [x[i]], ys: [y[i]], end: i };
      out.push(run);
    }
    run.xs.push(x[i + 1]);
    run.ys.push(y[i + 1]);
    run.end = i + 1;
  }
  return out.map((r) => ({ x: r.xs, y: r.ys, mode: "lines", line: { color: r.color, width: 2, shape: "hv" }, hoverinfo: "skip", showlegend: false }));
}

function plot(chartEl, r, settings, big) {
  if (!window.Plotly) return;
  const { traces, layout } = chartFigure(r, settings, big);
  window.Plotly.react(chartEl, traces, layout, { displayModeBar: false, responsive: true });
}

// ---- card bodies ----
// Distance and Area: the measured values in the mono font.
function measureBody(r) {
  const b = el("div", "qv");
  r.data.lines.forEach(([label, value]) => {
    const row = el("div", "val-big");
    row.append(el("span", "val-band", label), el("span", "val-main mono", value));
    b.appendChild(row);
  });
  return b;
}

function valueBody(r) {
  const b = el("div", "qv");
  if (r.data.error) b.appendChild(el("div", "val-code mono", r.data.error));
  if (!r.data.bands.length && !r.data.error) b.appendChild(el("div", "val-code", "No data at this point"));
  const many = r.data.bands.length > 1;
  r.data.bands.forEach((x) => {
    const row = el("div", "val-big");
    if (x.color) row.appendChild(swatch(x.color));
    if (many) row.appendChild(el("span", "val-band", x.band));
    row.appendChild(el("span", "val-main" + (x.label === null ? " mono" : ""), x.label !== null ? x.label : x.display));
    if (x.label !== null) row.appendChild(el("span", "val-code mono", "value " + x.display));
    b.appendChild(row);
  });
  return b;
}

function seriesBody(r, settings) {
  const b = el("div", "qs");
  const last = r.data.latest;
  if (last) {
    const row = el("div", "val-big");
    if (last.color) row.appendChild(swatch(last.color));
    const shown = last.label !== null ? last.label : Number.isInteger(last.value) ? String(last.value) : smartToFixed(last.value, 0.25, 3);
    row.appendChild(el("span", "val-main", shown));
    // say which value this is: the map draws a collection with its reducer
    const how = last.how && last.how !== "latest" ? last.how + ", " : "";
    row.appendChild(el("span", "val-code mono", how + (last.label !== null ? "value " + last.value + ", " : "") + last.x));
    row.title = last.how === "latest" ? "The latest value, as the map shows this layer" : "The " + last.how + " over the series, as the map shows this layer";
    b.appendChild(row);
  } else {
    b.appendChild(el("div", "val-code", "No data at this point"));
  }
  if (r.data.series.length) {
    const chart = el("div", "qchart");
    b.appendChild(chart);
    b._plot = () => plot(chart, r, settings, false);
    b._chart = chart;
  }
  return b;
}

// Chart area cards: a Plotly chart with its legend, or a d3 Sankey drawn at
// the card's width (redrawn when the width changes).
function areaChartBody(r, settings) {
  const b = el("div", "qa");
  const chart = el("div", r.kind === "sankey" ? "sankey-wrap" : "achart");
  b.appendChild(chart);
  b._chart = chart;
  if (r.kind === "sankey") {
    let width = 0;
    b._plot = () => {
      width = chart.clientWidth;
      renderSankey(chart, r, chartTheme());
    };
    if (typeof ResizeObserver === "function") {
      const ro = new ResizeObserver(() => {
        if (chart.clientWidth && Math.abs(chart.clientWidth - width) > 1) b._plot();
      });
      ro.observe(chart);
      b._dispose = () => ro.disconnect();
    }
  } else {
    b._plot = () => renderChart(chart, r, chartTheme(), settings);
  }
  return b;
}

function tableBody(r) {
  const b = el("div", "qt");
  if (!r.data.rows.length) {
    b.appendChild(el("div", "val-code", r.meta));
    return b;
  }
  const t = el("table", "kv");
  const tb = el("tbody");
  r.data.rows.forEach(([k, v]) => {
    const tr = el("tr");
    tr.append(el("th", null, k), el("td", "mono", v));
    tb.appendChild(tr);
  });
  t.appendChild(tb);
  b.appendChild(t);
  return b;
}

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const safeName = (s) => String(s).replace(/[\\/:*?"<>|]+/g, "-").trim() || "query";
const isAreaChart = (r) => r.kind === "chart" || r.kind === "sankey";

// port of area-charting.js makeChart outFilename: layer name, area name and scale
function chartFileName(r) {
  return safeName(`${r.data.layerName} ${r.data.areaLabel} (${r.data.nominalScale}m)`);
}

// port of getQueryImages nameEnd
function nameEnd(r) {
  const p = r.data.point;
  return p ? " Queried Values for Lng " + p.lng.toFixed(3) + " Lat " + p.lat.toFixed(3) : "";
}

export function mountOutput(store, { mountEl, whereEl, chipsEl, busyEl, notify, query, measure } = {}) {
  const phoneMq = matchMedia("(max-width: 760px)");
  const cards = new Map(); // result id -> {el, result, body}
  const closed = new Set();
  let selEl = null;
  let emptyEl = null;
  let modal = null;
  const settings = () => store.get().chartSettings || {};
  const say = notify || (() => {});
  const getMeasure = () => (typeof measure === "function" ? measure() : measure);
  const getQuery = () => (typeof query === "function" ? query() : query);

  function act(r, name, body) {
    if (name === "copy") {
      const text = r.kind === "measure" ? r.data.text : resultText(r);
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(() => say("Copied " + r.title), () => say("Copy is not allowed here"));
    } else if (name === "csv" && isAreaChart(r)) {
      download(chartFileName(r) + ".csv", chartCsv(r), "text/csv;charset=utf-8");
    } else if (name === "csv") {
      download(safeName(r.title + nameEnd(r)) + ".csv", resultCsv(r), "text/csv");
    } else if (name === "png" && isAreaChart(r)) {
      const save = r.kind === "sankey" ? sankeyPng : chartPng;
      Promise.resolve(body && body._chart ? save(body._chart, chartFileName(r), chartTheme()) : null).catch((e) => say(String(e && e.message ? e.message : e)));
    } else if (name === "png") {
      if (window.Plotly && body && body._chart) {
        window.Plotly.downloadImage(body._chart, { format: "png", width: 900, height: 600, filename: safeName(r.title + nameEnd(r)) });
      }
    } else if (name === "clear") {
      if (getMeasure()) getMeasure().clear();
    } else if (name === "expand") {
      expand(r);
    }
  }

  function buildBody(r) {
    if (isAreaChart(r)) return areaChartBody(r, settings());
    if (r.kind === "measure") return measureBody(r);
    if (r.kind === "series") return seriesBody(r, settings());
    if (r.kind === "table") return tableBody(r);
    return valueBody(r);
  }

  function buildCard(r) {
    const card = el("div", "card-r");
    card.dataset.rid = r.id;
    const h = el("div", "h");
    h.setAttribute("role", "button");
    h.tabIndex = 0;
    h.append(el("b", null, r.title), el("span", "val-code mono", r.meta), el("i", "ti ti-chevron-down"));
    const toggle = () => {
      if (closed.has(r.id)) closed.delete(r.id);
      else closed.add(r.id);
      card.classList.toggle("closed", closed.has(r.id));
      h.setAttribute("aria-expanded", String(!closed.has(r.id)));
    };
    h.addEventListener("click", toggle);
    h.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggle();
      }
    });
    const b = el("div", "b");
    const body = buildBody(r);
    const acts = el("div", "acts");
    (r.actions || []).forEach((a) => {
      const spec = ACTIONS[a];
      if (!spec) return;
      const btn = iconButton(spec.icon, spec.title, a);
      btn.addEventListener("click", () => act(r, a, body));
      acts.appendChild(btn);
    });
    b.append(body, acts);
    card.append(h, b);
    card.classList.toggle("closed", closed.has(r.id));
    h.setAttribute("aria-expanded", String(!closed.has(r.id)));
    return { el: card, result: r, body };
  }

  function expand(r) {
    if (!modal) {
      modal = el("dialog", "dz-modal");
      const head = el("div", "dz-modal-h");
      const title = el("b");
      const close = iconButton("ti-x", "Close");
      close.addEventListener("click", () => modal.close());
      head.append(title, close);
      const body = el("div", "dz-modal-b");
      modal.append(head, body);
      modal.addEventListener("click", (e) => e.target === modal && modal.close());
      document.body.appendChild(modal);
    }
    modal.querySelector(".dz-modal-h b").textContent = r.title + (r.meta ? " (" + r.meta + ")" : "");
    const body = modal.querySelector(".dz-modal-b");
    if (r.kind === "series") {
      const chart = el("div", "qchart big");
      body.replaceChildren(chart);
      modal.showModal();
      plot(chart, r, settings(), true);
    } else if (r.kind === "chart") {
      const chart = el("div", "achart big");
      body.replaceChildren(chart);
      modal.showModal();
      renderChart(chart, r, chartTheme(), settings(), { big: true });
    } else if (r.kind === "sankey") {
      const chart = el("div", "sankey-wrap big");
      body.replaceChildren(chart);
      modal.showModal();
      renderSankey(chart, r, chartTheme());
    } else {
      body.replaceChildren(buildBody(r));
      modal.showModal();
    }
  }

  // ---- selected features (select layers) ----
  function buildSelections(sel, units) {
    const card = el("div", "card-r sel-card");
    const h = el("div", "h");
    h.append(el("b", null, "Selected areas"), el("span", "val-code mono", sel.length + (sel.length === 1 ? " selection" : " selections")));
    const b = el("div", "b");
    const list = el("ul", "sel-list");
    sel.forEach((x) => {
      const li = el("li");
      li.append(el("span", "sel-name", x.name), el("span", "val-code", x.layerName));
      const rm = iconButton("ti-x", "Remove " + x.name, "remove");
      rm.addEventListener("click", () => store.update((s) => ({ ...s, selections: s.selections.filter((y) => y.key !== x.key) }), "unselect-feature"));
      li.appendChild(rm);
      list.appendChild(li);
    });
    const total = sel.reduce((a, x) => a + (x.areaM2 || 0), 0);
    const foot = el("div", "sel-foot");
    foot.appendChild(el("span", "mono", "Total " + formatArea(total, units)));
    const clear = el("button", "chip", "Clear");
    clear.type = "button";
    clear.dataset.act = "clear";
    clear.addEventListener("click", () => store.set({ selections: [] }, "clear-selections"));
    foot.appendChild(clear);
    list.appendChild(foot);
    b.appendChild(list);
    card.append(h, b);
    return card;
  }

  // Chart area's empty state: the layers that could chart here if they were
  // on, each with the Layers row's toggle (turning one on re-charts).
  const hiddenChartable = (s) => {
    const byId = new Map(s.layers.map((l) => [l.id, l]));
    return s.order
      .map((id) => byId.get(id))
      .filter((l) => l && l.chartable && !l.visible && l.kind !== "select" && l.kind !== "areaChartOnly");
  };
  let listSig = "";
  let offEl = null;
  function chartableList(layers) {
    const list = el("div", "chartable-off");
    list.dataset.role = "chartable-off";
    list.appendChild(el("div", "cset-h", "Layers that can be charted here"));
    layers.forEach((l) => {
      const row = el("div", "layer off chartable-row");
      row.dataset.id = l.id;
      const r = el("div", "lrow");
      const tgl = el("button", "tgl");
      tgl.type = "button";
      tgl.setAttribute("aria-pressed", "false");
      tgl.setAttribute("aria-label", "Show " + l.name);
      tgl.title = "Turn on " + l.name + " and chart it";
      const name = el("span", "lname", l.name);
      const on = () => store.update((st) => ({ ...st, layers: st.layers.map((x) => (x.id === l.id ? { ...x, visible: true } : x)) }), "layer-toggle");
      tgl.addEventListener("click", on);
      name.addEventListener("click", on);
      r.append(tgl, name);
      row.appendChild(r);
      list.appendChild(row);
    });
    return list;
  }

  function render() {
    const s = store.get();
    // Chart area: where the charts apply, with the area's size in the units chosen
    const chartTool = s.tool === "chart";
    const size = chartTool && s.where && s.chartArea && s.chartArea.areaM2 ? ", " + formatArea(s.chartArea.areaM2, s.units) : "";
    if (whereEl) whereEl.textContent = (s.where || "") + size;
    if (busyEl) busyEl.hidden = !(s.querying || s.charting);
    const infoMode = phoneMq.matches && isInfoWindowMode(s.query.windowMode);
    const results = s.results || [];

    // drop cards whose result is gone or changed
    const keep = new Set(results.map((r) => r.id));
    for (const [id, c] of cards) {
      if (!keep.has(id) || c.result !== results.find((r) => r.id === id)) {
        if (c.body._dispose) c.body._dispose();
        c.el.remove();
        cards.delete(id);
      }
    }
    if (selEl) selEl.remove();
    selEl = s.selections && s.selections.length ? buildSelections(s.selections, s.units) : null;
    const nodes = [];
    if (selEl) nodes.push(selEl);
    const fresh = [];
    if (!infoMode) {
      results.forEach((r) => {
        let c = cards.get(r.id);
        if (!c) {
          c = buildCard(r);
          cards.set(r.id, c);
          fresh.push(c);
        }
        nodes.push(c.el);
      });
    }
    if (emptyEl) emptyEl.remove();
    emptyEl = null;
    if (offEl) offEl.remove();
    offEl = null;
    if (!results.length && s.where && !s.querying && !s.charting) {
      emptyEl = el("div", "droptip");
      const msg = chartTool
        ? "No visible layer can be charted here. Turn on a chartable layer in Layers, or choose one in the chart settings."
        : "No visible layer could be queried here. Turn one on in Layers.";
      emptyEl.append(el("i", "ti ti-info-circle"), el("span", null, msg));
      nodes.push(emptyEl);
      if (chartTool) {
        const off = hiddenChartable(s);
        if (off.length) nodes.push((offEl = chartableList(off)));
      }
    }
    nodes.forEach((n, i) => {
      if (mountEl.children[i] !== n) mountEl.insertBefore(n, mountEl.children[i] || null);
    });
    fresh.forEach((c) => c.body._plot && c.body._plot());

    // jump chips: two or more results
    if (chipsEl) {
      const chips = !infoMode && results.length > 1 ? results : [];
      chipsEl.replaceChildren(
        ...chips.map((r) => {
          const c = el("button", "chip", r.title + (results.filter((x) => x.title === r.title).length > 1 ? " (" + r.meta + ")" : ""));
          c.type = "button";
          c.addEventListener("click", () => {
            const card = cards.get(r.id);
            if (card) card.el.scrollIntoView({ behavior: "smooth", block: "start" });
          });
          return c;
        })
      );
    }

    // phones in infoWindow mode: point results open in a Google info window
    const q = getQuery();
    if (infoMode && q) {
      if (results.length) {
        const box = el("div", "dz-info");
        if (s.where) box.appendChild(el("div", "val-code mono", s.where));
        const built = results.map((r) => buildCard(r));
        built.forEach((c) => box.appendChild(c.el));
        q.openInfo(box);
        built.forEach((c) => c.body._plot && c.body._plot());
      } else q.closeInfo();
    }
  }

  function replot() {
    cards.forEach((c) => c.body._plot && c.body._plot());
  }

  ["results", "where", "querying", "charting", "chartArea", "selections", "units", "query", "tool"].forEach((k) => store.on("change:" + k, render));
  // the empty state's list follows the layers (not every loading tick)
  store.on("change:layers", (layers, s) => {
    const sig = s.tool === "chart" ? JSON.stringify(hiddenChartable(s).map((l) => [l.id, l.name])) : "";
    if (sig !== listSig) {
      listSig = sig;
      render();
    }
  });
  store.on("change:theme", () => setTimeout(replot, 0));
  store.on("change:chartSettings", replot);
  phoneMq.addEventListener("change", render);
  render();
  return { render, replot };
}
