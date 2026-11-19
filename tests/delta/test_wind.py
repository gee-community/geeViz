"""Delta wind layers: Map.addWindLayer and Map.addWindTimeLapse draw animated
particles through the shared geeView/src/js/wind-particles.js, and turning the
layer off clears them.

Needs Earth Engine, the local eeCreds proxy and a network: every test is live.
"""
import time

import pytest

pytestmark = pytest.mark.live

# Verified against the live catalog (2026-11-19): NOAA/GFS0P25 is current (not
# deprecated); one run (creation_time 1.7942688E12) covers 2026-11-10 00:00
# with forecast hours 0..384. Band names as published.
GFS = "NOAA/GFS0P25"
U = "u_component_of_wind_10m_above_ground"
V = "v_component_of_wind_10m_above_ground"
RUN_START, RUN_END = "2026-11-10T00:00", "2026-11-10T01:00"


def gfs_run(ee, hours):
    """One GFS run, wind only, stamped with valid time (as examples/GFSTimeLapse.py)."""
    c = ee.ImageCollection(GFS).filterDate(RUN_START, RUN_END).filter(ee.Filter.inList("forecast_hours", hours))
    return c.map(lambda img: img.select([U, V]).set("system:time_start", img.get("forecast_time")))


def build_layer(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    Map.addWindLayer(ee.Image(gfs_run(ee, [0]).first()), {"units": "mi/hr"}, "Wind")
    Map.setCenter(-98, 39, 4)


def build_lapse(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    Map.addWindTimeLapse(gfs_run(ee, [0, 6, 12]), {"units": "m/s"}, "Wind TL")
    Map.setCenter(-98, 39, 4)


def layer(page, name):
    return page.evaluate("(n) => __delta.store.get().layers.find(l => l.name === n)", name)


def row_sel(page, name):
    return '#layer-list .layer[data-id="%s"]' % layer(page, name)["id"]


def wait_for(page, js, arg=None, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for " + js)


# Painted pixels on the adopted overlay's canvases: {particles, speed, running}.
PAINT = """(key) => {
  const wp = window.geeVizWindParticles;
  const st = wp && wp._adopted[key];
  if (!st) return null;
  const count = (c) => {
    if (!c || !c.width || !c.height) return 0;
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
    return n;
  };
  return {particles: count(st.canvas), speed: count(st.speedCanvas), running: st.running,
          inDom: !!(st.canvas && st.canvas.isConnected), frames: Object.keys(st.frames).length};
}"""


def wait_paint(page, key, timeout=20):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = page.evaluate(PAINT, key)
        if last and last["particles"] > 0:
            return last
        time.sleep(0.25)
    raise AssertionError("no particles drawn within %ss: %r" % (timeout, last))


def assert_cleared(page, key):
    deadline = time.time() + 3
    last = None
    while time.time() < deadline:
        last = page.evaluate(PAINT, key)
        if last and not last["running"] and last["particles"] == 0 and last["speed"] == 0:
            return
        time.sleep(0.1)
    raise AssertionError("wind not cleared after turning the layer off: %r" % (last,))


def no_jquery_notices(page):
    notices = page.evaluate("__delta.store.get().notices")
    assert not [n for n in notices if "$(" in str(n)], notices


def test_wind_layer_draws_particles_and_toggles_off(live_map):
    page = live_map(build_layer)
    lid = layer(page, "Wind")["id"]
    wait_for(page, "(k) => !!(window.geeVizWindParticles && geeVizWindParticles._adopted[k])", lid, timeout=60)
    got = wait_paint(page, lid)
    assert got["inDom"] and got["running"]
    # The grouped layer paints its own speed field from the decoded tiles.
    assert got["speed"] > 0
    # The encoded u/v RGB never goes on the map: not even briefly, so Google
    # never asks its overlay for a tile (the particles fetch their own).
    stats = page.evaluate("(id) => __delta.engine.layers.stats(id)", lid)
    assert stats["onMap"] is False and stats["requests"] == 0, stats
    no_jquery_notices(page)

    page.click(row_sel(page, "Wind") + " .tgl")
    assert layer(page, "Wind")["visible"] is False
    assert_cleared(page, lid)

    # And back on: it animates again.
    page.click(row_sel(page, "Wind") + " .tgl")
    wait_paint(page, lid)
    assert not page.delta_errors, page.delta_errors


def test_wind_timelapse_draws_particles_and_toggles_off(live_map):
    page = live_map(build_lapse)
    lid = layer(page, "Wind TL")["id"]
    wait_for(page, "(n) => { const l = __delta.store.get().layers.find(x => x.name === n); return l && l.timelapse && l.timelapse.loaded; }", "Wind TL")
    key = "tl:" + lid
    page.click(row_sel(page, "Wind TL") + " .tgl")
    wait_for(page, "(k) => !!(window.geeVizWindParticles && geeVizWindParticles._adopted[k])", key, timeout=30)
    got = wait_paint(page, key)
    assert got["frames"] == 3 and got["running"]
    stats = page.evaluate("(id) => __delta.engine.layers.stats(id)", lid)
    assert not any(f["onMap"] for f in stats["frames"]) and stats["requests"] == 0, stats

    # Stepping the lapse moves the particles to the next frame's tiles.
    first = page.evaluate("(k) => geeVizWindParticles._adopted[k].frameId", key)
    page.evaluate("(id) => __delta.engine.layers.timelapse(id).step(1)", lid)
    wait_for(page, "([k, f]) => geeVizWindParticles._adopted[k].frameId !== f", [key, first], timeout=5)
    no_jquery_notices(page)

    page.click(row_sel(page, "Wind TL") + " .tgl")
    assert_cleared(page, key)
    assert not page.delta_errors, page.delta_errors
