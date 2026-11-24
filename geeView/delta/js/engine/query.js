// The Query tool: double-click (tap on phones) queries every visible layer at
// a point; select layers turn clicked features into selections.
//
// port of lcms-viewer 5chart-manager.js getQueryImages, makeQueryTable,
// startQuery (the doubletap handler), addClickMarker, setupAreaLayerSelection
// and addSelectedFeaturesToMapWrapper. Differences, by design: an image
// collection is stacked into one multi-band image and reduced once with
// reduceRegion (the original used getRegion over the query box), every call
// is evaluate() (the original used getInfo for the time property), and each
// query carries a request token so answers to an older point are dropped.
//
// The only DOM this module touches is through Google map objects (markers,
// rectangles, Data layers and the InfoWindow, whose content the UI builds).
import { smartToFixed, tokenSource } from "../util.js";
import { addColorHash } from "./viz.js";

// port of 1variables.js plotRadius default
const DEFAULT_PLOT_RADIUS = 15;
// port of 1variables.js clickBoundsColor
const DEFAULT_BOX_COLOR = "#FF0";
// port of 1variables.js yLabelMaxTotalLines
const Y_LABEL_MAX_TOTAL_LINES = 18;
const VECTOR_TYPES = ["geeVectorImage", "geeVector"];

const isNil = (v) => v === undefined || v === null;

function toPoint(latLng) {
  const lat = typeof latLng.lat === "function" ? latLng.lat() : latLng.lat;
  const lng = typeof latLng.lng === "function" ? latLng.lng() : latLng.lng;
  return { lng: Number(lng), lat: Number(lat) };
}

export function formatPoint(p) {
  return p.lng.toFixed(4) + ", " + p.lat.toFixed(4);
}

export function isInfoWindowMode(mode) {
  return String(mode || "").toLowerCase() === "infowindow";
}

// The original's reduceRegion inputs: crsTransform wins over scale.
export function queryInputs(q) {
  const crs = isNil(q.crs) ? null : q.crs;
  if (Array.isArray(q.transform) && q.transform.length) return { crs, scale: null, crsTransform: q.transform };
  return { crs, scale: isNil(q.scale) ? null : q.scale, crsTransform: null };
}

// port of 4map-manager.js setQueryScale / setQueryTransform plotRadius
export function plotRadius(q) {
  if (Array.isArray(q.transform) && q.transform.length) return q.transform[0] / 2;
  if (!isNil(q.scale)) return q.scale / 2;
  return DEFAULT_PLOT_RADIUS;
}

// Points and lines are drawn a few pixels wide, so a click has to land within
// a few pixels of one, not within plotRadius meters (15 m by default, under a
// pixel once zoomed out). As ArcGIS identify's `tolerance`: a radius in screen
// pixels, in meters at this zoom and latitude. Polygons keep plotRadius: a
// click inside one finds it, and a wider net would pick its neighbors too.
export const POINT_TOLERANCE_PX = 8;
export const LINE_TOLERANCE_PX = 5;
export function vectorQueryRadius(q, geoms, lat, zoom) {
  const base = plotRadius(q);
  const kinds = geoms || [];
  const px = kinds.indexOf("point") > -1 ? POINT_TOLERANCE_PX : kinds.indexOf("line") > -1 ? LINE_TOLERANCE_PX : 0;
  if (!px || !Number.isFinite(zoom)) return base;
  return Math.max(base, px * metersPerPixel(lat, zoom));
}

const precisionArgs = (precision) => {
  const p = precision || {};
  return [isNil(p.chartDecimalProportion) ? 0.25 : p.chartDecimalProportion, isNil(p.chartPrecision) ? 3 : p.chartPrecision];
};

// port of 1variables.js arraySmartToFixed
function arraySmartToFixed(a, prop, prec) {
  return a.map((e) => (Array.isArray(e) ? arraySmartToFixed(e, prop, prec) : smartToFixed(e, prop, prec)));
}

