"""Map.setSkin('geoview') picks geoView (georest.view), which reads the map as a
document; the original skin keeps its page and run script."""
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


def _geoview(name):
    from georest.view import STATIC_DIR
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as f:
        return f.read()


def _document(html):
    import json
    m = re.search(r'<script type="application/json" id="geoview-document">(\{.*?)</script>', html, re.S)
    assert m, "no inline map document"
    return json.loads(m.group(1))


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


def test_default_skin_is_geoview(monkeypatch):
    gv, m = _fresh(monkeypatch)
    assert m.skin == "geoview" == gv.DEFAULT_SKIN
    # and the module's own Map, made at import time
    assert gv.Map.skin in gv.SKINS


def test_env_selects_the_skin(monkeypatch):
    _, m = _fresh(monkeypatch, "original")
    assert m.skin == "original"
    _, m = _fresh(monkeypatch, " Original ")
    assert m.skin == "original"
    _, m = _fresh(monkeypatch, "geoview")
    assert m.skin == "geoview"
    _, m = _fresh(monkeypatch, "bogus")
    assert m.skin == "geoview"


def test_setSkin_rejects_unknown(monkeypatch):
    _, m = _fresh(monkeypatch)
    with pytest.raises(ValueError) as e:
        m.setSkin("nope")
    assert "original" in str(e.value) and "geoview" in str(e.value)
    assert m.skin == "geoview"


def test_export_html_uses_geoview_page(monkeypatch, tmp_path):
    _, m = _fresh(monkeypatch)
    default = _export(m, tmp_path, "default.html")
    assert '<base href="/base/geoview/">' in default and "./js/main.js" in default
    m.setSkin("original")
    orig = _export(m, tmp_path, "o.html")
    assert "geoview" not in orig
    m.setSkin("geoview")
    delta = _export(m, tmp_path, "d.html")
    assert '<base href="/base/geoview/">' in delta
    # the same map: the original's run script and Delta's document
    assert '"one"' in _run_script(orig)
    assert [l["name"] for l in _document(delta)["layers"]] == ["one"]


def test_the_original_run_script_does_not_depend_on_the_skin(monkeypatch):
    import ee
    _, m = _fresh(monkeypatch)
    m.addLayer(ee.Image(1), {}, "one")
    m.setSkin("original")
    a = m._build_run_js()
    m.setSkin("geoview")
    m._build_document()
    m.setSkin("original")
    assert m._build_run_js() == a


def test_delta_page_shares_the_maps_key_with_the_original():
    o, d = _page("index.html"), _geoview("geoview.html")
    p = r'maps/api/js\?key=AIza[\w-]+'
    assert re.search(p, o).group(0) == re.search(p, d).group(0)
    assert "libraries=places,geometry" in re.search(r"maps/api/js\?[^\"]+", d).group(0)
    # Earth Engine loads only for a map that needs it: no script tag
    assert "earthengine-api" not in re.sub(r"<!--.*?-->", "", d, flags=re.S)




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
    delta = _spy_view(monkeypatch, m, mode, "geoview")
    assert "/geoview/geoview.html?" in delta and "doc=" in delta
    assert "geoview" not in orig
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
    delta = _spy_iframe_view(monkeypatch, m, env, "geoview")
    host = "https://colab.example.com/" if env == "colab" else "https://wb.example.com/proxy/"
    assert orig.startswith(host) and delta.startswith(host), (orig, delta)
    assert "/geoview/geoview.html?" in delta
    assert "/geeView/?" in orig and "geoview" not in orig


@pytest.mark.parametrize("skin", ["original", "geoview"])
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
    assert shots[0].startswith("http://127.0.0.1:8123/" + gv._SKIN_PAGES[skin] + "?v=")
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
    state = _geoview(os.path.join("js", "state.js"))
    assert "turnOffLayersWhenTimeLapseIsOn: false" in state


@pytest.mark.parametrize("mode", ["local", "detached"])
def test_delta_view_loads_its_own_document(monkeypatch, mode):
    """Two notebooks viewing at once each write their own map document
    (map-<token>-<hash>.json), so a geoView page keeps its own layers. The original
    skin is unchanged."""
    import ee
    import json
    gv, m = _fresh(monkeypatch)
    m.addLayer(ee.Image(1), {}, "mine")
    orig = _spy_view(monkeypatch, m, mode, "original")
    assert "doc=" not in orig
    url = _spy_view(monkeypatch, m, mode, "geoview")
    name = re.search(r"[?&]doc=\.\./geeView/src/gee/gee-run/(map-([0-9a-f]+)-[0-9a-f]+\.json)(?:&|$)", url)
    assert name.group(2) == m._run_token
    own = os.path.join(gv.ee_run_dir, name.group(1))
    # another Map (another notebook) viewing afterwards writes its own document
    _, other = _fresh(monkeypatch)
    other.addLayer(ee.Image(2), {}, "theirs")
    url2 = _spy_view(monkeypatch, other, mode, "geoview")
    assert [l["name"] for l in json.load(open(own, encoding="utf-8"))["layers"]] == ["mine"]
    name2 = re.search(r"(map-([0-9a-f]+)-[0-9a-f]+\.json)", url2)
    assert name2.group(2) != name.group(2)
    os.remove(own)
    os.remove(os.path.join(gv.ee_run_dir, name2.group(1)))


