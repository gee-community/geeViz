import { test } from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../js/state.js";
import { createTimelapse, frameOpacities, wrapFrame, uniqueYears, fpsToInterval, DEFAULT_FPS } from "../js/engine/timelapse.js";

const YEARS = ["2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023"];

test("frameOpacities: single frame, or every frame up to the current one when cumulative", () => {
  assert.deepEqual(frameOpacities(4, 2, false, 0.8), [0, 0, 0.8, 0]);
  assert.deepEqual(frameOpacities(4, 2, true, 0.8), [0.8, 0.8, 0.8, 0]);
  assert.deepEqual(frameOpacities(4, 0, true, 1), [1, 0, 0, 0]);
});

test("wrapFrame wraps both ways; uniqueYears keeps first-seen order; fps", () => {
  assert.equal(wrapFrame(-1, 9), 8);
  assert.equal(wrapFrame(9, 9), 0);
  assert.equal(wrapFrame(4, 9), 4);
  assert.deepEqual(uniqueYears(["2015", "2015", "2016", 2016, "2017"]), ["2015", "2016", "2017"]);
  assert.equal(fpsToInterval(2), 500);
  // the original's intervalPeriod 666.67 ms
  assert.equal(DEFAULT_FPS, 1.5);
});

// ---- controller against a fake engine, loader and timers ----
function fakeTimers() {
  const t = { live: new Map(), next: 1 };
  t.setInterval = (fn, ms) => {
    const id = t.next++;
    t.live.set(id, { fn, ms });
    return id;
  };
  t.clearInterval = (id) => t.live.delete(id);
  t.tick = (n = 1) => {
    for (let i = 0; i < n; i++) [...t.live.values()].forEach((x) => x.fn());
  };
  return t;
}

function deferred() {
  let resolve;
  const p = new Promise((r) => (resolve = r));
  return { p, resolve };
}

function fakeLoader(years = YEARS) {
  const frames = years.map(() => deferred());
  const yearsD = deferred();
  return {
    frames,
    resolveYears: () => yearsD.resolve(years),
    resolveAll: () => frames.forEach((f, i) => f.resolve("url-" + i)),
    loader: () => ({
      years: () => yearsD.p,
      frame: (i) => frames[i].p,
      legend: null,
    }),
  };
}

function setup({ visible = true, others = [], turnOff = true } = {}) {
  const store = createStore();
  const tl = { id: "tl-1", name: "TL", kind: "timelapse", visible, opacity: 1, timelapse: {}, legendOpen: false };
  const layers = [tl, ...others];
  store.set({ layers, order: layers.map((l) => l.id), turnOffLayersWhenTimeLapseIsOn: turnOff });
  const calls = { shown: [], init: [], urls: [], ready: [], jitter: 0 };
  const engine = {
    store,
    initFrames: (id, n) => calls.init.push([id, n]),
    setFrameUrl: (id, i, url) => calls.urls.push([id, i, url]),
    framesReady: (id) => calls.ready.push(id),
    showFrames: (id, ops) => calls.shown.push([id, ops]),
    jitter: () => calls.jitter++,
    fail: (id, e) => calls.fail = e,
  };
  const timers = fakeTimers();
  const fl = fakeLoader();
  const ctl = createTimelapse(engine, tl, { timers, loader: fl.loader });
  // The layer engine forwards store visibility changes to the controller,
  // comparing with its own record as layers.js setLayerVisible does.
  let recVisible = visible;
  store.on("change:layers", (ls) => {
    const l = ls.find((x) => x.id === "tl-1");
    if (l && l.visible !== recVisible) {
      recVisible = l.visible;
      ctl.setVisible(l.visible);
    }
  });
  return { store, ctl, calls, timers, fl, layer: () => store.get().layers.find((l) => l.id === "tl-1") };
}

const flush = () => new Promise((r) => setTimeout(r, 0));
const lastShown = (calls) => (calls.shown.length ? calls.shown[calls.shown.length - 1][1] : undefined);

async function loaded(s) {
  s.fl.resolveYears();
  await flush();
  s.fl.resolveAll();
  await flush();
  await flush();
}

test("load: years, one frame slot each, ready after every frame, first frame shown", async () => {
  const s = setup();
  s.fl.resolveYears();
  await flush();
  assert.deepEqual(s.layer().timelapse.years, YEARS);
  assert.deepEqual(s.calls.init, [["tl-1", 9]]);
  assert.equal(s.layer().timelapse.loaded, false);
  assert.equal(s.calls.shown.length, 0, "nothing is drawn while frames load");
  s.fl.resolveAll();
  await flush();
  await flush();
  assert.equal(s.layer().timelapse.loaded, true);
  assert.equal(s.calls.urls.length, 9);
  assert.deepEqual(s.calls.ready, ["tl-1"]);
  assert.deepEqual(lastShown(s.calls), [1, 0, 0, 0, 0, 0, 0, 0, 0]);
  assert.equal(s.layer().timelapse.frame, 0);
  assert.equal(s.layer().timelapse.playing, false);
});

test("toggle during load: off before loaded stays off after load, no frame drawn", async () => {
  const s = setup();
  s.fl.resolveYears();
  await flush();
  s.store.update((st) => ({ ...st, layers: st.layers.map((l) => ({ ...l, visible: false })) }), "toggle");
  s.fl.resolveAll();
  await flush();
  await flush();
  assert.equal(s.layer().timelapse.loaded, true);
  assert.equal(s.layer().visible, false);
  assert.ok(s.calls.shown.every(([, ops]) => ops === null), JSON.stringify(s.calls.shown));
});

