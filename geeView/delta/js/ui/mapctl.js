// Map chrome wiring: zoom, full screen, Street View pick, basemaps, view history.
// The engine does the map work; this module only connects buttons and body
// classes to it.

export function mountMapControls(engine, shell, status) {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const body = document.body;

  // zoom and full screen
  $("#mapctl [data-act=zoom-in]").addEventListener("click", () => engine.zoomBy(1));
  $("#mapctl [data-act=zoom-out]").addEventListener("click", () => engine.zoomBy(-1));
  $("#mapctl [data-act=fullscreen]").addEventListener("click", () => {
    try {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    } catch (e) {
      /* full screen can be refused */
    }
  });

  // basemaps; on a phone the first tap on the lone visible one opens the rest
  const phone = matchMedia("(max-width: 760px)");
  $$("#mapctl .bm").forEach((b) =>
    b.addEventListener(
      "click",
      (e) => {
        if (phone.matches && b.classList.contains("on") && !body.classList.contains("bm-open")) {
          e.stopImmediatePropagation();
          body.classList.add("bm-open");
          return;
        }
        body.classList.remove("bm-open");
        engine.setBasemap(b.dataset.bm);
      },
      true
    )
  );
  engine.onBasemap((key) => $$("#mapctl .bm").forEach((b) => b.classList.toggle("on", b.dataset.bm === key)));

  // Street View
  $("#svBtn").addEventListener("click", () => engine.streetViewPick(!engine.isPicking()));
  engine.onPick((on) => {
    body.classList.toggle("sv-pick", on);
    $("#svBtn").classList.toggle("on", on);
  });
  engine.onStreetView((on) => shell.setStreetView(on));

  // view history
  $$("[data-act=prev-view]").forEach((b) => b.addEventListener("click", () => engine.back()));
  $$("[data-act=next-view]").forEach((b) => b.addEventListener("click", () => engine.forward()));
  engine.onHistory((h) => {
    $$("[data-act=prev-view]").forEach((b) => (b.disabled = !h.canBack));
    $$("[data-act=next-view]").forEach((b) => (b.disabled = !h.canForward));
  });

  // locate
  $$("[data-act=locate]").forEach((b) =>
    b.addEventListener("click", () => {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition(
        (p) => engine.setCenter(p.coords.longitude, p.coords.latitude, Math.max(engine.gmap.getZoom(), 13)),
        () => {}
      );
    })
  );

  // status bar
  engine.onCursor((lat, lng, elev) => {
    status.setCursor(lat, lng);
    if (elev !== undefined) status.setElevation(elev);
  });
  engine.onZoom((z) => status.setZoom(z));
  status.setZoom(engine.gmap.getZoom());
}
