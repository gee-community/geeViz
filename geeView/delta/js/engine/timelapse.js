// Timelapses: one map frame per year (or per advanceInterval), loading
// tracking, play/pause/stop, back and forward one frame, speed in frames per
// second, cumulative mode, tile refresh, and turning other layers off.
//
// port of lcms-viewer 4map-manager.js addTimeLapseToMap and its helpers
// (selectFrame, playTimeLapse, pauseTimeLapse, pauseButtonFunction,
// forwardOneFrame, backOneFrame, setSpeed, stopTimeLapse, clearAllFrames,
// turnOffAllNonActiveTimeLapseLayers, toggleCumulativeMode, jitterZoom,
// timeLapseCheckbox), as bundled unchanged in geeView/src/js/lcms-viewer.min.js
// (no LOCAL PATCH touches them), plus the behavior of
// geeView/src/js/timelapse-toggle.js: the toggle works while frames load, and
// the choice is applied when loading completes.
//
// The controller never touches the DOM or overlayMapTypes. It drives the layer
// engine (engine/layers.js) through frame hooks, so frames are stacked by the
// same sync() as every other layer and z-order stays list order:
//   engine.initFrames(id, n)        allocate n frame slots (bottom = first year)
//   engine.setFrameUrl(id, i, url)  frame i has a map service
//   engine.framesReady(id)          every frame has its service
//   engine.showFrames(id, ops|null) per-frame opacities, or null: off the map
//   engine.jitter()                 jitterZoom
//   engine.fail(id, err)
// State lives in the store at layer.timelapse = {years, frame, playing, fps,
// cumulative, loaded, nLoaded}.
import { prepareViz } from "./viz.js";
import { windQueryItem, WIND_UNIT_PROPS } from "./wind.js";

// port of 4map-manager.js intervalPeriod (666.67 ms) as frames per second
export const DEFAULT_FPS = 1.5;
export const fpsToInterval = (fps) => 1000 / fps;

export function wrapFrame(i, n) {
  if (n <= 0) return 0;
  return ((i % n) + n) % n;
}

// port of 4map-manager.js selectFrame frame opacities: the current frame, or
// in cumulative mode every frame up to and including it.
export function frameOpacities(n, frame, cumulative, opacity) {
  const out = [];
  for (let i = 0; i < n; i++) out.push(i === frame || (cumulative && i < frame) ? opacity : 0);
  return out;
}

// port of the original's unique() on the formatted dates: first-seen order.
export function uniqueYears(list) {
  const out = [];
  (list || []).forEach((y) => {
    const s = String(y);
    if (out.indexOf(s) === -1) out.push(s);
  });
  return out;
}

const evaluateAsync = (obj) =>
  new Promise((resolve, reject) => obj.evaluate((v, err) => (err ? reject(new Error(err)) : resolve(v))));

