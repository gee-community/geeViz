// Vectors (geeVector, geoJSONVector) drawn as map tiles on canvases, so they
// stack in the layer list like any tile layer. Google's Data layer draws in a
// pane above every tile overlay, which pinned vectors on top of everything.
//
// Each tile draws the features whose bounds touch it, projected to Web
// Mercator pixels. Style keys are google.maps.Data's (engine/viz.js
// normVecStyle): strokeColor, strokeWeight, strokeOpacity, fillColor,
// fillOpacity. The layer's opacity follows the original's slider: the stroke
// takes the opacity and the fill keeps its ratio (opacityRatio).

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

// GeoJSON to a flat list of drawable parts with their bounds:
// {kind: "polygon" | "line" | "point", coords, bbox: [w, s, e, n]}.
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
  const add = (kind, coords, pts) => pts.length && out.push({ kind, coords, bbox: bboxOf(pts) });
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
    else if (o.type === "Feature") geom(o.geometry);
    else geom(o);
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

// opts: google, geojson, style, opacity, opacityRatio, dpr
export function createVectorTileOverlay(opts) {
  const g = opts.google || globalThis.google.maps;
  const parts = flatten(opts.geojson);
  let style = effectiveStyle(opts.style || {}, opts.opacity === undefined ? 1 : opts.opacity, false, opts.opacityRatio);
  let opacity = opts.opacity === undefined ? 1 : opts.opacity;
  const tiles = new Map(); // canvas -> {coord, zoom}
  const dpr = () => opts.dpr || (typeof devicePixelRatio === "number" ? Math.min(devicePixelRatio, 2) : 1);

  function draw(canvas, coord, zoom) {
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
    ctx.lineWidth = style.strokeWeight === undefined ? 3 : style.strokeWeight;
    for (const p of parts) {
      const [w, s, e, n] = p.bbox;
      if (e < b.west - pad || w > b.east + pad || n < b.south - pad || s > b.north + pad) continue;
      if (p.kind === "point") {
        p.coords.forEach((c) => {
          const [x, y] = px(c);
          ctx.beginPath();
          ctx.arc(x, y, 4 + (style.strokeWeight || 0) / 2, 0, 2 * Math.PI);
          ctx.fillStyle = rgba(style.strokeColor || "#000", style.strokeOpacity === undefined ? 1 : style.strokeOpacity);
          ctx.fill();
          ctx.lineWidth = 1.5;
          ctx.strokeStyle = rgba("#ffffff", style.strokeOpacity === undefined ? 1 : style.strokeOpacity);
          ctx.stroke();
          ctx.lineWidth = style.strokeWeight === undefined ? 3 : style.strokeWeight;
        });
        continue;
      }
      ctx.beginPath();
      p.coords.forEach((ring) => {
        ring.forEach((c, i) => {
          const [x, y] = px(c);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        if (p.kind === "polygon") ctx.closePath();
      });
      if (p.kind === "polygon" && style.fillOpacity > 0) {
        ctx.fillStyle = rgba(style.fillColor || style.strokeColor || "#000", style.fillOpacity);
        ctx.fill("evenodd");
      }
      if (ctx.lineWidth > 0) {
        ctx.strokeStyle = rgba(style.strokeColor || "#000", style.strokeOpacity === undefined ? 1 : style.strokeOpacity);
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }

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
      tiles.set(canvas, { coord: c, zoom });
      draw(canvas, c, zoom);
      return canvas;
    },
    releaseTile(canvas) {
      tiles.delete(canvas);
    },
    // the opacity slider: redraw with the stroke at the opacity, the fill at its ratio
    setOpacity(a, touched = true) {
      opacity = a;
      style = effectiveStyle(opts.style || {}, a, touched, opts.opacityRatio);
      tiles.forEach((t, canvas) => draw(canvas, t.coord, t.zoom));
    },
    getOpacity: () => opacity,
    style: () => ({ ...style }),
    // drawn at once: every tile on screen is in
    stats: () => ({ total: tiles.size, loaded: tiles.size, failed: 0 }),
    retryFailed: () => 0,
    features: () => parts.length,
  };
}
