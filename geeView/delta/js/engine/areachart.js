// Chart area: which layers chart over an area, with what settings, and the
// results they become. Ported from lcms-viewer area-charting.js (addLayer's
// settings and defaults, chartArea's layer selection, makeChart's CSV
// table, the Sankey CSV) with the numbers computed the charts.py way
// (engine/charts.js zonalStats, engine/sankey.js sankeyForCollection).
//
// Every reduction is cached by (layer, area, scale); a units or Show as
// change rebuilds the results from the cached raw reduction with no Earth
// Engine call. A new area takes a new request token: answers for an older
// area are dropped. Never touches the DOM or Google Maps.
import { AREA_FORMAT_DICT, SPLIT_STR, areaChartInputs, getObjInfo, parseReduction, reducerName, zonalStats } from "./charts.js";
import { SANKEY_MIN_PERCENTAGE, buildSankeyFromHistogram, ensureHexColor, formatPeriod, prepareSankeyData } from "./sankey.js";
import { evaluateAsync, getObjType } from "./viz.js";
import { smartToFixed, tokenSource } from "../util.js";

// port of 2templates.js addTransitionRow's two default rows (activeStartYear
// 1985, activeEndYear 2024, two-year periods)
export const DEFAULT_PERIODS = [
  [1985, 1987],
  [2022, 2024],
];

const given = (v) => v !== undefined && v !== null;
const splitList = (v) => (typeof v === "string" ? v.split(",").map((s) => s.trim()) : v);

// port of area-charting.js addLayer: the chart settings and their defaults.
// Map layers carry them in viz.areaChartParams (4map-manager.js
// setupAreaChartParams); chart-only layers (areaChart.addLayer) in viz.
export function chartParams(layer) {
  const viz = (layer && layer.viz) || {};
  const only = layer && layer.kind === "areaChartOnly";
  const src = only ? viz : viz.areaChartParams || {};
  const sankey = src.sankey === true;
  // class names, values and palette given with the layer (dictionaries by
  // band, as addClassVizDicts builds them); image properties otherwise
  const pick = (k) => (given(src[k]) ? src[k] : !only && given(viz[k]) ? viz[k] : null);
  const names = pick("class_names");
  const classDicts = names && typeof names === "object" && !Array.isArray(names) ? { names, values: pick("class_values") || {}, palette: pick("class_palette") || {} } : null;
  return {
    line: !!src.line || sankey === false,
    sankey,
    chartType: src.chartType || "line", // "line", "stacked-line", "bar", "stacked-bar"
    barChartMaxClasses: src.barChartMaxClasses || 20,
    rangeSlider: src.rangeSlider === true,
    hovermode: src.hovermode || "closest",
    showGrid: given(src.showGrid) ? !!src.showGrid : true,
    chartLabelMaxWidth: src.chartLabelMaxWidth || 40,
    chartLabelMaxLength: src.chartLabelMaxLength || 100,
    chartPrecision: given(src.chartPrecision) ? src.chartPrecision : null,
    chartDecimalProportion: given(src.chartDecimalProportion) ? src.chartDecimalProportion : null,
    palette: given(src.palette) ? splitList(src.palette) : null,
    thematic: src.thematic === true,
    reducer: given(src.reducer) ? src.reducer : null,
    yAxisLabel: src.yAxisLabel || null,
    xAxisLabel: src.xAxisLabel || null,
    sankeyMinPercentage: given(src.sankeyMinPercentage) ? src.sankeyMinPercentage : SANKEY_MIN_PERCENTAGE,
    sankeyTransitionPeriods: src.sankeyTransitionPeriods || null,
    sankeyBandName: src.sankeyBandName || null,
    minZoomSpecifiedScale: src.minZoomSpecifiedScale || 11,
    scale: src.scale,
    transform: src.transform,
    crs: src.crs || null,
    dateFormat: src.dateFormat || viz.dateFormat || "YYYY",
    // port of addLayer: with class names given, the bands are their keys
    bandNames: given(src.bandNames) ? splitList(src.bandNames) : classDicts ? Object.keys(classDicts.names) : !only && given(viz.bands) ? splitList(viz.bands) : null,
    layerType: src.layerType || viz.layerType || null,
    classDicts,
    // port of addLayer shouldUnmask / unmaskValue
    shouldUnmask: src.shouldUnmask === true,
    unmaskValue: src.unmaskValue || 0,
  };
}