// Earth Engine side of addTimeLapseToMap: deserialize, viz (autoViz legend),
// years, and one image and map service per year. Returns
// {prepare(), years(), frame(i)}: frame(i) resolves to the tile url format.
export function eeFrameLoader(engine, layer) {
  const eeApi = engine.ee || globalThis.ee;
  let item = layer.item;
  const vizIn = { ...(layer.viz || {}) };
  if (vizIn.serialized === true) {
    item = eeApi.Deserializer.decode(item);
    vizIn.serialized = false;
  }
  item = eeApi.ImageCollection(item);
  if (vizIn.mosaic === null || vizIn.mosaic === undefined) vizIn.mosaic = false;
  if (vizIn.dateFormat === null || vizIn.dateFormat === undefined) vizIn.dateFormat = "YYYY";
  vizIn.advanceInterval = vizIn.advanceInterval || "year";
  if (vizIn.dateField === null || vizIn.dateField === undefined) vizIn.dateField = "system:time_start";
  if (vizIn.opacity === undefined || vizIn.opacity === null) vizIn.opacity = 1;
  // The collection's viz and legend (the original's autoViz block in addTimeLapseToMap).
  vizIn.layerType = "geeImageCollection";

  let viz = null;
  let years = null;
  const preparing = prepareViz(item, vizIn, { name: layer.name, ee: eeApi }).then((p) => {
    viz = { ...p.viz, layerType: "geeImage", isTimeLapse: true, canQuery: false };
    return p;
  });

  // port of 4map-manager.js fillEmptyCollections
  const fillEmpty = (c, dummy) =>
    eeApi.ImageCollection(eeApi.Algorithms.If(c.toList(1).length().gt(0), c, eeApi.ImageCollection([dummy.mask(eeApi.Image(0))])));

  function frameImage(yr) {
    const d = eeApi.Date.parse(viz.dateFormat, String(yr));
    const dummy = eeApi.Image(item.first());
    let c;
    if (viz.dateField !== "system:time_start") {
      c = item.filter(eeApi.Filter.gte(viz.dateField, d.millis()));
      c = c.filter(eeApi.Filter.lt(viz.dateField, d.advance(1, viz.advanceInterval).millis()));
      c = fillEmpty(c, dummy);
    } else {
      c = fillEmpty(item.filterDate(d, d.advance(1, viz.advanceInterval)), dummy);
    }
    const img = viz.mosaic ? eeApi.Image(c.mosaic()) : eeApi.Image(c.first());
    return img.set("system:time_start", d.millis()).copyProperties(c.first());
  }

  return {
    prepare: () => preparing,
    async years() {
      await preparing;
      if (Array.isArray(viz.years) && viz.years.length) years = viz.years.map(String);
      else {
        const list = item
          .sort(viz.dateField, true)
          .toList(10000, 0)
          .map((img) => eeApi.Date(eeApi.Image(img).get(viz.dateField)).format(viz.dateFormat));
        years = uniqueYears(await evaluateAsync(list));
      }
      return years;
    },
    frame(i) {
      return new Promise((resolve, reject) => {
        engine.requestMap(frameImage(years[i]), viz, (url, err) => (err ? reject(err) : resolve(url)));
      });
    },
  };
}

const ROWLESS = ["select", "areaChartOnly"];

