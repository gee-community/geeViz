// ArcGIS renderers (a layer's drawingInfo.renderer), drawn by Delta as the
// ArcGIS JS API draws them: which symbol each feature gets (simple, unique
// value, class breaks), visual variables (color, size, transparency and
// rotation by a field), and the legend built from the same renderer.
import { esriColor, glyphFor, toEsriColor } from "./symbols.js";
import { SURFACES } from "./surfaces.js";

const GEOM = { esriGeometryPoint: "point", esriGeometryMultipoint: "point", esriGeometryPolyline: "line", esriGeometryPolygon: "polygon" };

// ArcGIS's default symbols, for a layer with no renderer.
function defaultSymbol(geom) {
  if (geom === "point") return { type: "esriSMS", style: "esriSMSCircle", size: 6, color: [51, 136, 204, 255], outline: { type: "esriSLS", style: "esriSLSSolid", color: [255, 255, 255, 255], width: 0.75 } };
  if (geom === "line") return { type: "esriSLS", style: "esriSLSSolid", color: [51, 136, 204, 255], width: 1.5 };
  return { type: "esriSFS", style: "esriSFSSolid", color: [51, 136, 204, 64], outline: { type: "esriSLS", style: "esriSLSSolid", color: [51, 136, 204, 255], width: 1 } };
}

const STYLE_KEYS = ["strokeColor", "fillColor", "fillOpacity", "strokeWeight", "strokeOpacity", "color"];
const PX_TO_PT = 0.75;

// geeViz style keys (Map.addEsriFeatureService viz_params) as one symbol.
function symbolFromViz(v, geom) {
  const stroke = v.strokeColor || v.color || "000000";
  const so = v.strokeOpacity === undefined ? 1 : Number(v.strokeOpacity);
  const width = (v.strokeWeight === undefined ? 2 : Number(v.strokeWeight)) * PX_TO_PT;
  const outline = { type: "esriSLS", style: width > 0 ? "esriSLSSolid" : "esriSLSNull", color: toEsriColor(stroke, so), width };
  if (geom === "line") return outline;
  if (geom === "point") return { type: "esriSMS", style: "esriSMSCircle", size: 8, color: toEsriColor(stroke, so), outline: { type: "esriSLS", style: "esriSLSSolid", color: [255, 255, 255, 255], width: 0.75 } };
  const fo = v.fillOpacity === undefined ? (v.fillColor ? 0.3 : 0) : Number(v.fillOpacity);
  return { type: "esriSFS", style: fo > 0 ? "esriSFSSolid" : "esriSFSNull", color: toEsriColor(v.fillColor || stroke, fo), outline };
}

const num = (v) => (v === null || v === undefined || v === "" ? null : Number.isFinite(Number(v)) ? Number(v) : null);

function lerp(stops, v, key) {
  if (!stops.length) return null;
  if (v <= stops[0].value) return { t: 0, a: stops[0], b: stops[0] };
  for (let i = 1; i < stops.length; i++) {
    if (v <= stops[i].value) {
      const a = stops[i - 1];
      const b = stops[i];
      const t = b.value === a.value ? 1 : (v - a.value) / (b.value - a.value);
      return { t, a, b };
    }
  }
  const last = stops[stops.length - 1];
  return { t: 0, a: last, b: last };
}

// A value for a visual variable: its field, normalized when it says so.
function vvValue(vv, props) {
  if (!vv.field) return null;
  let v = num(props[vv.field]);
  if (v === null) return null;
  if (vv.normalizationField) {
    const d = num(props[vv.normalizationField]);
    if (!d) return null;
    v /= d;
  }
  return v;
}

