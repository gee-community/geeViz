// Distance and Area tools: the measuring functions (with Google's spherical
// library stubbed by a geodesic implementation) and the result cards.
import { test, before } from "node:test";
import assert from "node:assert/strict";

const R = 6378137;
const rad = (d) => (d * Math.PI) / 180;
const pt = (p) => (typeof p.lat === "function" ? { lat: p.lat(), lng: p.lng() } : p);
const hav = (a, b) => {
  a = pt(a);
  b = pt(b);
  const h = Math.sin(rad(b.lat - a.lat) / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(rad(b.lng - a.lng) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};
const length = (path) => path.slice(1).reduce((s, p, i) => s + hav(path[i], p), 0);
// area of a polygon by summing trapezoids under each edge on the sphere
const area = (path) => {
  const p = path.map(pt);
  let s = 0;
  for (let i = 0; i < p.length; i++) {
    const a = p[i];
    const b = p[(i + 1) % p.length];
    s += rad(b.lng - a.lng) * (2 + Math.sin(rad(a.lat)) + Math.sin(rad(b.lat)));
  }
  return Math.abs((s * R * R) / 2);
};

let M;
before(async () => {
  globalThis.google = { maps: { geometry: { spherical: { computeLength: length, computeArea: area } } } };
  M = await import("../js/engine/measure.js");
});

const SLC = { lat: 40.7608, lng: -111.891 };
const PROVO = { lat: 40.2338, lng: -111.6585 };

test("distanceMeters: Salt Lake City to Provo is 61.8 km", () => {
  assert.ok(Math.abs(M.distanceMeters([SLC, PROVO]) / 1000 - 61.8) < 0.5);
  assert.equal(M.distanceMeters([SLC]), 0);
});

test("distanceMeters adds the legs of a longer line", () => {
  const mid = { lat: 40.5, lng: -111.8 };
  assert.ok(Math.abs(M.distanceMeters([SLC, mid, PROVO]) - (hav(SLC, mid) + hav(mid, PROVO))) < 1e-6);
});

const SQ = [
  { lat: 40, lng: -111 },
  { lat: 40, lng: -110.9 },
  { lat: 40.1, lng: -110.9 },
  { lat: 40.1, lng: -111 },
];

test("areaSquareMeters and perimeterMeters of a 0.1 degree square", () => {
  const exact = R * R * rad(0.1) * (Math.sin(rad(40.1)) - Math.sin(rad(40)));
  assert.ok(Math.abs(M.areaSquareMeters(SQ) - exact) / exact < 1e-9);
  const per = hav(SQ[0], SQ[1]) + hav(SQ[1], SQ[2]) + hav(SQ[2], SQ[3]) + hav(SQ[3], SQ[0]);
  assert.ok(Math.abs(M.perimeterMeters(SQ) - per) < 1e-6);
  assert.equal(M.areaSquareMeters(SQ.slice(0, 2)), 0);
});

test("measureResult: distance card in both unit systems, through the shared formatters", () => {
  const line = [SLC, PROVO];
  const m = M.measureResult("distance", line, "metric");
  assert.equal(m.kind, "measure");
  assert.equal(m.title, "Distance");
  assert.match(m.data.lines[0][1], /^61\.\d\d km$/);
  const i = M.measureResult("distance", line, "imperial");
  assert.match(i.data.lines[0][1], /^38\.\d\d mi$/);
  assert.equal(i.id, m.id);
  assert.equal(m.data.text, "Distance: " + m.data.lines[0][1]);
});

test("measureResult: area card also shows perimeter", () => {
  const m = M.measureResult("area", SQ, "metric");
  assert.equal(m.title, "Area");
  assert.deepEqual(m.data.lines.map((l) => l[0]), ["Area", "Perimeter"]);
  assert.match(m.data.lines[0][1], /ha$/);
  assert.match(m.data.lines[1][1], /km$/);
  const i = M.measureResult("area", SQ, "imperial");
  assert.match(i.data.lines[0][1], / sq mi$/);
  assert.match(i.data.lines[1][1], /mi$/);
});

test("measureResult: a readout from the first point; nothing before it", () => {
  assert.equal(M.measureResult("distance", [], "metric"), null);
  assert.equal(M.measureResult("area", [], "metric"), null);
  const d = M.measureResult("distance", [SLC], "metric");
  assert.equal(d.meta, "1 point");
  assert.deepEqual(d.data.lines.map((l) => l[0]), ["Distance"]);
  const a = M.measureResult("area", SQ.slice(0, 2), "metric");
  assert.equal(a.meta, "2 points");
  assert.deepEqual(a.data.lines.map((l) => l[0]), ["Area", "Perimeter"]);
  assert.match(a.data.lines[0][1], /^0 /); // no area until a third point
});
