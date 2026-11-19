// The Google map engine. The only DOM it touches is the map element it is
// given. UI chrome (buttons, body classes, the search input) lives in ui/.

export const DARK_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#1d1b1a" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#a39a93" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#141211" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#34302d" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#0f1a1c" }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
];

export const BASEMAPS = { satellite: "hybrid", map: "roadmap", dark: "dark" };

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
    mapTypeId: "hybrid",
    disableDefaultUI: true,
    disableDoubleClickZoom: true,
    clickableIcons: false,
    tilt: 0,
    streetViewControl: false,
    gestureHandling: "greedy",
  });
  gmap.mapTypes.set("dark", new g.StyledMapType(DARK_STYLE, { name: "Dark" }));

  const listeners = { history: [], streetView: [], pick: [], cursor: [], zoom: [], basemap: [] };
  const emit = (k, ...a) => listeners[k].forEach((fn) => fn(...a));
  const on = (k) => (fn) => {
    listeners[k].push(fn);
  };

  // ---- basemaps ----
  let basemap = "satellite";
  function setBasemap(key) {
    if (!BASEMAPS[key]) return;
    basemap = key;
    gmap.setMapTypeId(BASEMAPS[key]);
    emit("basemap", key);
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
  gmap.addListener("idle", () => {
    const here = currentView();
    const programmatic = pending !== null && sameView(here, pending);
    pending = null;
    if (!programmatic) hist.record(here);
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
      if (!eeReady) return resolve(null);
      try {
        const lat = typeof latLng.lat === "function" ? latLng.lat() : latLng.lat;
        const lng = typeof latLng.lng === "function" ? latLng.lng() : latLng.lng;
        ee.ImageCollection("projects/sat-io/open-datasets/GLO-30")
          .mosaic()
          .int16()
          .reduceRegion(ee.Reducer.first(), ee.Geometry.Point([lng, lat]))
          .get("b1")
          .evaluate((v) => resolve(v === undefined || v === null ? null : Number(v)));
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
    if (eeReady && !elevationBusy && now - lastElevationAt > 1000) {
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
    setCenter,
    centerObject,
    synchronousCenterObject,
    back,
    forward,
    history: () => hist.state(),
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
