// Right pane tool options: the units switch and the active tool's options.
// The tool buttons themselves are wired in shell.js (one active, clicking the
// active one turns it off and folds the pane). Ported from the approved
// mockup's opts() and units switch. Chart area adds the "Area from" and
// "Show as" switches and a settings panel (layers to chart, Sankey
// transition periods: port of area-charting.js populateChartLayerSelect and
// 2templates.js setupTransitionPeriodUI). Names are set as text.
import { UPLOAD_ACCEPT } from "../engine/areasources.js";
import { DEFAULT_PERIODS, validatePeriods } from "../engine/areachart.js";

const HINTS = {
  distance: "Click the map to start measuring. Double-click to finish.",
  area: "Click the map to outline an area. Double-click to finish.",
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
  draw: "Click the map to outline an area. Double-click to finish.",
  view: "Charts what the map shows, and again each time the map rests after you move it.",
  upload: "A .zip shapefile, .geojson, .json, .kml or .kmz file. .zip and .kmz files are converted by the ogre.adc4gis.com service; .geojson, .json and .kml stay in your browser.",
  select: "Click features of a select layer on the map, then chart them.",
};

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

export function mountTools(store, { optionsEl, unitsEl, chart, notify } = {}) {
  const say = notify || (() => {});
  // a source action that fails tells the user instead of failing silently
  const attempt = (what, fn) =>
    Promise.resolve()
      .then(fn)
      .catch((e) => say(`${what} failed: ${e && e.message ? e.message : e}`));
  const phoneMq = matchMedia("(max-width: 760px)");
  const unitButtons = unitsEl ? Array.from(unitsEl.querySelectorAll("[data-u]")) : [];
  const sources = () => (typeof chart === "function" ? chart() : chart);
  let settingsOpen = false;
  let draft = null; // transition period rows being edited
  let periodErrors = [];

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

  function periodEditor(s) {
    if (!draft) draft = (s.chartPeriods || DEFAULT_PERIODS).map((r) => r.slice());
    const box = el("div", "cset-sec");
    box.appendChild(el("div", "cset-h", "Transition periods"));
    box.appendChild(el("div", "val-code", "Each row is a period, start year to end year. Sankey charts use the most common class in each period."));
    const table = el("div", "cset-periods");
    draft.forEach((row, i) => {
      const r = el("div", "cset-prow");
      [0, 1].forEach((j) => {
        const inp = el("input", "cset-year mono");
        inp.type = "number";
        inp.step = "1";
        inp.value = Number.isFinite(row[j]) ? String(row[j]) : "";
        inp.setAttribute("aria-label", (j ? "End year of period " : "Start year of period ") + (i + 1));
        inp.addEventListener("input", () => (draft[i][j] = Number.parseInt(inp.value, 10)));
        r.appendChild(inp);
        if (!j) r.appendChild(el("span", "val-code", "to"));
      });
      table.appendChild(r);
    });
    box.appendChild(table);
    const acts = el("div", "cset-acts");
    const add = el("button", "ib");
    add.type = "button";
    add.title = "Add a period";
    add.setAttribute("aria-label", "Add a period");
    add.appendChild(el("i", "ti ti-plus"));
    add.addEventListener("click", () => {
      const lastRow = draft[draft.length - 1] || [2020, 2022];
      draft.push([lastRow[1] + 1, lastRow[1] + 3]);
      renderOptions();
    });
    const rm = el("button", "ib");
    rm.type = "button";
    rm.title = "Remove the last period";
    rm.setAttribute("aria-label", "Remove the last period");
    rm.appendChild(el("i", "ti ti-minus"));
    rm.addEventListener("click", () => {
      if (draft.length) draft.pop();
      renderOptions();
    });
    const apply = el("button", "chip", "Apply");
    apply.type = "button";
    apply.dataset.act = "apply-periods";
    apply.addEventListener("click", () => {
      const v = validatePeriods(draft);
      periodErrors = v.errors;
      if (v.periods) store.set({ chartPeriods: v.periods, chartPeriodsUser: true }, "chart-periods");
      renderOptions();
    });
    acts.append(add, rm, apply);
    box.appendChild(acts);
    periodErrors.forEach((e) => box.appendChild(el("div", "cset-err", e)));
    return box;
  }

  function sourceRow(s) {
    const src = s.areaFrom;
    const box = el("div", "csrc");
    box.appendChild(hintEl(SOURCE_HINTS[src] || "", "topt-hint sub"));
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
    nodes.push(seg("src", "Area from", SOURCES, s.areaFrom, (v) => store.set({ areaFrom: v }, "areaFrom")));
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
    optionsEl.replaceChildren(...(text ? [hintEl(text)] : []));
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
  renderUnits();
  renderOptions();
  return { renderOptions };
}
