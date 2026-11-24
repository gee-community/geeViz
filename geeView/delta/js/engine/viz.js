// Visualization preparation for a layer: layerType defaulting, autoViz class
// dictionaries, vector styling defaults and the legend. No DOM access.
//
// Ports of lcms-viewer 4map-manager.js buildLayer (as bundled in
// geeView/src/js/lcms-viewer.min.js, which adds _normalizeClassProp to
// addClassVizDicts), addClassVizDicts, getLookupDicts, getColor and the
// legend construction of buildLayer. Delta never calls getInfo(): object
// info is fetched with evaluate().

// port of 4map-manager.js colorList
const COLOR_LIST = [
  "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6",
  "#bcf60c", "#fabebe", "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000", "#aaffc3",
  "#808000", "#ffd8b1", "#000075", "#808080", "#ffffff", "#000000",
];

// port of 4map-manager.js getColor (colorMod starts at colorList.length, so the first color is the first in the list)
export function createColorCycle() {
  let colorMod = COLOR_LIST.length;
  return () => COLOR_LIST[colorMod++ % COLOR_LIST.length];
}
const defaultColorCycle = createColorCycle();

const typeLookup = {
  Image: "geeImage",
  ImageCollection: "geeImageCollection",
  Feature: "geeVectorImage",
  FeatureCollection: "geeVectorImage",
  Geometry: "geeVectorImage",
};
const reverseTypeLookup = {};
Object.keys(typeLookup).forEach((k) => (reverseTypeLookup[typeLookup[k]] = k));

const NON_EE_TYPES = ["geoJSONVector", "tileMapService", "dynamicMapService"];
const VECTOR_TYPES = ["geeVector", "geoJSONVector", "geeVectorImage"];

const isNil = (v) => v === undefined || v === null;

// port of getImagesLib.js getObjType
export function getObjType(obj, eeApi = globalThis.ee) {
  if (!eeApi || !obj) return undefined;
  let t;
  ["Image", "ImageCollection", "Geometry", "Feature", "FeatureCollection"].forEach((k) => {
    if (eeApi[k] && obj instanceof eeApi[k]) t = k;
  });
  return t;
}

// port of getImagesLib.js eeObjInfo (no time handling; the layer path never asks for it)
export function eeObjInfo(eeObj, objType, eeApi = globalThis.ee) {
  objType = objType || getObjType(eeObj, eeApi);
  eeObj = objType === "Geometry" ? eeApi.Feature(eeObj) : eeObj;
  let props = eeApi.Dictionary();
  let bandNames;
  let size;
  if (objType && objType.indexOf("Collection") > -1) {
    size = eeObj.size();
    if (objType === "ImageCollection") {
      const first = eeApi.Image(eeApi.ImageCollection(eeObj).first());
      bandNames = first.bandNames();
      props = first.toDictionary();
    }
  } else if (objType === "Image") {
    bandNames = eeApi.Image(eeObj).bandNames();
    props = eeApi.Image(eeObj).toDictionary();
  }
  props = props.set("layerType", objType);
  if (bandNames !== undefined) props = props.set("bandNames", bandNames);
  if (size !== undefined) props = props.set("size", size);
  return props;
}

export function evaluateAsync(obj) {
  return new Promise((resolve, reject) =>
    obj.evaluate((v, err) => (err ? reject(new Error(String(err))) : resolve(v)))
  );
}

