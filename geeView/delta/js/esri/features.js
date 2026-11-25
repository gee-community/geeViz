// An ArcGIS feature layer's features, fetched by the browser for the view
// as the ArcGIS JS API's FeatureLayer fetches them: one query per map tile
// (the tile's envelope), generalized for the zoom (maxAllowableOffset), in
// WGS84, paged while the service says there is more, only the fields the
// map needs (all fields are asked for the features a click hits), and
// nothing outside the layer's scale range.
import { esriRequest, toGeoJSON } from "./rest.js";
import { tile3857 } from "./draw.js";
import { flatten, tileBounds } from "../engine/vectortiles.js";

// The map scale at a zoom (ArcGIS's Web Mercator tiling at 96 dpi).
export const scaleAt = (zoom) => 591657527.591555 / Math.pow(2, zoom);

export function oidField(info) {
  if (info && info.objectIdField) return info.objectIdField;
  const f = ((info && info.fields) || []).find((x) => x.type === "esriFieldTypeOID");
  return f ? f.name : "OBJECTID";
}

// The fields a layer's renderer draws by (and its labels), for outFields.
export function rendererFields(info) {
  const r = (info && info.drawingInfo && info.drawingInfo.renderer) || {};
  const out = [r.field, r.field1, r.field2, r.field3, r.normalizationField, r.rotationField, r.valueExpression ? null : null];
  (r.visualVariables || []).forEach((v) => out.push(v.field, v.normalizationField));
  (r.attributes || []).forEach((a) => out.push(a.field));
  return out.filter((f) => typeof f === "string" && f);
}

const outOfScale = (info, zoom) => {
  const s = scaleAt(zoom);
  const min = Number(info && info.minScale) || 0;
  const max = Number(info && info.maxScale) || 0;
  return (min > 0 && s > min) || (max > 0 && s < max);
};

const unique = (xs) => [...new Set(xs)];
const DEG_PER_M = 1 / 111320;

