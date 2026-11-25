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
  // a service's own swatches (ArcGIS /legend): images the server drew
  if (legend.type === "images") return imageItems(legend.items);
  // a renderer's legend (ArcGIS drawingInfo): a glyph per class, ramps for
  // visual variables, and a note when it is drawn otherwise than it says
  if (legend.type === "symbols") {
    const items = (legend.items || []).map((it, i) => `<span class="sw sym" data-g="${i}"></span><span class="lbl">${escapeText(it.label)}</span>`).join("");
    const ramps = (legend.ramps || [])
      .map((r, k) => {
        const labels = (r.labels || []).map((l) => `<span>${escapeText(l)}</span>`).join("");
        return `<span class="lgsec">${escapeText(r.label || "")}</span><span class="ramp lgr" data-r="${k}"></span><span class="ramp-l mono lgr">${labels}</span>`;
      })
      .join("");
    const note = legend.note ? `<span class="lgnote">${escapeText(legend.note)}</span>` : "";
    return items + ramps + note;
  }
  if (legend.type === "sections") {
    return (legend.sections || [])
      .map((s) => `<span class="lgsec">${escapeText(s.title || "")}</span>${imageItems(s.items)}`)
      .join("");
  }
  return "";
}

// Only data: images are written (a legend comes from a service's JSON).
const isDataImage = (src) => /^data:image\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]*$/i.test(String(src || ""));
const imageItems = (items) =>
  (items || [])
    .filter((it) => isDataImage(it.src))
    .map((it) => `<img class="lgimg" src="${escapeText(it.src)}" alt=""><span class="lbl">${escapeText(it.label)}</span>`)
    .join("");
const legendImages = (legend) =>
  (legend.type === "images" ? legend.items || [] : (legend.sections || []).flatMap((s) => s.items || [])).filter((it) => isDataImage(it.src));

// Colors for the small legend-toggle swatch: up to four class colors, the
// ramp, or the outline color.
export function swatchColors(legend) {
  if (!legend) return null;
  if (legend.type === "classes") return { kind: "classes", colors: legend.items.slice(0, 4).map((it) => it.color) };
  if (legend.type === "ramp") return { kind: "ramp", colors: legend.palette.slice() };
  if (legend.type === "outline") return { kind: "outline", colors: [legend.color] };
  if (legend.type === "symbols") {
    const colors = (legend.items || []).slice(0, 4).map((it) => (it.glyph && (it.glyph.fill || it.glyph.stroke)) || "#888888");
    return colors.length ? { kind: "classes", colors } : null;
  }
  if (legend.type === "images" || legend.type === "sections") {
    const srcs = legendImages(legend).slice(0, 4).map((it) => it.src);
    return srcs.length ? { kind: "images", srcs, colors: srcs } : null;
  }
  return null;
}

export const gradient = (colors) => `linear-gradient(90deg, ${colors.join(", ")})`;

// ---- vector symbols ----
// A vector layer's legend is its symbol, one glyph per geometry type it holds,
// drawn as the map draws it, so there is nothing more to open below the row.
// A renderer with one symbol and nothing else to show (a simple renderer)
// is a symbol too.
export const isSymbolLegend = (legend) =>
  !!legend &&
  (legend.type === "outline" ||
    (legend.type === "symbols" && (legend.items || []).length === 1 && !(legend.ramps || []).length && !legend.note));

const GEOM_OF = {
  Point: "point", MultiPoint: "point", point: "point",
  LineString: "line", MultiLineString: "line", LinearRing: "line", line: "line",
  Polygon: "polygon", MultiPolygon: "polygon", polygon: "polygon",
};
export const GEOMS = ["point", "line", "polygon"];

// GeoJSON or Earth Engine geometry type names (or vectortiles kinds) to the
// kinds present, in point, line, polygon order.
export function geomKinds(types) {
  const seen = new Set((types || []).map((t) => GEOM_OF[t]).filter(Boolean));
  return GEOMS.filter((k) => seen.has(k));
}

// "#rgb", "#rgba", "#rrggbb", "#rrggbbaa" (with or without #) to the color
// and its alpha; a color name is opaque.
export function splitAlpha(c) {
  const s = String(c || "#000");
  const h = s.replace(/^#/, "");
  if (!/^[0-9a-fA-F]+$/.test(h) || [3, 4, 6, 8].indexOf(h.length) === -1) return { color: s, alpha: 1 };
  const full = h.length <= 4 ? h.split("").map((x) => x + x).join("") : h;
  return { color: "#" + full.slice(0, 6).toLowerCase(), alpha: full.length === 8 ? parseInt(full.slice(6), 16) / 255 : 1 };
}

// The glyphs for an outline legend: [{geom, fill, fillOpacity, stroke,
// strokeOpacity, width}], fill or stroke null when the map draws none.
// legend.paint says who draws the layer: "canvas" (GeoJSON, engine/
// vectortiles.js), "paint" (Earth Engine Image.paint: outlines only, points
// a solid dot) or "style" (FeatureCollection.style: colors carry their alpha).
export function vectorGlyphs(legend) {
  if (legend.type === "symbols") return (legend.items || []).slice(0, 1).map((it) => it.glyph);
  const kinds = legend.geoms && legend.geoms.length ? legend.geoms : ["polygon"];
  const st = splitAlpha(legend.color);
  const fl = splitAlpha(legend.fill || legend.color);
  const strokeOpacity = st.alpha * (legend.strokeOpacity === undefined || legend.strokeOpacity === null ? 1 : Number(legend.strokeOpacity));
  const weight = Number(legend.weight === undefined || legend.weight === null ? 2 : legend.weight);
  const width = weight > 0 ? Math.min(Math.max(weight, 1), 2.5) : 0;
  let fillOpacity;
  if (legend.paint === "paint") fillOpacity = 0;
  else if (legend.paint === "style") fillOpacity = fl.alpha;
  else fillOpacity = Number(legend.fillOpacity || 0) * fl.alpha;
  const stroke = width > 0 && strokeOpacity > 0 ? st.color : null;
  // Earth Engine draws styleParams lineType dashed or dotted; the swatch does too
  const dash = legend.paint === "style" && (legend.lineType === "dashed" || legend.lineType === "dotted") ? legend.lineType : null;
  return kinds.map((geom) => glyph(geom)).map((g) => (g.geom !== "point" && g.stroke ? { ...g, dash } : { ...g, dash: null }));
  function glyph(geom) {
    if (geom === "point") {
      if (legend.paint === "canvas") return { geom, fill: st.color, fillOpacity: strokeOpacity, stroke: "#ffffff", strokeOpacity, width: 1 };
      if (legend.paint === "paint") return { geom, fill: st.color, fillOpacity: strokeOpacity, stroke: null, strokeOpacity, width: 0 };
      return { geom, fill: fillOpacity > 0 ? fl.color : null, fillOpacity, stroke, strokeOpacity, width };
    }
    if (geom === "line") return { geom, fill: null, fillOpacity: 0, stroke: st.color, strokeOpacity, width: Math.max(width, 1.5) };
    return { geom, fill: fillOpacity > 0 ? fl.color : null, fillOpacity, stroke, strokeOpacity, width };
  }
}

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
