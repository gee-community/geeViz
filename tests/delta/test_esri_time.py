"""A time-enabled ArcGIS service as a Delta timelapse, with no Earth Engine:
one frame per catalog year, drawn with the service's time parameter, the
same play and step controls as an Earth Engine timelapse, the service's
legend, and a Query click that gives the values over time.

Needs the local eeCreds proxy (it serves the page) and a network.
"""
import time

import pytest

pytestmark = pytest.mark.live

LCMS = "https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_LCMS_AnnualChange_CONUS/ImageServer"
CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
MAP_CENTER = (750, 437)


def build(Map):
    Map.addTimeLapse(LCMS, {}, "LCMS change")
    Map.setCenter(-105.65, 40.6, 11)
    Map.turnOnInspector()


def wait_for(page, js, arg=None, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for " + js)


def layer(page):
    return page.evaluate("__delta.store.get().layers[0]")


def test_an_esri_timelapse_plays_with_no_earth_engine(live_map):
    seen = []

    def setup(ctx):
        ctx.set_extra_http_headers({"User-Agent": CHROME_UA})
        ctx.on("request", lambda req: seen.append(req.url))

    page = live_map(build, setup=setup, wait_layers=False)
    wait_for(page, "() => __delta.store.get().layers.length === 1")
    l = layer(page)
    assert l["kind"] == "esri.timelapse" and l["visible"] is False
    # timelapses start off; turning one on loads its frames
    page.evaluate("(id) => __delta.store.update(s => ({...s, layers: s.layers.map(x => x.id === id ? {...x, visible: true} : x)}), 'test')", l["id"])
    wait_for(page, "() => { const l = __delta.store.get().layers[0]; return l.timelapse && l.timelapse.loaded; }")
    time.sleep(2)
    # only the year shown and the next two are asked for, as 1024 px blocks
    first = {u.split("time=")[1].split("&")[0] for u in seen if "/exportImage?" in u and "time=" in u}
    assert 1 <= len(first) <= 3, sorted(first)
    assert all("size=1024%2C1024" in u for u in seen if "/exportImage?" in u), [u for u in seen if "/exportImage?" in u][:2]
    l = layer(page)
    assert l["error"] is None, l
    years = l["timelapse"]["years"]
    assert years[0] == "1985" and len(years) >= 40, years
    assert l["legend"]["type"] == "images" and len(l["legend"]["items"]) == 16
    sel = '#layer-list .layer[data-id="%s"]' % l["id"]
    f0 = layer(page)["timelapse"]["frame"]
    page.click(sel + " [data-tl=forward]")
    assert layer(page)["timelapse"]["frame"] == (f0 + 1) % len(years)
    page.click(sel + " [data-tl=play]")
    time.sleep(1.5)
    assert layer(page)["timelapse"]["playing"] is True
    page.click(sel + " [data-tl=pause]")
    # each frame asks for its own year
    wait_for(page, "() => true")
    stamps = [u for u in seen if "/exportImage?" in u and "time=" in u]
    assert len({u.split("time=")[1].split("&")[0] for u in stamps}) >= 2, stamps[:3]
    # the values over time at a point
    page.evaluate("() => __delta.store.set({results: []}, 'test')")
    page.mouse.click(*MAP_CENTER)
    wait_for(page, "() => __delta.store.get().querying === false && __delta.store.get().results.length > 0", timeout=60)
    r = page.evaluate("__delta.store.get().results[0]")
    assert r["kind"] == "series" and r["data"]["x"][0] == "1985", r
    # the line is colored by class, as an Earth Engine class series is
    cc = r["data"]["series"][0]["classColors"]
    assert cc and sum(1 for c in cc if c) >= len(cc) - 2, cc
    assert [u for u in seen if "ee_api_js" in u or "/ee-api/" in u] == []
