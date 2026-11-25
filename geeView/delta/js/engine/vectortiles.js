// Vectors (geeVector, geoJSONVector) drawn as map tiles on canvases, so they
// stack in the layer list like any tile layer. Google's Data layer draws in a
// pane above every tile overlay, which pinned vectors on top of everything.
//
// Each tile draws the features whose bounds touch it, projected to Web
// Mercator pixels. Style keys are google.maps.Data's (engine/viz.js
// normVecStyle): strokeColor, strokeWeight, strokeOpacity, fillColor,
// fillOpacity. The layer's opacity follows the original's slider: the stroke
// takes the opacity and the fill keeps its ratio (opacityRatio).

import { drawSymbol } from "../esri/symbols.js";

const TILE = 256;

// Web Mercator world pixels at zoom z.
export function worldPx(lng, lat, z) {
  const size = TILE * Math.pow(2, z);
  const s = Math.min(Math.max(Math.sin((lat * Math.PI) / 180), -0.9999), 0.9999);
  return [((lng + 180) / 360) * size, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * size];
}

// The lng/lat bounds of a tile.
export function tileBounds(x, y, z) {
  const n = Math.pow(2, z);
  const lat = (yy) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * yy) / n))) * 180) / Math.PI;
  return { west: (x / n) * 360 - 180, east: ((x + 1) / n) * 360 - 180, north: lat(y), south: lat(y + 1) };
}

// GeoJSON to a flat list of drawable parts with their bounds and feature:
// {kind: "polygon" | "line" | "point", coords, bbox: [w, s, e, n], fid,
// props, geom}. fid is the feature's id (else its position), props its
// properties, geom its whole geometry (shared by its parts).
export function flatten(geojson) {
  const out = [];
  const bboxOf = (pts) => {
    let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
    pts.forEach(([x, y]) => {
      if (x < w) w = x;
      if (x > e) e = x;
      if (y < s) s = y;
      if (y > n) n = y;
    });
    return [w, s, e, n];
  };
  let cur = { fid: 0, props: {}, geom: null };
  let n = 0;
  const add = (kind, coords, pts) => pts.length && out.push({ kind, coords, bbox: bboxOf(pts), fid: cur.fid, props: cur.props, geom: cur.geom });
  const geom = (g) => {
    if (!g) return;
    const c = g.coordinates;
    switch (g.type) {
      case "Point":
        return add("point", [c], [c]);
      case "MultiPoint":
        return add("point", c, c);
      case "LineString":
        return add("line", [c], c);
      case "MultiLineString":
        return add("line", c, c.flat());
      case "Polygon":
        return add("polygon", c, c.flat());
      case "MultiPolygon":
        return c.forEach((p) => add("polygon", p, p.flat()));
      case "GeometryCollection":
        return (g.geometries || []).forEach(geom);
    }
  };
  const walk = (o) => {
    if (!o) return;
    if (o.type === "FeatureCollection") (o.features || []).forEach(walk);
    else if (o.type === "Feature") {
      cur = { fid: o.id === undefined || o.id === null ? n : o.id, props: o.properties || {}, geom: o.geometry };
      n++;
      geom(o.geometry);
    } else {
      cur = { fid: n++, props: {}, geom: o };
      geom(o);
    }
  };
  walk(geojson);
  return out;
}

// The colors a layer draws with, after its opacity slider.
export function effectiveStyle(style, opacity, touched, opacityRatio) {
  const st = { ...style };
  if (opacity !== 1 || touched) {
    st.strokeOpacity = opacity;
    st.fillOpacity = opacity / (opacityRatio || 1);
  }
  return st;
}

