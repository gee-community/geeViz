// Right pane tool options: the units switch and the active tool's options.
// The tool buttons themselves are wired in shell.js (one active, clicking the
// active one turns it off and folds the pane). Ported from the approved
// mockup's opts() and units switch. Chart area adds the "Area from" and
// "Show as" switches and a settings panel (layers to chart, Sankey
// transition periods: port of area-charting.js populateChartLayerSelect and
// 2templates.js setupTransitionPeriodUI). Names are set as text.
import { UPLOAD_ACCEPT } from "../engine/areasources.js";
import { currentDefaults, insertPeriod, removePeriod, validatePeriods, yearRange } from "../engine/areachart.js";

const HINTS = {
  distance: "Click the map to start measuring. Double-click to finish. Drag a point to move it.",
  area: "Click the map to outline an area. Double-click to finish; click again for another polygon. Drag a point to move it.",
  query: "Double-click the map to query every visible layer at that point.",
  chart: "Pick where the area comes from. Every visible chartable layer gets charted inside it.",
};
const PHONE_HINTS = { query: "Tap the map to query every visible layer at that point." };

const SOURCES = [
  ["draw", "Draw"],
  ["view", "Map view"],
  ["upload", "Upload"],
  ["select", "Select"],
];
const SOURCE_HINTS = {
  draw: "Click the map to outline an area. Double-click to finish; click again for another polygon. Every polygon is charted together.",
  view: "Charts what the map shows, and again each time the map rests after you move it.",
  upload: "A .zip shapefile, .kml, .kmz, .gpkg, .gpx, .fgb or .geojson file. Files are converted on the geeViz server that serves this map; only the area outline is sent to Earth Engine.",
  select: "Click features of a select layer on the map, then chart them.",
};

// Which tools have something to work on: Chart area needs a layer that can
// be area charted, Query a layer that can be queried. Distance and Area always.
export function toolAvailability(s) {
  return {
    chart: s.layers.some((l) => l.chartable && l.kind !== "select"),
    query: s.layers.some((l) => l.queryable),
  };
}
export const hasSelectLayers = (s) => s.layers.some((l) => l.kind === "select");

// Transition periods in the url (the original's urlParams.transitionChartingYears).
export const PERIODS_PARAM = "transitionChartingYears";
export function readPeriodsParam(urlParams) {
  let v = urlParams && urlParams[PERIODS_PARAM];
  if (typeof v === "string") {
    try {
      v = JSON.parse(v);
    } catch (e) {
      v = null;
    }
  }
  if (!Array.isArray(v)) return null;
  const rows = v.filter((r) => Array.isArray(r) && r.length === 2).map((r) => [Number.parseInt(r[0], 10), Number.parseInt(r[1], 10)]);
  return rows.length ? rows : null;
}

export function hintFor(tool, phone) {
  if (!tool) return "";
  return (phone && PHONE_HINTS[tool]) || HINTS[tool] || "";
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}

function hintEl(text, cls = "topt-hint") {
  const d = el("div", cls);
  d.append(el("i", "ti ti-info-circle"), el("span", null, text));
  return d;
}

function seg(key, label, options, value, onPick) {
  const row = el("div", "row2");
  row.appendChild(el("span", "lbl", label));
  const s = el("div", "seg");
  s.dataset.k = key;
  s.setAttribute("role", "group");
  s.setAttribute("aria-label", label);
  options.forEach(([v, text]) => {
    const b = el("button", v === value ? "on" : "", text);
    b.type = "button";
    b.dataset.v = v;
    b.setAttribute("aria-pressed", String(v === value));
    b.addEventListener("click", () => onPick(v));
    s.appendChild(b);
  });
  row.appendChild(s);
  return row;
}

// Undo, redo and clear for the sketching tools, with the shortcuts in their tooltips.
const EDIT_ACTIONS = [
  ["undo", "ti-arrow-back-up", "Undo (Ctrl+Z)"],
  ["redo", "ti-arrow-forward-up", "Redo (Ctrl+Shift+Z or Ctrl+Y)"],
  ["clear", "ti-trash", "Clear all (Delete)"],
];

