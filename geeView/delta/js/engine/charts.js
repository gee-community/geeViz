// Earth Engine area charting for Delta, ported from geeViz/outputLib/charts.py
// so the viewer's numbers are charts.py's numbers.
//
// Method from charts.py: an ImageCollection is stacked into one multi-band
// image (bands "label----band") and reduced once with reduceRegion
// (bestEffort, maxPixels 1e13, tileScale 4, crsTransform winning over
// scale); thematic layers reduce with frequencyHistogram, continuous ones
// with mean. Inputs from the viewer: the layer's own crs/scale/transform,
// else EPSG:5070 on the snapped 30 m grid, coarsened when zoomed out as
// lcms-viewer area-charting.js autoSetScale does.
//
// Two things are reproduced on purpose so results match to the digit:
// - Earth Engine returns dictionaries with keys sorted as strings ("1",
//   "10", "2"). charts.py iterates them in that order, while a JavaScript
//   object iterates integer-like keys numerically. Every histogram here is
//   read in sorted-string order (column order and summation order).
// - Python's round() (half-even on the exact binary value) and sum()
//   (Neumaier-compensated for floats) are ported as pyRound and pySum.
//
// One deliberate difference: a label with no histogram at all (missing,
// null or empty) is a gap (null) for that band's columns, where charts.py's
// fillna(0) would chart it as zero. A class absent from a label that has
// data is 0, as in charts.py.
//
// Earth Engine calls use evaluate() only and return Promises. This module
// never touches the DOM.
import { evaluateAsync, getObjType } from "./viz.js";

const EE = () => globalThis.ee;

// port of charts.py SPLIT_STR
export const SPLIT_STR = "----";

// port of charts.py AREA_FORMAT_DICT
export const AREA_FORMAT_DICT = {
  Percentage: { mult: null, label: "% Area", places: 2, scale: 30 },
  Hectares: { mult: 0.09, label: "ha", places: 0, scale: 30 },
  Acres: { mult: 0.222395, label: "Acres", places: 0, scale: 30 },
  Pixels: { mult: 1.0, label: "Pixels", places: 0, scale: 30 },
};

// port of lcms-viewer 1variables.js crs and transform (the viewer's defaults)
export const DEFAULT_CRS = "EPSG:5070";
export const DEFAULT_TRANSFORM = [30, 0, -2361915.0, 0, -30, 3177735.0];

// Earth Engine's dictionary key order (Java String order is UTF-16 code
// unit order, which is also Array.prototype.sort's default).
const eeKeys = (obj) => Object.keys(obj).sort();

// Python round(x, n): correctly rounded, ties to even, decided on the exact
// decimal expansion of the double (toFixed(100) is exact for the values
// that can be ties).
export function pyRound(x, n = 0) {
  if (typeof x !== "number" || !Number.isFinite(x) || Number.isInteger(x) || Math.abs(x) >= 1e21) return x;
  const neg = x < 0;
  const s = Math.abs(x).toFixed(100);
  const dot = s.indexOf(".");
  const frac = s.slice(dot + 1);
  const digits = (s.slice(0, dot) + frac.slice(0, n)).split("").map(Number);
  const rest = frac.slice(n);
  const first = rest.charCodeAt(0) - 48;
  const tail = /[1-9]/.test(rest.slice(1));
  const last = digits[digits.length - 1];
  const up = first > 5 || (first === 5 && (tail || last % 2 === 1));
  if (up) {
    let i = digits.length - 1;
    while (i >= 0 && digits[i] === 9) digits[i--] = 0;
    if (i < 0) digits.unshift(1);
    else digits[i] += 1;
  }
  const str = digits.join("");
  const cut = str.length - n;
  const v = Number(n ? str.slice(0, cut) + "." + str.slice(cut) : str);
  return neg ? -v : v;
}

