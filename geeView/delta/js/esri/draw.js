// How ArcGIS map and image services are drawn as map tiles: a cached
// service's own tiles, or one export image per map tile (as the ArcGIS JS
// API's MapImageLayer and ImageryLayer ask the server for the view).

const HALF = 20037508.342789244;

// A Google map tile's Web Mercator bounds.
export function tile3857(x, y, z) {
  const size = (2 * HALF) / Math.pow(2, z);
  return { xmin: -HALF + x * size, xmax: -HALF + (x + 1) * size, ymax: HALF - y * size, ymin: HALF - (y + 1) * size };
}

export const tileUrl = (url) => (coord, zoom) => `${url}/tile/${zoom}/${coord.y}/${coord.x}`;

const INTEGER_PIXELS = ["U1", "U2", "U4", "U8", "S8", "U16", "S16", "U32", "S32"];
// A single integer band is most likely classes: smoothing would invent values between them.
export const isClassLike = (info) => !!info && INTEGER_PIXELS.indexOf(info.pixelType) > -1 && (info.bandCount || 1) === 1;

const json = (v) => (typeof v === "string" ? v : JSON.stringify(v));

// The export (MapServer) or exportImage (ImageServer) URL for bounds in Web
// Mercator. esriOpts: layers, time [start, end], renderingRule, mosaicRule,
// bandIds. info: the image service's metadata (pixel type), when known.
export function exportUrl(url, kind, esriOpts = {}, b, size = 256, info = null) {
  const o = esriOpts || {};
  const p = new URLSearchParams();
  p.set("bbox", [b.xmin, b.ymin, b.xmax, b.ymax].join(","));
  p.set("bboxSR", "3857");
  p.set("imageSR", "3857");
  p.set("size", `${size},${size}`);
  p.set("dpi", "96");
  if (kind === "esri.image") {
    p.set("format", "jpgpng");
    if (o.renderingRule) p.set("renderingRule", json(o.renderingRule));
    if (o.mosaicRule) p.set("mosaicRule", json(o.mosaicRule));
    if (o.bandIds !== undefined && o.bandIds !== null) p.set("bandIds", [].concat(o.bandIds).join(","));
    if (isClassLike(info)) p.set("interpolation", "RSP_NearestNeighbor");
  } else {
    p.set("format", "png32");
    p.set("transparent", "true");
    if (o.layers) p.set("layers", o.layers);
  }
  if (Array.isArray(o.time) && o.time.length === 2) p.set("time", o.time.join(","));
  p.set("f", "image");
  return `${url}/${kind === "esri.image" ? "exportImage" : "export"}?${p.toString()}`;
}

// The URL for each map tile of an export: from zoom 2, one 1024 px image per
// block of 4 by 4 map tiles, each tile showing its piece (engine/tiles.js
// block tiles). An ArcGIS export takes as long for 1024 px as for 256, so
// this is 16 times fewer slow requests. Below zoom 2, or for a service that
// limits images to under 1024 px, one image per tile.
export const BLOCK = 4;
export function exportTileUrl(url, kind, esriOpts, info) {
  const maxW = Number(info && info.maxImageWidth) || 4096;
  const maxH = Number(info && info.maxImageHeight) || 4096;
  const blocks = maxW >= 256 * BLOCK && maxH >= 256 * BLOCK;
  return (coord, zoom) => {
    if (!blocks || zoom < 2) return exportUrl(url, kind, esriOpts, tile3857(coord.x, coord.y, zoom), 256, info);
    const bx = Math.floor(coord.x / BLOCK);
    const by = Math.floor(coord.y / BLOCK);
    return {
      url: exportUrl(url, kind, esriOpts, tile3857(bx, by, zoom - 2), 256 * BLOCK, info),
      block: { size: 256 * BLOCK, x: (coord.x - bx * BLOCK) * 256, y: (coord.y - by * BLOCK) * 256 },
    };
  };
}

// The deepest zoom a cached service has tiles for.
export function maxTileZoom(info) {
  const lods = (info && info.tileInfo && info.tileInfo.lods) || [];
  return lods.length ? Math.max(...lods.map((l) => l.level)) : 20;
}
