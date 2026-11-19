"""Delta Distance and Area tools.

Click the map to add vertices, double-click to finish; the card shows the
measured value in the units the Units switch holds. Live: it needs the map
engine (Google Maps) and the local eeCreds proxy.
"""
import math
import time

import pytest

pytestmark = pytest.mark.live

CX, CY = 750, 450
LINE = [(-150, 0), (0, -60), (150, 40)]
POLY = [(-120, -80), (100, -90), (150, 20), (0, 110), (-130, 60)]


def build(Map):
    Map.setCenter(-111.9, 40.7, 10)


@pytest.fixture
def page(live_map):
    return live_map(build, wait_layers=False)


def wait_for(page, js, arg=None, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.2)
    raise AssertionError("timed out waiting for: " + js + " " + repr(page.delta_errors))


def draw(page, pts):
    for dx, dy in pts[:-1]:
        page.mouse.click(CX + dx, CY + dy)
        time.sleep(0.35)
    page.mouse.dblclick(CX + pts[-1][0], CY + pts[-1][1])
    wait_for(page, "__delta.store.get().results.length === 1")


def card_text(page):
    return page.evaluate("[...document.querySelectorAll('#pane-right .card-r .val-big')].map(r => r.textContent)")


def expected(page, tool):
    """The card text computed in the page from the drawn vertices."""
    return page.evaluate(
        """async ([tool, units]) => {
          const u = await import('./delta/js/util.js');
          const m = await import('./delta/js/engine/measure.js');
          const path = __delta.measure.path();
          const sph = google.maps.geometry.spherical;
          if (tool === 'distance') return [['Distance', u.formatLength(sph.computeLength(path), units)], path.length];
          return [['Area', u.formatArea(sph.computeArea(path), units)], ['Perimeter', u.formatLength(sph.computeLength(path.concat([path[0]])), units)], path.length];
        }""",
        [tool, page.evaluate("__delta.store.get().units")],
    )


def vertices(page):
    return page.evaluate("__delta.measure.path().map(p => [p.lat(), p.lng()])")


def hav(a, b):
    R = 6378137
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def test_distance_three_point_line_both_units(page):
    page.evaluate("__delta.store.set({tool: 'distance'}, 'test')")
    draw(page, LINE)
    v = vertices(page)
    assert len(v) == 3
    meters = sum(hav(v[i], v[i + 1]) for i in range(2))
    exp = expected(page, "distance")
    assert card_text(page) == [exp[0][0] + exp[0][1]]
    km = float(exp[0][1].split()[0].replace(",", ""))
    assert abs(km * 1000 - meters) / meters < 0.01
    page.click("#pane-right .units [data-u=imperial]")
    wait_for(page, "document.querySelector('#pane-right .card-r .val-main').textContent.endsWith(' mi') || document.querySelector('#pane-right .card-r .val-main').textContent.endsWith(' ft')")
    exp = expected(page, "distance")
    assert card_text(page) == [exp[0][0] + exp[0][1]]
    assert page.evaluate("document.querySelector('#pane-right .card-r .val-main').classList.contains('mono')")
    assert page.delta_errors == []


def test_area_five_point_polygon_with_perimeter(page):
    page.evaluate("__delta.store.set({tool: 'area'}, 'test')")
    draw(page, POLY)
    assert len(vertices(page)) == 5
    for units in ("metric", "imperial"):
        page.click("#pane-right .units [data-u=%s]" % units)
        time.sleep(0.5)
        exp = expected(page, "area")
        assert card_text(page) == [exp[0][0] + exp[0][1], exp[1][0] + exp[1][1]]
    assert page.delta_errors == []


def test_live_readout_clear_and_tool_switch(page):
    page.evaluate("__delta.store.set({tool: 'distance'}, 'test')")
    page.mouse.click(CX - 100, CY)
    time.sleep(0.4)
    page.mouse.move(CX + 100, CY + 20, steps=5)
    wait_for(page, "__delta.store.get().results.length === 1")
    assert card_text(page)  # a readout while drawing
    page.mouse.dblclick(CX + 100, CY + 20)
    wait_for(page, "__delta.store.get().results[0].meta === '2 points'")
    page.click("#pane-right .card-r [data-act=clear]")
    wait_for(page, "__delta.store.get().results.length === 0 && __delta.measure.path().length === 0")
    draw(page, LINE)
    page.evaluate("__delta.store.set({tool: 'area'}, 'test')")
    wait_for(page, "__delta.store.get().results.length === 0 && __delta.measure.path().length === 0")
    assert page.delta_errors == []


def test_crosshair_survives_switch_from_measure_to_chart_draw(page):
    cursor = "__delta.engine.gmap.get('draggableCursor')"
    page.evaluate("__delta.store.set({tool: 'distance'}, 'test')")
    assert page.evaluate(cursor) == "crosshair"
    page.evaluate("__delta.store.set({tool: 'chart', areaFrom: 'draw'}, 'test')")
    assert page.evaluate(cursor) == "crosshair"
    page.evaluate("__delta.store.set({areaFrom: 'view'}, 'test')")
    assert not page.evaluate(cursor)
    assert page.delta_errors == []


def test_escape_cancels_a_measurement(page):
    page.evaluate("__delta.store.set({tool: 'area'}, 'test')")
    page.mouse.click(CX - 100, CY)
    time.sleep(0.4)
    page.mouse.click(CX + 100, CY)
    time.sleep(0.4)
    page.keyboard.press("Escape")
    wait_for(page, "__delta.store.get().results.length === 0 && __delta.measure.path().length === 0")