// C long on the Windows build of CPython that charts.py's fixtures run on.
const LONG_MAX = 2147483647;
const isPyInt = (v) => Number.isInteger(v) && Math.abs(v) <= LONG_MAX;

// Python sum(values) (CPython 3.12+ builtin_sum): exact integer adds until
// the first float, then Neumaier-compensated float adds, with plain adds for
// ints that fit a C long. JSON integers are Python ints.
export function pySum(values) {
  const n = values.length;
  let i = 0;
  let iSum = 0;
  while (i < n && isPyInt(values[i]) && Math.abs(iSum + values[i]) <= LONG_MAX) iSum += values[i++];
  if (i === n) return iSum;
  if (isPyInt(values[i]) || Number.isInteger(values[i])) {
    // int overflowed a C long: CPython continues with plain adds
    let r = iSum;
    for (; i < n; i++) r += values[i];
    return r;
  }
  let f = iSum + values[i++];
  let c = 0;
  for (; i < n; i++) {
    const x = values[i];
    if (Number.isInteger(x)) {
      if (isPyInt(x)) {
        f += x;
        continue;
      }
      if (c && Number.isFinite(c)) f += c;
      for (; i < n; i++) f += values[i];
      return f;
    }
    const t = f + x;
    if (Math.abs(f) >= Math.abs(x)) c += f - t + x;
    else c += x - t + f;
    f = t;
  }
  if (c && Number.isFinite(c)) f += c;
  return f;
}

// port of charts.py truncate_class_name (lengths in code points, as Python's)
export function truncateClassName(name, maxLength = 30) {
  if (!maxLength || typeof name !== "string") return name;
  const cp = Array.from(name);
  if (cp.length <= maxLength) return name;
  const ellipsis = "...";
  const budget = maxLength - ellipsis.length;
  if (budget <= 0) return cp.slice(0, maxLength).join("");
  const endLen = Math.max(Math.floor(budget / 3), 1);
  const startLen = budget - endLen;
  return cp.slice(0, startLen).join("") + ellipsis + cp.slice(cp.length - endLen).join("");
}

// port of charts.py truncate_class_names
export function truncateClassNames(names, maxLength = 30) {
  if (!maxLength || !names || !names.length) return names;
  return names.map((n) => truncateClassName(n, maxLength));
}

const PY_INT_RE = /^[+-]?\d+(_\d+)*$/;
const PY_FLOAT_RE = /^[+-]?(\d+(_\d+)*\.?(\d+(_\d+)*)?|\.\d+(_\d+)*)([eE][+-]?\d+)?$/;

// Python int(p) for the values a class property holds; undefined when int() would raise.
function pyInt(p) {
  if (typeof p === "number") return Number.isFinite(p) ? Math.trunc(p) : undefined;
  if (typeof p === "boolean") return p ? 1 : 0;
  if (typeof p !== "string") return undefined;
  const s = p.trim();
  if (PY_INT_RE.test(s)) return parseInt(s.replace(/_/g, ""), 10);
  if (PY_FLOAT_RE.test(s)) {
    const f = Number(s.replace(/_/g, ""));
    return Number.isFinite(f) ? Math.trunc(f) : undefined;
  }
  return undefined;
}

// port of charts.py _normalize_class_prop
export function normalizeClassProp(value, asInt = false) {
  if (value === undefined || value === null || value === "") return [];
  let parts;
  if (typeof value === "string") parts = value.split(",").map((p) => p.trim()).filter((p) => p);
  else if (Array.isArray(value)) parts = value.slice();
  else return [value];
  if (!asInt) return parts;
  return parts.map((p) => {
    const v = pyInt(p);
    return v === undefined ? p : v;
  });
}

const has = (o, k) => o !== null && o !== undefined && Object.prototype.hasOwnProperty.call(o, k);

