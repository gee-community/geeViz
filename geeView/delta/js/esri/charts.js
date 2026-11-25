// Chart area on ArcGIS services, as Delta charts Earth Engine layers: an
// image service's class areas from computeHistograms (over time for a
// time-enabled service, and class transitions between periods for a
// Sankey), and a feature layer's features counted (or summed) by a field
// with outStatistics. Answers are shaped as Earth Engine's reductions, so
// Delta's own chart builders (engine/areachart.js) format them: units,
// percentages, class names and colors.
import { esriRequest, serviceInfo, normalizeUrl, toEsriPolygon, timeSteps, catalogYears, isWebMercator } from "./rest.js";
import { classInfoOf } from "./identify.js";
import { layerChoice } from "./legend.js";
import { glyphFor } from "./symbols.js";
import { oidField } from "./features.js";
import { lineResult, sankeyResult } from "../engine/areachart.js";
import { SPLIT_STR } from "../engine/charts.js";
import { transitionBandNames } from "../engine/sankey.js";

const BAND = "value";
// Web Mercator meters per map pixel at zoom 0
const MPP0 = 156543.03392804097;

// fn over items, at most n at a time, in order.
export async function mapLimit(items, n, fn) {
  const out = new Array(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      out[i] = await fn(items[i], i);
    }
  };
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, worker));
  return out;
}

// A request asked once more after a short wait when it fails (a service
// refuses a burst of requests now and then).
async function again(fn, delay) {
  try {
    return await fn();
  } catch (e) {
    await new Promise((r) => setTimeout(r, delay));
    return fn();
  }
}

// A histogram's counts by value: {value: count}, empty bins left out. A
// class map's bins are whole values; others are named by their centers.
export function histogramCounts(h, integer) {
  const out = {};
  if (!h || !Array.isArray(h.counts)) return out;
  const width = (h.max - h.min) / h.size;
  h.counts.forEach((n, i) => {
    if (!n) return;
    const center = h.min + (i + 0.5) * width;
    const key = integer ? String(Math.round(center)) : String(Number(center.toPrecision(4)));
    out[key] = (out[key] || 0) + n;
  });
  return out;
}

function areaOf(area) {
  const poly = toEsriPolygon(area && area.geojson);
  if (!poly.rings.length) throw new Error("This area has no outline to chart ArcGIS layers over.");
  let s = Infinity, n = -Infinity;
  poly.rings.forEach((r) => r.forEach(([, y]) => ((s = Math.min(s, y)), (n = Math.max(n, y)))));
  return { poly, lat: (s + n) / 2 };
}

// The pixel size to ask for (the service's, or one map pixel when coarser)
// and the ground size of a pixel in meters, for areas.
function pixelSizes(info, zoom, lat) {
  const native = Number(info.pixelSizeX) || 30;
  const wm = isWebMercator(info.spatialReference);
  const mapPx = wm ? MPP0 / Math.pow(2, zoom) : (MPP0 / Math.pow(2, zoom)) * Math.cos((lat * Math.PI) / 180);
  const s = Math.max(native, mapPx);
  return { s, ground: wm ? s * Math.cos((lat * Math.PI) / 180) : s };
}

const classInfoFor = (ci) => (ci ? { [BAND]: { classValues: ci.values, classNames: ci.names, ...(ci.colors.some(Boolean) ? { classPalette: ci.colors } : {}) } } : {});

async function catalogItem(url, info, year, opts) {
  const yf = (info.fields || []).find((f) => String(f.name).toLowerCase() === "year");
  const where = yf ? `${yf.name} = ${Number(year)}` : null;
  if (!where) return null;
  const out = await esriRequest(url + "/query", { where, outFields: oidField(info) + (yf ? "," + yf.name : ""), returnGeometry: false }, opts);
  const f = (out.features || [])[0];
  return f ? f.attributes[out.objectIdFieldName || oidField(info)] : null;
}

