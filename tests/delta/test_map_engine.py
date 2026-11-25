"""Delta map engine: Google map, Earth Engine init, basemaps, history, search, Street View.

Needs Earth Engine, the local eeCreds proxy and a network, so every test is
marked live (deselect with -m "not live"). The pure helpers run without them.
"""
import pytest

pytestmark = pytest.mark.live

CENTER = (-111.6, 40.6, 11)


def build(Map):
    Map.setCenter(*CENTER)


@pytest.fixture
def page(live_map):
    return live_map(build)


def view(page):
    return page.evaluate(
        "(() => { const m = __delta.engine.gmap; const c = m.getCenter();"
        " return {lng: c.lng(), lat: c.lat(), zoom: m.getZoom()}; })()"
    )


def go(page, lng, lat, zoom=None):
    """Move the map and wait until it has gone idle at the new view."""
    page.evaluate(
        """([lng, lat, zoom]) => new Promise((res) => {
          const m = __delta.engine.gmap;
          google.maps.event.addListenerOnce(m, 'idle', () => setTimeout(res, 50));
          m.setCenter({lat, lng});
          if (zoom !== null) m.setZoom(zoom);
        })""",
        [lng, lat, zoom],
    )


def settle(page):
    """Wait for the map to go idle after a move; fail (not hang) if it never moves."""
    ok = page.evaluate(
        "new Promise((res) => { google.maps.event.addListenerOnce(__delta.engine.gmap, 'idle', () => setTimeout(() => res(true), 50)); setTimeout(() => res(false), 10000); })"
    )
    assert ok, "the map never went idle (no move): history %s" % page.evaluate("JSON.stringify(__delta.engine.history())")


def test_ee_initialized(page):
    # this map has no Earth Engine layers: Earth Engine loads when asked
    assert page.evaluate("__delta.eeLoader.isReady()") is False
    page.evaluate("__delta.eeLoader.ensure()")
    assert page.evaluate("__delta.eeLoader.isReady()") is True
    assert page.evaluate("ee.data.getAuthToken() !== null || !!authProxyAPIURL")
    # Neither of those tells success from failure: check the boot outcome and a round trip.
    assert page.evaluate("__delta.ready === true")
    assert page.evaluate("__delta.eeError") is None
    got = page.evaluate("new Promise((res) => ee.Number(1).add(1).evaluate((v, err) => res(err ? 'err:' + err : v)))")
    assert got == 2
    assert page.delta_errors == []


def test_set_center_and_zoom(page):
    v = view(page)
    assert abs(v["lng"] - CENTER[0]) < 1e-4
    assert abs(v["lat"] - CENTER[1]) < 1e-4
    assert v["zoom"] == 11


def click_settle(page, sel):
    """Click, and wait for the idle that move causes; listening starts before the
    click (a short move to a cached view can go idle before a later listener)."""
    # (a statement, not the promise: evaluate would wait for a returned promise)
    page.evaluate("() => { window.__idle = new Promise((res) => { google.maps.event.addListenerOnce(__delta.engine.gmap, 'idle', () => setTimeout(() => res(true), 50)); setTimeout(() => res(false), 10000); }); }")
    page.click(sel)
    assert page.evaluate("window.__idle"), "the map never went idle after " + sel


def test_elevation_is_read_at_30_m(page):
    """It read 1861 m everywhere near Salt Lake City: the mosaic was sampled at
    its 1 degree default. Downtown is about 1290 m, near Alta about 2940 m."""
    # elevation reads Earth Engine, loaded on a map without Earth Engine layers only when asked
    page.evaluate("__delta.eeLoader.ensure()")
    vals = page.evaluate(
        "Promise.all([[40.76, -111.9], [40.6, -111.6]].map(([lat, lng]) => __delta.engine.elevationAt({lat, lng})))"
    )
    assert 1200 < vals[0] < 1400 and 2700 < vals[1] < 3100, vals


def test_view_history(page):
    go(page, -111.2, 40.9)
    go(page, -110.9, 41.1)
    # Back and forward are the buttons the shell already ships.
    click_settle(page, "#pane-left [data-act=prev-view]")
    v = view(page)
    assert abs(v["lng"] + 111.2) < 1e-4 and abs(v["lat"] - 40.9) < 1e-4
    click_settle(page, "#pane-left [data-act=next-view]")
    v = view(page)
    assert abs(v["lng"] + 110.9) < 1e-4 and abs(v["lat"] - 41.1) < 1e-4
    # Repeated cycles keep working (no recorded echo of a programmatic move).
    for _ in range(2):
        click_settle(page, "#pane-left [data-act=prev-view]")
        v = view(page)
        assert abs(v["lng"] + 111.2) < 1e-4
        click_settle(page, "#pane-left [data-act=next-view]")
        v = view(page)
        assert abs(v["lng"] + 110.9) < 1e-4
        assert page.evaluate("__delta.engine.history().canForward") is False
    # A zoom change is its own history entry.
    go(page, -110.9, 41.1, 14)
    click_settle(page, "#pane-left [data-act=prev-view]")
    assert view(page)["zoom"] == 11
    click_settle(page, "#pane-left [data-act=next-view]")
    assert view(page)["zoom"] == 14
    click_settle(page, "#pane-left [data-act=prev-view]")
    # A new pan after going back drops the forward branch.
    click_settle(page, "#pane-left [data-act=prev-view]")
    go(page, -112.0, 40.0)
    assert page.evaluate("__delta.engine.history().canForward") is False
    click_settle(page, "#pane-left [data-act=prev-view]")
    v = view(page)
    assert abs(v["lng"] + 111.2) < 1e-4


