import { test } from "node:test";
import assert from "node:assert/strict";
import { LABELS_STYLE, DARK_STYLE, labelsStyleFor, labelsEnabled } from "../js/engine/maps.js";

test("labels style: the original's labelsMapType (geometry fill off, hairline strokes)", () => {
  assert.deepEqual(LABELS_STYLE, [
    { elementType: "geometry.fill", stylers: [{ visibility: "off" }] },
    { elementType: "geometry.stroke", stylers: [{ weight: 0.01 }] },
  ]);
});

test("dark labels keep DARK_STYLE's label colors and hidden features, never its fills", () => {
  const s = labelsStyleFor(DARK_STYLE);
  assert.deepEqual(s.slice(0, 2), LABELS_STYLE);
  const rest = s.slice(2);
  assert.ok(rest.some((x) => x.elementType === "labels.text.fill" && x.stylers[0].color === "#a39a93"));
  assert.ok(rest.some((x) => x.elementType === "labels.text.stroke" && x.stylers[0].color === "#141211"));
  assert.ok(rest.some((x) => x.featureType === "poi" && x.stylers[0].visibility === "off"));
  // No geometry colors: they would paint over every layer.
  assert.ok(rest.every((x) => !x.elementType || x.elementType.indexOf("labels") === 0));
});

test("addLabelOverlay=false turns the overlay off (string or boolean); anything else leaves it on", () => {
  assert.equal(labelsEnabled({}), true);
  assert.equal(labelsEnabled(undefined), true);
  assert.equal(labelsEnabled({ addLabelOverlay: "true" }), true);
  assert.equal(labelsEnabled({ addLabelOverlay: "false" }), false);
  assert.equal(labelsEnabled({ addLabelOverlay: false }), false);
});
