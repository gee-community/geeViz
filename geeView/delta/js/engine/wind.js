// Wind layers: the adapter between Delta's layer engine and the shared
// geeView/src/js/wind-particles.js, which Delta loads unchanged.
//
// wind-particles.js was written against the original viewer. It reads:
//   map        the Google map (window.map), which it hands to an OverlayView
//   layerObj   the top-level `let` registry (here compat.js's), keyed by layer
//              id, each record {viz, layer, layerId, visible, opacity}:
//                viz.windParticles  adopt it
//                viz.timeLapseID    group frames of one timelapse ("tl:<id>")
//                layer.getTileUrl   the u/v tile url for (coord, zoom)
//                layerId            its overlayMapTypes slot: it nulls that
//                                   slot (detach) and stacks its canvases at
//                                   that z-index
//                visible, opacity   run/stop, and the frame on screen (the
//                                   highest raised opacity of a timelapse)
//              and writes loading/percent back.
// This module keeps those records in step with engine/layers.js, which holds
// the wind slots empty, so the raw RGB never reaches the map.
//
// A timelapse's frames are registered together once every frame has its map
// service, in year order: wind-particles.js takes frame order from the order
// it first sees the records.

// The records layerObj should hold, from engine/layers.js windSources().
// Pure; for tests. Returns {key: {viz, slot, visible, opacity, tileUrl, lapse}}.
export function windEntries(sources) {
  const out = {};
  (sources || []).forEach((s) => {
    if (!s.ready) return;
    if (!s.timelapse) {
      if (!s.tileUrl) return;
      const viz = { ...s.viz };
      delete viz.timeLapseID;
      out[s.id] = { viz, slot: s.slot, visible: !!s.visible, opacity: s.opacity, tileUrl: s.tileUrl, lapse: null };
      return;
    }
    s.frames.forEach((f, i) => {
      if (!f.tileUrl) return;
      out[frameKey(s.id, i)] = {
        viz: { ...s.viz, timeLapseID: s.id },
        slot: s.slot + i,
        visible: !!s.shown,
        opacity: f.opacity || 0,
        tileUrl: f.tileUrl,
        lapse: s.id,
      };
    });
  });
  return out;
}

export const frameKey = (id, i) => id + "-frame-" + i;

// registry: compat.js's layerObj (mutated in place: wind-particles.js holds the
// binding, not a copy). particles: window.geeVizWindParticles, once loaded.
export function createWind(layers, registry, opts = {}) {
  const particles = opts.particles || (() => window.geeVizWindParticles);
  const ours = new Set();

  // update() reaches the store (loading) and the store reaches the layer
  // engine, which may report a change again: run once more, never nested.
  let busy = false;
  let again = false;
  function update() {
    if (busy) {
      again = true;
      return;
    }
    busy = true;
    try {
      do {
        again = false;
        apply();
      } while (again);
    } finally {
      busy = false;
    }
  }

  function apply() {
    const want = windEntries(layers.windSources());
    Object.keys(want).forEach((key) => {
      const w = want[key];
      let rec = registry[key];
      if (!rec || !ours.has(key)) {
        rec = makeRecord(key, w.lapse);
        registry[key] = rec;
        ours.add(key);
      }
      rec.viz = w.viz;
      rec.layerId = w.slot;
      rec.visible = w.visible;
      rec.opacity = w.opacity;
      rec._tileUrl = w.tileUrl;
    });
    [...ours].forEach((key) => {
      if (want[key]) return;
      delete registry[key];
      ours.delete(key);
    });
    const wp = particles();
    if (wp) {
      // Adopt new layers and apply visibility now, not on the next tick.
      try {
        wp.scan();
        wp._refreshRunState();
      } catch (e) {
        if (window.console) console.warn("wind: refresh failed", e);
      }
    }
  }

  function makeRecord(key, lapse) {
    let loading = false;
    const rec = {
      viz: null,
      layerId: 0,
      visible: false,
      opacity: 1,
      percent: 0,
      _tileUrl: null,
      // A plain object, so wind-particles.js finds getTileUrl by name and
      // fetches tiles without counting them as map requests.
      layer: { getTileUrl: (coord, zoom) => (rec._tileUrl ? rec._tileUrl(coord, zoom) : null) },
    };
    // wind-particles.js reports the tiles it is fetching here; a single layer
    // shows it as the row's loading state. (A timelapse's progress is
    // reported under its group id, which has no record.)
    Object.defineProperty(rec, "loading", {
      enumerable: true,
      get: () => loading,
      set: (v) => {
        loading = !!v;
        if (!lapse && layers.setLayerLoading) layers.setLayerLoading(key, loading);
      },
    });
    return rec;
  }

  const off = layers.onChange(update);
  update();
  return { update, dispose: off, keys: () => [...ours] };
}
