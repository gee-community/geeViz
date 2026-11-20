import { test } from "node:test";
import assert from "node:assert/strict";
import { windEntries, createWind, frameKey } from "../js/engine/wind.js";

const url = (tag) => (c, z) => `https://t/${tag}/${z}/${c.x}/${c.y}`;

function fakeLayers(sources) {
  const f = { sources, listeners: new Set(), loading: [] };
  f.windSources = () => f.sources;
  f.onChange = (fn) => {
    f.listeners.add(fn);
    return () => f.listeners.delete(fn);
  };
  f.fire = () => f.listeners.forEach((fn) => fn());
  f.setLayerLoading = (id, v) => f.loading.push([id, v]);
  f.progress = [];
  f.setLayerProgress = (id, v) => f.progress.push([id, v]);
  return f;
}

const single = (p = {}) => ({ id: "layer-1", viz: { windParticles: true }, visible: true, opacity: 0.7, slot: 2, timelapse: false, tileUrl: url("a"), ready: true, shown: true, frames: [], ...p });
const lapse = (p = {}) => ({
  id: "layer-2",
  viz: { windParticles: true },
  visible: true,
  opacity: 1,
  slot: 4,
  timelapse: true,
  tileUrl: null,
  ready: true,
  shown: true,
  frames: [
    { tileUrl: url("f0"), opacity: 0 },
    { tileUrl: url("f1"), opacity: 1 },
    { tileUrl: url("f2"), opacity: 0 },
  ],
  ...p,
});

test("windEntries: a single layer is one record at its slot, without a timeLapseID", () => {
  const e = windEntries([single({ viz: { windParticles: true, timeLapseID: "x" } })]);
  assert.deepEqual(Object.keys(e), ["layer-1"]);
  assert.equal(e["layer-1"].slot, 2);
  assert.equal(e["layer-1"].visible, true);
  assert.equal(e["layer-1"].opacity, 0.7);
  assert.equal(e["layer-1"].viz.timeLapseID, undefined);
});

test("windEntries: a timelapse is one record per frame, in year order, grouped by its id", () => {
  const e = windEntries([lapse()]);
  const keys = Object.keys(e);
  assert.deepEqual(keys, [0, 1, 2].map((i) => frameKey("layer-2", i)));
  keys.forEach((k, i) => {
    assert.equal(e[k].viz.timeLapseID, "layer-2");
    assert.equal(e[k].slot, 4 + i);
    assert.equal(e[k].visible, true);
  });
  assert.deepEqual(keys.map((k) => e[k].opacity), [0, 1, 0]);
});

test("windEntries: nothing until ready; a hidden timelapse's frames are not visible", () => {
  assert.deepEqual(windEntries([lapse({ ready: false }), single({ tileUrl: null, ready: false })]), {});
  const e = windEntries([lapse({ shown: false })]);
  assert.ok(Object.values(e).every((r) => r.visible === false));
});

test("createWind keeps the registry in step, in place, and tells wind-particles", () => {
  const layers = fakeLayers([single()]);
  const reg = {};
  const calls = [];
  const wp = { scan: () => calls.push("scan"), _refreshRunState: () => calls.push("refresh") };
  createWind(layers, reg, { particles: () => wp });
  const rec = reg["layer-1"];
  assert.ok(rec);
  assert.equal(rec.layerId, 2);
  assert.equal(rec.visible, true);
  assert.equal(rec.viz.windParticles, true);
  // getTileUrl is a plain property, as wind-particles.js looks for it first.
  assert.equal(rec.layer.getTileUrl({ x: 1, y: 2 }, 3), "https://t/a/3/1/2");
  assert.deepEqual(calls, ["scan", "refresh"]);

  // Toggled off and moved: the same record object changes.
  layers.sources = [single({ visible: false, slot: 0 })];
  layers.fire();
  assert.equal(reg["layer-1"], rec);
  assert.equal(rec.visible, false);
  assert.equal(rec.layerId, 0);

  // Removed: gone from the registry.
  layers.sources = [];
  layers.fire();
  assert.deepEqual(Object.keys(reg), []);
});

test("createWind: loading and percent written by wind-particles reach the layer row", () => {
  const layers = fakeLayers([single(), lapse()]);
  const reg = {};
  createWind(layers, reg, { particles: () => null });
  reg["layer-1"].loading = true;
  reg["layer-1"].percent = 40;
  // a frame's record is not where a timelapse reports
  reg[frameKey("layer-2", 0)].loading = true;
  reg[frameKey("layer-2", 0)].percent = 10;
  assert.deepEqual(layers.loading, [["layer-1", true]]);
  assert.deepEqual(layers.progress, [["layer-1", 40]]);
  assert.equal(reg["layer-1"].loading, true);
  assert.equal(reg["layer-1"].percent, 40);
});

test("createWind: a timelapse reports under tl:<id>, a record scan() cannot list", () => {
  const layers = fakeLayers([lapse({ shown: false })]);
  const reg = {};
  createWind(layers, reg, { particles: () => null });
  const g = reg["tl:layer-2"];
  assert.ok(g);
  assert.equal(Object.keys(reg).includes("tl:layer-2"), false);
  for (const k in reg) assert.notEqual(k, "tl:layer-2");
  // wind-particles.js reads visible off it (hidden reports 0)
  assert.equal(g.visible, false);
  layers.sources = [lapse({ shown: true })];
  layers.fire();
  assert.equal(reg["tl:layer-2"], g);
  assert.equal(g.visible, true);
  g.loading = true;
  g.percent = 65;
  assert.deepEqual(layers.loading, [["layer-2", true]]);
  assert.deepEqual(layers.progress, [["layer-2", 65]]);
  assert.equal(g.percent, 65);
  // removed with its layer
  layers.sources = [];
  layers.fire();
  assert.equal(reg["tl:layer-2"], undefined);
});

test("createWind leaves records it did not make alone", () => {
  const layers = fakeLayers([]);
  const reg = { other: { viz: {} } };
  createWind(layers, reg, { particles: () => null });
  layers.fire();
  assert.ok(reg.other);
});

import { windQueryItem, WIND_UNIT_PROPS } from "../js/engine/wind.js";

test("windQueryItem: a wind layer's serialized speed/direction object, decoded; null otherwise", () => {
  const seen = [];
  const ee = { Deserializer: { fromJSON: (s) => (seen.push(s), { decoded: s }), decode: (o) => ({ decodedObj: o }) } };
  assert.deepEqual(windQueryItem({ windParticles: true, windQueryItem: '{"result":"0"}' }, ee), { decoded: '{"result":"0"}' });
  assert.deepEqual(windQueryItem({ windParticles: true, windQueryItem: { result: "0" } }, ee), { decodedObj: { result: "0" } });
  const live = { evaluate() {} };
  assert.equal(windQueryItem({ windParticles: true, windQueryItem: live }, ee), live);
  assert.equal(windQueryItem({ windQueryItem: '{"result":"0"}' }, ee), null);
  assert.equal(windQueryItem({ windParticles: true }, ee), null);
  assert.equal(windQueryItem(null, ee), null);
  assert.deepEqual(seen, ['{"result":"0"}']);
  assert.deepEqual(WIND_UNIT_PROPS, { speed: "wind_units", direction: "wind_direction_units" });
});