@pytest.mark.parametrize("mode", ["local", "detached"])
def test_each_view_keeps_its_own_map(monkeypatch, mode):
    """A notebook that views one Map, changes it and views it again keeps
    both maps: the first output still shows the first map. Viewing an
    unchanged map again reuses its document."""
    import ee
    import json
    gv, m = _fresh(monkeypatch)
    m.addLayer(ee.Image(1), {}, "first")
    url1 = _spy_view(monkeypatch, m, mode, "geoview")
    again = _spy_view(monkeypatch, m, mode, "geoview")
    m.clearMap()
    m.addLayer(ee.Image(2), {}, "second")
    url2 = _spy_view(monkeypatch, m, mode, "geoview")
    doc = lambda u: os.path.join(gv.ee_run_dir, re.search(r"(map-[0-9a-f]+-[0-9a-f]+\.json)", u).group(1))
    assert doc(url1) == doc(again)
    assert doc(url1) != doc(url2)
    assert [l["name"] for l in json.load(open(doc(url1), encoding="utf-8"))["layers"]] == ["first"]
    assert [l["name"] for l in json.load(open(doc(url2), encoding="utf-8"))["layers"]] == ["second"]
    os.remove(doc(url1))
    os.remove(doc(url2))

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


# ---- refresh_exported_html: a saved map rebuilt on today's viewer ----

def test_refresh_moves_a_saved_map_onto_todays_viewer(monkeypatch, tmp_path):
    gv, m = _fresh(monkeypatch)
    m.setSkin("original")
    saved = _export(m, tmp_path, "saved.html")
    # a map saved with a run script moves to geoView carrying that script
    page = gv.refresh_exported_html(saved)
    assert _run_script(page) == _run_script(saved)
    assert "./js/main.js" in page and '<base href="/base/geoview/">' in page
    # and back, and idempotent
    assert gv.refresh_exported_html(page, "original") == saved
    assert gv.refresh_exported_html(page, "geoview") == page
    # GEEVIZ_SKIN picks the default, as for a new Map
    monkeypatch.setenv("GEEVIZ_SKIN", "original")
    assert gv.refresh_exported_html(page) == saved


def test_refresh_keeps_a_delta_maps_document(monkeypatch, tmp_path):
    gv, m = _fresh(monkeypatch)
    m.setSkin("geoview")
    now = _export(m, tmp_path, "now.html")
    assert gv.refresh_exported_html(now, "geoview") == now
    with pytest.raises(ValueError, match="geoView"):
        gv.refresh_exported_html(now, "original")


def test_refresh_keeps_the_run_script_asset_base_and_placeholders(monkeypatch, tmp_path):
    gv, m = _fresh(monkeypatch)
    import ee
    m.setSkin("original")
    m.clearMap()
    m.addLayer(ee.Image(1), {}, "one</b>")
    out = tmp_path / "custom.html"
    m.export_html(str(out), asset_base="/elsewhere/static", token_placeholder="TOK",
                  token_time_placeholder="0", project_placeholder="PROJ",
                  auth_proxy_placeholder="/proxy")
    saved = out.read_text(encoding="utf-8")
    page = gv.refresh_exported_html(saved, "geoview")
    assert _run_script(page) == _run_script(saved)
    assert '<base href="/elsewhere/static/geoview/">' in page
    assert "./js/main.js" in page
    assert "urlParams.accessToken='TOK';" in page and "urlParams.projectID='PROJ';" in page
    assert "urlParams.geeAuthProxyURL='/proxy';" in page

def test_refresh_refuses_a_page_it_did_not_write(monkeypatch):
    gv, _ = _fresh(monkeypatch)
    for html in ("<html><body>a chart</body></html>",
                 '<base href="/x/"><script>function runGeeViz(){}</script>'):
        with pytest.raises(ValueError, match="export_html"):
            gv.refresh_exported_html(html)
    with pytest.raises(ValueError, match="Unknown skin"):
        gv.refresh_exported_html("", "neon")


def test_rebuilding_a_page_needs_no_earth_engine():
    """A host serving saved maps (askterra's server) rebuilds them without
    initializing Earth Engine: geeViz.viewerPages imports neither ee nor
    geeViz.geeView, and geeView re-exports the same function."""
    import subprocess
    import sys as _sys
    code = ("import sys, geeViz.viewerPages as vp; "
            "print(sorted(m for m in ('ee', 'geeViz.geeView') if m in sys.modules)); "
            "print(vp.refresh_exported_html.__module__)")
    out = subprocess.run([_sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                         cwd=os.path.dirname(os.path.dirname(_gv().__file__)))
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["[]", "geeViz.viewerPages"], out.stdout
    assert _gv().refresh_exported_html.__module__ == "geeViz.viewerPages"


def test_delta_is_the_old_name_for_geoview(monkeypatch):
    # scripts and saved pages from before the rename still say "delta"
    gv, m = _fresh(monkeypatch, "delta")
    assert m.skin == "geoview"
    m.setSkin("original")
    m.setSkin("Delta")
    assert m.skin == "geoview"
    assert "delta" not in gv.SKINS


def test_a_saved_page_refreshes_under_the_old_skin_name(monkeypatch, tmp_path):
    gv, m = _fresh(monkeypatch)
    page = _export(m, tmp_path, "saved.html")
    assert gv.refresh_exported_html(page, "delta") == gv.refresh_exported_html(page, "geoview")
