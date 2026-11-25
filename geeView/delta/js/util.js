// Small pure helpers shared by the Delta modules.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

// A layer drawn frame by frame: an Earth Engine timelapse, or a
// time-enabled ArcGIS service.
export const isTimelapseKind = (kind) => kind === "timelapse" || kind === "esri.timelapse";
export const isTimelapse = (layer) => !!layer && isTimelapseKind(layer.kind);

export function escapeText(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

const M_PER_MI = 1609.344;
const M_PER_FT = 0.3048;
const M2_PER_ACRE = 4046.8564224;
const M2_PER_SQMI = M_PER_MI * M_PER_MI;

function num(n, digits) {
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatLength(meters, units = "metric") {
  if (units === "imperial") {
    const mi = meters / M_PER_MI;
    if (mi < 0.1) return num(meters / M_PER_FT, 0) + " ft";
    return num(mi, 2) + " mi";
  }
  if (meters < 1000) return num(meters, 0) + " m";
  return num(meters / 1000, 2) + " km";
}

export function formatArea(m2, units = "metric", showAs = "area", totalM2 = null) {
  if (showAs === "pct") {
    if (!totalM2) return "n/a";
    return num((m2 / totalM2) * 100, 1) + "%";
  }
  if (units === "imperial") {
    const acres = m2 / M2_PER_ACRE;
    if (acres >= 640 * 10) return num(m2 / M2_PER_SQMI, 1) + " sq mi";
    if (acres < 1) return num(m2 * 10.7639104167, 0) + " sq ft";
    return num(acres, acres >= 100 ? 0 : 1) + " acres";
  }
  const ha = m2 / 10000;
  if (ha >= 100000) return num(m2 / 1e6, 0) + " km²";
  if (ha < 1) return num(m2, 0) + " m²";
  return num(ha, ha >= 100 ? 0 : 1) + " ha";
}

let tokenCounter = 0;

// A newer token makes every older one not current. Used to drop stale async results.
export function requestToken() {
  const id = ++tokenCounter;
  return { id, isCurrent: () => id === tokenCounter };
}

// An independent stream of request tokens: a newer token from the same source
// makes the older ones not current, without touching other sources.
export function tokenSource() {
  let counter = 0;
  return () => {
    const id = ++counter;
    return { id, isCurrent: () => id === counter };
  };
}

const isNumber = (n) => typeof n === "number" && !Number.isNaN(n) && Number.isFinite(n);

// port of 1variables.js smartToFixed: keep at least `precision` decimals, or
// `proportion` of the decimals the number has, whichever is more.
// Non-numbers (strings included, as the original's isNumber) come back as given;
// so do numbers in exponent notation, which the original could not split.
export function smartToFixed(v, proportion = 0.25, precision = 3) {
  if (!isNumber(v) || Number.isInteger(v) || /e/i.test(String(v))) return v;
  const decimals = (String(v).split(".")[1] || "").length;
  const toFixedL = Math.max(precision, Math.ceil(decimals * proportion));
  return Number.parseFloat(v.toFixed(Math.min(100, toFixedL)));
}
