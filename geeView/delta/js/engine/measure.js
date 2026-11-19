// Distance and Area tools: click the map to add vertices, double-click to
// finish, with a live readout while drawing. Ports of lcms-viewer
// 4map-manager.js distance and area measuring. Lengths and areas come from
// google.maps.geometry.spherical; the text from util.js formatLength and
// formatArea, in the units the Units switch holds.
import { formatLength, formatArea } from "../util.js";
import { sameLatLng, drawStyle, restyleShapes } from "./drawing.js";

const spherical = () => globalThis.google.maps.geometry.spherical;

export const MEASURE_ID = "measure";

export function distanceMeters(path) {
  return path.length < 2 ? 0 : spherical().computeLength(path);
}

export function perimeterMeters(path) {
  return path.length < 2 ? 0 : spherical().computeLength(path.concat([path[0]]));
}

export function areaSquareMeters(path) {
  return path.length < 3 ? 0 : spherical().computeArea(path);
}

// The result card for a path, or null when it has too few points.
export function measureResult(tool, path, units) {
  let lines;
  if (tool === "distance") {
    if (path.length < 2) return null;
    lines = [["Distance", formatLength(distanceMeters(path), units)]];
  } else {
    if (path.length < 3) return null;
    lines = [
      ["Area", formatArea(areaSquareMeters(path), units)],
      ["Perimeter", formatLength(perimeterMeters(path), units)],
    ];
  }
  const title = tool === "distance" ? "Distance" : "Area";
  return {
    id: MEASURE_ID,
    layerId: null,
    title,
    meta: path.length + " points",
    kind: "measure",
    data: { tool, lines, text: lines.map((l) => l.join(": ")).join("\n") },
    actions: ["copy", "clear"],
  };
}

// opts: google, colors() -> {stroke}, notify(msg)
export function createMeasure(engine, store, opts = {}) {
  const g = opts.google || globalThis.google.maps;
  const gmap = engine.gmap;
  const colors = opts.colors || (() => ({ stroke: "#e2602a" }));
  const picking = () => (engine.isPicking ? engine.isPicking() : false);
  const tool = () => store.get().tool;
  const active = () => tool() === "distance" || tool() === "area";

  let pts = []; // fixed vertices
  let hover = null; // the cursor, while drawing
  let drawing = false;
  let shape = null;

  const style = () => drawStyle(colors().stroke);
  function paint() {
    const path = drawing && hover ? pts.concat([hover]) : pts.slice();
    const wantPoly = tool() === "area" && (!drawing || path.length >= 3);
    if (shape && shape.isPoly !== wantPoly) {
      shape.setMap(null);
      shape = null;
    }
    if (!path.length) {
      if (shape) shape.setMap(null);
      shape = null;
      return path;
    }
    if (!shape) {
      shape = wantPoly ? new g.Polygon({ ...style(), paths: path, map: gmap }) : new g.Polyline({ ...style(), path, map: gmap });
      shape.isPoly = wantPoly;
    } else {
      shape.setOptions(style());
      if (wantPoly) shape.setPaths(path);
      else shape.setPath(path);
    }
    return path;
  }
  function readout(path) {
    const r = measureResult(tool(), path, store.get().units);
    store.set({ results: r ? [r] : [], where: "" }, "measure");
  }
  // Clear the drawing; with `output` also empty the results card.
  function clear(output = true) {
    pts = [];
    hover = null;
    drawing = false;
    if (shape) shape.setMap(null);
    shape = null;
    if (output) store.set({ results: [], where: "" }, "measure");
  }
  function ready(ev) {
    return ev && ev.latLng && !picking() && active();
  }

  gmap.addListener("click", (ev) => {
    if (!ready(ev)) return;
    if (!drawing) {
      // a click after a finished measurement starts a new one
      pts = [];
      drawing = true;
      store.set({ results: [], where: "" }, "measure");
    }
    // the second click of a double-click lands on the point just added
    if (!pts.length || !sameLatLng(pts[pts.length - 1], ev.latLng)) pts.push(ev.latLng);
    hover = null;
    readout(paint());
  });
  gmap.addListener("mousemove", (ev) => {
    if (!drawing || !ready(ev)) return;
    hover = ev.latLng;
    readout(paint());
  });
  gmap.addListener("dblclick", (ev) => {
    if (!drawing || !ready(ev)) return;
    if (ev.stop) ev.stop();
    finish();
  });
  function finish() {
    if (!drawing) return null;
    const need = tool() === "area" ? 3 : 2;
    if (pts.length < need) {
      if (opts.notify) opts.notify(tool() === "area" ? "Click at least three points to outline an area, then double-click to finish." : "Click at least two points to measure a distance, then double-click to finish.");
      return null;
    }
    drawing = false;
    hover = null;
    const path = paint();
    readout(path);
    return path;
  }
  if (typeof document !== "undefined")
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && drawing && active()) clear();
    });

  // switching tools clears the previous tool's drawing; the tool-output reset
  // in tools.js empties the results
  store.on("change:tool", () => {
    clear(false);
  });
  // units re-render the card without redrawing
  store.on("change:units", () => {
    if (active() && shape) readout(drawing && hover ? pts.concat([hover]) : pts);
  });
  // anything else that empties the output removes the drawing
  store.on("change:results", (v, st, reason) => {
    if (reason !== "measure" && shape && !(v || []).length) clear(false);
  });

  return { finish, clear: () => clear(), restyle: () => restyleShapes([shape], colors().stroke), path: () => pts.slice() };
}
