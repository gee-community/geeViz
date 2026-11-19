// Chart area sources: uploaded files become GeoJSON features (port of the
// original's upload, which accepts .zip, .geojson, .json, .kmz and .kml),
// and the map view's label (port of chartMapExtent).
import { test } from "node:test";
import assert from "node:assert/strict";
import { UPLOAD_ACCEPT, uploadKind, featuresFromGeoJSON, featuresFromKml, dropZ, viewLabel, ringBounds } from "../js/engine/areasources.js";

const SQUARE = [[[-111.6, 40.6], [-111.58, 40.6], [-111.58, 40.62], [-111.6, 40.62], [-111.6, 40.6]]];

test("the upload accepts what the original's upload accepts", () => {
  assert.equal(UPLOAD_ACCEPT, ".zip,.geojson,.json,.kmz,.kml");
  assert.equal(uploadKind("a.GeoJSON"), "geojson");
  assert.equal(uploadKind("a.json"), "geojson");
  assert.equal(uploadKind("a.kml"), "kml");
  assert.equal(uploadKind("a.zip"), "convert");
  assert.equal(uploadKind("a.kmz"), "convert");
  assert.equal(uploadKind("a.txt"), null);
});

test("featuresFromGeoJSON: FeatureCollection, Feature or bare geometry; non-polygons left out", () => {
  const fc = { type: "FeatureCollection", features: [{ type: "Feature", properties: { n: 1 }, geometry: { type: "Polygon", coordinates: SQUARE } }, { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [0, 0] } }] };
  assert.equal(featuresFromGeoJSON(fc).length, 1);
  assert.equal(featuresFromGeoJSON(fc[0] || fc.features[0]).length, 1);
  assert.deepEqual(featuresFromGeoJSON({ type: "MultiPolygon", coordinates: [SQUARE] })[0].geometry.type, "MultiPolygon");
  assert.deepEqual(featuresFromGeoJSON({ type: "Polygon", coordinates: SQUARE })[0].geometry.coordinates, SQUARE);
});

test("dropZ: port of fixGeoJSONZ", () => {
  const f = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [SQUARE[0].map((c) => c.concat([1500]))] } };
  assert.deepEqual(dropZ(f).geometry.coordinates, SQUARE);
});

test("featuresFromKml: every Polygon's outer and inner rings, z dropped", () => {
  const kml = `<?xml version="1.0"?><kml><Document><Placemark><name>A &amp; B</name><MultiGeometry>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>
      -111.6,40.6,0 -111.58,40.6,0 -111.58,40.62,0 -111.6,40.62,0 -111.6,40.6,0
    </coordinates></LinearRing></outerBoundaryIs>
    <innerBoundaryIs><LinearRing><coordinates>-111.595,40.605 -111.59,40.605 -111.59,40.61 -111.595,40.605</coordinates></LinearRing></innerBoundaryIs></Polygon>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>1,1 2,1 2,2 1,1</coordinates></LinearRing></outerBoundaryIs></Polygon>
  </MultiGeometry></Placemark></Document></kml>`;
  const fs = featuresFromKml(kml);
  assert.equal(fs.length, 2);
  assert.deepEqual(fs[0].geometry.coordinates[0], SQUARE[0]);
  assert.equal(fs[0].geometry.coordinates.length, 2);
  assert.deepEqual(fs[1].geometry.coordinates, [[[1, 1], [2, 1], [2, 2], [1, 1]]]);
});

test("ringBounds and viewLabel", () => {
  assert.deepEqual(ringBounds(featuresFromGeoJSON({ type: "Polygon", coordinates: SQUARE })), { west: -111.6, south: 40.6, east: -111.58, north: 40.62 });
  assert.equal(viewLabel({ west: -111.123456, north: 40.5, east: -110.9, south: 40.25 }), "Map view (-111.123, 40.5, -110.9, 40.25)");
});
