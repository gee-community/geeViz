import { test } from "node:test";
import assert from "node:assert/strict";
import { createTileOverlay, wrapTile, progressOf } from "../js/engine/tiles.js";
import { progressView } from "../js/ui/layers.js";

// A minimal document: images "load" or "fail" when the test says so.
function fakeDoc() {
  const imgs = [];
  const mk = (tag) => {
    const e = { tag, style: {}, children: [], ownerDocument: null, replaceChildren(...c) { this.children = c; } };
    if (tag === "img") imgs.push(e);
    return e;
  };
  const doc = { createElement: (t) => { const e = mk(t); e.ownerDocument = doc; return e; }, imgs };
  return doc;
}
const google = { Size: function (w, h) { this.width = w; this.height = h; } };

function setup(delays = [10, 20]) {
  const reports = [];
  let requests = 0;
  const o = createTileOverlay({
    google,
    urlFor: (c, z) => `t/${z}/${c.x}/${c.y}`,
    delays,
    random: () => 0.5, // no jitter
    onRequest: () => requests++,
    onProgress: (s) => reports.push(s),
  });
  return { o, reports, requests: () => requests };
}
const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));

test("x wraps around the world; rows past the poles have no tile", () => {
  assert.deepEqual(wrapTile({ x: -1, y: 0 }, 2), { x: 3, y: 0 });
  assert.deepEqual(wrapTile({ x: 5, y: 1 }, 2), { x: 1, y: 1 });
  assert.equal(wrapTile({ x: 0, y: 4 }, 2), null);
  assert.equal(wrapTile({ x: 0, y: -1 }, 2), null);
});

test("progress counts the tiles on screen: loaded over total", async () => {
  const { o } = setup();
  const doc = fakeDoc();
  const tiles = [0, 1, 2, 3].map((x) => o.getTile({ x, y: 0 }, 2, doc));
  assert.deepEqual(o.stats(), { total: 4, loaded: 0, failed: 0 });
  doc.imgs[0].onload();
  doc.imgs[1].onload();
  assert.deepEqual(o.stats(), { total: 4, loaded: 2, failed: 0 });
  // a released tile leaves the count (the view moved)
  o.releaseTile(tiles[3]);
  assert.deepEqual(o.stats(), { total: 3, loaded: 2, failed: 0 });
  assert.equal(progressOf([o.stats()]).done, 2 / 3);
});

test("a failed tile is asked for again with backoff, then counted as failed", async () => {
  const { o, requests } = setup([10, 20]);
  const doc = fakeDoc();
  o.getTile({ x: 0, y: 0 }, 1, doc);
  assert.equal(requests(), 1);
  doc.imgs[0].onerror();
  await tick(15);
  assert.equal(requests(), 2, "first retry after the first delay");
  doc.imgs[1].onerror();
  await tick(5);
  assert.equal(requests(), 2, "second retry waits for the longer delay");
  await tick(25);
  assert.equal(requests(), 3);
  doc.imgs[2].onerror(); // out of retries
  await tick(40);
  assert.equal(requests(), 3);
  assert.deepEqual(o.stats(), { total: 1, loaded: 0, failed: 1 });
  // retryFailed asks again; a load then counts
  assert.equal(o.retryFailed(), 1);
  assert.equal(requests(), 4);
  doc.imgs[3].onload();
  assert.deepEqual(o.stats(), { total: 1, loaded: 1, failed: 0 });
});

test("a retry succeeding loads the tile", async () => {
  const { o } = setup([5]);
  const doc = fakeDoc();
  o.getTile({ x: 0, y: 0 }, 1, doc);
  doc.imgs[0].onerror();
  await tick(15);
  doc.imgs[1].onload();
  assert.deepEqual(o.stats(), { total: 1, loaded: 1, failed: 0 });
});

test("a released tile is never retried", async () => {
  const { o, requests } = setup([5]);
  const doc = fakeDoc();
  const t = o.getTile({ x: 0, y: 0 }, 1, doc);
  doc.imgs[0].onerror();
  o.releaseTile(t);
  await tick(20);
  assert.equal(requests(), 1);
  assert.deepEqual(o.stats(), { total: 0, loaded: 0, failed: 0 });
});

test("opacity applies to every tile, now and later", () => {
  const { o } = setup();
  const doc = fakeDoc();
  const a = o.getTile({ x: 0, y: 0 }, 1, doc);
  o.setOpacity(0.4);
  assert.equal(a.style.opacity, "0.4");
  assert.equal(o.getOpacity(), 0.4);
  const b = o.getTile({ x: 1, y: 0 }, 1, doc);
  assert.match(b.style.cssText, /opacity:0\.4/);
});

test("the row: fills while tiles load, shows failures, nothing for hidden layers", () => {
  assert.deepEqual(progressView({ visible: true, progress: { total: 8, loaded: 2, failed: 0 } }), { show: true, pct: 25, failed: 0 });
  assert.deepEqual(progressView({ visible: true, progress: { total: 8, loaded: 6, failed: 2 } }), { show: false, pct: 100, failed: 2 });
  assert.deepEqual(progressView({ visible: false, progress: { total: 8, loaded: 2, failed: 0 } }), { show: false, pct: 0, failed: 0 });
  assert.deepEqual(progressView({ visible: true, progress: null }), { show: false, pct: 0, failed: 0 });
});
