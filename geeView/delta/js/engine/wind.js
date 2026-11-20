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

// What a wind layer's click reads. The tiles are u/v encoded as RGB, so
// querying them reports bytes that look like numbers. geeViz.weather sends the
// speed/direction image (a timelapse: collection) as viz.windQueryItem,
// serialized; the original viewer points its query there (wind-particles.js
// retargetQuery). Returns the Earth Engine object, or null for any other layer.
export function windQueryItem(viz, eeApi) {
  const q = viz && viz.windParticles ? viz.windQueryItem : null;
  if (q === null || q === undefined) return null;
  if (typeof q === "string") return eeApi.Deserializer.fromJSON(q);
  if (typeof q.evaluate === "function") return q;
  return eeApi.Deserializer.decode(q);
}

// geeViz.weather.windImage stamps each band's units on the image as
// properties; the query reads them in the same request, so the values are
// labeled in the units the script chose (the speed is already converted).
export const WIND_UNIT_PROPS = { speed: "wind_units", direction: "wind_direction_units" };

// The key wind-particles.js files a layer's state under in _adopted: a
// timelapse's frames are one group, "tl:<timeLapseID>".
export const adoptedKey = (s) => (s.timelapse ? "tl:" + s.id : s.id);

// registry: compat.js's layerObj (mutated in place: wind-particles.js holds the
// binding, not a copy). particles: window.geeVizWindParticles, once loaded.
// opts.particleOpacity(id): a grouped layer's particle slider (0..1, undefined
// for other layers); wind-particles.js reads it as the adopted state's
// particleDim, which its own injected slider sets in the original.
export function createWind(layers, registry, opts = {}) {
  const particles = opts.particles || (() => window.geeVizWindParticles);
  const ours = new Set();
  const groups = new Map(); // timelapse id -> its "tl:<id>" record

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
    // wind-particles.js reports a timelapse's tile loading under its group
    // key, "tl:<id>", where the original viewer has no record either. Give it
    // one, non-enumerable: scan() lists the registry to find layers, and must
    // not find this.
    const lapses = new Map();
    layers.windSources().forEach((s) => s.timelapse && s.ready && lapses.set(s.id, s));
    lapses.forEach((s, id) => {
      let g = groups.get(id);
      if (!g) {
        g = { visible: false };
        reportTo(g, id);
        groups.set(id, g);
        Object.defineProperty(registry, "tl:" + id, { value: g, enumerable: false, configurable: true, writable: true });
      }
      g.visible = !!s.shown;
    });
    [...groups.keys()].forEach((id) => {
      if (lapses.has(id)) return;
      delete registry["tl:" + id];
      groups.delete(id);
    });
    const wp = particles();
    if (wp) {
      // Adopt new layers and apply visibility now, not on the next tick.
      try {
        wp.scan();
        if (opts.particleOpacity && wp._adopted) {
          layers.windSources().forEach((s) => {
            const po = opts.particleOpacity(s.id);
            const st = wp._adopted[adoptedKey(s)];
            if (st && typeof po === "number") st.particleDim = po;
          });
        }
        wp._refreshRunState();
      } catch (e) {
        if (window.console) console.warn("wind: refresh failed", e);
      }
    }
  }

  // wind-particles.js reports the tiles it is fetching as loading and percent
  // (0..100, 100 once in, 0 while hidden) on a record; forward both to layer
  // `id`'s row: its loading state and its progress fill, the share of tiles
  // in, as for every other tile layer.
  function reportTo(rec, id) {
    let loading = false;
    let percent = 0;
    Object.defineProperty(rec, "loading", {
      enumerable: true,
      get: () => loading,
      set: (v) => {
        loading = !!v;
        if (layers.setLayerLoading) layers.setLayerLoading(id, loading);
      },
    });
    Object.defineProperty(rec, "percent", {
      enumerable: true,
      get: () => percent,
      set: (v) => {
        percent = Number(v) || 0;
        if (layers.setLayerProgress) layers.setLayerProgress(id, percent);
      },
    });
  }

  function makeRecord(key, lapse) {
    const rec = {
      viz: null,
      layerId: 0,
      visible: false,
      opacity: 1,
      _tileUrl: null,
      // A plain object, so wind-particles.js finds getTileUrl by name and
      // fetches tiles without counting them as map requests.
      layer: { getTileUrl: (coord, zoom) => (rec._tileUrl ? rec._tileUrl(coord, zoom) : null) },
    };
    // A single layer's record is the one wind-particles.js reports to; a
    // timelapse reports under its group record (above), not per frame.
    if (!lapse) reportTo(rec, key);
    else Object.assign(rec, { loading: false, percent: 0 });
    return rec;
  }

  const off = layers.onChange(update);
  update();
  return { update, dispose: off, keys: () => [...ours] };
}
