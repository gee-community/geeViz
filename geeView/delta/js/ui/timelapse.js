// Timelapse controls: the block inside a timelapse row (large year readout,
// back, pause, stop, play, forward, refresh, frames, the Cumulative chip, and
// the year and speed sliders, which line up with the row's opacity slider), the year badge on the map while a timelapse plays, and the
// phone's floating player.
//
// Ported from the approved mockup (docs/superpowers/specs/2026-11-18-delta-
// mockup.html: .tl, .yearbadge, .mplayer, setYear/step/play/pause) over the
// original's controls (4map-manager.js addTimeLapseToMap icon bar and
// sliders). The buttons call the engine's controller; the block reads
// layer.timelapse from the store. Years are written as text.

import { DEFAULT_FPS } from "../engine/timelapse.js";

// Speed slider range and step, as the original's speed slider.
export const SPEED = { min: 0.5, max: 3, step: 0.5 };

function paint(input) {
  const min = Number(input.min);
  const max = Number(input.max);
  const v = max > min ? ((Number(input.value) - min) / (max - min)) * 100 : 0;
  input.style.setProperty("--v", v + "%");
}

const fpsText = (fps) => Number(fps).toFixed(1) + " fps";

// The active timelapse: the topmost one that is on and loaded.
export function activeTimelapse(state) {
  const byId = new Map(state.layers.map((l) => [l.id, l]));
  for (const id of state.order) {
    const l = byId.get(id);
    if (l && l.kind === "timelapse" && l.visible && l.timelapse && l.timelapse.loaded) return l;
  }
  return null;
}

export function yearText(tl) {
  if (!tl || !tl.loaded) {
    if (tl && tl.years && tl.years.length) return "Loading " + (tl.nLoaded || 0) + "/" + tl.years.length;
    return "Loading";
  }
  return String(tl.years[tl.frame]);
}

export function timelapseBlock(id, getCtl) {
  const tpl = document.getElementById("tpl-timelapse");
  const el = tpl.content.firstElementChild.cloneNode(true);
  const q = (k) => el.querySelector(`[data-tl="${k}"]`);
  const parts = {
    year: el.querySelector(".tl-year"),
    play: q("play"),
    pause: q("pause"),
    cumulative: q("cumulative"),
    yearIn: q("year"),
    speedIn: q("speed"),
    speedV: q("speedv"),
    frames: el.querySelector(".tl-frames"),
  };
  parts.speedIn.min = String(SPEED.min);
  parts.speedIn.max = String(SPEED.max);
  parts.speedIn.step = String(SPEED.step);

  const ctl = () => getCtl(id);
  const call = (fn) => () => {
    const c = ctl();
    if (c) fn(c);
  };
  let last = {};
  q("back").addEventListener("click", call((c) => c.step(-1)));
  q("forward").addEventListener("click", call((c) => c.step(1)));
  parts.play.addEventListener("click", call((c) => c.play()));
  parts.pause.addEventListener("click", call((c) => c.pause()));
  q("stop").addEventListener("click", call((c) => c.stop()));
  q("refresh").addEventListener("click", call((c) => c.refresh()));
  parts.cumulative.addEventListener("click", call((c) => c.setCumulative(!last.cumulative)));
  // port of 4map-manager.js toggleFrames: the frame list the original keeps hidden
  q("frames").addEventListener("click", () => el.classList.toggle("frames-open"));
  parts.frames.addEventListener("click", (e) => {
    const b = e.target.closest("[data-frame]");
    const c = ctl();
    if (b && c) c.setFrame(Number(b.dataset.frame));
  });
  parts.yearIn.addEventListener("input", () => {
    paint(parts.yearIn);
    const c = ctl();
    if (c) c.setFrame(Number(parts.yearIn.value));
  });
  parts.speedIn.addEventListener("input", () => {
    paint(parts.speedIn);
    parts.speedV.textContent = fpsText(parts.speedIn.value);
    const c = ctl();
    if (c) c.setSpeed(Number(parts.speedIn.value));
  });

  function update(layer) {
    const tl = layer.timelapse || {};
    const years = tl.years || [];
    const loaded = !!tl.loaded;
    el.classList.toggle("loading", !loaded);
    el.querySelectorAll("button, input").forEach((b) => (b.disabled = !loaded && b.dataset.tl !== "refresh"));
    parts.year.textContent = yearText(tl);
    parts.play.classList.toggle("on", !!tl.playing);
    parts.play.setAttribute("aria-pressed", String(!!tl.playing));
    parts.pause.classList.toggle("on", loaded && !tl.playing);
    parts.cumulative.classList.toggle("on", !!tl.cumulative);
    parts.cumulative.setAttribute("aria-pressed", String(!!tl.cumulative));
    if (last.n !== years.length) {
      parts.yearIn.min = "0";
      parts.yearIn.max = String(Math.max(0, years.length - 1));
      parts.frames.replaceChildren(
        ...years.map((y, i) => {
          const b = document.createElement("button");
          b.type = "button";
          b.className = "tlf mono";
          b.dataset.frame = String(i);
          b.textContent = String(y);
          return b;
        })
      );
    }
    const frame = tl.frame || 0;
    if (Number(parts.yearIn.value) !== frame) parts.yearIn.value = String(frame);
    paint(parts.yearIn);
    const fps = tl.fps || DEFAULT_FPS;
    if (Number(parts.speedIn.value) !== fps) parts.speedIn.value = String(fps);
    paint(parts.speedIn);
    parts.speedV.textContent = fpsText(fps);
    parts.frames.querySelectorAll("[data-frame]").forEach((b) => b.classList.toggle("on", Number(b.dataset.frame) === frame));
    last = { n: years.length, cumulative: !!tl.cumulative };
  }

  return { el, update };
}

// Year badge (desktop and phone, while playing) and the phone's floating
// player (while a timelapse is on; CSS shows it on phones with no sheet open).
export function mountTimelapseHud(store, getCtl, { badge, player }) {
  const pYear = player.querySelector(".tl-year");
  const pPlay = player.querySelector('[data-tl="play"]');
  const act = () => activeTimelapse(store.get());
  const call = (fn) => () => {
    const l = act();
    const c = l && getCtl(l.id);
    if (c) fn(c, l);
  };
  player.querySelector('[data-tl="back"]').addEventListener("click", call((c) => c.step(-1)));
  player.querySelector('[data-tl="forward"]').addEventListener("click", call((c) => c.step(1)));
  pPlay.addEventListener("click", call((c, l) => (l.timelapse.playing ? c.pause() : c.play())));

  function render() {
    const l = act();
    const tl = l && l.timelapse;
    const playing = !!(tl && tl.playing);
    badge.hidden = !playing;
    document.body.classList.toggle("tl-on", !!l);
    document.body.classList.toggle("tl-playing", playing);
    if (!tl) return;
    const y = yearText(tl);
    if (badge.textContent !== y) badge.textContent = y;
    if (pYear.textContent !== y) pYear.textContent = y;
    pPlay.classList.toggle("on", playing);
    pPlay.setAttribute("aria-pressed", String(playing));
    const icon = pPlay.querySelector("i");
    icon.className = playing ? "ti ti-player-pause" : "ti ti-player-play";
    pPlay.title = playing ? "Pause" : "Play";
  }
  store.on("change:layers", render);
  store.on("change:order", render);
  render();
  return { render };
}