// The pure half of charts.py get_obj_info: class metadata from the first
// image's properties.
export function objInfoFromProps(props, bandNames, objType, size, maxClassLabelLength = 30) {
  const classInfo = {};
  let isThematic = false;
  for (const bn of bandNames) {
    const valuesKey = `${bn}_class_values`;
    const namesKey = `${bn}_class_names`;
    const paletteKey = `${bn}_class_palette`;
    if (has(props, valuesKey) && has(props, namesKey)) {
      isThematic = true;
      classInfo[bn] = {
        classValues: normalizeClassProp(props[valuesKey], true),
        classNames: truncateClassNames(normalizeClassProp(props[namesKey]), maxClassLabelLength),
        classPalette: normalizeClassProp(has(props, paletteKey) ? props[paletteKey] : []),
      };
    }
  }
  return { objType, bandNames, isThematic, classInfo, size };
}

const coerceBandNames = (bandNames) =>
  typeof bandNames === "string" ? bandNames.split(",").map((b) => b.trim()) : bandNames;

// port of charts.py get_obj_info: one evaluate() for size, band names and
// the first image's properties (charts.py makes up to three getInfo calls).
export async function getObjInfo(eeObj, bandNames = null, maxClassLabelLength = 30) {
  const ee = EE();
  bandNames = coerceBandNames(bandNames);
  const objType = getObjType(eeObj, ee);
  const isCollection = objType === "ImageCollection";
  const first = isCollection ? ee.Image(eeObj.first()) : ee.Image(eeObj);
  const req = { props: first.toDictionary() };
  if (isCollection) req.size = eeObj.size();
  if (bandNames === null || bandNames === undefined) req.bandNames = first.bandNames();
  const got = await evaluateAsync(ee.Dictionary(req));
  return objInfoFromProps(
    got.props || {},
    bandNames ?? got.bandNames,
    isCollection ? "ImageCollection" : "Image",
    isCollection ? got.size : 1,
    maxClassLabelLength
  );
}

// port of charts.py prepare_for_reduction's expected_names loop: label-major, band-minor
export function stackBandNames(labels, bands) {
  const out = [];
  for (const x of labels) for (const bn of bands) out.push(`${x}${SPLIT_STR}${bn}`);
  return out;
}

// port of charts.py prepare_for_reduction. One evaluate() for the labels
// and their counts (charts.py makes two getInfo calls).
export async function prepareForReduction(eeObj, objInfo, xAxisProperty = "system:time_start", dateFormat = "YYYY") {
  const ee = EE();
  const bandNames = objInfo.bandNames;
  if (objInfo.objType !== "ImageCollection") {
    return { image: ee.Image(eeObj).select(bandNames), bandNames, labels: [] };
  }
  let ic = eeObj;
  // date_format must be non-empty, and colons and spaces become "_": band
  // names reject ":" (charts.py's reason, kept verbatim in behavior).
  const df = dateFormat || "YYYY";
  let prop = xAxisProperty;
  if (["year", "date", "system:time_start"].includes(prop)) {
    ic = ic.map((img) => img.set("year", img.date().format(df).replace("[: ]", "_", "g")));
    if (prop === "date" || prop === "system:time_start") prop = "year";
  }
  // keys and values as lists keep Earth Engine's key order
  const hist = ee.Dictionary(ic.aggregate_histogram(prop));
  const [labels, counts] = await evaluateAsync(ee.List([hist.keys(), hist.values()]));

  ic = ic.select(bandNames);
  if (counts.some((v) => v > 1)) {
    // mosaic per label when a label has several images
    const p = prop;
    const src = ic;
    ic = ee.ImageCollection(
      ee.List(labels).map((label) => {
        label = ee.String(label);
        const filtered = src.filter(ee.Filter.eq(p, label));
        return ee.Image(filtered.mosaic().copyProperties(filtered.first())).set(p, label);
      })
    );
  }
  const p = prop;
  ic = ic.map((img) => {
    const label = ee.String(img.get(p));
    const newNames = ee.List(bandNames).map((bn) => label.cat(SPLIT_STR).cat(ee.String(bn)));
    return img.select(bandNames).rename(newNames);
  });
  const expected = stackBandNames(labels, bandNames);
  // toBands() prefixes system:index; rename to the names already known
  const image = ic.toBands().rename(expected);
  return { image, bandNames: expected, labels };
}

