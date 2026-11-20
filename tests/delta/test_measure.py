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
    # Chart area is offered only with a layer it can chart
    page.evaluate("Map.addLayer(ee.Image(1), {canAreaChart: true}, 'Chartable', false)")
    wait_for(page, "!document.querySelector('.tool[data-tool=chart]').hidden")
    page.evaluate("__delta.store.set({tool: 'distance'}, 'test')")
    assert page.evaluate(cursor) == "crosshair"
    page.evaluate("__delta.store.set({tool: 'chart', areaFrom: 'draw'}, 'test')")
    assert page.evaluate(cursor) == "crosshair"
    page.evaluate("__delta.store.set({areaFrom: 'view'}, 'test')")
    assert not page.evaluate(cursor)
    # Query shows the original's question mark
    page.evaluate("__delta.store.set({tool: 'query'}, 'test')")
    assert page.evaluate(cursor) == "help"
    assert page.delta_errors == []


def test_escape_cancels_a_measurement(page):
    page.evaluate("__delta.store.set({tool: 'area'}, 'test')")
    page.mouse.click(CX - 100, CY)
    time.sleep(0.4)
    page.mouse.click(CX + 100, CY)
    time.sleep(0.4)
    page.keyboard.press("Escape")
    wait_for(page, "__delta.store.get().results.length === 0 && __delta.measure.path().length === 0")


# ---- editing parity with the original (Task 11k part B) ----

def n_points(page):
    return page.evaluate("__delta.measure.paths().map(p => p.length)")


def test_ctrl_z_undoes_and_ctrl_shift_z_redoes_distance_points(page):
    page.evaluate("__delta.store.set({tool: 'distance'}, 'test')")
    for dx, dy in LINE:
        page.mouse.click(CX + dx, CY + dy)
        time.sleep(0.35)
    assert n_points(page) == [3]
    page.keyboard.press("Control+z")
    assert n_points(page) == [2]
    page.keyboard.press("Control+z")
    assert n_points(page) == [1]
    page.keyboard.press("Control+Shift+z")
    assert n_points(page) == [2]
    page.keyboard.press("Control+y")
    assert n_points(page) == [3]
    page.mouse.dblclick(CX + LINE[-1][0], CY + LINE[-1][1])
    wait_for(page, "__delta.store.get().results[0] && __delta.store.get().results[0].meta === '3 points'")
    # the buttons do the same, and say so
    assert page.get_attribute("#tool-options [data-sk=undo]", "title") == "Undo (Ctrl+Z)"
    page.click("#tool-options [data-sk=undo]")  # un-finish
    page.click("#tool-options [data-sk=undo]")
    assert n_points(page) == [2]
    page.click("#tool-options [data-sk=redo]")
    assert n_points(page) == [3]
    assert page.delta_errors == []


def test_area_second_polygon_after_double_click_and_total(page):
    page.evaluate("__delta.store.set({tool: 'area'}, 'test')")
    small = [(-200, -60), (-120, -60), (-120, 20)]
    other = [(80, -60), (200, -60), (200, 40), (80, 40)]
    draw(page, small)
    draw(page, other)
    assert n_points(page) == [3, 4]
    lines = page.evaluate("__delta.store.get().results[0].data.lines")
    assert [l[0] for l in lines] == ["Total area", "Polygon 1", "Polygon 2"]
    exp = page.evaluate(
        """async (units) => { const u = await import('./delta/js/util.js');
          const a = __delta.measure.paths().map(p => google.maps.geometry.spherical.computeArea(p));
          return [u.formatArea(a[0] + a[1], units), u.formatArea(a[0], units), u.formatArea(a[1], units)]; }""",
        page.evaluate("__delta.store.get().units"),
    )
    assert [l[1] for l in lines] == exp
    # undo walks back into the second polygon, then out of it; the first stays
    page.keyboard.press("Control+z")
    assert page.evaluate("__delta.measure.sketch('area').state().open") is True
    for _ in range(4):
        page.keyboard.press("Control+z")
    assert n_points(page) == [3]
    # Delete clears everything, and is itself undoable
    page.keyboard.press("Delete")
    assert n_points(page) == []
    page.keyboard.press("Control+z")
    assert n_points(page) == [3]
    assert page.delta_errors == []


def test_dragging_a_vertex_updates_the_measurement(page):
    page.evaluate("__delta.store.set({tool: 'area'}, 'test')")
    draw(page, POLY)
    before = page.evaluate("__delta.store.get().results[0].data.lines[0][1]")
    v0 = vertices(page)[0]
    x, y = CX + POLY[0][0], CY + POLY[0][1]
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 60, y - 50, steps=8)
    page.mouse.up()
    wait_for(page, "(b) => __delta.store.get().results[0].data.lines[0][1] !== b", before)
    v1 = vertices(page)[0]
    assert v1 != v0 and len(vertices(page)) == 5
    # the move is one undo step
    page.keyboard.press("Control+z")
    wait_for(page, "(b) => __delta.store.get().results[0].data.lines[0][1] === b", before)
    assert page.delta_errors == []


def test_shortcuts_only_in_the_sketching_tool(page):
    page.evaluate("__delta.store.set({tool: 'area'}, 'test')")
    draw(page, POLY)
    page.evaluate("__delta.store.set({tool: 'query'}, 'test')")
    page.evaluate("__delta.store.set({tool: 'area'}, 'test')")
    assert n_points(page) == []  # a tool switch starts over
    draw(page, POLY)
    page.evaluate("__delta.store.set({tool: null}, 'test')")
    page.keyboard.press("Control+z")
    page.keyboard.press("Delete")
    # nothing active: nothing heard (the area sketch was reset by the switch anyway)
    assert page.evaluate("__delta.store.get().tool") is None
    assert page.delta_errors == []


def test_area_polygon_drags_whole_and_a_click_inside_starts_another(page):
    page.evaluate("__delta.store.set({tool: 'area'}, 'test')")
    draw(page, POLY)
    v0 = vertices(page)
    area0 = page.evaluate("__delta.store.get().results[0].data.lines[0][1]")
    # press inside, drag, release: the whole polygon moves
    x, y = CX + 10, CY + 10
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 60, y + 40, steps=10)
    page.mouse.up()
    wait_for(page, "(v) => JSON.stringify(__delta.measure.paths()[0].map(p => [p.lat(), p.lng()])) !== JSON.stringify(v)", v0)
    v1 = vertices(page)
    assert len(v1) == len(v0)
    dlat = [b[0] - a[0] for a, b in zip(v0, v1)]
    dlng = [b[1] - a[1] for a, b in zip(v0, v1)]
    # moved east and south, together (a geodesic shape moves over the sphere, so not to the last digit)
    assert max(dlng) - min(dlng) < 1e-3 and max(dlat) - min(dlat) < 1e-3 and dlng[0] > 0 and dlat[0] < 0, (dlat, dlng)
    assert n_points(page) == [5]  # no new polygon from the press
    # the move is one undo step
    page.keyboard.press("Control+z")
    wait_for(page, "(v) => JSON.stringify(__delta.measure.paths()[0].map(p => [p.lat(), p.lng()])) === JSON.stringify(v)", v0)
    assert page.evaluate("__delta.store.get().results[0].data.lines[0][1]") == area0
    # a click inside (no drag) starts another, overlapping polygon
    page.mouse.click(CX + 10, CY + 10)
    wait_for(page, "__delta.measure.sketch('area').state().open === true")
    assert n_points(page) == [5, 1]
    assert page.delta_errors == []
