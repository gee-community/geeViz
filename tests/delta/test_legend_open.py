"""Delta: a layer's legend opens the first time the layer is on, unless the
layer has no legend (addToLegend: False). The rule itself is unit-tested in
georest tests/view/js/legendopen.test.mjs; this checks the wiring on a live map.

Needs Earth Engine, the local eeCreds proxy and a network.
"""
import time

import pytest

pytestmark = pytest.mark.live


def build(Map):
    import geeViz.geeView as gv

    ee = gv.ee
    dem = ee.Image("USGS/SRTMGL1_003")
    Map.addLayer(dem, {"min": 0, "max": 3000, "palette": "000,fff"}, "On now")
    Map.addLayer(dem, {"min": 0, "max": 3000, "palette": "000,f00"}, "On later", False)
    Map.addLayer(dem, {"min": 0, "max": 3000, "palette": "000,00f", "addToLegend": False}, "No legend")
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


def test_legend_opens_on_first_on(live_map):
    page = live_map(build)
    wait_for(page, "() => { const l = __delta.store.get().layers.find(x => x.name === 'On now'); return l && l.legend; }")
    wait_for(page, "() => __delta.store.get().layers.find(x => x.name === 'On now').legendOpen === true", timeout=10)
    assert page.locator(row_sel(page, "On now") + " .legend").is_visible()

    # added off: closed until first turned on, then open
    assert layer(page, "On later")["legendOpen"] is False
    page.click(row_sel(page, "On later") + " .tgl")
    wait_for(page, "() => __delta.store.get().layers.find(x => x.name === 'On later').legendOpen === true", timeout=60)
    assert page.locator(row_sel(page, "On later") + " .legend").is_visible()

    # first time only: closed by the user, it stays closed through off and on
    sel = row_sel(page, "On later")
    page.click(sel + " .legbtn")
    page.click(sel + " .tgl")
    page.click(sel + " .tgl")
    time.sleep(0.5)
    assert layer(page, "On later")["legendOpen"] is False

    # addToLegend: False has no legend, so nothing opens
    wait_for(page, "() => __delta.engine.layers.stats(__delta.store.get().layers.find(x => x.name === 'No legend').id).onMap")
    time.sleep(0.5)
    nl = layer(page, "No legend")
    assert nl["legend"] is None and nl["legendOpen"] is False
    assert not page.delta_errors, page.delta_errors
