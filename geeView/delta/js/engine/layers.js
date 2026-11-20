// Map layers: Earth Engine images, collections and vector images as tile
// overlays, vectors as google.maps.Data, external XYZ tile services, and
// dynamic (export) map services as ground overlays. The only DOM it touches
// is through Google map objects.
//
// port of lcms-viewer 2templates.js addLayer (as bundled in
// geeView/src/js/lcms-viewer.min.js, with its LOCAL PATCH tile legend v3) and
// 4map-manager.js getGroundOverlay. Store-driven: the engine reacts to each
// layer's `visible` and `opacity` and to `order`, and writes `loading`,
// `error` and `legend` back. A timelapse is one record with a frame overlay
// per year; its controller (engine/timelapse.js) drives it through the frame
// hooks below, and sync() stacks the frames in the timelapse's list slot.
import { prepareViz, createColorCycle, normVecStyle } from "./viz.js";
import { createTimelapse } from "./timelapse.js";
import { createTileOverlay, progressOf } from "./tiles.js";
import { windQueryItem, WIND_UNIT_PROPS } from "./wind.js";

const TILE_TYPES = ["geeImage", "geeImageCollection", "geeVectorImage", "tileMapService"];
const DATA_TYPES = ["geeVector", "geoJSONVector"];
const VIZ_KEYS = ["bands", "min", "max", "gain", "bias", "gamma", "palette", "forceRgbOutput"];
// the original's possibleVizKeys
const POSSIBLE_VIZ_KEYS = ["bands", "min", "max", "gain", "bias", "gamma", "palette", "color"];
// Select layers draw like any vector (port of 4map-manager.js addSelectLayerToMap).
const SKIP_KINDS = ["areaChartOnly"];
const NOT_QUERYABLE = ["geoJSONVector", "tileMapService", "dynamicMapService"];

// A wind layer (geeViz.weather addWindLayer / addWindTimeLapse): its tiles
// are u/v encoded as RGB, decoded and drawn by wind-particles.js through
// engine/wind.js, never shown as a picture. It keeps its slot (or one per
// frame) in the stack, empty, so the particles stack there.
export const isWindViz = (viz) => !!(viz && viz.windParticles);

function layerTypeOf(layer) {
  if (layer.kind === "timelapse") return "timelapse";
  if (layer.kind === "geojson") return "geoJSONVector";
  if (layer.kind === "tile") return "tileMapService";
  if (layer.kind === "dynamic") return "dynamicMapService";
  return layer.viz && layer.viz.layerType;
}

// port of 4map-manager.js Xcoord4326To3857 and Ycoord4326To3857
const x3857 = (x) => (x * 20037508.34) / 180;
const y3857 = (y) => ((Math.log(Math.tan(((90 + y) * Math.PI) / 360)) / (Math.PI / 180)) * 20037508.34) / 180;

// port of 4map-manager.js getGroundOverlay. Returns null below minZoom (the
// original returned a blank image).
export function groundOverlayUrl(baseUrl, minZoom, ending, zoom, bounds, width, height) {
  if (zoom < minZoom) return null;
  ending = ending === undefined || ending === null ? "" : ending;
  const w = x3857(bounds.west);
  const s = y3857(bounds.south);
  const e = x3857(bounds.east);
  const n = y3857(bounds.north);
  return `${baseUrl}${w}%2C${s}%2C${e}%2C${n}&bboxSR=3857&imageSR=3857&size=${width}%2C${height}${ending}`;
}

// Bottom-to-top ids of the records that share one stacking (list order is top-first).
export function stackOrder(orderTopFirst, has) {
  return orderTopFirst.filter(has).reverse();
}

