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
import { createVectorTileOverlay, tileBounds, flatten } from "./vectortiles.js";
import { geomKinds } from "../ui/legend.js";
import { pluginFor } from "../plugins/index.js";
import { isTimelapse } from "../util.js";
import { lazyEE } from "./ee.js";
import { windQueryItem, WIND_UNIT_PROPS } from "./wind.js";

const TILE_TYPES = ["geeImage", "geeImageCollection", "geeVectorImage", "tileMapService"];
const DATA_TYPES = ["geeVector", "geoJSONVector"];
const VIZ_KEYS = ["bands", "min", "max", "gain", "bias", "gamma", "palette", "forceRgbOutput"];
// the original's possibleVizKeys
const POSSIBLE_VIZ_KEYS = ["bands", "min", "max", "gain", "bias", "gamma", "palette", "color"];
// Select layers draw like any vector (port of 4map-manager.js addSelectLayerToMap).
// GeoJSON is queried by hit test (plugins/geojson.js).
const NOT_QUERYABLE = ["tileMapService", "dynamicMapService"];

// A wind layer (geeViz.weather addWindLayer / addWindTimeLapse): its tiles
// are u/v encoded as RGB, decoded and drawn by wind-particles.js through
// engine/wind.js, never shown as a picture. It keeps its slot (or one per
// frame) in the stack, empty, so the particles stack there.
export const isWindViz = (viz) => !!(viz && viz.windParticles);

