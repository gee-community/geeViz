"""Delta timelapses: frames per year, play, pause, step, speed, cumulative,
off folds and pauses, toggle while loading, and turnOffLayersWhenTimeLapseIsOn.

Needs Earth Engine, the local eeCreds proxy and a network: every test is live.
"""
import re
import time

import pytest

pytestmark = pytest.mark.live

# Verified against the live catalog (2026-11-18).
LCMS = "projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11"
NDVI = "MODIS/061/MOD13A2"
YEARS = [str(y) for y in range(2015, 2024)]


def build(Map, turn_off=True):
    import geeViz.geeView as gv

    ee = gv.ee
    if turn_off is not None:  # None: leave it to the skin
        Map.turnOffLayersWhenTimeLapseIsOn = turn_off
    Map.addLayer(ee.Image("USGS/SRTMGL1_003"), {"min": 0, "max": 3000}, "SRTM")
    lcms = (
        ee.ImageCollection(LCMS)
        .filter('study_area=="CONUS"')
        .filter(ee.Filter.calendarRange(2015, 2023, "year"))
        .select(["Land_Cover"])
    )
    Map.addTimeLapse(lcms, {"autoViz": True}, "LCMS TL")
    ndvi = ee.ImageCollection(NDVI).filterDate("2018-01-01", "2021-01-01").select(["NDVI"])
    # visible=True is ignored: timelapses start off, as the original.
    Map.addTimeLapse(ndvi, {"min": 0, "max": 9000, "palette": ["b5651d", "f7f7b5", "1a9641"]}, "NDVI TL", True)
    Map.addLayer(ee.Image("USGS/SRTMGL1_003"), {"min": 1000, "max": 4000}, "SRTM top")
    Map.setCenter(-111.6, 40.6, 9)


def layer(page, name):
    return page.evaluate("(n) => __delta.store.get().layers.find(l => l.name === n)", name)


def row_sel(page, name):
    return '#layer-list .layer[data-id="%s"]' % layer(page, name)["id"]


def frames(page, name):
    return page.evaluate("(id) => __delta.engine.layers.stats(id).frames", layer(page, name)["id"])


def shown_years(page, name):
    years = layer(page, name)["timelapse"]["years"]
    return [years[i] for i, f in enumerate(frames(page, name)) if f["onMap"] and f["opacity"] > 0]


