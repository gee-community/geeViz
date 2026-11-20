// The one owner of the map's draggable cursor. It is derived from the store,
// as the original's toolCursorLookup: a crosshair while Distance or Area is
// active or Chart area draws its area, a pointer while it selects features,
// and the question mark ("help") while Query is on, "progress" while a query
// runs. No other module sets draggableCursor, so tools cannot undo each other.

export function cursorFor(state) {
  const t = state.tool;
  if (t === "distance" || t === "area") return "crosshair";
  if (t === "chart" && state.areaFrom === "draw") return "crosshair";
  if (t === "chart" && state.areaFrom === "select") return "pointer";
  if (t === "query") return state.querying ? "progress" : "help";
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
  store.on("change:querying", apply);
  apply();
  return { apply, current: () => now };
}