def test_basemaps(page):
    # Basemaps carry no labels of their own; the labels overlay draws them above every layer.
    for key, type_id in (("map", "roadmap-base"), ("terrain", "terrain"), ("darkterrain", "terrain"), ("satellite", "satellite")):
        page.click("#mapctl .bm[data-bm=%s]" % key)
        assert page.evaluate("__delta.engine.gmap.getMapTypeId()") == type_id
        assert "on" in page.get_attribute("#mapctl .bm[data-bm=%s]" % key, "class").split()


def test_no_plain_dark_basemap(page):
    assert page.locator("#mapctl .bm[data-bm=dark]").count() == 0
    page.evaluate("__delta.engine.setBasemap('dark')")  # not a basemap: ignored
    assert page.evaluate("__delta.engine.basemap()") != "dark"
    assert page.evaluate("__delta.engine.gmap.mapTypes.get('dark') || null") is None


def test_labels_button_lines_up_with_the_basemap_tiles(page):
    # "Dark terrain" wraps to two lines; the Labels icon still sits level with the tiles
    tops = page.evaluate("[...document.querySelectorAll('#mapctl .bm i, #mapctl .bm-labels i')].map(i => i.getBoundingClientRect().top)")
    assert len(tops) == 5
    assert max(tops) - min(tops) < 0.5, tops


def test_street_view_round_trip(page):
    go(page, -111.8910, 40.7608, 17)
    page.click("#svBtn")
    assert page.evaluate("document.body.classList.contains('sv-pick')")
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_function("__delta.engine.gmap.getStreetView().getVisible()", timeout=20000)
    assert page.evaluate("document.body.classList.contains('sv')")
    assert not page.locator("#pane-left").is_visible()
    # The exit button of Google's panorama just hides it.
    page.evaluate("__delta.engine.gmap.getStreetView().setVisible(false)")
    page.wait_for_function("!document.body.classList.contains('sv')")
    assert page.locator("#pane-left").is_visible()
    assert not page.evaluate("document.body.classList.contains('sv-pick')")


def test_street_view_on_a_phone(page):
    page.set_viewport_size({"width": 390, "height": 844})
    go(page, -111.8910, 40.7608, 17)
    page.click("#svBtn")
    assert page.evaluate("document.body.classList.contains('sv-pick')")
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_function("__delta.engine.gmap.getStreetView().getVisible()", timeout=20000)
    page.evaluate("__delta.engine.gmap.getStreetView().setVisible(false)")
    page.wait_for_function("!document.body.classList.contains('sv')")
    page.set_viewport_size({"width": 1500, "height": 900})


def test_search_coordinates(page):
    box = page.locator("#pane-left [data-role=search]")
    box.fill("40.5, -111.9")
    box.press("Enter")
    settle(page)
    v = view(page)
    assert abs(v["lng"] + 111.9) < 1e-4 and abs(v["lat"] - 40.5) < 1e-4


def test_street_view_no_imagery_notice_and_stays_picking(page):
    # Open ocean: no panorama within 80 m.
    go(page, -150.0, 30.0, 8)
    page.click("#svBtn")
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_function("__delta.store.get().notices.some(n => n.includes('No Street View imagery'))", timeout=20000)
    assert page.evaluate("document.body.classList.contains('sv-pick')")


def arrows(page):
    return page.evaluate(
        "[...document.querySelectorAll('#pane-left [data-act=prev-view], #pane-left [data-act=next-view]')]"
        ".map(b => ({act: b.dataset.act, disabled: b.disabled, opacity: Number(getComputedStyle(b).opacity)}))"
    )


def test_history_arrows_look_inactive_at_either_end(page):
    """Forward is inactive until the user has gone back; back is inactive at
    the first view recorded. Inactive shows (dimmed), not only refuses."""
    page.wait_for_function("__delta.engine.history().length === 1")  # recording starts once the map has loaded
    # at load: the first view is the one the map script set, so neither arrow
    # has anywhere to go (the page's default view before it is not recorded)
    prev, nxt = arrows(page)
    assert prev["disabled"] and prev["opacity"] < 0.5, prev
    assert nxt["disabled"] and nxt["opacity"] < 0.5, nxt
    go(page, -111.2, 40.9)
    prev, nxt = arrows(page)
    assert not prev["disabled"] and prev["opacity"] == 1 and nxt["disabled"], (prev, nxt)
    click_settle(page, "#pane-left [data-act=prev-view]")
    prev, nxt = arrows(page)
    assert prev["disabled"] and prev["opacity"] < 0.5, prev  # the first view
    assert not nxt["disabled"] and nxt["opacity"] == 1, nxt
    v = view(page)
    assert abs(v["lng"] - CENTER[0]) < 1e-4 and abs(v["lat"] - CENTER[1]) < 1e-4 and v["zoom"] == CENTER[2], v


def test_locate_marks_your_location(live_map):
    page = live_map(build, setup=lambda ctx: (ctx.grant_permissions(["geolocation"]), ctx.set_geolocation({"latitude": 40.76, "longitude": -111.89, "accuracy": 120})))
    page.click("#pane-left [data-act=locate]")
    page.wait_for_function("__delta.engine.location() !== null", timeout=15000)
    loc = page.evaluate("__delta.engine.location()")
    assert abs(loc["lat"] - 40.76) < 1e-6 and abs(loc["lng"] + 111.89) < 1e-6 and loc["accuracy"] == 120
    v = view(page)
    assert abs(v["lat"] - 40.76) < 1e-3 and v["zoom"] >= 13
    assert page.delta_errors == []
