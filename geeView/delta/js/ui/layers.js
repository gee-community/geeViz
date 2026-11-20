// The layer list: one row per layer (round toggle, name, opacity
// slider, legend toggle, legend inside the row), drag to reorder.
// Rows read the store and write actions back to it; the engine reacts.
//
// Row behavior is ported from the approved mockup
// (docs/superpowers/specs/2026-11-18-delta-mockup.html): fitRows, the
// opacity paint (--v, --a), name click toggles, Sortable with pinned restore.
// Ordering is a port of 2templates.js addLayerSortListener, getLayerIDOrder
// and urlParams.layerOrders.
import { legendMarkup, swatchColors, gradient, cometGradient, restorePinned, orderFromStored, toStoredOrder } from "./legend.js";
import { timelapseBlock } from "./timelapse.js";

const LIST_ID = "layer-list";
// Area-chart-only layers have no row. Select layers are listed (Task 7) but,
// as in the original, turning every layer on or off leaves them alone.
const NO_ROW_KINDS = ["areaChartOnly"];
const NOT_ALL_KINDS = ["select", "areaChartOnly"];

const patchLayer = (store, id, p, reason) =>
  store.update((s) => ({ ...s, layers: s.layers.map((l) => (l.id === id ? { ...l, ...p } : l)) }), reason);

export function setAllVisible(store, visible, reason) {
  store.update(
    (s) => ({ ...s, layers: s.layers.map((l) => (NOT_ALL_KINDS.indexOf(l.kind) > -1 ? l : { ...l, visible })) }),
    reason
  );
}

// A layer's legend opens the first time the layer is on and has a legend to
// show. A layer drawn with addToLegend: false has none (legendFor returns
// null), so it stays closed. Each layer gets this once: after that the legend
// is the user's to open and close. `seen` holds the ids already handled;
// returns the ids to open now.
export function legendsToOpen(layers, seen) {
  const open = [];
  for (const l of layers) {
    if (seen.has(l.id) || !l.visible) continue;
    const sw = swatchColors(l.legend);
    if (!sw || !sw.colors.length) continue;
    seen.add(l.id);
    if (!l.legendOpen) open.push(l.id);
  }
  return open;
}

// How a row shows its tiles loading (layer.progress from engine/tiles.js):
// the name row fills left to right as tiles on screen come in and stays
// full once they have, and tiles that failed after every retry show as a
// count to try again.
export function progressView(l) {
  const p = l && l.visible ? l.progress : null;
  if (!p || !p.total) return { show: false, pct: 0, failed: 0 };
  const settled = p.loaded + p.failed;
  return { show: true, pct: Math.round((settled / p.total) * 1000) / 10, failed: p.failed };
}

// The original keeps urlParams values JSON-encoded in the query string.
function readStoredOrders(urlParams) {
  let v = urlParams && urlParams.layerOrders;
  if (typeof v === "string") {
    try {
      v = JSON.parse(v);
    } catch (e) {
      v = null;
    }
  }
  return v && typeof v === "object" ? v : {};
}