test("toggle during load: on before loaded (from off) shows after load", async () => {
  const s = setup({ visible: false, others: [other("a", { visible: false })] });
  s.store.update((st) => ({ ...st, layers: st.layers.map((l) => ({ ...l, visible: true })) }), "toggle");
  assert.equal(s.calls.shown.length, 0);
  // The choice is only recorded: other layers stay on until the frames load.
  assert.equal(s.store.get().layers.find((l) => l.id === "a").visible, true);
  await loaded(s);
  assert.deepEqual(lastShown(s.calls), [1, 0, 0, 0, 0, 0, 0, 0, 0]);
  // Applied at load as the user's choice (timelapse-toggle.js reconcile calls timeLapseCheckbox).
  assert.equal(s.store.get().layers.find((l) => l.id === "a").visible, false);
});

test("play advances one frame per tick at 1000/fps ms; pause stops; step wraps", async () => {
  const s = setup();
  await loaded(s);
  s.ctl.play(2);
  const [timer] = [...s.timers.live.values()];
  assert.equal(timer.ms, 500);
  assert.equal(s.layer().timelapse.playing, true);
  assert.equal(s.layer().timelapse.fps, 2);
  s.timers.tick(3);
  assert.equal(s.layer().timelapse.frame, 3);
  assert.equal(lastShown(s.calls)[3], 1);
  s.ctl.pause();
  assert.equal(s.timers.live.size, 0);
  assert.equal(s.layer().timelapse.playing, false);
  s.timers.tick(2);
  assert.equal(s.layer().timelapse.frame, 3);
  s.ctl.setFrame(0);
  s.ctl.step(-1);
  assert.equal(s.layer().timelapse.frame, 8);
  s.ctl.step(1);
  assert.equal(s.layer().timelapse.frame, 0);
  // play wraps from the last frame to the first
  s.ctl.setFrame(8);
  s.ctl.play();
  s.timers.tick(1);
  assert.equal(s.layer().timelapse.frame, 0);
  // step pauses, as the original's forwardOneFrame does
  s.ctl.step(1);
  assert.equal(s.layer().timelapse.playing, false);
  assert.equal(s.timers.live.size, 0);
});

test("cumulative shows every frame up to the current one", async () => {
  const s = setup();
  await loaded(s);
  s.ctl.setFrame(3);
  s.ctl.setCumulative(true);
  assert.equal(s.layer().timelapse.cumulative, true);
  assert.deepEqual(lastShown(s.calls), [1, 1, 1, 1, 0, 0, 0, 0, 0]);
  s.ctl.setCumulative(false);
  assert.deepEqual(lastShown(s.calls), [0, 0, 0, 1, 0, 0, 0, 0, 0]);
});

test("off pauses and takes the frames off the map", async () => {
  const s = setup();
  await loaded(s);
  s.ctl.play(2);
  s.store.update((st) => ({ ...st, layers: st.layers.map((l) => (l.id === "tl-1" ? { ...l, visible: false } : l)) }), "toggle");
  assert.equal(s.layer().timelapse.playing, false);
  assert.equal(s.timers.live.size, 0);
  assert.equal(lastShown(s.calls), null);
});

const other = (id, extra = {}) => ({ id, name: id, kind: "ee", visible: true, opacity: 1, ...extra });

test("turning a timelapse on turns other layers off when the setting is true", async () => {
  const s = setup({ visible: false, others: [other("a"), other("sel", { kind: "select" })] });
  await loaded(s);
  s.store.update((st) => ({ ...st, layers: st.layers.map((l) => (l.id === "tl-1" ? { ...l, visible: true } : l)) }), "toggle");
  const byId = (id) => s.store.get().layers.find((l) => l.id === id);
  assert.equal(byId("a").visible, false);
  assert.equal(byId("sel").visible, true, "select layers are not in the layer list");
});

test("the setting false leaves other layers on; the initial show at load never turns them off", async () => {
  const s = setup({ visible: false, others: [other("a")], turnOff: false });
  await loaded(s);
  s.store.update((st) => ({ ...st, layers: st.layers.map((l) => (l.id === "tl-1" ? { ...l, visible: true } : l)) }), "toggle");
  assert.equal(s.store.get().layers.find((l) => l.id === "a").visible, true);
  const s2 = setup({ visible: true, others: [other("a")] });
  await loaded(s2);
  assert.equal(s2.store.get().layers.find((l) => l.id === "a").visible, true);
});

test("only one timelapse plays: turning one on turns the other timelapses off", async () => {
  const s = setup({ visible: false, others: [other("tl-2", { kind: "timelapse", timelapse: {} })], turnOff: false });
  await loaded(s);
  s.store.update((st) => ({ ...st, layers: st.layers.map((l) => (l.id === "tl-1" ? { ...l, visible: true } : l)) }), "toggle");
  assert.equal(s.store.get().layers.find((l) => l.id === "tl-2").visible, false);
});

test("refresh jitters the zoom; controls do nothing before load", async () => {
  const s = setup();
  s.ctl.play(2);
  assert.equal(s.timers.live.size, 0);
  s.ctl.refresh();
  assert.equal(s.calls.jitter, 1);
});
