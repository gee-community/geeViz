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
    page.evaluate("new Promise((res) => google.maps.event.addListenerOnce(__delta.engine.gmap, 'idle', () => setTimeout(res, 50)))")


def test_ee_initialized(page):
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


def test_view_history(page):
    go(page, -111.2, 40.9)
    go(page, -110.9, 41.1)
    # Back and forward are the buttons the shell already ships.
    page.click("#pane-left [data-act=prev-view]")
    settle(page)
    v = view(page)
    assert abs(v["lng"] + 111.2) < 1e-4 and abs(v["lat"] - 40.9) < 1e-4
    page.click("#pane-left [data-act=next-view]")
    settle(page)
    v = view(page)
    assert abs(v["lng"] + 110.9) < 1e-4 and abs(v["lat"] - 41.1) < 1e-4
    # Repeated cycles keep working (no recorded echo of a programmatic move).
    for _ in range(2):
        page.click("#pane-left [data-act=prev-view]")
        settle(page)
        v = view(page)
        assert abs(v["lng"] + 111.2) < 1e-4
        page.click("#pane-left [data-act=next-view]")
        settle(page)
        v = view(page)
        assert abs(v["lng"] + 110.9) < 1e-4
        assert page.evaluate("__delta.engine.history().canForward") is False
    # A zoom change is its own history entry.
    go(page, -110.9, 41.1, 14)
    page.click("#pane-left [data-act=prev-view]")
    settle(page)
    assert view(page)["zoom"] == 11
    page.click("#pane-left [data-act=next-view]")
    settle(page)
    assert view(page)["zoom"] == 14
    page.click("#pane-left [data-act=prev-view]")
    settle(page)
    # A new pan after going back drops the forward branch.
    page.click("#pane-left [data-act=prev-view]")
    settle(page)
    go(page, -112.0, 40.0)
    assert page.evaluate("__delta.engine.history().canForward") is False
    page.click("#pane-left [data-act=prev-view]")
    settle(page)
    v = view(page)
    assert abs(v["lng"] + 111.2) < 1e-4


def test_basemaps(page):
    # Basemaps carry no labels of their own; the labels overlay draws them above every layer.
    for key, type_id in (("map", "roadmap-base"), ("terrain", "terrain"), ("dark", "dark"), ("satellite", "satellite")):
        page.click("#mapctl .bm[data-bm=%s]" % key)
        assert page.evaluate("__delta.engine.gmap.getMapTypeId()") == type_id
        assert "on" in page.get_attribute("#mapctl .bm[data-bm=%s]" % key, "class").split()


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