function listOrder(s) {
  const byId = new Map(s.layers.map((l) => [l.id, l]));
  const listed = s.order.filter((id) => byId.has(id)).map((id) => byId.get(id));
  return listed.concat(s.layers.filter((l) => s.order.indexOf(l.id) === -1));
}

// port of area-charting.js chartArea's selection: every visible map layer
// with canAreaChart (line and Sankey as two charts when both are asked
// for), plus the chart-only layers chosen in settings (shouldChart by
// default). Settings can also leave a map layer out. List order, top first.
export function chartJobs(s) {
  const choices = s.chartChoices || {};
  const jobs = [];
  listOrder(s).forEach((layer) => {
    if (!layer.chartable || layer.kind === "select") return;
    const chosen = layer.kind === "areaChartOnly" ? (given(choices[layer.id]) ? !!choices[layer.id] : !!layer.visible) : layer.visible && choices[layer.id] !== false;
    if (!chosen) return;
    const params = chartParams(layer);
    if (params.line) jobs.push({ layer, params, kind: "line" });
    if (params.sankey) jobs.push({ layer, params, kind: "sankey" });
  });
  return jobs;
}

// Show as and units pick the charts.py area format.
export function areaFormatFor(units, showAs) {
  if (showAs === "pct") return "Percentage";
  return units === "imperial" ? "Acres" : "Hectares";
}

const UNIT_TEXT = { Percentage: "%", Hectares: "ha", Acres: "acres", Pixels: "pixels" };

// cyrb53: a 53-bit string hash (area keys)
export function hashString(str) {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}

function precisionOf(params, ctx) {
  const g = (ctx && ctx.precision) || {};
  return {
    chartPrecision: given(params.chartPrecision) ? params.chartPrecision : given(g.chartPrecision) ? g.chartPrecision : 3,
    chartDecimalProportion: given(params.chartDecimalProportion) ? params.chartDecimalProportion : given(g.chartDecimalProportion) ? g.chartDecimalProportion : 0.25,
  };
}

function settingsOf(params) {
  const keys = ["chartType", "barChartMaxClasses", "rangeSlider", "hovermode", "showGrid", "chartLabelMaxWidth", "chartLabelMaxLength"];
  return Object.fromEntries(keys.map((k) => [k, params[k]]));
}

// charts.py picks class_info[band], else the first band's
function bandInfo(classInfo, band) {
  if (!classInfo) return {};
  if (classInfo[band]) return classInfo[band];
  const first = Object.keys(classInfo)[0];
  return first !== undefined ? classInfo[first] : {};
}

// Colors by column: the band's class palette (port of chartArea's
// class_palette lookup), else the layer's palette by position.
function columnColors(columns, objInfo, params, isHistogram) {
  const bands = objInfo.bandNames || [];
  const multi = bands.length > 1;
  const pal = (i) => (params.palette && given(params.palette[i]) ? ensureHexColor(params.palette[i]) : null);
  return columns.map((col, i) => {
    if (!isHistogram) return pal(i);
    let band = bands[0];
    let name = col;
    if (multi) {
      const at = col.indexOf(SPLIT_STR);
      if (at > -1) {
        band = col.slice(0, at);
        name = col.slice(at + SPLIT_STR.length);
      }
    }
    const info = (objInfo.classInfo || {})[band] || {};
    const k = (info.classNames || []).indexOf(name);
    if (k > -1 && info.classPalette && given(info.classPalette[k])) return ensureHexColor(info.classPalette[k]);
    return pal(i);
  });
}

