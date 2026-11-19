// Right pane tool options: the units switch and the active tool's options.
// The tool buttons themselves are wired in shell.js (one active, clicking the
// active one turns it off and folds the pane). Ported from the approved
// mockup's opts() and units switch. Query is wired here; Distance, Area and
// Chart area show their hints until their tasks add the rest.

const HINTS = {
  distance: "Click the map to start measuring. Double-click to finish.",
  area: "Click the map to outline an area. Double-click to finish.",
  query: "Double-click the map to query every visible layer at that point.",
  chart: "Pick where the area comes from. Every visible chartable layer gets charted inside it.",
};
const PHONE_HINTS = { query: "Tap the map to query every visible layer at that point." };

export function hintFor(tool, phone) {
  if (!tool) return "";
  return (phone && PHONE_HINTS[tool]) || HINTS[tool] || "";
}

function hintEl(text) {
  const d = document.createElement("div");
  d.className = "topt-hint";
  const i = document.createElement("i");
  i.className = "ti ti-info-circle";
  const span = document.createElement("span");
  span.textContent = text;
  d.append(i, span);
  return d;
}

export function mountTools(store, { optionsEl, unitsEl } = {}) {
  const phoneMq = matchMedia("(max-width: 760px)");
  const unitButtons = unitsEl ? Array.from(unitsEl.querySelectorAll("[data-u]")) : [];

  function renderUnits() {
    const u = store.get().units;
    unitButtons.forEach((b) => {
      b.classList.toggle("on", b.dataset.u === u);
      b.setAttribute("aria-pressed", String(b.dataset.u === u));
    });
  }
  unitButtons.forEach((b) => b.addEventListener("click", () => store.set({ units: b.dataset.u }, "units")));

  function renderOptions() {
    if (!optionsEl) return;
    const text = hintFor(store.get().tool, phoneMq.matches);
    optionsEl.replaceChildren(...(text ? [hintEl(text)] : []));
  }

  // Each tool has its own output: a new tool starts with an empty one.
  store.on("change:tool", () => {
    store.set({ results: [], where: "" }, "tool-output-reset");
    renderOptions();
  });
  store.on("change:units", renderUnits);
  phoneMq.addEventListener("change", renderOptions);
  renderUnits();
  renderOptions();
  return { renderOptions };
}
