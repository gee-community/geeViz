// A small ArcGIS REST client for the Esri plug-ins: requests (GET, or a POST
// form when the URL would be too long), the service's own errors, service
// metadata, which kind of layer a service is, Esri JSON and GeoJSON
// geometries, and a time-enabled service's time steps. No ArcGIS JS API.

export class EsriError extends Error {
  constructor(message, code = null, details = []) {
    super(message);
    this.name = "EsriError";
    this.code = code;
    this.details = details || [];
  }
}

const CROSS_SITE = "This service does not allow requests from this page.";

function encodeParams(params) {
  const out = new URLSearchParams();
  Object.keys(params).forEach((k) => {
    const v = params[k];
    if (v === undefined || v === null) return;
    out.set(k, typeof v === "object" ? JSON.stringify(v) : String(v));
  });
  return out;
}

// esriRequest(url, params, {fetch, signal, maxGet}) -> Promise of the JSON.
// ArcGIS answers many failures with HTTP 200 and an {error} body: both that
// and an HTTP error reject with EsriError.
export async function esriRequest(url, params = {}, opts = {}) {
  const fetchFn = opts.fetch || globalThis.fetch;
  const maxGet = opts.maxGet || 2000;
  const p = { ...params };
  if (p.f === undefined) p.f = "json";
  const query = encodeParams(p).toString();
  const getUrl = url + (url.indexOf("?") > -1 ? "&" : "?") + query;
  let res;
  try {
    if (getUrl.length <= maxGet) res = await fetchFn(getUrl, { signal: opts.signal });
    else {
      res = await fetchFn(url, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: query,
        signal: opts.signal,
      });
    }
  } catch (e) {
    if (e && e.name === "AbortError") throw e;
    // fetch rejects with a TypeError when the browser blocks the answer
    // (no CORS headers) or the network is down; the page cannot tell which.
    if (e instanceof TypeError) throw new EsriError(CROSS_SITE);
    throw e;
  }
  if (!res.ok) throw new EsriError(`The service answered HTTP ${res.status}.`, res.status);
  // the answer's size as received (opts.onSize), for a layer's size budget
  let body;
  try {
    if (typeof res.text === "function") {
      const text = await res.text();
      if (opts.onSize) opts.onSize(text.length);
      body = JSON.parse(text);
    } else body = await res.json();
  } catch (e) {
    throw new EsriError("The service did not answer with JSON.");
  }
  if (body && body.error) {
    const err = body.error;
    const details = (err.details || []).filter((d) => d && d !== err.message);
    const parts = (err.message ? [err.message] : []).concat(details);
    const msg = parts.length ? parts.join("; ") : "The service reported an error.";
    throw new EsriError(msg, err.code === undefined ? null : err.code, err.details || []);
  }
  return body;
}

// Service metadata (?f=json), asked once per URL for the page's life.
const INFO = new Map();
export function serviceInfo(url, opts = {}) {
  if (!INFO.has(url)) {
    const pr = esriRequest(url, {}, opts);
    INFO.set(url, pr);
    pr.catch(() => INFO.get(url) === pr && INFO.delete(url));
  }
  return INFO.get(url);
}

export function isWebMercator(sr) {
  if (!sr) return false;
  return [102100, 102113, 3857, 900913].some((id) => sr.wkid === id || sr.latestWkid === id);
}

const cached = (info) => !!info && !!info.tileInfo && isWebMercator(info.tileInfo.spatialReference) && (info.singleFusedMapCache === true || !!info.cacheType);

// The plug-in kind for a service URL and its metadata. A FeatureServer root
// is its first layer (normalizeUrl). opts: {renderingRule, time} the layer
// asks for: a cached image service drawn with either is exported, not tiled.
export function serviceKind(url, info, opts = {}) {
  const u = normalizeUrl(url);
  if (/\/(FeatureServer|MapServer)\/\d+$/i.test(u)) return "esri.feature";
  if (/\/ImageServer$/i.test(u)) return cached(info) && !opts.renderingRule && !opts.time ? "esri.tile" : "esri.image";
  if (/\/MapServer$/i.test(u)) return cached(info) ? "esri.tile" : "esri.map";
  return "esri.map";
}

// A map service sublayer (".../MapServer/3"): its map service and id; else null.
export function sublayerOf(url) {
  const m = /^(.*\/MapServer)\/(\d+)$/i.exec(normalizeUrl(url));
  return m ? { parent: m[1], id: Number(m[2]) } : null;
}

