// ArcGIS services, drawn, queried, legended and charted in the browser the
// way the ArcGIS JS API does it, with no ArcGIS JS API and no Earth Engine.
// A layer's item is the service URL; its viz.esri holds the service options
// (layers, renderingRule, mosaicRule, bandIds, time, where, outFields, bbox,
// maxFeatures, simplify, maxLayerMB). The kind given is a first guess: the
// service's metadata decides (a cached map service draws as tiles).
import { serviceInfo, serviceKind, normalizeUrl } from "../esri/rest.js";
import { exportUrl, tileUrl, tile3857, maxTileZoom } from "../esri/draw.js";
import { serviceLegend } from "../esri/legend.js";
import { identifyMap, identifyImage } from "../esri/identify.js";

export const esriOptsOf = (r) => (r && r.viz && r.viz.esri) || {};

// A view to identify in when the map gives none: a small box around the point.
const viewAround = (p) => ({ bounds: { west: p.lng - 0.01, south: p.lat - 0.01, east: p.lng + 0.01, north: p.lat + 0.01 }, width: 256, height: 256 });

export const esriPlugin = {
  kinds: ["esri.feature", "esri.map", "esri.tile", "esri.image", "esri.timelapse"],
  needsEE: false,
  // the viz is the plug-in's own: no Earth Engine viz preparation
  ownsViz: true,
  async draw(r, item, ctx) {
    const url = normalizeUrl(item);
    r.url = url;
    let info;
    try {
      info = await serviceInfo(url, { fetch: ctx.fetch });
    } catch (e) {
      return ctx.fail(r, e);
    }
    r.info = info;
    const opts = esriOptsOf(r);
    const kind = serviceKind(url, info, opts);
    if (kind !== r.kind) ctx.setKind(r, kind);
    if (kind === "esri.tile") {
      r.overlay = ctx.tileOverlay(r, tileUrl(url), { maxZoom: maxTileZoom(info) });
    } else if (kind === "esri.map" || kind === "esri.image") {
      r.overlay = ctx.tileOverlay(r, (coord, zoom) => exportUrl(url, kind, opts, tile3857(coord.x, coord.y, zoom), 256, info));
    } else {
      return ctx.fail(r, "Feature layers cannot be drawn yet.");
    }
    r.tileType = true;
    ctx.setLoading(r, false);
    ctx.sync();
  },
  // The Query tool: identify on the service (a tile service asks the
  // service behind its tiles).
  async query(target, layer, point, qctx) {
    const url = normalizeUrl(layer.item);
    const info = await serviceInfo(url, { fetch: qctx.fetch });
    const opts = esriOptsOf(layer);
    const common = { fetch: qctx.fetch, info, layer, precision: qctx.query && qctx.query.precision };
    if (serviceKind(url, info, opts) === "esri.feature") return [];
    if (/\/ImageServer$/i.test(url)) return identifyImage(url, point, opts, layer.legend, common);
    return identifyMap(url, point, qctx.view || viewAround(point), opts, common);
  },
  // The service's legend (/legend), once it is drawn.
  async legend(r, ctx) {
    if (!r.info || r.kind === "esri.feature") return null;
    return serviceLegend(r.url, r.info, esriOptsOf(r), { fetch: ctx.fetch, title: r.name });
  },
};
