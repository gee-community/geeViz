// Delta compatibility shim. Classic script, loaded before runGeeViz.js.
//
// The generated per-session script (geeView._build_run_js) calls the original
// viewer's globals: Map.*, map.*, areaChart.*, synchronousCenterObject(...),
// showMessage(...), $('#close-modal-button').click(), and assigns a few bare
// globals (queryWindowMode, yLabel*, authProxyAPIURL). This file defines all of
// them. Calls made before main.js installs the real engine are recorded and
// replayed, in order, by window.__deltaCompat.install({...}).
//
// Note: this replaces the built-in global Map, exactly as the original viewer
// does. Delta modules must not call `new Map()`; the native constructor is kept
// at window.__NativeMap.

// Top-level `let` so the generator's `authProxyAPIURL=...` reassignment works.
let authProxyAPIURL = "";

(function () {
  "use strict";
  var w = window;
  w.__NativeMap = w.Map;

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

  w.Map = makeProxy("Map");
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

  // jQuery stand-in: only $('#close-modal-button').click() is meaningful.
  w.$ = function (selector) {
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
        if (e.t === "@handler") {
          dispatchHandler(e.name, e.payload);
        } else if (e.op === "fn") {
          dispatchTarget(e.t, "fn", null, e.payload);
        } else {
          dispatchTarget(e.t, e.op, e.name, e.payload);
        }
      });
    },
    pending: function () {
      return queue.length;
    },
  };
})();
