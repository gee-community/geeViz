// A grouped wind layer (geeViz.weather.addWindLayer) in Delta: the legend is
// the speed ramp with a particle crossing it, and the layer has a second
// opacity slider for the particles, as in the original viewer.
import { test } from "node:test";
import assert from "node:assert/strict";
import { legendFor, windLegend, particleOpacityFor } from "../js/engine/viz.js";
import { legendMarkup, swatchColors, cometGradient, hexRgb } from "../js/ui/legend.js";
import { createWind, adoptedKey } from "../js/engine/wind.js";
import { createStore } from "../js/state.js";
import { createMapApi } from "../js/api.js";

// What geeViz.weather._group_wind_vizzes sends (the keys this code reads).
const grouped = (p = {}) => ({
  windParticles: true,
  windSpeedRaster: true,
  windSpeedPalette: ["#6271b7", "39a3ae", "#c1c1c1"],
  windRampMin: 0,
  windRampMax: 34,
  windUnits: "mi/hr",
  particleColor: "#ffcc00",
  opacity: 0.6,
  windParticleDim: 0.8,
  addToLegend: true,
  classLegendDict: { "Wind speed 0-34 mi/hr": "linear-gradient(90deg, red, blue)" },
  ...p,
});

test("windLegend: a grouped wind layer's legend is the speed ramp with its ends, not the class chip", () => {
  const l = legendFor(grouped(), "Wind");
  assert.equal(l.type, "ramp");
  assert.equal(l.wind, true);
  assert.deepEqual(l.palette, ["#6271b7", "#39a3ae", "#c1c1c1"]);
  assert.deepEqual(l.labels, ["0", "34 mi/hr"]);
  assert.equal(l.particle, "#ffcc00");
  assert.equal(l.title, "Wind");
  // the toggle's swatch is the ramp
  assert.deepEqual(swatchColors(l), { kind: "ramp", colors: l.palette });
});

test("windLegend: only the grouped kind, and only with a ramp to draw", () => {
  // the particle-only layer keeps its class chip (as in the original)
  assert.equal(windLegend(grouped({ windSpeedRaster: false })), null);
  assert.equal(legendFor(grouped({ windSpeedRaster: false }), "W").type, "classes");
  assert.equal(windLegend({ min: 0, max: 1, palette: "000,fff" }), null);
  assert.equal(windLegend(grouped({ windSpeedPalette: ["#fff"] })), null);
  assert.equal(windLegend(grouped({ windRampMax: undefined })), null);
  assert.equal(windLegend(grouped({ addToLegend: false })), null);
  // no units: the bare number
  assert.deepEqual(windLegend(grouped({ windUnits: "" })).labels, ["0", "34"]);
  // no particle color: white, the client's default
  assert.equal(windLegend(grouped({ particleColor: undefined })).particle, "#fff");
});

test("legendMarkup: the wind ramp carries the particle; labels escaped", () => {
  const html = legendMarkup(windLegend(grouped({ windUnits: "<b>" })));
  assert.match(html, /<span class="ramp wind-ramp" data-c="ramp"><i class="wind-comet" data-c="comet"><\/i><\/span>/);
  assert.match(html, /<span>34 &lt;b&gt;<\/span>/);
  // an ordinary ramp has no particle
  assert.doesNotMatch(legendMarkup({ type: "ramp", palette: ["#000", "#fff"], labels: ["0", "1"] }), /comet/);
});

test("cometGradient: a trail fading in to the head, in the particle color", () => {
  assert.equal(cometGradient("#ffcc00"), "linear-gradient(90deg, rgba(255,204,0,0), rgba(255,204,0,.95))");
  assert.deepEqual(hexRgb("#fc0"), [255, 204, 0]);
  assert.deepEqual(hexRgb("nonsense"), [255, 255, 255]);
  assert.deepEqual(hexRgb(undefined), [255, 255, 255]);
});

test("particleOpacityFor: windParticleDim, else opacity, else 1, clamped; none for other layers", () => {
  assert.equal(particleOpacityFor(grouped()), 0.8);
  assert.equal(particleOpacityFor(grouped({ windParticleDim: undefined })), 0.6);
  assert.equal(particleOpacityFor(grouped({ windParticleDim: undefined, opacity: undefined })), 1);
  assert.equal(particleOpacityFor(grouped({ windParticleDim: 3 })), 1);
  assert.equal(particleOpacityFor(grouped({ windSpeedRaster: false })), undefined);
  assert.equal(particleOpacityFor({ opacity: 0.5 }), undefined);
});

test("addLayer: a grouped wind layer starts with both opacities; others have no particle opacity", () => {
  const store = createStore();
  const api = createMapApi(store, {});
  api.addLayer({}, grouped(), "Wind", true);
  api.addLayer({}, { opacity: 0.5 }, "Plain", true);
  const [w, p] = store.get().layers;
  assert.equal(w.opacity, 0.6);
  assert.equal(w.particleOpacity, 0.8);
  assert.equal("particleOpacity" in p, false);
});

test("createWind: the particle slider reaches wind-particles.js as particleDim, under the adopted key", () => {
  const src = (p) => ({ viz: { windParticles: true }, visible: true, opacity: 1, slot: 0, tileUrl: () => "u", ready: true, shown: true, frames: [], ...p });
  const sources = [
    src({ id: "layer-1", timelapse: false }),
    src({ id: "layer-2", timelapse: true, tileUrl: null, frames: [{ tileUrl: () => "f", opacity: 1 }] }),
  ];
  assert.equal(adoptedKey(sources[0]), "layer-1");
  assert.equal(adoptedKey(sources[1]), "tl:layer-2");
  const listeners = new Set();
  const layers = { windSources: () => sources, onChange: (fn) => (listeners.add(fn), () => listeners.delete(fn)) };
  const adopted = { "layer-1": { particleDim: 1 }, "tl:layer-2": { particleDim: 1 } };
  const dimAtRefresh = [];
  const wp = { _adopted: adopted, scan() {}, _refreshRunState: () => dimAtRefresh.push([adopted["layer-1"].particleDim, adopted["tl:layer-2"].particleDim]) };
  const dims = { "layer-1": 0.3, "layer-2": 0.55 };
  const w = createWind(layers, {}, { particles: () => wp, particleOpacity: (id) => dims[id] });
  // set before the refresh that paints with it
  assert.deepEqual(dimAtRefresh, [[0.3, 0.55]]);
  dims["layer-1"] = 0.9;
  w.update();
  assert.deepEqual(dimAtRefresh[1], [0.9, 0.55]);
  // a layer without the slider is left as wind-particles.js set it
  delete dims["layer-1"];
  w.update();
  assert.equal(adopted["layer-1"].particleDim, 0.9);
});