// The visual variables' effect on one feature: {color, size, opacity, rotation}.
function visualVariables(vvs, props) {
  const out = {};
  (vvs || []).forEach((vv) => {
    if (!vv.field) return; // an Arcade expression: not supported
    const v = vvValue(vv, props);
    if (vv.type === "colorInfo" && v !== null && Array.isArray(vv.stops) && vv.stops.length) {
      const m = lerp(vv.stops, v);
      const ca = m.a.color;
      const cb = m.b.color;
      out.color = esriColor(ca.map((x, i) => x + ((cb[i] === undefined ? x : cb[i]) - x) * m.t));
    } else if (vv.type === "sizeInfo" && v !== null) {
      if (Array.isArray(vv.stops) && vv.stops.length) {
        const m = lerp(vv.stops, v);
        out.size = m.a.size + (m.b.size - m.a.size) * m.t;
      } else if (typeof vv.minSize === "number" && typeof vv.maxSize === "number" && vv.maxDataValue !== vv.minDataValue) {
        const t = Math.max(0, Math.min(1, (v - vv.minDataValue) / (vv.maxDataValue - vv.minDataValue)));
        out.size = vv.minSize + (vv.maxSize - vv.minSize) * t;
      }
    } else if (vv.type === "transparencyInfo" && v !== null && Array.isArray(vv.stops) && vv.stops.length) {
      const m = lerp(vv.stops, v);
      const tr = m.a.transparency + (m.b.transparency - m.a.transparency) * m.t;
      out.opacity = 1 - tr / 100;
    } else if (vv.type === "rotationInfo") {
      const deg = num(props[vv.field]);
      if (deg !== null) out.rotation = vv.rotationType === "arithmetic" ? 90 - deg : deg;
    }
  });
  return out;
}

const fmt = (v) => (typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString("en-US") : String(Number(v.toPrecision(4)))) : String(v));

// rendererFor(drawingInfo, vizOverride, geometryType) ->
// {type, fields, styleFor(props, zoom) -> {symbol, color, size, opacity,
// rotation} | null (not drawn), legend(title) -> legend}
export function rendererFor(drawingInfo, vizOverride = null, geometryType = null) {
  const geom = GEOM[geometryType] || null;
  const v = vizOverride || {};
  if (STYLE_KEYS.some((k) => v[k] !== undefined)) {
    const symbol = symbolFromViz(v, geom || "polygon");
    return { ...simple({ type: "simple", symbol }, geom), alpha: 1 };
  }
  const r = (drawingInfo && drawingInfo.renderer) || { type: "simple", symbol: defaultSymbol(geom) };
  const out = r.type === "uniqueValue" ? uniqueValue(r, geom) : r.type === "classBreaks" ? classBreaks(r, geom) : r.type === "simple" ? simple(r, geom) : SURFACES[r.type] ? SURFACES[r.type](r, geom) : unknown(r, geom);
  // drawingInfo.transparency (percent): the layer's own opacity
  out.alpha = 1 - Math.max(0, Math.min(100, Number(drawingInfo && drawingInfo.transparency) || 0)) / 100;
  return out;
}

// a legend from items, the visual variables' ramps and size glyphs, and a note
function makeLegend(title, items, r, geom, note) {
  const ramps = [];
  const extra = [];
  (r.visualVariables || []).forEach((vv) => {
    if (!vv.field) return;
    const name = (vv.legendOptions && vv.legendOptions.title) || vv.field;
    if (vv.type === "colorInfo" && Array.isArray(vv.stops) && vv.stops.length) {
      const first = vv.stops[0];
      const last = vv.stops[vv.stops.length - 1];
      ramps.push({
        label: name,
        palette: vv.stops.map((s) => esriColor(s.color).color),
        labels: [first.label === null || first.label === undefined ? fmt(first.value) : String(first.label), last.label === null || last.label === undefined ? fmt(last.value) : String(last.label)],
      });
    } else if (vv.type === "sizeInfo" && items.length) {
      const base = items[0].symbol;
      const sizes = Array.isArray(vv.stops) && vv.stops.length
        ? [[vv.stops[0].value, vv.stops[0].size], [vv.stops[vv.stops.length - 1].value, vv.stops[vv.stops.length - 1].size]]
        : [[vv.minDataValue, vv.minSize], [vv.maxDataValue, vv.maxSize]];
      sizes.forEach(([val, size]) => extra.push({ label: `${name}: ${fmt(val)}`, glyph: { ...glyphFor({ ...base, size }, geom || undefined), size } }));
    }
  });
  const legend = {
    type: "symbols",
    title,
    items: items.map((it) => ({ label: it.label, glyph: glyphFor(it.symbol, geom || undefined) })).concat(extra),
    ramps,
  };
  if (note) legend.note = note;
  return legend;
}

const ARCADE = "This layer's renderer uses an Arcade expression, which Delta does not run: features are drawn with one symbol.";