def wait_for(page, js, arg=None, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for " + js)


def wait_tl_loaded(page, name):
    wait_for(page, "(n) => { const l = __delta.store.get().layers.find(x => x.name === n); return l && l.timelapse && l.timelapse.loaded; }", name)


@pytest.fixture
def page(live_map):
    p = live_map(lambda M: build(M, turn_off=False))
    wait_tl_loaded(p, "LCMS TL")
    wait_tl_loaded(p, "NDVI TL")
    # Timelapses start off whatever Python's visible says.
    assert layer(p, "LCMS TL")["visible"] is False and layer(p, "NDVI TL")["visible"] is False
    assert not any(f["onMap"] for f in frames(p, "NDVI TL"))
    p.click(row_sel(p, "LCMS TL") + " .tgl")
    return p


def test_frames_and_years(page):
    tl = layer(page, "LCMS TL")["timelapse"]
    assert tl["years"] == YEARS
    f = frames(page, "LCMS TL")
    assert len(f) == 9
    assert all(x["onMap"] for x in f), f
    assert shown_years(page, "LCMS TL") == ["2015"]
    # The nine frame overlays are contiguous in overlayMapTypes and sit in
    # list order between their neighbors (SRTM below, SRTM top above).
    z = page.evaluate("__delta.engine.layers.zOrder()")
    ids = {n: layer(page, n)["id"] for n in ("SRTM", "LCMS TL", "SRTM top")}
    assert z["tiles"] == [ids["SRTM"]] + [ids["LCMS TL"]] * 9 + [ids["SRTM top"]], z["tiles"]
    # Eleven layer overlays, then the labels overlay on top (test_labels.py).
    omt = page.evaluate("__delta.engine.gmap.overlayMapTypes.getArray().filter(o => o && o !== __delta.engine.labelsOverlay()).length")
    assert omt == 11
    assert page.evaluate("(a => a[a.length - 1] === __delta.engine.labelsOverlay())(__delta.engine.gmap.overlayMapTypes.getArray())")
    assert layer(page, "NDVI TL")["timelapse"]["years"] == ["2018", "2019", "2020"]
    sel = row_sel(page, "LCMS TL")
    assert page.locator(sel + " .tl").is_visible()
    assert page.locator(sel + " .tl-year").inner_text() == "2015"
    assert page.delta_errors == []


def test_play_pause_step_speed(page):
    sel = row_sel(page, "LCMS TL")
    page.locator(sel + " input[data-tl=speed]").fill("2")
    assert page.locator(sel + " [data-tl=speedv]").inner_text() == "2.0 fps"
    page.click(sel + " [data-tl=play]")
    f0 = layer(page, "LCMS TL")["timelapse"]["frame"]
    assert layer(page, "LCMS TL")["timelapse"]["playing"] is True
    assert page.locator("#yearbadge").is_visible()
    time.sleep(2.0)
    f1 = layer(page, "LCMS TL")["timelapse"]["frame"]
    assert 3 <= (f1 - f0) % 9 <= 5, (f0, f1)
    page.click(sel + " [data-tl=pause]")
    assert layer(page, "LCMS TL")["timelapse"]["playing"] is False
    assert not page.locator("#yearbadge").is_visible()
    f2 = layer(page, "LCMS TL")["timelapse"]["frame"]
    time.sleep(1.2)
    assert layer(page, "LCMS TL")["timelapse"]["frame"] == f2
    # step wraps both ways and the readout follows
    page.locator(sel + " input[data-tl=year]").fill("0")
    page.click(sel + " [data-tl=back]")
    assert layer(page, "LCMS TL")["timelapse"]["frame"] == 8
    assert page.locator(sel + " .tl-year").inner_text() == "2023"
    assert shown_years(page, "LCMS TL") == ["2023"]
    page.click(sel + " [data-tl=forward]")
    assert layer(page, "LCMS TL")["timelapse"]["frame"] == 0
    assert shown_years(page, "LCMS TL") == ["2015"]


def test_cumulative(page):
    sel = row_sel(page, "LCMS TL")
    page.locator(sel + " input[data-tl=year]").fill("3")
    assert shown_years(page, "LCMS TL") == ["2018"]
    chip = page.locator(sel + " [data-tl=cumulative]")
    assert chip.get_attribute("aria-label") == "Cumulative"
    assert chip.get_attribute("aria-pressed") == "false"
    page.click(sel + " [data-tl=cumulative]")
    assert layer(page, "LCMS TL")["timelapse"]["cumulative"] is True
    assert "on" in page.get_attribute(sel + " [data-tl=cumulative]", "class")
    assert chip.get_attribute("aria-pressed") == "true"
    assert shown_years(page, "LCMS TL") == ["2015", "2016", "2017", "2018"]
    page.click(sel + " [data-tl=cumulative]")
    assert shown_years(page, "LCMS TL") == ["2018"]
    assert chip.get_attribute("aria-pressed") == "false"


def test_off_folds_and_pauses(page):
    sel = row_sel(page, "LCMS TL")
    # the timelapse is on: its legend opened the first time
    assert page.locator(sel + " .legend").is_visible()
    page.click(sel + " [data-tl=play]")
    assert layer(page, "LCMS TL")["timelapse"]["playing"] is True
    page.click(sel + " .tgl")
    tl = layer(page, "LCMS TL")
    assert tl["visible"] is False and tl["timelapse"]["playing"] is False
    assert not page.locator(sel + " .tl").is_visible()
    assert not page.locator(sel + " .legend").is_visible()
    assert not any(f["onMap"] for f in frames(page, "LCMS TL"))
    assert not page.locator("#yearbadge").is_visible()
    page.click(sel + " .tgl")
    assert page.locator(sel + " .tl").is_visible()
    assert page.locator(sel + " .legend").is_visible()
    assert len(shown_years(page, "LCMS TL")) == 1


def test_toggle_during_load(live_map):
    held = []
    state = {"hold": True}

    def hold_maps(route):
        if state["hold"]:
            held.append(route)
        else:
            route.continue_()

    def setup(ctx):
        ctx.route(re.compile(r".*/maps(\?.*)?$"), hold_maps)

    def build_one(Map):
        import geeViz.geeView as gv

        ee = gv.ee
        lcms = (
            ee.ImageCollection(LCMS)
            .filter('study_area=="CONUS"')
            .filter(ee.Filter.calendarRange(2015, 2023, "year"))
            .select(["Land_Cover"])
        )
        Map.addTimeLapse(lcms, {"autoViz": True}, "LCMS TL")
        Map.setCenter(-111.6, 40.6, 9)

    page = live_map(build_one, setup=setup, wait_layers=False)
    wait_for(page, "() => { const l = __delta.store.get().layers[0]; return l && l.timelapse.years && l.timelapse.years.length === 9; }")
    deadline = time.time() + 60
    while len(held) < 9 and time.time() < deadline:
        page.wait_for_timeout(250)
    assert len(held) == 9, len(held)
    sel = row_sel(page, "LCMS TL")
    # The toggle works while loading and records the choice: on, then off.
    assert layer(page, "LCMS TL")["timelapse"]["loaded"] is False
    assert layer(page, "LCMS TL")["visible"] is False
    assert layer(page, "LCMS TL")["loading"] is False, "an off timelapse does not report loading"
    page.click(sel + " .tgl")
    assert layer(page, "LCMS TL")["visible"] is True
    assert layer(page, "LCMS TL")["loading"] is True
    page.click(sel + " .tgl")
    assert layer(page, "LCMS TL")["visible"] is False
    assert layer(page, "LCMS TL")["loading"] is False
    state["hold"] = False
    for r in held:
        r.continue_()
    wait_tl_loaded(page, "LCMS TL")
    page.wait_for_timeout(500)
    assert layer(page, "LCMS TL")["visible"] is False
    assert not any(f["onMap"] for f in frames(page, "LCMS TL"))
    # Turning it on after load shows the first frame.
    page.click(sel + " .tgl")
    assert shown_years(page, "LCMS TL") == ["2015"]


def test_turn_off_layers_when_timelapse_on(live_map):
    page = live_map(lambda M: build(M, turn_off=True))
    wait_tl_loaded(page, "LCMS TL")
    wait_tl_loaded(page, "NDVI TL")
    assert layer(page, "SRTM")["visible"] is True
    page.click(row_sel(page, "LCMS TL") + " .tgl")
    assert layer(page, "LCMS TL")["visible"] is True
    assert layer(page, "SRTM")["visible"] is False
    assert layer(page, "SRTM top")["visible"] is False
    page.click(row_sel(page, "NDVI TL") + " .tgl")
    assert layer(page, "NDVI TL")["visible"] is True
    # Only one timelapse at a time, as the original.
    assert layer(page, "LCMS TL")["visible"] is False
    assert shown_years(page, "NDVI TL") == ["2018"]
    # The other direction: turning a layer on while the timelapse plays turns
    # the timelapse off, and the layer stays on through what would be ticks.
    sel = row_sel(page, "NDVI TL")
    page.locator(sel + " input[data-tl=speed]").fill("3")
    page.click(sel + " [data-tl=play]")
    assert layer(page, "NDVI TL")["timelapse"]["playing"] is True
    page.click(row_sel(page, "SRTM") + " .tgl")
    time.sleep(1.5)
    assert layer(page, "SRTM")["visible"] is True
    assert layer(page, "NDVI TL")["visible"] is False
    assert layer(page, "NDVI TL")["timelapse"]["playing"] is False
    assert not any(f["onMap"] for f in frames(page, "NDVI TL"))

    page2 = live_map(lambda M: build(M, turn_off=False))
    wait_tl_loaded(page2, "NDVI TL")
    page2.click(row_sel(page2, "NDVI TL") + " .tgl")
    assert layer(page2, "NDVI TL")["visible"] is True
    assert layer(page2, "SRTM")["visible"] is True


def test_unset_keeps_other_layers_on_and_stacks_in_list_order(live_map):
    """Delta's default: a timelapse turned on leaves the other layers on, and
    its frames take its place in the list order (below the layer listed above
    it, above the one listed below)."""
    page = live_map(lambda M: build(M, turn_off=None))
    wait_tl_loaded(page, "NDVI TL")
    assert page.evaluate("__delta.store.get().turnOffLayersWhenTimeLapseIsOn") is False
    page.click(row_sel(page, "NDVI TL") + " .tgl")
    wait_for(page, "(id) => __delta.engine.layers.stats(id).frames.some(f => f.onMap)", layer(page, "NDVI TL")["id"])
    assert layer(page, "SRTM")["visible"] is True and layer(page, "SRTM top")["visible"] is True
    z = page.evaluate("__delta.engine.layers.zOrder().tiles")
    ids = {n: layer(page, n)["id"] for n in ("SRTM", "NDVI TL", "SRTM top")}
    first = lambda i: z.index(i)
    # list (top first): SRTM top, NDVI TL, LCMS TL, SRTM; the map stacks bottom to top
    assert first(ids["SRTM"]) < first(ids["NDVI TL"]) < first(ids["SRTM top"]), z
    assert not page.delta_errors, page.delta_errors


def test_controls_line_up_with_the_opacity_slider(page):
    """The frame and speed sliders share the opacity slider's left and right
    edges; the buttons sit inline to their left in one row, as tall as the two
    compact sliders together; the labels are right-justified; neither the block
    nor the legend reaches under the legend button."""
    page.evaluate("__delta.store.update(s => ({...s, panes: {...s.panes, left: {...s.panes.left, width: 560}}}), 'test')")
    sel = row_sel(page, "LCMS TL")
    if not layer(page, "LCMS TL")["visible"]:
        page.click(sel + " .tgl")
    wait_for(page, "(id) => __delta.store.get().layers.find(l => l.id === id).timelapse.loaded", layer(page, "LCMS TL")["id"])
    page.wait_for_timeout(300)
    m = page.evaluate(
        """(s) => { const row = document.querySelector(s); const r = (q) => row.querySelector(q).getBoundingClientRect();
          return {op: r('input.op'), year: r('input[data-tl=year]'), speed: r('input[data-tl=speed]'), btns: r('.tl-transport'),
                  sl: r('.tl-sl'), tl: r('.tl'), leg: r('.legbtn'), legend: r('.legend'), stack: row.classList.contains('stack'),
                  labels: [r('.tl-year').right, r('[data-tl=speedv]').right],
                  tops: [...row.querySelectorAll('.tl-transport .tlb')].filter(b => b.getClientRects().length).map(b => Math.round(b.getBoundingClientRect().top))}; }""",
        sel,
    )
    assert not m["stack"], m
    for k in ("year", "speed"):
        assert abs(m[k]["left"] - m["op"]["left"]) <= 1 and abs(m[k]["right"] - m["op"]["right"]) <= 1, (k, m[k], m["op"])
    assert m["btns"]["right"] <= m["sl"]["left"], m
    assert abs(m["btns"]["height"] - m["sl"]["height"]) <= 1 and abs(m["btns"]["top"] - m["sl"]["top"]) <= 1, m
    assert len(set(m["tops"])) == 1, m["tops"]  # one row
    assert abs(m["labels"][0] - m["labels"][1]) <= 1, m["labels"]  # right-justified
    assert m["tl"]["right"] <= m["leg"]["left"] + 1, (m["tl"], m["leg"])
    assert m["legend"]["right"] <= m["leg"]["left"] + 1, (m["legend"], m["leg"])


def test_step_buttons_show_a_press_and_are_24_px(page):
    """Back and forward have no lasting state, so a click flashes them
    (.pressed, the same look as while held); the buttons are 24 px."""
    sel = row_sel(page, "LCMS TL")
    if not layer(page, "LCMS TL")["visible"]:
        page.click(sel + " .tgl")
    wait_for(page, "(id) => __delta.store.get().layers.find(l => l.id === id).timelapse.loaded", layer(page, "LCMS TL")["id"])
    size = page.evaluate("(s) => { const b = document.querySelector(s + ' [data-tl=forward]').getBoundingClientRect(); return [b.width, b.height]; }", sel)
    assert size == [24, 24], size
    for act in ("forward", "back"):
        f0 = layer(page, "LCMS TL")["timelapse"]["frame"]
        got = page.evaluate(
            """([s, act]) => { const b = document.querySelector(s + ' [data-tl=' + act + ']'); const idle = getComputedStyle(b).backgroundColor;
                b.click(); return {pressed: b.classList.contains('pressed'), idle, now: getComputedStyle(b).backgroundColor}; }""",
            [sel, act],
        )
        assert got["pressed"] and got["now"] != got["idle"], (act, got)
        assert layer(page, "LCMS TL")["timelapse"]["frame"] != f0
        page.wait_for_timeout(400)
        assert not page.evaluate("([s, act]) => document.querySelector(s + ' [data-tl=' + act + ']').classList.contains('pressed')", [sel, act])


def test_phone_shows_the_year_once(page):
    """On a phone the floating player at the bottom carries the year, so the
    badge at the top stays hidden while playing."""
    sel = row_sel(page, "LCMS TL")
    if not layer(page, "LCMS TL")["visible"]:
        page.click(sel + " .tgl")
    wait_for(page, "(id) => __delta.store.get().layers.find(l => l.id === id).timelapse.loaded", layer(page, "LCMS TL")["id"])
    page.set_viewport_size({"width": 390, "height": 844})
    page.click("#mplayer [data-tl=play]")
    assert layer(page, "LCMS TL")["timelapse"]["playing"] is True
    assert page.locator("#mplayer .tl-year").is_visible()
    assert not page.locator("#yearbadge").is_visible()
    page.click("#mplayer [data-tl=play]")
