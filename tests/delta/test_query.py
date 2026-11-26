"""Delta Query tool and select layers.

A click queries every visible layer at a point (values must equal the
Python earthengine-api for the same inputs), stale answers are dropped,
select layers draw and list, and clicking the active tool folds the pane.

Needs Earth Engine, the local eeCreds proxy and a network: every test is live.
"""
import time

import pytest

pytestmark = pytest.mark.live

# Verified against the live catalog (2026-11-18): the current LCMS release.
LCMS = "projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11"
SRTM = "USGS/SRTMGL1_003"
POINT = (-111.527, 40.504)
UNITS = ["Bear Unit", "Elk Unit", "Moose Unit"]
MAP_CENTER = (750, 437)  # the map fills the 1500 x 900 window above the 26 px status bar; panes overlay it


def _square(x, y, d=0.02):
    return [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]]


def unit_center(i):
    return (-111.40 + 0.05 * i + 0.01, 40.50 + 0.01)


def build(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    Map.addLayer(ee.Image(SRTM), {"min": 1000, "max": 3500}, "SRTM")
    lc = ee.ImageCollection(LCMS).filter('study_area=="CONUS"').select(["Land_Cover"])
    Map.addLayer(lc, {"autoViz": True}, "LCMS Land Cover")
    # An empty collection queries to a no-data card, not a failure.
    Map.addLayer(lc.filter(ee.Filter.calendarRange(1900, 1900, "year")), {"min": 1, "max": 15}, "Empty LCMS")
    fc = ee.FeatureCollection(
        [ee.Feature(ee.Geometry.Polygon(_square(-111.40 + 0.05 * i, 40.50)), {"nm": n, "code": i}) for i, n in enumerate(UNITS)]
    )
    Map.addSelectLayer(fc, {"strokeColor": "00F", "selectLayerNameProperty": "nm"}, "Units")
    Map.setCenter(POINT[0], POINT[1], 13)
    Map.turnOnInspector()


@pytest.fixture
def page(live_map):
    return live_map(build)


def ee():
    import geeViz.geeView as gv

    return gv.ee


def go(page, lng, lat):
    page.evaluate(
        """([lng, lat]) => new Promise((res) => {
          const m = __delta.engine.gmap;
          google.maps.event.addListenerOnce(m, 'idle', () => setTimeout(res, 100));
          m.setCenter({lat, lng});
          m.panBy(0, 1); m.panBy(0, -1);
        })""",
        [lng, lat],
    )


def wait_for(page, js, arg=None, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for: " + js)


def results(page):
    return page.evaluate("__delta.store.get().results")


def wait_query_done(page):
    wait_for(page, "__delta.store.get().querying === false && __delta.store.get().results.length > 0")


def click_center(page, dx=0, dy=0):
    page.mouse.click(MAP_CENTER[0] + dx, MAP_CENTER[1] + dy)


def by_title(rs, title):
    found = [r for r in rs if r["title"] == title]
    assert found, [r["title"] for r in rs]
    return found[0]


def query_inputs(page):
    return page.evaluate("__delta.store.get().query")


def py_first(img, pt, q):
    kw = {"crs": q["crs"]}
    if q["transform"]:
        kw["crsTransform"] = q["transform"]
    else:
        kw["scale"] = q["scale"]
    return img.reduceRegion(ee().Reducer.first(), pt, **kw).getInfo()


def test_query_values_match_python(page):
    go(page, *POINT)
    click_center(page)
    wait_query_done(page)
    wait_for(page, "__delta.store.get().results.length >= 2")
    rs = results(page)
    srtm = by_title(rs, "SRTM")
    p = srtm["data"]["point"]
    assert abs(p["lng"] - POINT[0]) < 0.001 and abs(p["lat"] - POINT[1]) < 0.001
    pt = ee().Geometry.Point([p["lng"], p["lat"]])
    q = query_inputs(page)
    assert q["crs"] == "EPSG:5070" and q["transform"] == [30, 0, -2361915.0, 0, -30, 3177735.0]
    expected = py_first(ee().Image(SRTM), pt, q)
    assert srtm["kind"] == "value"
    assert {b["band"]: b["value"] for b in srtm["data"]["bands"]} == expected

    lcms = by_title(rs, "LCMS Land Cover")
    assert lcms["kind"] == "series"
    xs = lcms["data"]["x"]
    ys = lcms["data"]["series"][0]["y"]
    labels = lcms["data"]["series"][0]["labels"]
    i2023 = [i for i, x in enumerate(xs) if x.startswith("2023")]
    assert len(i2023) == 1
    assert ys[i2023[0]] == 1 and labels[i2023[0]] == "Trees"
    # The whole series equals the Python getRegion at the same point and grid.
    lc = ee().ImageCollection(LCMS).filter('study_area=="CONUS"').select(["Land_Cover"])
    region = lc.getRegion(pt, None, q["crs"], q["transform"]).getInfo()
    hdr = region[0]
    py = {r[hdr.index("id")]: r[hdr.index("Land_Cover")] for r in region[1:]}
    assert len(py) == len(ys)
    assert dict(zip(lcms["data"]["ids"], ys)) == py
    # The card shows the class name as text.
    card = page.locator('#results-mount .card-r[data-rid="%s"]' % lcms["id"])
    assert "Trees" in card.inner_text()
    assert page.locator("#chips .chip").count() == 0  # no jump buttons above the results
    empty = by_title(rs, "Empty LCMS")
    assert empty["kind"] == "series" and empty["meta"] == "No data" and "error" not in empty["data"]
    # The only console errors are the empty collection's map service (400); nothing from the query.
    assert [e for e in page.delta_errors if "status of 400" not in e] == []


def test_query_respects_scale_and_crs(page):
    page.evaluate("__delta.api.setQueryScale(120)")
    # At this point and scale only Web Mercator changes SRTM's answer, so
    # the crs is checked too.
    page.evaluate("__delta.api.setQueryCRS('EPSG:3857')")
    go(page, *POINT)
    click_center(page)
    wait_query_done(page)
    srtm = by_title(results(page), "SRTM")
    p = srtm["data"]["point"]
    pt = ee().Geometry.Point([p["lng"], p["lat"]])
    q = query_inputs(page)
    assert q["scale"] == 120 and q["transform"] is None and q["crs"] == "EPSG:3857"
    expected = py_first(ee().Image(SRTM), pt, q)
    at30 = py_first(ee().Image(SRTM), pt, {"crs": "EPSG:5070", "transform": [30, 0, -2361915.0, 0, -30, 3177735.0]})
    no_crs = ee().Image(SRTM).reduceRegion(ee().Reducer.first(), pt, 120).getInfo()
    assert expected != at30, "pick a point where the scale changes the answer"
    assert expected != no_crs, "pick a point where the crs changes the answer"
    assert {b["band"]: b["value"] for b in srtm["data"]["bands"]} == expected


def test_stale_query_results_are_dropped(page):
    go(page, *POINT)
    click_center(page)
    page.wait_for_timeout(400)  # past the 300 ms double-click wait: the first query starts
    click_center(page, dx=120)
    wait_query_done(page)
    wait_for(page, "__delta.store.get().results.length >= 2")
    page.wait_for_timeout(3000)  # let any answer to the first query arrive
    rs = results(page)
    pts = {(round(r["data"]["point"]["lng"], 6), round(r["data"]["point"]["lat"], 6)) for r in rs}
    assert len(pts) == 1, pts
    (lng, lat), = pts
    assert lng > POINT[0] + 0.001  # the second point, to the east
    assert len(rs) == len({r["layerId"] for r in rs})
    assert page.locator("#results-mount .card-r").count() == len(rs)
    where = page.inner_text("#where")
    assert "%.4f" % lng in where


def test_select_layer_selection(page):
    units = page.evaluate("__delta.store.get().layers.find(l => l.name === 'Units')")
    assert units["kind"] == "select"
    row = '#layer-list .layer[data-id="%s"]' % units["id"]
    assert page.locator(row).count() == 1  # listed
    page.click(row + " .tgl")
    wait_for(page, "(id) => __delta.engine.layers.stats(id).onMap", units["id"])  # drawn
    go(page, *unit_center(1))
    # Under Query a click selects nothing (only Chart area's Select source does).
    assert page.evaluate("__delta.store.get().tool") == "query"
    page.mouse.click(*MAP_CENTER)
    page.wait_for_timeout(2500)
    assert page.evaluate("__delta.store.get().selections") == []
    # Chart area shows only with a layer that can be area charted; add one so Select has something to chart.
    page.evaluate("Map.addLayer(ee.Image(1).rename('one'), {min: 0, max: 1, canAreaChart: true}, 'Chartable', true)")
    wait_for(page, "!document.querySelector('#pane-right .tool[data-tool=chart]').hidden")
    page.evaluate("__delta.api.turnOnSelectionAreaCharting()")
    wait_for(page, "__delta.store.get().tool === 'chart'")
    assert page.evaluate("[__delta.store.get().tool, __delta.store.get().areaFrom]") == ["chart", "select"]
    page.mouse.click(*MAP_CENTER)
    wait_for(page, "__delta.store.get().selections.length === 1")
    sel = page.evaluate("__delta.store.get().selections")
    assert [s["name"] for s in sel] == [UNITS[1]]
    assert sel[0]["names"] == [UNITS[1]] and len(sel[0]["ids"]) == 1 and sel[0]["years"] is None
    assert sel[0]["label"] == "Selected Units " + UNITS[1]
    assert sel[0]["areaM2"] > 0
    wait_for(page, "document.querySelector('#results-mount .sel-list') !== null")
    assert UNITS[1] in page.inner_text("#results-mount .sel-list")
    # Clicking the same feature again does not add it twice; another adds a second.
    page.mouse.click(*MAP_CENTER)
    go(page, *unit_center(2))
    page.mouse.click(*MAP_CENTER)
    wait_for(page, "__delta.store.get().selections.length === 2")
    page.wait_for_timeout(1500)
    assert [s["name"] for s in page.evaluate("__delta.store.get().selections")] == [UNITS[1], UNITS[2]]
    # Usable by Chart area: an ee.FeatureCollection of the selected features.
    names = page.evaluate(
        """() => __delta.query.selectionCollection().then(fc => new Promise(res =>
             fc.aggregate_array('nm').evaluate(v => res(v))))"""
    )
    assert sorted(names) == sorted(UNITS[1:])
    page.click("#results-mount .sel-list [data-act=clear]")
    wait_for(page, "__delta.store.get().selections.length === 0")


def test_select_layers_are_not_queried(page):
    units = page.evaluate("__delta.store.get().layers.find(l => l.name === 'Units')")
    page.click('#layer-list .layer[data-id="%s"] .tgl' % units["id"])
    wait_for(page, "(id) => __delta.engine.layers.stats(id).onMap", units["id"])
    go(page, *unit_center(1))  # inside a select polygon
    click_center(page)
    wait_query_done(page)
    wait_for(page, "__delta.store.get().results.length >= 2")
    page.wait_for_timeout(2000)
    rs = results(page)
    assert {r["title"] for r in rs} >= {"SRTM", "LCMS Land Cover"}
    assert [r for r in rs if r["layerId"] == units["id"]] == []
    # and a query click does not edit the selection
    assert page.evaluate("__delta.store.get().selections") == []


def test_tool_toggle_off_folds_pane(page):
    assert page.evaluate("__delta.store.get().tool") == "query"
    hint = page.inner_text("#tool-options")
    assert "Click the map to query every visible layer at that point." in hint
    w = page.evaluate("document.querySelector('#pane-right').getBoundingClientRect().width")
    assert w > 200
    page.click("#pane-right .tool[data-tool=query]")
    assert page.evaluate("__delta.store.get().tool") is None
    page.wait_for_timeout(400)
    w = page.evaluate("document.querySelector('#pane-right').getBoundingClientRect().width")
    assert w == 64
    go(page, *POINT)
    click_center(page)
    page.wait_for_timeout(1500)
    assert results(page) == []
    assert page.evaluate("__delta.store.get().querying") is False
    # The other tools show their one-line hints.
    page.click("#pane-right .tool[data-tool=measure]")
    assert "Click the map to start measuring" in page.inner_text("#tool-options")
    # No layer on this map can be area charted, so Chart area is not offered.
    assert page.locator("#pane-right .tool[data-tool=chart]").is_hidden()
    page.click("#pane-right .units [data-u=imperial]")
    assert page.evaluate("__delta.store.get().units") == "imperial"
