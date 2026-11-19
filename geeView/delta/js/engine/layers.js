// Map layers: Earth Engine images, collections and vector images as tile
// overlays, vectors as google.maps.Data, external XYZ tile services, and
// dynamic (export) map services as ground overlays. The only DOM it touches
// is through Google map objects.
//
// port of lcms-viewer 2templates.js addLayer (as bundled in
// geeView/src/js/lcms-viewer.min.js, with its LOCAL PATCH tile legend v3) and
// 4map-manager.js getGroundOverlay. Store-driven: the engine reacts to each
// layer's `visible` and `opacity` and to `order`, and writes `loading`,
// `error` and `legend` back.
import { prepareViz, createColorCycle, normVecStyle } from "./viz.js";

const TILE_TYPES = ["geeImage", "geeImageCollection", "geeVectorImage", "tileMapService"];
const DATA_TYPES = ["geeVector", "geoJSONVector"];
const VIZ_KEYS = ["bands", "min", "max", "gain", "bias", "gamma", "palette", "forceRgbOutput"];
// the original's possibleVizKeys
const POSSIBLE_VIZ_KEYS = ["bands", "min", "max", "gain", "bias", "gamma", "palette", "color"];
const SKIP_KINDS = ["timelapse", "select", "areaChartOnly"];

function layerTypeOf(layer) {
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
  function sync() {
    const omt = gmap.overlayMapTypes;
    const tiles = stackOrder(order, (id) => recs.has(id) && recs.get(id).tileType);
    while (omt.getLength() < tiles.length) omt.push(null);
    tiles.forEach((id, i) => {
      const r = recs.get(id);
      const want = r.visible && r.overlay ? r.overlay : null;
      if (omt.getAt(i) !== want) omt.setAt(i, want);
    });
    for (let i = tiles.length; i < omt.getLength(); i++) if (omt.getAt(i) !== null) omt.setAt(i, null);
    const vectors = stackOrder(order, (id) => recs.has(id) && recs.get(id).dataType);
    vectors.forEach((id, i) => {
      const r = recs.get(id);
      const z = 1000 + i;
      if (r.overlay && r.zIndex !== z) {
        r.zIndex = z;
        applyDataStyle(r);
      }
    });
  }

  function applyOrder(next) {
    order = next.slice();
    sync();
  }

  // ---- Data (vector) layers ----
  function applyDataStyle(r) {
    if (!r.overlay) return;
    const style = { ...r.style, zIndex: r.zIndex || 1000 };
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
  // A tile overlay counts the tiles it is asked for and reports loading until
  // Google's tilesloaded. port of 2templates.js addLayer geeAltService.
  function tileOverlay(r, urlFor, extra = {}) {
    const overlay = new g.ImageMapType({
      tileSize: new g.Size(256, 256),
      ...extra,
      getTileUrl: (coord, zoom) => {
        r.requests++;
        if (r.visible) setLoading(r, true);
        return urlFor(coord, zoom);
      },
    });
    overlay.addListener("tilesloaded", () => setLoading(r, false));
    overlay.setOpacity(r.opacity);
    return overlay;
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
    // port of 2templates.js addLayer getGEEMapService
    const vizFound = POSSIBLE_VIZ_KEYS.some((k) => k in viz);
    let usedViz = {};
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
        if (!recs.has(r.id)) return;
        if (eeLayer === undefined && tries <= 1) return request();
        if (eeLayer === undefined || failure !== undefined) return fail(r, failure || "Earth Engine did not return a map service");
        const tilesUrl = eeLayer.urlFormat;
        r.overlay = tileOverlay(r, (coord, zoom) => tilesUrl.replace("{x}", coord.x).replace("{y}", coord.y).replace("{z}", zoom));
        if (!r.visible) setLoading(r, false);
        sync();
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

  // ---- public ----
  async function addLayerToMap(layer) {
    if (SKIP_KINDS.indexOf(layer.kind) > -1) return;
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
    };
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
      if (!recs.has(r.id)) return;
      r.viz = prepared.viz;
      item = prepared.item;
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
      fail(r, e);
    }
  }

  function setLayerVisible(id, on) {
    const r = recs.get(id);
    if (!r) return;
    r.visible = !!on;
    if (r.tileType) sync();
    else if (r.dataType) r.overlay && r.overlay.setMap(on ? gmap : null);
    else if (r.layerType === "dynamicMapService") refreshGround(r);
    if (!on) setLoading(r, false);
  }

  function setLayerOpacity(id, a) {
    const r = recs.get(id);
    if (!r) return;
    r.opacity = a;
    if (r.dataType) {
      r.opacityTouched = true;
      applyDataStyle(r);
    } else if (r.overlay) r.overlay.setOpacity(a);
  }

  function removeLayer(layer) {
    const r = recs.get(layer.id);
    if (!r) return;
    recs.delete(layer.id);
    if (r.listener) r.listener.remove();
    if (r.overlay && (r.dataType || r.layerType === "dynamicMapService")) r.overlay.setMap(null);
    order = order.filter((id) => id !== layer.id);
    sync();
  }

  // What is drawn, bottom to top: tile overlays by overlayMapTypes index and
  // Data layers by zIndex. For tests and debugging.
  function zOrder() {
    const byOverlay = new Map();
    recs.forEach((r) => r.overlay && byOverlay.set(r.overlay, r.id));
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
    return r ? { requests: r.requests, loading: r.loading, layerType: r.layerType, onMap: !!(r.overlay && (r.tileType ? gmap.overlayMapTypes.getArray().includes(r.overlay) : r.overlay.getMap())) } : null;
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

  return { addLayerToMap, setLayerVisible, setLayerOpacity, applyOrder, removeLayer, zOrder, slotOrder, stats };
}
