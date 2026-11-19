// Class-transition (Sankey) data for Delta, ported from charts.py
// prepare_sankey_data: the mode of each period, one transition band per
// consecutive period pair encoding from*10000 + 9900 + to, every pair
// stacked and reduced in a single frequencyHistogram reduceRegion. Flows
// under the minimum percentage leave the links but stay in the matrix.
//
// The minimum defaults to the original viewer's sankeyMinPercentage, 0.5
// (lcms-viewer area-charting.js); 0.2 is charts.py's own default.
//
// Histograms are read in Earth Engine's sorted-string key order, as
// charts.py reads them (see charts.js). Never touches the DOM.
import { convertPixelArea, getObjInfo, pySum, reduceArea } from "./charts.js";

const EE = () => globalThis.ee;

// port of lcms-viewer area-charting.js sankeyMinPercentage default
export const SANKEY_MIN_PERCENTAGE = 0.5;

// port of charts.py _format_period
export function formatPeriod(period) {
  if (Array.isArray(period) && period.length === 2) {
    if (period[0] === period[1]) return String(period[0]);
    return `${period[0]}-${period[1]}`;
  }
  return String(period);
}

// port of charts.py _ensure_hex_color
export function ensureHexColor(color) {
  if (color === null || color === undefined) return null;
  color = String(color);
  return color.startsWith("#") ? color : "#" + color;
}

// port of charts.py prepare_sankey_data band naming: "{p1}---{p2}" per consecutive pair
export function transitionBandNames(periods) {
  const out = [];
  for (let i = 0; i < periods.length - 1; i++) out.push(`${formatPeriod(periods[i])}---${formatPeriod(periods[i + 1])}`);
  return out;
}

const bounds = (p) => (Array.isArray(p) ? [p[0], p[p.length - 1]] : [p, p]);
const floorDiv = (a, b) => Math.floor(a / b);
const pyMod = (a, b) => ((a % b) + b) % b;

// charts.py picks class_info[band], else the first band's info
function bandInfo(classInfo, band) {
  if (!classInfo) return {};
  if (classInfo.classValues) return classInfo;
  if (classInfo[band]) return classInfo[band];
  const first = Object.keys(classInfo)[0];
  return first !== undefined ? classInfo[first] : {};
}

// port of charts.py prepare_sankey_data (the parse half). hist is the raw
// reduceRegion dict keyed by transition band name; classInfo is the band's
// {classValues, classNames, classPalette}. Returns {links, matrix}: links
// carry charts.py's sankey_df columns; matrix maps "{p1} → {p2}" to
// {index, columns, values}.
export function buildSankeyFromHistogram(hist, classInfo, periods, areaFormat = "Percentage", scale = 30, minPercentage = SANKEY_MIN_PERCENTAGE) {
  const info = bandInfo(classInfo);
  const classValues = info.classValues || [];
  const classNames = info.classNames || [];
  const classPalette = info.classPalette || [];
  const valueToIdx = new Map();
  classValues.forEach((v, i) => valueToIdx.set(Number(v), i));
  const idxToName = new Map(classNames.map((n, i) => [i, n]));
  const idxToColor = new Map(classPalette.map((c, i) => [i, ensureHexColor(c)]));
  const numClasses = classValues.length;

  const links = [];
  const matrix = {};
  const names = transitionBandNames(periods);
  names.forEach((tBn, ti) => {
    let h = hist ? hist[tBn] : undefined;
    if (h === undefined || h === null) h = {};
    const keys = Object.keys(h).sort();
    const pixelTotal = pySum(keys.map((k) => h[k])) || 1;
    const p1Label = formatPeriod(periods[ti]);
    const p2Label = formatPeriod(periods[ti + 1]);
    const offset1 = ti * numClasses;
    const offset2 = (ti + 1) * numClasses;
    const countLookup = new Map();
    for (const encodedStr of keys) {
      const count = h[encodedStr];
      const encoded = Math.trunc(Number(encodedStr));
      const fromClass = floorDiv(encoded, 10000);
      const toClass = pyMod(encoded, 10000) - 9900;
      const fromIdx = valueToIdx.get(fromClass);
      const toIdx = valueToIdx.get(toClass);
      if (fromIdx === undefined || toIdx === undefined) continue;
      const pct = (count / pixelTotal) * 100;
      const displayVal = convertPixelArea(count, scale, areaFormat, pixelTotal);
      countLookup.set(`${fromIdx},${toIdx}`, displayVal);
      if (pct >= minPercentage) {
        links.push({
          source: fromIdx + offset1,
          target: toIdx + offset2,
          value: displayVal,
          source_name: `${p1Label} ${idxToName.has(fromIdx) ? idxToName.get(fromIdx) : String(fromClass)}`,
          target_name: `${p2Label} ${idxToName.has(toIdx) ? idxToName.get(toIdx) : String(toClass)}`,
          source_color: idxToColor.has(fromIdx) ? idxToColor.get(fromIdx) : "#888888",
          target_color: idxToColor.has(toIdx) ? idxToColor.get(toIdx) : "#888888",
          period: `${p1Label} -> ${p2Label}`,
        });
      }
    }
    // rows are "from" class names, columns "to" class names (a repeated
    // name is one column holding the last value, as in the charts.py dict)
    const index = [];
    const rows = [];
    for (let fi = 0; fi < numClasses; fi++) {
      index.push(idxToName.has(fi) ? idxToName.get(fi) : String(fi));
      const row = new Map();
      for (let tj = 0; tj < numClasses; tj++) {
        const col = idxToName.has(tj) ? idxToName.get(tj) : String(tj);
        const k = `${fi},${tj}`;
        row.set(col, countLookup.has(k) ? countLookup.get(k) : 0);
      }
      rows.push(row);
    }
    if (rows.length) {
      const columns = [...rows[0].keys()];
      matrix[`${p1Label} → ${p2Label}`] = { index, columns, values: rows.map((r) => columns.map((c) => r.get(c))) };
    }
  });
  return { links, matrix };
}