// createFeatureSource(url, info, esriOpts, {fetch, onStatus}) ->
// {partsFor(coord, zoom, signal) -> Promise<parts>, attributes(fids, signal)}.
// esriOpts: where, outFields, bbox [w, s, e, n], time [start, end],
// maxFeatures (per tile, default 2000), simplify (false: exact geometry; a
// number: tolerance in meters), maxLayerMB (what the layer may fetch,
// default 64: the most the layer keeps; the tiles used longest ago are
// dropped to stay within it, and fetched again if shown again).
// onStatus({key, zoom, capped, shown, outOfScale}) each time a tile is asked
// for, cached or not. Caps are per map tile.
export function createFeatureSource(url, info, esriOpts = {}, opts = {}) {
  const o = esriOpts || {};
  const fetch = opts.fetch;
  const onStatus = opts.onStatus || (() => {});
  const maxFeatures = Number(o.maxFeatures) > 0 ? Number(o.maxFeatures) : Number(opts.defaultMaxFeatures) > 0 ? Number(opts.defaultMaxFeatures) : 2000;
  const budget = (Number(o.maxLayerMB) > 0 ? Number(o.maxLayerMB) : 64) * 1e6;
  const maxRecord = Number(info.maxRecordCount) > 0 ? Number(info.maxRecordCount) : 1000;
  const paging = !info.advancedQueryCapabilities || info.advancedQueryCapabilities.supportsPagination !== false;
  const oid = oidField(info);
  const geojson = /geojson/i.test(String(info.supportedQueryFormats || ""));
  const outFields = o.outFields ? [].concat(o.outFields).join(",") : unique([oid, info.displayField, ...rendererFields(info)].filter(Boolean)).join(",");
  const cacheTiles = Number(opts.cacheTiles) > 0 ? Number(opts.cacheTiles) : 512;
  const cache = new Map(); // "z/x/y" -> {promise, bytes, status}, least recently used first
  // a heatmap needs the points around a tile too (its blur radius in pixels)
  const padPx = Number(opts.padPx) || 0;
  const padded = (b, zoom) => {
    if (!padPx) return b;
    const m = (padPx * (b.xmax - b.xmin)) / 256;
    return { xmin: b.xmin - m, ymin: b.ymin - m, xmax: b.xmax + m, ymax: b.ymax + m };
  };
  const heldBytes = () => [...cache.values()].reduce((n, e) => n + (e.bytes || 0), 0);
  // drop the tiles used longest ago until the layer is within its budget (never `keep`)
  function trim(keep) {
    for (const [k, e] of cache) {
      if (heldBytes() <= budget && cache.size <= cacheTiles) break;
      if (k !== keep && e.done) cache.delete(k);
    }
  }

  function featuresOf(out) {
    if (geojson) {
      return (out.features || []).map((f) => ({
        type: "Feature",
        id: f.id !== undefined && f.id !== null ? f.id : f.properties && f.properties[oid],
        properties: f.properties || {},
        geometry: f.geometry,
      }));
    }
    return (out.features || []).map((f) => ({
      type: "Feature",
      id: f.attributes ? f.attributes[oid] : undefined,
      properties: f.attributes || {},
      geometry: toGeoJSON(f.geometry),
    }));
  }

  async function fetchTile(coord, zoom, key, signal, entry) {
    const params = {
      geometry: { ...padded(tile3857(coord.x, coord.y, zoom), zoom), spatialReference: { wkid: 3857 } },
      geometryType: "esriGeometryEnvelope",
      inSR: 3857,
      spatialRel: "esriSpatialRelIntersects",
      outSR: 4326,
      outFields,
      where: o.where || "1=1",
      returnGeometry: true,
      geometryPrecision: 6,
      f: geojson ? "geojson" : "json",
    };
    if (o.simplify !== false) {
      params.maxAllowableOffset = typeof o.simplify === "number" ? o.simplify * DEG_PER_M : 360 / (256 * Math.pow(2, zoom));
    }
    if (Array.isArray(o.time) && o.time.length === 2) params.time = o.time.join(",");
    const feats = [];
    let offset = 0;
    let capped = false;
    for (;;) {
      if (paging) params.resultRecordCount = Math.min(maxRecord, maxFeatures - feats.length);
      if (offset) params.resultOffset = offset;
      const out = await esriRequest(url + "/query", params, { fetch, signal, onSize: (n) => (entry.bytes += n) });
      let got = featuresOf(out);
      const more = !!(out.exceededTransferLimit || (out.properties && out.properties.exceededTransferLimit));
      if (feats.length + got.length >= maxFeatures) {
        capped = more || feats.length + got.length > maxFeatures;
        feats.push(...got.slice(0, maxFeatures - feats.length));
        break;
      }
      feats.push(...got);
      if (!more || !got.length || !paging) {
        capped = more;
        break;
      }
      offset += got.length;
    }
    const parts = flatten({ type: "FeatureCollection", features: feats });
    entry.status = { key, zoom, capped, shown: feats.length, outOfScale: false };
    entry.done = true;
    onStatus(entry.status);
    trim(key);
    return parts;
  }

  function partsFor(coord, zoom, signal) {
    const key = `${zoom}/${coord.x}/${coord.y}`;
    if (outOfScale(info, zoom)) {
      onStatus({ key, zoom, capped: false, shown: 0, outOfScale: true });
      return Promise.resolve([]);
    }
    if (Array.isArray(o.bbox) && o.bbox.length === 4) {
      const b = tileBounds(coord.x, coord.y, zoom);
      const [w, s, e, n] = o.bbox.map(Number);
      if (b.east < w || b.west > e || b.north < s || b.south > n) return Promise.resolve([]);
    }
    if (cache.has(key)) {
      const e = cache.get(key);
      cache.delete(key); // most recently used last
      cache.set(key, e);
      // the tile's status again: the row's note follows what is shown
      return e.promise.then((parts) => {
        if (e.status) onStatus(e.status);
        return parts;
      });
    }
    const entry = { promise: null, bytes: 0, status: null, done: false };
    entry.promise = fetchTile(coord, zoom, key, signal, entry);
    cache.set(key, entry);
    entry.promise.catch(() => cache.get(key) === entry && cache.delete(key));
    return entry.promise;
  }

  // Every field of the features a click hit, by object id: {fid: attributes}.
  async function attributes(fids, signal) {
    const ids = unique(fids).filter((x) => x !== undefined && x !== null);
    if (!ids.length) return {};
    const out = await esriRequest(url + "/query", { objectIds: ids.join(","), outFields: "*", returnGeometry: false }, { fetch, signal });
    const by = {};
    (out.features || []).forEach((f) => {
      const a = f.attributes || f.properties || {};
      by[a[oid]] = a;
    });
    return by;
  }

  return { partsFor, attributes, oid, heldBytes };
}
