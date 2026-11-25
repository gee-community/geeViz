// GeoJSON given as data (Map.addLayer with a GeoJSON dict): drawn on canvas
// tiles in the browser (engine/vectortiles.js), and queried by hit test on
// what is drawn (engine/hittest.js).
import { hitTest } from "../engine/hittest.js";
import { tableResults } from "../engine/query.js";

export const geojsonPlugin = {
  kinds: ["geojson"],
  needsEE: false,
  draw(r, item, ctx) {
    ctx.addGeoJson(r, item);
  },
  query(target, layer, point, qctx) {
    const ov = target.overlay && target.overlay();
    const hits = ov ? hitTest(ov.loadedParts(), point, qctx.zoom) : [];
    const features = hits.map((p) => ({ type: "Feature", properties: p.props, geometry: p.geom }));
    if (features.length && qctx.onVectors) qctx.onVectors({ type: "FeatureCollection", features });
    return Promise.resolve(tableResults(layer, { features }, point, qctx.query && qctx.query.precision));
  },
};
