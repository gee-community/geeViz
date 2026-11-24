// GeoJSON given as data (Map.addLayer with a GeoJSON dict): drawn on canvas
// tiles in the browser (engine/vectortiles.js).
export const geojsonPlugin = {
  kinds: ["geojson"],
  needsEE: false,
  draw(r, item, ctx) {
    ctx.addGeoJson(r, item);
  },
};