// port of lcms-viewer.min.js _normalizeClassProp: a comma-separated string
// property becomes a list (commas followed by a space stay inside a name).
export function normalizeClassProp(v, asNum) {
  if (typeof v !== "string") return v;
  const parts = v
    .split(/,(?! )/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
  if (asNum) return parts.map((p) => (isNaN(Number(p)) ? p : Number(p)));
  return parts;
}

// port of 4map-manager.js addClassVizDicts (bundled version)
export function addClassVizDicts(viz) {
  const info = viz.eeObjInfo || {};
  const keys = Object.keys(info).filter((k) => k.indexOf("_class_names") > -1);
  if (keys.length > 0) {
    const bandNames = info.bandNames || [];
    const bns = keys.map((k) => k.split("_class_names")[0]).filter((bn) => bandNames.indexOf(bn) > -1);
    if (bns.length >= 1) {
      viz.autoViz = true;
      viz.class_names = {};
      viz.class_values = {};
      viz.class_palette = {};
      viz.class_visibility = {};
      bns.forEach((bn) => {
        const cns = normalizeClassProp(info[`${bn}_class_names`], false);
        const cvs = normalizeClassProp(info[`${bn}_class_values`], true);
        const cp = normalizeClassProp(info[`${bn}_class_palette`], false);
        const cv = normalizeClassProp(info[`${bn}_class_visibility`], false);
        if (cns !== undefined) {
          viz.class_names[bn] = viz.class_names[bn] || cns;
          viz.class_values[bn] = viz.class_values[bn] || cvs;
          viz.class_palette[bn] = viz.class_palette[bn] || cp;
          viz.class_visibility[bn] = viz.class_visibility[bn] || cv;
        }
      });
    }
  }
  return viz;
}

// port of 4map-manager.js getLookupDicts
export function getLookupDicts(bandName, class_values, class_names, class_palette, includeClassValues) {
  const values = class_values && class_values[bandName];
  const palette = class_palette && class_palette[bandName];
  const names = class_names && class_names[bandName];
  if (!Array.isArray(values) || !Array.isArray(names) || !Array.isArray(palette)) {
    return { classLegendDict: {}, queryDict: {} };
  }
  includeClassValues = includeClassValues == true || includeClassValues == undefined;
  const labels = includeClassValues ? values.map((v, i) => [v, names[i]].join("- ")) : names;
  const classLegendDict = {};
  labels.forEach((l, i) => (classLegendDict[l] = palette[i]));
  const queryDict = {};
  values.forEach((v, i) => (queryDict[v] = names[i]));
  return { classLegendDict, queryDict };
}

// port of 4map-manager.js addColorHash
export function addColorHash(color) {
  color = String(color);
  return /^[0-9a-fA-F]+$/.test(color) ? "#" + color : color;
}

// port of 4map-manager.js qcHex
function qcHex(hex) {
  if (hex.indexOf("#") === 0) hex = hex.slice(1);
  if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2] + "FF";
  else if (hex.length === 4) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3];
  else if (hex.length === 6) hex = `${hex}FF`;
  return hex;
}

const NAMED = /^(red|blue|green|black|white|yellow|orange|purple|pink|gray|grey|cyan|magenta|brown|navy|teal|lime|aqua|olive|maroon|silver|gold|transparent)$/i;
const VEC_KEYS = ["strokeColor", "fillColor", "strokeWeight", "strokeOpacity", "fillOpacity", "clickable", "cursor", "draggable", "editable", "icon", "shape", "title", "visible", "zIndex"];

// port of lcms-viewer.min.js addLayer _normVecStyle (google.maps.Data style from a viz)
export function normVecStyle(v) {
  const s = {};
  const fix = (k) => {
    let x = v[k];
    if (typeof x === "string" && x.length > 0 && x.indexOf("#") === -1 && !NAMED.test(x)) x = "#" + x;
    return x;
  };
  if (v.color !== undefined && v.strokeColor === undefined) s.strokeColor = fix("color");
  for (const k of VEC_KEYS) {
    if (v[k] !== undefined) s[k] = k === "strokeColor" || k === "fillColor" ? fix(k) : v[k];
  }
  if (s.strokeColor === undefined) s.strokeColor = "#000000";
  if (s.strokeWeight === undefined) s.strokeWeight = 3;
  if (s.strokeOpacity === undefined) s.strokeOpacity = 1;
  if (s.fillOpacity === undefined) s.fillOpacity = 0;
  return s;
}

