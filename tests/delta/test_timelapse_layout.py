"""Delta timelapse block layout: the Year and Speed sliders line up with the
row's opacity slider, the buttons sit beside or above them, nothing is cut
off at any left-pane width, and the Cumulative chip.

Offline: the shell stub (no Earth Engine) with a timelapse row built from the
store, as Python's Map.addTimeLapse would leave it once loaded.
"""
import pytest

SHELL = {"delta-test": "shell"}
NAME = "LCMS Land Cover"
LEFT_MIN, LEFT_DEFAULT, LEFT_MAX = 240, 500, 750

SETUP = """() => {
  const { api, store } = __delta;
  api.addLayer({}, {}, "SRTM");
  api.addTimeLapse({}, {}, "%s");
  const years = ["2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023"];
  store.update((s) => ({ ...s, layers: s.layers.map((l) => l.kind !== "timelapse" ? l : { ...l, visible: true,
    legend: { type: "ramp", palette: ["#b5651d", "#f7f7b5", "#1a9641"], labels: ["0", "9000"] },
    timelapse: { years, loaded: true, nLoaded: 9, frame: 3, fps: 1.5, playing: false, cumulative: false } }) }), "test");
}""" % NAME

MEASURE = """() => {
  const row = Array.from(document.querySelectorAll('#layer-list .layer.is-tl'))[0];
  const r = (el) => { const b = el.getBoundingClientRect(); return {left: b.left, right: b.right, top: b.top, bottom: b.bottom, width: b.width, height: b.height}; };
  const shown = (el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const name = row.querySelector('.lname');
  const chip = row.querySelector('[data-tl=cumulative]');
  const readout = row.querySelector('.tl-year');
  return {
    stack: row.classList.contains('stack'),
    pane: r(document.querySelector('#pane-left')),
    row: r(row),
    op: r(row.querySelector('input.op')),
    year: r(row.querySelector('input[data-tl=year]')),
    speed: r(row.querySelector('input[data-tl=speed]')),
    name: {cut: name.scrollWidth > name.clientWidth, rect: r(name)},
    chip: {cut: chip.scrollWidth > chip.clientWidth, rect: r(chip)},
    readout: {cut: readout.scrollWidth > readout.clientWidth, rect: r(readout)},
    buttons: Array.from(row.querySelectorAll('.tl button')).filter(shown).filter(b => !b.closest('.tl-frames')).map(b => ({tl: b.dataset.tl, rect: r(b)})),
    labels: Array.from(row.querySelectorAll('.tl-lbl')).filter(shown).map(l => ({text: l.textContent, cut: l.scrollWidth > l.clientWidth, rect: r(l)})),
  };
}"""


def settle(page, ms=60):
    page.evaluate("(ms) => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, ms))))", ms)


def set_left_width(page, w):
    page.evaluate("(w) => __delta.store.update(s => ({...s, panes: {...s.panes, left: {...s.panes.left, width: w}}}), 'test')", w)
    settle(page)


def open_page(delta_page, **kw):
    page = delta_page(SHELL, **kw)
    page.evaluate(SETUP)
    settle(page)
    return page


@pytest.fixture
def page(delta_page):
    return open_page(delta_page)


def at(page, w):
    set_left_width(page, w)
    m = page.evaluate(MEASURE)
    assert abs(m["pane"]["width"] - w) <= 1, (w, m["pane"])
    return m


def overlap(a, b):
    return a["left"] < b["right"] - 0.5 and b["left"] < a["right"] - 0.5 and a["top"] < b["bottom"] - 0.5 and b["top"] < a["bottom"] - 0.5


def check_aligned(w, m):
    op = m["op"]
    for k in ("year", "speed"):
        s = m[k]
        assert abs(s["width"] - op["width"]) <= 1, (w, k, s, op)
        assert abs(s["right"] - op["right"]) <= 1, (w, k, s, op)
        if m["stack"]:
            assert abs(s["left"] - op["left"]) <= 1, (w, k, s, op)


