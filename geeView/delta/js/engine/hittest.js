// What a click hits among vectors drawn in the browser (GeoJSON and ArcGIS
// feature layers), as the ArcGIS JS API's hit test answers it: in screen
// pixels at the zoom, a point within the point tolerance of its marker, a
// line within the line tolerance, a polygon when the click is inside it
// (holes excluded). One hit per feature, the one drawn last first.
import { worldPx } from "./vectortiles.js";
import { POINT_TOLERANCE_PX, LINE_TOLERANCE_PX } from "./query.js";

// distance from p to the segment a-b, all [x, y]
function segDist(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  let t = len2 ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2 : 0;
  t = Math.max(0, Math.min(1, t));
  const x = a[0] + t * dx - p[0];
  const y = a[1] + t * dy - p[1];
  return Math.sqrt(x * x + y * y);
}

// even-odd point in polygon over all rings (holes are rings too)
function inside(p, rings) {
  let hit = false;
  rings.forEach((ring) => {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if (yi > p[1] !== yj > p[1] && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) hit = !hit;
    }
  });
  return hit;
}

// hitTest(parts, {lng, lat}, zoom, {pointPx, linePx, markerPx}) -> parts hit
export function hitTest(parts, at, zoom, opts = {}) {
  const pointPx = opts.pointPx === undefined ? POINT_TOLERANCE_PX : opts.pointPx;
  const linePx = opts.linePx === undefined ? LINE_TOLERANCE_PX : opts.linePx;
  const markerPx = opts.markerPx === undefined ? 4 : opts.markerPx;
  const click = worldPx(at.lng, at.lat, zoom);
  const reach = Math.max(pointPx + markerPx, linePx);
  const degPerPx = 360 / (256 * Math.pow(2, zoom));
  const near = (bbox) => {
    const pad = reach * degPerPx * 2;
    return at.lng >= bbox[0] - pad && at.lng <= bbox[2] + pad && at.lat >= bbox[1] - pad && at.lat <= bbox[3] + pad;
  };
  const px = (c) => worldPx(c[0], c[1], zoom);
  const hits = [];
  const seen = new Set();
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (seen.has(p.fid) || !near(p.bbox)) continue;
    let hit = false;
    if (p.kind === "point") {
      hit = p.coords.some((c) => {
        const [x, y] = px(c);
        return Math.hypot(x - click[0], y - click[1]) <= pointPx + markerPx;
      });
    } else if (p.kind === "line") {
      hit = p.coords.some((line) => {
        const pts = line.map(px);
        for (let k = 1; k < pts.length; k++) if (segDist(click, pts[k - 1], pts[k]) <= linePx) return true;
        return false;
      });
    } else if (p.kind === "polygon") {
      hit = inside(click, p.coords.map((ring) => ring.map(px)));
    }
    if (hit) {
      seen.add(p.fid);
      hits.push(p);
    }
  }
  return hits;
}
