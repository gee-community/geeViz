// ArcGIS services, drawn, queried, legended and charted in the browser the
// way the ArcGIS JS API does it, with no ArcGIS JS API and no Earth Engine.
// A layer's item is the service URL; its viz.esri holds the service options
// (layers, renderingRule, mosaicRule, bandIds, time, where, outFields, bbox,
// maxFeatures, simplify, maxLayerMB). The kind given is a first guess: the
// service's metadata decides (a cached map service draws as tiles).
import { serviceInfo, serviceKind, normalizeUrl, sublayerOf } from "../esri/rest.js";
import { exportTileUrl, tileUrl, maxTileZoom } from "../esri/draw.js";
import { serviceLegend } from "../esri/legend.js";
import { identifyMap, identifyImage } from "../esri/identify.js";
import { createFeatureSource } from "../esri/features.js";
import { rendererFor } from "../esri/renderers.js";
import { onSymbolImage } from "../esri/symbols.js";
import { esriFrameLoader } from "../esri/timelapse.js";
import { imageChart, featureChart, serviceYears } from "../esri/charts.js";
import { withSwatchColors } from "../esri/legend.js";
import { hitTest } from "../engine/hittest.js";
import { tableResults } from "../engine/query.js";

export const esriOptsOf = (r) => (r && r.viz && r.viz.esri) || {};

// A view to identify in when the map gives none: a small box around the point.
const viewAround = (p) => ({ bounds: { west: p.lng - 0.01, south: p.lat - 0.01, east: p.lng + 0.01, north: p.lat + 0.01 }, width: 256, height: 256 });

// The row's note for a feature layer, from the tiles at the zoom shown.
export function noteFor(statuses) {
  if (statuses.some((s) => s.outOfScale)) return "Zoom in to see this layer.";
  const capped = statuses.filter((s) => s.capped);
  if (!capped.length) return null;
  const shown = statuses.reduce((n, s) => n + s.shown, 0);
  return `Showing the first ${shown.toLocaleString("en-US")} features in view; zoom in for the rest.`;
}

// A feature layer answers by hit test on what it drew, then every field of
// the features hit (as a popup asks for them).
async function queryFeatures(target, layer, point, qctx, common) {
  const ov = target.overlay && target.overlay();
  const src = ov && ov.loadedParts ? ov : null;
  const hits = src ? hitTest(src.loadedParts(qctx.zoom), point, qctx.zoom) : [];
  let attrs = {};
  const rec = target.source && target.source();
  if (hits.length && rec) attrs = await rec.attributes(hits.map((p) => p.fid));
  const features = hits.map((p) => ({ type: "Feature", properties: attrs[p.fid] || p.props, geometry: p.geom }));
  if (features.length && qctx.onVectors) qctx.onVectors({ type: "FeatureCollection", features });
  return tableResults(layer, { features }, point, common.precision);
}