// imageChart(layer, area, {fetch, zoom, kind, params, periods}) ->
// {results(ctx)}: a class (or value) chart, or for kind "sankey" the class
// transitions between periods.
export async function imageChart(layer, area, cctx) {
  const url = normalizeUrl(layer.item);
  const req = { fetch: cctx.fetch };
  const info = await serviceInfo(url, req);
  const opts = (layer.viz && layer.viz.esri) || {};
  const { poly, lat } = areaOf(area);
  const { s, ground } = pixelSizes(info, cctx.zoom === undefined ? 10 : cctx.zoom, lat);
  const ci = classInfoOf(layer.legend);
  const base = { geometry: poly, geometryType: "esriGeometryPolygon", pixelSize: { x: s, y: s, spatialReference: info.spatialReference } };
  const delay = cctx.retryDelay === undefined ? 1500 : cctx.retryDelay;
  const histogram = (extra) => again(() => esriRequest(url + "/computeHistograms", { ...base, ...extra }, req), delay).then((o) => (o.histograms || [])[0] || null);

  if (cctx.kind === "sankey") {
    if (!ci) throw new Error(`${layer.name} is not a class map, so it has no class transitions to chart.`);
    const periods = cctx.periods || [];
    const K = Number(info.maxValues && info.maxValues[0]) + 1;
    if (!(K > 1)) throw new Error(`${layer.name} does not say its largest class value.`);
    const raw = {};
    const names = transitionBandNames(periods);
    for (let i = 0; i + 1 < periods.length; i++) {
      const [a, b] = await Promise.all([catalogItem(url, info, periods[i][0], req), catalogItem(url, info, periods[i + 1][0], req)]);
      if (a === null || b === null) throw new Error(`${layer.name} has no image for ${a === null ? periods[i][0] : periods[i + 1][0]}.`);
      const rule = {
        rasterFunction: "Arithmetic",
        rasterFunctionArguments: { Raster: { rasterFunction: "Arithmetic", rasterFunctionArguments: { Raster: `$${a}`, Raster2: K, Operation: 3 } }, Raster2: `$${b}`, Operation: 1 },
        outputPixelType: "U16",
      };
      const h = await histogram({ renderingRule: rule });
      const enc = {};
      Object.entries(histogramCounts(h, true)).forEach(([v, n]) => {
        const from = Math.floor(Number(v) / K);
        const to = Number(v) % K;
        // the encoding engine/sankey.js decodes: from * 10000 + 9900 + to
        enc[String(from * 10000 + 9900 + to)] = n;
      });
      raw[names[i]] = enc;
    }
    const entry = { raw, objInfo: { objType: "ImageCollection", bandNames: [BAND], classInfo: classInfoFor(ci) }, periods, band: BAND, scale: ground };
    return { results: (ctx) => [sankeyResult(layer, cctx.params, entry, { ...ctx, nominalScale: Math.round(ground) })] };
  }

  const timed = !!info.timeInfo && (layer.kind === "esri.timelapse" || (layer.viz && layer.viz.timelapse) || opts.time === "all");
  const common = {};
  if (opts.renderingRule) common.renderingRule = opts.renderingRule;
  if (opts.mosaicRule) common.mosaicRule = opts.mosaicRule;
  let raw;
  let labels = null;
  if (timed) {
    const steps = timeSteps(info, await catalogYears(url, info, req));
    // a few at a time: dozens at once and the service refuses some
    const hs = await mapLimit(steps, 4, (st) => histogram({ ...common, time: st.time.join(",") }));
    raw = {};
    labels = steps.map((st) => st.label);
    steps.forEach((st, i) => (raw[`${st.label}${SPLIT_STR}${BAND}`] = histogramCounts(hs[i], !!ci)));
  } else {
    if (Array.isArray(opts.time) && opts.time.length === 2) common.time = opts.time.join(",");
    raw = { [BAND]: histogramCounts(await histogram(common), !!ci) };
  }
  const entry = {
    raw,
    objInfo: { objType: timed ? "ImageCollection" : "Image", bandNames: [BAND], classInfo: classInfoFor(ci) },
    labels,
    isHistogram: true,
    scale: ground,
  };
  return { results: (ctx) => [lineResult(layer, cctx.params, entry, { ...ctx, nominalScale: Math.round(ground) })] };
}

const sqlValue = (v) => (typeof v === "number" ? String(v) : `'${String(v).replace(/'/g, "''")}'`);

