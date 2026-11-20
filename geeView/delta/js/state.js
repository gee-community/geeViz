// Single observable store for Delta. All UI state lives here.

export function defaultState() {
  return {
    layers: [],
    order: [],
    tool: null,
    units: "metric",
    showAs: "area",
    areaFrom: "view",
    results: [],
    where: "",
    querying: false,
    // Chart area: busy flag, the area last charted ({label, key, bounds}),
    // Sankey transition periods (null until the Sankey layers' years are
    // known; then single years at the ends of their range, port of
    // setupTransitionPeriodUI's two default rows), whether the user applied
    // them, periods given by the url, the layers' years, and settings choices
    // of which layers chart.
    charting: false,
    chartArea: null,
    chartPeriods: null,
    chartPeriodsUser: false,
    chartPeriodsGiven: null,
    chartYears: {},
    chartChoices: {},
    selections: [],
    // the active sketch (Distance, Area, Chart area Draw): {tool, canUndo,
    // canRedo, shapes, drawing}, for the undo/redo/clear buttons
    sketch: null,
    notices: [],
    theme: "system",
    panes: { left: { visible: true, width: null }, right: { width: null } },
    // port of 1variables.js crs, transform and scale: the query grid is the
    // 30 m CONUS Albers grid until setQueryScale or setQueryTransform.
    query: {
      crs: "EPSG:5070",
      scale: null,
      transform: [30, 0, -2361915.0, 0, -30, 3177735.0],
      precision: { chartPrecision: 3, chartDecimalProportion: 0.25 },
      dateFormat: "YYYY-MM-dd",
      boxColor: null,
      windowMode: "sidepane",
    },
    chartSettings: { yLabelMaxLength: 30, yLabelBreakLength: 10, yLabelMaxLines: 5, yLabelFontSize: 10 },
    canReorder: true,
    title: null,
    turnOffLayersWhenTimeLapseIsOn: true,
  };
}

export function createStore(initial) {
  let state = { ...defaultState(), ...(initial || {}) };
  const handlers = Object.create(null);

  function emit(event, ...args) {
    const list = handlers[event];
    if (list) list.slice().forEach((fn) => fn(...args));
  }

  function commit(next, reason) {
    const prev = state;
    state = next;
    const keys = [...Object.keys(prev), ...Object.keys(next).filter((k) => !(k in prev))];
    for (const k of keys) if (prev[k] !== next[k]) emit("change:" + k, next[k], next, reason);
    emit("change", next, reason);
  }

  return {
    get: () => state,
    set(patch, reason) {
      commit({ ...state, ...patch }, reason);
    },
    update(fn, reason) {
      commit(fn(state), reason);
    },
    on(event, fn) {
      (handlers[event] = handlers[event] || []).push(fn);
      return () => {
        handlers[event] = (handlers[event] || []).filter((f) => f !== fn);
      };
    },
  };
}