// A line (or bar) chart result from a cached reduction. ctx: {units,
// showAs, areaLabel, areaKey, nominalScale, precision}.
export function lineResult(layer, params, entry, ctx) {
  const fmt = entry.isHistogram ? areaFormatFor(ctx.units, ctx.showAs) : null;
  const table = parseReduction(entry.raw, entry.objInfo, entry.labels, {
    isHistogram: entry.isHistogram,
    sentinel: entry.sentinel,
    areaFormat: fmt || "Percentage",
    scale: entry.scale,
  });
  const isCollection = entry.objInfo.objType === "ImageCollection";
  const labels = table.rows.map((r) => r.x);
  const span = !isCollection ? "" : labels.length > 1 ? `${labels[0]}-${labels[labels.length - 1]}, ` : labels.length ? `${labels[0]}, ` : "";
  return {
    id: `${layer.id}:chart`,
    layerId: layer.id,
    title: isCollection ? `${layer.name} over time` : layer.name,
    meta: `${span}${ctx.nominalScale} m`,
    kind: "chart",
    actions: ["csv", "png", "expand"],
    data: {
      layerName: layer.name,
      columns: table.columns,
      rows: table.rows,
      colors: columnColors(table.columns, entry.objInfo, params, entry.isHistogram),
      isCollection,
      isThematic: !!entry.isHistogram,
      chartType: isCollection ? params.chartType : "bar",
      xLabel: isCollection ? params.xAxisLabel || "Year" : "",
      yLabel: params.yAxisLabel || (entry.isHistogram ? AREA_FORMAT_DICT[fmt].label : entry.reducerLabel || "Mean"),
      areaFormat: fmt,
      unitText: fmt ? UNIT_TEXT[fmt] : "",
      nominalScale: ctx.nominalScale,
      crs: ctx.crs || null,
      transform: ctx.transform || null,
      areaLabel: ctx.areaLabel,
      areaKey: ctx.areaKey,
      settings: settingsOf(params),
      precision: precisionOf(params, ctx),
    },
  };
}

// A Sankey result from a cached transition reduction.
export function sankeyResult(layer, params, entry, ctx) {
  const fmt = areaFormatFor(ctx.units, ctx.showAs);
  const { links, matrix } = buildSankeyFromHistogram(entry.raw, entry.objInfo.classInfo, entry.periods, fmt, entry.scale, params.sankeyMinPercentage, entry.band);
  const info = bandInfo(entry.objInfo.classInfo, entry.band);
  const multi = (entry.objInfo.bandNames || []).length > 1;
  const periods = entry.periods.map(formatPeriod);
  return {
    id: `${layer.id}:sankey:${entry.band}`,
    layerId: layer.id,
    title: `${layer.name}${multi ? " " + entry.band : ""} transitions`,
    meta: `${periods[0]} to ${periods[periods.length - 1]}, ${ctx.nominalScale} m`,
    kind: "sankey",
    actions: ["csv", "png", "expand"],
    data: {
      layerName: layer.name,
      band: entry.band,
      periods,
      links,
      matrix,
      classNames: info.classNames || [],
      classPalette: (info.classPalette || []).map(ensureHexColor),
      minPercentage: params.sankeyMinPercentage,
      areaFormat: fmt,
      unitText: UNIT_TEXT[fmt],
      nominalScale: ctx.nominalScale,
      crs: ctx.crs || null,
      transform: ctx.transform || null,
      areaLabel: ctx.areaLabel,
      areaKey: ctx.areaKey,
      precision: precisionOf(params, ctx),
    },
  };
}

const sanitize = (s) => String(s).replace(/[^A-Za-z0-9 -]/g, "-");
function csvCell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
const csvLines = (rows) => rows.map((r) => r.map(csvCell).join(",")).join("\n") + "\n";

// port of area-charting.js makeChart's csvTable (collections: the x axis
// label, then class columns with [^A-Za-z0-9 -] made "-"; single images:
// transposed under "Class Name" and the y axis label) and of chartArea's
// Sankey outCSV (one block per transition: "to" classes across, "from"
// classes down, a blank row after each). Gaps are empty cells.
export function chartCsv(r) {
  const d = r.data;
  const p = d.precision || {};
  const fix = (v) => (v === null || v === undefined ? "" : smartToFixed(v, p.chartDecimalProportion, p.chartPrecision));
  if (r.kind === "sankey") {
    const out = [];
    Object.keys(d.matrix).forEach((key) => {
      const [p1, p2] = key.split(" → ");
      const m = d.matrix[key];
      out.push([""].concat(m.columns.map((nm) => `${sanitize(nm)} ${p2} `)));
      m.index.forEach((nm1, i) => out.push([`${sanitize(nm1)} ${p1}`].concat(m.values[i])));
      out.push([""]);
    });
    return out.map((row) => row.map(csvCell).join(",")).join("\n");
  }
  if (d.isCollection) {
    const head = [d.xLabel].concat(d.columns.map(sanitize));
    return csvLines([head].concat(d.rows.map((row) => [row.x].concat(row.values.map(fix)))));
  }
  const values = d.rows.length ? d.rows[0].values : [];
  return csvLines([["Class Name", d.yLabel]].concat(d.columns.map((c, i) => [sanitize(c), fix(values[i])])));
}

