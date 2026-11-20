// The one owner of the map's draggable cursor. It is derived from the store:
// a crosshair while Distance or Area is active, or Chart area draws its area.
// No other module sets draggableCursor, so tools cannot undo each other.

export function cursorFor(state) {
  const t = state.tool;
  if (t === "distance" || t === "area") return "crosshair";
  if (t === "chart" && state.areaFrom === "draw") return "crosshair";
  return null;
}

export function createCursor(gmap, store) {
  let now;
  const apply = () => {
    const next = cursorFor(store.get());
    if (next === now) return next;
    now = next;
    gmap.setOptions({ draggableCursor: next });
    return next;
  };
  store.on("change:tool", apply);
  store.on("change:areaFrom", apply);
  apply();
  return { apply, current: () => now };
}
