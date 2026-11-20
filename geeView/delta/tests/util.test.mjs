import { test } from "node:test";
import assert from "node:assert/strict";
import { escapeText, formatLength, formatArea, requestToken } from "../js/util.js";

test("formatLength", () => {
  assert.equal(formatLength(4820, "metric"), "4.82 km");
  assert.equal(formatLength(4820, "imperial"), "3.00 mi");
});

test("formatArea", () => {
  assert.equal(formatArea(4120000, "metric", "area"), "412 ha");
  assert.equal(formatArea(4120000, "imperial", "area"), "1,018 acres");
  assert.equal(formatArea(1030000, "metric", "pct", 4120000), "25.0%");
});

test("escapeText removes angle brackets and quotes", () => {
  const out = escapeText('<b>"x"</b>');
  assert.ok(!out.includes("<"));
  assert.ok(!out.includes(">"));
  assert.ok(!out.includes('"'));
});

test("requestToken: newer token invalidates older", () => {
  const a = requestToken();
  assert.equal(a.isCurrent(), true);
  const b = requestToken();
  assert.equal(a.isCurrent(), false);
  assert.equal(b.isCurrent(), true);
  assert.notEqual(a.id, b.id);
});