// port of 2templates.js getTransitionRowData's checks (the year range
// check is left out: a geeViz map has no fixed range).
const PERIOD_ERRORS = {
  noValues: "No year pairs provided. Please add at least two rows of years.",
  blank: "One or more blank value found",
  backwards: "One or more row has a first year that is greater than the last year",
  overlap: "Please ensure all transition periods have values and are in succession of one another and do not overlap",
};
export function validatePeriods(periods) {
  const errs = [];
  if (!Array.isArray(periods) || periods.length <= 1) errs.push("noValues");
  else {
    periods.forEach((row, i) => {
      row.forEach((n) => {
        if (!Number.isFinite(n)) errs.push("blank");
      });
      if (row[1] < row[0]) errs.push("backwards");
      if (i > 0 && periods[i - 1][1] >= row[0]) errs.push("overlap");
    });
  }
  const errors = [...new Set(errs)].map((e) => PERIOD_ERRORS[e]);
  return { periods: errors.length ? null : periods.map((r) => r.slice()), errors };
}

const title = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// The Earth Engine object of a layer: deserialized once when serialized.
function makeItemOf(ee) {
  const memo = new Map();
  return (layer) => {
    if (memo.has(layer.id)) return memo.get(layer.id);
    let item = layer.item;
    if (layer.viz && layer.viz.serialized === true && item && typeof item.evaluate !== "function") item = ee.Deserializer.decode(item);
    memo.set(layer.id, item);
    return item;
  };
}

// The layer's declared type wins (port of setupAreaChartParams layerType):
// a deserialized collection.filter() is typed FeatureCollection by its
// function signature, so instanceof alone cannot tell.
function eeTypeOf(ee, obj, hint) {
  if (hint === "ImageCollection" || hint === "geeImageCollection") return "ImageCollection";
  if (hint === "Image" || hint === "geeImage") return "Image";
  return getObjType(obj, ee);
}

// Class dictionaries given with the layer, set as the {band}_class_*
// properties charts.py get_obj_info reads (they win over the image's own).
export function classProps(classDicts) {
  if (!classDicts) return null;
  const props = {};
  const list = (v) => (Array.isArray(v) ? v : typeof v === "string" ? v.split(",").map((x) => x.trim()) : [v]);
  Object.keys(classDicts.names).forEach((bn) => {
    props[`${bn}_class_names`] = list(classDicts.names[bn]);
    if (given(classDicts.values[bn])) props[`${bn}_class_values`] = list(classDicts.values[bn]);
    if (given(classDicts.palette[bn])) props[`${bn}_class_palette`] = list(classDicts.palette[bn]);
  });
  return props;
}
function withClassProps(ee, obj, type, params) {
  const props = classProps(params.classDicts);
  if (!props) return obj;
  return type === "ImageCollection" ? obj.map((img) => img.set(props)) : ee.Image(obj).set(props);
}

// port of area-charting.js autoSankeyTransitionPeriods: the first row starts
// at the earliest first year of the Sankey layers, the last row ends at the
// latest last year (sankeyTransitionPeriodYearBuffer 0).
export function autoPeriods(current, layerYears, buffer = 0) {
  const ys = layerYears.filter((v) => v && v.length);
  if (!ys.length) return current;
  const start = Math.min(...ys.map((v) => v[0]));
  const end = Math.max(...ys.map((v) => v[v.length - 1]));
  const out = (current && current.length >= 2 ? current : DEFAULT_PERIODS).map((r) => r.slice());
  out[0] = [start, start + buffer];
  out[out.length - 1] = [end - buffer, end];
  return out;
}

function reducerOf(ee, params) {
  let r = params.reducer;
  if (typeof r === "string") r = ee.Deserializer.fromJSON(r);
  else if (r && typeof r === "object" && typeof r.evaluate !== "function") r = ee.Deserializer.decode(r);
  if (!r && params.thematic) r = ee.Reducer.frequencyHistogram();
  return r || null;
}