// port of charts.py reduce_region (evaluate, not getInfo)
export function reduceArea(image, geometry, reducer, { scale = 30, crs = null, transform = null, tileScale = 4 } = {}) {
  const ee = EE();
  if (transform !== null && transform !== undefined && scale !== null && scale !== undefined) scale = null;
  if (geometry instanceof ee.Feature) geometry = geometry.geometry();
  else if (geometry instanceof ee.FeatureCollection) geometry = geometry.geometry();
  const args = { reducer, geometry, bestEffort: true, maxPixels: 1e13, tileScale };
  if (scale !== null && scale !== undefined) args.scale = scale;
  if (crs) args.crs = crs;
  if (transform) args.crsTransform = transform;
  return evaluateAsync(ee.Image(image).reduceRegion(args));
}

// port of charts.py convert step in parse_thematic_results (and
// prepare_sankey_data): a pixel count in the chosen unit. Percentage needs
// the area's pixel total.
export function convertPixelArea(count, scale, areaFormat, pixelTotal = 1) {
  if (areaFormat === "Percentage") return pyRound((count / pixelTotal) * 100, 2);
  if (areaFormat === "Pixels") return count;
  const scaleMult = (scale / AREA_FORMAT_DICT.Hectares.scale) ** 2;
  const f = AREA_FORMAT_DICT[areaFormat];
  return pyRound(count * (f.mult * scaleMult), f.places);
}

const emptyHist = (h) => h === undefined || h === null || typeof h !== "object" || Object.keys(h).length === 0;
// the unmask sentinel's histogram keys (charts.py strips "0" and "0.0")
const isSentinelKey = (k) => ["0", "0.0"].includes(String(k).trim());

// port of charts.py parse_thematic_results. Returns {columns, rows}: rows
// are {x, values} with values aligned to columns (x is null for an Image).
// With sentinel true (images were unmask(0)ed), a histogram holding only
// the sentinel class is a band masked over the whole area: a gap.
export function parseThematicResults(raw, objInfo, labels, areaFormat = "Percentage", scale = 30, sentinel = false) {
  const { classInfo, bandNames } = objInfo;
  const multi = bandNames.length > 1;
  const lookups = {};
  for (const bn of bandNames) {
    const info = classInfo[bn] || {};
    const vals = info.classValues || [];
    const names = info.classNames || [];
    const m = new Map();
    for (let i = 0; i < Math.min(vals.length, names.length); i++) m.set(String(vals[i]), names[i]);
    lookups[bn] = m;
  }
  const colBand = new Map(); // column -> band, in first-appearance order
  const rows = [];
  const keyed = labels && labels.length ? labels.map((x) => [x, (bn) => `${x}${SPLIT_STR}${bn}`]) : [[null, (bn) => bn]];
  for (const [x, keyOf] of keyed) {
    const cells = new Map();
    const gaps = new Set();
    for (const bn of bandNames) {
      const hist = raw ? raw[keyOf(bn)] : undefined;
      if (emptyHist(hist) || (sentinel && Object.keys(hist).every(isSentinelKey))) {
        gaps.add(bn);
        continue;
      }
      const keys = eeKeys(hist);
      const pixelTotal = pySum(keys.map((k) => hist[k])) || 1;
      for (const strVal of keys) {
        const name = lookups[bn].has(strVal) ? lookups[bn].get(strVal) : strVal;
        const col = multi ? `${bn}${SPLIT_STR}${name}` : name;
        if (!colBand.has(col)) colBand.set(col, bn);
        cells.set(col, convertPixelArea(hist[strVal], scale, areaFormat, pixelTotal));
      }
    }
    rows.push({ x, cells, gaps });
  }
  const columns = [...colBand.keys()];
  return {
    columns,
    rows: rows.map(({ x, cells, gaps }) => ({
      x,
      values: columns.map((c) => (cells.has(c) ? cells.get(c) : gaps.has(colBand.get(c)) ? null : 0)),
    })),
  };
}

