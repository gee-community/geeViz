// ArcGIS renderers drawn by Delta (js/esri/renderers.js, js/esri/symbols.js):
// which symbol each feature gets, visual variables, and the legend built
// from the renderer as the ArcGIS JS API builds it. Recorded drawingInfo.
import { test } from "node:test";
import assert from "node:assert/strict";
import { response } from "./esrifake.mjs";
import { rendererFor } from "../js/esri/renderers.js";
import { esriColor, glyphFor, ptToPx } from "../js/esri/symbols.js";
import { legendMarkup, isSymbolLegend, vectorGlyphs } from "../js/ui/legend.js";

const info = (name) => response(name);
const di = (name) => info(name).drawingInfo;

test("esriColor: [r, g, b, a] with a from 0 to 255", () => {
  assert.deepEqual(esriColor([247, 173, 164, 137]), { color: "#f7ada4", alpha: 137 / 255 });
  assert.equal(esriColor(null), null);
  assert.equal(ptToPx(3), 4);
});

test("unique values: each feature gets its value's symbol, others the default", () => {
  const d = di("drawinginfo_unique");
  const r = rendererFor(d, null, "esriGeometryPolygon");
  const infos = d.renderer.uniqueValueInfos;
  assert.equal(r.type, "uniqueValue");
  assert.deepEqual(r.fields, ["FeatureCategory"]);
  assert.equal(r.styleFor({ FeatureCategory: infos[0].value }).symbol, infos[0].symbol);
  assert.equal(r.styleFor({ FeatureCategory: infos[1].value }).symbol, infos[1].symbol);
  const def = d.renderer.defaultSymbol || null;
  const other = r.styleFor({ FeatureCategory: "something else" });
  assert.equal(other ? other.symbol : null, def);
  // several fields joined by the delimiter; numbers match their text
  const multi = rendererFor({ renderer: { type: "uniqueValue", field1: "a", field2: "b", fieldDelimiter: "|", uniqueValueInfos: [{ value: "1|x", symbol: { type: "esriSMS" }, label: "one x" }] } });
  assert.equal(multi.styleFor({ a: 1, b: "x" }).symbol.type, "esriSMS");
});

test("class breaks: a value at a break's max is in that break; normalization first", () => {
  const sym = (n) => ({ type: "esriSFS", style: "esriSFSSolid", color: [n, 0, 0, 255] });
  const renderer = { type: "classBreaks", field: "v", minValue: 0, classBreakInfos: [{ classMaxValue: 10, symbol: sym(1), label: "0 - 10" }, { classMaxValue: 20, symbol: sym(2), label: "10 - 20" }] };
  const r = rendererFor({ renderer });
  assert.equal(r.styleFor({ v: 10 }).symbol, renderer.classBreakInfos[0].symbol);
  assert.equal(r.styleFor({ v: 10.5 }).symbol, renderer.classBreakInfos[1].symbol);
  assert.equal(r.styleFor({ v: -1 }), null, "below minValue: not drawn");
  assert.equal(r.styleFor({ v: null }), null);
  const norm = rendererFor({ renderer: { ...renderer, normalizationType: "esriNormalizeByField", normalizationField: "d" } });
  assert.equal(norm.styleFor({ v: 30, d: 2 }).symbol, renderer.classBreakInfos[1].symbol);
  const pct = rendererFor({ renderer: { ...renderer, normalizationType: "esriNormalizeByPercentOfTotal", normalizationTotal: 200 } });
  assert.equal(pct.styleFor({ v: 30 }).symbol, renderer.classBreakInfos[1].symbol, "30 of 200 is 15%");
  // the recorded layer
  const cb = di("drawinginfo_classbreaks");
  const rec = rendererFor(cb);
  const first = cb.renderer.classBreakInfos[0];
  assert.equal(rec.styleFor({ prop_recov: first.classMaxValue }).symbol, first.symbol);
});

test("visual variables: color between stops, size from data, transparency, rotation", () => {
  const r = rendererFor(di("drawinginfo_visualvars"));
  const st = r.styleFor({ MEAN: 1.75 });
  // halfway between [255,244,181] at 1 and [254,153,41] at 2.5
  assert.equal(st.color.color, "#ffc76f");
  const size = rendererFor({ renderer: { type: "simple", symbol: { type: "esriSMS", style: "esriSMSCircle", size: 6 }, visualVariables: [{ type: "sizeInfo", field: "n", minDataValue: 0, maxDataValue: 100, minSize: 4, maxSize: 20 }] } });
  assert.equal(size.styleFor({ n: 0 }).size, 4);
  assert.equal(size.styleFor({ n: 50 }).size, 12);
  assert.equal(size.styleFor({ n: 500 }).size, 20);
  const tr = rendererFor({ renderer: { type: "simple", symbol: { type: "esriSMS" }, visualVariables: [{ type: "transparencyInfo", field: "t", stops: [{ value: 0, transparency: 0 }, { value: 10, transparency: 80 }] }] } });
  assert.ok(Math.abs(tr.styleFor({ t: 5 }).opacity - 0.6) < 1e-9);
  const rot = rendererFor({ renderer: { type: "simple", symbol: { type: "esriSMS" }, visualVariables: [{ type: "rotationInfo", field: "deg", rotationType: "geographic" }] } });
  assert.equal(rot.styleFor({ deg: 90 }).rotation, 90);
  const ari = rendererFor({ renderer: { type: "simple", symbol: { type: "esriSMS" }, visualVariables: [{ type: "rotationInfo", field: "deg", rotationType: "arithmetic" }] } });
  assert.equal(ari.styleFor({ deg: 0 }).rotation, 90, "arithmetic 0 is east: 90 clockwise from north");
});

