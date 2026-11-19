// Place and coordinate search on every [data-role=search] input.
import { parseCoordinates } from "../engine/search.js";

const COORD_ZOOM = 14;
const LIMITS = { south: [-85, 85], west: [-179, 179], north: [-85, 85], east: [-179, 179] };

export function mountSearch(engine, { notify } = {}) {
  const g = window.google.maps;
  const gmap = engine.gmap;
  let markers = [];

  Array.from(document.querySelectorAll("[data-role=search]")).forEach((input) => {
    // Coordinates win over place search; registered before the SearchBox so it sees Enter first.
    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const c = parseCoordinates(input.value);
      if (!c) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      engine.setCenter(c.lng, c.lat, Math.max(gmap.getZoom(), COORD_ZOOM));
    });

    // port of 4map-manager.js initSearchBox
    const box = new g.places.SearchBox(input);
    gmap.addListener("bounds_changed", () => box.setBounds(gmap.getBounds()));
    box.addListener("places_changed", () => {
      const places = box.getPlaces();
      if (!places || places.length === 0) return;
      markers.forEach((m) => m.setMap(null));
      markers = [];
      const bounds = new g.LatLngBounds();
      places.forEach((place) => {
        if (!place.geometry) return;
        markers.push(new g.Marker({ map: gmap, title: place.name, position: place.geometry.location }));
        if (place.geometry.viewport) bounds.union(place.geometry.viewport);
        else bounds.extend(place.geometry.location);
      });
      const b = bounds.toJSON();
      let clamped = false;
      Object.keys(b).forEach((k) => {
        const [min, max] = LIMITS[k];
        if (b[k] < min) {
          b[k] = min;
          clamped = true;
        } else if (b[k] > max) {
          b[k] = max;
          clamped = true;
        }
      });
      if (clamped && notify) notify("Search coordinates format is lat lng (e.g. 45 -111)");
      gmap.fitBounds(b);
    });
  });
}
