// ArcGIS services, drawn, queried, legended and charted in the browser the
// way the ArcGIS JS API does it, with no ArcGIS JS API and no Earth Engine.
// A layer's item is the service URL; its viz.esri holds the service options
// (layers, renderingRule, mosaicRule, bandIds, time, where, outFields, bbox,
// maxFeatures, simplify, maxLayerMB). The kind given is a first guess: the
// service's metadata decides (a cached map service draws as tiles).
import { serviceInfo, serviceKind, normalizeUrl } from "../esri/rest.js";
import { exportUrl, tileUrl, tile3857, maxTileZoom } from "../esri/draw.js";
import { serviceLegend } from "../esri/legend.js";

export const esriOptsOf = (r) => (r && r.viz && r.viz.esri) || {};

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
  // The service's legend (/legend), once it is drawn.
  async legend(r, ctx) {
    if (!r.info || r.kind === "esri.feature") return null;
    return serviceLegend(r.url, r.info, esriOptsOf(r), { fetch: ctx.fetch, title: r.name });
  },
};