// A grouped wind layer (geeViz.weather.addWindLayer: one layer, a speed field
// under particle trails). port of wind-particles.js restyleLegend: a color bar
// from the speed ramp with its two end values, the high one in the layer's
// units, and a particle crossing the bar in the trail color. The viz also
// carries a classLegendDict chip for viewers without that code; this replaces
// it. Returns null for any other layer.
export function windLegend(viz, name) {
  if (!viz || !viz.windParticles || !viz.windSpeedRaster || viz.addToLegend === false) return null;
  const pal = Array.isArray(viz.windSpeedPalette) ? viz.windSpeedPalette : [];
  if (pal.length < 2 || isNil(viz.windRampMin) || isNil(viz.windRampMax)) return null;
  const units = viz.windUnits ? " " + viz.windUnits : "";
  return {
    type: "ramp",
    wind: true,
    title: isNil(viz.legendTitle) ? name : viz.legendTitle,
    min: viz.windRampMin,
    max: viz.windRampMax,
    palette: pal.map((c) => addColorHash(String(c).replace(/^#/, ""))),
    labels: [String(viz.windRampMin), String(viz.windRampMax) + units],
    particle: viz.particleColor || "#fff",
  };
}

// Where a grouped wind layer's particle opacity slider starts. port of
// wind-particles.js initialDim: geeViz.weather sends the particles' opacity as
// windParticleDim (opacity is the speed field's); a hand-built viz without it
// falls back to opacity. undefined for any other layer: it has one slider.
export function particleOpacityFor(viz) {
  if (!viz || !viz.windParticles || !viz.windSpeedRaster) return undefined;
  const d = typeof viz.windParticleDim === "number" ? viz.windParticleDim : typeof viz.opacity === "number" ? viz.opacity : 1;
  return Math.min(1, Math.max(0, d));
}

// Legend for a prepared viz. port of the legend construction at the end of
// 4map-manager.js buildLayer (addColorRampLegendEntry and addClassLegendEntry
// inputs). Deliberate difference: a tile or dynamic map service with no
// legend information gets no legend, not the original's grey "min"/"max"
// ramp (the "tile legend v2" patch calls that ramp a defect).
export function legendFor(viz, name) {
  if (!viz) return null;
  if (viz.legend && typeof viz.legend === "object" && viz.legend.type) return viz.legend;
  const wind = windLegend(viz, name);
  if (wind) return wind;
  const title = isNil(viz.legendTitle) ? name : viz.legendTitle;
  const isService = viz.layerType === "tileMapService" || viz.layerType === "dynamicMapService";
  if (
    (viz.bands == null || viz.bands.length == 1) &&
    viz.addToLegend != false &&
    (isNil(viz.addToClassLegend) || viz.addToClassLegend === false) &&
    viz.classLegendDict == undefined
  ) {
    if (isService && isNil(viz.palette) && isNil(viz.min) && isNil(viz.max)) return null;
    let paletteList = isNil(viz.palette) ? "000,FFF" : viz.palette;
    if (typeof paletteList === "string") paletteList = paletteList.split(",");
    if (paletteList.length == 1) paletteList = [paletteList[0], paletteList[0]];
    const palette = paletteList.map((c) => addColorHash(String(c).replace(/^#/, "")));
    const fmt = (v) => (viz.legendNumbersWithCommas && typeof v === "number" ? v.toLocaleString("en-US") : String(v));
    let minL = isNil(viz.min) ? null : fmt(viz.min);
    let maxL = isNil(viz.max) ? null : fmt(viz.max);
    const minV = minL;
    const maxV = maxL;
    if (!isNil(viz.legendLabelLeft)) minL = viz.legendLabelLeft + " " + minV;
    if (!isNil(viz.legendLabelRight)) maxL = viz.legendLabelRight + " " + maxV;
    if (!isNil(viz.legendLabelLeftAfter)) minL = minV + " " + viz.legendLabelLeftAfter;
    if (!isNil(viz.legendLabelRightAfter)) maxL = maxV + " " + viz.legendLabelRightAfter;
    return {
      type: "ramp",
      title,
      min: isNil(viz.min) ? null : viz.min,
      max: isNil(viz.max) ? null : viz.max,
      palette,
      labels: [minL === null ? "min" : minL, maxL === null ? "max" : maxL],
    };
  }
  if (viz.classLegendDict != null || viz.addToClassLegend === true) {
    if (VECTOR_TYPES.indexOf(viz.layerType) === -1) {
      const dict = viz.classLegendDict || {};
      return { type: "classes", title, items: Object.keys(dict).map((k) => ({ label: k, color: addColorHash(dict[k]) })) };
    }
    return {
      type: "outline",
      title,
      label: title,
      color: viz.strokeColor,
      fill: viz.fillColor,
      fillOpacity: viz.fillOpacity,
      weight: viz.strokeWeight,
      strokeOpacity: isNil(viz.strokeOpacity) ? 1 : viz.strokeOpacity,
      // styleParams lineType: "solid", "dashed" or "dotted"
      lineType: isNil(viz.lineType) ? "solid" : viz.lineType,
      // who draws it, so the swatch matches: GeoJSON on a canvas, or Earth
      // Engine's paint (outlines) or style (styleParams)
      paint: viz.layerType !== "geeVectorImage" ? "canvas" : isNil(viz.styleParams) ? "paint" : "style",
      // the geometry types present, once the layer has loaded (point, line, polygon)
      geoms: null,
    };
  }
  return null;
}

// port of 4map-manager.js buildLayer (viz handling). Resolves to
// {viz, legend, item}: `item` is the original object, or a FeatureCollection
// when a Feature or Geometry was given with no layerType.
// opts: name, nextColor (getColor), ee, and evaluateInfo(item, objType, givenInfo)
// -> Promise of the client-side object info (default: eeObjInfo + evaluate).
export async function prepareViz(item, vizIn, opts = {}) {
  const eeApi = opts.ee || globalThis.ee;
  const nextColor = opts.nextColor || defaultColorCycle;
  const evaluateInfo =
    opts.evaluateInfo ||
    ((obj, objType, given) => evaluateAsync(given ? eeApi.Dictionary(given) : eeObjInfo(obj, objType, eeApi)));
  const viz = { ...(vizIn || {}) };
  if (viz.styleParams) viz.styleParams = { ...viz.styleParams };
  viz.isTimeLapse = viz.isTimeLapse || false;
  const isEE = NON_EE_TYPES.indexOf(viz.layerType) === -1;

  // Object info: client-side when given as a plain object, else server-side (lazy).
  const infoIsClient = viz.eeObjInfo && typeof viz.eeObjInfo === "object" && !(eeApi && getObjType(viz.eeObjInfo, eeApi)) && typeof viz.eeObjInfo.evaluate !== "function";
  async function clientInfo() {
    if (infoIsClient) return viz.eeObjInfo;
    return evaluateInfo(item, reverseTypeLookup[viz.layerType] || getObjType(item, eeApi), viz.eeObjInfo || null);
  }

  if (viz.autoViz === true && isNil(viz.class_names) && isEE) {
    viz.eeObjInfo = await clientInfo();
    addClassVizDicts(viz);
  }

  if (isNil(viz.layerType)) {
    let eeType = getObjType(item, eeApi);
    if (eeType === "Feature") {
      item = eeApi.FeatureCollection([item]);
      eeType = "FeatureCollection";
    } else if (eeType === "Geometry") {
      item = eeApi.FeatureCollection([eeApi.Feature(item)]);
      eeType = "FeatureCollection";
    }
    viz.eeObjectType = eeType;
    viz.layerType = typeLookup[eeType];
  } else {
    viz.eeObjectType = reverseTypeLookup[viz.layerType];
  }

  if (viz.layerType === "geoJSONVector") viz.canQuery = false;

  if (viz.layerType === "geeVector" || viz.layerType === "geoJSONVector") {
    if (isNil(viz.strokeOpacity)) viz.strokeOpacity = 1;
    if (isNil(viz.fillOpacity)) viz.fillOpacity = 0.2;
    if (isNil(viz.fillColor)) viz.fillColor = "222222";
    if (isNil(viz.strokeColor)) viz.strokeColor = nextColor();
    if (isNil(viz.strokeWeight)) viz.strokeWeight = 3;
    viz.opacityRatio = viz.strokeOpacity / viz.fillOpacity;
    if (viz.fillColor.indexOf("#") == -1) viz.fillColor = "#" + viz.fillColor;
    if (viz.strokeColor.indexOf("#") == -1) viz.strokeColor = "#" + viz.strokeColor;
    if (isNil(viz.addToClassLegend)) viz.addToClassLegend = true;
  } else if (viz.layerType === "geeVectorImage") {
    if (!isNil(viz.styleParams)) {
      const sp = viz.styleParams;
      sp.color = sp.color || "000";
      sp.fillColor = sp.fillColor || "000A";
      sp.width = sp.width || 2;
      sp.lineType = sp.lineType || "solid";
      sp.pointSize = sp.pointSize || 3;
      sp.pointShape = sp.pointShape || "circle";
      sp.color = qcHex(sp.color);
      sp.fillColor = qcHex(sp.fillColor);
      viz.fillColor = sp.fillColor;
      viz.strokeColor = sp.color;
      viz.strokeWeight = sp.width;
      viz.lineType = sp.lineType;
    } else {
      viz.fillOpacity = 0;
      if (isNil(viz.fillColor)) viz.fillColor = "222222";
      if (isNil(viz.strokeColor)) viz.strokeColor = nextColor();
      if (isNil(viz.strokeWeight)) viz.strokeWeight = 2;
      if (isNil(viz.strokeOpacity)) viz.strokeOpacity = 1;
    }
    if (viz.fillColor.indexOf("#") == -1) viz.fillColor = "#" + viz.fillColor;
    if (viz.strokeColor.indexOf("#") == -1) viz.strokeColor = "#" + viz.strokeColor;
    if (isNil(viz.addToClassLegend)) {
      viz.addToClassLegend = true;
      viz.addToLegend = false;
    }
  }
  if (viz.bands !== undefined && typeof viz.bands === "string") viz.bands = viz.bands.split(",");
  if (viz.palette !== undefined && typeof viz.palette === "string") viz.palette = viz.palette.split(",");

  // AutoViz if specified
  if (viz.autoViz && viz.isTimeLapse === false && isEE) {
    if (!viz.eeObjInfo || !viz.eeObjInfo.bandNames) {
      viz.eeObjInfo = await clientInfo();
      addClassVizDicts(viz);
    }
    if (isNil(viz.bands)) viz.bands = viz.eeObjInfo.bandNames || [];
    viz.bands = viz.bands[0];
    const dicts = getLookupDicts(viz.bands, viz.class_values, viz.class_names, viz.class_palette, viz.includeClassValues);
    viz.classLegendDict = dicts.classLegendDict;
    viz.queryDict = dicts.queryDict;
  }

  return { viz, legend: legendFor(viz, opts.name), item };
}
