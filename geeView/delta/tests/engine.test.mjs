import test from "node:test";
import assert from "node:assert/strict";
import { createViewHistory, sameView } from "../js/engine/maps.js";
import { parseCoordinates } from "../js/engine/search.js";
import { hasAccessToken, projectIdFrom, describeEEFailure, initEE } from "../js/engine/ee.js";

const v = (lng, lat, zoom = 10) => ({ lng, lat, zoom });

test("history: back and forward walk the stack", () => {
  const h = createViewHistory();
  h.record(v(1, 1));
  h.record(v(2, 2));
  h.record(v(3, 3));
  assert.deepEqual(h.back(), v(2, 2));
  assert.deepEqual(h.back(), v(1, 1));
  assert.equal(h.back(), null);
  assert.deepEqual(h.forward(), v(2, 2));
  assert.deepEqual(h.state(), { index: 2, length: 3, canBack: true, canForward: true });
});

test("history: recording after back drops the forward branch", () => {
  const h = createViewHistory();
  h.record(v(1, 1));
  h.record(v(2, 2));
  h.back();
  h.record(v(9, 9));
  assert.equal(h.state().canForward, false);
  assert.deepEqual(h.back(), v(1, 1));
});

test("history: re-recording the current view is a no-op (landing from back/forward)", () => {
  const h = createViewHistory();
  h.record(v(1, 1));
  h.record(v(2, 2));
  const target = h.back();
  assert.equal(h.record(target), false);
  assert.equal(h.state().canForward, true);
});

test("coordinates: lat lng, lng lat, separators, junk", () => {
  assert.deepEqual(parseCoordinates("40.5, -111.9"), { lat: 40.5, lng: -111.9 });
  assert.deepEqual(parseCoordinates("45 -111"), { lat: 45, lng: -111 });
  assert.deepEqual(parseCoordinates("-111.9, 40.5"), { lat: 40.5, lng: -111.9 });
  assert.equal(parseCoordinates("Salt Lake City"), null);
  assert.equal(parseCoordinates("95, 200"), null);
  assert.equal(parseCoordinates(""), null);
});

test("ee: token detection and project id", () => {
  assert.equal(hasAccessToken({ accessToken: "ya29" }), true);
  for (const t of [undefined, null, "None", "null", ""]) assert.equal(hasAccessToken({ accessToken: t }), false);
  assert.equal(projectIdFrom({ projectID: "None" }), null);
  assert.equal(projectIdFrom({ projectID: "p" }), "p");
  assert.match(describeEEFailure("x", { accessToken: "t", projectID: "p" }), /x/);
});

// ---- initEE wiring, against a stubbed `ee` global ----
function stubEE({ fail = false } = {}) {
  const calls = [];
  globalThis.ee = {
    data: {
      setAuthToken: (...a) => calls.push(["setAuthToken", ...a]),
      setDefaultWorkloadTag: (t) => calls.push(["setDefaultWorkloadTag", t]),
    },
    initialize: (proxy, api, ok, err, lib, project) => {
      calls.push(["initialize", proxy, api, lib, project]);
      if (fail) err("boom");
      else ok();
    },
  };
  globalThis.location = { origin: "http://127.0.0.1:8889" };
  globalThis.mode = "geeViz";
  return calls;
}
const names = (calls) => calls.map((c) => c[0]);

test("initEE token mode: setAuthToken, then initialize(null, null) with the project", async () => {
  const calls = stubEE();
  await initEE({ accessToken: "ya29", projectID: "my-proj", geeAuthProxyURL: "http://x" }, "http://tenant");
  assert.deepEqual(names(calls), ["setAuthToken", "initialize", "setDefaultWorkloadTag"]);
  assert.deepEqual(calls[0].slice(1, 4), ["", "Bearer", "ya29"]);
  assert.deepEqual(calls[1], ["initialize", null, null, null, "my-proj"]);
});

test("initEE proxy mode: the tenant-prefixed url beats geeAuthProxyURL; a getter is read at call time", async () => {
  let calls = stubEE();
  await initEE({ geeAuthProxyURL: "http://param" }, "http://127.0.0.1:8889/ee-api/t/acme");
  assert.equal(calls.find((c) => c[0] === "initialize")[1], "http://127.0.0.1:8889/ee-api/t/acme");
  assert.equal(names(calls).includes("setAuthToken"), false);
  calls = stubEE();
  let current = "";
  const getter = () => current;
  current = "http://late/ee-api/t/t";
  await initEE({}, getter);
  assert.equal(calls.find((c) => c[0] === "initialize")[1], "http://late/ee-api/t/t");
});

test("initEE proxy mode: geeAuthProxyURL, then origin + /ee-api", async () => {
  let calls = stubEE();
  await initEE({ geeAuthProxyURL: "http://param" }, "");
  assert.equal(calls.find((c) => c[0] === "initialize")[1], "http://param");
  calls = stubEE();
  await initEE({ accessToken: "None" }, "");
  const init = calls.find((c) => c[0] === "initialize");
  assert.equal(init[1], "http://127.0.0.1:8889/ee-api");
  assert.equal(init[2], "https://earthengine.googleapis.com");
  assert.equal(init[4], null);
});

test("initEE sets the default workload tag from mode, after initialize", async () => {
  const calls = stubEE();
  await initEE({}, "");
  assert.deepEqual(calls[calls.length - 1], ["setDefaultWorkloadTag", "geeviz---viewer-exports"]);
});

test("initEE rejects when ee.initialize fails and sets no tag", async () => {
  const calls = stubEE({ fail: true });
  await assert.rejects(initEE({}, ""), /boom/);
  assert.equal(names(calls).includes("setDefaultWorkloadTag"), false);
});

test("sameView: tolerance scales with zoom, zoom must match", () => {
  const px = 360 / (256 * 2 ** 10);
  assert.equal(sameView({ lng: 0, lat: 0, zoom: 10 }, { lng: px, lat: 0, zoom: 10 }), true);
  assert.equal(sameView({ lng: 0, lat: 0, zoom: 10 }, { lng: 5 * px, lat: 0, zoom: 10 }), false);
  assert.equal(sameView({ lng: 0, lat: 0, zoom: 10 }, { lng: 0, lat: 0, zoom: 11 }), false);
});
