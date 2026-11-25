// ArcGIS symbols (drawingInfo's esriSMS, esriSLS, esriSFS, esriPMS, esriPFS)
// drawn on Delta's canvas tiles, and as legend glyphs, as the ArcGIS JS API
// draws them. Sizes and widths are in points (4/3 px each).

export const ptToPx = (pt) => (Number(pt) || 0) * (4 / 3);

const hex2 = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0");
// [r, g, b, a] (a from 0 to 255) to {color: "#rrggbb", alpha 0..1}
export function esriColor(c) {
  if (!Array.isArray(c) || c.length < 3) return null;
  return { color: "#" + hex2(c[0]) + hex2(c[1]) + hex2(c[2]), alpha: c.length > 3 ? Number(c[3]) / 255 : 1 };
}
export const toEsriColor = (hex, alpha = 1) => {
  const h = String(hex || "000").replace(/^#/, "");
  const f = h.length === 3 ? h.split("").map((x) => x + x).join("") : h.slice(0, 6);
  return [parseInt(f.slice(0, 2), 16), parseInt(f.slice(2, 4), 16), parseInt(f.slice(4, 6), 16), Math.round(alpha * 255)];
};

const SHAPES = { esriSMSCircle: "circle", esriSMSSquare: "square", esriSMSDiamond: "diamond", esriSMSCross: "cross", esriSMSX: "x", esriSMSTriangle: "triangle" };
const DASHED = ["esriSLSDash", "esriSLSLongDash", "esriSLSShortDash", "esriSLSDashDot", "esriSLSDashDotDot", "esriSLSLongDashDot", "esriSLSShortDashDot", "esriSLSShortDashDotDot"];
const DOTTED = ["esriSLSDot", "esriSLSShortDot"];
const dashOf = (style) => (DASHED.indexOf(style) > -1 ? "dashed" : DOTTED.indexOf(style) > -1 ? "dotted" : null);
const GEOM_OF_TYPE = { esriSMS: "point", esriPMS: "point", esriSLS: "line", esriSFS: "polygon", esriPFS: "polygon" };
const pictureSrc = (s) => (s && s.imageData ? `data:${s.contentType || "image/png"};base64,${s.imageData}` : null);

// A line symbol's stroke: {stroke, strokeOpacity, width, dash}, or none.
function strokeOf(line) {
  if (!line || line.style === "esriSLSNull") return { stroke: null, strokeOpacity: 0, width: 0, dash: null };
  const c = esriColor(line.color);
  const w = ptToPx(line.width === undefined ? 1 : line.width);
  if (!c || c.alpha === 0 || w <= 0) return { stroke: null, strokeOpacity: 0, width: 0, dash: null };
  return { stroke: c.color, strokeOpacity: c.alpha, width: w, dash: dashOf(line.style) };
}

// The legend glyph for a symbol (ui/layers.js glyphSvg): the map's colors.
export function glyphFor(symbol, geom) {
  const s = symbol || {};
  const g = geom || GEOM_OF_TYPE[s.type] || "polygon";
  const clamp = (w) => (w > 0 ? Math.min(Math.max(w, 1), 2.5) : 0);
  if (s.type === "esriPMS" || s.type === "esriPFS") return { geom: g, image: pictureSrc(s), fill: null, fillOpacity: 0, stroke: null, strokeOpacity: 0, width: 0, dash: null };
  if (s.type === "esriSLS") {
    const st = strokeOf(s);
    return { geom: "line", fill: null, fillOpacity: 0, ...st, width: Math.max(clamp(st.width), st.stroke ? 1.5 : 0) };
  }
  const fc = s.style === "esriSFSNull" ? null : esriColor(s.color);
  const st = strokeOf(s.outline);
  const fill = fc && fc.alpha > 0 ? fc.color : null;
  const out = { geom: g, fill, fillOpacity: fc ? fc.alpha : 0, stroke: st.stroke, strokeOpacity: st.strokeOpacity, width: clamp(st.width), dash: st.dash };
  if (s.type === "esriSMS") out.shape = SHAPES[s.style] || "circle";
  if (s.type === "esriSFS" && s.style && s.style !== "esriSFSSolid" && s.style !== "esriSFSNull") out.hatch = s.style;
  return out;
}

// ---- pictures ----
const IMAGES = new Map(); // src -> HTMLImageElement (complete or loading)
const imageListeners = new Set();
// fn() when a picture symbol's image has loaded (to redraw); returns an unsubscribe.
export function onSymbolImage(fn) {
  imageListeners.add(fn);
  return () => imageListeners.delete(fn);
}
function imageFor(src) {
  if (!src || typeof Image === "undefined") return null;
  let img = IMAGES.get(src);
  if (!img) {
    img = new Image();
    img.onload = () => imageListeners.forEach((fn) => fn());
    img.src = src;
    IMAGES.set(src, img);
  }
  return img.complete && img.naturalWidth ? img : null;
}

// ---- hatches ----
const HATCH = {
  esriSFSHorizontal: (c, n) => c.fillRect(0, n / 2, n, 1),
  esriSFSVertical: (c, n) => c.fillRect(n / 2, 0, 1, n),
  esriSFSCross: (c, n) => (c.fillRect(0, n / 2, n, 1), c.fillRect(n / 2, 0, 1, n)),
  esriSFSForwardDiagonal: (c, n) => diag(c, n, 1),
  esriSFSBackwardDiagonal: (c, n) => diag(c, n, -1),
  esriSFSDiagonalCross: (c, n) => (diag(c, n, 1), diag(c, n, -1)),
};
function diag(c, n, dir) {
  c.beginPath();
  if (dir > 0) {
    c.moveTo(0, n);
    c.lineTo(n, 0);
  } else {
    c.moveTo(0, 0);
    c.lineTo(n, n);
  }
  c.lineWidth = 1;
  c.strokeStyle = c.fillStyle;
  c.stroke();
}
const PATTERNS = new Map();
function hatchPattern(ctx, style, color) {
  const key = style + color;
  if (PATTERNS.has(key)) return PATTERNS.get(key);
  if (typeof document === "undefined" || !HATCH[style]) return null;
  const n = 8;
  const c = document.createElement("canvas");
  c.width = n;
  c.height = n;
  const x = c.getContext("2d");
  x.fillStyle = color;
  HATCH[style](x, n);
  const p = ctx.createPattern(c, "repeat");
  PATTERNS.set(key, p);
  return p;
}

// ---- drawing ----
function tracePath(ctx, part, px) {
  ctx.beginPath();
  part.coords.forEach((ring) => {
    ring.forEach((c, i) => {
      const [x, y] = px(c);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    if (part.kind === "polygon") ctx.closePath();
  });
}

const DASH_PX = { dashed: [6, 4], dotted: [1.5, 3] };
function strokeWith(ctx, line, alpha, colorOver) {
  const st = strokeOf(line);
  if (!st.stroke && !colorOver) return;
  const c = colorOver || { color: st.stroke, alpha: st.strokeOpacity };
  ctx.globalAlpha = Math.max(0, Math.min(1, c.alpha * alpha));
  ctx.strokeStyle = c.color;
  ctx.lineWidth = st.width || 1;
  if (ctx.setLineDash) ctx.setLineDash(st.dash ? DASH_PX[st.dash] : []);
  ctx.stroke();
  if (ctx.setLineDash) ctx.setLineDash([]);
}

function markerPath(ctx, shape, x, y, r) {
  ctx.beginPath();
  if (shape === "square") ctx.rect(x - r, y - r, 2 * r, 2 * r);
  else if (shape === "diamond") {
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r, y);
    ctx.lineTo(x, y + r);
    ctx.lineTo(x - r, y);
    ctx.closePath();
  } else if (shape === "triangle") {
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r, y + r);
    ctx.lineTo(x - r, y + r);
    ctx.closePath();
  } else if (shape === "cross") {
    ctx.moveTo(x - r, y);
    ctx.lineTo(x + r, y);
    ctx.moveTo(x, y - r);
    ctx.lineTo(x, y + r);
  } else if (shape === "x") {
    ctx.moveTo(x - r, y - r);
    ctx.lineTo(x + r, y + r);
    ctx.moveTo(x - r, y + r);
    ctx.lineTo(x + r, y - r);
  } else ctx.arc(x, y, r, 0, 2 * Math.PI);
}

// drawSymbol(ctx, symbol, part, px, over, alpha): one part (engine/
// vectortiles.js) with an ArcGIS symbol. over: visual variables {color
// {color, alpha}, size (pt), opacity (0..1), rotation (degrees clockwise)};
// alpha: the layer's opacity.
export function drawSymbol(ctx, symbol, part, px, over = {}, alpha = 1) {
  const s = symbol || {};
  const a = alpha * (over.opacity === undefined || over.opacity === null ? 1 : over.opacity);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  if (part.kind === "point") {
    part.coords.forEach((c) => {
      const [x, y] = px(c);
      ctx.save();
      ctx.translate(x, y);
      const rot = (Number(over.rotation) || 0) + (Number(s.angle) || 0) * (s.type === "esriSMS" || s.type === "esriPMS" ? -1 : 0);
      if (rot) ctx.rotate((rot * Math.PI) / 180);
      if (s.type === "esriPMS") {
        const img = imageFor(pictureSrc(s));
        const w = over.size ? ptToPx(over.size) : ptToPx(s.width || 12);
        const h = over.size ? ptToPx(over.size) : ptToPx(s.height || s.width || 12);
        if (img) {
          ctx.globalAlpha = Math.max(0, Math.min(1, a));
          ctx.drawImage(img, -w / 2 + ptToPx(s.xoffset || 0), -h / 2 - ptToPx(s.yoffset || 0), w, h);
        }
      } else {
        const r = ptToPx(over.size || s.size || 8) / 2;
        const shape = SHAPES[s.style] || "circle";
        markerPath(ctx, shape, ptToPx(s.xoffset || 0), -ptToPx(s.yoffset || 0), r);
        const fc = over.color || esriColor(s.color);
        if (fc && shape !== "cross" && shape !== "x") {
          ctx.globalAlpha = Math.max(0, Math.min(1, fc.alpha * a));
          ctx.fillStyle = fc.color;
          ctx.fill();
        }
        if (shape === "cross" || shape === "x") strokeWith(ctx, { color: s.color, width: (s.outline && s.outline.width) || 1 }, a, fc);
        else strokeWith(ctx, s.outline, a);
      }
      ctx.restore();
    });
    return;
  }
  tracePath(ctx, part, px);
  if (part.kind === "line") {
    strokeWith(ctx, s.type === "esriSLS" ? s : s.outline || s, a, over.color);
    return;
  }
  // polygons
  if (s.type === "esriPFS") {
    const img = imageFor(pictureSrc(s));
    if (img) {
      ctx.globalAlpha = Math.max(0, Math.min(1, a));
      ctx.fillStyle = ctx.createPattern(img, "repeat");
      ctx.fill("evenodd");
    }
  } else if (s.type === "esriSFS" && s.style !== "esriSFSNull") {
    const fc = over.color || esriColor(s.color);
    if (fc && fc.alpha > 0) {
      const pat = s.style && s.style !== "esriSFSSolid" ? hatchPattern(ctx, s.style, fc.color) : null;
      ctx.globalAlpha = Math.max(0, Math.min(1, fc.alpha * a));
      ctx.fillStyle = pat || fc.color;
      ctx.fill("evenodd");
    }
  } else if (s.type === "esriSMS" || s.type === "esriPMS") {
    // a marker symbol on a polygon layer: fill with its color
    const fc = over.color || esriColor(s.color);
    if (fc) {
      ctx.globalAlpha = Math.max(0, Math.min(1, fc.alpha * a));
      ctx.fillStyle = fc.color;
      ctx.fill("evenodd");
    }
  }
  strokeWith(ctx, s.outline, a);
  ctx.globalAlpha = 1;
}