function displayOf(v, precision) {
  const [prop, prec] = precisionArgs(precision);
  if (v === null || v === undefined) return "No data";
  if (Array.isArray(v)) return JSON.stringify(arraySmartToFixed(v, prop, prec));
  if (typeof v === "object") return JSON.stringify(v);
  return String(smartToFixed(v, prop, prec));
}

// The class dictionary belongs to the viz band (autoViz sets viz.bands to the first band).
function dictFor(viz, band) {
  const d = viz && viz.queryDict;
  if (!d || typeof d !== "object" || !Object.keys(d).length) return null;
  const vb = viz.bands;
  if (isNil(vb)) return d;
  const vbs = Array.isArray(vb) ? vb : [vb];
  return vbs.length === 1 && vbs[0] !== band ? null : d;
}

function labelOf(viz, band, v) {
  if (!Number.isInteger(v)) return null;
  const d = dictFor(viz, band);
  if (!d) return null;
  const t = d[v];
  return t === undefined ? null : String(t);
}

function colorOf(viz, band, v) {
  const values = viz && viz.class_values && viz.class_values[band];
  const palette = viz && viz.class_palette && viz.class_palette[band];
  if (!Array.isArray(values) || !Array.isArray(palette)) return null;
  const i = values.indexOf(v);
  return i > -1 && palette[i] !== undefined ? addColorHash(String(palette[i]).replace(/^#/, "")) : null;
}

// port of makeQueryTable for a geeImage: one value per band, class names
// from the layer's query dictionary, floats rounded for display only.
// Units per band: `units` is {band: unit string}, shown after the value.
const withUnit = (display, unit) => (unit && display !== "No data" ? display + " " + unit : display);

export function imageResult(layer, viz, values, point, precision, units) {
  viz = viz || {};
  let keys = values && typeof values === "object" ? Object.keys(values) : [];
  // An RGB-visualized query image carries viz-red/green/blue; show the main band.
  if (keys.length === 4 && ["viz-red", "viz-green", "viz-blue"].every((k) => keys.indexOf(k) > -1)) {
    keys = keys.filter((k) => k.indexOf("viz-") === -1);
  }
  const bands = keys.map((band) => {
    const value = values[band];
    return { band, value, display: withUnit(displayOf(value, precision), units && units[band]), label: labelOf(viz, band, value), color: colorOf(viz, band, value) };
  });
  return {
    id: layer.id + "-v",
    layerId: layer.id,
    title: layer.name,
    meta: bands.length === 0 ? "No data" : bands.length === 1 ? bands[0].band : bands.length + " bands",
    kind: "value",
    data: { point, bands },
    actions: ["copy"],
  };
}

// The reducer a collection layer is drawn with (viz.reducer, serialized by
// geeView.py; lastNonNull when not given, as engine/layers.js eeTileLayer).
// Returns the Earth Engine name without "Reducer.", or null when it cannot be
// read (a combined or custom reducer).
export function displayReducer(viz) {
  const r = viz && viz.reducer;
  if (r === null || r === undefined || r === "") return "lastNonNull";
  if (typeof r === "string") {
    const m = /"functionName"\s*:\s*"Reducer\.(\w+)"/.exec(r);
    return m ? m[1] : null;
  }
  try {
    const sig = r.func && r.func.getSignature && r.func.getSignature();
    if (sig && sig.name) return String(sig.name).replace(/^Reducer\./, "");
  } catch (e) {
    /* unreadable */
  }
  return null;
}

// What the map shows at this point for a collection layer: its series reduced
// with the layer's own reducer, so the headline above the chart matches the
// pixel on the map. Earth Engine reduces each pixel over the images that have
// data there, as here over the non-null values. Unknown reducers fall back to
// the latest value and say so.
const SUMMARY = {
  lastNonNull: { how: "latest", pick: (v) => v.length - 1 },
  firstNonNull: { how: "first", pick: () => 0 },
  mode: { how: "most common" },
  mean: { how: "mean", calc: (v) => v.reduce((a, b) => a + b, 0) / v.length },
  median: {
    how: "median",
    calc: (v) => {
      const s = [...v].sort((a, b) => a - b);
      const m = Math.floor(s.length / 2);
      return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
    },
  },
  min: { how: "minimum", calc: (v) => Math.min(...v) },
  max: { how: "maximum", calc: (v) => Math.max(...v) },
  sum: { how: "sum", calc: (v) => v.reduce((a, b) => a + b, 0) },
  count: { how: "count", calc: (v) => v.length },
};
// mode: the most frequent value; a tie goes to the smallest value
export function modeOf(values) {
  const n = new Map();
  values.forEach((v) => n.set(v, (n.get(v) || 0) + 1));
  let best = null;
  n.forEach((c, v) => {
    if (best === null || c > n.get(best) || (c === n.get(best) && v < best)) best = v;
  });
  return best;
}
export function summarize(reducer, x, y) {
  const idx = [];
  y.forEach((v, i) => v !== null && v !== undefined && idx.push(i));
  if (!idx.length) return null;
  const vals = idx.map((i) => y[i]);
  const span = x.length ? (idx.length > 1 ? x[idx[0]] + " to " + x[idx[idx.length - 1]] : String(x[idx[0]])) : "";
  const rule = SUMMARY[reducer] || null;
  if (!rule || rule.pick) {
    const i = idx[rule ? rule.pick(vals) : vals.length - 1];
    return { value: y[i], x: x[i], how: rule ? rule.how : reducer ? "latest; the map shows " + reducer : "latest", reducer: rule ? reducer : null };
  }
  const value = rule.calc ? rule.calc(vals) : modeOf(vals);
  return { value, x: span, how: rule.how, reducer };
}

// port of getCollectionValues: one trace per band over the collection's
// images. `out` is {ids, labels, bands, values, hasTime} where values holds
// the stacked image's reduceRegion answer keyed `${id}_${band}`.
export function seriesResult(layer, viz, out, point, precision, dateFormat, units) {
  viz = viz || {};
  const ids = out.ids || [];
  const x = out.hasTime ? out.labels || ids : ids;
  const values = out.values || {};
  const palette = (viz.queryParams && viz.queryParams.palette) || [];
  const series = ids.length
    ? (out.bands || []).map((band, i) => {
        const y = ids.map((id) => {
          const v = values[id + "_" + band];
          return v === undefined ? null : v;
        });
        const unit = units && units[band];
        // a thematic band: each value's class color (null where it has none)
        const classColors = y.map((v) => (v === null ? null : colorOf(viz, band, v)));
        return {
          name: unit ? band + " (" + unit + ")" : band,
          band,
          y,
          labels: y.map((v) => labelOf(viz, band, v)),
          color: palette[i] !== undefined ? addColorHash(String(palette[i]).replace(/^#/, "")) : null,
          classColors: classColors.some((c) => c !== null) ? classColors : null,
        };
      })
    : [];
  // The headline: the first band reduced the way the map draws this layer.
  let latest = null;
  if (series.length) {
    const s = series[0];
    const sum = summarize(displayReducer(viz), x, s.y);
    if (sum) {
      const isInt = Number.isInteger(sum.value);
      latest = {
        x: sum.x,
        band: s.name,
        value: sum.value,
        how: sum.how,
        label: isInt ? labelOf(viz, s.band, sum.value) : null,
        color: isInt ? colorOf(viz, s.band, sum.value) : null,
      };
    }
  }
  // port of getQueryImages: the layer's queryDateFormat, else the default (setQueryDateFormat)
  const fmt = String(dateFormat || viz.queryDateFormat || "");
  return {
    id: layer.id + "-s",
    layerId: layer.id,
    title: layer.name,
    meta: series.length && x.length ? (x.length > 1 ? x[0] + " to " + x[x.length - 1] : String(x[0])) : "No data",
    kind: "series",
    data: {
      point,
      ids,
      x,
      xLabel: out.hasTime ? "Time" : "ID",
      xTickDateFormat: fmt.indexOf("HH:mm") > -1 ? "%Y-%m-%d\n%H:%M" : null,
      yLabel: (viz.queryParams && viz.queryParams.yLabel) || null,
      queryDict: dictFor(viz, (out.bands || [])[0]) || null,
      precision: precision || null,
      series,
      latest,
    },
    actions: ["csv", "png", "expand"],
  };
}

// port of makeQueryTable for vectors: one attribute table per feature.
export function tableResults(layer, fc, point, precision) {
  const [prop, prec] = precisionArgs(precision);
  const features = (fc && fc.features) || [];
  const table = (rows, i) => ({
    id: layer.id + "-t" + i,
    layerId: layer.id,
    title: layer.name,
    meta: rows === null ? "No features here" : features.length > 1 ? "Feature " + (i + 1) + " of " + features.length : "Attribute table",
    kind: "table",
    data: { point, rows: rows || [] },
    actions: ["copy", "csv"],
  });
  if (!features.length) return [table(null, 0)];
  return features.map((f, i) =>
    table(
      Object.keys(f.properties || {}).map((k) => {
        const v = f.properties[k];
        let s = smartToFixed(v, prop, prec);
        if (k === "Acres" && typeof s === "number") s = s.toLocaleString("en-US", { maximumFractionDigits: 20 });
        else if (s !== null && typeof s === "object") s = JSON.stringify(s);
        return [k, String(s)];
      }),
      i
    )
  );
}

// port of getQueryImages breakLabels: labels cut to yLabelMaxLength, broken
// every yLabelBreakLength, at most yLabelMaxLines lines each, fewer lines
// when all labels together pass the total line cap.
export function breakLabels(labels, settings = {}) {
  const maxLength = settings.yLabelMaxLength || 30;
  const breakLength = settings.yLabelBreakLength || 10;
  let maxLines = settings.yLabelMaxLines || 5;
  const maxTotal = settings.yLabelMaxTotalLines || Y_LABEL_MAX_TOTAL_LINES;
  const chunk = (s) => String(s).match(new RegExp(".{1," + breakLength + "}", "g")) || [String(s)];
  for (;;) {
    let total = 0;
    const out = labels.map((l) => {
      const parts = chunk(String(l).slice(0, maxLength)).slice(0, maxLines);
      total += parts.length;
      return parts.join("<br>");
    });
    if (total > maxTotal && maxLines > 1) maxLines--;
    else return out;
  }
}

function csvCell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
const csvRows = (rows) => rows.map((r) => r.map(csvCell).join(",")).join("\n") + "\n";

export function resultCsv(r) {
  if (r.kind === "series") {
    const head = [r.data.xLabel].concat(r.data.series.map((s) => s.name));
    return csvRows([head].concat(r.data.x.map((x, i) => [x].concat(r.data.series.map((s) => s.y[i])))));
  }
  if (r.kind === "table") return csvRows([["Property", "Value"]].concat(r.data.rows));
  if (r.kind === "value") return csvRows([["Band", "Value", "Label"]].concat(r.data.bands.map((b) => [b.band, b.value, b.label])));
  return "";
}

export function resultText(r) {
  if (r.kind === "value") {
    const b = r.data.bands;
    if (!b.length) return r.title + ": No data";
    const one = (x) => (x.label !== null ? x.label + " (" + x.display + ")" : x.display);
    if (b.length === 1) return r.title + ": " + one(b[0]);
    return [r.title].concat(b.map((x) => x.band + ": " + one(x))).join("\n");
  }
  if (r.kind === "table") return [r.title].concat(r.data.rows.map(([k, v]) => k + ": " + v)).join("\n");
  return resultCsv(r);
}

// port of 2templates.js addLayer select layer name: selectLayerNameProperty,
// else the last property with "name" in it, else null (the feature id).
export function pickNameProperty(viz, props) {
  if (viz && !isNil(viz.selectLayerNameProperty)) return viz.selectLayerNameProperty;
  let name = null;
  Object.keys(props || {}).forEach((p) => {
    if (p.toLowerCase().indexOf("name") !== -1) name = p;
  });
  return name;
}

const evaluate = (obj) =>
  new Promise((resolve, reject) => obj.evaluate((v, err) => (err ? reject(new Error(String(err))) : resolve(v))));

// One Earth Engine request per layer.
function queryOne(eeApi, target, layer, point, query, opts) {
  const viz = target.viz || {};
  const pt = eeApi.Geometry.Point([point.lng, point.lat]);
  const { crs, scale, crsTransform } = queryInputs(query);
  const reduce = (img) => img.reduceRegion(eeApi.Reducer.first(), pt, scale, crs, crsTransform, true, 1e13, 4);
  const precision = query.precision;
  // target.unitProps {band: image property naming its units}: read in the
  // same request as the values.
  const props = target.unitProps || null;
  const propNames = props ? Object.keys(props).map((b) => props[b]) : [];
  const unitsOf = (got) => {
    if (!props || !got) return null;
    const out = {};
    Object.keys(props).forEach((b) => {
      if (got[props[b]] !== undefined && got[props[b]] !== null) out[b] = String(got[props[b]]);
    });
    return out;
  };
  if (target.type === "geeImage") {
    const img = eeApi.Image(target.item);
    if (props) {
      return evaluate(eeApi.Dictionary({ values: reduce(img), units: img.toDictionary(propNames) })).then((o) => [
        imageResult(layer, viz, o.values, point, precision, unitsOf(o.units)),
      ]);
    }
    return evaluate(reduce(img)).then((v) => [imageResult(layer, viz, v, point, precision)]);
  }
  if (target.type === "geeImageCollection") {
    const source = eeApi.ImageCollection(target.item);
    const first = eeApi.Image(source.first());
    const hasTime = first.propertyNames().contains("system:time_start");
    const fmt = viz.queryDateFormat || query.dateFormat || "YYYY-MM-dd";
    // Each image carries its own label, so ids and labels stay aligned even
    // when some images have no system:time_start.
    const c = eeApi
      .ImageCollection(eeApi.Algorithms.If(hasTime, source.sort("system:time_start"), source))
      .map((img) =>
        img.set(
          "dz_label",
          eeApi.Algorithms.If(img.propertyNames().contains("system:time_start"), img.date().format(fmt), img.get("system:index"))
        )
      );
    const full = eeApi.Dictionary({
      ids: c.aggregate_array("system:index"),
      labels: c.aggregate_array("dz_label"),
      hasTime,
      bands: first.bandNames(),
      values: reduce(c.toBands()),
      units: props ? first.toDictionary(propNames) : {},
    });
    // An empty collection is a no-data card (the original's makeQueryTable(null)), not a failure.
    const empty = eeApi.Dictionary({ ids: [], labels: [], hasTime: false, bands: [], values: {} });
    const out = eeApi.Dictionary(eeApi.Algorithms.If(source.size().gt(0), full, empty));
    return evaluate(out).then((o) => [seriesResult(layer, viz, o, point, precision, fmt, unitsOf(o.units))]);
  }
  if (VECTOR_TYPES.indexOf(target.type) > -1) {
    const item = target.item;
    const fc = typeof item.filterBounds === "function" ? item : eeApi.FeatureCollection([item]);
    const geoms = layer.legend && layer.legend.geoms;
    return evaluate(fc.filterBounds(pt.buffer(vectorQueryRadius(query, geoms, point.lat, opts.zoom)))).then((v) => {
      if (opts.onVectors) opts.onVectors(v);
      return tableResults(layer, v, point, precision);
    });
  }
  return Promise.resolve([]);
}

function errorResult(layer, point, err) {
  return {
    id: layer.id + "-e",
    layerId: layer.id,
    title: layer.name,
    meta: "Query failed",
    kind: "value",
    data: { point, bands: [], error: String((err && err.message) || err) },
    actions: ["copy"],
  };
}

// port of 4map-manager.js addSelectLayerToMap (viz.canQuery = false): select
// layers are never point queried; their selections feed Chart area.
export function queryableLayers(layers) {
  return layers.filter((l) => l.visible && l.queryable && l.kind !== "areaChartOnly" && l.kind !== "select");
}

// One click on a select layer becomes one selection (port of
// setupAreaLayerSelection: ids, names and fire years of every feature under
// the click, names joined by "-"; addSelectedFeaturesToMapWrapper's layer
// name). Features with no name are left out of names, as aggregate_array
// leaves them out; a click with no names selects nothing (nms.length > 0).
export function buildSelection(layer, viz, features) {
  if (!features || !features.length) return null;
  viz = viz || {};
  const ids = features.map((f) => String(f.id));
  const names = [];
  const years = [];
  let areaM2 = 0;
  let areaKnown = false;
  features.forEach((f) => {
    const props = f.properties || {};
    const prop = pickNameProperty(viz, props);
    const n = prop === null ? String(f.id) : props[prop];
    if (n !== undefined && n !== null) names.push(String(n));
    if (!isNil(viz.selectLayerIgnitionYearProperty)) {
      const y = props[viz.selectLayerIgnitionYearProperty];
      if (y !== undefined && y !== null) years.push(y);
    }
    const a = Number(props.dz_area_m2);
    if (Number.isFinite(a)) {
      areaM2 += a;
      areaKnown = true;
    }
  });
  if (!names.length) return null;
  return {
    key: layer.id + ":" + ids.slice().sort().join("|"),
    layerId: layer.id,
    layerName: layer.name,
    ids,
    names,
    years: isNil(viz.selectLayerIgnitionYearProperty) ? null : years,
    name: names.join("-"),
    label: "Selected " + layer.name + " " + names.join("-").replace(/&/g, "-"),
    areaM2: areaKnown ? areaM2 : null,
  };
}

// Query every visible queryable layer at latLng. All requests are issued at
// once; each answer goes to opts.onResult as it arrives, unless opts.token
// is no longer current, in which case it is dropped (and the promise
// resolves to []). Resolves to the results in layer order.
export async function queryPoint(engine, layers, latLng, query, opts = {}) {
  const eeApi = opts.ee || globalThis.ee;
  const point = toPoint(latLng);
  const isCurrent = () => !opts.token || opts.token.isCurrent();
  const targets = queryableLayers(layers);
  const byLayer = new Map();
  await Promise.all(
    targets.map(async (layer) => {
      let rs;
      try {
        const target = await engine.layers.queryTarget(layer.id);
        if (!target) return;
        rs = await queryOne(eeApi, target, layer, point, query, {
          zoom: opts.zoom,
          onVectors: (v) => isCurrent() && opts.onVectors && opts.onVectors(v),
        });
      } catch (e) {
        rs = [errorResult(layer, point, e)];
      }
      if (!isCurrent()) return;
      byLayer.set(layer.id, rs);
      rs.forEach((r) => opts.onResult && opts.onResult(r));
    })
  );
  if (!isCurrent()) return [];
  const all = [];
  targets.forEach((l) => byLayer.has(l.id) && all.push(...byLayer.get(l.id)));
  return all;
}

// Pixel size in meters at a latitude and zoom: the simplify tolerance for drawn selections.
const metersPerPixel = (lat, zoom) => (156543.03392 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, zoom);

// The map side of the Query tool and of select layers. opts: isPhone(),
// colors() -> {pin, pinEdge, selection}, notify(msg).
export function createQueryTool(engine, store, opts = {}) {
  const g = opts.google || window.google.maps;
  const eeApi = opts.ee || window.ee;
  const gmap = engine.gmap;
  const tokens = tokenSource();
  const colors = () => (opts.colors ? opts.colors() : { pin: "#ff834c", pinEdge: "#fff", selection: "#ff834c" });
  const notify = opts.notify || (() => {});
  const isPhone = opts.isPhone || (() => false);

  let pin = null;
  let box = null;
  let lastPoint = null;
  // port of 4map-manager.js queryGeoJSON (yellow outline of queried features)
  const queried = new g.Data({ map: gmap });
  queried.setStyle({ strokeColor: DEFAULT_BOX_COLOR, fillOpacity: 0, strokeWeight: 2, clickable: false, zIndex: 3000 });
  const info = new g.InfoWindow({ maxWidth: 350 });

  function clearMarks() {
    if (pin) pin.setMap(null);
    if (box) box.setMap(null);
    pin = box = null;
    queried.forEach((f) => queried.remove(f));
    info.close();
  }

  // port of addClickMarker: the query box is the point buffered by plotRadius, bounded.
  function drawMarks(point, query) {
    clearMarks();
    const c = colors();
    pin = new g.Marker({
      position: { lat: point.lat, lng: point.lng },
      map: gmap,
      clickable: false,
      zIndex: 4000,
      icon: { path: g.SymbolPath.CIRCLE, scale: 7, fillColor: c.pin, fillOpacity: 1, strokeColor: c.pinEdge, strokeWeight: 3 },
    });
    const r = plotRadius(query);
    const dLat = r / 111320;
    const dLng = r / (111320 * Math.cos((point.lat * Math.PI) / 180));
    box = new g.Rectangle({
      map: gmap,
      clickable: false,
      bounds: { north: point.lat + dLat, south: point.lat - dLat, east: point.lng + dLng, west: point.lng - dLng },
      strokeColor: query.boxColor || DEFAULT_BOX_COLOR,
      strokeWeight: 2,
      fillOpacity: 0,
      zIndex: 3500,
    });
  }

  function orderedLayers(s) {
    const byId = new Map(s.layers.map((l) => [l.id, l]));
    const listed = s.order.filter((id) => byId.has(id)).map((id) => byId.get(id));
    return listed.concat(s.layers.filter((l) => s.order.indexOf(l.id) === -1));
  }

  async function run(latLng) {
    const token = tokens();
    const point = toPoint(latLng);
    lastPoint = point;
    const s = store.get();
    drawMarks(point, s.query);
    const layers = orderedLayers(s);
    const rank = new Map(layers.map((l, i) => [l.id, i]));
    store.set({ results: [], where: formatPoint(point), querying: true }, "query-start");
    if (!queryableLayers(layers).length) {
      store.set({ querying: false }, "query-done");
      // port of getQueryImages "No Layers to Query!"
      notify("No visible layers to query. Turn on any layers you would like to query.");
      return [];
    }
    const results = await queryPoint(engine, layers, point, s.query, {
      ee: eeApi,
      token,
      zoom: gmap.getZoom(),
      onVectors: (v) => queried.addGeoJson(v),
      onResult: (r) =>
        store.update((st) => {
          const next = st.results.concat([r]);
          next.sort((a, b) => rank.get(a.layerId) - rank.get(b.layerId) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
          return { ...st, results: next };
        }, "query-result"),
    });
    if (token.isCurrent()) store.set({ querying: false }, "query-done");
    return results;
  }

  // ---- select layers ----
  // port of setupAreaLayerSelection and addSelectedFeaturesToMapWrapper:
  // a click adds the features of each visible select layer under it as one
  // selection, once (notSelected compares the selected ids).
  const selected = new g.Data({ map: gmap });
  const restyle = () =>
    selected.setStyle({ strokeColor: colors().selection, strokeWeight: 3, fillColor: colors().selection, fillOpacity: 0.15, clickable: false, zIndex: 3200 });
  restyle();
  const drawn = new Map(); // key -> google.maps.Data.Feature[]

  async function selectAt(latLng) {
    const point = toPoint(latLng);
    const s = store.get();
    const layers = s.layers.filter((l) => l.kind === "select" && l.visible);
    const tol = metersPerPixel(point.lat, gmap.getZoom() || 10);
    await Promise.all(
      layers.map(async (layer) => {
        try {
          const t = await engine.layers.queryTarget(layer.id);
          if (!t) return;
          const fc = eeApi
            .FeatureCollection(t.item)
            .filterBounds(eeApi.Geometry.Point([point.lng, point.lat]))
            .map((f) => eeApi.Feature(f).simplify(tol).set("dz_area_m2", eeApi.Feature(f).geometry().area(1000)));
          const v = await evaluate(fc);
          addSelection(layer, t.viz, v.features || []);
        } catch (e) {
          notify("Selecting from " + layer.name + " failed: " + (e && e.message));
        }
      })
    );
  }

  function addSelection(layer, viz, features) {
    const sel = buildSelection(layer, viz, features);
    if (!sel || store.get().selections.some((x) => x.key === sel.key)) return;
    if (!drawn.has(sel.key)) {
      const feats = [];
      features.forEach((f) => feats.push(...selected.addGeoJson({ type: "Feature", geometry: f.geometry, properties: {} })));
      drawn.set(sel.key, feats);
    }
    store.update((st) => ({ ...st, selections: st.selections.concat([sel]) }), "select-feature");
  }

  store.on("change:selections", (sel) => {
    const keep = new Set(sel.map((x) => x.key));
    for (const [key, feats] of drawn) {
      if (!keep.has(key)) {
        feats.forEach((f) => selected.remove(f));
        drawn.delete(key);
      }
    }
  });

  // The selected features as one ee.FeatureCollection (Chart area's Select source).
  async function selectionCollection() {
    const sel = store.get().selections;
    const byLayer = new Map();
    sel.forEach((x) => byLayer.set(x.layerId, (byLayer.get(x.layerId) || []).concat(x.ids)));
    const parts = [];
    for (const [layerId, ids] of byLayer) {
      const t = await engine.layers.queryTarget(layerId);
      if (t) parts.push(eeApi.FeatureCollection(t.item).filter(eeApi.Filter.inList("system:index", ids)));
    }
    return eeApi.FeatureCollection(parts).flatten();
  }

  // ---- map events ----
  const picking = () => (engine.isPicking ? engine.isPicking() : false);
  // port of setupAreaLayerSelection: only the dedicated select mode selects
  // ("Area Tools-Select an Area on map" is Chart area with the Select source).
  const selecting = (s) => s.tool === "chart" && s.areaFrom === "select";
  gmap.addListener("dblclick", (ev) => {
    if (!ev.latLng || picking() || isPhone()) return;
    if (store.get().tool === "query") run(ev.latLng);
  });
  gmap.addListener("click", (ev) => {
    if (!ev.latLng || picking()) return;
    const s = store.get();
    if (selecting(s) && s.layers.some((l) => l.kind === "select" && l.visible)) selectAt(ev.latLng);
    // Phones: a tap queries (a double tap zooms on touch screens).
    if (isPhone() && s.tool === "query") run(ev.latLng);
  });

  store.on("change:tool", (tool) => {
    if (tool === "query") return;
    tokens(); // whatever is in flight is now stale
    clearMarks();
    if (store.get().querying) store.set({ querying: false }, "query-cancel");
  });

  return {
    run,
    selectAt,
    selectionCollection,
    restyle,
    // Phones in infoWindow mode: the UI hands over the built content.
    openInfo(contentEl) {
      if (!lastPoint) return;
      info.setContent(contentEl);
      info.setPosition({ lat: lastPoint.lat, lng: lastPoint.lng });
      if (!info.getMap()) info.open({ map: gmap });
    },
    closeInfo: () => info.close(),
    marks: () => ({ pin: !!(pin && pin.getMap()), box: !!(box && box.getMap()) }),
  };
}
