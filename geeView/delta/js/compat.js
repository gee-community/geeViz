// Delta compatibility shim. Classic script, loaded before runGeeViz.js.
//
// The generated per-session script (geeView._build_run_js) calls the original
// viewer's globals: Map.*, map.*, areaChart.*, synchronousCenterObject(...),
// showMessage(...), $('#close-modal-button').click(), and assigns a few bare
// globals (queryWindowMode, yLabel*, authProxyAPIURL). This file defines all of
// them. Calls made before main.js installs the real engine are recorded and
// replayed, in order, by window.__deltaCompat.install({...}).
//
// Note: window.Map stays the native Map constructor. As in the original viewer
// (`Object.keys(Map2).map((k) => (Map[k] = Map2[k]))`), the viewer methods are
// attached to it as static properties, so `new Map()` keeps working everywhere.

// Top-level `let` so the generator's `authProxyAPIURL=...` reassignment works.
let authProxyAPIURL = "";

// The layer registry geeView/src/js/wind-particles.js reads, as the original
// viewer's top-level `let layerObj`: a global lexical binding, not a property
// of window. engine/wind.js fills it with Delta's wind layers.
let layerObj = {};

(function () {
  "use strict";
  var w = window;

  var queue = []; // {t: target, op: "call"|"set"|"fn", name, args|value}
  var targets = {}; // Map, map, areaChart, synchronousCenterObject (object or function)
  var handlers = {}; // globals, showMessage, closeLoading, notify

  function dispatchTarget(t, op, name, payload) {
    var target = targets[t];
    if (!target) {
      queue.push({ t: t, op: op, name: name, payload: payload });
      return undefined;
    }
    if (op === "fn") return target.apply(null, payload);
    if (op === "set") {
      target[name] = payload;
      return undefined;
    }
    if (typeof target[name] !== "function") {
      throw new TypeError(t + "." + name + " is not a function in Delta");
    }
    return target[name].apply(target, payload);
  }

  function dispatchHandler(name, args) {
    var h = handlers[name];
    if (!h) {
      queue.push({ t: "@handler", op: "fn", name: name, payload: args });
      return undefined;
    }
    return h.apply(null, args);
  }

  function makeProxy(t) {
    return new Proxy(
      {},
      {
        get: function (_, key) {
          if (typeof key === "symbol") return undefined;
          if (targets[t] && typeof targets[t][key] !== "function") return targets[t][key];
          return function () {
            return dispatchTarget(t, "call", key, Array.prototype.slice.call(arguments));
          };
        },
        set: function (_, key, value) {
          dispatchTarget(t, "set", key, value);
          return true;
        },
      }
    );
  }

  var MAP_METHODS = [
    "addLayer", "removeLayer", "addSerializedLayer", "hideSelectLayerAreaCharting",
    "showSelectLayerAreaCharting", "addSelectLayer", "addSelectLayerGroup",
    "addSerializedSelectLayer", "addTimeLapse", "addSerializedTimeLapse", "addREST",
    "addExport", "addPlot", "addFeatureView", "addMBSankey", "centerObject", "setCenter",
    "setTitle", "turnOnInspector", "turnOffInspector", "turnOnAutoAreaCharting",
    "turnOffAutoAreaCharting", "turnOnUserDefinedAreaCharting",
    "turnOffUserDefinedAreaCharting", "turnOnSelectionAreaCharting",
    "turnOffSelectionAreaCharting", "turnOnTimeSeriesCharting", "turnOffTimeSeriesCharting",
    "setQueryCRS", "setQueryScale", "setQueryTransform", "setQueryPrecision",
    "setQueryDateFormat", "setQueryBoxColor", "showSpinner", "hideSpinner",
  ];
  var MAP_PROPS = { selectLayerAdded: false, canReorderLayers: true, turnOffLayersWhenTimeLapseIsOn: true };

  MAP_METHODS.forEach(function (name) {
    Object.defineProperty(w.Map, name, {
      configurable: true,
      writable: true,
      enumerable: false,
      value: function () {
        return dispatchTarget("Map", "call", name, Array.prototype.slice.call(arguments));
      },
    });
  });
  Object.keys(MAP_PROPS).forEach(function (name) {
    Object.defineProperty(w.Map, name, {
      configurable: true,
      enumerable: false,
      get: function () {
        return targets.Map ? targets.Map[name] : MAP_PROPS[name];
      },
      set: function (v) {
        MAP_PROPS[name] = v;
        if (targets.Map) targets.Map[name] = v;
        else queue.push({ t: "Map", op: "set", name: name, payload: v });
      },
    });
  });
  w.map = makeProxy("map");
  w.areaChart = makeProxy("areaChart");
  w.synchronousCenterObject = function () {
    return dispatchTarget("synchronousCenterObject", "fn", null, Array.prototype.slice.call(arguments));
  };

  w.showMessage = function (title, html) {
    dispatchHandler("showMessage", [title, html]);
  };
  w.staticTemplates = { loadingModal: { geeViz: "" } };
  if (typeof w.mode === "undefined") w.mode = "geeViz";

  // Bare globals assigned by the generated script.
  var globalVals = {
    queryWindowMode: "sidepane",
    yLabelMaxLength: 30,
    yLabelBreakLength: 10,
    yLabelMaxLines: 5,
    yLabelFontSize: 10,
  };
  Object.keys(globalVals).forEach(function (name) {
    Object.defineProperty(w, name, {
      configurable: true,
      enumerable: true,
      get: function () {
        return globalVals[name];
      },
      set: function (v) {
        globalVals[name] = v;
        dispatchHandler("globals", [name, v]);
      },
    });
  });

  // urlParams: parsed from the query string; values already set by the
  // export_html bootstrap win.
  function parseQuery(search) {
    var out = {};
    String(search || "")
      .replace(/^\?/, "")
      .split("&")
      .forEach(function (pair) {
        if (!pair) return;
        var i = pair.indexOf("=");
        var k = i < 0 ? pair : pair.slice(0, i);
        var v = i < 0 ? "" : pair.slice(i + 1);
        try {
          out[decodeURIComponent(k)] = decodeURIComponent(v.replace(/\+/g, " "));
        } catch (e) {
          out[k] = v;
        }
      });
    return out;
  }
  w.urlParams = Object.assign(parseQuery(w.location && w.location.search), w.urlParams || {});

  // An empty, chainable jQuery set: what jQuery returns for no match.
  function emptySet() {
    var set = new Proxy(
      { length: 0 },
      {
        get: function (o, key) {
          if (typeof key === "symbol") return undefined;
          if (key in o) return o[key];
          return function () {
            return set;
          };
        },
      }
    );
    return set;
  }
  // wind-particles.js looks up the original viewer's layer panel elements
  // (#<layer id>-spinner2, -layer-container, -class-container, -opacity...)
  // for the layers in layerObj. Delta has no such elements, so those lookups
  // find nothing, quietly, as jQuery would.
  function windSelector(selector) {
    if (selector === undefined) return true;
    if (typeof selector !== "string" || selector.charAt(0) !== "#") return false;
    for (var k in layerObj) {
      var L = layerObj[k];
      var ids = [k, L && L.viz && L.viz.timeLapseID];
      for (var i = 0; i < ids.length; i++) {
        if (ids[i] && selector.indexOf("#" + ids[i] + "-") === 0) return true;
      }
    }
    return false;
  }

  // jQuery stand-in: only $('#close-modal-button').click() is meaningful.
  w.$ = function (selector) {
    if (windSelector(selector)) return emptySet();
    if (selector === "#close-modal-button") {
      return {
        click: function () {
          dispatchHandler("closeLoading", []);
        },
      };
    }
    function stub() {
      return new Proxy(function () {}, {
        get: function (_, key) {
          if (typeof key === "symbol") return undefined;
          return function () {
            dispatchHandler("notify", ["$(" + JSON.stringify(String(selector)) + ")." + String(key) + "() is not available in Delta yet."]);
            return stub();
          };
        },
      });
    }
    return stub();
  };

  w.__deltaCompat = {
    // targets: any of Map, map, areaChart, synchronousCenterObject;
    // handlers: any of globals(name, value), showMessage(title, html), closeLoading(), notify(msg).
    // May be called more than once (e.g. `map` once the Google map exists).
    install: function (opts) {
      opts = opts || {};
      ["Map", "map", "areaChart", "synchronousCenterObject"].forEach(function (k) {
        if (opts[k]) targets[k] = opts[k];
      });
      ["globals", "showMessage", "closeLoading", "notify"].forEach(function (k) {
        if (opts[k]) handlers[k] = opts[k];
      });
      var pending = queue;
      queue = [];
      pending.forEach(function (e) {
        try {
          if (e.t === "@handler") dispatchHandler(e.name, e.payload);
          else dispatchTarget(e.t, e.op, e.name, e.payload);
        } catch (err) {
          var msg = (e.t === "@handler" ? e.name : e.t + (e.name ? "." + e.name : "")) + " failed during startup: " + (err && err.message);
          if (handlers.notify) handlers.notify(msg);
          else if (w.console) w.console.error(msg);
        }
      });
    },
    pending: function () {
      return queue.length;
    },
    layerObj: layerObj,
  };
})();