// port of charts.py _collect_band_outputs
export function collectBandOutputs(raw, baseKey) {
  const out = new Map();
  if (has(raw, baseKey)) out.set("", raw[baseKey]);
  const prefix = baseKey + "_";
  for (const k of eeKeys(raw || {})) if (k.startsWith(prefix)) out.set(k.slice(prefix.length), raw[k]);
  return out;
}

// port of charts.py parse_continuous_results. Missing values are null.
export function parseContinuousResults(raw, objInfo, labels) {
  const { bandNames } = objInfo;
  const columns = [];
  const seen = new Set();
  const rows = [];
  const keyed = labels && labels.length ? labels.map((x) => [x, (bn) => `${x}${SPLIT_STR}${bn}`]) : [[null, (bn) => bn]];
  for (const [x, keyOf] of keyed) {
    const cells = new Map();
    for (const bn of bandNames) {
      const outputs = collectBandOutputs(raw, keyOf(bn));
      const put = (col, v) => {
        if (!seen.has(col)) {
          seen.add(col);
          columns.push(col);
        }
        cells.set(col, v);
      };
      if (outputs.size === 1 && outputs.has("")) put(bn, outputs.get(""));
      else for (const [suffix, v] of outputs) put(suffix ? `${bn}_${suffix}` : bn, v);
    }
    rows.push({ x, cells });
  }
  return {
    columns,
    rows: rows.map(({ x, cells }) => ({
      x,
      values: columns.map((c) => {
        const v = cells.get(c);
        return v === undefined || v === null || Number.isNaN(v) ? null : v;
      }),
    })),
  };
}

// port of charts.py zonal_stats _strip_sentinel_cols: drop the unmask
// sentinel class (0) after it has counted toward the area total
export function stripSentinelColumns(table) {
  const keep = table.columns.map((c) => !isSentinelKey(c));
  return {
    ...table,
    columns: table.columns.filter((_, i) => keep[i]),
    rows: table.rows.map((r) => ({ ...r, values: r.values.filter((_, i) => keep[i]) })),
  };
}

// The parse step of charts.py zonal_stats (single region): thematic
// results with the sentinel class dropped after it has counted toward each
// year's total, or continuous results. zonalStats parses only through this.
export function parseReduction(raw, objInfo, labels, { isHistogram, sentinel = false, areaFormat = "Percentage", scale = 30 }) {
  if (!isHistogram) return parseContinuousResults(raw, objInfo, labels);
  const table = parseThematicResults(raw, objInfo, labels, areaFormat, scale, sentinel);
  return sentinel ? stripSentinelColumns(table) : table;
}

// The Earth Engine name of a reducer, read from the client object (no
// server call; charts.py asks the server with reducer.getInfo()).
export function reducerName(reducer) {
  try {
    const sig = reducer.func && reducer.func.getSignature && reducer.func.getSignature();
    if (sig && sig.name) return sig.name;
  } catch (e) {
    /* fall through */
  }
  try {
    return JSON.stringify(EE().Serializer.encode(reducer));
  } catch (e) {
    return "";
  }
}

