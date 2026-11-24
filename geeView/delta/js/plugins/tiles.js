// XYZ tile services (Map.addTileLayer) and dynamic map services
// (Map.addDynamicMapService: one export image per map tile).
export const tilesPlugin = {
  kinds: ["tile", "dynamic"],
  needsEE: false,
  draw(r, item, ctx) {
    if (r.layerType === "tileMapService") {
      const maxZoom = Number.isFinite(Number(r.viz.maxZoom)) ? Number(r.viz.maxZoom) : 15;
      r.overlay = ctx.tileOverlay(r, (coord, zoom) => item(coord, zoom), { maxZoom });
      // LOCAL PATCH tile legend v3 is carried by the row: the legend is the row's own, shown whenever the layer is on.
      ctx.setLoading(r, false);
      ctx.sync();
      return;
    }
    // one export image per map tile, in the tile stack like any layer (the
    // original drew one image per view above the tiles); below a service's
    // minZoom there is no image
    const svcs = r.item;
    r.overlay = ctx.tileOverlay(r, (coord, zoom) => {
      const svc = zoom > svcs[1].minZoom ? svcs[1] : svcs[0];
      return ctx.groundOverlayUrl(svc.baseURL, svc.minZoom, svc.ending, zoom, ctx.tileBounds(coord.x, coord.y, zoom), 256, 256);
    });
    r.tileType = true;
    ctx.setLoading(r, false);
    ctx.sync();
  },
};
