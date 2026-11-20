"""Delta layers: every layer type renders, legends, opacity, order, drag.

Needs Earth Engine, the local eeCreds proxy and a network: every test is live.
"""
import time

import pytest

pytestmark = pytest.mark.live

# Verified against the live catalog (2026-11-18): the current LCMS release.
LCMS = "projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11"
# A public dynamic (uncached, singleFusedMapCache false) MapServer.
DYNAMIC = "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_ForestSystemBoundaries_01/MapServer"
TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"

NAMES = ["SRTM", "LCMS Land Cover", "Polygons", "Polygons vector", "GeoJSON", "Topo tiles", "Forest boundaries"]


def _rect(x, y, d=1.5):
    return [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]]


GEOJSON = {
    "type": "FeatureCollection",
    "features": [{"type": "Feature", "properties": {"n": 1}, "geometry": {"type": "Polygon", "coordinates": _rect(-100, 38)}}],
}


def build_all(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    Map.addLayer(ee.Image("USGS/SRTMGL1_003"), {"min": 0, "max": 3000}, NAMES[0])
    lcms = ee.ImageCollection(LCMS).filter('study_area=="CONUS"').select(["Land_Cover"])
    Map.addLayer(lcms, {"autoViz": True}, NAMES[1])
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Polygon(_rect(x, 40))) for x in (-110, -105, -95)])
    Map.addLayer(fc, {}, NAMES[2])
    Map.addLayer(fc, {"layerType": "geeVector"}, NAMES[3])
    Map.addLayer(GEOJSON, {}, NAMES[4])
    Map.addTileLayer(TILES, name=NAMES[5])
    Map.addEsriMapService(DYNAMIC, name=NAMES[6])


ROWS = "Array.from(document.querySelectorAll('#layer-list .layer'))"


def rows(page):
    return page.evaluate(ROWS + ".map(r => ({id: r.dataset.id, name: r.querySelector('.lname').textContent}))")


def layer(page, name):
    return page.evaluate("(n) => __delta.store.get().layers.find(l => l.name === n)", name)


def row_sel(page, name):
    rid = layer(page, name)["id"]
    return '#layer-list .layer[data-id="%s"]' % rid


def settle(page, ms=120):
    page.evaluate("(ms) => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, ms))))", ms)


