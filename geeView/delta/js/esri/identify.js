// The Query tool on ArcGIS map, tile and image services, as the ArcGIS JS
// API's popups ask them: identify at the clicked point, within Delta's point
// tolerance in screen pixels. Answers become Delta's own result cards.
import { esriRequest } from "./rest.js";
import { layerChoice } from "./legend.js";
import { tableResults, imageResult, seriesResult, POINT_TOLERANCE_PX } from "../engine/query.js";

const pointGeometry = (p) => ({ x: p.lng, y: p.lat, spatialReference: { wkid: 4326 } });

// The `layers` an identify asks: the sublayers the layer draws.
function identifyLayers(info, spec) {
  if (!info || !Array.isArray(info.layers) || !info.layers.length) return "visible";
  const ids = [...layerChoice(info.layers, spec)].sort((a, b) => a - b);
  return ids.length ? "visible:" + ids.join(",") : "visible";
}

// identifyMap(url, point, view, esriOpts, {fetch, info, layer, precision})
// -> result cards: one attribute table per feature hit.
export async function identifyMap(url, point, view, esriOpts = {}, opts = {}) {
  const o = esriOpts || {};
  const b = view.bounds;
  const params = {
    geometry: pointGeometry(point),
    geometryType: "esriGeometryPoint",
    sr: 4326,
    layers: identifyLayers(opts.info, o.layers),
    tolerance: POINT_TOLERANCE_PX,
    mapExtent: [b.west, b.south, b.east, b.north].join(","),
    imageDisplay: `${Math.round(view.width)},${Math.round(view.height)},96`,
    returnGeometry: false,
  };
  if (Array.isArray(o.time) && o.time.length === 2) params.time = o.time.join(",");
  const out = await esriRequest(url + "/identify", params, { fetch: opts.fetch, signal: opts.signal });
  const layer = opts.layer;
  const hits = out.results || [];
  if (!hits.length) return tableResults(layer, { features: [] }, point, opts.precision);
  return hits.map((h, i) => {
    const r = tableResults(layer, { features: [{ properties: h.attributes || {} }] }, point, opts.precision)[0];
    const value = h.value === undefined || h.value === null || h.value === "" ? "" : `: ${h.value}`;
    return { ...r, id: `${layer.id}-t${i}`, meta: `${h.layerName || "Layer " + h.layerId}${value}` };
  });
}

// A class map's values, names and colors from its legend (items with a
// value); null when the legend does not number its classes.
export function classInfoOf(legend) {
  const items = legend && legend.type === "images" ? legend.items || [] : [];
  if (!items.length || items.some((it) => !Number.isFinite(it.value))) return null;
  return {
    values: items.map((it) => it.value),
    names: items.map((it) => it.label),
    colors: items.map((it) => it.color || null),
  };
}

const num = (v) => (v === null || v === undefined || v === "" || /^nodata$/i.test(String(v)) ? null : Number.isFinite(Number(v)) ? Number(v) : null);

// The viz keys query.js reads class names and colors from.
function classViz(ci, band) {
  if (!ci) return {};
  const queryDict = {};
  ci.values.forEach((v, i) => (queryDict[v] = ci.names[i]));
  const viz = { queryDict };
  // the classes whose swatch has a color (a class without one draws grey)
  const known = ci.values.map((v, i) => [v, ci.colors[i]]).filter(([, c]) => !!c);
  if (known.length) {
    viz.class_values = { [band]: known.map(([v]) => v) };
    viz.class_palette = { [band]: known.map(([, c]) => c) };
  }
  return viz;
}

// The year (or date) of a catalog item, for the x axis.
function itemTime(attrs, info) {
  const keys = Object.keys(attrs || {});
  const yk = keys.find((k) => k.toLowerCase() === "year");
  if (yk && attrs[yk] !== null) return Number(attrs[yk]);
  const sf = info && info.timeInfo && info.timeInfo.startTimeField;
  const v = sf ? attrs[sf] : null;
  if (v === null || v === undefined) return null;
  if (/^\d{8}$/.test(String(v))) return Number(String(v).slice(0, 4));
  return new Date(v).getUTCFullYear();
}

// identifyImage(url, point, esriOpts, legend, {fetch, info, layer, precision})
// -> the pixel value with its class, or with time, the values over time.
export async function identifyImage(url, point, esriOpts = {}, legend = null, opts = {}) {
  const o = esriOpts || {};
  const info = opts.info || {};
  const timed = !!info.timeInfo;
  const params = {
    geometry: pointGeometry(point),
    geometryType: "esriGeometryPoint",
    returnGeometry: false,
    returnCatalogItems: timed,
    returnPixelValues: true,
  };
  if (o.renderingRule) params.renderingRule = o.renderingRule;
  if (o.mosaicRule) params.mosaicRule = o.mosaicRule;
  if (Array.isArray(o.time) && o.time.length === 2) params.time = o.time.join(",");
  const out = await esriRequest(url + "/identify", params, { fetch: opts.fetch, signal: opts.signal });
  const layer = opts.layer;
  const band = "value";
  const viz = classViz(classInfoOf(legend), band);
  const items = (out.catalogItems && out.catalogItems.features) || [];
  const values = (out.properties && out.properties.Values) || [];
  if (timed && items.length && values.length === items.length && !(Array.isArray(o.time) && o.time.length === 2)) {
    const rows = items
      .map((f, i) => ({ t: itemTime(f.attributes, info), v: num(values[i]) }))
      .filter((r) => r.t !== null)
      .sort((a, b) => a.t - b.t);
    const ids = rows.map((r) => String(r.t));
    const vals = {};
    rows.forEach((r) => (vals[`${r.t}_${band}`] = r.v));
    return [seriesResult(layer, viz, { ids, labels: ids, bands: [band], values: vals, hasTime: true }, point, opts.precision)];
  }
  return [imageResult(layer, viz, { [band]: num(out.value) }, point, opts.precision)];
}
