// Sketching on the map, shared by Distance, Area and Chart area's Draw so
// they edit the same way. Port of lcms-viewer 4map-manager.js startArea /
// startDistance / undoAreaMeasuring and 5chart-manager.js
// startUserDefinedAreaCharting / undoUserDefinedAreaCharting:
//   click adds a point, double-click finishes the shape;
//   polygons: clicking after a finished polygon starts another one;
//   lines: clicking after a finished line starts over;
//   ctrl+z undoes, ctrl+shift+z and ctrl+y redo, Delete or Backspace clears,
//   Escape drops the shape being drawn;
//   finished shapes are editable: drag a vertex, or a midpoint to add one.
// Every change (point, finish, vertex edit, clear) is one undo step.
import { sameLatLng, drawStyle } from "./drawing.js";

const lit = (p) => ({ lat: typeof p.lat === "function" ? p.lat() : p.lat, lng: typeof p.lng === "function" ? p.lng() : p.lng });
const clone = (s) => ({ shapes: s.shapes.map((sh) => sh.map((p) => ({ lat: p.lat, lng: p.lng }))), open: s.open });
export const EMPTY = Object.freeze({ shapes: [], open: false });
const DUP_PX = 3;

// ---- the model: plain {lat, lng} points, no Google objects ----

// Add a point. Polygons (multi) start another shape after a finished one;
// lines replace the finished one. Returns null for the repeated second click
// of a double-click.
export function addPoint(state, p, multi, tol = 1e-9) {
  const s = clone(state);
  if (!s.open) {
    if (multi) s.shapes.push([]);
    else s.shapes = [[]];
    s.open = true;
  }
  const cur = s.shapes[s.shapes.length - 1];
  const last = cur[cur.length - 1];
  // within tol degrees of the last point: the second click of a double-click
  if (last && Math.abs(last.lat - p.lat) < tol && Math.abs(last.lng - p.lng) < tol) return null;
  cur.push({ lat: p.lat, lng: p.lng });
  return s;
}
// Finish the open shape; null when it has fewer than `min` points.
export function finishShape(state, min) {
  if (!state.open) return null;
  const cur = state.shapes[state.shapes.length - 1];
  if (cur.length < min) return null;
  return { ...clone(state), open: false };
}
// Drop the shape being drawn (Escape).
export function dropOpen(state) {
  if (!state.open) return null;
  const s = clone(state);
  s.shapes.pop();
  s.open = false;
  return s;
}
export const finished = (state) => (state.open ? state.shapes.slice(0, -1) : state.shapes);

// Snapshot history: undo and redo step through it; a new step drops the redo branch.
export function createHistory() {
  let stack = [clone(EMPTY)];
  let i = 0;
  return {
    push(s) {
      stack = stack.slice(0, i + 1);
      stack.push(clone(s));
      i = stack.length - 1;
    },
    undo() {
      if (i === 0) return null;
      i--;
      return clone(stack[i]);
    },
    redo() {
      if (i >= stack.length - 1) return null;
      i++;
      return clone(stack[i]);
    },
    reset() {
      stack = [clone(EMPTY)];
      i = 0;
    },
    canUndo: () => i > 0,
    canRedo: () => i < stack.length - 1,
  };
}

// True when a key event is the shortcut and focus is not in a text field.
const typing = (e) => {
  const t = e.target;
  return !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ""));
};
export function shortcut(e) {
  if (typing(e)) return null;
  const k = String(e.key || "").toLowerCase();
  const mod = e.ctrlKey || e.metaKey;
  if (mod && k === "z") return e.shiftKey ? "redo" : "undo";
  if (mod && k === "y") return "redo";
  if (!mod && (e.key === "Delete" || e.key === "Backspace")) return "clear";
  if (e.key === "Escape") return "drop";
  return null;
}