function layerTypeOf(layer) {
  if (isTimelapse(layer)) return "timelapse";
  if (layer.kind === "geojson") return "geoJSONVector";
  if (layer.kind === "tile") return "tileMapService";
  if (layer.kind === "dynamic") return "dynamicMapService";
  if (String(layer.kind).startsWith("esri.")) return layer.kind;
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
  const eeApi = deps.ee || lazyEE;
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
    rec.failed = true;
    patch(rec.id, { loading: false, error: String((err && err.message) || err) }, "layer-error");
  }
  // A layer that failed before it had a record (Earth Engine did not load).
  function failLayer(id, err) {
    const error = String((err && err.message) || err);
    store.update((s) => ({ ...s, layers: s.layers.map((l) => (l.id === id ? { ...l, loading: false, error } : l)) }), "layer-error");
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
    if (!r.overlay || typeof r.overlay.setStyle !== "function") return;
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

  // port of 2templates.js addLayer addGeoJsonToMap. Drawn as canvas tiles
  // (engine/vectortiles.js) in the tile stack, so a vector takes its place in
  // the layer order instead of Google's Data pane above every tile layer.
  // The geometry types a vector holds, for its legend symbol.
  function setGeoms(r, geoms) {
    if (!recs.has(r.id) || !r.legend || r.legend.type !== "outline" || !geoms.length) return;
    r.legend = { ...r.legend, geoms };
    patch(r.id, { legend: r.legend }, "layer-legend");
  }

  function addGeoJson(r, v) {
    setGeoms(r, geomKinds(flatten(v).map((p) => p.kind)));
    r.style = normVecStyle(r.viz);
    r.overlay = createVectorTileOverlay({ google: g, geojson: v, style: r.style, opacity: r.opacity, opacityRatio: r.viz.opacityRatio, name: r.id, onProgress: () => reportProgress(r) });
    if (r.opacity !== 1) r.overlay.setOpacity(r.opacity);
    r.tileType = true;
    r.dataType = false;
    r.requests++;
    sync();
    setLoading(r, false);
  }

  // A vector layer whose features a source fetches tile by tile as the map
  // shows them (an ArcGIS feature layer: esri/features.js). The overlay
  // counts a tile as loading until its features arrive.
  function addFeatureSource(r, source, extra = {}) {
    r.style = extra.style || normVecStyle(r.viz);
    r.overlay = createVectorTileOverlay({
      google: g,
      source,
      style: r.style,
      styleFor: extra.styleFor,
      drawTile: extra.drawTile,
      onRelease: extra.onRelease,
      onError: extra.onError,
      opacity: r.opacity,
      opacityRatio: r.viz.opacityRatio,
      name: r.id,
      onProgress: () => reportProgress(r),
    });
    if (r.opacity !== 1) r.overlay.setOpacity(r.opacity);
    r.tileType = true;
    r.dataType = false;
    r.requests++;
    sync();
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
      // Painted on the server, so ask what it holds: the geometry types of
      // up to 500 features, enough for the legend symbol. A failure leaves
      // the plain polygon swatch.
      try {
        eeApi
          .FeatureCollection(item)
          .limit(500)
          .map((f) => eeApi.Feature(f).set("dz_geom", eeApi.Feature(f).geometry().type()))
          .aggregate_array("dz_geom")
          .distinct()
          .evaluate((types, err) => {
            if (!err && Array.isArray(types)) setGeoms(r, geomKinds(types));
          });
      } catch (err) {
        /* the legend keeps its polygon swatch */
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
      // the layer's own workload tag (geeViz puts it in the viz) for this
      // request: Earth Engine reads it as the request is built
      const tag = viz.workloadTag;
      if (tag) eeApi.data.setWorkloadTag(tag);
      try {
        eeApi.Image(mapItem).getMap(usedViz, (eeLayer, failure) => {
          if (eeLayer === undefined && tries <= 1) return request();
          if (eeLayer === undefined || failure !== undefined) return cb(null, failure || "Earth Engine did not return a map service");
          cb(eeLayer.urlFormat);
        });
      } finally {
        if (tag) eeApi.data.resetWorkloadTag();
      }
    };
    request();
  }

  // ---- dynamic map services ----
  // port of 2templates.js addLayer groundOverlayWrapper: now one export image
  // per map tile (addLayerToMap), through the tile overlay's progress and retry.

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
    fetch: deps.fetch,
    requestMap,
    initFrames(id, n) {
      const r = recs.get(id);
      if (!r) return;
      r.frames = Array.from({ length: n }, () => ({ overlay: null, opacity: 0 }));
      sync();
    },
    // tilesUrl: an Earth Engine URL format, or (coord, zoom) => url
    setFrameUrl(id, i, tilesUrl) {
      const r = recs.get(id);
      if (!r || !r.frames[i]) return;
      const tileUrl = typeof tilesUrl === "function" ? tilesUrl : (coord, zoom) => tilesUrl.replace("{x}", coord.x).replace("{y}", coord.y).replace("{z}", zoom);
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

  // loader: the frame loader (engine/timelapse.js eeFrameLoader by default;
  // a time-enabled ArcGIS service's is esri/timelapse.js)
  function addTimelapse(layer, loader) {
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
    r.tl = createTimelapse(frameHooks, layer, loader ? { loader } : {});
  }

  // ---- public ----
  // What a plug-in (plugins/) draws with: this engine's own helpers.
  const ctx = {
    g,
    gmap,
    ee: eeApi,
    store,
    recs,
    tileOverlay,
    eeTileLayer,
    addGeoJson,
    addFeatureSource,
    addTimelapse,
    setLoading,
    sync,
    fail,
    patch,
    groundOverlayUrl,
    tileBounds,
    // a plug-in that learns a layer's real kind (an Esri service's metadata)
    setKind(r, kind) {
      r.kind = kind;
      r.layerType = kind;
      patch(r.id, { kind }, "layer-kind");
    },
    setNote(r, note) {
      if (!recs.has(r.id) || r.note === note) return;
      r.note = note;
      patch(r.id, { note }, "layer-note");
    },
    setLegend(r, legend) {
      if (!recs.has(r.id)) return;
      r.legend = legend;
      patch(r.id, { legend }, "layer-legend");
    },
    fetch: deps.fetch,
  };

  async function addLayerToMap(layer) {
    const plugin = pluginFor(layer.kind);
    // Earth Engine is loaded and signed in for the first layer that needs it,
    // and only then; a failure is that layer's error, the others draw.
    if (plugin.needsEE && deps.eeLoader && !deps.eeLoader.isReady()) {
      // A visible layer the plug-in draws shows loading while Earth Engine
      // loads. Not one that is off, nor one a plug-in starts itself (a
      // timelapse reports its own frames; an area-chart-only layer is never
      // drawn): those would show loading with nothing to load.
      const shows = layer.visible && !isTimelapse(layer) && layer.kind !== "areaChartOnly";
      if (shows) store.update((s) => ({ ...s, layers: s.layers.map((l) => (l.id === layer.id ? { ...l, loading: true } : l)) }), "layer-loading");
      try {
        await deps.eeLoader.ensure();
      } catch (e) {
        failLayer(layer.id, e);
        return;
      }
      if (!store.get().layers.some((l) => l.id === layer.id)) return; // removed while loading
    }
    if (plugin.start && plugin.start(layer, ctx)) return;
    const layerType = layerTypeOf(layer);
    const r = {
      id: layer.id,
      kind: layer.kind,
      name: layer.name,
      layerType,
      tileType: TILE_TYPES.indexOf(layerType) > -1,
      dataType: DATA_TYPES.indexOf(layerType) > -1,
      visible: layer.visible,
      opacity: layer.opacity,
      overlay: null,
      loading: false,
      requests: 0,
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
      if (!plugin.ownsViz && vizIn.serialized === true && ["geoJSONVector", "tileMapService", "dynamicMapService"].indexOf(layerType) === -1) {
        item = eeApi.Deserializer.decode(item);
      }
      if (layerType === "geoJSONVector" && typeof item === "string") item = JSON.parse(item);
      const prepared = plugin.ownsViz ? { viz: vizIn, legend: null, item } : await prepareViz(item, vizIn, { name: layer.name, nextColor, ee: eeApi });
      if (!recs.has(r.id)) return resolveTarget(null);
      r.viz = prepared.viz;
      item = prepared.item;
      // port of 2templates.js addLayer: layer.queryItem = viz.queryItem || item
      let queryItem = r.viz.queryItem || item;
      if (r.viz.queryItem && vizIn.serialized === true && typeof queryItem.evaluate !== "function") queryItem = eeApi.Deserializer.decode(queryItem);
      // A wind layer is queried on its speed/direction image, not its tiles.
      const windItem = windQueryItem(r.viz, eeApi);
      const qType = r.layerType || r.viz.layerType;
      const target = { type: qType, item: windItem || queryItem, viz: r.viz, overlay: () => r.overlay, source: () => r.source };
      if (windItem) target.unitProps = WIND_UNIT_PROPS;
      resolveTarget(NOT_QUERYABLE.indexOf(qType) > -1 ? null : target);
      if (!r.layerType) {
        // layerType defaulted from the Earth Engine object type
        r.layerType = r.viz.layerType;
        r.tileType = TILE_TYPES.indexOf(r.layerType) > -1;
        r.dataType = DATA_TYPES.indexOf(r.layerType) > -1;
      }
      r.legend = prepared.legend;
      patch(r.id, { legend: prepared.legend }, "layer-legend");

      const drawn = plugin.draw(r, item, ctx);
      if (drawn && typeof drawn.then === "function") drawn.catch((e) => fail(r, e));
      // A plug-in's own legend (an Esri service's /legend), once it is drawn.
      if (plugin.legend) {
        Promise.resolve(drawn)
          .then(() => (recs.has(r.id) && !r.failed ? plugin.legend(r, ctx) : null))
          .then((lg) => lg && ctx.setLegend(r, lg))
          .catch(() => {});
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
    if (r.overlay && typeof r.overlay.setMap === "function") r.overlay.setMap(null);
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
  // A wind layer's tiles never go on the map (wind-particles.js fetches and
  // decodes them), so its progress comes from there as a percent; it fills the
  // row like any tile layer's, as a share of 100.
  const setLayerProgress = (id, percent) => {
    const r = recs.get(id);
    if (!r) return;
    const next = { total: 100, loaded: Math.max(0, Math.min(100, Math.round(percent))), failed: 0 };
    const prev = r.progress || {};
    if (prev.total === next.total && prev.loaded === next.loaded && prev.failed === 0) return;
    r.progress = next;
    patch(id, { progress: next }, "layer-progress");
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
  return { sync, addLayerToMap, setLayerVisible, setLayerOpacity, applyOrder, removeLayer, zOrder, slotOrder, stats, timelapse, queryTarget, windSources, onChange, setLayerLoading, setLayerProgress, retryTiles };
}
