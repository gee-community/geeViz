"""Fixtures for the Delta viewer browser tests.

delta_page serves geeView/ from a local http.server (127.0.0.1, free port) and
blocks every third-party request, so shell tests are fast and offline-safe.
live_map builds a real geeViz map with the delta skin (needs Earth Engine).
"""

import functools
import http.server
import pathlib
import threading
import time
from urllib.parse import urlencode

import pytest

GEEVIEW = pathlib.Path(__file__).resolve().parents[2] / "geeView"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs Earth Engine credentials and network (deselect with -m 'not live')")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass


@pytest.fixture(scope="session")
def delta_server():
    # the Delta skin's viewer is geoView, from the installed georest
    from georest.view import STATIC_DIR
    handler = functools.partial(_Quiet, directory=str(STATIC_DIR))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


# Per test file, not per session: Playwright's sync API runs an asyncio
# event loop in the main thread while it is open, and a session-long browser
# kept it running through the rest of the suite, so every later test calling
# asyncio.run (the MCP server tests) failed with "cannot be called from a
# running event loop".
@pytest.fixture(scope="module")
def _browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _collect_errors(page):
    page.delta_errors = []
    page.on("pageerror", lambda e: page.delta_errors.append(str(e)))
    page.on(
        "console",
        lambda m: page.delta_errors.append(m.text) if m.type == "error" else None,
    )


@pytest.fixture
def delta_page(delta_server, _browser):
    """delta_page(url_params, viewport=None, color_scheme=None) -> Page."""
    contexts = []

    def make(url_params=None, viewport=None, color_scheme=None):
        ctx = _browser.new_context(
            viewport=viewport or {"width": 1500, "height": 900},
            color_scheme=color_scheme or "light",
        )
        contexts.append(ctx)
        # Shell tests never need Google, Earth Engine or CDN assets.
        ctx.route(
            "**/*",
            lambda route: route.continue_()
            if route.request.url.startswith(delta_server)
            else route.abort(),
        )
        page = ctx.new_page()
        _collect_errors(page)
        qs = urlencode(url_params or {})
        page.goto(delta_server + "/geoview.html" + ("?" + qs if qs else ""))
        page.wait_for_function("window.__delta !== undefined")
        return page

    yield make
    for c in contexts:
        c.close()


@pytest.fixture
def live_map(_browser):
    """live_map(build, skin="geoview", setup=None, wait_layers=True) -> Page.

    build(Map) adds layers; needs Earth Engine. setup(context) runs before the
    page opens (to route requests). With wait_layers=False the page is
    returned once Delta is ready, without waiting for layers to load.
    With skin="original" the original viewer opens and the page is returned
    as soon as it has loaded; the caller waits for what it needs.
    """
    contexts = []

    def make(build, skin="geoview", setup=None, wait_layers=True):
        import geeViz.geeView as gv

        Map = gv.mapper()
        Map.setSkin(skin)
        build(Map)
        # view() returns None; it hands the viewer URL to webbrowser.open, so
        # capture it there (nothing opens). It uses the already-running local
        # eeCreds proxy.
        opened = []
        orig = gv.webbrowser.open
        gv.webbrowser.open = lambda u, new=0, **k: opened.append(u) or True
        try:
            Map.view(open_browser=True, open_iframe=False)
        finally:
            gv.webbrowser.open = orig
        assert len(opened) == 1, opened
        url = opened[0]
        ctx = _browser.new_context(viewport={"width": 1500, "height": 900})
        contexts.append(ctx)
        if setup is not None:
            setup(ctx)
        page = ctx.new_page()
        _collect_errors(page)
        page.goto(url)
        if skin != "geoview":
            return page
        page.wait_for_function("window.__delta !== undefined && window.__delta.ready === true", timeout=90000)
        if not wait_layers:
            return page
        deadline = time.time() + 60
        while time.time() < deadline:
            if not page.evaluate("window.__delta.store.get().layers.some(l => l.loading)"):
                break
            time.sleep(0.5)
        return page

    yield make
    for c in contexts:
        c.close()
