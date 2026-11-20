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
    assert "libraries=places,geometry" in re.search(r"maps/api/js\?[^\"]+", d).group(0)




def _spy_view(monkeypatch, m, mode, skin):
    """Run view() under `skin`; return the URL it hands to the browser."""
    gv = _gv()
    opened = []
    monkeypatch.setattr(gv.webbrowser, "open", lambda u, new=0: opened.append(u))
    monkeypatch.setattr(gv.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(gv, "_ensure_server", lambda port: port)
    monkeypatch.setattr(gv, "_set_ee_api_upstream", lambda *_a: None)
    if mode == "local":
        m.setAuthMode("legacy")
    else:
        m.setAuthMode(None)
        # the default mode, whatever the session set (eeAuth/tests' conftest
        # forces legacy for every test in the run when it is collected)
        monkeypatch.delenv("GEEVIZ_EEAUTH_MODE", raising=False)
        import importlib  # the singleton itself: see the testView test below
        monkeypatch.setattr(
            importlib.import_module("geeViz.eeAuth.eeCreds").eeCreds, "ensure_started",
            lambda **kw: {"proxy_url": "http://127.0.0.1:8123", "current": "t",
                          "tenants": ["t"], "mode": "detached"})
    m.setSkin(skin)
    m.view(open_browser=True, open_iframe=False)
    assert len(opened) == 1
    return opened[0]


@pytest.mark.parametrize("mode", ["local", "detached"])
def test_view_url_uses_skin_page_per_branch(monkeypatch, mode):
    import ee
    _, m = _fresh(monkeypatch)
    m.addLayer(ee.Image(1), {}, "one")
    orig = _spy_view(monkeypatch, m, mode, "original")
    delta = _spy_view(monkeypatch, m, mode, "delta")
    assert "/geeView/delta.html" in delta
    assert "delta.html" not in orig
    assert "/geeView/" in orig


def _spy_iframe_view(monkeypatch, m, env, skin):
    """Run view() in a mocked Colab or Workbench; return the IFrame src."""
    gv = _gv()
    frames = []
    monkeypatch.setattr(gv, "IFrame", lambda src, **kw: frames.append(src) or src)
    monkeypatch.setattr(gv, "display", lambda *_a, **_k: None)
    monkeypatch.setattr(gv, "_ensure_server", lambda port: port)
    monkeypatch.setattr(gv, "_set_ee_api_upstream", lambda *_a: None)
    monkeypatch.setattr(gv, "_detect_proxy_url", lambda: "https://wb.example.com/lab/tree")
    m.setAuthMode("legacy")
    if env == "colab":
        monkeypatch.setattr(gv, "IS_COLAB", True)
        monkeypatch.setattr(gv, "eval_js", lambda js: "https://colab.example.com", raising=False)
    else:
        monkeypatch.setattr(gv, "IS_COLAB", False)
        monkeypatch.setattr(gv, "IS_WORKBENCH", True)
        m.proxy_url = None
    m.setSkin(skin)
    m.view()
    assert len(frames) == 1, frames
    return frames[0]


@pytest.mark.parametrize("env", ["colab", "workbench"])
def test_view_url_uses_skin_page_in_notebook_hosts(monkeypatch, env):
    import ee
    _, m = _fresh(monkeypatch)
    m.addLayer(ee.Image(1), {}, "one")
    orig = _spy_iframe_view(monkeypatch, m, env, "original")
    delta = _spy_iframe_view(monkeypatch, m, env, "delta")
    host = "https://colab.example.com/geeView/" if env == "colab" else "https://wb.example.com/proxy/"
    assert orig.startswith(host) and delta.startswith(host), (orig, delta)
    assert "/geeView/delta.html?" in delta
    assert "/geeView/?" in orig and "delta.html" not in orig


@pytest.mark.parametrize("skin", ["original", "delta"])
def test_testView_screenshots_the_page_view_built(monkeypatch, skin):
    import ee
    gv = _gv()
    from geeViz.outputLib import charts
    _, m = _fresh(monkeypatch)
    m.addLayer(ee.Image(1), {}, "one")
    shots, opened, frames = [], [], []
    monkeypatch.setattr(charts, "screenshot_url",
                        lambda url, **kw: shots.append(url) or (None, ["stub"]))
    monkeypatch.setattr(gv.webbrowser, "open", lambda u, new=0: opened.append(u))
    monkeypatch.setattr(gv, "IFrame", lambda src, **kw: frames.append(src))
    monkeypatch.setattr(gv, "display", lambda *_a, **_k: None)
    monkeypatch.setattr(gv.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(gv, "_ensure_server", lambda port: port)
    monkeypatch.setattr(gv, "_set_ee_api_upstream", lambda *_a: None)
    # The singleton view() imports (from geeViz.eeAuth.eeCreds import eeCreds).
    # Not "from geeViz.eeAuth import eeCreds": once any test imports the
    # submodule geeViz.eeAuth.eeCreds, that package attribute is the MODULE,
    # the patch misses the singleton, and view() falls back to a legacy URL.
    import importlib
    ec_inst = importlib.import_module("geeViz.eeAuth.eeCreds").eeCreds
    monkeypatch.setattr(
        ec_inst, "ensure_started",
        lambda **kw: {"proxy_url": "http://127.0.0.1:8123", "current": "t",
                      "tenants": ["t"], "mode": "detached"})
    m.setAuthMode(None)
    monkeypatch.delenv("GEEVIZ_EEAUTH_MODE", raising=False)  # as above
    m.setSkin(skin)
    res = m.testView()
    # It screenshots the page view() built, without opening a browser or
    # an inline frame of its own.
    assert len(shots) == 1, res
    assert shots[0] == m.view_url
    assert shots[0].startswith("http://127.0.0.1:8123/geeView/" + gv._SKIN_PAGES[skin] + "?v=")
    assert opened == [] and frames == []
    assert res == {"error": "Screenshot failed.", "console_messages": ["stub"]}


def test_timelapse_turn_off_default_belongs_to_each_skin(monkeypatch):
    """Unset, the run script leaves turnOffLayersWhenTimeLapseIsOn to the skin
    (the original turns other layers off, Delta keeps them on, stacked in
    list order); set, it is written for either skin."""
    import ee
    _, m = _fresh(monkeypatch)
    m.addLayer(ee.Image(1), {}, "one")
    assert m.turnOffLayersWhenTimeLapseIsOn is None
    assert "turnOffLayersWhenTimeLapseIsOn" not in m._build_run_js()
    for v in (True, False):
        m.turnOffLayersWhenTimeLapseIsOn = v
        assert "Map.turnOffLayersWhenTimeLapseIsOn = %s;" % str(v).lower() in m._build_run_js()
    # the original's own default is on
    src = open(os.path.join(os.path.dirname(_gv().__file__), "geeView", "src", "js", "lcms-viewer.min.js"), encoding="utf-8").read()
    assert re.search(r"turnOffLayersWhenTimeLapseIsOn\s*=\s*(!0|true)", src)
    # Delta's is off
    state = _page(os.path.join("delta", "js", "state.js"))
    assert "turnOffLayersWhenTimeLapseIsOn: false" in state


@pytest.mark.parametrize("mode", ["local", "detached"])
def test_delta_view_loads_its_own_run_script(monkeypatch, mode):
    """Two notebooks viewing at once both rewrite the shared runGeeViz.js; a
    Delta page names its own Map's script (?run=<token>) so it keeps its own
    layers. The original skin is unchanged."""
    import ee
    gv, m = _fresh(monkeypatch)
    m.addLayer(ee.Image(1), {}, "mine")
    orig = _spy_view(monkeypatch, m, mode, "original")
    assert "run=" not in orig
    url = _spy_view(monkeypatch, m, mode, "delta")
    tok = re.search(r"[?&]run=([0-9a-f]+)(?:&|$)", url).group(1)
    assert tok == m._run_token
    own = os.path.join(gv.ee_run_dir, "runGeeViz-%s.js" % tok)
    shared = os.path.join(gv.ee_run_dir, "runGeeViz.js")
    assert open(own, encoding="utf-8").read() == open(shared, encoding="utf-8").read()
    # another Map (another notebook) viewing afterwards changes only the shared file
    _, other = _fresh(monkeypatch)
    other.addLayer(ee.Image(2), {}, "theirs")
    _spy_view(monkeypatch, other, mode, "delta")
    assert '"mine"' in open(own, encoding="utf-8").read()
    assert '"theirs"' in open(shared, encoding="utf-8").read()
    # the page loads the named script after the shared one, and only a token
    page = _page("delta.html")
    assert page.index("gee-run/runGeeViz.js") < page.index("gee-run/runGeeViz-")
    assert "run=([0-9a-f]{8,32})" in page
    os.remove(own)


def test_old_own_run_scripts_are_removed(tmp_path):
    gv = _gv()
    old = tmp_path / "runGeeViz-aaaaaaaaaaaaaaaa.js"
    old.write_text("x")
    keep = tmp_path / "runGeeViz-bbbbbbbbbbbbbbbb.js"
    keep.write_text("y")
    shared = tmp_path / "runGeeViz.js"
    shared.write_text("z")
    now = os.path.getmtime(keep)
    os.utime(old, (now - 8 * 24 * 3600, now - 8 * 24 * 3600))
    os.utime(shared, (now - 30 * 24 * 3600, now - 30 * 24 * 3600))
    gv._write_own_run_script(str(tmp_path), "cccccccccccccccc", "w", now=now)
    assert not old.exists() and keep.exists() and shared.exists()
    assert (tmp_path / "runGeeViz-cccccccccccccccc.js").read_text() == "w"
