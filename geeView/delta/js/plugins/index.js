// The layer plug-ins: each layer kind (layer.kind, set by api.js) is drawn,
// and queried, by exactly one plug-in. Earth Engine is one plug-in among
// others; a map with no Earth Engine kinds never loads Earth Engine.
//
// A plug-in: {
//   kinds: [kind, ...],
//   needsEE: true when its layers need Earth Engine loaded and signed in,
//   start(layer, ctx)?: handles a layer that gets no layer record of its own
//     (a timelapse, an area-chart-only layer); returns true when it did,
//   draw(rec, item, ctx): puts a prepared layer on the map,
//   query?(target, layer, point, qctx): Promise<results>, for the Query tool,
//   legend?(rec, ctx): Promise<legend | null>, asked once the layer is drawn,
//   chart?(layer, area, cctx): Promise<results>, for Chart area,
//   ownsViz: true when its viz is its own (no Earth Engine viz preparation),
// }
// ctx is the layer engine's own helpers (engine/layers.js).
import { eePlugin } from "./ee.js";
import { tilesPlugin } from "./tiles.js";
import { geojsonPlugin } from "./geojson.js";
import { esriPlugin } from "./esri.js";

// Filled on first use: the plug-ins import engine modules that import this
// registry, so the list cannot be built while those modules load.
export const PLUGINS = [];
function plugins() {
  if (!PLUGINS.length) PLUGINS.push(eePlugin, tilesPlugin, geojsonPlugin, esriPlugin);
  return PLUGINS;
}

export function pluginFor(kind) {
  const p = plugins().find((x) => x.kinds.indexOf(kind) > -1);
  if (!p) throw new Error("No plug-in for layer kind: " + kind);
  return p;
}

export const needsEE = (layer) => !!layer && pluginFor(layer.kind).needsEE;
