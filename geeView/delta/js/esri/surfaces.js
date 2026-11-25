// ArcGIS renderers that draw a whole tile rather than a symbol per feature:
// heatmap (a kernel density surface, redrawn as the view moves), dot density
// (dots placed in each polygon by a field) and pie chart (a pie per feature),
// with their legends, as the ArcGIS JS API draws them.
import { esriColor, glyphFor, ptToPx, drawSymbol } from "./symbols.js";
import { scaleAt } from "./features.js";

const num = (v) => (v === null || v === undefined || v === "" ? null : Number.isFinite(Number(v)) ? Number(v) : null);
const fmtInt = (v) => Math.round(v).toLocaleString("en-US");

// ---- heatmap ----
// The density on a size x size grid from points [x, y, weight] in its pixels,
// with ArcGIS's quartic kernel of the blur radius.
export function heatGrid(points, size, radius) {
  const g = new Float32Array(size * size);
  const r = Math.max(1, radius);
  const r2 = r * r;
  points.forEach(([px, py, w]) => {
    const wt = w === undefined || w === null ? 1 : w;
    if (!wt) return;
    const x0 = Math.max(0, Math.floor(px - r));
    const x1 = Math.min(size - 1, Math.ceil(px + r));
    const y0 = Math.max(0, Math.floor(py - r));
    const y1 = Math.min(size - 1, Math.ceil(py + r));
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        const d2 = (x - px) * (x - px) + (y - py) * (y - py);
        if (d2 >= r2) continue;
        const k = 1 - d2 / r2;
        g[y * size + x] += wt * (15 / 16) * k * k;
      }
    }
  });
  return g;
}

// The color stops' color at a ratio (0..1), [r, g, b, a].
export function heatColor(ratio, stops) {
  const s = (stops || []).slice().sort((a, b) => a.ratio - b.ratio);
  if (!s.length) return [0, 0, 0, 0];
  if (ratio <= s[0].ratio) return s[0].color.slice(0, 4);
  for (let i = 1; i < s.length; i++) {
    if (ratio <= s[i].ratio) {
      const a = s[i - 1];
      const b = s[i];
      const t = b.ratio === a.ratio ? 1 : (ratio - a.ratio) / (b.ratio - a.ratio);
      return a.color.map((c, k) => Math.round(c + (b.color[k] - c) * t)).slice(0, 4);
    }
  }
  return s[s.length - 1].color.slice(0, 4);
}

function heatmap(r) {
  const blur = Number(r.blurRadius) || 10;
  const minI = Number(r.minPixelIntensity) || 0;
  const maxI = Number(r.maxPixelIntensity) || 100;
  const lo = (r.legendOptions && r.legendOptions.minLabel) || "Low";
  const hi = (r.legendOptions && r.legendOptions.maxLabel) || "High";
  return {
    type: "heatmap",
    fields: r.field ? [r.field] : [],
    // a tile cut short draws a weaker surface than its neighbors: points are small, fetch more
    maxFeatures: 20000,
    padPx: blur,
    styleFor: () => null,
    drawTile(ctx, parts, t) {
      if (typeof document === "undefined") return;
      const size = 256;
      const pts = [];
      parts.forEach((p) => {
        if (p.kind !== "point") return;
        const w = r.field ? num(p.props[r.field]) : 1;
        if (w === null) return;
        p.coords.forEach((c) => {
          const [x, y] = t.px(c);
          pts.push([x, y, w]);
        });
      });
      if (!pts.length) return;
      const grid = heatGrid(pts, size, blur);
      const off = document.createElement("canvas");
      off.width = size;
      off.height = size;
      const octx = off.getContext("2d");
      const img = octx.createImageData(size, size);
      for (let i = 0; i < grid.length; i++) {
        if (!grid[i]) continue;
        const c = heatColor((grid[i] - minI) / (maxI - minI), r.colorStops);
        img.data[i * 4] = c[0];
        img.data[i * 4 + 1] = c[1];
        img.data[i * 4 + 2] = c[2];
        img.data[i * 4 + 3] = c[3];
      }
      octx.putImageData(img, 0, 0);
      ctx.globalAlpha = t.opacity;
      ctx.drawImage(off, 0, 0, size, size);
      ctx.globalAlpha = 1;
    },
    legend: (title) => ({
      type: "symbols",
      title,
      items: [],
      ramps: [{ label: r.field || "", palette: (r.colorStops || []).filter((s) => s.color[3] > 0).map((s) => esriColor(s.color).color), labels: [lo, hi] }],
    }),
  };
}

