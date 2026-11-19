// Delta shell: pane layout, resize grips, hamburger, theme, tool strip, phone sheets.
// The static markup lives in delta.html; this module only wires it to the store.

const LEFT_MIN = 240;
const RIGHT_MIN = 280;
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

// Initial store patch from the url and local storage; call before mountShell.
export function initialShellState(store) {
  const panes = store.get().panes;
  return {
    theme: readStoredTheme(),
    panes: {
      left: { ...panes.left, visible: readShowSidebar(), width: readStoredWidth("left") },
      right: { ...panes.right, width: readStoredWidth("right") },
    },
  };
}

export function mountShell(store, { mapEl } = {}) {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const body = document.body;
  const root = document.documentElement;
  const sysDark = matchMedia("(prefers-color-scheme: dark)");
  const isPhone = () => matchMedia("(max-width: 760px)").matches;

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
  }
  store.on("change:panes", renderPanes);

  function setWidth(side, width) {
    store.update((s) => ({ ...s, panes: { ...s.panes, [side]: { ...s.panes[side], width } } }), "pane-width");
  }
  $$(".grip").forEach((grip) => {
    const side = grip.dataset.side;
    grip.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      grip.classList.add("drag");
      try {
        grip.setPointerCapture(e.pointerId);
      } catch (err) {
        /* synthetic events have no capturable pointer */
      }
      const move = (ev) => {
        const raw = side === "left" ? ev.clientX : innerWidth - ev.clientX;
        setWidth(side, clampWidth(side, raw, innerWidth));
      };
      const up = () => {
        grip.classList.remove("drag");
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", up);
        grip.removeEventListener("pointercancel", up);
        lsSet("delta-" + side, store.get().panes[side].width);
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", up);
      grip.addEventListener("pointercancel", up);
    });
    grip.addEventListener("dblclick", () => {
      setWidth(side, null);
      lsSet("delta-" + side, null);
    });
  });

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
    b.addEventListener("click", () => store.set({ tool: store.get().tool === b.dataset.tool ? null : b.dataset.tool }, "tool-button"))
  );

  // ---- phones: one bottom sheet at a time ----
  function openSheet(name) {
    const was = body.classList.contains("m-" + name);
    body.classList.remove("m-layers", "m-tools", "m-full");
    if (!was) body.classList.add("m-" + name);
    $$("#mtabs [data-m]").forEach((b) => b.classList.toggle("on", body.classList.contains("m-" + b.dataset.m)));
  }
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
  return { setStreetView, openSheet, mapEl: mapEl || null };
}
