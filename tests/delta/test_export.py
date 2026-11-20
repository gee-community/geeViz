"""Delta through the other output paths: export_html (the agent's chat map and
hosted maps) and testView.

export_html pages are served the way the geeViz agent serves them
(geeViz_agent/run_ui.py): geeView/ mounted at /geeView/static, the auth
placeholders substituted at serve time (_patch_geeviz_html_auth: token "None",
token time 0, auth proxy "" so the page falls back to same-origin /ee-api,
project id), and /ee-api forwarded to an Earth Engine proxy. Here that proxy is
the user's running eeCreds proxy at 127.0.0.1:8889, which is why the browser
tests are live.
"""
import http.server
import pathlib
import re
import threading
import time
import urllib.error
import urllib.request

import pytest

GEEVIEW = pathlib.Path(__file__).resolve().parents[2] / "geeView"
EE_PROXY = "http://127.0.0.1:8889"
ASSET_BASE = "/geeView/static"


def _gv():
    import geeViz.geeView as gv

    return gv


def _patch_auth(html, project):
    # Mirror of geeViz_agent run_ui._patch_geeviz_html_auth.
    if "__GEEVIZ_TOKEN__" not in html and "__GEEVIZ_AUTH_PROXY__" not in html:
        return html
    return (
        html.replace("__GEEVIZ_TOKEN__", "None")
        .replace("__GEEVIZ_TOKEN_TIME__", "0")
        .replace("__GEEVIZ_AUTH_PROXY__", "")
        .replace("__GEEVIZ_PROJECT__", project)
    )


class _AgentLike(http.server.BaseHTTPRequestHandler):
    maps = {}  # "/maps/<name>.html" -> exported page path
    project = ""

    def log_message(self, *a, **k):
        pass

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _forward(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n) if n else None
        req = urllib.request.Request(EE_PROXY + self.path, data=data, method=self.command)
        for k in ("Content-Type", "Accept", "X-Goog-User-Project"):
            if self.headers.get(k):
                req.add_header(k, self.headers[k])
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                self._send(r.status, r.read(), r.headers.get("Content-Type", "application/octet-stream"))
        except urllib.error.HTTPError as e:
            self._send(e.code, e.read(), e.headers.get("Content-Type", "text/plain"))

    def _handle(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/ee-api/"):
            return self._forward()
        if path in self.maps:
            html = pathlib.Path(self.maps[path]).read_text(encoding="utf-8")
            return self._send(200, _patch_auth(html, self.project).encode("utf-8"), "text/html; charset=utf-8")
        if path.startswith(ASSET_BASE + "/"):
            f = (GEEVIEW / path[len(ASSET_BASE) + 1 :]).resolve()
            if GEEVIEW in f.parents and f.is_file():
                import mimetypes

                ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                if f.suffix == ".js":
                    ctype = "text/javascript"
                return self._send(200, f.read_bytes(), ctype)
        self._send(404, b"not found", "text/plain")

    do_GET = _handle
    do_POST = _handle


@pytest.fixture(scope="module")
def agent_server():
    _AgentLike.maps = {}
    _AgentLike.project = _gv().ee.data._get_state().cloud_api_user_project or ""
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _AgentLike)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def _export(Map, tmp_path, name):
    out = tmp_path / (name + ".html")
    Map.export_html(str(out))
    _AgentLike.maps["/maps/%s.html" % name] = str(out)
    return "/maps/%s.html" % name


def _open(_browser, url):
    ctx = _browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.delta_errors = []
    page.bad = []
    page.ee_api = []  # (status, url) of every /ee-api call
    page.tiles = []  # (status, content type) of every Earth Engine map tile
    page.on("pageerror", lambda e: page.delta_errors.append(str(e)))
    page.on("console", lambda m: page.delta_errors.append(m.text) if m.type == "error" else None)

    def on_response(r):
        if r.status >= 400:
            page.bad.append((r.status, r.url))
        if "/ee-api/" in r.url:
            page.ee_api.append((r.status, r.url))
        if re.search(r"/v1/projects/[^/]+/maps/[^/]+/tiles/\d+/\d+/\d+", r.url):
            page.tiles.append((r.status, r.headers.get("content-type", "")))

    page.on("response", on_response)
    page.goto(url)
    return ctx, page


def _srtm_map(skin):
    gv = _gv()
    Map = gv.mapper()
    Map.setSkin(skin)
    Map.addLayer(gv.ee.Image("USGS/SRTMGL1_003"), {"min": 0, "max": 3000}, "SRTM")
    Map.setCenter(-105.5, 39.5, 8)
    return Map


