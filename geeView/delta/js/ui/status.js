// Bottom status bar: active tool, cursor coordinates, elevation, zoom, tiles loading.

const TOOL_LABELS = { distance: "Distance", area: "Area", query: "Query", chart: "Chart area" };

export function formatElevation(meters, units) {
  if (meters === null || meters === undefined || !Number.isFinite(meters)) return "-";
  return units === "imperial" ? Math.round(meters * 3.28084) + " ft" : Math.round(meters) + " m";
}

export function formatCoords(lat, lng) {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return "-";
  return lat.toFixed(5) + ", " + lng.toFixed(5);
}

export function mountStatus(store, el, loadbarEl) {
  const cells = {};
  const mk = (key) => {
    const s = document.createElement("span");
    cells[key] = s;
    return s;
  };
  const sep = () => {
    const s = document.createElement("span");
    s.className = "sep";
    s.textContent = "|";
    return s;
  };
  const grow = document.createElement("span");
  grow.className = "grow";
  el.replaceChildren(mk("tool"), sep(), mk("coords"), sep(), mk("elev"), grow, mk("zoom"), sep(), mk("loading"));

  let coords = "-";
  let elevM = null;
  let zoom = null;
  let loading = 0;

  function render() {
    const { tool, units } = store.get();
    cells.tool.textContent = tool ? TOOL_LABELS[tool] || tool : "No tool";
    cells.coords.textContent = coords;
    cells.elev.textContent = "Elev " + formatElevation(elevM, units);
    cells.zoom.textContent = "Zoom " + (zoom === null ? "-" : zoom);
    cells.loading.textContent = loading ? loading + " loading" : "Idle";
    if (loadbarEl) loadbarEl.hidden = loading === 0;
  }
  store.on("change:tool", render);
  store.on("change:units", render);
  render();

  return {
    setCursor(lat, lng) {
      coords = formatCoords(lat, lng);
      render();
    },
    setElevation(meters) {
      elevM = meters;
      render();
    },
    setZoom(z) {
      zoom = z;
      render();
    },
    setLoading(n) {
      loading = n;
      render();
    },
  };
}