// One feature layer's counts (or sums) by its renderer's classes within
// the area: {columns, values, colors}.
async function featureCounts(url, info, viz, area, req) {
  const opts = (viz && viz.esri) || {};
  const renderer = (info.drawingInfo && info.drawingInfo.renderer) || {};
  const sum = viz && viz.chartStatistic === "sum" && viz.chartValueField;
  const stat = { statisticType: sum ? "sum" : "count", onStatisticField: sum ? viz.chartValueField : oidField(info), outStatisticFieldName: "v" };
  const params = {
    geometry: areaOf(area).poly,
    geometryType: "esriGeometryPolygon",
    inSR: 4326,
    spatialRel: "esriSpatialRelIntersects",
    where: opts.where || "1=1",
    outStatistics: [stat],
    returnGeometry: false,
  };
  if (Array.isArray(opts.time) && opts.time.length === 2) params.time = opts.time.join(",");
  const field = (viz && viz.chartField) || (renderer.type === "uniqueValue" ? renderer.field1 : null);
  const colorOf = (symbol) => {
    const g = glyphFor(symbol, null);
    return g.fill || g.stroke || null;
  };
  if (field) {
    const out = await esriRequest(url + "/query", { ...params, groupByFieldsForStatistics: field }, req);
    const rows = (out.features || []).map((f) => [f.attributes[field], Number(f.attributes.v) || 0]);
    const infos = new Map(((renderer.type === "uniqueValue" && renderer.field1 === field && renderer.uniqueValueInfos) || []).map((i) => [String(i.value), i]));
    return {
      columns: rows.map(([k]) => (infos.has(String(k)) && infos.get(String(k)).label ? infos.get(String(k)).label : String(k))),
      values: rows.map(([, v]) => v),
      colors: rows.map(([k]) => (infos.has(String(k)) ? colorOf(infos.get(String(k)).symbol) : null)),
    };
  }
  if (renderer.type === "classBreaks" && renderer.field) {
    const infos = (renderer.classBreakInfos || []).slice().sort((a, b) => a.classMaxValue - b.classMaxValue);
    let lo = renderer.minValue;
    const outs = await Promise.all(
      infos.map((i) => {
        const where = `(${params.where}) AND ${renderer.field} ${lo === undefined || lo === null ? ">=" : infos.indexOf(i) === 0 ? ">=" : ">"} ${sqlValue(lo === undefined || lo === null ? -1e308 : lo)} AND ${renderer.field} <= ${sqlValue(i.classMaxValue)}`;
        lo = i.classMaxValue;
        return esriRequest(url + "/query", { ...params, where }, req);
      })
    );
    return {
      columns: infos.map((i) => String(i.label || i.classMaxValue)),
      values: outs.map((o) => Number(((o.features || [])[0] || { attributes: {} }).attributes.v) || 0),
      colors: infos.map((i) => colorOf(i.symbol)),
    };
  }
  const out = await esriRequest(url + "/query", params, req);
  return { columns: ["Features"], values: [Number(((out.features || [])[0] || { attributes: {} }).attributes.v) || 0], colors: [null] };
}

function barResult(layer, params, counts, label, sum, viz) {
  const raw = {};
  counts.columns.forEach((c, i) => (raw[c] = counts.values[i]));
  const entry = { raw, objInfo: { objType: "Image", bandNames: counts.columns }, labels: null, isHistogram: false, reducerLabel: sum ? `Sum of ${viz.chartValueField}` : "Features" };
  const palette = counts.colors.every(Boolean) ? counts.colors : params.palette;
  return (ctx) => lineResult({ ...layer, name: label }, { ...params, palette }, entry, { ...ctx, nominalScale: 0 });
}

// featureChart(layer, area, {fetch, params}) -> {results(ctx)}: a feature
// layer, or each charted sublayer of a map service.
export async function featureChart(layer, area, cctx) {
  const url = normalizeUrl(layer.item);
  const req = { fetch: cctx.fetch };
  const info = await serviceInfo(url, req);
  const viz = layer.viz || {};
  const sum = viz.chartStatistic === "sum" && viz.chartValueField;
  if (/\/(FeatureServer|MapServer)\/\d+$/i.test(url)) {
    const counts = await featureCounts(url, info, viz, area, req);
    const build = barResult(layer, cctx.params, counts, layer.name, sum, viz);
    return { results: (ctx) => [build(ctx)] };
  }
  // a map service: each sublayer it draws that has classes by a field
  const ids = [...layerChoice(info.layers || [], (viz.esri || {}).layers)];
  const subs = await Promise.all(ids.map((id) => serviceInfo(`${url}/${id}`, req).then((i) => [id, i], () => [id, null])));
  const charted = subs.filter(([, i]) => i && i.type === "Feature Layer" && i.drawingInfo && ["uniqueValue", "classBreaks"].includes((i.drawingInfo.renderer || {}).type));
  const builds = await Promise.all(
    charted.map(async ([id, i]) => {
      const counts = await featureCounts(`${url}/${id}`, i, { esri: viz.esri }, area, req);
      const build = barResult({ ...layer, id: `${layer.id}-${id}` }, cctx.params, counts, `${layer.name}: ${i.name}`, false, viz);
      return build;
    })
  );
  return { results: (ctx) => builds.map((b) => b(ctx)) };
}

// The first and last years a time-enabled image service has, for the
// Sankey period editor.
export async function serviceYears(layer, cctx) {
  const url = normalizeUrl(layer.item);
  const info = await serviceInfo(url, { fetch: cctx.fetch });
  const years = await catalogYears(url, info, { fetch: cctx.fetch });
  if (years && years.length) return years;
  const steps = timeSteps(info, null);
  return steps.length ? steps.map((s) => Number(s.label.slice(0, 4))) : null;
}