export function normalizeUrl(url) {
  let u = String(url).trim().replace(/[?#].*$/, "").replace(/\/+$/, "");
  if (/\/FeatureServer$/i.test(u)) u += "/0";
  return u;
}

// ---- geometry ----
// Twice the signed area of a ring in x/y order: negative is clockwise.
function ringArea(ring) {
  let a = 0;
  for (let i = 0, n = ring.length; i < n; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[(i + 1) % n];
    a += x1 * y2 - x2 * y1;
  }
  return a;
}
const isClockwise = (ring) => ringArea(ring) < 0;

// Esri JSON geometry to GeoJSON. Polygon rings: a clockwise ring starts a
// polygon, counterclockwise rings that follow are its holes (Esri JSON's rule).
export function toGeoJSON(g) {
  if (!g) return null;
  if (typeof g.x === "number" && typeof g.y === "number") return { type: "Point", coordinates: [g.x, g.y] };
  if (Array.isArray(g.points)) return { type: "MultiPoint", coordinates: g.points.map((p) => [p[0], p[1]]) };
  if (Array.isArray(g.paths)) {
    const paths = g.paths.map((p) => p.map((c) => [c[0], c[1]]));
    return paths.length === 1 ? { type: "LineString", coordinates: paths[0] } : { type: "MultiLineString", coordinates: paths };
  }
  if (Array.isArray(g.rings)) {
    const polys = [];
    g.rings.forEach((r) => {
      const ring = r.map((c) => [c[0], c[1]]);
      if (ring.length < 4) return;
      if (isClockwise(ring) || !polys.length) polys.push([ring]);
      else polys[polys.length - 1].push(ring);
    });
    if (!polys.length) return null;
    return polys.length === 1 ? { type: "Polygon", coordinates: polys[0] } : { type: "MultiPolygon", coordinates: polys };
  }
  if (typeof g.xmin === "number") {
    const { xmin, ymin, xmax, ymax } = g;
    return { type: "Polygon", coordinates: [[[xmin, ymin], [xmin, ymax], [xmax, ymax], [xmax, ymin], [xmin, ymin]]] };
  }
  return null;
}

// GeoJSON polygons (a geometry, Feature or FeatureCollection) to one Esri
// polygon in WGS84: outer rings clockwise, holes counterclockwise.
export function toEsriPolygon(gj) {
  const rings = [];
  const orient = (ring, cw) => (isClockwise(ring) === cw ? ring : ring.slice().reverse());
  const poly = (coords) => coords.forEach((ring, i) => rings.push(orient(ring.map((c) => [c[0], c[1]]), i === 0)));
  const walk = (o) => {
    if (!o) return;
    if (o.type === "FeatureCollection") (o.features || []).forEach(walk);
    else if (o.type === "Feature") walk(o.geometry);
    else if (o.type === "GeometryCollection") (o.geometries || []).forEach(walk);
    else if (o.type === "Polygon") poly(o.coordinates);
    else if (o.type === "MultiPolygon") o.coordinates.forEach(poly);
  };
  walk(gj);
  return { rings, spatialReference: { wkid: 4326 } };
}

// ---- time ----
const UNIT = {
  esriTimeUnitsYears: "y",
  esriTimeUnitsMonths: "m",
  esriTimeUnitsWeeks: "w",
  esriTimeUnitsDays: "d",
  esriTimeUnitsHours: "h",
};
function advance(t, n, unit) {
  const d = new Date(t);
  if (unit === "y") return Date.UTC(d.getUTCFullYear() + n, d.getUTCMonth(), d.getUTCDate(), d.getUTCHours());
  if (unit === "m") return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + n, d.getUTCDate(), d.getUTCHours());
  const ms = { w: 7 * 864e5, d: 864e5, h: 36e5 }[unit];
  return t + n * ms;
}
const pad = (n) => String(n).padStart(2, "0");
function stepLabel(t, unit) {
  const d = new Date(t);
  const y = String(d.getUTCFullYear());
  if (unit === "y") return y;
  if (unit === "m") return `${y}-${pad(d.getUTCMonth() + 1)}`;
  if (unit === "h") return `${y}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:00`;
  return `${y}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}
export const yearSpan = (y) => [Date.UTC(Number(y), 0, 1), Date.UTC(Number(y) + 1, 0, 1) - 1];

// A time-enabled service's steps, [{label, time: [startMs, endMs]}]: from its
// timeInfo interval, else one per catalog year; none without timeInfo.
export function timeSteps(info, years = null) {
  const ti = info && info.timeInfo;
  if (!ti) return [];
  const unit = UNIT[ti.defaultTimeIntervalUnits];
  const n = Number(ti.defaultTimeInterval);
  const ext = ti.timeExtent || [];
  if (unit && n > 0 && ext.length === 2 && ext[0] !== null && ext[1] !== null) {
    const out = [];
    for (let t = ext[0]; t <= ext[1] && out.length < 10000; ) {
      const next = advance(t, n, unit);
      out.push({ label: stepLabel(t, unit), time: [t, next - 1] });
      t = next;
    }
    return out;
  }
  return (years || []).map((y) => ({ label: String(y), time: yearSpan(y) }));
}

// The distinct catalog years of a time-enabled image service with no
// interval (the `year` field, else the start time field as years), sorted;
// null for anything else.
export async function catalogYears(url, info, opts = {}) {
  const ti = info && info.timeInfo;
  if (!ti || Number(ti.defaultTimeInterval) > 0 || !/\/ImageServer$/i.test(normalizeUrl(url))) return null;
  const fields = info.fields || [];
  const yearField = fields.find((f) => String(f.name).toLowerCase() === "year");
  const field = yearField ? yearField.name : ti.startTimeField;
  if (!field) return null;
  const out = await esriRequest(normalizeUrl(url) + "/query", {
    where: "1=1",
    outFields: field,
    returnDistinctValues: true,
    returnGeometry: false,
    orderByFields: field,
  }, opts);
  const years = new Set();
  (out.features || []).forEach((f) => {
    let v = f.attributes && f.attributes[field];
    if (v === null || v === undefined) return;
    if (!yearField) v = /^\d{8}$/.test(String(v)) ? Number(String(v).slice(0, 4)) : new Date(v).getUTCFullYear();
    if (Number.isFinite(Number(v))) years.add(Number(v));
  });
  return [...years].sort((a, b) => a - b);
}
