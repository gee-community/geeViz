import { test } from "node:test";
import assert from "node:assert/strict";
import { EMPTY, addPoint, finishShape, dropOpen, finished, createHistory, shortcut } from "../js/engine/sketch.js";

const P = (lat, lng) => ({ lat, lng });

test("polygons: a click after a finished polygon starts another (multi-polygon)", () => {
  let s = EMPTY;
  for (const p of [P(0, 0), P(0, 1), P(1, 1)]) s = addPoint(s, p, true);
  s = finishShape(s, 3);
  assert.equal(s.open, false);
  s = addPoint(s, P(5, 5), true);
  assert.equal(s.shapes.length, 2);
  assert.equal(s.open, true);
  assert.equal(finished(s).length, 1);
});

test("lines: a click after a finished line starts over", () => {
  let s = addPoint(addPoint(EMPTY, P(0, 0), false), P(0, 1), false);
  s = finishShape(s, 2);
  s = addPoint(s, P(3, 3), false);
  assert.deepEqual(s.shapes, [[P(3, 3)]]);
});

test("the repeated click of a double-click adds nothing; too few points do not finish", () => {
  const s = addPoint(EMPTY, P(0, 0), true);
  assert.equal(addPoint(s, P(0, 0), true), null);
  assert.equal(finishShape(addPoint(s, P(0, 1), true), 3), null);
});

test("Escape drops only the shape being drawn", () => {
  let s = EMPTY;
  for (const p of [P(0, 0), P(0, 1), P(1, 1)]) s = addPoint(s, p, true);
  s = finishShape(s, 3);
  s = addPoint(s, P(9, 9), true);
  s = dropOpen(s);
  assert.equal(s.shapes.length, 1);
  assert.equal(s.open, false);
  assert.equal(dropOpen(s), null);
});

test("history: undo and redo step through every change; a new change drops the redo branch", () => {
  const h = createHistory();
  let s = EMPTY;
  for (const p of [P(0, 0), P(0, 1), P(1, 1)]) {
    s = addPoint(s, p, true);
    h.push(s);
  }
  s = finishShape(s, 3);
  h.push(s);
  // undo the finish: the polygon is being drawn again with its three points
  let u = h.undo();
  assert.equal(u.open, true);
  assert.equal(u.shapes[0].length, 3);
  u = h.undo();
  assert.equal(u.shapes[0].length, 2);
  assert.ok(h.canRedo());
  assert.equal(h.redo().shapes[0].length, 3);
  h.push(addPoint(u, P(7, 7), true));
  assert.equal(h.canRedo(), false);
  // all the way back to empty, then no further
  while (h.canUndo()) u = h.undo();
  assert.deepEqual(u, { shapes: [], open: false });
  assert.equal(h.undo(), null);
});

test("shortcuts: ctrl+z, ctrl+shift+z, ctrl+y, Delete, Escape; never while typing", () => {
  const k = (key, o = {}) => ({ key, ctrlKey: false, metaKey: false, shiftKey: false, target: { tagName: "DIV" }, ...o });
  assert.equal(shortcut(k("z", { ctrlKey: true })), "undo");
  assert.equal(shortcut(k("Z", { ctrlKey: true, shiftKey: true })), "redo");
  assert.equal(shortcut(k("y", { ctrlKey: true })), "redo");
  assert.equal(shortcut(k("z", { metaKey: true })), "undo");
  assert.equal(shortcut(k("Delete")), "clear");
  assert.equal(shortcut(k("Backspace")), "clear");
  assert.equal(shortcut(k("Escape")), "drop");
  assert.equal(shortcut(k("z")), null);
  assert.equal(shortcut(k("z", { ctrlKey: true, target: { tagName: "INPUT" } })), null);
  assert.equal(shortcut(k("Backspace", { target: { tagName: "TEXTAREA" } })), null);
});