// port of charts.py prepare_sankey_data: every period pair is stacked into
// one image and reduced once. Resolves to {links, matrix, raw}.
export async function prepareSankeyData(ic, band, periods, classInfo, geometry, opts = {}) {
  const ee = EE();
  const { scale = 30, crs = null, transform = null, tileScale = 4, areaFormat = "Percentage", minPercentage = SANKEY_MIN_PERCENTAGE } = opts;
  ic = ic.filterBounds(geometry);
  const names = transitionBandNames(periods);
  let stacked = null;
  for (let i = 0; i < periods.length - 1; i++) {
    const [s1, e1] = bounds(periods[i]);
    const [s2, e2] = bounds(periods[i + 1]);
    const f1 = ic.filter(ee.Filter.calendarRange(Math.trunc(Number(s1)), Math.trunc(Number(e1)), "year")).select([band]);
    const f2 = ic.filter(ee.Filter.calendarRange(Math.trunc(Number(s2)), Math.trunc(Number(e2)), "year")).select([band]);
    const combined = f1.mode().rename(["from"]).addBands(f2.mode().rename(["to"]));
    const transition = combined.select("from").multiply(10000).add(9900).add(combined.select("to")).rename([names[i]]);
    stacked = stacked === null ? transition : stacked.addBands(transition);
  }
  const raw = await reduceArea(stacked.toInt(), geometry, ee.Reducer.frequencyHistogram(), { scale, crs, transform, tileScale });
  const info = bandInfo(classInfo, band);
  return { ...buildSankeyFromHistogram(raw, info, periods, areaFormat, scale, minPercentage), raw };
}

// port of charts.py summarize_and_chart's Sankey branch: class info from
// get_obj_info on the collection as given, the band is sankeyBandName or
// the first band, then prepare_sankey_data. Resolves to {links, matrix,
// raw, objInfo, band}.
export async function sankeyForCollection(ic, geometry, periods, opts = {}) {
  const objInfo = await getObjInfo(ic, opts.bandNames ?? null, opts.maxClassLabelLength ?? 30);
  const band = opts.sankeyBandName || objInfo.bandNames[0];
  const res = await prepareSankeyData(ic, band, periods, objInfo.classInfo, geometry, opts);
  return { ...res, objInfo, band };
}
