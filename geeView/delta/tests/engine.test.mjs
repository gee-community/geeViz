import test from "node:test";
import assert from "node:assert/strict";
import { createViewHistory } from "../js/engine/maps.js";
import { parseCoordinates } from "../js/engine/search.js";
import { hasAccessToken, projectIdFrom, describeEEFailure } from "../js/engine/ee.js";

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