export function createTimelapse(engine, layer, opts = {}) {
  const store = engine.store;
  const id = layer.id;
  const timers = opts.timers || { setInterval: (f, ms) => setInterval(f, ms), clearInterval: (t) => clearInterval(t) };
  const loader = (opts.loader || eeFrameLoader)(engine, layer);

  // Timelapses start off (api.js, as addTimeLapseToMap). A toggle while
  // frames load only records the choice (timelapse-toggle.js INTENT).
  let visible = !!layer.visible;
  let shown = false;
  const failed = new Set();
  let firstError = null;
  let timer = null;
  let disposed = false;
  const st = {
    years: [],
    frame: 0,
    playing: false,
    fps: DEFAULT_FPS,
    cumulative: false,
    loaded: false,
    nLoaded: 0,
    failed: [],
    ...(layer.timelapse || {}),
  };

  const current = () => store.get().layers.find((l) => l.id === id);
  function patch(p, reason) {
    Object.assign(st, p);
    if (disposed || !current()) return;
    store.update(
      (s) => ({ ...s, layers: s.layers.map((l) => (l.id === id ? { ...l, timelapse: { ...st } } : l)) }),
      reason || "timelapse"
    );
  }
  const setVisibleIn = (pred, v, reason) =>
    store.update((s) => ({ ...s, layers: s.layers.map((l) => (pred(l) && l.visible !== v ? { ...l, visible: v } : l)) }), reason);

  function render() {
    const l = current();
    if (!st.loaded || !visible || !l) return;
    shown = true;
    engine.showFrames(id, frameOpacities(st.years.length, st.frame, st.cumulative, l.opacity));
  }
  function hide() {
    if (!shown) return;
    shown = false;
    engine.showFrames(id, null);
  }
  function clearTimer() {
    if (timer !== null) timers.clearInterval(timer);
    timer = null;
  }

  // port of 5chart-manager.js turnOffLayers, as selectFrame calls it.
  function turnOffOtherLayers() {
    if (!store.get().turnOffLayersWhenTimeLapseIsOn) return;
    const others = (l) => l.id !== id && l.kind !== "timelapse" && ROWLESS.indexOf(l.kind) === -1;
    if (store.get().layers.some((l) => others(l) && l.visible)) setVisibleIn(others, false, "turnOffLayersWhenTimeLapseIsOn");
  }
  // port of 4map-manager.js turnOffAllNonActiveTimeLapseLayers
  function turnOffOtherTimelapses() {
    const others = (l) => l.id !== id && l.kind === "timelapse";
    if (store.get().layers.some((l) => others(l) && l.visible)) setVisibleIn(others, false, "timelapse-exclusive");
  }

  // port of 4map-manager.js selectFrame
  function selectFrame(i) {
    st.frame = wrapFrame(i, st.years.length);
    turnOffOtherLayers();
    patch({ frame: st.frame }, "timelapse-frame");
    render();
  }

  // Turning on (port of timeLapseCheckbox -> pauseButtonFunction).
  function activate() {
    turnOffOtherTimelapses();
    selectFrame(st.frame);
  }

  // The other direction (port of 2templates.js addLayer turnOn ->
  // turnOffTimeLapseCheckboxes): a layer in the list turned on turns a visible
  // timelapse off when the setting is true, so playback does not switch the
  // user's layer straight back off.
  const listLayer = (l) => l.id !== id && l.kind !== "timelapse" && ROWLESS.indexOf(l.kind) === -1;
  let prevVisible = new Map(store.get().layers.filter(listLayer).map((l) => [l.id, !!l.visible]));
  const unsubscribe = store.on("change:layers", () => {
    const layers = store.get().layers.filter(listLayer);
    const turnedOn = layers.some((l) => l.visible && prevVisible.get(l.id) === false);
    prevVisible = new Map(layers.map((l) => [l.id, !!l.visible]));
    if (turnedOn && visible && store.get().turnOffLayersWhenTimeLapseIsOn) {
      ctl.pause();
      setVisibleIn((l) => l.id === id, false, "turnOffTimeLapseCheckboxes");
    }
  });

  // port of 4map-manager.js stopTimeLapse (the off side of timeLapseCheckbox)
  function deactivate() {
    clearTimer();
    if (st.playing) patch({ playing: false }, "timelapse-pause");
    hide();
  }

  // Controls act only on a loaded timelapse (the original's isReady). Playing
  // or picking a frame turns the timelapse on (turnOnTimeLapseLayers).
  function ensureOn() {
    if (!visible) setVisibleIn((l) => l.id === id, true, "timelapse-on");
  }

  const ctl = {
    setVisible(on) {
      on = !!on;
      if (on === visible) return;
      visible = on;
      if (!st.loaded) return;
      if (on) activate();
      else deactivate();
    },
    setFrame(i) {
      if (!st.loaded) return;
      ctl.pause();
      ensureOn();
      selectFrame(i);
    },
    step(delta) {
      if (!st.loaded) return;
      ctl.setFrame(st.frame + delta);
    },
    // port of 4map-manager.js playTimeLapse and setSpeed
    play(fps) {
      if (!st.loaded) return;
      if (fps !== undefined && fps !== null && Number(fps) > 0) st.fps = Number(fps);
      clearTimer();
      ensureOn();
      patch({ playing: true, fps: st.fps }, "timelapse-play");
      selectFrame(st.frame);
      timer = timers.setInterval(() => selectFrame(st.frame + 1), fpsToInterval(st.fps));
    },
    pause() {
      clearTimer();
      if (st.playing) patch({ playing: false }, "timelapse-pause");
    },
    // Speed changes restart a playing timelapse and only set the speed of a paused one.
    setSpeed(fps) {
      if (!(Number(fps) > 0)) return;
      if (st.playing) ctl.play(fps);
      else patch({ fps: Number(fps) }, "timelapse-speed");
    },
    // port of stopTimeLapse: clears the animation and turns the timelapse off
    stop() {
      ctl.pause();
      setVisibleIn((l) => l.id === id, false, "timelapse-stop");
    },
    // port of toggleCumulativeMode
    setCumulative(on) {
      patch({ cumulative: !!on }, "timelapse-cumulative");
      render();
    },
    // port of jitterZoom(true): re-request tiles that got stuck; also asks
    // again for the map service of any frame that failed to load.
    refresh() {
      engine.jitter();
      if (st.loaded) [...failed].forEach(requestFrame);
    },
    // The layer opacity changed.
    render,
    dispose() {
      disposed = true;
      clearTimer();
      unsubscribe();
    },
    state: () => ({ ...st }),
    _visible: () => visible,
    // port of 4map-manager.js addTimeLapseToMap queryObj: the collection is
    // queried as a time series (type geeImageCollection).
    async queryTarget() {
      if (!loader.prepare) return null;
      const p = await loader.prepare();
      if (!p || !p.item) return null;
      // port of addTimeLapseToMap: queryItem: viz.queryItem || item
      let item = p.item;
      const qi = p.viz && p.viz.queryItem;
      if (qi) item = typeof qi.evaluate === "function" ? qi : (engine.ee || globalThis.ee).Deserializer.decode(qi);
      // A wind timelapse is queried on its speed/direction collection (the
      // original's retargetQuery), as a time series like any timelapse.
      const windItem = windQueryItem(p.viz, engine.ee || globalThis.ee);
      if (windItem) return { type: "geeImageCollection", item: windItem, viz: p.viz, unitProps: WIND_UNIT_PROPS };
      return { type: "geeImageCollection", item, viz: p.viz };
    },
  };

  async function load() {
    try {
      if (loader.prepare) {
        const p = await loader.prepare();
        if (p && p.legend !== undefined && engine.setLegend) engine.setLegend(id, p.legend);
      }
      const years = await loader.years();
      if (disposed) return;
      patch({ years: years.slice(), frame: wrapFrame(st.frame, years.length) }, "timelapse-years");
      engine.initFrames(id, years.length);
      let n = 0;
      // A frame that fails does not hold the others back: it is marked, the
      // row shows the error, and refresh asks for it again.
      await Promise.allSettled(
        years.map((_, i) =>
          loader.frame(i).then(
            (url) => {
              if (disposed) return;
              engine.setFrameUrl(id, i, url);
              patch({ nLoaded: ++n }, "timelapse-progress");
            },
            (err) => {
              failed.add(i);
              if (firstError === null) firstError = err;
            }
          )
        )
      );
      if (disposed) return;
      patch({ loaded: true, failed: [...failed].sort((a, b) => a - b) }, "timelapse-loaded");
      engine.framesReady(id);
      reportFailures();
      // timelapse-toggle.js reconcile: a choice made while loading applies now.
      if (visible) activate();
    } catch (e) {
      if (!disposed && engine.fail) engine.fail(id, e);
    }
  }

  function reportFailures() {
    if (!failed.size || !engine.fail) return;
    const msg = firstError && firstError.message ? firstError.message : String(firstError);
    engine.fail(id, failed.size + " of " + st.years.length + " frames failed to load: " + msg);
  }

  function requestFrame(i) {
    loader.frame(i).then(
      (url) => {
        if (disposed || !failed.has(i)) return;
        failed.delete(i);
        engine.setFrameUrl(id, i, url);
        patch({ nLoaded: st.nLoaded + 1, failed: [...failed].sort((a, b) => a - b) }, "timelapse-retry");
        if (!failed.size && engine.clearError) engine.clearError(id);
        if (shown) render();
      },
      (err) => {
        firstError = err;
        reportFailures();
      }
    );
  }
  patch({}, "timelapse-init");
  load();
  return ctl;
}
