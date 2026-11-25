// Map chrome wiring: zoom, full screen, Street View pick, basemaps, view history.
// The engine does the map work; this module only connects buttons and body
// classes to it.

export function mountMapControls(engine, shell, status, notify = () => {}) {
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

  // map labels on or off (the labels overlay drawn above every layer)
  const labelsBtn = $("#labelsBtn");
  if (labelsBtn && engine.setLabels) {
    const showLabels = (on) => labelsBtn.setAttribute("aria-pressed", String(!!on));
    showLabels(engine.labelsOn());
    labelsBtn.addEventListener("click", () => engine.setLabels(!engine.labelsOn()));
    engine.onLabels(showLabels);
  }

  // Street View
  // A click toggles pick mode (coverage, then click the map); a drag carries
  // the man onto the map, as on Google's own map, and drops him where to look.
  const svBtn = $("#svBtn");
  let drag = null; // {x, y, id, moved, ghost}
  let swallowClick = false;
  svBtn.addEventListener("click", () => {
    if (swallowClick) {
      swallowClick = false;
      return;
    }
    engine.streetViewPick(!engine.isPicking());
  });
  svBtn.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY, id: e.pointerId, moved: false, ghost: null };
    try {
      svBtn.setPointerCapture(e.pointerId);
    } catch (err) {
      /* a synthetic pointer */
    }
  });
  svBtn.addEventListener("pointermove", (e) => {
    if (!drag) return;
    if (!drag.moved && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 5) return;
    if (!drag.moved) {
      drag.moved = true;
      engine.streetViewPick(true);
      drag.ghost = document.createElement("div");
      drag.ghost.className = "sv-ghost";
      drag.ghost.innerHTML = '<i class="ti ti-walk"></i>';
      document.body.appendChild(drag.ghost);
    }
    drag.ghost.style.left = e.clientX + "px";
    drag.ghost.style.top = e.clientY + "px";
  });
  const endDrag = (e, cancelled) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (!d.moved) return; // a click: the click handler toggles
    swallowClick = true;
    setTimeout(() => (swallowClick = false), 0);
    d.ghost.remove();
    const over = !cancelled && document.elementFromPoint(e.clientX, e.clientY);
    const onMap = over && $("#map").contains(over) && !over.closest(".mapctl");
    if (!onMap || !engine.streetViewAtPixel(e.clientX, e.clientY)) engine.streetViewPick(false);
  };
  svBtn.addEventListener("pointerup", (e) => endDrag(e, false));
  svBtn.addEventListener("pointercancel", (e) => endDrag(e, true));
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
      if (!navigator.geolocation) return notify("This browser cannot share your location.");
      b.classList.add("busy");
      navigator.geolocation.getCurrentPosition(
        (p) => {
          b.classList.remove("busy");
          engine.showLocation(p.coords.latitude, p.coords.longitude, p.coords.accuracy);
          engine.setCenter(p.coords.longitude, p.coords.latitude, Math.max(engine.gmap.getZoom(), 13));
        },
        (err) => {
          b.classList.remove("busy");
          const why = err && err.code === 1 ? "Location access is blocked for this page. Allow it in the browser's site settings to use Locate." : "Your location could not be found.";
          notify(why);
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
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