def wait_loaded(page, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not page.evaluate("__delta.store.get().layers.some(l => l.loading)"):
            return
        time.sleep(0.5)
    raise AssertionError("layers still loading: %s" % page.evaluate("__delta.store.get().layers.filter(l => l.loading).map(l => l.name)"))


def set_left_width(page, w):
    page.evaluate(
        "(w) => __delta.store.update(s => ({...s, panes: {...s.panes, left: {...s.panes.left, width: w}}}), 'test')", w
    )
    settle(page)


@pytest.fixture
def page(live_map):
    p = live_map(build_all)
    wait_loaded(p)
    return p


def test_all_types_render(page):
    got = rows(page)
    assert [r["name"] for r in got] == list(reversed(NAMES))
    layers = page.evaluate("__delta.store.get().layers.map(l => ({name: l.name, loading: l.loading, error: l.error, legend: l.legend}))")
    for l in layers:
        assert l["loading"] is False, l
        assert l["error"] is None, l
    for r in got:
        stats = page.evaluate("(id) => __delta.engine.layers.stats(id)", r["id"])
        assert stats["requests"] >= 1, (r, stats)
        assert stats["onMap"], (r, stats)
    by = {l["name"]: l for l in layers}
    assert by["SRTM"]["legend"]["type"] == "ramp"
    assert by["SRTM"]["legend"]["labels"] == ["0", "3000"]
    lc = by["LCMS Land Cover"]["legend"]
    assert lc["type"] == "classes" and lc["items"][0] == {"label": "1- Trees", "color": "#004e2b"}
    assert by["Polygons"]["legend"]["type"] == "outline"
    assert by["Polygons vector"]["legend"]["type"] == "outline"
    assert page.delta_errors == []


def test_order_matches_original(page, live_map):
    delta_names = [r["name"] for r in rows(page)]
    orig = live_map(build_all, skin="original")
    orig.wait_for_function("document.querySelectorAll('#layer-list > li .layer-span').length >= %d" % len(NAMES), timeout=120000)
    orig_names = orig.evaluate("Array.from(document.querySelectorAll('#layer-list > li .layer-span')).map(s => s.textContent.trim())")
    assert delta_names == orig_names
    # z-order equals row order: every layer type is in the one tile stack
    # (vectors and the dynamic service draw as tiles), bottom to top.
    ids = [r["id"] for r in rows(page)]
    z = page.evaluate("__delta.engine.layers.zOrder()")
    assert z["tiles"] == list(reversed(ids)), (z, ids)
    assert z["vectors"] == []


def test_name_click_toggles(page):
    sel = row_sel(page, "SRTM")
    page.click(sel + " .lname")
    settle(page, 300)
    assert layer(page, "SRTM")["visible"] is False
    assert page.evaluate("(id) => __delta.engine.layers.stats(id).onMap", layer(page, "SRTM")["id"]) is False
    assert "off" in page.get_attribute(sel, "class")
    page.click(sel + " .lname")
    settle(page, 300)
    assert layer(page, "SRTM")["visible"] is True
    assert page.evaluate("(id) => __delta.engine.layers.stats(id).onMap", layer(page, "SRTM")["id"]) is True
    page.click(sel + " .tgl")
    settle(page)
    assert layer(page, "SRTM")["visible"] is False


def test_off_folds_legend_and_restores(page):
    sel = row_sel(page, "LCMS Land Cover")
    legend = page.locator(sel + " .legend")
    # on with a legend: its legend opened the first time, unasked
    assert legend.is_visible()
    page.click(sel + " .legbtn")
    assert not legend.is_visible()
    page.click(sel + " .legbtn")
    assert legend.is_visible()
    assert page.locator(sel + " .legend .sw").count() == 15
    assert page.locator(sel + " .lsw i").count() == 4
    page.click(sel + " .tgl")
    assert not legend.is_visible()
    page.click(sel + " .tgl")
    assert legend.is_visible()
    # A closed legend stays closed through off and on.
    page.click(sel + " .legbtn")
    page.click(sel + " .tgl")
    page.click(sel + " .tgl")
    assert not legend.is_visible()


FIT = """() => Array.from(document.querySelectorAll('#layer-list .layer')).map(r => {
  const n = r.querySelector('.lname'); const s = r.querySelector('input.op');
  const nb = n.getBoundingClientRect(); const sb = s.getBoundingClientRect();
  return {name: n.textContent, stack: r.classList.contains('stack'), cut: n.scrollWidth > n.clientWidth + 1,
          sliderTop: sb.top, nameBottom: nb.bottom, sliderWidth: sb.width};
})"""


def test_opacity_inline_only_when_fits(page):
    seen_stack = seen_inline = False
    for w in (260, 300, 340, 400, 480):
        set_left_width(page, w)
        for r in page.evaluate(FIT):
            if r["stack"]:
                seen_stack = True
                assert r["sliderTop"] > r["nameBottom"], (w, r)
            else:
                seen_inline = True
                assert not r["cut"], (w, r)
    assert seen_stack and seen_inline


def test_slider_grows_then_caps(page):
    def width(w):
        set_left_width(page, w)
        r = [x for x in page.evaluate(FIT) if x["name"] == "SRTM"][0]
        assert not r["stack"], (w, r)
        return r["sliderWidth"]

    assert abs(width(300) - 64) <= 1
    a, b = width(340), width(420)
    assert abs((b - a) - 80) <= 2, (a, b)
    assert abs(width(480) - 180) <= 1
    assert abs(width(560) - 180) <= 1


def test_loaded_fill_stays_and_ends_before_the_legend_button(page):
    """Every layer type shows its tiles in as a fill behind the name row
    that stays once loaded and ends just before the legend button, where a
    timelapse's controls end."""
    settle(page, 400)
    got = page.evaluate("""() => [...document.querySelectorAll('#layer-list .layer:not(.off)')].map(row => {
      const lr = row.querySelector('.lrow').getBoundingClientRect(); const be = getComputedStyle(row.querySelector('.lrow'), '::before');
      const tl = row.querySelector('.tl');
      return {name: row.querySelector('.lname').textContent, prog: row.classList.contains('prog'), pct: row.style.getPropertyValue('--prog'),
              end: lr.right - parseFloat(be.right), leg: row.querySelector('.legbtn').getBoundingClientRect().left,
              tlEnd: tl && tl.getClientRects().length ? tl.getBoundingClientRect().right : null};
    })""")
    assert len(got) == len(NAMES), got
    for r in got:
        assert r["prog"] and r["pct"] == "100%", r
        assert abs(r["end"] - (r["leg"] - 1)) <= 1, r

    # the same point as a timelapse's controls (their margin: legend button + gap - padding)
    tl_end = page.evaluate("""() => { const row = document.querySelector('#layer-list .layer'); const lb = row.querySelector('.lrow').getBoundingClientRect();
      const s = getComputedStyle(row); const leg = parseFloat(s.getPropertyValue('--leg-w')), gap = parseFloat(s.getPropertyValue('--lrow-gap')), pad = parseFloat(s.getPropertyValue('--tl-pad'));
      return [lb.right - (leg + gap - pad), lb.right - parseFloat(getComputedStyle(row.querySelector('.lrow'), '::before').right)]; }""")
    assert abs(tl_end[0] - tl_end[1]) <= 0.5, tl_end


def test_drag_reorder_moves_every_layer_type(page):
    """Vectors, the dynamic map service and tiles all move with the list; the
    original pinned vectors and dynamic services above the tile layers."""
    before = rows(page)
    names = [r["name"] for r in before]
    assert not any(layer(page, n)["pinned"] for n in names)
    z0 = page.evaluate("__delta.engine.layers.zOrder()")["tiles"]
    # a true vector (GeoJSON) dragged below the SRTM image
    page.locator(row_sel(page, "GeoJSON") + " .lname").drag_to(page.locator(row_sel(page, "SRTM") + " .lname"), target_position={"x": 5, "y": 14})
    settle(page, 400)
    after = [r["name"] for r in rows(page)]
    assert after != names
    assert after.index("GeoJSON") > after.index("SRTM"), after
    # and the dynamic service to the top
    page.locator(row_sel(page, "Forest boundaries") + " .lname").drag_to(page.locator(row_sel(page, after[0]) + " .lname"), target_position={"x": 5, "y": 2})
    settle(page, 400)
    after = [r["name"] for r in rows(page)]
    assert after[0] == "Forest boundaries", after
    z1 = page.evaluate("__delta.engine.layers.zOrder()")["tiles"]
    assert z1 != z0
    ids = [r["id"] for r in rows(page)]
    assert z1 == [i for i in reversed(ids) if i in z1]
    stored = page.evaluate("urlParams.layerOrders['layer-list']")
    assert stored == list(reversed(ids))
    assert "layerOrders" in page.evaluate("location.search")


def build_many(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    names = ["L%d" % i for i in range(21)] + ["A"] + ["L%d" % i for i in range(21, 43)] + ["A"]
    for i, n in enumerate(names):
        Map.addLayer(ee.Image.constant(i), {"min": 0, "max": 45}, n, False)
    return names


def test_duplicate_names_and_many_layers(live_map):
    page = live_map(build_many)
    wait_loaded(page)
    got = rows(page)
    assert len(got) == 45
    names = ["L%d" % i for i in range(21)] + ["A"] + ["L%d" % i for i in range(21, 43)] + ["A"]
    assert [r["name"] for r in got] == list(reversed(names))
    assert len({r["id"] for r in got}) == 45
    assert page.evaluate("__delta.engine.layers.slotOrder()") == [r["id"] for r in reversed(got)]
    assert page.evaluate("__delta.store.get().layers.every(l => !l.error)")


EVIL = '</script><b>x</b>"'


def build_evil(Map):
    Map.addLayer(GEOJSON, {}, EVIL)
    Map.setCanReorderLayers(False)


def test_names_render_as_text(live_map):
    page = live_map(build_evil)
    wait_loaded(page)
    assert [r["name"] for r in rows(page)] == [EVIL]
    assert page.locator("#layer-list b").count() == 0
    assert page.evaluate("document.querySelectorAll('#pane-left b').length") == 1  # the "Delta" brand only
    # setCanReorderLayers(False) turns dragging off.
    assert page.evaluate("__delta.layersUI.sortable().option('disabled')") is True
