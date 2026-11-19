// Single observable store for Delta. All UI state lives here.

export function defaultState() {
  return {
    layers: [],
    order: [],
    tool: null,
    units: "metric",
    showAs: "area",
    areaFrom: "draw",
    results: [],
    notices: [],
    theme: "system",
    panes: { left: { visible: true, width: null }, right: { width: null } },
    query: {
      crs: "EPSG:5070",
      scale: 30,
      transform: null,
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
  const handlers = Object.create(null); // not Map: compat.js shadows the global Map

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
