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


# ---- Query: wind layers answer from viz.windQueryItem (speed, direction) ----
MAP_CENTER = (750, 437)  # the map fills the 1500 x 900 window above the 26 px status bar; panes overlay it


def wait_results(page, name):
    wait_for(
        page,
        "(n) => __delta.store.get().querying === false && __delta.store.get().results.some(r => r.title === n)",
        name,
    )
    return [r for r in page.evaluate("__delta.store.get().results") if r["title"] == name][0]


def test_wind_layer_query_reports_speed_and_direction(live_map):
    import geeViz.geeView as gv
    import geeViz.weather as wx

    page = live_map(build_layer)
    page.mouse.dblclick(*MAP_CENTER)
    r = wait_results(page, "Wind")
    assert r["kind"] == "value", r
    bands = {b["band"]: b for b in r["data"]["bands"]}
    # The speed/direction image, not the encoded u/v tile bands (vis-red ...).
    assert sorted(bands) == ["direction", "speed"], r
    assert 0 <= bands["speed"]["value"] < 150 and 0 <= bands["direction"]["value"] <= 360, bands
    assert bands["speed"]["display"].endswith(" mi/hr") and bands["direction"]["display"].endswith(" degrees"), bands

    # The same numbers as the Python earthengine-api for the same point and inputs.
    ee = gv.ee
    p, q = r["data"]["point"], page.evaluate("__delta.store.get().query")
    img = wx.windImage(ee.Image(gfs_run(ee, [0]).first()), {"units": "mi/hr"})
    kw = {"crs": q["crs"]}
    if q["transform"]:
        kw["crsTransform"] = q["transform"]
    else:
        kw["scale"] = q["scale"]
    want = img.reduceRegion(ee.Reducer.first(), ee.Geometry.Point([p["lng"], p["lat"]]), **kw).getInfo()
    assert abs(bands["speed"]["value"] - want["speed"]) < 1e-6, (bands, want)
    assert abs(bands["direction"]["value"] - want["direction"]) < 1e-6, (bands, want)
    assert not page.delta_errors, page.delta_errors


def test_wind_timelapse_query_is_a_speed_and_direction_series(live_map):
    page = live_map(build_lapse)
    wait_for(page, "(n) => { const l = __delta.store.get().layers.find(x => x.name === n); return l && l.timelapse && l.timelapse.loaded; }", "Wind TL")
    page.click(row_sel(page, "Wind TL") + " .tgl")
    page.mouse.dblclick(*MAP_CENTER)
    r = wait_results(page, "Wind TL")
    assert r["kind"] == "series", r
    names = [s["name"] for s in r["data"]["series"]]
    assert names == ["speed (m/s)", "direction (degrees)"], names
    assert len(r["data"]["x"]) == 3, r["data"]["x"]
    speed, direction = (s["y"] for s in r["data"]["series"])
    assert all(v is not None and 0 <= v < 70 for v in speed), speed
    assert all(v is not None and 0 <= v <= 360 for v in direction), direction
    assert not page.delta_errors, page.delta_errors


# ---- Legend and opacity: as the original (wind-particles.js restyleLegend,
# addParticleSlider): a color bar from the speed ramp with a particle crossing
# it, and two stacked sliders, particles over the speed field ----
SLIDE = """([sel, v]) => { const i = document.querySelector(sel); i.value = String(v);
  i.dispatchEvent(new Event('input', {bubbles: true})); }"""

ALPHAS = """(k) => { const st = geeVizWindParticles._adopted[k];
  return {particles: st.canvas.style.opacity, speed: st.speedCanvas.style.opacity, dim: st.particleDim}; }"""


