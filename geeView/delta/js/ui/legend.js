// Pure helpers for the layer list: legend markup, the legend-toggle swatch,
// the pinned-layer restore after a drag, and stored layer orders. No DOM
// access, so they run under node --test.
import { escapeText } from "../util.js";

// Legend markup. Labels are escaped; colors are never written into the
// markup (no inline styles): elements that need one carry data-c="<index>"
// and paintLegend() sets the color through the CSSOM.
export function legendMarkup(legend) {
  if (!legend) return "";
  if (legend.type === "classes") {
    return legend.items.map((it, i) => `<span class="sw" data-c="${i}"></span><span class="lbl">${escapeText(it.label)}</span>`).join("");
  }
  if (legend.type === "ramp" && legend.wind) {
    const labels = (legend.labels || []).map((l) => `<span>${escapeText(l)}</span>`).join("");
    return `<span class="ramp wind-ramp" data-c="ramp"><i class="wind-comet" data-c="comet"></i></span><span class="ramp-l mono">${labels}</span>`;
  }
  if (legend.type === "ramp") {
    const labels = (legend.labels || []).map((l) => `<span>${escapeText(l)}</span>`).join("");
    return `<span class="ramp" data-c="ramp"></span><span class="ramp-l mono">${labels}</span>`;
  }
  if (legend.type === "outline") {
    return `<span class="sw outline" data-c="outline"></span><span class="lbl">${escapeText(legend.label || "")}</span>`;
  }
  return "";
}

// Colors for the small legend-toggle swatch: up to four class colors, the
// ramp, or the outline color.
export function swatchColors(legend) {
  if (!legend) return null;
  if (legend.type === "classes") return { kind: "classes", colors: legend.items.slice(0, 4).map((it) => it.color) };
  if (legend.type === "ramp") return { kind: "ramp", colors: legend.palette.slice() };
  if (legend.type === "outline") return { kind: "outline", colors: [legend.color] };
  return null;
}

export const gradient = (colors) => `linear-gradient(90deg, ${colors.join(", ")})`;

// "#rgb" / "#rrggbb" to [r, g, b]; white for anything else (a legend is not
// worth failing over). port of wind-particles.js hexToRgb.
export function hexRgb(h) {
  h = String(h || "#fff").replace("#", "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  const n = parseInt(h, 16);
  return h.length !== 6 || isNaN(n) ? [255, 255, 255] : [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// The wind legend's particle: a trail fading in to its head, in the particle
// color (port of wind-particles.js restyleLegend's comet).
export function cometGradient(color) {
  const c = hexRgb(color).join(",");
  return `linear-gradient(90deg, rgba(${c},0), rgba(${c},.95))`;
}

// After a drop, put each pinned layer back at the index it had when the drag
// started, so only movable layers trade places (the mockup's onEnd, done by
// removing the pinned layers first so the indices are exact either way).
// ids: list order after the drop. pinnedAt: [[index, id], ...] from the start.
export function restorePinned(ids, pinnedAt) {
  const pinned = new Set(pinnedAt.map(([, id]) => id));
  const out = ids.filter((id) => !pinned.has(id));
  pinnedAt
    .slice()
    .sort((a, b) => a[0] - b[0])
    .forEach(([i, id]) => out.splice(Math.min(i, out.length), 0, id));
  return out;
}

// port of 2templates.js updateMapLayerOrder: the layers named in a stored
// order (bottom-up, as urlParams.layerOrders keeps it) trade the list slots
// they occupy now; other layers do not move. currentTopFirst: list order.
export function orderFromStored(currentTopFirst, storedBottomUp) {
  if (!Array.isArray(storedBottomUp)) return currentTopFirst.slice();
  const known = storedBottomUp.filter((id, i) => currentTopFirst.indexOf(id) > -1 && storedBottomUp.indexOf(id) === i);
  const wanted = known.slice().reverse();
  const slots = currentTopFirst.map((id, i) => (known.indexOf(id) > -1 ? i : -1)).filter((i) => i > -1);
  const out = currentTopFirst.slice();
  slots.forEach((slot, k) => (out[slot] = wanted[k]));
  return out;
}

// The original's urlParams.layerOrders value for the main list: ids bottom-up.
export const toStoredOrder = (topFirst) => topFirst.slice().reverse();
