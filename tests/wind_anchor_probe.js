// Drives the real wind-particles.js through a fast pan and reports, at
// each step, how far the speed raster sits from where it was painted
// for. Read by test_wind_raster_anchor.py.
//
// The bug (reported 2026-11-12): drag the map and let go so it keeps
// moving, and the speed raster slid with it and stayed off its anchor,
// showing one place's wind over another. The map's center moves ahead
// of the overlay's draw(); a repaint in between used draw()'s OLD
// origin but was keyed with the NEW center, so once draw() moved the
// canvas the key still matched and nothing repainted.
//
// A fake Mercator projection stands in for google.maps: world pixels
// at zoom 4, a fixed div-pixel base, longitude normalized into
// [-180, 180) the way google.maps does it.
"use strict";

const fs = require("fs");
const vm = require("vm");

const SRC = process.argv[2];
const Z = 4, WORLD = 256 * (1 << Z), W = 800, H = 600, DIV_BASE = 1000;

function makeEl(tag) {
  return {
    tagName: tag.toUpperCase(),
    style: { setProperty(k, v) { this[k] = v; } },
    children: [], appendChild(c) { this.children.push(c); },
    setAttribute() {}, getAttribute() { return null; }, addEventListener() {},
    getContext: () => ctx,
  };
}

// Each clearRect starts a paint: note the origin it is laid out from.
let st = null;
const paints = [];
const ctx = {
  clearRect() { paints.push({ x: st.origin.x, y: st.origin.y, nw: st.speedNw }); },
  createImageData: (w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
  putImageData() {}, drawImage() {}, globalAlpha: 1,
};

const sandbox = {
  console: { log() {}, warn() {}, error() {} },
  setInterval: () => 0, requestAnimationFrame: () => 1, cancelAnimationFrame: () => {},
  performance: { now: () => 0 },
};
sandbox.window = sandbox;
sandbox.document = {
  hidden: false, addEventListener() {}, getElementById: () => null,
  createElement: makeEl, head: makeEl("head"), documentElement: makeEl("html"),
};

function LatLng(lat, lng) {
  lng = ((lng + 180) % 360 + 360) % 360 - 180;    // google.maps normalizes
  this._lat = lat; this._lng = lng;
}
LatLng.prototype.lat = function () { return this._lat; };
LatLng.prototype.lng = function () { return this._lng; };

function toLL(wx, wy) {
  const lng = wx / WORLD * 360 - 180;
  const n = Math.PI * (1 - 2 * wy / WORLD);
  return new LatLng(180 / Math.PI * Math.atan(Math.sinh(n)), lng);
}
function toWorld(ll) {
  const x = (ll.lng() + 180) / 360 * WORLD;
  const s = Math.sin(ll.lat() * Math.PI / 180);
  const y = (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * WORLD;
  return { x, y };
}

// The map: `center` is where google.maps says it is; `drawn` is the
// center as of the overlay's last draw(). They differ mid-momentum.
const view = { cx: 900, cy: 1500 };
const proj = {
  fromContainerPixelToLatLng: p => toLL(view.cx - W / 2 + p.x, view.cy - H / 2 + p.y),
  fromLatLngToDivPixel: ll => { const w = toWorld(ll); return { x: w.x - DIV_BASE, y: w.y - DIV_BASE }; },
  fromDivPixelToLatLng: p => toLL(p.x + DIV_BASE, p.y + DIV_BASE),
  getWorldWidth: () => WORLD,
};
const mapPane = makeEl("div");
sandbox.google = { maps: {
  Point: function (x, y) { this.x = x; this.y = y; },
  OverlayView: function () {
    this.setMap = function () {};
    this.getPanes = () => ({ mapPane });
    this.getProjection = () => proj;
  },
} };
sandbox.map = {
  addListener() {}, getZoom: () => Z,
  getCenter: () => toLL(view.cx, view.cy),
  getDiv: () => ({ offsetWidth: W, offsetHeight: H }),
  overlayMapTypes: { getArray: () => [], getAt: () => undefined },
};

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(SRC, "utf8"), sandbox);
const WP = sandbox.geeVizWindParticles;

// Every tile is already decoded, so every paint completes and is cached.
const tile = new Uint8ClampedArray(256 * 256 * 4).fill(200);
st = {
  id: "w", frameId: "w", cfg: { speedRaster: true, rampMinMs: 0, rampMaxMs: 30,
    rampPalette: ["000000", "ffffff"], tileMin: -40, tileMax: 40, layerId: 0 },
  tiles: new Proxy({}, { get: () => tile }), tileFails: {}, inflight: 0,
  getTileUrl: () => "x", frames: {},
};
const ov = WP._makeOverlay(st);
ov.onAdd();

// How far the raster canvas is from the place its last paint was laid
// out for, in screen pixels. 0 means anchored.
function offset() {
  const last = paints[paints.length - 1];
  const nw = WP._speedCanvasAt(proj, proj.fromDivPixelToLatLng(last), last);
  const left = parseFloat(st.speedCanvas.style.left), top = parseFloat(st.speedCanvas.style.top);
  return Math.round(Math.hypot(left - nw.x, top - nw.y));
}

const out = {};
ov.draw(); WP._ensureSpeedRaster(st);
out.settled = offset();

// Momentum: the center moves on, draw() has not run yet, and the
// animation frame asks for a repaint.
view.cx += 300; view.cy += 120;
WP._ensureSpeedRaster(st);
out.midMomentum = offset();

// draw() catches up with the final center, then the next frame.
ov.draw();
out.afterDraw = offset();
WP._ensureSpeedRaster(st);
out.afterRepaint = offset();
// Anchored is not enough: the paint must also be FOR the view now on
// screen, or the edges the pan uncovered stay empty.
const last = paints[paints.length - 1];
out.coversView = last.x === st.origin.x && last.y === st.origin.y;
WP._ensureSpeedRaster(st);
out.paints = paints.length;

// Across the dateline: a paint made at lng ~179 shown from lng ~-179.
const pWest = { x: WORLD - DIV_BASE - 100, y: 0 };
const nwEast = proj.fromDivPixelToLatLng({ x: WORLD - DIV_BASE + 50, y: 0 });
out.datelineDx = Math.round(WP._speedCanvasAt(proj, nwEast, pWest).x - pWest.x);

process.stdout.write(JSON.stringify(out));