export function createLayerEngine(gmap, store, deps = {}) {
  const g = deps.google || window.google.maps;
  const eeApi = deps.ee || window.ee;
  const recs = new Map();
  const nextColor = createColorCycle();
  let order = store.get().order.slice();
  // Called after anything engine/wind.js mirrors changes: stacking, frames,
  // visibility, opacity, tile services, removal.
  const listeners = new Set();
  const changed = () => listeners.forEach((fn) => fn());
  // The labels overlay (engine/maps.js labelsOverlay), or null.
  const labelsOverlay = deps.labels || (() => null);

  function patch(id, p, reason) {
    if (!recs.has(id)) return;
    store.update((s) => ({ ...s, layers: s.layers.map((l) => (l.id === id ? { ...l, ...p } : l)) }), reason || "layer-engine");
  }
  function setLoading(rec, loading) {
    if (rec.loading === loading) return;
    rec.loading = loading;
    patch(rec.id, { loading }, "layer-loading");
  }
  function fail(rec, err) {
    rec.loading = false;
    patch(rec.id, { loading: false, error: String((err && err.message) || err) }, "layer-error");
  }

  // ---- stacking ----
  // port of 2templates.js updateMapLayerOrder: overlayMapTypes index order
  // equals list order (bottom of the list at index 0); Data layers take zIndex.
  // A timelapse fills one slot per frame, first year lowest (the original adds
  // its frames in year order), and is on the map only while its controller
  // shows it. The labels overlay comes last, above every layer (port of
  // 4map-manager.js addLabelOverlay: index = number of layers), and nothing
  // follows it.
  function slotsFor(r) {
    if (isWindViz(r.viz)) return r.timelapse ? r.frames.map(() => null) : [null];
    if (r.timelapse) return r.frames.map((f) => (r.framesShown && f.overlay ? f.overlay : null));
    return [r.visible && r.overlay ? r.overlay : null];
  }
  function sync() {
    const omt = gmap.overlayMapTypes;
    const tiles = stackOrder(order, (id) => recs.has(id) && recs.get(id).tileType);
    const slots = [];
    tiles.forEach((id) => {
      const r = recs.get(id);
      r.slot = slots.length;
      slots.push(...slotsFor(r));
    });
    const labels = labelsOverlay();
    if (labels) slots.push(labels);
    while (omt.getLength() < slots.length) omt.push(null);
    slots.forEach((want, i) => {
      if (omt.getAt(i) !== want) omt.setAt(i, want);
    });
    // Only empty slots can follow; dropping them shifts nothing.
    while (omt.getLength() > slots.length) omt.removeAt(omt.getLength() - 1);
    const vectors = stackOrder(order, (id) => recs.has(id) && recs.get(id).dataType);
    vectors.forEach((id, i) => {
      const r = recs.get(id);
      const z = 1000 + i;
      if (r.overlay && r.zIndex !== z) {
        r.zIndex = z;
        applyDataStyle(r);
      }
    });
    changed();
  }

  function applyOrder(next) {
    order = next.slice();
    sync();
  }

  // ---- Data (vector) layers ----
  function applyDataStyle(r) {
    if (!r.overlay) return;
    // Vectors pass clicks to the map unless the viz asks for clickable
    // features, so the Query tool's double-click works over them.
    const style = { clickable: false, ...r.style, zIndex: r.zIndex || 1000 };
    // port of 2templates.js addLayer opacity slide: stroke takes the opacity, fill keeps its ratio
    if (r.opacity !== 1 || r.opacityTouched) {
      style.strokeOpacity = r.opacity;
      style.fillOpacity = r.opacity / (r.viz.opacityRatio || 1);
    }
    r.overlay.setStyle(style);
  }

  function addGeoJson(r, v) {
    // port of 2templates.js addLayer addGeoJsonToMap
    const data = new g.Data();
    r.style = normVecStyle(r.viz);
    r.overlay = data;
    applyDataStyle(r);
    try {
      data.addGeoJson(v);
    } catch (err) {
      data.addGeoJson({ type: "Feature", geometry: v, id: "0", properties: {} });
    }
    r.requests++;
    if (r.visible) data.setMap(gmap);
    sync();
    setLoading(r, false);
  }

  // ---- tile layers ----
  // Tile overlays load their own tiles (engine/tiles.js), so each layer knows
  // how many of the tiles on screen are in (layer.progress, the row's
  // progress fill) and failed tiles are retried. port of 2templates.js addLayer
  // geeAltService (which counted requests and waited on tilesloaded).
  function reportProgress(r) {
    const overlays = r.timelapse ? r.frames.map((f) => f.overlay).filter(Boolean) : r.overlay && r.overlay.stats ? [r.overlay] : [];
    const p = progressOf(overlays.map((o) => o.stats()));
    const shown = r.timelapse ? r.framesShown : r.visible;
    const settled = p.loaded + p.failed;
    if (r.timelapse) frameLoading(r, p);
    else setLoading(r, !!shown && p.total > 0 && settled < p.total);
    const next = { total: p.total, loaded: p.loaded, failed: p.failed };
    const prev = r.progress || {};
    if (prev.total === next.total && prev.loaded === next.loaded && prev.failed === next.failed) return;
    r.progress = next;
    patch(r.id, { progress: next }, "layer-progress");
  }
  function tileOverlay(r, urlFor, extra = {}) {
    return createTileOverlay({
      google: g,
      ...extra,
      opacity: r.opacity,
      urlFor,
      onRequest: () => r.requests++,
      onProgress: () => reportProgress(r),
    });
  }

  function eeTileLayer(r, item) {
    const viz = r.viz;
    if (viz.layerType === "geeImageCollection") {
      // port of 2templates.js addLayer image collection reducer
      let reducer = viz.reducer;
      if (reducer === null || reducer === undefined) reducer = eeApi.Reducer.lastNonNull();
      else if (typeof reducer === "string") reducer = eeApi.Deserializer.fromJSON(reducer);
      const ic = item;
      const bandNames = eeApi.Image(ic.first()).bandNames();
      item = eeApi.Image(eeApi.ImageCollection(ic).reduce(reducer).rename(bandNames).copyProperties(ic.first()).set(ic.toDictionary()));
      if (viz.selfMask === true) item = item.selfMask();
    } else if (viz.layerType === "geeVectorImage") {
      try {
        viz.asyncBounds = item.geometry().bounds(100, "EPSG:4326");
      } catch (err) {
        viz.asyncBounds = item.bounds(100, "EPSG:4326");
      }
      item = viz.styleParams !== undefined ? item.style(viz.styleParams) : eeApi.Image().paint(item, null, viz.strokeWeight);
      viz.palette = viz.strokeColor;
    }
    requestMap(item, viz, (tilesUrl, failure) => {
      if (!recs.has(r.id)) return;
      if (failure) return fail(r, failure);
      r.tileUrl = (coord, zoom) => tilesUrl.replace("{x}", coord.x).replace("{y}", coord.y).replace("{z}", zoom);
      r.overlay = tileOverlay(r, r.tileUrl);
      // A wind layer is never on the map, so Google never reports its tiles
      // loaded; wind.js reports the particles' own tile loading instead.
      if (!r.visible || isWindViz(r.viz)) setLoading(r, false);
      sync();
    });
  }

  // port of 2templates.js addLayer getGEEMapService: one retry when Earth
  // Engine returns nothing. cb(urlFormat) or cb(null, failure).
  function requestMap(item, viz, cb) {
    const vizFound = POSSIBLE_VIZ_KEYS.some((k) => k in viz);
    const usedViz = {};
    if (vizFound && !viz.autoViz && viz.styleParams === undefined) {
      VIZ_KEYS.forEach((k) => {
        if (viz[k] !== undefined && viz[k] !== null) usedViz[k] = viz[k];
      });
    }
    const mapItem = viz.bands !== undefined ? eeApi.Image(item).select(viz.bands) : eeApi.Image(item);
    let tries = 0;
    const request = () => {
      tries++;
      eeApi.Image(mapItem).getMap(usedViz, (eeLayer, failure) => {
        if (eeLayer === undefined && tries <= 1) return request();
        if (eeLayer === undefined || failure !== undefined) return cb(null, failure || "Earth Engine did not return a map service");
        cb(eeLayer.urlFormat);
      });
    };
    request();
  }

  // ---- dynamic map services ----
  // port of 2templates.js addLayer groundOverlayWrapper and updateGroundOverlay.
  // A preloading Image replaces the original's HEAD request and 1 s retries;
  // the overlay refreshes on idle (after both zooms and drags).
  function refreshGround(r) {
    if (r.overlay) r.overlay.setMap(null);
    r.overlay = null;
    if (!r.visible) return setLoading(r, false);
    const b = gmap.getBounds();
    if (!b) return;
    const zoom = gmap.getZoom();
    const svc = zoom > r.item[1].minZoom ? r.item[1] : r.item[0];
    const div = gmap.getDiv();
    const url = groundOverlayUrl(svc.baseURL, svc.minZoom, svc.ending, zoom, b.toJSON(), div.clientWidth, div.clientHeight);
    if (!url) return setLoading(r, false);
    const reqId = ++r.groundRequest;
    setLoading(r, true);
    r.requests++;
    const overlay = new g.GroundOverlay(url, b, { opacity: r.opacity, clickable: false });
    overlay.setMap(gmap);
    r.overlay = overlay;
    const img = new Image();
    img.onload = () => reqId === r.groundRequest && setLoading(r, false);
    img.onerror = () => reqId === r.groundRequest && fail(r, "The map service did not return an image");
    img.src = url;
  }

  // ---- timelapses ----
  // Frame hooks for engine/timelapse.js. Each frame counts the tiles it is
  // asked for; the timelapse reports loading until its frames have map
  // services and, while shown, until every frame's tiles are in.
  // An off timelapse never reports loading, even while its frames load.
  function frameLoading(r, p) {
    if (!p) p = progressOf((r.frames || []).map((f) => f.overlay).filter(Boolean).map((o) => o.stats()));
    const pending = p ? p.total > 0 && p.loaded + p.failed < p.total : false;
    setLoading(r, !!r.visible && (!r.ready || (r.framesShown && pending)));
  }
  const frameHooks = {
    store,
    ee: eeApi,
    requestMap,
    initFrames(id, n) {
      const r = recs.get(id);
      if (!r) return;
      r.frames = Array.from({ length: n }, () => ({ overlay: null, opacity: 0 }));
      sync();
    },
    setFrameUrl(id, i, tilesUrl) {
      const r = recs.get(id);
      if (!r || !r.frames[i]) return;
      const tileUrl = (coord, zoom) => tilesUrl.replace("{x}", coord.x).replace("{y}", coord.y).replace("{z}", zoom);
      // every frame's tiles count toward the timelapse's progress
      const overlay = tileOverlay(r, tileUrl);
      overlay.setOpacity(r.frames[i].opacity);
      r.frames[i].overlay = overlay;
      r.frames[i].tileUrl = tileUrl;
      changed();
    },
    framesReady(id) {
      const r = recs.get(id);
      if (!r) return;
      r.ready = true;
      frameLoading(r);
      changed();
    },
    // ops: per-frame opacities (every frame stays on the map so the next one
    // is already loaded, as the original's opacity-0 frames), or null: off.
    showFrames(id, ops) {
      const r = recs.get(id);
      if (!r) return;
      if (ops) {
        r.frames.forEach((f, i) => {
          f.opacity = ops[i] || 0;
          if (f.overlay && f.overlay.getOpacity() !== f.opacity) f.overlay.setOpacity(f.opacity);
        });
      } else r.pending.clear();
      r.framesShown = !!ops;
      sync();
      frameLoading(r);
    },
    // port of 4map-manager.js jitterZoom(true); the view history ignores the
    // return to the same view.
    jitter() {
      const z = gmap.getZoom();
      gmap.setZoom(z - 1);
      gmap.setZoom(z);
    },
    setLegend(id, legend) {
      patch(id, { legend }, "layer-legend");
    },
    clearError(id) {
      patch(id, { error: null }, "layer-error");
    },
    fail(id, err) {
      const r = recs.get(id);
      if (r) fail(r, err);
    },
  };

  function addTimelapse(layer) {
    const r = {
      id: layer.id,
      layerType: "timelapse",
      tileType: true,
      dataType: false,
      timelapse: true,
      visible: layer.visible,
      opacity: layer.opacity,
      overlay: null,
      frames: [],
      framesShown: false,
      ready: false,
      pending: new Set(),
      loading: false,
      requests: 0,
      viz: layer.viz,
      item: layer.item,
    };
    recs.set(layer.id, r);
    frameLoading(r);
    r.tl = createTimelapse(frameHooks, layer);
  }

  // ---- public ----
  async function addLayerToMap(layer) {
    if (SKIP_KINDS.indexOf(layer.kind) > -1) return;
    if (layer.kind === "timelapse") return addTimelapse(layer);
    const layerType = layerTypeOf(layer);
    const r = {
      id: layer.id,
      layerType,
      tileType: TILE_TYPES.indexOf(layerType) > -1,
      dataType: DATA_TYPES.indexOf(layerType) > -1,
      visible: layer.visible,
      opacity: layer.opacity,
      overlay: null,
      loading: false,
      requests: 0,
      groundRequest: 0,
      viz: null,
      item: layer.item,
      target: null,
    };
    // What the Query tool reduces: the layer's queryItem (else the item as
    // given, before any reduce or paint), its type and prepared viz.
    let resolveTarget;
    r.target = new Promise((res) => (resolveTarget = res));
    recs.set(layer.id, r);
    setLoading(r, true);
    try {
      let item = layer.item;
      const vizIn = { ...(layer.viz || {}) };
      if (layerType) vizIn.layerType = layerType;
      if (vizIn.serialized === true && ["geoJSONVector", "tileMapService", "dynamicMapService"].indexOf(layerType) === -1) {
        item = eeApi.Deserializer.decode(item);
      }
      if (layerType === "geoJSONVector" && typeof item === "string") item = JSON.parse(item);
      const prepared = await prepareViz(item, vizIn, { name: layer.name, nextColor, ee: eeApi });
      if (!recs.has(r.id)) return resolveTarget(null);
      r.viz = prepared.viz;
      item = prepared.item;
      // port of 2templates.js addLayer: layer.queryItem = viz.queryItem || item
      let queryItem = r.viz.queryItem || item;
      if (r.viz.queryItem && vizIn.serialized === true && typeof queryItem.evaluate !== "function") queryItem = eeApi.Deserializer.decode(queryItem);
      // A wind layer is queried on its speed/direction image, not its tiles.
      const windItem = windQueryItem(r.viz, eeApi);
      const qType = r.layerType || r.viz.layerType;
      const target = { type: qType, item: windItem || queryItem, viz: r.viz };
      if (windItem) target.unitProps = WIND_UNIT_PROPS;
      resolveTarget(NOT_QUERYABLE.indexOf(qType) > -1 ? null : target);
      if (!r.layerType) {
        // layerType defaulted from the Earth Engine object type
        r.layerType = r.viz.layerType;
        r.tileType = TILE_TYPES.indexOf(r.layerType) > -1;
        r.dataType = DATA_TYPES.indexOf(r.layerType) > -1;
      }
      patch(r.id, { legend: prepared.legend }, "layer-legend");

      if (r.layerType === "tileMapService") {
        const maxZoom = Number.isFinite(Number(r.viz.maxZoom)) ? Number(r.viz.maxZoom) : 15;
        r.overlay = tileOverlay(r, (coord, zoom) => item(coord, zoom), { maxZoom });
        // LOCAL PATCH tile legend v3 is carried by the row: the legend is the row's own, shown whenever the layer is on.
        setLoading(r, false);
        sync();
      } else if (r.tileType) {
        eeTileLayer(r, item);
      } else if (r.layerType === "geeVector") {
        r.requests++;
        item.evaluate((v, err) => {
          if (!recs.has(r.id)) return;
          if (v === undefined || err) return fail(r, err || "The features could not be loaded");
          addGeoJson(r, v);
        });
      } else if (r.layerType === "geoJSONVector") {
        addGeoJson(r, item);
      } else if (r.layerType === "dynamicMapService") {
        r.listener = gmap.addListener("idle", () => r.visible && refreshGround(r));
        refreshGround(r);
      } else {
        fail(r, "Unknown layer type: " + r.layerType);
      }
    } catch (e) {
      resolveTarget(null);
      fail(r, e);
    }
  }

  function setLayerVisible(id, on) {
    const r = recs.get(id);
    if (!r) return;
    r.visible = !!on;
    if (r.timelapse) {
      r.tl.setVisible(r.visible);
      frameLoading(r);
      return changed();
    }
    if (r.tileType) sync();
    else if (r.dataType) r.overlay && r.overlay.setMap(on ? gmap : null);
    else if (r.layerType === "dynamicMapService") refreshGround(r);
    if (!on) setLoading(r, false);
    changed();
  }

  function setLayerOpacity(id, a) {
    const r = recs.get(id);
    if (!r) return;
    r.opacity = a;
    if (r.timelapse) r.tl.render();
    else if (r.dataType) {
      r.opacityTouched = true;
      applyDataStyle(r);
    } else if (r.overlay) r.overlay.setOpacity(a);
    changed();
  }

  function removeLayer(layer) {
    const r = recs.get(layer.id);
    if (!r) return;
    recs.delete(layer.id);
    if (r.tl) r.tl.dispose();
    if (r.listener) r.listener.remove();
    if (r.overlay && (r.dataType || r.layerType === "dynamicMapService")) r.overlay.setMap(null);
    order = order.filter((id) => id !== layer.id);
    sync();
  }

  // What is drawn, bottom to top: tile overlays by overlayMapTypes index and
  // Data layers by zIndex. For tests and debugging.
  function zOrder() {
    const byOverlay = new Map();
    recs.forEach((r) => {
      if (r.overlay) byOverlay.set(r.overlay, r.id);
      if (r.frames) r.frames.forEach((f) => f.overlay && byOverlay.set(f.overlay, r.id));
    });
    const tiles = gmap.overlayMapTypes.getArray().filter((o) => o && byOverlay.has(o)).map((o) => byOverlay.get(o));
    const vectors = [...recs.values()]
      .filter((r) => r.dataType && r.overlay && r.overlay.getMap())
      .sort((a, b) => a.zIndex - b.zIndex)
      .map((r) => r.id);
    return { tiles, vectors };
  }
  // Intended stacking of every tile layer, visible or not, bottom to top.
  const slotOrder = () => stackOrder(order, (id) => recs.has(id) && recs.get(id).tileType);
  const stats = (id) => {
    const r = recs.get(id);
    if (!r) return null;
    const omt = gmap.overlayMapTypes.getArray();
    if (r.timelapse) {
      const frames = r.frames.map((f) => ({ onMap: !!f.overlay && omt.includes(f.overlay), opacity: f.overlay ? f.overlay.getOpacity() : 0 }));
      return { requests: r.requests, loading: r.loading, layerType: r.layerType, onMap: frames.some((f) => f.onMap), frames };
    }
    return { requests: r.requests, loading: r.loading, layerType: r.layerType, progress: r.overlay && r.overlay.stats ? r.overlay.stats() : null, onMap: !!(r.overlay && (r.tileType ? omt.includes(r.overlay) : r.overlay.getMap())) };
  };
  // The wind layers, for engine/wind.js: each with its stack slot, its tile
  // url function (not counted as a request: the particles fetch their own
  // tiles) and, for a timelapse, one entry per frame in year order.
  const windSources = () =>
    [...recs.values()]
      .filter((r) => r.tileType && isWindViz(r.viz))
      .map((r) => ({
        id: r.id,
        viz: r.viz,
        visible: !!r.visible,
        opacity: r.opacity,
        slot: r.slot,
        timelapse: !!r.timelapse,
        tileUrl: r.tileUrl || null,
        ready: r.timelapse ? !!r.ready : !!r.tileUrl,
        shown: r.timelapse ? !!(r.visible && r.framesShown) : !!r.visible,
        frames: r.timelapse ? r.frames.map((f) => ({ tileUrl: f.tileUrl || null, opacity: f.opacity })) : [],
      }));
  const onChange = (fn) => {
    listeners.add(fn);
    return () => listeners.delete(fn);
  };
  const setLayerLoading = (id, loading) => {
    const r = recs.get(id);
    if (r) setLoading(r, !!loading);
  };
  const timelapse = (id) => (recs.get(id) && recs.get(id).tl) || null;
  // Promise of {type, item, viz} for the Query tool, or null.
  const queryTarget = (id) => {
    const r = recs.get(id);
    if (!r) return Promise.resolve(null);
    if (r.tl) return r.tl.queryTarget ? r.tl.queryTarget() : Promise.resolve(null);
    return r.target || Promise.resolve(null);
  };

  // React to the store: visibility, opacity and order are state.
  store.on("change:layers", (layers) => {
    layers.forEach((l) => {
      const r = recs.get(l.id);
      if (!r) return;
      if (l.visible !== r.visible) setLayerVisible(l.id, l.visible);
      if (l.opacity !== r.opacity) setLayerOpacity(l.id, l.opacity);
    });
  });
  store.on("change:order", (o) => applyOrder(o));
  // The labels overlay is on the map before any layer is.
  sync();

  // Ask again for a layer's tiles that ran out of retries; the number asked for.
  function retryTiles(id) {
    const r = recs.get(id);
    if (!r) return 0;
    const overlays = r.timelapse ? r.frames.map((f) => f.overlay).filter(Boolean) : r.overlay && r.overlay.retryFailed ? [r.overlay] : [];
    return overlays.reduce((n, o) => n + o.retryFailed(), 0);
  }
  return { sync, addLayerToMap, setLayerVisible, setLayerOpacity, applyOrder, removeLayer, zOrder, slotOrder, stats, timelapse, queryTarget, windSources, onChange, setLayerLoading, retryTiles };
}
