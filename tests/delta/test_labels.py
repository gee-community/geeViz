"""Delta map labels: a labels-only overlay above every layer, as the original's
addLabelOverlay (4map-manager.js labelsMapType at overlayMapTypes index =
number of layers).

The overlay is the last entry in gmap.overlayMapTypes after every change that
restacks layers, its tiles load (checked from the tile urls, which carry the
style), the dark basemap uses dark label colors, it stacks above wind
canvases, and addLabelOverlay=false turns it off.

Needs Earth Engine, the local eeCreds proxy and a network: every test is live.
"""
import time

import pytest

pytestmark = pytest.mark.live

# Verified against the live catalog (2026-11-18 / 2026-11-19).
NDVI = "MODIS/061/MOD13A2"
GFS = "NOAA/GFS0P25"
U = "u_component_of_wind_10m_above_ground"
V = "v_component_of_wind_10m_above_ground"


def build(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    Map.turnOffLayersWhenTimeLapseIsOn = False
    # Opaque everywhere: without the labels overlay it hides every basemap label.
    Map.addLayer(ee.Image(1).visualize(palette=["8a2be2"]), {}, "Opaque")
    Map.addLayer(ee.Image("USGS/SRTMGL1_003"), {"min": 0, "max": 3000}, "SRTM")
    Map.setCenter(-111.9, 40.7, 9)


def wait_for(page, js, arg=None, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for " + js)


def layer(page, name):
    return page.evaluate("(n) => __delta.store.get().layers.find(l => l.name === n)", name)


def row_sel(page, name):
    return '#layer-list .layer[data-id="%s"]' % layer(page, name)["id"]


# The labels overlay is the current one and nothing follows it.
LAST = """() => {
  const omt = __delta.engine.gmap.overlayMapTypes;
  const labels = __delta.engine.labelsOverlay();
  return !!labels && omt.getLength() > 0 && omt.getAt(omt.getLength() - 1) === labels
    && omt.getArray().filter(o => o === labels).length === 1;
}"""

# Decoded style of every loaded labels tile on the map. The overlay's tiles
# carry its style in the url (`!1sstyles!2z<base64>`); the basemap's do not
# switch geometry fill off.
LABEL_TILES = r"""() => [...document.querySelectorAll('#map img')].map(i => {
  const m = /!1sstyles!2z([^!&]+)/.exec(i.src || '');
  if (!m) return null;
  let s = '';
  try { s = atob(m[1].replace(/-/g, '+').replace(/_/g, '/')); } catch (e) { return null; }
  return s.indexOf('s.e:g.f|p.v:off') === 0 ? {style: s, loaded: i.complete && i.naturalWidth > 0} : null;
}).filter(Boolean)"""


def assert_last(page, when):
    try:
        wait_for(page, LAST, timeout=10)
    except AssertionError:
        names = page.evaluate("__delta.engine.gmap.overlayMapTypes.getArray().map(o => o ? (o.name || 'tiles') : null)")
        raise AssertionError("labels not last after %s: %r" % (when, names))


def labels_loaded(page, color=None):
    js = "(c) => (" + LABEL_TILES + ")().some(t => t.loaded && (!c || t.style.indexOf(c) > -1))"
    wait_for(page, js, color, timeout=30)


def on_map(page, name):
    wait_for(page, "(n) => { const l = __delta.store.get().layers.find(x => x.name === n); return l && __delta.engine.layers.stats(l.id).onMap; }", name)


def test_labels_stay_on_top(live_map):
    page = live_map(build)
    on_map(page, "Opaque")
    assert_last(page, "initial load")
    labels_loaded(page)
    assert page.evaluate("__delta.engine.labelsOverlay().name") == "Satellite labels"

    # A layer added later (asynchronously, after the map service arrives).
    page.evaluate("Map.addLayer(ee.Image(2).visualize({palette: ['ff8800']}), {}, 'Later', true)")
    on_map(page, "Later")
    assert_last(page, "adding a layer later")

    # Drag reorder.
    z0 = page.evaluate("__delta.engine.layers.zOrder().tiles")
    page.locator(row_sel(page, "Opaque") + " .lname").drag_to(page.locator(row_sel(page, "Later") + " .lname"), target_position={"x": 5, "y": 2})
    wait_for(page, "(z) => JSON.stringify(__delta.engine.layers.zOrder().tiles) !== JSON.stringify(z)", z0, timeout=10)
    assert_last(page, "drag reorder")

    # Visibility off and on.
    page.click(row_sel(page, "SRTM") + " .tgl")
    assert_last(page, "turning a layer off")
    page.click(row_sel(page, "SRTM") + " .tgl")
    on_map(page, "SRTM")
    assert_last(page, "turning a layer on")

    # Every overlay basemap. No map-wide
    # styles on these: while the map has any, Google draws the overlay's tiles
    # unstyled (the satellite labels lost their white text). The terrain types
    # draw their own labels and are covered by test_terrain_basemaps_draw_their_own_labels.
    for key, name in (("map", "Labels"), ("satellite", "Satellite labels")):
        page.evaluate("(k) => __delta.engine.setBasemap(k)", key)
        assert_last(page, "basemap " + key)
        assert page.evaluate("__delta.engine.labelsOverlay().name") == name
        assert page.evaluate("__delta.engine.gmap.get('styles') || null") is None, key
    # back on satellite after a terrain basemap: the overlay is styled again
    page.evaluate("__delta.engine.setBasemap('darkterrain')")
    page.evaluate("__delta.engine.setBasemap('satellite')")
    assert page.evaluate("__delta.engine.gmap.get('styles') || null") is None
    page.evaluate("__delta.engine.gmap.panBy(300, 0)")
    labels_loaded(page, "p.c:#ffffff")

    # Removing every layer and adding again (clearMap's effect).
    page.evaluate("__delta.store.get().layers.map(l => l.id).forEach(id => Map.removeLayer(id))")
    assert_last(page, "removing every layer")
    assert page.evaluate("__delta.engine.gmap.overlayMapTypes.getLength()") == 1
    page.evaluate("Map.addLayer(ee.Image(3).visualize({palette: ['00aa00']}), {}, 'Again', true)")
    on_map(page, "Again")
    assert_last(page, "re-adding a layer")

    # setCanReorderLayers(false) does not restack anything above the labels.
    page.evaluate("Map.canReorderLayers = false")
    assert_last(page, "canReorderLayers = false")
    assert not page.delta_errors, page.delta_errors


def build_timelapse_and_wind(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    Map.turnOffLayersWhenTimeLapseIsOn = False
    Map.addLayer(ee.Image(1).visualize(palette=["8a2be2"]), {}, "Opaque")
    ndvi = ee.ImageCollection(NDVI).filterDate("2018-01-01", "2021-01-01").select(["NDVI"])
    Map.addTimeLapse(ndvi, {"min": 0, "max": 9000, "palette": ["b5651d", "f7f7b5", "1a9641"]}, "NDVI TL")
    gfs = ee.ImageCollection(GFS).filterDate("2026-11-10T00:00", "2026-11-10T01:00").filter(ee.Filter.eq("forecast_hours", 0))
    Map.addWindLayer(ee.Image(gfs.first()).select([U, V]), {"units": "m/s"}, "Wind")
    Map.setCenter(-98, 39, 5)


def test_labels_above_timelapse_frames_and_wind(live_map):
    page = live_map(build_timelapse_and_wind)
    wait_for(page, "(n) => { const l = __delta.store.get().layers.find(x => x.name === n); return l && l.timelapse && l.timelapse.loaded; }", "NDVI TL", timeout=90)
    assert_last(page, "initial load")
    page.click(row_sel(page, "NDVI TL") + " .tgl")
    wait_for(page, "(id) => __delta.engine.layers.stats(id).frames.some(f => f.onMap && f.opacity > 0)", layer(page, "NDVI TL")["id"])
    assert_last(page, "turning the timelapse on")
    tl = "__delta.engine.layers.timelapse(%r)" % layer(page, "NDVI TL")["id"]
    page.evaluate(tl + ".step(1)")
    assert_last(page, "a timelapse frame step")
    page.evaluate(tl + ".setCumulative(true)")
    assert_last(page, "cumulative mode")

    # Wind draws on canvases in the same map pane as the tile overlays, stacked
    # by z-index at its layer's slot: the labels container must be above them.
    wid = layer(page, "Wind")["id"]
    wait_for(page, "(k) => { const s = window.geeVizWindParticles && geeVizWindParticles._adopted[k]; return !!(s && s.canvas && s.canvas.isConnected && s.canvas.style.zIndex !== ''); }", wid)
    labels_loaded(page)
    z = page.evaluate(
        "(k) => { const s = geeVizWindParticles._adopted[k];"
        " const img = [...document.querySelectorAll('#map img')].find(i => /!1sstyles!2z/.test(i.src) && atob(/!1sstyles!2z([^!&]+)/.exec(i.src)[1].replace(/-/g,'+').replace(/_/g,'/')).indexOf('s.e:g.f|p.v:off') === 0);"
        " let el = img; while (el && el.parentNode !== s.canvas.parentNode) el = el.parentNode;"
        " return {labels: el ? Number(getComputedStyle(el).zIndex) : null, wind: Number(s.canvas.style.zIndex), speed: s.speedCanvas ? Number(s.speedCanvas.style.zIndex) : null}; }",
        wid,
    )
    assert z["labels"] is not None and z["labels"] > z["wind"] and z["labels"] > z["speed"], z
    assert not page.delta_errors, page.delta_errors


def test_add_label_overlay_false_turns_it_off(live_map):
    page = live_map(build)
    url = page.url
    page.goto(url + ("&" if "?" in url else "?") + "addLabelOverlay=false")
    page.wait_for_function("window.__delta !== undefined && window.__delta.ready === true", timeout=90000)
    on_map(page, "Opaque")
    assert page.evaluate("__delta.engine.labelsOverlay()") is None
    assert page.evaluate("__delta.engine.gmap.overlayMapTypes.getArray().filter(o => o && /abels/.test(o.name || '')).length") == 0
    assert page.evaluate("(" + LABEL_TILES + ")().length") == 0
    assert not page.delta_errors, page.delta_errors


def test_labels_toggle(live_map):
    page = live_map(build)
    on_map(page, "Opaque")
    assert_last(page, "initial load")
    assert page.get_attribute("#labelsBtn", "aria-pressed") == "true"
    # Labels off: no labels overlay at all, the button says so, the URL remembers it.
    page.click("#labelsBtn")
    assert page.get_attribute("#labelsBtn", "aria-pressed") == "false"
    assert page.evaluate("__delta.engine.labelsOverlay()") is None
    assert page.evaluate("__delta.engine.gmap.overlayMapTypes.getArray().filter(o => o && /abels/.test(o.name || '')).length") == 0
    assert "addLabelOverlay=false" in page.url
    # A basemap switch while off keeps them off.
    page.evaluate("__delta.engine.setBasemap('map')")
    assert page.evaluate("__delta.engine.labelsOverlay()") is None
    # On again: the overlay for the current basemap, last above every layer.
    page.click("#labelsBtn")
    assert page.get_attribute("#labelsBtn", "aria-pressed") == "true"
    assert page.evaluate("__delta.engine.labelsOverlay().name") == "Labels"
    assert_last(page, "labels back on")
    assert "addLabelOverlay" not in page.url
    # The basemaps themselves carry no labels, so labels are never drawn twice.
    styles = page.evaluate("['roadmap-base'].map(id => JSON.stringify(__delta.engine.gmap.mapTypes.get(id).styles || []))")
    for st in styles:
        assert '"elementType":"labels"' in st and '"visibility":"off"' in st, st
    assert not page.delta_errors, page.delta_errors


def test_terrain_basemaps_draw_their_own_labels(live_map):
    """Google's terrain type can only be restyled map-wide, and map-wide styles
    unstyle overlays, so Terrain and Dark terrain draw their own labels (no
    overlay) and the toggle switches those."""
    page = live_map(build)
    on_map(page, "Opaque")
    lbl_off = "() => (__delta.engine.gmap.get('styles') || []).some(s => s.elementType === 'labels' && !s.featureType && s.stylers.some(x => x.visibility === 'off'))"
    for key in ("terrain", "darkterrain"):
        page.evaluate("(k) => __delta.engine.setBasemap(k)", key)
        assert page.evaluate("__delta.engine.gmap.getMapTypeId()") == "terrain"
        assert page.evaluate("__delta.engine.labelsOverlay()") is None
        assert page.evaluate("__delta.engine.gmap.overlayMapTypes.getArray().filter(o => o && /abels/.test(o.name || '')).length") == 0
        assert page.evaluate("__delta.engine.gmap.get('styles') !== null")
        assert not page.evaluate(lbl_off), key
        page.click("#labelsBtn")
        assert page.evaluate(lbl_off), key
        page.click("#labelsBtn")
        assert not page.evaluate(lbl_off), key
    # dark terrain darkens the land; plain terrain leaves Google's colors
    assert "\"lightness\":-80" in page.evaluate("JSON.stringify(__delta.engine.gmap.get('styles'))")
    page.evaluate("__delta.engine.setBasemap('terrain')")
    assert "\"lightness\":-80" not in page.evaluate("JSON.stringify(__delta.engine.gmap.get('styles'))")
    assert not page.delta_errors, page.delta_errors