test("the legend is built from the renderer: a glyph per class, ramps for color", () => {
  const r = rendererFor(di("drawinginfo_unique"), null, "esriGeometryPolygon");
  const lg = r.legend("Fires");
  const infos = di("drawinginfo_unique").renderer.uniqueValueInfos;
  assert.equal(lg.type, "symbols");
  assert.equal(lg.title, "Fires");
  assert.deepEqual(lg.items.slice(0, infos.length).map((i) => i.label), infos.map((i) => i.label));
  const g = lg.items[0].glyph;
  assert.equal(g.geom, "polygon");
  assert.equal(g.fill, esriColor(infos[0].symbol.color).color);
  assert.equal(g.stroke, esriColor(infos[0].symbol.outline.color).color);
  const vv = rendererFor(di("drawinginfo_visualvars")).legend("Hazard");
  assert.equal(vv.ramps.length, 1);
  assert.equal(vv.ramps[0].palette.length, 5);
  assert.deepEqual(vv.ramps[0].labels, ["0", "5"]);
  const html = legendMarkup(lg);
  assert.ok(html.includes('data-g="0"') && html.includes("Wildfire Daily Fire Perimeter"), html);
  assert.ok(legendMarkup(vv).includes('data-r="0"'));
});

test("a simple renderer is a symbol in the row, as a vector's is", () => {
  const lg = rendererFor(di("states_info")).legend("States");
  assert.equal(lg.items.length, 1);
  assert.ok(isSymbolLegend(lg));
  assert.equal(vectorGlyphs(lg).length, 1);
  assert.equal(vectorGlyphs(lg)[0].geom, "polygon");
  assert.ok(!isSymbolLegend(rendererFor(di("drawinginfo_unique")).legend("x")));
});

test("geeViz style keys replace the service's renderer", () => {
  const r = rendererFor(di("drawinginfo_unique"), { strokeColor: "ff0000", fillColor: "00ff00", fillOpacity: 0.5, strokeWeight: 3 }, "esriGeometryPolygon");
  assert.equal(r.type, "simple");
  const s = r.styleFor({}).symbol;
  assert.equal(s.type, "esriSFS");
  assert.equal(esriColor(s.color).color, "#00ff00");
  assert.ok(Math.abs(esriColor(s.color).alpha - 0.5) < 1 / 255);
  assert.equal(esriColor(s.outline.color).color, "#ff0000");
  assert.equal(ptToPx(s.outline.width), 3);
});

test("an Arcade expression draws with the default symbol and says so", () => {
  const r = rendererFor(di("drawinginfo_unique_size"), null, "esriGeometryPoint");
  const infos = di("drawinginfo_unique_size").renderer.uniqueValueInfos;
  const st = r.styleFor({ DailyAcres: 5 });
  assert.ok(st && st.symbol, "drawn");
  const lg = r.legend("Incidents");
  assert.deepEqual(lg.items.slice(0, infos.length).map((i) => i.label), infos.map((i) => i.label));
  assert.match(lg.note, /Arcade/);
  assert.equal(lg.items[0].glyph.image.slice(0, 22), "data:image/png;base64,");
});

test("glyphs for marker symbols and line styles", () => {
  assert.deepEqual(glyphFor({ type: "esriSMS", style: "esriSMSDiamond", color: [255, 0, 0, 255], size: 9, outline: { color: [0, 0, 0, 255], width: 1 } }, "point").shape, "diamond");
  assert.equal(glyphFor({ type: "esriSLS", style: "esriSLSDash", color: [0, 0, 255, 255], width: 2 }, "line").dash, "dashed");
  assert.equal(glyphFor({ type: "esriSFS", style: "esriSFSNull", outline: { type: "esriSLS", color: [0, 0, 0, 255], width: 1 } }, "polygon").fill, null);
});

test("every recorded renderer builds, with a label on every legend item", () => {
  for (const n of ["states_info", "mtbs63_info", "drawinginfo_unique", "drawinginfo_unique_size", "drawinginfo_classbreaks", "drawinginfo_visualvars"]) {
    const r = rendererFor(di(n), null, info(n).geometryType);
    const lg = r.legend(n);
    assert.ok(lg.items.length > 0, n);
    lg.items.forEach((it) => assert.equal(typeof it.label, "string", n));
  }
});