export function mountLayers(store, mountEl, opts = {}) {
  const urlParams = opts.urlParams || window.urlParams || (window.urlParams = {});
  const tpl = document.getElementById("tpl-layer-row");
  const list = document.createElement("div");
  list.id = LIST_ID;
  list.className = "layer-list";
  mountEl.appendChild(list);

  const rows = new Map(); // id -> {el, parts, last}
  const legendSeen = new Set(); // layers whose legend has had its first-on opening
  let dragging = false;

  // ---- ordering ----
  function storeOrder(topFirst, reason) {
    store.set({ order: topFirst }, reason);
    const orders = readStoredOrders(urlParams);
    orders[LIST_ID] = toStoredOrder(topFirst.filter((id) => rows.has(id)));
    urlParams.layerOrders = orders;
    try {
      const url = new URL(location.href);
      url.searchParams.set("layerOrders", JSON.stringify(orders));
      history.replaceState(history.state, "", url);
    } catch (e) {
      /* history can be unavailable */
    }
  }

  // port of 2templates.js initializeLayerSortOrder: a stored order from the url applies once the script has run.
  function restoreOrder() {
    const stored = readStoredOrders(urlParams)[LIST_ID];
    if (!Array.isArray(stored)) return;
    const next = orderFromStored(store.get().order, stored);
    if (next.join() !== store.get().order.join()) store.set({ order: next }, "layerOrders");
  }

  // ---- rows ----
  function paintRange(input, a, label = "Opacity") {
    input.style.setProperty("--v", a * 100 + "%");
    input.style.setProperty("--a", String(a));
    input.title = label + " " + Math.round(a * 100) + "%";
  }

  function paintLegend(row, legend) {
    const { legendEl, swatch, legbtn } = row.parts;
    legendEl.innerHTML = legendMarkup(legend);
    legendEl.querySelectorAll("[data-c]").forEach((el) => {
      const c = el.dataset.c;
      if (c === "ramp") el.style.background = gradient(legend.palette);
      else if (c === "comet") el.style.background = cometGradient(legend.particle);
      else if (c === "outline") {
        el.style.boxShadow = `inset 0 0 0 2px ${legend.color}`;
        el.style.background = "transparent";
      } else el.style.background = legend.items[Number(c)].color;
    });
    legendEl.classList.toggle("ramped", !!legend && legend.type === "ramp");
    const sw = swatchColors(legend);
    swatch.replaceChildren();
    // No legend: the toggle keeps its place (sliders stay aligned) but is not shown or focusable.
    legbtn.classList.toggle("none", !sw);
    if (sw) legbtn.removeAttribute("tabindex");
    else legbtn.setAttribute("tabindex", "-1");
    if (!sw) return;
    if (sw.kind === "ramp") {
      const i = document.createElement("i");
      i.style.background = gradient(sw.colors);
      swatch.appendChild(i);
    } else if (sw.kind === "outline") {
      const i = document.createElement("i");
      i.style.boxShadow = `inset 0 0 0 2px ${sw.colors[0]}`;
      swatch.appendChild(i);
    } else {
      sw.colors.forEach((c) => {
        const i = document.createElement("i");
        i.style.background = c;
        swatch.appendChild(i);
      });
    }
  }

  function makeRow(layer) {
    const el = tpl.content.firstElementChild.cloneNode(true);
    el.dataset.id = layer.id;
    const parts = {
      tgl: el.querySelector(".tgl"),
      name: el.querySelector(".lname"),
      range: el.querySelector("input.op"),
      legbtn: el.querySelector(".legbtn"),
      swatch: el.querySelector(".lsw"),
      legendEl: el.querySelector(".legend"),
      tileErr: el.querySelector(".tile-err"),
    };
    const id = layer.id;
    parts.tileErr.addEventListener("click", () => opts.retryTiles && opts.retryTiles(id));
    if (layer.kind === "select") parts.name.title = "Select layer: with Chart area and Select on, click a feature to select it";
    const toggle = () => {
      const l = store.get().layers.find((x) => x.id === id);
      if (l) patchLayer(store, id, { visible: !l.visible }, "layer-toggle");
    };
    parts.tgl.addEventListener("click", toggle);
    // port of 2templates.js addLayer: clicking the name toggles the layer (not at the end of a drag)
    parts.name.addEventListener("click", () => {
      if (!dragging) toggle();
    });
    parts.legbtn.addEventListener("click", () => {
      const l = store.get().layers.find((x) => x.id === id);
      legendSeen.add(id); // the user has taken over this legend
      if (l) patchLayer(store, id, { legendOpen: !l.legendOpen }, "legend-toggle");
    });
    // A grouped wind layer has two things to fade, as in the original
    // (wind-particles.js addParticleSlider): the particles get a slider of
    // their own, stacked above the layer's, which fades the speed field. Above
    // because the particles are drawn over the field.
    const opLabel = typeof layer.particleOpacity === "number" ? "Wind speed opacity" : "Opacity";
    if (typeof layer.particleOpacity === "number") {
      const part = parts.range.cloneNode();
      part.classList.add("op-part");
      part.setAttribute("aria-label", "Particle opacity");
      parts.range.setAttribute("aria-label", "Wind speed opacity");
      parts.range.parentNode.insertBefore(part, parts.range);
      parts.range.parentNode.classList.add("two");
      parts.part = part;
      part.addEventListener("input", () => {
        const a = Number(part.value) / 100;
        paintRange(part, a, "Particle opacity");
        patchLayer(store, id, { particleOpacity: a }, "particle-opacity");
      });
    }
    parts.range.addEventListener("input", () => {
      const a = Number(parts.range.value) / 100;
      paintRange(parts.range, a, opLabel);
      patchLayer(store, id, { opacity: a }, "layer-opacity");
    });
    // A timelapse's controls sit between the row and its legend, as the mockup.
    let tl = null;
    if (layer.kind === "timelapse") {
      tl = timelapseBlock(id, (lid) => (opts.timelapse ? opts.timelapse(lid) : null));
      el.insertBefore(tl.el, parts.legendEl);
      el.classList.add("is-tl");
    }
    const row = { el, parts, tl, opLabel, last: {} };
    nameRows.set(parts.name, row);
    nameRo.observe(parts.name);
    return row;
  }

  function updateRow(row, l) {
    const { el, parts, last } = row;
    if (last.name !== l.name) {
      parts.name.textContent = l.name;
      parts.tgl.setAttribute("aria-label", "Show or hide " + l.name);
    }
    el.classList.toggle("off", !l.visible);
    parts.tgl.setAttribute("aria-pressed", String(!!l.visible));
    el.classList.toggle("leg-open", !!l.legendOpen);
    el.classList.toggle("pinned", !!l.pinned);
    el.classList.toggle("is-select", l.kind === "select");
    el.classList.toggle("err", !!l.error);
    el.title = l.error ? "Layer failed to load: " + l.error : "";
    // Loading shows in the name row's background, never as an element that
    // takes room (a spinner pushed the slider to a new line and back): the
    // share of tiles in for tile layers, an animated fill for the rest.
    const pv = progressView(l);
    el.classList.toggle("prog", pv.show);
    if (pv.show) el.style.setProperty("--prog", pv.pct + "%");
    el.classList.toggle("busy", !pv.show && !!(l.loading && l.visible));
    parts.tileErr.hidden = !pv.failed;
    if (pv.failed) {
      const t = pv.failed + (pv.failed === 1 ? " tile" : " tiles") + " failed to load after retrying. Click to try again.";
      parts.tileErr.title = t;
      parts.tileErr.setAttribute("aria-label", t);
      parts.tileErr.querySelector(".tile-err-n").textContent = String(pv.failed);
    }
    if (last.opacity !== l.opacity) {
      if (Number(parts.range.value) / 100 !== l.opacity) parts.range.value = String(Math.round(l.opacity * 100));
      paintRange(parts.range, l.opacity, row.opLabel);
    }
    if (parts.part && last.particleOpacity !== l.particleOpacity) {
      if (Number(parts.part.value) / 100 !== l.particleOpacity) parts.part.value = String(Math.round(l.particleOpacity * 100));
      paintRange(parts.part, l.particleOpacity, "Particle opacity");
    }
    if (last.legend !== l.legend) paintLegend(row, l.legend);
    if (row.tl && last.timelapse !== l.timelapse) row.tl.update(l);
    // a new name in the same box: the name observer does not see it
    if (last.name !== undefined && last.name !== l.name && el.isConnected) fitRow(row);
    row.last = { name: l.name, opacity: l.opacity, particleOpacity: l.particleOpacity, legend: l.legend, timelapse: l.timelapse };
  }

  function render() {
    const { layers, order } = store.get();
    const byId = new Map(layers.map((l) => [l.id, l]));
    const shown = order.filter((id) => byId.has(id) && NO_ROW_KINDS.indexOf(byId.get(id).kind) === -1);
    let added = false;
    for (const [id, row] of rows) {
      if (!shown.includes(id)) {
        nameRo.unobserve(row.parts.name);
        row.el.remove();
        rows.delete(id);
      }
    }
    shown.forEach((id, i) => {
      let row = rows.get(id);
      if (!row) {
        row = makeRow(byId.get(id));
        rows.set(id, row);
        added = true;
      }
      updateRow(row, byId.get(id));
      if (list.children[i] !== row.el) list.insertBefore(row.el, list.children[i] || null);
    });
    if (added) fitRows();
  }

  // ---- fit: inline opacity only if the name is not cut off ----
  function fitRow({ el, parts }) {
    el.classList.remove("stack");
    if (parts.name.scrollWidth > parts.name.clientWidth + 1) el.classList.add("stack");
  }
  function fitRows() {
    rows.forEach(fitRow);
  }
  const ro = new ResizeObserver(() => fitRows());
  ro.observe(mountEl);
  // A row's own content can take room from its name (a failed-tiles count
  // appears, the timelapse block mounts) or the name itself can change: refit
  // that row when its name's box changes. ResizeObserver reports once per
  // frame and only for a final size that differs, so a row that settles into
  // stacked does not loop.
  const nameRows = new WeakMap();
  const nameRo = new ResizeObserver((entries) => {
    entries.forEach((e) => {
      const row = nameRows.get(e.target);
      if (row && rows.get(row.el.dataset.id) === row) fitRow(row);
    });
  });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitRows);

  // ---- drag to reorder; pinned layers keep their index ----
  let sortable = null;
  let pinnedAt = [];
  const domOrder = () => Array.from(list.children).map((el) => el.dataset.id);
  if (window.Sortable) {
    sortable = window.Sortable.create(list, {
      handle: ".lname",
      filter: ".pinned",
      preventOnFilter: false,
      draggable: ".layer",
      animation: 160,
      ghostClass: "sortable-ghost",
      chosenClass: "sortable-chosen",
      dragClass: "sortable-drag",
      disabled: !store.get().canReorder,
      onStart() {
        dragging = true;
        pinnedAt = domOrder()
          .map((id, i) => [i, id])
          .filter(([, id]) => rows.get(id).el.classList.contains("pinned"));
      },
      onEnd() {
        const ids = restorePinned(domOrder(), pinnedAt);
        // Rows not in the list (area chart only) keep their place at the end.
        const rest = store.get().order.filter((id) => !rows.has(id));
        storeOrder(ids.concat(rest), "layer-drag");
        render();
        setTimeout(() => (dragging = false), 0);
      },
    });
  }
  store.on("change:canReorder", (v) => sortable && sortable.option("disabled", !v));

  // Open each layer's legend the first time it is on with a legend (the
  // legend arrives with the map service, after the layer is added).
  function openFirstLegends() {
    const ids = legendsToOpen(store.get().layers, legendSeen);
    if (!ids.length) return;
    store.update((s) => ({ ...s, layers: s.layers.map((l) => (ids.indexOf(l.id) > -1 ? { ...l, legendOpen: true } : l)) }), "legend-first-on");
  }
  store.on("change:layers", () => queueMicrotask(openFirstLegends));

  store.on("change:layers", render);
  store.on("change:order", render);
  render();
  openFirstLegends();

  return {
    list,
    fitRows,
    restoreOrder,
    turnOffAllLayers: () => setAllVisible(store, false, "turnOffAllLayers"),
    turnOnAllLayers: () => setAllVisible(store, true, "turnOnAllLayers"),
    sortable: () => sortable,
  };
}
