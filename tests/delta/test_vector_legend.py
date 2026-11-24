"""Delta: a vector layer's legend is its symbol, in the row. One glyph per
geometry type it holds (point, line, polygon), filled and stroked as the map
draws it, and no legend to open below the row. The glyph rules are
unit-tested in geeView/delta/tests/vectorlegend.test.mjs; this checks the
geometry types found on real layers and the row on a live map.

Needs Earth Engine, the local eeCreds proxy and a network.
"""
import time

import pytest

pytestmark = pytest.mark.live

SQUARE = [[-112.0, 40.6], [-111.8, 40.6], [-111.8, 40.8], [-112.0, 40.8], [-112.0, 40.6]]
MIXED = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [-111.9, 40.7]}},
    {"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": [[-112.0, 40.6], [-111.8, 40.8]]}},
]}
FILLED = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [SQUARE]}}


def build(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([-111.9, 40.7])), ee.Feature(ee.Geometry.Point([-111.85, 40.75]))])
    line = ee.FeatureCollection([ee.Feature(ee.Geometry.LineString([[-112.0, 40.6], [-111.8, 40.8]]))])
    poly = ee.FeatureCollection([ee.Feature(ee.Geometry.Polygon([SQUARE]))])
    Map.addLayer(pts, {"strokeColor": "ff0000"}, "EE points")
    Map.addLayer(line, {"strokeColor": "00aa00"}, "EE line")
    Map.addLayer(poly, {"strokeColor": "0000ff"}, "EE polygon outline")
    Map.addLayer(poly, {"styleParams": {"color": "ff8800", "fillColor": "ff880066", "width": 2}}, "EE polygon styled")
    Map.addLayer(poly, {"styleParams": {"color": "ff8800", "fillColor": "00000000", "width": 2}}, "EE polygon styled no fill")
    Map.addLayer(FILLED, {"strokeColor": "aa00aa", "fillColor": "aa00aa", "fillOpacity": 0.4}, "GeoJSON filled")
    Map.addLayer(FILLED, {"strokeColor": "aa00aa", "fillOpacity": 0}, "GeoJSON hollow")
    Map.addLayer(MIXED, {"strokeColor": "008888"}, "GeoJSON mixed")
    Map.setCenter(-111.9, 40.7, 10)


@pytest.fixture
def page(live_map):
    return live_map(build)


def wait_for(page, js, arg=None, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for: " + js + " " + repr(page.delta_errors))


SYMBOL_JS = """(name) => {
  const l = __delta.store.get().layers.find(x => x.name === name);
  const row = document.querySelector('#layer-list .layer[data-id="' + l.id + '"]');
  const btn = row.querySelector('.legbtn');
  return {
    geoms: (l.legend && l.legend.geoms) || null,
    symbol: btn.classList.contains('symbol'),
    arrow: getComputedStyle(btn.querySelector('.ti')).display !== 'none',
    open: row.classList.contains('leg-open'),
    glyphs: [...btn.querySelectorAll('svg')].map(s => {
      const e = s.firstElementChild;
      return {geom: s.dataset.geom, fill: e.getAttribute('fill'), stroke: e.getAttribute('stroke')};
    }),
  };
}"""


def symbol(page, name):
    wait_for(page, "(n) => { const l = __delta.store.get().layers.find(x => x.name === n); return !!(l && l.legend && l.legend.geoms); }", name)
    return page.evaluate(SYMBOL_JS, name)


def test_each_vector_shows_its_geometry_as_drawn(page):
    got = {n: symbol(page, n) for n in (
        "EE points", "EE line", "EE polygon outline", "EE polygon styled", "EE polygon styled no fill",
        "GeoJSON filled", "GeoJSON hollow", "GeoJSON mixed")}
    # Earth Engine paints these on the server; the types come from Earth Engine
    assert got["EE points"]["glyphs"] == [{"geom": "point", "fill": "#ff0000", "stroke": "none"}]
    assert got["EE line"]["glyphs"] == [{"geom": "line", "fill": "none", "stroke": "#00aa00"}]
    # painted outlines (the default) have no fill
    assert got["EE polygon outline"]["glyphs"] == [{"geom": "polygon", "fill": "none", "stroke": "#0000ff"}]
    assert got["EE polygon styled"]["glyphs"] == [{"geom": "polygon", "fill": "#ff8800", "stroke": "#ff8800"}]
    assert got["EE polygon styled no fill"]["glyphs"][0]["fill"] == "none"
    assert got["GeoJSON filled"]["glyphs"] == [{"geom": "polygon", "fill": "#aa00aa", "stroke": "#aa00aa"}]
    assert got["GeoJSON hollow"]["glyphs"][0]["fill"] == "none"
    assert [g["geom"] for g in got["GeoJSON mixed"]["glyphs"]] == ["point", "line"]
    for name, s in got.items():
        assert s["symbol"] and not s["arrow"] and not s["open"], (name, s)
    assert page.delta_errors == []


def test_the_symbol_is_not_a_toggle(page):
    symbol(page, "GeoJSON filled")
    row = page.evaluate("() => __delta.store.get().layers.find(x => x.name === 'GeoJSON filled').id")
    sel = f'#layer-list .layer[data-id="{row}"]'
    page.locator(sel + " .legbtn").click(force=True)
    time.sleep(0.3)
    assert "leg-open" not in (page.get_attribute(sel, "class") or "")
    assert page.evaluate("() => __delta.store.get().layers.find(x => x.name === 'GeoJSON filled').legendOpen") is False



def build_points(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([-111.9, 40.7]), {"name": "here"})])
    Map.addLayer(pts, {"strokeColor": "ff0000"}, "EE points")
    Map.setCenter(-111.9, 40.7, 12)


def test_a_point_is_found_a_few_pixels_from_the_click(live_map):
    # at zoom 12, 15 m (plotRadius) is under half a pixel; the point's dot is
    # several pixels wide, so a click near its edge must find it
    page = live_map(build_points)
    symbol(page, "EE points")
    page.evaluate("__delta.engine.gmap.setCenter({lat: 40.7, lng: -111.9})")
    page.evaluate("__delta.store.set({tool: 'query'}, 'test')")
    time.sleep(1.5)
    cx, cy = page.evaluate("(() => { const r = document.querySelector('#map').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
    page.mouse.dblclick(cx + 5, cy - 4)
    wait_for(page, "__delta.store.get().querying === false && __delta.store.get().results.length > 0", timeout=60)
    r = [x for x in page.evaluate("__delta.store.get().results") if x["title"] == "EE points"]
    assert r, page.evaluate("__delta.store.get().results")
    # the feature itself, not the "No features here" card
    assert r[0]["meta"] != "No features here", r[0]
    assert ["name", "here"] in r[0]["data"]["rows"], r[0]
    assert page.delta_errors == []