def _check_legend_and_sliders(page, name, key, units):
    sel = row_sel(page, name)
    l = layer(page, name)
    assert l["legend"]["type"] == "ramp" and l["legend"]["wind"], l["legend"]
    wait_for(page, "(s) => document.querySelector(s).classList.contains('leg-open')", sel, timeout=10)
    leg = page.evaluate(
        """(s) => { const r = document.querySelector(s + ' .legend .wind-ramp');
        const c = r && r.querySelector('.wind-comet');
        const rb = r && r.getBoundingClientRect();
        return r && {ramp: r.style.background, comet: c && c.style.background,
          anim: c && getComputedStyle(c).animationName, w: rb.width, h: rb.height,
          ends: [...document.querySelectorAll(s + ' .legend .ramp-l span')].map(e => e.textContent)}; }""",
        sel,
    )
    assert leg and "linear-gradient" in leg["ramp"], leg
    assert "rgba(255, 255, 255" in leg["comet"], leg  # the default particle color
    assert leg["anim"] == "dz-wind-flow" and leg["w"] > 100 and leg["h"] >= 12, leg
    assert len(leg["ends"]) == 2 and leg["ends"][1].endswith(" " + units), leg

    # Two sliders, the particles' above the layer's, the same width.
    box = page.evaluate(
        """(s) => [...document.querySelectorAll(s + ' .lrow .opacity input')].map(i => {
          const b = i.getBoundingClientRect();
          return {cls: i.className, label: i.getAttribute('aria-label'), top: b.top, bottom: b.bottom, w: b.width, v: i.value}; })""",
        sel,
    )
    assert [b["label"] for b in box] == ["Particle opacity", "Wind speed opacity"], box
    assert box[0]["bottom"] <= box[1]["top"] and abs(box[0]["w"] - box[1]["w"]) < 1, box
    # apart enough that the two 13 px handles do not touch, in a row taller
    # than a one-slider row
    assert box[1]["top"] - box[0]["bottom"] >= 8, box
    assert page.evaluate("(s) => document.querySelector(s + ' .lrow').getBoundingClientRect().height", sel) >= 34
    assert box[0]["v"] == str(round(l["particleOpacity"] * 100)), (box, l)

    # Each fades its own canvas only.
    page.evaluate(SLIDE, [sel + " input.op-part", 30])
    wait_for(page, "(k) => geeVizWindParticles._adopted[k].canvas.style.opacity === '0.3'", key, timeout=5)
    a = page.evaluate(ALPHAS, key)
    assert a["dim"] == 0.3 and a["speed"] != "0.3", a
    assert layer(page, name)["particleOpacity"] == 0.3
    page.evaluate(SLIDE, [sel + " input.op:not(.op-part)", 45])
    wait_for(page, "(k) => geeVizWindParticles._adopted[k].speedCanvas.style.opacity === '0.45'", key, timeout=5)
    assert page.evaluate(ALPHAS, key)["particles"] == "0.3"


def test_wind_layer_legend_and_two_opacity_sliders(live_map):
    page = live_map(build_layer)
    lid = layer(page, "Wind")["id"]
    wait_paint(page, lid)
    _check_legend_and_sliders(page, "Wind", lid, "mi/hr")
    # the particles keep painting at their new opacity
    wait_paint(page, lid)
    assert not page.delta_errors, page.delta_errors


def test_wind_timelapse_legend_and_two_opacity_sliders(live_map):
    page = live_map(build_lapse)
    lid = layer(page, "Wind TL")["id"]
    wait_for(page, "(n) => { const l = __delta.store.get().layers.find(x => x.name === n); return l && l.timelapse && l.timelapse.loaded; }", "Wind TL")
    page.click(row_sel(page, "Wind TL") + " .tgl")
    wait_paint(page, "tl:" + lid)
    _check_legend_and_sliders(page, "Wind TL", "tl:" + lid, "m/s")
    assert not page.delta_errors, page.delta_errors


# ---- Loading: the row's progress fill, as every tile layer has. The tiles are
# wind-particles.js's own (never on the map), so the fill is its share in ----
FILL = """(sel) => { const el = document.querySelector(sel);
  return {prog: el.classList.contains('prog'), pct: el.style.getPropertyValue('--prog')}; }"""


def _wait_fill_full(page, name):
    sel = row_sel(page, name)
    wait_for(page, "(s) => { const el = document.querySelector(s); return el.classList.contains('prog') && el.style.getPropertyValue('--prog') === '100%'; }", sel, timeout=60)
    p = layer(page, name)["progress"]
    assert p["total"] == 100 and p["loaded"] == 100, p
    # and it stays once loaded
    page.wait_for_timeout(1500)
    assert page.evaluate(FILL, sel) == {"prog": True, "pct": "100%"}


def test_wind_layer_row_fills_as_its_tiles_load(live_map):
    page = live_map(build_layer)
    wait_paint(page, layer(page, "Wind")["id"])
    _wait_fill_full(page, "Wind")
    assert not page.delta_errors, page.delta_errors


def test_wind_timelapse_row_fills_as_its_tiles_load(live_map):
    page = live_map(build_lapse)
    lid = layer(page, "Wind TL")["id"]
    wait_for(page, "(n) => { const l = __delta.store.get().layers.find(x => x.name === n); return l && l.timelapse && l.timelapse.loaded; }", "Wind TL")
    page.click(row_sel(page, "Wind TL") + " .tgl")
    wait_paint(page, "tl:" + lid)
    _wait_fill_full(page, "Wind TL")
    # the group record is not a layer to wind-particles.js
    assert "tl:" + lid not in page.evaluate("Object.keys(window.__deltaCompat.layerObj)")
    assert not page.delta_errors, page.delta_errors
