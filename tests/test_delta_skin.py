"""Map.setSkin('delta') picks geeView/delta.html; the run script is shared."""
import os
import re

import pytest


def _gv():
    # test_esriLib leaves a stub in sys.modules["geeViz.geeView"]; import
    # the real module around it without disturbing the stub (same approach
    # as test_addlayer_opacity._gv).
    import importlib
    import sys
    import geeViz
    mod = sys.modules.get("geeViz.geeView")
    if mod is not None and hasattr(mod, "mapper"):
        return mod
    saved = sys.modules.pop("geeViz.geeView", None)
    had = hasattr(geeViz, "geeView")
    prev = getattr(geeViz, "geeView", None)
    try:
        return importlib.import_module("geeViz.geeView")
    finally:
        if saved is not None:
            sys.modules["geeViz.geeView"] = saved
        if had:
            geeViz.geeView = prev
        elif hasattr(geeViz, "geeView"):
            del geeViz.geeView


def _fresh(monkeypatch, env=None):
    gv = _gv()
    if env is None:
        monkeypatch.delenv("GEEVIZ_SKIN", raising=False)
    else:
        monkeypatch.setenv("GEEVIZ_SKIN", env)
    return gv, gv.mapper()


def _page(name):
    gv = _gv()
    with open(os.path.join(os.path.dirname(gv.__file__), "geeView", name),
              encoding="utf-8") as f:
        return f.read()


def _run_script(html):
    m = re.search(r"<script>([^<]*function runGeeViz\([\s\S]*?)</script>", html)
    assert m, "no inline runGeeViz script"
    return m.group(1)


def _export(m, tmp_path, name):
    import ee
    m.clearMap()
    m.addLayer(ee.Image(1), {}, "one")
    out = tmp_path / name
    m.export_html(str(out), asset_base="/base")
    return out.read_text(encoding="utf-8")


def test_default_skin_is_original(monkeypatch):
    _, m = _fresh(monkeypatch)
    assert m.skin == "original"


def test_env_selects_delta(monkeypatch):
    _, m = _fresh(monkeypatch, "delta")
    assert m.skin == "delta"
    _, m = _fresh(monkeypatch, "bogus")
    assert m.skin == "original"


def test_setSkin_rejects_unknown(monkeypatch):
    _, m = _fresh(monkeypatch)
    with pytest.raises(ValueError) as e:
        m.setSkin("nope")
    assert "original" in str(e.value) and "delta" in str(e.value)
    assert m.skin == "original"


def test_export_html_uses_delta_page(monkeypatch, tmp_path):
    _, m = _fresh(monkeypatch)
    orig = _export(m, tmp_path, "o.html")
    assert "delta/js/main.js" not in orig
    m.setSkin("delta")
    delta = _export(m, tmp_path, "d.html")
    assert "/base/delta/js/main.js" in delta
    assert _run_script(delta) == _run_script(orig)


def test_run_js_identical_across_skins(monkeypatch):
    import ee
    _, m = _fresh(monkeypatch)
    m.addLayer(ee.Image(1), {}, "one")
    a = m._build_run_js()
    m.setSkin("delta")
    assert m._build_run_js() == a


def test_delta_page_tags_match_original():
    o, d = _page("index.html"), _page("delta.html")
    patterns = [
        r'<script type="text/javascript" src="https://cdn\.jsdelivr\.net/gh/google/earthengine-api@[^"]+"[^>]*></script>',
        r'maps/api/js\?key=AIza[\w-]+',
        r'<script type="text/javascript" src="\./src/gee/gee-run/runGeeViz\.js"></script>',
    ]
    for p in patterns:
        mo, md = re.search(p, o), re.search(p, d)
        assert mo and md, p
        assert mo.group(0) == md.group(0)


def test_view_url_uses_skin_page(monkeypatch):
    gv = _gv()
    assert gv._SKIN_PAGES == {"original": "", "delta": "delta.html"}
