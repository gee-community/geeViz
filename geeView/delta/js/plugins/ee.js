// Earth Engine layers: images and collections drawn as Earth Engine map tiles,
// vectors painted by Earth Engine or pulled down as GeoJSON, select layers,
// timelapses and area-chart-only layers. Earth Engine is loaded and signed in
// only for these.
export const eePlugin = {
  kinds: ["ee", "select", "timelapse", "areaChartOnly"],
  needsEE: true,
  start(layer, ctx) {
    if (layer.kind === "areaChartOnly") return true; // charted, never drawn
    if (layer.kind === "timelapse") {
      ctx.addTimelapse(layer);
      return true;
    }
    return false;
  },
  draw(r, item, ctx) {
    if (r.tileType) return ctx.eeTileLayer(r, item);
    if (r.layerType === "geeVector") {
      r.requests++;
      item.evaluate((v, err) => {
        if (!ctx.recs.has(r.id)) return;
        if (v === undefined || err) return ctx.fail(r, err || "The features could not be loaded");
        ctx.addGeoJson(r, v);
      });
      return;
    }
    ctx.fail(r, "Unknown layer type: " + r.layerType);
  },
};