// The Earth Engine side: charts.py's zonal_stats and prepare_sankey_data
// with the viewer's inputs.
export function eeCompute(ee) {
  return {
    async line(obj, params, geometry, inputs) {
      const type = eeTypeOf(ee, obj, params.layerType);
      if (type !== "Image" && type !== "ImageCollection") {
        throw new Error(`Cannot chart ee object type ${type}. Accepted types are ee.ImageCollection and ee.Image`);
      }
      const reducer = reducerOf(ee, params);
      let item = withClassProps(ee, type === "ImageCollection" ? ee.ImageCollection(obj) : ee.Image(obj), type, params);
      // port of chartArea: with shouldUnmask, masked pixels take unmaskValue
      // and count; otherwise they are left out (percent of valid pixels)
      if (params.shouldUnmask) {
        const v = params.unmaskValue;
        item = type === "ImageCollection" ? item.map((img) => ee.Image(img.unmask(v).copyProperties(img, ["system:time_start"]))) : ee.Image(item).unmask(v);
      }
      const r = await zonalStats(item, geometry, {
        reducer,
        scale: inputs.nominalScale,
        crs: inputs.crs,
        transform: inputs.transform,
        dateFormat: params.dateFormat,
        bandNames: params.bandNames,
        includeMaskedArea: false,
      });
      const name = reducerName(reducer || ee.Reducer.mean()).replace(/^Reducer\./, "");
      return {
        raw: r.raw,
        objInfo: r.objInfo,
        labels: r.labels,
        isHistogram: r.isHistogram,
        sentinel: false,
        scale: inputs.nominalScale,
        reducerLabel: /^[A-Za-z]+$/.test(name) ? title(name) : null,
      };
    },
    async sankey(obj, params, geometry, inputs, periods) {
      const type = eeTypeOf(ee, obj, params.layerType);
      if (type !== "ImageCollection") {
        throw new Error(`Sankey charts need an ee.ImageCollection, not ${type}`);
      }
      // port of chartArea's Sankey branch: one Sankey per thematic band, each
      // band's period pairs stacked into one reduction (charts.py prepare_sankey_data)
      const ic = withClassProps(ee, ee.ImageCollection(obj), "ImageCollection", params);
      const objInfo = await getObjInfo(ic, params.bandNames);
      const bands = params.sankeyBandName ? [params.sankeyBandName] : objInfo.bandNames.filter((b) => objInfo.classInfo[b]);
      if (!bands.length) throw new Error("Sankey charts need class values and names ({band}_class_values and {band}_class_names)");
      const opts = { scale: inputs.nominalScale, crs: inputs.crs, transform: inputs.transform, minPercentage: params.sankeyMinPercentage };
      const out = await Promise.all(bands.map((band) => prepareSankeyData(ic, band, periods, objInfo.classInfo, geometry, opts)));
      return { objInfo, periods, scale: inputs.nominalScale, bands: bands.map((band, i) => ({ band, raw: out[i].raw })) };
    },
    // the first and last year of a collection (port of addLayer's sankey_years)
    async years(obj, params) {
      const ic = ee.ImageCollection(obj);
      const ys = await evaluateAsync(
        ee.Dictionary(ic.reduceColumns(ee.Reducer.minMax(), ["system:time_start"]))
          .values()
          .map((n) => ee.Date(n).format(params.dateFormat))
          .sort()
      );
      return ys.map((y) => Number.parseInt(y, 10)).filter((y) => Number.isFinite(y));
    },
  };
}

