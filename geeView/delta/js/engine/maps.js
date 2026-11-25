// The Google map engine. The only DOM it touches is the map element it is
// given. UI chrome (buttons, body classes, the search input) lives in ui/.

// Satellite and Map carry no labels of their own: labels come from the
// labels overlay above every layer, so a layer never hides them, they are
// never drawn twice, and one toggle turns them off.
//
// Terrain and Dark terrain are Google's terrain type, whose hillshade only
// map-wide styles can restyle. While map-wide styles are set, Google draws
// every StyledMapType overlay unstyled (seen in Chrome: the satellite labels
// lost their white text), so those two basemaps draw their own labels,
// under the layers, and get no overlay. The other basemaps set no map styles.
import { esriRequest } from "../esri/rest.js";

export const BASEMAPS = { satellite: "satellite", map: "roadmap-base", terrain: "terrain", darkterrain: "terrain" };
const NO_LABELS = [{ elementType: "labels", stylers: [{ visibility: "off" }] }];
export const OWN_LABELS = new Set(["terrain", "darkterrain"]);
export const DARK_TERRAIN_STYLE = [
  // Darken the land relative to its own colors, not to one flat color: Google
  // draws the hillshade over the land and ignores styles on it, so over a flat
  // fill its lit (northwest-facing) slopes wash out to one gray.
  { featureType: "landscape", elementType: "geometry", stylers: [{ saturation: -60 }, { lightness: -80 }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  // peak and park markers
  { featureType: "landscape", elementType: "labels.icon", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#3a3531" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#0f1a1c" }] },
  { featureType: "administrative", elementType: "geometry", stylers: [{ visibility: "off" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#c9c0b8" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#141211" }] },
];
const TERRAIN_STYLE = [
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "landscape", elementType: "labels.icon", stylers: [{ visibility: "off" }] },
];
// The map-wide styles for a basemap: null (none) except on the terrain types.
export function mapStylesFor(key, labelsOn) {
  if (!OWN_LABELS.has(key)) return null;
  const base = key === "darkterrain" ? DARK_TERRAIN_STYLE : TERRAIN_STYLE;
  return labelsOn ? base : [...base, ...NO_LABELS];
}

// The labels overlay: a labels-only map drawn above every layer, so opaque
// layers do not hide place names. port of 4map-manager.js labelsMapType
// (geometry fill off, strokes as hairlines).
export const LABELS_STYLE = [
  { elementType: "geometry.fill", stylers: [{ visibility: "off" }] },
  { elementType: "geometry.stroke", stylers: [{ weight: 0.01 }] },
];
// Labels for the satellite basemap look like Google's hybrid labels: light
// text with a dark halo, readable on imagery.
export const SATELLITE_LABELS_STYLE = [
  ...LABELS_STYLE,
  { elementType: "labels.text.fill", stylers: [{ color: "#ffffff" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#000000" }, { weight: 2 }] },
];
// port of smartAddLabelOverlay: on unless the URL says addLabelOverlay=false.
// The original's urlParams are JSON-parsed (false); Delta's are strings.
export const labelsEnabled = (params) => String((params || {}).addLabelOverlay) !== "false";

const SAME = 1e-7;

// Resolves once the async Google Maps script (with places) has defined itself.
export function whenGoogleReady(timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    (function poll() {
      const g = window.google;
      if (g && g.maps && g.maps.Map && g.maps.places) return resolve(g);
      if (Date.now() - t0 > timeoutMs) return reject(new Error("Google Maps did not load"));
      setTimeout(poll, 50);
    })();
  });
}

// The elevation at a point: the GLO-30 mosaic at its own 30 m. port of
// 4map-manager.js getElevation, which leaves out the scale: a mosaic has no
// projection of its own (1 degree pixels), so every point within the same
// degree read one value (1861 m all over the Wasatch).
export const ELEVATION_SCALE = 30;
export function elevationValue(ee, lng, lat) {
  return ee
    .ImageCollection("projects/sat-io/open-datasets/GLO-30")
    .mosaic()
    .int16()
    .reduceRegion(ee.Reducer.first(), ee.Geometry.Point([lng, lat]), ELEVATION_SCALE)
    .get("b1");
}

// Without Earth Engine: USGS 3DEP, the United States' elevation service
// (identify at the point; elsewhere it answers NoData). Meters, rounded.
export const ELEVATION_3DEP_URL = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer";
export async function elevation3DEP(lng, lat, opts = {}) {
  try {
    const out = await esriRequest(
      ELEVATION_3DEP_URL + "/identify",
      { geometry: { x: lng, y: lat, spatialReference: { wkid: 4326 } }, geometryType: "esriGeometryPoint", returnGeometry: false, returnCatalogItems: false },
      { fetch: opts.fetch }
    );
    const v = Number(out && out.value);
    return out && out.value !== "NoData" && Number.isFinite(v) ? Math.round(v) : null;
  } catch (e) {
    return null;
  }
}

// True when two views are the same to within `px` screen pixels at their zoom.
export function sameView(a, b, px = 2) {
  if (a.zoom !== b.zoom) return false;
  const degPerPx = 360 / (256 * Math.pow(2, a.zoom));
  return Math.abs(a.lng - b.lng) <= px * degPerPx && Math.abs(a.lat - b.lat) <= px * degPerPx;
}

// Pure view-history stack. port of 4map-manager.js trackView, checkViewIndex,
// backView and forwardView: a list plus a 1-based index; recording truncates
// the forward branch. Recording a view equal to the current one is ignored,
// which replaces the original's `updateViewList` flag (that flag stuck when a
// back/forward landed on a view that fires no idle event).
export function createViewHistory() {
  let list = [];
  let index = 0;
  const near = (a, b) => Math.abs(a.lng - b.lng) < SAME && Math.abs(a.lat - b.lat) < SAME && a.zoom === b.zoom;
  return {
    record(view) {
      if (index > 0 && near(list[index - 1], view)) return false;
      list = list.slice(0, index);
      list.push({ lng: view.lng, lat: view.lat, zoom: view.zoom });
      index = list.length;
      return true;
    },
    back() {
      if (index <= 1) return null;
      index--;
      return list[index - 1];
    },
    forward() {
      if (index >= list.length) return null;
      index++;
      return list[index - 1];
    },
    state() {
      return { index, length: list.length, canBack: index > 1, canForward: index < list.length };
    },
  };
}

export function createMap(el, store) {
  const g = window.google.maps;
  const params = window.urlParams || {};
  const num = (v, d) => (v !== undefined && v !== null && v !== "" && Number.isFinite(Number(v)) ? Number(v) : d);

  const gmap = new g.Map(el, {
    center: { lat: num(params.lat, 39.5), lng: num(params.lng, -98.5) },
    zoom: num(params.zoom, 4),
    minZoom: 2,
    mapTypeId: "satellite",
    disableDefaultUI: true,
    // Google's scale bar, in its strip with the logo and data credits
    scaleControl: true,
    disableDoubleClickZoom: true,
    clickableIcons: false,
    tilt: 0,
    streetViewControl: false,
    gestureHandling: "greedy",
  });
  gmap.mapTypes.set("roadmap-base", new g.StyledMapType(NO_LABELS, { name: "Map" }));
  // One labels map type per basemap style, made once; the layer engine stacks
  // the current one above every layer (engine/layers.js sync). The toggle
  // (setLabels) starts from the URL (addLabelOverlay=false starts it off).
  let labelsOn = labelsEnabled(params);
  const labels = {
    satellite: new g.StyledMapType(SATELLITE_LABELS_STYLE, { name: "Satellite labels" }),
    map: new g.StyledMapType(LABELS_STYLE, { name: "Labels" }),
  };

  const listeners = { history: [], streetView: [], pick: [], cursor: [], zoom: [], basemap: [], labels: [] };
  const emit = (k, ...a) => listeners[k].forEach((fn) => fn(...a));
  const on = (k) => (fn) => {
    listeners[k].push(fn);
  };

  // ---- basemaps ----
  let basemap = "satellite";
  function setBasemap(key) {
    if (!BASEMAPS[key]) return;
    basemap = key;
    gmap.setOptions({ styles: mapStylesFor(key, labelsOn) });
    gmap.setMapTypeId(BASEMAPS[key]);
    emit("basemap", key);
  }
  function setLabels(on) {
    on = !!on;
    if (on === labelsOn) return;
    labelsOn = on;
    if (OWN_LABELS.has(basemap)) gmap.setOptions({ styles: mapStylesFor(basemap, on) });
    // Remembered the way the original reads it: addLabelOverlay=false in the URL.
    try {
      const url = new URL(location.href);
      if (on) url.searchParams.delete("addLabelOverlay");
      else url.searchParams.set("addLabelOverlay", "false");
      if (url.href !== location.href) history.replaceState(history.state, "", url);
    } catch (e) {
      /* no URL to update (tests, file pages) */
    }
    emit("labels", on);
  }

  // ---- centering ----
  function setCenter(lng, lat, zoom) {
    gmap.setCenter({ lat: Number(lat), lng: Number(lng) });
    if (zoom !== undefined && zoom !== null) gmap.setZoom(Number(zoom));
  }
  // port of 4map-manager.js synchronousCenterObject
  function synchronousCenterObject(feature) {
    const bounds = new g.LatLngBounds();
    feature.coordinates[0].forEach((p) => bounds.extend({ lng: p[0], lat: p[1] }));
    gmap.fitBounds(bounds);
  }
  // port of 4map-manager.js centerObject. Always evaluates asynchronously:
  // Delta never blocks the browser with getInfo.
  function centerObject(fc, _async, callback) {
    const done = (f) => {
      synchronousCenterObject(f);
      if (typeof callback === "function") callback();
    };
    let geom;
    try {
      geom = typeof fc.geometry === "function" ? fc.geometry() : fc;
    } catch (e) {
      geom = fc;
    }
    try {
      geom.bounds(100).evaluate((f, err) => {
        if (f) done(f);
        else if (window.console) console.error("centerObject failed:", err);
      });
    } catch (e) {
      try {
        fc.bounds(100).evaluate((f) => f && done(f));
      } catch (e2) {
        if (window.console) console.error("centerObject failed:", e2);
      }
    }
  }

  // ---- your location (the locate button) ----
  // A dot at the position and a circle for its accuracy, replaced on the
  // next locate. Neither takes clicks, so tools work through them.
  let here = null;
  function showLocation(lat, lng, accuracy) {
    const pos = { lat, lng };
    if (!here) {
      here = {
        circle: new g.Circle({ map: gmap, clickable: false, strokeColor: "#1a73e8", strokeOpacity: 0.5, strokeWeight: 1, fillColor: "#1a73e8", fillOpacity: 0.12, zIndex: 3300 }),
        marker: new g.Marker({
          map: gmap,
          clickable: false,
          zIndex: 3301,
          title: "Your location",
          icon: { path: g.SymbolPath.CIRCLE, scale: 7, fillColor: "#1a73e8", fillOpacity: 1, strokeColor: "#ffffff", strokeWeight: 2 },
        }),
      };
    }
    here.marker.setPosition(pos);
    here.circle.setCenter(pos);
    here.circle.setRadius(Number.isFinite(accuracy) ? accuracy : 0);
  }

  // ---- view history ----
  const hist = createViewHistory();
  const currentView = () => {
    const c = gmap.getCenter();
    return { lng: c.lng(), lat: c.lat(), zoom: gmap.getZoom() };
  };
  // A back/forward move is programmatic: the idle it causes must not be
  // recorded, whatever rounding getCenter() adds. `pending` is the target; the
  // next idle at (about) that view is swallowed, any other idle is a real move.
  let pending = null;
  // Nothing is recorded until the map script has run (startHistory): the
  // first view is the one it set, not the default view the page opens on.
  let recording = false;
  function startHistory() {
    if (recording) return;
    recording = true;
    hist.record(currentView());
    emit("history", hist.state());
  }
  gmap.addListener("idle", () => {
    const here = currentView();
    const programmatic = pending !== null && sameView(here, pending);
    pending = null;
    if (!programmatic && recording) hist.record(here);
    emit("history", hist.state());
    emit("zoom", gmap.getZoom());
  });
  function apply(view) {
    if (!view) return;
    // No move, no idle: do not leave a pending target to swallow the next pan.
    pending = sameView(currentView(), view, 0.01) ? null : view;
    setCenter(view.lng, view.lat, view.zoom);
    emit("history", hist.state());
  }
  const back = () => apply(hist.back());
  const forward = () => apply(hist.forward());

  // ---- elevation ----
  // port of 4map-manager.js getElevation (GLO-30 mosaic, first value at a point)
  let eeReady = false;
  function elevationAt(latLng) {
    return new Promise((resolve) => {
      const lat = typeof latLng.lat === "function" ? latLng.lat() : latLng.lat;
      const lng = typeof latLng.lng === "function" ? latLng.lng() : latLng.lng;
      // a map with no Earth Engine (or before it signs in): 3DEP
      if (!eeReady) return elevation3DEP(lng, lat).then(resolve);
      try {
        elevationValue(ee, lng, lat).evaluate((v) => resolve(v === undefined || v === null ? null : Number(v)));
      } catch (e) {
        resolve(null);
      }
    });
  }

  // Cursor position, throttled elevation (one lookup per second, as the original).
  let lastElevationAt = 0;
  let elevationBusy = false;
  gmap.addListener("mousemove", (ev) => {
    if (!ev.latLng) return;
    const lat = ev.latLng.lat();
    const lng = ev.latLng.lng();
    emit("cursor", lat, lng, undefined);
    const now = Date.now();
    if (!elevationBusy && now - lastElevationAt > 1000) {
      lastElevationAt = now;
      elevationBusy = true;
      elevationAt(ev.latLng).then((m) => {
        elevationBusy = false;
        emit("cursor", lat, lng, m);
      });
    }
  });

  // ---- Street View ----
  // The pick button shows the coverage layer; a click on a blue line opens the
  // nearest outdoor panorama. Google's own close button hides the panorama.
  const pano = gmap.getStreetView();
  pano.setOptions({
    addressControl: true,
    fullscreenControl: false,
    enableCloseButton: true,
    motionTracking: false,
    panControl: true,
    zoomControl: true,
  });
  const coverage = new g.StreetViewCoverageLayer();
  const svc = new g.StreetViewService();
  let picking = false;
  function streetViewPick(on) {
    picking = !!on;
    coverage.setMap(picking ? gmap : null);
    emit("pick", picking);
  }
  gmap.addListener("click", (ev) => {
    if (!picking || !ev.latLng) return;
    svc.getPanorama({ location: ev.latLng, radius: 80, source: g.StreetViewSource.OUTDOOR }, (data, status) => {
      if (status === g.StreetViewStatus.OK) {
        pano.setPano(data.location.pano);
        pano.setPov({ heading: 0, pitch: 0 });
        pano.setVisible(true);
      } else if (store) {
        // Stay in pick mode so the next click can try a blue line.
        store.update((s) => ({ ...s, notices: [...s.notices, "No Street View imagery here. Click a blue line."] }), "notice");
      }
    });
  });
  pano.addListener("visible_changed", () => {
    const v = pano.getVisible();
    if (v) streetViewPick(false);
    emit("streetView", v);
  });

  gmap.addListener("zoom_changed", () => emit("zoom", gmap.getZoom()));

  return {
    gmap,
    setBasemap,
    basemap: () => basemap,
    // The labels map type for the current basemap; null while labels are off
    // or on a basemap that draws its own (OWN_LABELS).
    labelsOverlay: () => (labelsOn && labels[basemap]) || null,
    labelsOn: () => labelsOn,
    setLabels,
    onLabels: on("labels"),
    setCenter,
    showLocation,
    location: () => (here ? { lat: here.marker.getPosition().lat(), lng: here.marker.getPosition().lng(), accuracy: here.circle.getRadius() } : null),
    centerObject,
    synchronousCenterObject,
    back,
    forward,
    history: () => hist.state(),
    startHistory,
    zoomBy: (d) => gmap.setZoom(gmap.getZoom() + d),
    streetViewPick,
    isPicking: () => picking,
    onStreetView: on("streetView"),
    onPick: on("pick"),
    onHistory: on("history"),
    onCursor: on("cursor"),
    onZoom: on("zoom"),
    onBasemap: on("basemap"),
    elevationAt,
    setEEReady: (ok) => {
      eeReady = !!ok;
    },
  };
}