// ---- dot density ----
// What one dot stands for at a zoom: dotValue at the reference scale.
export function dotValueAt(r, zoom) {
  const dv = Number(r.dotValue) || 1;
  const ref = Number(r.referenceScale) || 0;
  return ref > 0 ? dv * Math.pow(scaleAt(zoom) / ref, 2) : dv;
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function insideRings(x, y, rings) {
  let hit = false;
  rings.forEach((ring) => {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit;
    }
  });
  return hit;
}

// n dots inside a polygon's rings, placed the same way for the same seed.
export function dotsIn(rings, n, seed) {
  const count = Math.max(0, Math.floor(n));
  if (!count || !rings.length) return [];
  let w = Infinity, s = Infinity, e = -Infinity, nn = -Infinity;
  rings[0].forEach(([x, y]) => {
    w = Math.min(w, x);
    e = Math.max(e, x);
    s = Math.min(s, y);
    nn = Math.max(nn, y);
  });
  const rand = mulberry32(seed);
  const out = [];
  for (let tries = 0; out.length < count && tries < count * 200; tries++) {
    const x = w + rand() * (e - w);
    const y = s + rand() * (nn - s);
    if (insideRings(x, y, rings)) out.push([x, y]);
  }
  return out;
}

// A whole number of dots for an exact count: the fraction is a seeded draw,
// so small polygons (a fraction of a dot each) still add up to their total.
export function dotCount(exact, seed) {
  const n = Math.max(0, Number(exact) || 0);
  const whole = Math.floor(n);
  return whole + (mulberry32(seed)() < n - whole ? 1 : 0);
}

const ringArea = (ring) => Math.abs(ring.reduce((a, [x, y], i) => {
  const [x2, y2] = ring[(i + 1) % ring.length];
  return a + (x * y2 - x2 * y);
}, 0) / 2);
const hashOf = (s) => {
  let h = 2166136261;
  for (const ch of String(s)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return h >>> 0;
};

function dotDensity(r) {
  const attrs = r.attributes || [];
  const size = Number(r.dotSize) || 1;
  const cache = new Map();
  const background = { type: "esriSFS", style: "esriSFSSolid", color: r.backgroundColor || [0, 0, 0, 0], outline: r.outline };
  return {
    type: "dotDensity",
    fields: attrs.map((a) => a.field).filter(Boolean),
    styleFor: () => null,
    drawTile(ctx, parts, t) {
      const dv = dotValueAt(r, t.zoom);
      // a feature's dots are shared among its polygons by area
      const total = new Map();
      parts.forEach((p) => p.kind === "polygon" && total.set(p.fid, (total.get(p.fid) || 0) + ringArea(p.coords[0])));
      parts.forEach((p) => {
        if (p.kind !== "polygon") return;
        drawSymbol(ctx, background, p, t.px, {}, t.opacity);
        const share = total.get(p.fid) ? ringArea(p.coords[0]) / total.get(p.fid) : 1;
        attrs.forEach((a, i) => {
          const v = num(p.props[a.field]);
          if (!v || v <= 0) return;
          const base = `${p.fid}|${i}|${p.bbox.join(",")}`;
          const n = dotCount((v * share) / dv, hashOf(base + "|n"));
          const key = `${base}|${n}`;
          if (!cache.has(key)) {
            cache.set(key, dotsIn(p.coords, n, hashOf(key)));
            if (cache.size > 20000) cache.delete(cache.keys().next().value);
          }
          const c = esriColor(a.color) || { color: "#000", alpha: 1 };
          ctx.globalAlpha = Math.max(0, Math.min(1, c.alpha * t.opacity));
          ctx.fillStyle = c.color;
          cache.get(key).forEach((d) => {
            const [x, y] = t.px(d);
            ctx.fillRect(x - size / 2, y - size / 2, size, size);
          });
        });
      });
      ctx.globalAlpha = 1;
    },
    legend(title, zoom = 10) {
      return {
        type: "symbols",
        title,
        items: attrs.map((a) => ({ label: String(a.label || a.field || ""), glyph: { ...glyphFor({ type: "esriSMS", style: "esriSMSSquare", color: a.color }, "point"), stroke: null, size: 6 } })),
        ramps: [],
        caption: `1 dot = ${fmtInt(dotValueAt(r, zoom))}`,
      };
    },
  };
}

// ---- pie chart ----
// Slices in degrees from 0 (clockwise from the top), one per value; values
// below `threshold` of the total join one slice in othersColor, when given.
export function pieSlices(values, colors, opts = {}) {
  const vals = values.map((v) => Math.max(0, Number(v) || 0));
  const total = vals.reduce((a, b) => a + b, 0);
  if (!total) return [];
  const th = Number(opts.threshold) || 0;
  const out = [];
  let others = 0;
  let at = 0;
  vals.forEach((v, i) => {
    if (!v) return;
    if (opts.othersColor && v / total < th) {
      others += v;
      return;
    }
    const sweep = (v / total) * 360;
    out.push({ start: at, end: at + sweep, color: colors[i] });
    at += sweep;
  });
  if (others) out.push({ start: at, end: at + (others / total) * 360, color: opts.othersColor });
  return out;
}

// A point inside a polygon to put its pie on: the outer ring's centroid, or
// when that falls outside (a C shape), the middle of the widest span inside
// along the centroid's row.
export function interiorPoint(rings) {
  const ring = rings[0];
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[i + 1];
    const f = x1 * y2 - x2 * y1;
    a += f;
    cx += (x1 + x2) * f;
    cy += (y1 + y2) * f;
  }
  if (!a) return ring[0].slice(0, 2);
  cx /= 3 * a;
  cy /= 3 * a;
  if (insideRings(cx, cy, rings)) return [cx, cy];
  const xs = [];
  rings.forEach((r) => {
    for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
      const [xi, yi] = r[i];
      const [xj, yj] = r[j];
      if (yi > cy !== yj > cy) xs.push(xi + ((cy - yi) * (xj - xi)) / (yj - yi));
    }
  });
  xs.sort((p, q) => p - q);
  let best = null;
  for (let i = 0; i + 1 < xs.length; i += 2) if (!best || xs[i + 1] - xs[i] > best[1] - best[0]) best = [xs[i], xs[i + 1]];
  return best ? [(best[0] + best[1]) / 2, cy] : [cx, cy];
}