// opts: google, geojson | source, style, opacity, opacityRatio, dpr,
// onProgress(stats) (once a frame as tiles come and go, so the layer row
// shows them in). A source fetches each tile's parts as it is shown
// ({partsFor(coord, zoom, signal) -> Promise<parts>}: an ArcGIS feature
// layer, engine/../esri/features.js); GeoJSON given whole is drawn at once.
// styleFor(part, zoom, style) -> style, when parts draw differently.
export function createVectorTileOverlay(opts) {
  const g = opts.google || globalThis.google.maps;
  const all = opts.source ? null : flatten(opts.geojson);
  let style = effectiveStyle(opts.style || {}, opts.opacity === undefined ? 1 : opts.opacity, false, opts.opacityRatio);
  let opacity = opts.opacity === undefined ? 1 : opts.opacity;
  const tiles = new Map(); // canvas -> {coord, zoom, parts (null while fetching), failed, ctrl}
  let queued = false;
  const stats = () => {
    let loaded = 0;
    let failed = 0;
    tiles.forEach((t) => {
      if (t.failed) failed++;
      else if (t.parts) loaded++;
    });
    return { total: tiles.size, loaded, failed };
  };
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
  const dpr = () => opts.dpr || (typeof devicePixelRatio === "number" ? Math.min(devicePixelRatio, 2) : 1);

  function draw(canvas, coord, zoom, parts) {
    const ratio = dpr();
    canvas.width = TILE * ratio;
    canvas.height = TILE * ratio;
    const ctx = canvas.getContext && canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, TILE, TILE);
    const b = tileBounds(coord.x, coord.y, zoom);
    // room for strokes and point markers that reach in from a neighbor
    const pad = (((style.strokeWeight || 3) + 10) / TILE) * (b.east - b.west);
    const ox = coord.x * TILE;
    const oy = coord.y * TILE;
    const px = ([lng, lat]) => {
      const [x, y] = worldPx(lng, lat, zoom);
      return [x - ox, y - oy];
    };
    const rgba = (c, a) => {
      ctx.globalAlpha = Math.max(0, Math.min(1, a));
      return c;
    };
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    for (const p of parts) {
      const [w, s, e, n] = p.bbox;
      if (e < b.west - pad || w > b.east + pad || n < b.south - pad || s > b.north + pad) continue;
      const st = opts.styleFor ? opts.styleFor(p, zoom, style) : style;
      if (!st) continue;
      if (st.symbol) {
        // an ArcGIS symbol (esri/symbols.js), at the layer's opacity
        drawSymbol(ctx, st.symbol, p, px, st, opacity);
        continue;
      }
      const weight = st.strokeWeight === undefined ? 3 : st.strokeWeight;
      const strokeOpacity = st.strokeOpacity === undefined ? 1 : st.strokeOpacity;
      if (p.kind === "point") {
        p.coords.forEach((c) => {
          const [x, y] = px(c);
          ctx.beginPath();
          ctx.arc(x, y, 4 + (st.strokeWeight || 0) / 2, 0, 2 * Math.PI);
          ctx.fillStyle = rgba(st.strokeColor || "#000", strokeOpacity);
          ctx.fill();
          ctx.lineWidth = 1.5;
          ctx.strokeStyle = rgba("#ffffff", strokeOpacity);
          ctx.stroke();
        });
        continue;
      }
      ctx.lineWidth = weight;
      ctx.beginPath();
      p.coords.forEach((ring) => {
        ring.forEach((c, i) => {
          const [x, y] = px(c);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        if (p.kind === "polygon") ctx.closePath();
      });
      if (p.kind === "polygon" && st.fillOpacity > 0) {
        ctx.fillStyle = rgba(st.fillColor || st.strokeColor || "#000", st.fillOpacity);
        ctx.fill("evenodd");
      }
      if (weight > 0) {
        ctx.strokeStyle = rgba(st.strokeColor || "#000", strokeOpacity);
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }

  // A source tile is drawn when its parts arrive, unless the canvas was
  // released (or reused) by then.
  function fetchTile(canvas, t) {
    const ctrl = typeof AbortController === "function" ? new AbortController() : null;
    t.ctrl = ctrl;
    Promise.resolve()
      .then(() => opts.source.partsFor(t.coord, t.zoom, ctrl && ctrl.signal))
      .then(
        (parts) => {
          if (tiles.get(canvas) !== t) return;
          t.parts = parts || [];
          draw(canvas, t.coord, t.zoom, t.parts);
          report();
        },
        () => {
          if (tiles.get(canvas) !== t) return;
          t.failed = true;
          report();
        }
      );
  }

  const redraw = () => tiles.forEach((t, canvas) => t.parts && draw(canvas, t.coord, t.zoom, t.parts));

  return {
    tileSize: new g.Size(TILE, TILE),
    maxZoom: 24,
    minZoom: 0,
    name: opts.name || null,
    getTile(coord, zoom, doc) {
      const canvas = doc.createElement("canvas");
      canvas.style.cssText = `width:${TILE}px;height:${TILE}px;display:block`;
      const n = 1 << zoom;
      if (coord.y < 0 || coord.y >= n) return canvas;
      const c = { x: ((coord.x % n) + n) % n, y: coord.y };
      const t = { coord: c, zoom, parts: all, failed: false, ctrl: null };
      tiles.set(canvas, t);
      if (all) draw(canvas, c, zoom, all);
      else fetchTile(canvas, t);
      report();
      return canvas;
    },
    releaseTile(canvas) {
      const t = tiles.get(canvas);
      if (t && t.ctrl && !t.parts) t.ctrl.abort();
      tiles.delete(canvas);
      report();
    },
    // the opacity slider: redraw with the stroke at the opacity, the fill at its ratio
    setOpacity(a, touched = true) {
      opacity = a;
      style = effectiveStyle(opts.style || {}, a, touched, opts.opacityRatio);
      redraw();
    },
    getOpacity: () => opacity,
    style: () => ({ ...style }),
    redraw,
    stats,
    // ask again for the tiles whose features failed to load
    retryFailed() {
      let n = 0;
      tiles.forEach((t, canvas) => {
        if (!t.failed) return;
        t.failed = false;
        n++;
        fetchTile(canvas, t);
      });
      if (n) report();
      return n;
    },
    features: () => (all ? all.length : new Set(loadedParts().map((p) => p.fid)).size),
    // the parts drawn on the tiles shown (at the zoom given, if one is)
    loadedParts,
  };

  function loadedParts(zoom) {
    if (all) return all;
    const out = [];
    tiles.forEach((t) => {
      if (t.parts && (zoom === undefined || t.zoom === zoom)) out.push(...t.parts);
    });
    return out;
  }
}
