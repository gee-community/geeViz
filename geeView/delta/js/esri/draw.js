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

// The deepest zoom a cached service has tiles for.
export function maxTileZoom(info) {
  const lods = (info && info.tileInfo && info.tileInfo.lods) || [];
  return lods.length ? Math.max(...lods.map((l) => l.level)) : 20;
}