function simple(r, geom) {
  const symbol = r.symbol || defaultSymbol(geom);
  return {
    type: "simple",
    fields: (r.visualVariables || []).map((vv) => vv.field).filter(Boolean),
    styleFor: (props) => ({ symbol, ...visualVariables(r.visualVariables, props || {}) }),
    legend: (title) => makeLegend(title, [{ label: r.label || r.description || title || "", symbol }], r, geom, (r.visualVariables || []).some((vv) => !vv.field && vv.valueExpression) ? ARCADE : null),
  };
}

function uniqueValue(r, geom) {
  const fields = [r.field1, r.field2, r.field3].filter(Boolean);
  const delim = r.fieldDelimiter || ",";
  const infos = r.uniqueValueInfos || (r.uniqueValueGroups || []).flatMap((g) => (g.classes || []).map((c) => ({ ...c, value: (c.values || [[]])[0].join(delim) })));
  const byValue = new Map(infos.map((i) => [String(i.value), i]));
  const arcade = !fields.length && !!r.valueExpression;
  const fallback = r.defaultSymbol || (arcade && infos.length ? infos[0].symbol : null);
  return {
    type: "uniqueValue",
    fields: fields.concat((r.visualVariables || []).map((vv) => vv.field).filter(Boolean)),
    styleFor(props) {
      const p = props || {};
      let symbol = fallback;
      if (!arcade) {
        const key = fields.map((f) => (p[f] === null || p[f] === undefined ? "<Null>" : String(p[f]))).join(delim);
        const info = byValue.get(key);
        if (info) symbol = info.symbol;
        else symbol = r.defaultSymbol || null;
      }
      return symbol ? { symbol, ...visualVariables(r.visualVariables, p) } : null;
    },
    legend(title) {
      const items = infos.map((i) => ({ label: String(i.label === undefined || i.label === null || i.label === "" ? i.value : i.label), symbol: i.symbol }));
      if (r.defaultSymbol && !arcade) items.push({ label: r.defaultLabel || "Other", symbol: r.defaultSymbol });
      return makeLegend(title, items, r, geom, arcade ? ARCADE : null);
    },
  };
}

function classBreaks(r, geom) {
  const infos = (r.classBreakInfos || []).slice().sort((a, b) => a.classMaxValue - b.classMaxValue);
  const arcade = !r.field && !!r.valueExpression;
  const value = (p) => {
    let v = num(p[r.field]);
    if (v === null) return null;
    const t = r.normalizationType;
    if (t === "esriNormalizeByField") {
      const d = num(p[r.normalizationField]);
      if (!d) return null;
      v /= d;
    } else if (t === "esriNormalizeByLog") {
      if (v <= 0) return null;
      v = Math.log10(v);
    } else if (t === "esriNormalizeByPercentOfTotal") {
      if (!r.normalizationTotal) return null;
      v = (v / r.normalizationTotal) * 100;
    }
    return v;
  };
  return {
    type: "classBreaks",
    fields: [r.field, r.normalizationField].concat((r.visualVariables || []).map((vv) => vv.field)).filter(Boolean),
    styleFor(props) {
      const p = props || {};
      let symbol = null;
      if (arcade) symbol = r.defaultSymbol || (infos[0] && infos[0].symbol) || null;
      else {
        const v = value(p);
        if (v !== null) {
          const min = num(r.minValue);
          if (min === null || v >= min) {
            const hit = infos.find((i) => v <= i.classMaxValue);
            if (hit) symbol = hit.symbol;
          }
        }
        if (!symbol) symbol = r.defaultSymbol || null;
      }
      return symbol ? { symbol, ...visualVariables(r.visualVariables, p) } : null;
    },
    legend(title) {
      // the classes as the service orders them
      const items = (r.classBreakInfos || []).map((i) => ({ label: String(i.label || i.description || fmt(i.classMaxValue)), symbol: i.symbol }));
      if (r.defaultSymbol) items.push({ label: r.defaultLabel || "Other", symbol: r.defaultSymbol });
      return makeLegend(title, items, r, geom, arcade ? ARCADE : null);
    },
  };
}

// A renderer type Delta does not draw: the default symbol, and the legend says so.
function unknown(r, geom) {
  const symbol = r.defaultSymbol || r.symbol || defaultSymbol(geom);
  return {
    type: r.type || "unknown",
    fields: [],
    styleFor: () => ({ symbol }),
    legend: (title) => makeLegend(title, [{ label: title || "", symbol }], {}, geom, `Drawn with a default symbol: ${r.type || "this"} renderers are not supported.`),
  };
}
