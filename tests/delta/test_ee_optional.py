"""Delta without Earth Engine: a map with no Earth Engine layers never loads
the Earth Engine library or signs in; Earth Engine loads when the first Earth
Engine layer needs it; and an Earth Engine failure leaves the other layers
drawn. The loader itself is unit-tested in georest tests/view/js/eeloader.test.mjs.

Needs the local eeCreds proxy (the page is served by it) and a network.
"""
import json
import time

import pytest

pytestmark = pytest.mark.live

TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
SQUARE = [[-112.0, 40.6], [-111.8, 40.6], [-111.8, 40.8], [-112.0, 40.8], [-112.0, 40.6]]
GEOJSON = {"type": "Feature", "properties": {"n": 1}, "geometry": {"type": "Polygon", "coordinates": [SQUARE]}}


def wait_for(page, js, arg=None, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for: " + js + " " + repr(page.delta_errors))


def recorder(seen):
    """A live_map setup that records every request the page makes."""
    def setup(ctx):
        ctx.on("request", lambda req: seen.append(req.url))
    return setup


def ee_requests(seen):
    return [u for u in seen if "ee_api_js" in u or "/ee-api/" in u]


def layer(page, name):
    return page.evaluate("(n) => __delta.store.get().layers.find(l => l.name === n)", name)


def build_no_ee(Map):
    Map.addLayer(GEOJSON, {"strokeColor": "ff0000"}, "GeoJSON")
    Map.addTileLayer(TILES, name="Topo")
    Map.setCenter(-111.9, 40.7, 10)


def test_a_map_without_earth_engine_never_loads_it(live_map):
    seen = []
    page = live_map(build_no_ee, setup=recorder(seen))
    wait_for(page, "() => __delta.store.get().layers.length === 2 && __delta.store.get().layers.every(l => !l.loading)")
    for name in ("GeoJSON", "Topo"):
        l = layer(page, name)
        assert l["error"] is None, l
        assert page.evaluate("(id) => __delta.engine.layers.stats(id).onMap", l["id"]), name
    time.sleep(2)
    assert ee_requests(seen) == [], ee_requests(seen)
    assert page.evaluate("__delta.eeLoader.isReady()") is False
    assert page.delta_errors == []


def build_mixed(Map):
    import geeViz.geeView as gv

    Map.addLayer(gv.ee.Image("USGS/SRTMGL1_003"), {"min": 0, "max": 3000}, "SRTM")
    Map.addLayer(GEOJSON, {"strokeColor": "ff0000"}, "GeoJSON")
    Map.setCenter(-111.9, 40.7, 10)


def test_earth_engine_failing_spares_the_other_layers(live_map):
    def setup(ctx):
        ctx.route("**/ee-api/**", lambda route: route.abort())
    page = live_map(build_mixed, setup=setup, wait_layers=False)
    wait_for(page, "() => { const ls = __delta.store.get().layers; return ls.length === 2 && ls.every(l => !l.loading); }", timeout=120)
    g = layer(page, "GeoJSON")
    assert g["error"] is None, g
    assert page.evaluate("(id) => __delta.engine.layers.stats(id).onMap", g["id"])
    srtm = layer(page, "SRTM")
    assert isinstance(srtm["error"], str) and srtm["error"], srtm
    ee_notices = [n for n in page.evaluate("__delta.store.get().notices") if "Earth Engine" in str(n)]
    assert len(ee_notices) == 1, page.evaluate("__delta.store.get().notices")


def test_a_layer_added_later_loads_earth_engine(live_map):
    import geeViz.geeView as gv

    seen = []
    page = live_map(lambda Map: (Map.addLayer(GEOJSON, {}, "GeoJSON"), Map.setCenter(-111.9, 40.7, 10)), setup=recorder(seen))
    time.sleep(2)
    assert ee_requests(seen) == []
    item = json.loads(gv.ee.Image("USGS/SRTMGL1_003").serialize())
    page.evaluate("(item) => __delta.api.addSerializedLayer(item, {min: 0, max: 3000}, 'SRTM', true)", item)
    # while Earth Engine loads, the row says it is loading
    assert layer(page, "SRTM")["loading"] is True
    wait_for(page, "() => { const l = __delta.store.get().layers.find(x => x.name === 'SRTM'); const st = l && __delta.engine.layers.stats(l.id); return l && !l.loading && !l.error && st && st.onMap; }", timeout=120)
    assert len([u for u in seen if "ee_api_js" in u]) == 1, [u for u in seen if "ee_api_js" in u]
    assert page.delta_errors == []


def build_auto_chart(Map):
    import geeViz.geeView as gv

    nlcd = gv.ee.ImageCollection("USGS/NLCD_RELEASES/2021_REL/NLCD").select(["landcover"]).first()
    Map.addLayer(nlcd, {"autoViz": True, "canAreaChart": True}, "NLCD")
    Map.turnOnAutoAreaCharting()
    Map.setCenter(-111.9, 40.7, 12)


def test_auto_area_charting_at_load_waits_for_earth_engine(live_map):
    # the map rests, and auto charting starts, while Earth Engine is still
    # loading: the library is held back past the first rest and idle delay
    def setup(ctx):
        def slow(route):
            time.sleep(5)
            route.continue_()
        ctx.route("**/ee_api_js.js", slow)
    page = live_map(build_auto_chart, setup=setup, wait_layers=False)
    wait_for(page, "() => __delta.store.get().results.some(r => r.title === 'NLCD') && !__delta.store.get().charting", timeout=150)
    notices = page.evaluate("__delta.store.get().notices")
    assert not [n for n in notices if "not loaded" in str(n)], notices
    assert page.delta_errors == []
