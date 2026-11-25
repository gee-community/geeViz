// A time-enabled ArcGIS service played as a timelapse: one frame per time
// step (from its timeInfo interval, or an image service's catalog years),
// each drawn with the service's time= parameter. The frame loader contract is
// engine/timelapse.js's: {prepare(), years(), frame(i), queryTarget()}.
import { serviceInfo, serviceKind, normalizeUrl, sublayerOf, timeSteps, catalogYears } from "./rest.js";
import { exportTileUrl } from "./draw.js";
import { serviceLegend } from "./legend.js";

export function esriFrameLoader(engine, layer) {
  const url = normalizeUrl(layer.item);
  // a map service sublayer is drawn by its map service, that sublayer only
  const sub = sublayerOf(url);
  const drawUrl = sub ? sub.parent : url;
  const opts = { ...((layer.viz && layer.viz.esri) || {}), ...(sub ? { layers: `show:${sub.id}` } : {}) };
  const req = { fetch: engine.fetch };
  let steps = null;
  const info = () => serviceInfo(url, req);

  async function stepsOf() {
    if (steps) return steps;
    const i = await info();
    if (/\/FeatureServer\/\d+$/i.test(url)) {
      throw new Error(`${layer.name} is a feature layer: a timelapse of its features is not supported yet. Add it with time= for one period.`);
    }
    if (!i.timeInfo) throw new Error(`${layer.name} is not time-enabled, so it cannot play as a timelapse.`);
    const years = await catalogYears(url, i, req);
    steps = timeSteps(i, years);
    if (!steps.length) throw new Error(`${layer.name} has no time steps to play.`);
    return steps;
  }
  const kindOf = (i) => (sub ? "esri.map" : serviceKind(url, i, { ...opts, time: [0, 1] }) === "esri.image" ? "esri.image" : "esri.map");

  return {
    // an ArcGIS export is slow: the frame shown and the next two are asked for
    prefetch: 2,
    async prepare() {
      const i = sub ? await serviceInfo(drawUrl, req) : await info();
      let legend = null;
      try {
        legend = await serviceLegend(drawUrl, i, opts, { ...req, title: layer.name });
      } catch (e) {
        legend = null;
      }
      return { legend, viz: layer.viz };
    },
    async years() {
      return (await stepsOf()).map((s) => s.label);
    },
    async frame(n) {
      const i = await info();
      const st = (await stepsOf())[n];
      const kind = kindOf(i);
      const frameOpts = { ...opts, time: st.time };
      return exportTileUrl(drawUrl, kind, frameOpts, i);
    },
    // the Query tool: the service's values over time at the point
    async queryTarget() {
      const i = await info();
      return { type: kindOf(i), item: drawUrl, viz: { ...(layer.viz || {}), esri: opts } };
    },
  };
}
