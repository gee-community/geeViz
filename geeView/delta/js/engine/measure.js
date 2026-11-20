// Distance and Area tools: click the map to add vertices, double-click to
// finish, with a live readout while drawing. Ports of lcms-viewer
// 4map-manager.js distance and area measuring; the drawing, undo/redo and
// editing are engine/sketch.js, shared with Chart area's Draw. Area is
// multi-polygon (the original's areaPolygonObj): after a polygon is finished,
// a click starts another and the card totals them. Lengths and areas come
// from google.maps.geometry.spherical; the text from util.js formatLength and
// formatArea, in the units the Units switch holds.
import { formatLength, formatArea } from "../util.js";
import { createSketch } from "./sketch.js";

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

// A list of paths, or one path (a list of points).
const asPaths = (p) => (p.length && Array.isArray(p[0]) ? p : [p]);

// The result card, or null when there is nothing to measure yet. `paths` is
// one path or a list of them (Area's polygons; shapes too small are skipped).
export function measureResult(tool, paths, units) {
  const all = asPaths(paths || []);
  let lines;
  let points;
  if (tool === "distance") {
    const path = all[all.length - 1] || [];
    if (path.length < 2) return null;
    lines = [["Distance", formatLength(distanceMeters(path), units)]];
    points = path.length;
  } else {
    const polys = all.filter((p) => p.length >= 3);
    if (!polys.length) return null;
    points = polys.reduce((a, p) => a + p.length, 0);
    if (polys.length === 1) {
      lines = [
        ["Area", formatArea(areaSquareMeters(polys[0]), units)],
        ["Perimeter", formatLength(perimeterMeters(polys[0]), units)],
      ];
    } else {
      // port of updateArea: the total across polygons, then each one
      const each = polys.map((p) => areaSquareMeters(p));
      lines = [["Total area", formatArea(each.reduce((a, b) => a + b, 0), units)]];
      each.forEach((a, i) => lines.push(["Polygon " + (i + 1), formatArea(a, units)]));
    }
  }
  const title = tool === "distance" ? "Distance" : "Area";
  const polyCount = tool === "area" ? all.filter((p) => p.length >= 3).length : 1;
  return {
    id: MEASURE_ID,
    layerId: null,
    title,
    meta: (polyCount > 1 ? polyCount + " polygons, " : "") + points + " points",
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

  function readout(sk) {
    const t = tool();
    const st = sk.state();
    // finished shapes as drawn, the open one following the cursor
    const paths = sk.paths(false);
    if (st.open) paths.push(sk.pathWithHover());
    const r = measureResult(t, paths, store.get().units);
    store.set({ results: r ? [r] : [], where: "" }, "measure");
  }
  function make(name, polygon) {
    const sk = createSketch({
      google: g,
      gmap,
      polygon,
      multi: polygon,
      active: () => tool() === name,
      picking,
      color: () => colors().stroke,
      tooFew: () =>
        opts.notify &&
        opts.notify(polygon ? "Click at least three points to outline an area, then double-click to finish." : "Click at least two points to measure a distance, then double-click to finish."),
      onChange: (state, hover, why, status) => {
        if (why !== "reset") readout(sk);
        store.set({ sketch: { tool: name, ...status } }, "sketch");
      },
    });
    return sk;
  }
  const sketches = { distance: make("distance", false), area: make("area", true) };
  const current = () => sketches[tool()] || null;

  // switching tools starts each tool over; the tool-output reset in tools.js
  // empties the results
  store.on("change:tool", () => {
    Object.values(sketches).forEach((s) => s.reset());
  });
  // units re-render the card without redrawing
  store.on("change:units", () => {
    const sk = current();
    if (sk && sk.state().shapes.length) readout(sk);
  });
  // anything else that empties the output removes the drawing
  store.on("change:results", (v, st, reason) => {
    const sk = current();
    if (reason !== "measure" && sk && sk.state().shapes.length && !(v || []).length) sk.reset();
  });

  const call = (fn) => () => {
    const sk = current();
    return sk ? sk[fn]() : null;
  };
  return {
    finish: call("finish"),
    undo: call("undo"),
    redo: call("redo"),
    // the card's Clear: an undoable step, then the empty output
    clear() {
      const sk = current();
      if (sk) sk.clear();
      store.set({ results: [], where: "" }, "measure");
    },
    restyle: () => Object.values(sketches).forEach((s) => s.restyle()),
    // the last shape's points (Google LatLngs); paths() all of them
    path: () => {
      const sk = current();
      const p = sk ? sk.paths() : [];
      return p.length ? p[p.length - 1] : [];
    },
    paths: () => (current() ? current().paths() : []),
    sketch: (name) => sketches[name],
  };
}
