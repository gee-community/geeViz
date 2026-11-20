"""Delta: per-layer tile progress and retry (engine/tiles.js).

A tile layer counts the tiles on screen and how many are in; its name row
fills with that share while loading. Failed tiles are asked for again with
backoff, then counted as failed with a button to try again. Failures are made
with Playwright routes on the layer's own tile urls.

Needs Earth Engine, the local eeCreds proxy and a network.
"""
import re
import time

import pytest

pytestmark = pytest.mark.live

TILE = re.compile(r"/tiles/\d+/\d+/\d+")


def build(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    Map.addLayer(ee.Image("USGS/SRTMGL1_003"), {"min": 0, "max": 3000, "palette": "000,fff"}, "SRTM")
    Map.setCenter(-111.9, 40.7, 9)


def wait_for(page, js, arg=None, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(js, arg):
            return
        time.sleep(0.2)
    raise AssertionError("timed out waiting for " + js + " " + repr(page.evaluate("__delta.store.get().layers.map(l => [l.name, l.progress, l.loading])")))


def srtm(page):
    return page.evaluate("__delta.store.get().layers.find(l => l.name === 'SRTM')")


def row(page):
    return '#layer-list .layer[data-id="%s"]' % srtm(page)["id"]


def test_progress_reaches_every_tile_on_screen(live_map):
    page = live_map(build)
    wait_for(page, "(() => { const l = __delta.store.get().layers.find(x => x.name === 'SRTM'); return l && l.progress && l.progress.total > 0 && l.progress.loaded === l.progress.total; })()")
    p = srtm(page)["progress"]
    # the store's count is the overlay's own: every tile Google shows now
    st = page.evaluate("(id) => __delta.engine.layers.stats(id).progress", srtm(page)["id"])
    assert p == st and p["failed"] == 0
    assert not page.evaluate("(s) => document.querySelector(s).classList.contains('prog')", row(page))
    assert not page.delta_errors, page.delta_errors


def test_failed_tiles_are_retried_and_the_row_fills(live_map):
    page = live_map(build, wait_layers=False)
    fails = {}

    def flaky(route, request):
        # each tile fails twice (a 503), then loads
        k = TILE.search(request.url).group(0)
        fails[k] = fails.get(k, 0) + 1
        if fails[k] <= 2:
            route.fulfill(status=503, body="busy")
        else:
            route.continue_()

    page.route(TILE, flaky)
    try:
        # the row fills while tiles are still coming
        page.evaluate("Map.addLayer(ee.Image(7).visualize({palette: ['ff8800']}), {}, 'Flaky', true)")
        wait_for(page, "(() => { const r = [...document.querySelectorAll('#layer-list .layer')].find(x => x.textContent.includes('Flaky')); return r && r.classList.contains('prog') && r.style.getPropertyValue('--prog') !== ''; })()", timeout=60)
        wait_for(page, "(() => { const l = __delta.store.get().layers.find(x => x.name === 'Flaky'); return l && l.progress && l.progress.total > 0 && l.progress.loaded === l.progress.total; })()", timeout=90)
    finally:
        page.unroute(TILE)
    flaky_tiles = [k for k, n in fails.items() if n >= 3]
    assert flaky_tiles, fails
    lid = page.evaluate("__delta.store.get().layers.find(x => x.name === 'Flaky').id")
    assert page.evaluate("(id) => __delta.engine.layers.stats(id).progress.failed", lid) == 0


def test_tiles_that_keep_failing_are_counted_and_can_be_tried_again(live_map):
    page = live_map(build, wait_layers=False)
    page.route(TILE, lambda route, request: route.fulfill(status=404, body="no"))
    page.evaluate("Map.addLayer(ee.Image(3).visualize({palette: ['00aaff']}), {}, 'Broken', true)")
    sel = "(() => [...document.querySelectorAll('#layer-list .layer')].find(x => x.textContent.includes('Broken')))()"
    # every retry runs out (0.5 + 1 + 2 + 4 s, with jitter)
    wait_for(page, "(() => { const l = __delta.store.get().layers.find(x => x.name === 'Broken'); return l && l.progress && l.progress.total > 0 && l.progress.failed === l.progress.total; })()", timeout=60)
    n = page.evaluate("__delta.store.get().layers.find(x => x.name === 'Broken').progress.failed")
    btn = page.evaluate("(() => { const b = " + sel + ".querySelector('.tile-err'); return {hidden: b.hidden, text: b.textContent, title: b.title}; })()")
    assert not btn["hidden"] and btn["text"] == str(n), btn
    assert "failed to load after retrying" in btn["title"]
    # the service is back: try again loads them
    page.unroute(TILE)
    page.evaluate("(() => " + sel + ".querySelector('.tile-err').click())()")
    wait_for(page, "(() => { const l = __delta.store.get().layers.find(x => x.name === 'Broken'); return l.progress.failed === 0 && l.progress.loaded === l.progress.total; })()", timeout=60)
    assert page.evaluate("(() => " + sel + ".querySelector('.tile-err').hidden)()")