// The Chart area controller. deps: ee, compute ({line, sankey}, default
// eeCompute(ee)), item(layer) -> Earth Engine object, zoom() -> map zoom,
// key(geometry) -> area key (default: hash of the serialized geometry),
// notify(msg).
export function createAreaCharter(store, deps = {}) {
  const ee = deps.ee || globalThis.ee;
  const compute = deps.compute || eeCompute(ee);
  const itemOf = deps.item || makeItemOf(ee);
  const zoom = deps.zoom || (() => 11);
  const keyOf = deps.key || ((g) => hashString(ee.Serializer.toJSON(g)));
  const notify = deps.notify || (() => {});
  const tokens = tokenSource();
  const cache = new Map(); // "layer|kind|area|scale[|periods]" -> Promise of a cached reduction
  const years = new Map(); // layer id -> Promise of the collection's [first, last] years
  let current = null; // {token, label, areaKey, done: [{index, job, entry, inputs}]}

  function build(d) {
    const s = store.get();
    const ctx = {
      units: s.units,
      showAs: s.showAs,
      areaLabel: d.label,
      areaKey: d.areaKey,
      nominalScale: d.inputs.nominalScale,
      crs: d.inputs.crs,
      transform: d.inputs.transform,
      precision: s.query && s.query.precision,
    };
    if (d.job.kind !== "sankey") return [lineResult(d.job.layer, d.job.params, d.entry, ctx)];
    const bands = d.entry.bands || [{ band: d.entry.band, raw: d.entry.raw }];
    return bands.map((b) => sankeyResult(d.job.layer, d.job.params, { ...d.entry, band: b.band, raw: b.raw }, ctx));
  }

  // Results from what has arrived, in job order. No Earth Engine.
  function publish(reason) {
    if (!current) return;
    const done = current.done.slice().sort((a, b) => a.index - b.index);
    const results = [];
    done.forEach((d) => {
      try {
        results.push(...build(d));
      } catch (e) {
        notify(`Charting ${d.job.layer.name} failed: ${e && e.message ? e.message : e}`);
      }
    });
    store.set({ results }, reason);
  }

  async function chartArea(geometry, label, extra = {}) {
    const token = tokens();
    const s = store.get();
    const areaKey = keyOf(geometry);
    const z = zoom();
    const jobs = chartJobs(s);
    current = { token, label, areaKey, done: [] };
    store.set({ results: [], where: label, charting: jobs.length > 0, chartArea: { label, key: areaKey, ...extra } }, "chart-start");

    let shared = null;
    const sharedJobs = jobs.filter((j) => j.kind === "sankey" && !j.params.sankeyTransitionPeriods);
    if (sharedJobs.length && !s.chartPeriodsUser && compute.years) {
      // port of autoSankeyTransitionPeriods: default rows from the layers' own years
      const ys = await Promise.all(
        sharedJobs.map((j) => {
          if (!years.has(j.layer.id)) {
            const pr = Promise.resolve()
              .then(() => compute.years(itemOf(j.layer), j.params))
              .catch(() => null);
            years.set(j.layer.id, pr);
          }
          return years.get(j.layer.id);
        })
      );
      if (!token.isCurrent()) return;
      const next = autoPeriods(store.get().chartPeriods, ys);
      if (JSON.stringify(next) !== JSON.stringify(store.get().chartPeriods)) store.set({ chartPeriods: next }, "chart-periods-auto");
    }
    if (sharedJobs.length) {
      const v = validatePeriods(store.get().chartPeriods || DEFAULT_PERIODS);
      if (v.periods) shared = v.periods;
      else notify("Invalid Transition Periods Provided: " + v.errors.join(" "));
    }

    const tasks = jobs.map((job, index) => {
      const p = job.params;
      const inputs = areaChartInputs({ scale: p.scale, transform: p.transform, crs: p.crs, minZoomSpecifiedScale: p.minZoomSpecifiedScale }, z);
      let periods = null;
      if (job.kind === "sankey") {
        periods = p.sankeyTransitionPeriods || shared;
        if (!periods) return null;
      }
      const ck = [job.layer.id, job.kind, areaKey, inputs.nominalScale, periods ? JSON.stringify(periods) : ""].join("|");
      let pr = cache.get(ck);
      if (!pr) {
        try {
          pr = Promise.resolve(compute[job.kind](itemOf(job.layer), p, geometry, inputs, periods));
        } catch (e) {
          pr = Promise.reject(e);
        }
        cache.set(ck, pr);
        pr.catch(() => cache.delete(ck));
      }
      return pr.then(
        (entry) => {
          if (!token.isCurrent()) return;
          current.done.push({ index, job, entry, inputs, label, areaKey });
          publish("chart-result");
        },
        (e) => {
          if (!token.isCurrent()) return;
          notify(`Charting ${job.layer.name} failed: ${e && e.message ? e.message : e}`);
        }
      );
    });
    await Promise.all(tasks);
    if (token.isCurrent()) store.set({ charting: false }, "chart-done");
  }

  function cancel() {
    tokens();
    current = null;
    if (store.get().charting) store.set({ charting: false }, "chart-cancel");
  }

  const rerender = () => current && store.get().tool === "chart" && publish("chart-rerender");
  store.on("change:units", rerender);
  store.on("change:showAs", rerender);
  store.on("change:query", rerender);
  store.on("change:tool", (tool) => tool !== "chart" && cancel());

  return { chartArea, rerender, cancel, cacheSize: () => cache.size, current: () => current };
}

// chartArea(engine, store, geometry, sourceLabel): the Chart area entry point.
export function chartArea(engine, store, geometry, sourceLabel, extra) {
  return engine.charter.chartArea(geometry, sourceLabel, extra);
}