// opts: google, gmap, polygon (bool), multi (bool), active() -> bool,
// picking() -> bool, color() -> stroke, onChange(state, hover, why),
// tooFew(), name (for the store's sketch status).
export function createSketch(opts) {
  const g = opts.google || globalThis.google.maps;
  const gmap = opts.gmap;
  const polygon = !!opts.polygon;
  const min = polygon ? 3 : 2;
  const active = opts.active;
  const picking = opts.picking || (() => false);
  const color = opts.color || (() => "#e2602a");
  const onChange = opts.onChange || (() => {});
  const history = createHistory();

  let state = clone(EMPTY);
  let hover = null;
  let objs = []; // one Google shape per state shape
  let syncing = false; // our own setPath calls must not read back as edits

  const style = () => drawStyle(color());

  // ---- drawing the state ----
  function openPath() {
    const cur = state.shapes[state.shapes.length - 1] || [];
    return hover ? cur.concat([hover]) : cur;
  }
  function render() {
    syncing = true;
    objs.forEach((o) => o.setMap(null));
    objs = state.shapes.map((pts, i) => {
      const isOpen = state.open && i === state.shapes.length - 1;
      const path = isOpen ? openPath() : pts;
      return makeShape(path, isOpen);
    });
    syncing = false;
  }
  function makeShape(path, isOpen) {
    const asPoly = polygon && (!isOpen || path.length >= 3);
    const o = asPoly
      ? new g.Polygon({ ...style(), paths: path, map: gmap, editable: !isOpen, clickable: true })
      : new g.Polyline({ ...style(), path, map: gmap, editable: !isOpen, clickable: true });
    o.isPoly = asPoly;
    o.isOpen = isOpen;
    // clicks on a shape draw on, as clicks on the map do (not vertex handles)
    o.addListener("click", (ev) => {
      if (ev && (ev.vertex !== undefined || ev.edge !== undefined)) return;
      onClick(ev);
    });
    o.addListener("dblclick", (ev) => {
      if (ev && ev.stop) ev.stop();
      onDblClick(ev);
    });
    // the map hears no mouse moves over a shape: keep the rubber band going
    o.addListener("mousemove", (ev) => onMove(ev));
    if (!isOpen) {
      const paths = asPoly ? [o.getPath()] : [o.getPath()];
      paths.forEach((p) => ["set_at", "insert_at", "remove_at"].forEach((t) => p.addListener(t, () => !syncing && edited())));
    }
    return o;
  }
  // Only the open shape follows the cursor: no rebuild per mouse move.
  function paintHover() {
    if (!state.open) return;
    const i = state.shapes.length - 1;
    const o = objs[i];
    const path = openPath();
    const wantPoly = polygon && path.length >= 3;
    syncing = true;
    if (!o || o.isPoly !== wantPoly) {
      if (o) o.setMap(null);
      objs[i] = makeShape(path, true);
    } else if (o.isPoly) o.setPaths(path);
    else o.setPath(path);
    syncing = false;
  }
  function edited() {
    // a vertex dragged or added on a finished shape
    const shapes = state.shapes.map((pts, i) => {
      const o = objs[i];
      if (!o || o.isOpen) return pts;
      return o.getPath().getArray().map(lit);
    });
    commit({ shapes, open: state.open }, "edit", false);
  }

  function status() {
    return { canUndo: history.canUndo(), canRedo: history.canRedo(), shapes: state.shapes.length, drawing: state.open };
  }
  function commit(next, why, redraw = true) {
    state = clone(next);
    history.push(state);
    if (why !== "point") hover = null;
    if (redraw) render();
    onChange(state, hover, why, status());
  }
  function restore(next, why) {
    if (!next) return false;
    state = next;
    hover = null;
    render();
    onChange(state, hover, why, status());
    return true;
  }

  // ---- input ----
  const ready = (ev) => ev && ev.latLng && !picking() && active();
  function onClick(ev) {
    if (!ready(ev)) return;
    // the clicks of a double-click land within a few pixels of each other
    const z = gmap.getZoom ? gmap.getZoom() : 20;
    const next = addPoint(state, lit(ev.latLng), !!opts.multi, (DUP_PX * 360) / (256 * Math.pow(2, z)));
    if (next) commit(next, "point");
  }
  function onDblClick(ev) {
    if (!ready(ev) || !state.open) return;
    if (ev && ev.stop) ev.stop();
    finish();
  }
  function finish() {
    if (!state.open) return null;
    const next = finishShape(state, min);
    if (!next) {
      if (opts.tooFew) opts.tooFew();
      return null;
    }
    commit(next, "finish");
    return state;
  }
  gmap.addListener("click", onClick);
  gmap.addListener("dblclick", onDblClick);
  function onMove(ev) {
    if (!state.open || !ready(ev)) return;
    hover = lit(ev.latLng);
    paintHover();
    onChange(state, hover, "hover", status());
  }
  gmap.addListener("mousemove", onMove);
  if (typeof document !== "undefined")
    document.addEventListener("keydown", (e) => {
      if (!active()) return;
      const act = shortcut(e);
      if (!act) return;
      if (act === "drop" ? !state.open : act === "clear" ? !state.shapes.length : false) return;
      e.preventDefault();
      api[act]();
    });

  const api = {
    undo: () => restore(history.undo(), "undo"),
    redo: () => restore(history.redo(), "redo"),
    clear() {
      if (!state.shapes.length) return;
      commit(EMPTY, "clear");
    },
    drop() {
      const next = dropOpen(state);
      if (next) commit(next, "drop");
    },
    // Start over with no history (the tool or the source changed).
    reset() {
      history.reset();
      state = clone(EMPTY);
      hover = null;
      render();
      onChange(state, hover, "reset", status());
    },
    finish,
    state: () => clone(state),
    status,
    // Google LatLngs, for the spherical math
    paths: (all = true) => (all ? state.shapes : finished(state)).map((pts) => pts.map((p) => new g.LatLng(p.lat, p.lng))),
    pathWithHover: () => (state.open ? openPath() : []).map((p) => new g.LatLng(p.lat, p.lng)),
    restyle() {
      objs.forEach((o) => o.setOptions(style()));
    },
  };
  return api;
}

export { sameLatLng };