export function mountTools(store, { optionsEl, unitsEl, toolsEl, chart, measure, notify, urlParams } = {}) {
  const say = notify || (() => {});
  // a source action that fails tells the user instead of failing silently
  const attempt = (what, fn) =>
    Promise.resolve()
      .then(fn)
      .catch((e) => say(`${what} failed: ${e && e.message ? e.message : e}`));
  const phoneMq = matchMedia("(max-width: 760px)");
  const unitButtons = unitsEl ? Array.from(unitsEl.querySelectorAll("[data-u]")) : [];
  const sources = () => (typeof chart === "function" ? chart() : chart);
  const measurer = () => (typeof measure === "function" ? measure() : measure);
  // the sketch the active tool draws with: Distance, Area, or Chart area's Draw
  function activeSketch() {
    const s = store.get();
    if (s.tool === "distance" || s.tool === "area") {
      const m = measurer();
      return m && m.sketch ? m.sketch(s.tool) : null;
    }
    if (s.tool === "chart" && s.areaFrom === "draw") {
      const src = sources();
      return src && src.sketch ? src.sketch() : null;
    }
    return null;
  }
  function editBar() {
    const bar = el("div", "sk-bar");
    bar.setAttribute("role", "group");
    bar.setAttribute("aria-label", "Edit the drawing");
    EDIT_ACTIONS.forEach(([act, icon, tip]) => {
      const b = el("button", "ib");
      b.type = "button";
      b.dataset.sk = act;
      b.title = tip;
      b.setAttribute("aria-label", tip);
      b.appendChild(el("i", "ti " + icon));
      b.addEventListener("click", () => {
        const sk = activeSketch();
        if (sk) sk[act]();
      });
      bar.appendChild(b);
    });
    paintEditBar(bar);
    return bar;
  }
  function paintEditBar(bar) {
    const st = store.get().sketch;
    const mine = !!activeSketch() && st;
    bar.querySelector("[data-sk=undo]").disabled = !(mine && st.canUndo);
    bar.querySelector("[data-sk=redo]").disabled = !(mine && st.canRedo);
    bar.querySelector("[data-sk=clear]").disabled = !(mine && st.shapes > 0);
  }
  store.on("change:sketch", () => {
    if (optionsEl) optionsEl.querySelectorAll(".sk-bar").forEach(paintEditBar);
  });
  let settingsOpen = false;
  let draft = null; // transition period rows being edited
  let periodErrors = [];
  const params = urlParams || window.urlParams || (window.urlParams = {});
  const fromUrl = readPeriodsParam(params);
  if (fromUrl) store.set({ chartPeriodsGiven: fromUrl }, "chart-periods-url");

  function renderUnits() {
    const u = store.get().units;
    unitButtons.forEach((b) => {
      b.classList.toggle("on", b.dataset.u === u);
      b.setAttribute("aria-pressed", String(b.dataset.u === u));
    });
  }
  unitButtons.forEach((b) => b.addEventListener("click", () => store.set({ units: b.dataset.u }, "units")));

  // ---- Chart area settings: layers to chart and transition periods ----
  function layerChoices(s) {
    const box = el("div", "cset-sec");
    box.appendChild(el("div", "cset-h", "Layers to chart"));
    const layers = s.layers.filter((l) => l.chartable && l.kind !== "select");
    if (!layers.length) box.appendChild(el("div", "val-code", "No layer can be charted. Add one with canAreaChart or Map.addAreaChartLayer."));
    const choices = s.chartChoices || {};
    layers.forEach((l) => {
      const only = l.kind === "areaChartOnly";
      const on = only ? (choices[l.id] !== undefined ? !!choices[l.id] : !!l.visible) : choices[l.id] !== false;
      const lab = el("label", "cset-layer");
      const cb = el("input");
      cb.type = "checkbox";
      cb.checked = on;
      cb.dataset.layer = l.id;
      cb.addEventListener("change", () => store.update((st) => ({ ...st, chartChoices: { ...st.chartChoices, [l.id]: cb.checked } }), "chart-choice"));
      lab.append(cb, el("span", "cset-name", l.name), el("span", "val-code", only ? "chart only" : "when visible"));
      box.appendChild(lab);
    });
    return box;
  }

  // ---- Sankey transition periods: port of 2templates.js setupTransitionPeriodUI,
  // addRow, addTransitionRow, removeLastTransitionRow, removeRow and
  // getTransitionRowData. One row per period; single-year defaults at the ends
  // of the valid year range; "+" adds in the middle; rows drag to reorder.
  let sortable = null;
  function moveRow(from, to) {
    if (to < 0 || to >= draft.length || from === to) return;
    const [row] = draft.splice(from, 1);
    draft.splice(to, 0, row);
  }
  function storePeriodsParam(rows) {
    params[PERIODS_PARAM] = JSON.stringify(rows);
    try {
      const url = new URL(location.href);
      url.searchParams.set(PERIODS_PARAM, JSON.stringify(rows));
      history.replaceState(history.state, "", url);
    } catch (e) {
      /* history can be unavailable */
    }
  }
  function periodEditor(s) {
    const range = yearRange(s);
    if (!draft) {
      const start = s.chartPeriods || currentDefaults(s);
      if (start) draft = start.map((r) => r.slice());
    }
    const box = el("div", "cset-sec");
    box.dataset.role = "periods";
    box.title =
      "Define periods for transition area charting. Each row is a period (start year to end year). Periods should not overlap. The most common value for each period is used in the Sankey chart. Add or remove rows as needed.";
    box.appendChild(el("div", "cset-h", "Transition periods"));
    if (!draft || !range) {
      box.appendChild(el("div", "val-code", "Reading the years of the Sankey layers."));
      return box;
    }
    box.appendChild(el("div", "val-code", `Each row is a period, start year to end year, from ${range[0]} to ${range[1]}. Drag a row by its handle to reorder.`));
    const rangeTitle = `Enter a year within the valid range (${range[0]} - ${range[1]})`;
    const head = el("div", "cset-prow cset-phead");
    head.append(el("span"), el("span", "cset-ph", "Start year"), el("span"), el("span", "cset-ph", "End year"));
    const table = el("div", "cset-periods");
    draft.forEach((row, i) => {
      const r = el("div", "cset-prow");
      r.dataset.i = String(i);
      const grip = el("button", "ib cset-grip");
      grip.type = "button";
      grip.title = "Drag to reorder. The up and down arrow keys move this period.";
      grip.setAttribute("aria-label", `Move period ${i + 1} (up and down arrow keys)`);
      grip.appendChild(el("i", "ti ti-grip-vertical"));
      grip.addEventListener("keydown", (e) => {
        const to = e.key === "ArrowUp" ? i - 1 : e.key === "ArrowDown" ? i + 1 : null;
        if (to === null) return;
        e.preventDefault();
        if (to < 0 || to >= draft.length) return;
        moveRow(i, to);
        renderOptions();
        const g = optionsEl.querySelector(`.cset-prow[data-i="${to}"] .cset-grip`);
        if (g) g.focus();
      });
      r.appendChild(grip);
      [0, 1].forEach((j) => {
        const inp = el("input", "cset-year mono");
        inp.type = "number";
        inp.step = "1";
        inp.min = String(range[0]);
        inp.max = String(range[1]);
        inp.title = rangeTitle;
        inp.placeholder = "Year";
        inp.value = Number.isFinite(row[j]) ? String(row[j]) : "";
        inp.dataset.j = String(j);
        inp.setAttribute("aria-label", (j ? "End year of period " : "Start year of period ") + (i + 1));
        inp.addEventListener("input", () => {
          draft[i][j] = Number.parseInt(inp.value, 10);
          showErrors();
        });
        r.appendChild(inp);
        if (!j) r.appendChild(el("span", "val-code", "to"));
      });
      const x = el("button", "ib");
      x.type = "button";
      x.dataset.act = "remove-period";
      x.title = "Remove this transition period";
      x.setAttribute("aria-label", `Remove period ${i + 1}`);
      x.appendChild(el("i", "ti ti-x"));
      x.addEventListener("click", () => {
        draft.splice(i, 1);
        renderOptions();
      });
      r.appendChild(x);
      table.appendChild(r);
    });
    box.append(head, table);
    if (sortable) sortable.destroy();
    sortable = null;
    if (window.Sortable) {
      sortable = window.Sortable.create(table, {
        handle: ".cset-grip",
        draggable: ".cset-prow",
        animation: 120,
        onEnd(e) {
          if (e.oldIndex !== e.newIndex) moveRow(e.oldIndex, e.newIndex);
          renderOptions();
        },
      });
    }
    const acts = el("div", "cset-acts");
    const button = (act, icon, title, fn) => {
      const b = el("button", "ib");
      b.type = "button";
      b.dataset.act = act;
      b.title = title;
      b.setAttribute("aria-label", title);
      b.appendChild(el("i", "ti " + icon));
      b.addEventListener("click", fn);
      return b;
    };
    const add = button("add-period", "ti-plus", "Add a transition period in the middle", () => {
      draft = insertPeriod(draft, yearRange(store.get())).rows;
      renderOptions();
    });
    const rm = button("remove-last-period", "ti-minus", "Remove the second to last transition period", () => {
      draft = removePeriod(draft);
      renderOptions();
    });
    const apply = el("button", "chip", "Apply");
    apply.type = "button";
    apply.dataset.act = "apply-periods";
    apply.addEventListener("click", () => {
      const v = validatePeriods(draft, yearRange(store.get()));
      periodErrors = v.errors;
      if (v.periods) {
        store.set({ chartPeriods: v.periods, chartPeriodsUser: true }, "chart-periods");
        storePeriodsParam(v.periods);
      }
      renderOptions();
    });
    acts.append(add, rm, apply);
    box.appendChild(acts);
    const errBox = el("div", "cset-errs");
    errBox.setAttribute("role", "status");
    box.appendChild(errBox);
    // port of getTransitionRowData: every check, shown as the rows change; nothing charts until they pass
    function showErrors() {
      periodErrors = validatePeriods(draft, yearRange(store.get())).errors;
      errBox.replaceChildren(...periodErrors.map((e) => el("div", "cset-err", e)));
      apply.disabled = periodErrors.length > 0;
    }
    showErrors();
    return box;
  }

  function sourceRow(s) {
    const src = s.areaFrom;
    const box = el("div", "csrc");
    box.appendChild(hintEl(SOURCE_HINTS[src] || "", "topt-hint sub"));
    if (src === "draw") box.appendChild(editBar());
    if (src === "upload") {
      const lab = el("label", "chip file-chip");
      lab.appendChild(el("i", "ti ti-upload"));
      lab.appendChild(el("span", null, "Choose a file"));
      const inp = el("input");
      inp.type = "file";
      inp.accept = UPLOAD_ACCEPT;
      inp.dataset.role = "area-upload";
      inp.addEventListener("change", () => {
        const f = inp.files && inp.files[0];
        const src = sources();
        if (f && src) attempt("Charting the uploaded area", () => src.upload(f));
        inp.value = "";
      });
      lab.appendChild(inp);
      box.appendChild(lab);
    } else if (src === "select") {
      const n = (s.selections || []).length;
      const b = el("button", "chip", n ? `Chart ${n} selected ${n === 1 ? "area" : "areas"}` : "Chart selected areas");
      b.type = "button";
      b.dataset.act = "chart-selection";
      b.disabled = !n;
      b.addEventListener("click", () => sources() && attempt("Charting the selected areas", () => sources().chartSelection()));
      box.appendChild(b);
    }
    return box;
  }

  function chartOptions(s) {
    const nodes = [hintEl(HINTS.chart)];
    // Select only when there is a select layer to pick from
    const sources = SOURCES.filter(([v]) => v !== "select" || hasSelectLayers(s));
    nodes.push(seg("src", "Area from", sources, s.areaFrom, (v) => store.set({ areaFrom: v }, "areaFrom")));
    const show = seg("showas", "Show as", [["area", s.units === "imperial" ? "Acres" : "Hectares"], ["pct", "% of area"]], s.showAs, (v) => store.set({ showAs: v }, "showAs"));
    const gear = el("button", "ib" + (settingsOpen ? " on" : ""));
    gear.type = "button";
    gear.dataset.act = "chart-settings";
    gear.title = "Choose layers to chart, and transition periods for Sankey charts";
    gear.setAttribute("aria-label", gear.title);
    gear.setAttribute("aria-expanded", String(settingsOpen));
    gear.appendChild(el("i", "ti ti-adjustments-horizontal"));
    gear.addEventListener("click", () => {
      settingsOpen = !settingsOpen;
      if (!settingsOpen) {
        draft = null;
        periodErrors = [];
      }
      renderOptions();
    });
    show.appendChild(gear);
    nodes.push(show);
    nodes.push(sourceRow(s));
    if (settingsOpen) {
      const panel = el("div", "cset");
      panel.append(layerChoices(s), periodEditor(s));
      nodes.push(panel);
    }
    return nodes;
  }

  function renderOptions() {
    if (!optionsEl) return;
    const s = store.get();
    if (s.tool === "chart") {
      optionsEl.replaceChildren(...chartOptions(s));
      return;
    }
    const text = hintFor(s.tool, phoneMq.matches);
    const nodes = text ? [hintEl(text)] : [];
    if (s.tool === "distance" || s.tool === "area") nodes.push(editBar());
    optionsEl.replaceChildren(...nodes);
  }

  // Each tool has its own output: a new tool starts with an empty one.
  store.on("change:tool", () => {
    store.set({ results: [], where: "" }, "tool-output-reset");
    renderOptions();
  });
  store.on("change:units", () => {
    renderUnits();
    if (store.get().tool === "chart") renderOptions();
  });
  // Re-render chart options only when what they show changes (typing in a
  // period field is not interrupted by layers loading).
  const chartSig = (s) =>
    JSON.stringify([
      s.areaFrom,
      s.showAs,
      (s.selections || []).length,
      s.chartChoices,
      s.chartPeriods,
      s.chartYears,
      hasSelectLayers(s),
      s.layers.filter((l) => l.chartable).map((l) => [l.id, l.name, l.kind, l.visible]),
    ]);
  let lastSig = chartSig(store.get());
  store.on("change:chartPeriods", (v, st, reason) => {
    if (reason !== "chart-periods") draft = null; // filled in from the layers' years
  });
  store.on("change", (s) => {
    const sig = chartSig(s);
    if (sig === lastSig) return;
    lastSig = sig;
    if (s.tool === "chart") renderOptions();
  });
  phoneMq.addEventListener("change", renderOptions);

  // ---- tool strip: Chart area and Query show only with layers to work on ----
  // Checked after the current task, so a map script that turns a tool on
  // before or after adding its layers ends the same way. A script request
  // the layers cannot meet yet waits and applies when they arrive.
  const strip = toolsEl || document.querySelector("#pane-right .tools");
  let pending = null; // {tool, areaFrom} the map script asked for
  let pendingFrom = null; // "select" asked for before any select layer
  let lastToolReason = "";
  let queued = false;
  const fromScript = (reason) => /^turnOn/.test(String(reason || ""));
  function gate() {
    queued = false;
    const s = store.get();
    const av = toolAvailability(s);
    if (strip) {
      strip.querySelectorAll("[data-tool]").forEach((b) => {
        const t = b.dataset.tool;
        const hide = t in av && !av[t];
        if (b.hidden !== hide) b.hidden = hide;
      });
    }
    if (s.tool in av && !av[s.tool]) {
      if (fromScript(lastToolReason)) pending = { tool: s.tool, areaFrom: s.tool === "chart" ? s.areaFrom : null };
      store.set({ tool: null }, "tool-unavailable");
      return;
    }
    if (pending && !s.tool && av[pending.tool]) {
      const p = pending;
      pending = null;
      store.set(p.areaFrom ? { tool: p.tool, areaFrom: p.areaFrom } : { tool: p.tool }, "turnOn-pending");
      return;
    }
    if (s.areaFrom === "select" && !hasSelectLayers(s)) {
      if (s.tool === "chart" && fromScript(lastToolReason)) pendingFrom = "select";
      store.set({ areaFrom: "view" }, "areaFrom-unavailable");
      return;
    }
    if (pendingFrom === "select" && hasSelectLayers(s) && s.tool === "chart" && s.areaFrom === "view") {
      pendingFrom = null;
      store.set({ areaFrom: "select" }, "areaFrom-pending");
    }
  }
  const schedule = () => {
    if (queued) return;
    queued = true;
    queueMicrotask(gate);
  };
  store.on("change:tool", (t, s, reason) => {
    lastToolReason = reason;
    // the user picked a tool: an earlier script request no longer applies
    if (reason === "tool-button") pending = pendingFrom = null;
    schedule();
  });
  store.on("change:areaFrom", (v, s, reason) => {
    if (reason === "areaFrom") pendingFrom = null;
    schedule();
  });
  store.on("change:layers", schedule);
  gate();

  renderUnits();
  renderOptions();
  return { renderOptions, gate };

}
