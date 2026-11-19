// Search helpers. No DOM access (the input wiring lives in ui/search.js).

const NUM = String.raw`[-+]?\d+(?:\.\d+)?`;
const PAIR = new RegExp(String.raw`^\s*(${NUM})\s*[,;\s]\s*(${NUM})\s*$`);

// Parse "lat, lng" or "lng, lat". The original viewer documents the order as
// "lat lng (e.g. 45 -111)" and clamps results to a valid range; here the order
// is decided by range: the first number is the latitude unless it cannot be
// one (|value| > 90) while the second can, as in "-111.9, 40.5".
// Returns {lat, lng} or null when the text is not a coordinate pair.
export function parseCoordinates(text) {
  const m = PAIR.exec(String(text == null ? "" : text));
  if (!m) return null;
  let a = Number(m[1]);
  let b = Number(m[2]);
  let lat = a;
  let lng = b;
  if (Math.abs(a) > 90 && Math.abs(b) <= 90) {
    lat = b;
    lng = a;
  }
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  return { lat, lng };
}