// port of charts.py zonal_stats (single region path), as summarize_and_chart
// calls it: filterBounds, thematic -> frequencyHistogram else mean, masked
// pixels counted through an unmask(0) sentinel, one stacked reduceRegion.
// The object info is read once (charts.py re-reads it after unmasking;
// unmask keeps band names and properties, so the result is the same).
// Resolves to {columns, rows, objInfo, labels, raw, isHistogram}; raw is
// kept so a unit change can re-parse without Earth Engine.
// Rows are the labels of the images that intersect the area (charts.py
// filterBounds before reading labels): a label with no image over the area
// has no row. A label whose image is masked over the whole area is a gap.
export async function zonalStats(eeObj, geometry, opts = {}) {
  const ee = EE();
  const {
    reducer: reducerIn = null,
    scale = 30,
    crs = null,
    transform = null,
    tileScale = 4,
    areaFormat = "Percentage",
    xAxisProperty = "system:time_start",
    dateFormat = "YYYY",
    includeMaskedArea = true,
    maxClassLabelLength = 30,
  } = opts;
  const bandNames = coerceBandNames(opts.bandNames ?? null);
  const isCollection = getObjType(eeObj, ee) === "ImageCollection";
  if (isCollection) eeObj = eeObj.filterBounds(geometry);
  const objInfo = await getObjInfo(eeObj, bandNames, maxClassLabelLength);
  const reducer = reducerIn || (objInfo.isThematic ? ee.Reducer.frequencyHistogram() : ee.Reducer.mean());
  const isHistogram = reducerName(reducer).includes("frequencyHistogram");
  const sentinel = includeMaskedArea && isHistogram;
  if (sentinel) {
    eeObj = isCollection
      ? eeObj.map((img) => img.unmask(0).copyProperties(img, ["system:time_start"]))
      : ee.Image(eeObj).unmask(0);
  }
  const prep = await prepareForReduction(eeObj, objInfo, xAxisProperty, dateFormat);
  const raw = await reduceArea(prep.image, geometry, reducer, { scale, crs, transform, tileScale });
  const table = parseReduction(raw, objInfo, prep.labels, { isHistogram, sentinel, areaFormat, scale });
  return { ...table, objInfo, labels: prep.labels, stackBandNames: prep.bandNames, raw, isHistogram };
}

// port of lcms-viewer area-charting.js autoSetScale: 2x coarser per zoom
// level below minZoomSpecifiedScale, at most maxAutoScale. With a
// transform, the transform's pixel size is scaled and scale becomes null.
// The transform passed in is not modified.
export function autoScale(zoom, baseScale, minZoomSpecifiedScale = 11, maxAutoScale = 2 ** 6, transform = null) {
  minZoomSpecifiedScale = minZoomSpecifiedScale || 11;
  let scaleT = baseScale || transform[0];
  let scaleMult = 1 / ((1 << zoom) / (1 << minZoomSpecifiedScale));
  scaleMult = scaleMult < 1 ? 1 : scaleMult;
  scaleMult = scaleMult > maxAutoScale ? maxAutoScale : scaleMult;
  scaleT = scaleT * scaleMult;
  const nominalScale = scaleT;
  let t = null;
  if (transform !== undefined && transform !== null) {
    t = transform.slice();
    t[0] = scaleT;
    t[4] = -scaleT;
    scaleT = null;
  }
  return { scale: scaleT, transform: t, scaleMult, nominalScale };
}

// port of lcms-viewer area-charting.js (the chart object's scale, transform
// and crs setup, then autoSetScale at the current zoom): the inputs a
// layer's area chart reduces with.
export function areaChartInputs(params = {}, zoom) {
  let scale = params.scale !== undefined ? params.scale : null;
  const transform = params.transform !== undefined ? params.transform : DEFAULT_TRANSFORM;
  const crs = params.crs || DEFAULT_CRS;
  // only when the layer gives both does the transform win (it snaps); a
  // scale alone sizes the default grid in autoSetScale (scaleT || transformT[0])
  const given = (v) => v !== undefined && v !== null;
  if (given(params.scale) && given(params.transform)) scale = null;
  const r = autoScale(zoom, scale, params.minZoomSpecifiedScale || 11, 2 ** 6, transform);
  return { crs, scale: r.scale, transform: r.transform, scaleMult: r.scaleMult, nominalScale: r.nominalScale };
}