function pieChart(r) {
  const attrs = r.attributes || [];
  const colors = attrs.map((a) => (esriColor(a.color) || { color: "#888" }).color);
  const others = r.othersCategory || null;
  const othersColor = others && others.color ? esriColor(others.color).color : null;
  const radius = ptToPx(r.size || 12) / 2;
  const hole = Math.max(0, Math.min(0.95, Number(r.holePercentage) || 0));
  return {
    type: "pieChart",
    fields: attrs.map((a) => a.field).filter(Boolean),
    styleFor: () => null,
    drawTile(ctx, parts, t) {
      // one pie per feature: at its point, or inside its largest polygon
      const byFid = new Map();
      parts.forEach((p) => {
        if (p.kind === "line") return;
        const prev = byFid.get(p.fid);
        if (!prev || (p.kind === "polygon" && ringArea(p.coords[0]) > ringArea(prev.coords[0]))) byFid.set(p.fid, p);
      });
      byFid.forEach((p) => {
        const where = p.kind === "point" ? p.coords : [interiorPoint(p.coords)];
        const slices = pieSlices(attrs.map((a) => p.props[a.field]), colors, { threshold: others && others.threshold, othersColor });
        where.forEach((c) => {
          const [x, y] = t.px(c);
          ctx.globalAlpha = t.opacity;
          slices.forEach((s) => {
            const a0 = ((s.start - 90) * Math.PI) / 180;
            const a1 = ((s.end - 90) * Math.PI) / 180;
            ctx.beginPath();
            ctx.arc(x, y, radius, a0, a1);
            if (hole) ctx.arc(x, y, radius * hole, a1, a0, true);
            else ctx.lineTo(x, y);
            ctx.closePath();
            ctx.fillStyle = s.color;
            ctx.fill();
          });
          if (r.outline && slices.length) {
            ctx.beginPath();
            ctx.arc(x, y, radius, 0, 2 * Math.PI);
            const oc = esriColor(r.outline.color);
            if (oc) {
              ctx.globalAlpha = oc.alpha * t.opacity;
              ctx.strokeStyle = oc.color;
              ctx.lineWidth = ptToPx(r.outline.width || 1);
              ctx.stroke();
            }
          }
        });
      });
      ctx.globalAlpha = 1;
    },
    legend: (title) => ({
      type: "symbols",
      title,
      items: attrs
        .map((a, i) => ({ label: String(a.label || a.field || ""), glyph: { geom: "polygon", fill: colors[i], fillOpacity: 1, stroke: null, strokeOpacity: 0, width: 0, dash: null } }))
        .concat(othersColor ? [{ label: String(others.label || "Others"), glyph: { geom: "polygon", fill: othersColor, fillOpacity: 1, stroke: null, strokeOpacity: 0, width: 0, dash: null } }] : []),
      ramps: [],
    }),
  };
}

// The tile-drawing renderers by type; renderers.js asks here first.
export const SURFACES = { heatmap, dotDensity, pieChart };