@pytest.mark.live
def test_export_html_delta_served_like_the_agent(agent_server, _browser, tmp_path):
    path = _export(_srtm_map("delta"), tmp_path, "delta")
    ctx, page = _open(_browser, agent_server + path)
    try:
        page.wait_for_function("window.__delta !== undefined && window.__delta.ready === true", timeout=90000)
        assert page.evaluate("window.__delta.eeError || null") is None
        deadline = time.time() + 60
        while time.time() < deadline and page.evaluate("__delta.store.get().layers.some(l => l.loading)"):
            time.sleep(0.5)
        layers = page.evaluate("__delta.store.get().layers.map(l => ({id: l.id, name: l.name, loading: l.loading, error: l.error}))")
        assert [l["name"] for l in layers] == ["SRTM"]
        assert layers[0]["loading"] is False and layers[0]["error"] is None, layers
        stats = page.evaluate("(id) => __delta.engine.layers.stats(id)", layers[0]["id"])
        assert stats["requests"] >= 1 and stats["onMap"], stats
        # Earth Engine was reached through the agent's same-origin /ee-api
        # (the auth proxy placeholder became "", as the agent serves it) ...
        assert page.ee_api, "no Earth Engine call went through /ee-api"
        assert all(u.startswith(agent_server + "/ee-api/") and s == 200 for s, u in page.ee_api), page.ee_api
        assert any(u.split("?")[0].endswith("/maps") for _, u in page.ee_api), page.ee_api
        # ... and the layer drew: its map tiles came back as images. Tiles
        # load from the tile url Earth Engine returns, as in the original.
        assert page.tiles, "no Earth Engine map tile was loaded"
        assert all(s == 200 and t.startswith("image/") for s, t in page.tiles), page.tiles
        # Every Delta and geeView asset resolved under the mount.
        assert [b for b in page.bad if b[1].startswith(agent_server)] == []
        assert page.delta_errors == []
    finally:
        ctx.close()


def test_export_html_delta_assets_resolve_under_mount(tmp_path):
    gv = _gv()
    Map = gv.mapper()
    Map.setSkin("delta")
    Map.addLayer(gv.ee.Image(1), {}, "one")
    out = tmp_path / "d.html"
    Map.export_html(str(out))
    html = out.read_text(encoding="utf-8")
    assert '<base href="%s/">' % ASSET_BASE in html
    refs = re.findall(r'<(?!base)\w+[^>]*?\s(?:src|href)="([^"]+)"', html)
    local = [r for r in refs if not r.startswith(("http://", "https://", "data:"))]
    assert local, refs
    for r in local:
        assert r.startswith(ASSET_BASE + "/"), r
        assert (GEEVIEW / r[len(ASSET_BASE) + 1 :]).is_file(), r
    # No relative ./ path survived the rewrite (it would resolve against
    # wherever the host serves the page, not the mount).
    assert '"./' not in html
    for ph in ("__GEEVIZ_TOKEN__", "__GEEVIZ_TOKEN_TIME__", "__GEEVIZ_PROJECT__", "__GEEVIZ_AUTH_PROXY__"):
        assert ph in html, ph


def test_export_html_delta_ten_layers_under_limit(tmp_path):
    gv = _gv()
    sizes = {}
    for skin in ("original", "delta"):
        Map = gv.mapper()
        Map.setSkin(skin)
        for i in range(10):
            Map.addLayer(gv.ee.Image(i).rename("b"), {"min": 0, "max": 10}, "Layer %d" % i)
        out = tmp_path / (skin + ".html")
        Map.export_html(str(out))
        sizes[skin] = out.stat().st_size
    limit = gv._export_max_bytes(None)
    assert 0 < sizes["delta"] < limit, sizes
    # Delta's page carries no inlined bundle: it is no larger than the
    # original's for the same map.
    assert sizes["delta"] <= sizes["original"] + 20000, sizes


@pytest.mark.live
def test_testView_delta_screenshot_no_tile_errors(monkeypatch):
    # Without websocket-client, screenshot_url falls back to a plain headless
    # screenshot with no console capture, and "no tile errors" means nothing.
    pytest.importorskip("websocket")
    Map = _srtm_map("delta")
    monkeypatch.setattr(_gv().webbrowser, "open", lambda *a, **k: True)
    from geeViz.outputLib import charts

    shot = charts.screenshot_url
    urls = []
    monkeypatch.setattr(charts, "screenshot_url", lambda url, **kw: urls.append(url) or shot(url, **kw))
    res = Map.testView(width=1200, height=800, wait_seconds=20)
    assert "error" not in res, res
    assert len(urls) == 1 and "/geeView/delta.html" in urls[0], urls
    p = pathlib.Path(res["screenshot_path"])
    try:
        assert p.is_file() and p.stat().st_size > 10000, res
        assert res["tile_errors"] == [], res
        assert not any("websocket-client" in m for m in res["console_messages"]), res
    finally:
        if p.is_file():
            p.unlink()
