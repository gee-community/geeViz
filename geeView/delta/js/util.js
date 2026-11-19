// Small pure helpers shared by the Delta modules.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

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