export const esriPlugin = {
  kinds: ["esri.feature", "esri.map", "esri.tile", "esri.image", "esri.timelapse"],
  needsEE: false,
  // the viz is the plug-in's own: no Earth Engine viz preparation
  ownsViz: true,
  // a time-enabled service played frame by frame (engine/timelapse.js)
  start(layer, ctx) {
    if (layer.kind !== "esri.timelapse") return false;
    ctx.addTimelapse(layer, esriFrameLoader);
    return true;
  },
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
      r.overlay = ctx.tileOverlay(r, exportTileUrl(url, kind, opts, info));
    } else {
      // drawn with the service's renderer (geeViz style keys replace it)
      r.renderer = rendererFor(info.drawingInfo, r.viz, info.geometryType);
      // features fetched for the view, tile by tile
      const statuses = new Map(); // "z/x/y" -> status, for the tiles shown
      // the note from the tiles on the map now (none until the overlay exists)
      const renote = () => {
        const live = r.overlay && r.overlay.liveKeys ? r.overlay.liveKeys() : null;
        ctx.setNote(r, noteFor([...statuses.values()].filter((s) => !live || live.has(s.key))));
      };
      let legendZoom = null;
      r.source = createFeatureSource(url, info, opts, {
        fetch: ctx.fetch,
        padPx: r.renderer.padPx,
        defaultMaxFeatures: r.renderer.maxFeatures,
        onStatus: (s) => {
          for (const k of statuses.keys()) if (statuses.get(k).zoom !== s.zoom) statuses.delete(k);
          statuses.set(s.key, s);
          renote();
          // a tile that loads clears a failure the row was showing
          if (r.failed) {
            r.failed = false;
            ctx.patch(r.id, { error: null }, "layer-error");
          }
          // "1 dot = N" follows the zoom
          if (r.renderer.type === "dotDensity" && s.zoom !== legendZoom) {
            legendZoom = s.zoom;
            ctx.setLegend(r, r.renderer.legend(r.name, s.zoom));
          }
        },
      });
      // drawingInfo.transparency: the service's own layer opacity, under the slider's
      const alpha = r.renderer.alpha === undefined ? 1 : r.renderer.alpha;
      const drawTile = r.renderer.drawTile ? (c2d, parts, t) => r.renderer.drawTile(c2d, parts, { ...t, opacity: t.opacity * alpha }) : null;
      const styleFor = (p, zoom) => {
        const st = r.renderer.styleFor(p.props, zoom);
        return st && alpha !== 1 ? { ...st, opacity: (st.opacity === undefined ? 1 : st.opacity) * alpha } : st;
      };
      // a tile that leaves the map leaves the note; when every tile shown
      // fails, the row says the service's own message
      const onRelease = (c, z) => {
        statuses.delete(`${z}/${c.x}/${c.y}`);
        renote();
      };
      const onError = (e) =>
        setTimeout(() => {
          const st = r.overlay && r.overlay.stats ? r.overlay.stats() : null;
          if (st && st.total > 0 && st.failed === st.total) ctx.fail(r, e);
        }, 0);
      ctx.addFeatureSource(r, r.source, { styleFor, drawTile, onRelease, onError });
      // a picture symbol draws once its image has loaded
      onSymbolImage(() => r.overlay && r.overlay.redraw && r.overlay.redraw());
      return;
    }
    r.tileType = true;
    ctx.setLoading(r, false);
    ctx.sync();
  },
  // The Query tool: identify on the service (a tile service asks the
  // service behind its tiles).
  async query(target, layer, point, qctx) {
    let url = normalizeUrl(layer.item);
    let opts = esriOptsOf(layer);
    // a sublayer timelapse is drawn, and so asked, by its map service
    const sub = layer.kind === "esri.timelapse" ? sublayerOf(url) : null;
    if (sub) {
      url = sub.parent;
      opts = { ...opts, layers: `show:${sub.id}` };
    }
    const info = await serviceInfo(url, { fetch: qctx.fetch });
    const common = { fetch: qctx.fetch, info, layer, precision: qctx.query && qctx.query.precision };
    if (serviceKind(url, info, opts) === "esri.feature") return queryFeatures(target, layer, point, qctx, common);
    if (/\/ImageServer$/i.test(url)) return identifyImage(url, point, opts, layer.legend, common);
    return identifyMap(url, point, qctx.view || viewAround(point), opts, common);
  },
  // The service's legend (/legend), once it is drawn; its swatches' colors
  // are read for charts and query cards.
  async legend(r, ctx) {
    if (!r.info) return null;
    if (r.kind === "esri.feature") return r.renderer ? r.renderer.legend(r.name) : null;
    return withSwatchColors(await serviceLegend(r.url, r.info, esriOptsOf(r), { fetch: ctx.fetch, title: r.name }));
  },
  // Chart area: an image service's class areas (computeHistograms), a
  // feature layer's or map service's features by class (outStatistics).
  async chart(layer, area, cctx) {
    const url = normalizeUrl(layer.item);
    const info = await serviceInfo(url, { fetch: cctx.fetch });
    const kind = serviceKind(url, info, esriOptsOf(layer));
    if (/\/ImageServer$/i.test(url)) {
      // the classes come from the legend: ask for it if the layer has none yet
      let legend = layer.legend && layer.legend.type ? layer.legend : null;
      if (!legend) legend = await withSwatchColors(await serviceLegend(url, info, esriOptsOf(layer), { fetch: cctx.fetch, title: layer.name }).catch(() => null));
      return imageChart({ ...layer, legend }, area, cctx);
    }
    if (kind === "esri.feature" || kind === "esri.map" || kind === "esri.tile") return featureChart(layer, area, cctx);
    throw new Error(`${layer.name} cannot be charted.`);
  },
  // the first and last years, for the Sankey periods
  years: (layer, cctx) => serviceYears(layer, cctx),
};
