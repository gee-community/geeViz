"""Delta: each Map's page reads that Map's own document (?doc=.../map-<token>-<hash>.json),
so another notebook's Map.view() does not change a page that is open or
reloaded.

Needs Earth Engine, the local eeCreds proxy and a network.
"""
import pytest

pytestmark = pytest.mark.live


def mine(Map):
    import geeViz.geeView as gv

    Map.addLayer(gv.ee.Image(1), {}, "Mine")
    Map.setCenter(-111.9, 40.7, 9)


def test_another_maps_view_does_not_replace_this_one(live_map):
    page = live_map(mine, wait_layers=False)
    assert "doc=" in page.url
    names = "__delta.store.get().layers.map(l => l.name)"
    page.wait_for_function("__delta.store.get().layers.length > 0")
    assert page.evaluate(names) == ["Mine"]

    # another notebook's Map views (rewriting the shared run script)
    import geeViz.geeView as gv

    other = gv.mapper()
    other.setSkin("geoview")
    other.addLayer(gv.ee.Image(2), {}, "Theirs")
    opened = []
    orig = gv.webbrowser.open
    gv.webbrowser.open = lambda u, new=0, **k: opened.append(u) or True
    try:
        other.view(open_browser=True, open_iframe=False)
    finally:
        gv.webbrowser.open = orig
    assert opened and "Theirs" in open(gv.os.path.join(gv.ee_run_dir, "runGeeViz.js"), encoding="utf-8").read()

    page.reload()
    page.wait_for_function("window.__delta && window.__delta.ready === true", timeout=90000)
    page.wait_for_function("__delta.store.get().layers.length > 0")
    assert page.evaluate(names) == ["Mine"]
    assert not page.delta_errors, page.delta_errors
