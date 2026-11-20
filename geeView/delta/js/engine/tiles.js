// A tile overlay that loads its own tiles, so a layer knows how many of the
// tiles on screen have loaded (a true progress bar) and can retry the ones
// that fail. Google's ImageMapType hides both: it only says "tilesloaded".
//
// The progress counts the tiles Google is showing right now: every getTile
// that has not been released. Panning or zooming releases the old tiles and
// asks for new ones, so the count follows the view. Retries are the only
// requests added: a failed tile is asked for again after 0.5, 1, 2 and 4 s
// (with jitter), then once more after a pause of 8 s (a service that was
// briefly overloaded has usually recovered), then counted as failed;
// retryFailed() asks again for those.

export const RETRY_DELAYS = [500, 1000, 2000, 4000];
export const AUTO_RETRY_MS = 8000;

// Earth Engine and tile services number x around the world; Google asks for
// tiles past the antimeridian and above or below the poles.
export function wrapTile(coord, zoom) {
  const n = 1 << zoom;
  if (coord.y < 0 || coord.y >= n) return null;
  return { x: ((coord.x % n) + n) % n, y: coord.y };
}

// Progress of a set of tiles: {total, loaded, failed, done} with done in 0..1
// (1 when there is nothing to load).
export function progressOf(stats) {
  const total = stats.reduce((a, s) => a + s.total, 0);
  const loaded = stats.reduce((a, s) => a + s.loaded, 0);
  const failed = stats.reduce((a, s) => a + s.failed, 0);
  return { total, loaded, failed, done: total ? (loaded + failed) / total : 1 };
}

// opts: google, urlFor(coord, zoom) -> url or null, maxZoom, minZoom,
// opacity, onRequest(), onProgress({total, loaded, failed}), delays, autoRetry
// (ms before the one late retry), random()
export function createTileOverlay(opts) {
  const g = opts.google || globalThis.google.maps;
  const delays = opts.delays || RETRY_DELAYS;
  const random = opts.random || Math.random;
  const autoRetry = opts.autoRetry === undefined ? AUTO_RETRY_MS : opts.autoRetry;
  const size = 256;
  let opacity = opts.opacity === undefined ? 1 : opts.opacity;
  const tiles = new Map(); // div -> {div, url, state, tries, timer, released}
  let queued = false;

  function stats() {
    let loaded = 0;
    let failed = 0;
    tiles.forEach((t) => {
      if (t.state === "loaded") loaded++;
      else if (t.state === "failed") failed++;
    });
    return { total: tiles.size, loaded, failed };
  }
  // one report per frame, however many tiles settle in it
  function report() {
    if (queued || !opts.onProgress) return;
    queued = true;
    const run = () => {
      queued = false;
      opts.onProgress(stats());
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
    else setTimeout(run, 0);
  }

  function load(t) {
    const img = t.div.ownerDocument.createElement("img");
    img.alt = "";
    img.draggable = false;
    img.width = size;
    img.height = size;
    img.style.cssText = "display:block;width:256px;height:256px;border:0;user-select:none;pointer-events:none";
    img.onload = () => {
      if (t.released) return;
      t.state = "loaded";
      t.div.replaceChildren(img);
      report();
    };
    img.onerror = () => {
      if (t.released) return;
      if (t.tries < delays.length) {
        const wait = delays[t.tries] * (0.75 + random() * 0.5);
        t.tries++;
        t.timer = setTimeout(() => !t.released && load(t), wait);
      } else if (!t.late) {
        // the backoff ran out: one more try after a pause, once per tile
        t.late = true;
        t.timer = setTimeout(() => !t.released && load(t), autoRetry);
      } else {
        t.state = "failed";
        report();
      }
    };
    if (opts.onRequest) opts.onRequest();
    img.src = t.url;
  }

  const overlay = {
    tileSize: new g.Size(size, size),
    maxZoom: opts.maxZoom === undefined ? 24 : opts.maxZoom,
    minZoom: opts.minZoom === undefined ? 0 : opts.minZoom,
    name: opts.name || null,
    getTile(coord, zoom, doc) {
      const div = doc.createElement("div");
      div.style.cssText = `width:${size}px;height:${size}px;opacity:${opacity}`;
      const c = wrapTile(coord, zoom);
      const url = c ? opts.urlFor(c, zoom) : null;
      if (!url) return div; // nothing to load: not counted
      const t = { div, url, state: "loading", tries: 0, late: false, timer: 0, released: false };
      tiles.set(div, t);
      load(t);
      report();
      return div;
    },
    releaseTile(div) {
      const t = tiles.get(div);
      if (!t) return;
      t.released = true;
      clearTimeout(t.timer);
      tiles.delete(div);
      report();
    },
    setOpacity(v) {
      opacity = v;
      tiles.forEach((t) => (t.div.style.opacity = String(v)));
    },
    getOpacity: () => opacity,
    stats,
    // Ask again for the tiles that ran out of retries.
    retryFailed() {
      let n = 0;
      tiles.forEach((t) => {
        if (t.state !== "failed") return;
        t.state = "loading";
        t.tries = 0;
        n++;
        load(t);
      });
      if (n) report();
      return n;
    },
  };
  return overlay;
}
