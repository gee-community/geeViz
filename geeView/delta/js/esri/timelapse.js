// A time-enabled ArcGIS service played as a timelapse: one frame per time
// step (from its timeInfo interval, or an image service's catalog years),
// each drawn with the service's time= parameter. The frame loader contract is
// engine/timelapse.js's: {prepare(), years(), frame(i), queryTarget()}.
import { serviceInfo, serviceKind, normalizeUrl, timeSteps, catalogYears } from "./rest.js";
import { exportUrl, tile3857 } from "./draw.js";
import { serviceLegend } from "./legend.js";

export function esriFrameLoader(engine, layer) {
  const url = normalizeUrl(layer.item);
  const opts = (layer.viz && layer.viz.esri) || {};
  const req = { fetch: engine.fetch };
  let steps = null;
  const info = () => serviceInfo(url, req);

  async function stepsOf() {
    if (steps) return steps;
    const i = await info();
    if (!i.timeInfo) throw new Error(`${layer.name} is not time-enabled, so it cannot play as a timelapse.`);
    const years = await catalogYears(url, i, req);
    steps = timeSteps(i, years);
    if (!steps.length) throw new Error(`${layer.name} has no time steps to play.`);
    return steps;
  }
  const kindOf = (i) => {
    const k = serviceKind(url, i, { ...opts, time: [0, 1] });
    return k === "esri.image" ? "esri.image" : "esri.map";
  };

  return {
    async prepare() {
      const i = await info();
      let legend = null;
      try {
        legend = await serviceLegend(url, i, opts, { ...req, title: layer.name });
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
      return (coord, zoom) => exportUrl(url, kind, frameOpts, tile3857(coord.x, coord.y, zoom), 256, i);
    },
    // the Query tool: the service's values over time at the point
    async queryTarget() {
      const i = await info();
      return { type: kindOf(i), item: url, viz: layer.viz };
    },
  };
}
