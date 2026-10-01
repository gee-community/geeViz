"""An exported map carries a browser key, never the server's Maps key.

From 2026-09-11 export_html stamped GOOGLE_MAPS_PLATFORM_API_KEY into
every exported page, so every deployment that set it (askterra, geeviz,
houston_26) shipped its server key - unrestricted by referrer, enabled
for Places, Routes, Solar and more - inside HTML that is served to
browsers, shared and downloaded. Anyone could lift it and bill us.

The page may only carry a key meant for browsers: GOOGLE_MAPS_BROWSER_KEY
(referrer-restricted to the deployment's sites), else the template's own.
"""
import re

import pytest

SERVER = "AIzaSERVER_KEY_must_never_reach_a_page_0000"
BROWSER = "AIzaBROWSER_KEY_referrer_restricted_00000"


def _export(tmp_path):
    # Imported at run time: test_esriLib stubs sys.modules["geeViz.geeView"]
    # during collection, so a module-level import captures the stub.
    import geeViz.geeView as gv

    m = gv.mapper()
    m.idDictList = []
    m.mapCommandList = []
    out = tmp_path / "map.html"
    m.export_html(str(out))
    return out.read_text(encoding="utf-8")


def _template_key():
    import geeViz.geeView as gv
    import os
    with open(os.path.join(os.path.dirname(gv.__file__), "geeView", "index.html"),
              encoding="utf-8") as f:
        return re.search(r"maps/api/js\?key=([\w-]+)", f.read()).group(1)


def _page_keys(html):
    return set(re.findall(r"maps/api/js\?key=([\w-]+)", html))


def test_the_server_key_never_reaches_the_page(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_PLATFORM_API_KEY", SERVER)
    monkeypatch.delenv("GOOGLE_MAPS_BROWSER_KEY", raising=False)
    html = _export(tmp_path)
    assert SERVER not in html
    assert _page_keys(html) == {_template_key()}


def test_a_browser_key_is_stamped_in(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_PLATFORM_API_KEY", SERVER)
    monkeypatch.setenv("GOOGLE_MAPS_BROWSER_KEY", BROWSER)
    html = _export(tmp_path)
    assert SERVER not in html
    assert _page_keys(html) == {BROWSER}


def test_with_no_keys_set_the_template_key_stays(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_PLATFORM_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_MAPS_BROWSER_KEY", raising=False)
    assert _page_keys(_export(tmp_path)) == {_template_key()}