def check_not_clipped(w, m):
    assert not m["name"]["cut"], (w, m["name"])
    assert not m["chip"]["cut"], (w, m["chip"])
    assert not m["readout"]["cut"], (w, m["readout"])
    controls = [b["rect"] for b in m["buttons"]] + [m["readout"]["rect"]] + [l["rect"] for l in m["labels"]]
    for l in m["labels"]:
        assert not l["cut"], (w, l)
    # Everything sits inside the row (and so inside the pane), never past its edge.
    for c in controls + [m["year"], m["speed"]]:
        assert c["left"] >= m["row"]["left"] - 0.5 and c["right"] <= m["row"]["right"] + 0.5, (w, c, m["row"])
    sliders = [m["year"], m["speed"]]
    for i, a in enumerate(controls):
        for s in sliders:
            assert not overlap(a, s), (w, a, s)
        for b in controls[i + 1 :]:
            assert not overlap(a, b), (w, a, b)
    # the layer name keeps its line: no control rides over it
    for c in controls + sliders:
        assert not overlap(c, m["name"]["rect"]), (w, c, m["name"]["rect"])


def band(rects):
    return min(r["left"] for r in rects), max(r["right"] for r in rects), min(r["top"] for r in rects), max(r["bottom"] for r in rects)


@pytest.mark.parametrize("w", [LEFT_MIN, LEFT_DEFAULT, LEFT_MAX])
def test_sliders_match_opacity_slider(page, w):
    m = at(page, w)
    # The three widths cover both opacity layouts: stacked at the minimum, inline at the default and maximum.
    assert m["stack"] is (w == LEFT_MIN), (w, m["stack"])
    check_aligned(w, m)
    check_not_clipped(w, m)
    # blocked CDN requests are expected offline; anything else is a page error
    assert [e for e in page.delta_errors if "Failed to load resource" not in e] == []


def test_every_width_aligned_and_unclipped(page):
    modes = set()
    for w in range(LEFT_MIN, LEFT_MAX + 1, 10):
        m = at(page, w)
        modes.add(m["stack"])
        check_aligned(w, m)
        check_not_clipped(w, m)
    assert modes == {True, False}


def test_buttons_beside_sliders_when_wide(page):
    m = at(page, LEFT_MAX)
    assert not m["stack"]
    left, right, top, bottom = band([b["rect"] for b in m["buttons"]] + [m["readout"]["rect"]])
    assert right < m["year"]["left"], (right, m["year"])
    # labels sit left of their sliders, after the buttons
    for l in m["labels"]:
        assert right <= l["rect"]["left"], (l, right)
    # side by side: the buttons and the sliders share a vertical band
    assert top < m["speed"]["bottom"] and m["year"]["top"] < bottom, (top, bottom, m["year"], m["speed"])


def test_sliders_under_buttons_when_narrow_inline(page):
    m = at(page, LEFT_DEFAULT)
    assert not m["stack"]
    _, _, _, bottom = band([b["rect"] for b in m["buttons"]] + [m["readout"]["rect"]])
    assert m["year"]["top"] > bottom and m["speed"]["top"] > bottom, (bottom, m["year"], m["speed"])


def test_stacked_buttons_then_sliders(page):
    m = at(page, LEFT_MIN)
    assert m["stack"]
    _, _, _, bottom = band([b["rect"] for b in m["buttons"]] + [m["readout"]["rect"]])
    assert m["year"]["top"] > bottom and m["speed"]["top"] > bottom
    assert m["year"]["top"] > m["op"]["bottom"]


def test_labels_and_no_year_value(page):
    at(page, LEFT_DEFAULT)
    row = "#layer-list .layer.is-tl"
    # the big readout is the year; the slider has no value of its own
    assert page.locator(row + " [data-tl=yearv]").count() == 0
    assert page.locator(row + " .tl-year").inner_text() == "2018"
    assert page.locator(row + " [data-tl=speedv]").inner_text() == "1.5 fps"
    m = page.evaluate(MEASURE)
    labels = {l["text"]: l["rect"] for l in m["labels"]}
    assert set(labels) == {"Year", "1.5 fps"}
    # immediately left of their slider, on its line
    for text, s in (("Year", m["year"]), ("1.5 fps", m["speed"])):
        lr = labels[text]
        assert lr["right"] <= s["left"] and s["left"] - lr["right"] <= 10, (text, lr, s)
        assert lr["top"] < s["bottom"] and s["top"] < lr["bottom"], (text, lr, s)
    # the speed label follows the slider without moving it
    before = page.evaluate(MEASURE)["speed"]
    page.locator(row + " input[data-tl=speed]").fill("3")
    assert page.locator(row + " [data-tl=speedv]").inner_text() == "3.0 fps"
    after = page.evaluate(MEASURE)["speed"]
    assert abs(after["left"] - before["left"]) < 0.5 and abs(after["width"] - before["width"]) < 0.5


