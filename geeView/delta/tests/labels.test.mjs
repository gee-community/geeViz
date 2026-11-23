import { test } from "node:test";
import assert from "node:assert/strict";
import { LABELS_STYLE, labelsEnabled } from "../js/engine/maps.js";

test("labels style: the original's labelsMapType (geometry fill off, hairline strokes)", () => {
  assert.deepEqual(LABELS_STYLE, [
    { elementType: "geometry.fill", stylers: [{ visibility: "off" }] },
    { elementType: "geometry.stroke", stylers: [{ weight: 0.01 }] },
  ]);
});

test("addLabelOverlay=false turns the overlay off (string or boolean); anything else leaves it on", () => {
  assert.equal(labelsEnabled({}), true);
  assert.equal(labelsEnabled(undefined), true);
  assert.equal(labelsEnabled({ addLabelOverlay: "true" }), true);
  assert.equal(labelsEnabled({ addLabelOverlay: "false" }), false);
  assert.equal(labelsEnabled({ addLabelOverlay: false }), false);
});
