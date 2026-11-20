// Drawing bits shared by Distance, Area and Chart area's Draw source, so the
// stroke style and the double-click handling cannot drift apart.

// The second click of a double-click lands on the point just added.
export function sameLatLng(a, b) {
  return !!a && !!b && Math.abs(a.lat() - b.lat()) < 1e-9 && Math.abs(a.lng() - b.lng()) < 1e-9;
}

export function drawStyle(stroke) {
  return { strokeColor: stroke, strokeOpacity: 1, strokeWeight: 3, fillColor: stroke, fillOpacity: 0.12, clickable: false, geodesic: true, zIndex: 3100 };
}

// Re-style drawn shapes (the theme changed). Null entries are skipped.
export function restyleShapes(shapes, stroke) {
  shapes.forEach((s) => s && s.setOptions(drawStyle(stroke)));
}