def test_cumulative_chip(page):
    at(page, LEFT_DEFAULT)
    chip = page.locator("#layer-list .layer.is-tl [data-tl=cumulative]")
    assert chip.inner_text().strip() == "Cumulative"
    assert chip.get_attribute("title") == "Show every year up to this one stacked together"
    assert chip.get_attribute("aria-label") == "Cumulative"
    assert chip.get_attribute("aria-pressed") == "false"
    assert chip.locator("svg").count() == 2  # one icon per state; CSS shows one
    off = page.evaluate("(s) => getComputedStyle(document.querySelector(s)).backgroundColor", "#layer-list .layer.is-tl [data-tl=cumulative]")
    page.evaluate("() => __delta.store.update(s => ({...s, layers: s.layers.map(l => l.kind === 'timelapse' ? {...l, timelapse: {...l.timelapse, cumulative: true}} : l)}), 'test')")
    assert chip.get_attribute("aria-pressed") == "true"
    assert "on" in chip.get_attribute("class")
    # on: the same accent fill as the play button when it is on
    js = """() => {
      const b = document.querySelector('#layer-list .layer.is-tl [data-tl=play]');
      b.classList.add('on');
      const c = document.querySelector('#layer-list .layer.is-tl [data-tl=cumulative]');
      const out = [getComputedStyle(c).backgroundColor, getComputedStyle(b).backgroundColor];
      b.classList.remove('on');
      return out;
    }"""
    on, play_on = page.evaluate(js)
    assert on == play_on and on != off, (on, play_on, off)
    # very narrow rows: the chip may go icon only but never wraps mid-word
    set_left_width(page, LEFT_MIN)
    h = page.evaluate("(s) => { const c = document.querySelector(s); return [c.getBoundingClientRect().height, Array.from(c.querySelectorAll('svg')).find(v => v.getClientRects().length).getBoundingClientRect().height]; }", "#layer-list .layer.is-tl [data-tl=cumulative]")
    assert h[0] < 2 * max(h[1], 14), h



ICON = """(s) => {
  const c = document.querySelector(s);
  const shown = Array.from(c.querySelectorAll('svg')).filter(v => v.getClientRects().length > 0);
  return shown.map(v => ({state: v.dataset.state, w: v.getBoundingClientRect().width, h: v.getBoundingClientRect().height,
    joined: !!v.querySelector('path[d="M4 12h12"]'), stroke: v.getAttribute('stroke'), fill: v.getAttribute('fill')}));
}"""
CHIP = "#layer-list .layer.is-tl [data-tl=cumulative]"


def set_cumulative(page, on):
    page.evaluate("(on) => __delta.store.update(s => ({...s, layers: s.layers.map(l => l.kind === 'timelapse' ? {...l, timelapse: {...l.timelapse, cumulative: on}} : l)}), 'test')", on)


@pytest.mark.parametrize("scheme", ["dark", "light"])
@pytest.mark.parametrize("w", [LEFT_DEFAULT, LEFT_MIN])
def test_cumulative_icon_switches_with_state(delta_page, scheme, w):
    page = open_page(delta_page, color_scheme=scheme)
    set_left_width(page, w)
    # icon only in the narrowest rows, word plus icon otherwise
    assert page.locator(CHIP + " span").is_visible() is (w != LEFT_MIN)
    off = page.evaluate(ICON, CHIP)
    assert [i["state"] for i in off] == ["off"] and not off[0]["joined"], off
    assert abs(off[0]["w"] - 16) <= 0.5 and abs(off[0]["h"] - 16) <= 0.5, off
    assert off[0]["stroke"] == "currentColor" and off[0]["fill"] == "none", off
    set_cumulative(page, True)
    assert page.get_attribute(CHIP, "aria-pressed") == "true"
    on = page.evaluate(ICON, CHIP)
    assert [i["state"] for i in on] == ["on"] and on[0]["joined"], on
    set_cumulative(page, False)
    assert [i["state"] for i in page.evaluate(ICON, CHIP)] == ["off"]
