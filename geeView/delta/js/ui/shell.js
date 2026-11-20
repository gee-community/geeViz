// Delta shell: pane layout, resize grips, hamburger, theme, tool strip, phone sheets.
// The static markup lives in delta.html; this module only wires it to the store.

const LEFT_MIN = 240;
// wide enough for the four tool tabs with their labels
const RIGHT_MIN = 330;
const LOGO = "./src/assets/images/geeviz-logo-";

function lsGet(key) {
  try {
    return localStorage.getItem(key);
  } catch (e) {
    return null;
  }
}
function lsSet(key, value) {
  try {
    if (value === null || value === undefined) localStorage.removeItem(key);
    else localStorage.setItem(key, String(value));
  } catch (e) {
    /* storage can be blocked */
  }
}

export function readStoredWidth(side) {
  const n = Number(lsGet("delta-" + side));
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function readStoredTheme() {
  const t = lsGet("delta-theme");
  return t === "light" || t === "dark" ? t : "system";
}

export function readShowSidebar(search = location.search) {
  return new URLSearchParams(search).get("showSidebar") !== "false";
}

export function clampWidth(side, w, windowWidth) {
  const min = side === "left" ? LEFT_MIN : RIGHT_MIN;
  return Math.round(Math.max(min, Math.min(windowWidth * 0.5, w)));
}

function clampStored(side) {
  const w = readStoredWidth(side);
  return w === null ? null : clampWidth(side, w, innerWidth);
}

// Initial store patch from the url and local storage; call before mountShell.
export function initialShellState(store) {
  const panes = store.get().panes;
  return {
    theme: readStoredTheme(),
    panes: {
      left: { ...panes.left, visible: readShowSidebar(), width: clampStored("left") },
      right: { ...panes.right, width: clampStored("right") },
    },
  };
}

export function mountShell(store, { mapEl } = {}) {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const body = document.body;
  const root = document.documentElement;
  const sysDark = matchMedia("(prefers-color-scheme: dark)");
  const phoneMq = matchMedia("(max-width: 760px)");
  const isPhone = () => phoneMq.matches;

  // A pane that is slid off-screen (hidden sidebar, closed phone sheet) must
  // also leave the tab order and the accessibility tree.
  function renderInert() {
    const phone = isPhone();
    const leftShown = phone ? body.classList.contains("m-layers") : store.get().panes.left.visible !== false;
    const rightShown = phone ? body.classList.contains("m-tools") || body.classList.contains("m-output") : true;
    [["#pane-left", leftShown], ["#pane-right", rightShown]].forEach(([sel, shown]) => {
      const el = $(sel);
      el.inert = !shown;
      if (shown) el.removeAttribute("aria-hidden");
      else el.setAttribute("aria-hidden", "true");
    });
  }
  phoneMq.addEventListener("change", renderInert);

  // ---- theme ----
  const effectiveTheme = () => {
    const t = store.get().theme;
    return t === "system" ? (sysDark.matches ? "dark" : "light") : t;
  };
  function renderTheme() {
    const eff = effectiveTheme();
    root.setAttribute("data-bs-theme", eff);
    const icon = $("#theme-btn i");
    if (icon) icon.className = "ti " + (eff === "dark" ? "ti-sun" : "ti-moon");
    $$(".logo-img").forEach((img) => (img.src = LOGO + (eff === "dark" ? "dark" : "light") + ".png"));
    $$("#mmenu [data-t]").forEach((b) => b.classList.toggle("on", b.dataset.t === store.get().theme));
  }
  store.on("change:theme", (t) => {
    lsSet("delta-theme", t === "system" ? null : t);
    renderTheme();
  });
  sysDark.addEventListener("change", () => {
    if (store.get().theme === "system") renderTheme();
  });
  $("#theme-btn").addEventListener("click", () => store.set({ theme: effectiveTheme() === "dark" ? "light" : "dark" }, "theme-button"));
  $$("#mmenu [data-t]").forEach((b) => b.addEventListener("click", () => store.set({ theme: b.dataset.t }, "theme-menu")));
  $("#mlogo-btn").addEventListener("click", (e) => {
    e.stopPropagation();
    body.classList.toggle("menu-open");
  });
  document.addEventListener("click", () => body.classList.remove("menu-open"));

  // ---- pane widths and visibility ----
  function renderPanes() {
    const { left, right } = store.get().panes;
    const set = (name, w) => (w ? root.style.setProperty(name, w + "px") : root.style.removeProperty(name));
    set("--lw", left.width);
    set("--rw", right.width);
    body.classList.toggle("left-hidden", left.visible === false);
    const url = new URL(location.href);
    if (left.visible === false) url.searchParams.set("showSidebar", "false");
    else url.searchParams.delete("showSidebar");
    if (url.href !== location.href) history.replaceState(null, "", url);
    renderInert();
  }
  store.on("change:panes", renderPanes);

  // Panes are as tall as their content (desktop). The status bar and the map
  // controls make room only for a pane that reaches down to them: left-reach and
  // right-reach when a pane's bottom gets to the status bar, right-over-ctl when
  // the right pane comes down into the band the map controls occupy.
  function measureReach() {
    const vh = innerHeight;
    const statusH = $("#status") ? $("#status").offsetHeight : 0;
    const bottomOf = (sel) => {
      const el = $(sel);
      if (!el || el.offsetParent === null) return 0;
      return el.getBoundingClientRect().bottom;
    };
    const ctl = $("#mapctl");
    const ctlTop = ctl ? vh - parseFloat(getComputedStyle(ctl).bottom || "0") - ctl.offsetHeight : vh;
    const lb = bottomOf("#pane-left");
    const rb = bottomOf("#pane-right");
    body.classList.toggle("left-reach", lb >= vh - statusH - 1);
    body.classList.toggle("right-reach", rb >= vh - statusH - 1);
    body.classList.toggle("right-over-ctl", rb > ctlTop - 8);
  }
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => requestAnimationFrame(measureReach));
    ["#pane-left", "#pane-right", "#mapctl"].forEach((sel) => $(sel) && ro.observe($(sel)));
  }
  addEventListener("resize", measureReach);
  measureReach();

  function setWidth(side, width) {
    store.update((s) => ({ ...s, panes: { ...s.panes, [side]: { ...s.panes[side], width } } }), "pane-width");
  }
  // Live width while dragging: only the elements that depend on it, never :root
  // (a custom property on :root restyles the whole page on every move).
  // The store, and so --lw/--rw on :root, takes the final width on release.
  const liveTargets = {
    left: { pane: "#pane-left", vars: ["#status", "#loadbar"], name: "--lw" },
    right: { pane: "#pane-right", vars: ["#status", "#loadbar", "#mapctl"], name: "--rw" },
  };
  function applyLive(side, w) {
    const t = liveTargets[side];
    const pane = $(t.pane);
    const vars = t.vars.map((sel) => $(sel)).filter(Boolean);
    if (w === null) {
      pane.style.removeProperty("width");
      vars.forEach((el) => el.style.removeProperty(t.name));
    } else {
      pane.style.width = w + "px";
      vars.forEach((el) => el.style.setProperty(t.name, w + "px"));
    }
  }

  // A drag always ends: pointer capture can fail or be lost (seen on the
  // running demo, with the map under the pointer), so the moves and the
  // release are heard on window (capture phase, before the map can stop them),
  // filtered by pointer id, and the drag also ends on lostpointercapture,
  // window blur, Escape, or a new pointerdown on a grip.
  let endDrag = null;
  // A press near a pane edge belongs to that edge's grip even when it lands a
  // few pixels out on the map: heard on window in the capture phase and
  // stopped there, so Google Maps never sees it and never starts a pan.
  const GRIP_SLOP = 6;
  function gripAt(x, y) {
    for (const grip of $$(".grip")) {
      if (grip.offsetParent === null) continue;
      const r = grip.getBoundingClientRect();
      if (r.width && x >= r.left - GRIP_SLOP && x <= r.right + GRIP_SLOP && y >= r.top && y <= r.bottom) return grip;
    }
    return null;
  }
  addEventListener(
    "pointerdown",
    (e) => {
      if (e.button !== 0 || e.pointerType === "touch") return;
      const grip = gripAt(e.clientX, e.clientY);
      if (!grip) return;
      e.stopPropagation();
      startDrag(grip, e);
    },
    { capture: true }
  );
  $$(".grip").forEach((grip) => {
    const side = grip.dataset.side;
    // touch presses, and any press the window listener did not claim (a
    // claimed press is stopped on window, so it never reaches the grip)
    grip.addEventListener("pointerdown", (e) => startDrag(grip, e));
    grip.addEventListener("dblclick", () => {
      setWidth(side, null);
      lsSet("delta-" + side, null);
    });
  });
  function startDrag(grip, e) {
    const side = grip.dataset.side;
    {
      e.preventDefault();
      if (endDrag) endDrag();
      const pid = e.pointerId;
      grip.classList.add("drag");
      body.classList.add("resizing");
      try {
        grip.setPointerCapture(pid);
      } catch (err) {
        /* synthetic events have no capturable pointer; window still hears the drag */
      }
      // One update per animation frame, from the latest pointer x.
      let latest = null;
      let raf = 0;
      // Relative to where the press landed, so grabbing a few pixels off the
      // edge does not make the pane jump to the pointer.
      const edgeOf = (x) => (side === "left" ? x : innerWidth - x);
      const paneEl = $("#pane-" + side);
      const offset = paneEl ? edgeOf(e.clientX) - paneEl.getBoundingClientRect().width : 0;
      const widthAt = (x) => clampWidth(side, Math.round(edgeOf(x) - offset), innerWidth);
      const frame = () => {
        raf = 0;
        if (latest !== null) applyLive(side, latest);
      };
      const move = (ev) => {
        if (ev.pointerId !== pid) return;
        // the map below never hears a resize drag
        ev.stopPropagation();
        latest = widthAt(ev.clientX);
        if (!raf) raf = requestAnimationFrame(frame);
      };
      const opts = { capture: true };
      const end = () => {
        if (endDrag !== end) return;
        endDrag = null;
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
        grip.classList.remove("drag");
        body.classList.remove("resizing");
        removeEventListener("pointermove", move, opts);
        removeEventListener("pointerup", onPointerEnd, opts);
        removeEventListener("pointercancel", onPointerEnd, opts);
        removeEventListener("blur", end);
        removeEventListener("keydown", onKey, opts);
        grip.removeEventListener("lostpointercapture", onPointerEnd);
        try {
          if (grip.hasPointerCapture && grip.hasPointerCapture(pid)) grip.releasePointerCapture(pid);
        } catch (err) {
          /* nothing to release */
        }
        if (latest !== null && latest !== store.get().panes[side].width) setWidth(side, latest);
        applyLive(side, null);
        lsSet("delta-" + side, store.get().panes[side].width);
      };
      const onPointerEnd = (ev) => {
        if (ev.pointerId !== pid) return;
        if (ev.type !== "lostpointercapture") ev.stopPropagation();
        end();
      };
      const onKey = (ev) => {
        if (ev.key === "Escape") end();
      };
      end.grip = grip;
      endDrag = end;
      addEventListener("pointermove", move, opts);
      addEventListener("pointerup", onPointerEnd, opts);
      addEventListener("pointercancel", onPointerEnd, opts);
      addEventListener("blur", end);
      addEventListener("keydown", onKey, opts);
      grip.addEventListener("lostpointercapture", onPointerEnd);
    }
  }

  // Stored or earlier widths can exceed the window after it shrinks: clamp what is shown.
  function reclamp() {
    const { left, right } = store.get().panes;
    const l = left.width ? clampWidth("left", left.width, innerWidth) : null;
    const r = right.width ? clampWidth("right", right.width, innerWidth) : null;
    if (l !== left.width) setWidth("left", l);
    if (r !== right.width) setWidth("right", r);
  }
  addEventListener("resize", reclamp);
  reclamp();

  const setLeftVisible = (visible) =>
    store.update((s) => ({ ...s, panes: { ...s.panes, left: { ...s.panes.left, visible } } }), "hamburger");
  $("#hamburger").addEventListener("click", () => setLeftVisible(false));
  $("#hamburger-float").addEventListener("click", () => setLeftVisible(true));

  // ---- title ----
  function renderTitle() {
    const el = $("#title");
    const t = store.get().title;
    if (t) el.textContent = t;
    else {
      el.textContent = "geeViz ";
      const b = document.createElement("b");
      b.textContent = "Delta";
      el.appendChild(b);
    }
  }
  store.on("change:title", renderTitle);

  // ---- tools: one active at a time, none folds the right pane ----
  function renderTool() {
    const tool = store.get().tool;
    body.classList.toggle("no-tool", !tool);
    $$("#pane-right .tool").forEach((b) => b.classList.toggle("on", b.dataset.tool === tool));
  }
  store.on("change:tool", renderTool);
  $$("#pane-right .tool").forEach((b) =>
    // Phones: the Tools sheet stays open on a pick (its settings are there);
    // the tab bar closes it.
    b.addEventListener("click", () => store.set({ tool: store.get().tool === b.dataset.tool ? null : b.dataset.tool }, "tool-button"))
  );

  // ---- phones: one bottom sheet at a time ----
  // Layers, Tools (the tool tabs and their settings) and Output (results).
  const SHEETS = ["layers", "tools", "output"];
  function openSheet(name) {
    const was = body.classList.contains("m-" + name);
    body.classList.remove(...SHEETS.map((n) => "m-" + n), "m-full");
    if (!was) body.classList.add("m-" + name);
    $$("#mtabs [data-m]").forEach((b) => b.classList.toggle("on", body.classList.contains("m-" + b.dataset.m)));
    if (name === "output" && !was) outputDot(false);
    renderInert();
  }
  function closeSheets() {
    SHEETS.forEach((n) => body.classList.contains("m-" + n) && openSheet(n));
  }
  // New output while the Output sheet is closed: a dot on its tab.
  function outputDot(on) {
    const d = $("#mtabs .mdot");
    if (d) d.hidden = !on;
  }
  store.on("change:results", (v) => {
    if (isPhone() && (v || []).length && !body.classList.contains("m-output")) outputDot(true);
    if (!(v || []).length) outputDot(false);
  });
  $$("#mtabs [data-m]").forEach((b) => b.addEventListener("click", () => openSheet(b.dataset.m)));
  $$(".pane").forEach((p) =>
    p.addEventListener("click", (e) => {
      if (isPhone() && e.clientY - p.getBoundingClientRect().top < 16) body.classList.toggle("m-full");
    })
  );

  // ---- street view: panes, controls, status and phone bars step aside ----
  function setStreetView(on) {
    body.classList.toggle("sv", !!on);
  }

  renderTheme();
  renderPanes();
  renderTitle();
  renderTool();
  return { setStreetView, openSheet, closeSheets, mapEl: mapEl || null };
}
