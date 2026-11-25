"""geeViz serves geoView's files (georest.view) at /geoview: the 8889 proxy
(eeAuth) and the in-process fallback server both."""
import http.server
import threading
import urllib.request

import pytest


def test_the_proxy_serves_geoview():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from geeViz.eeAuth.server import mount_geeview
    app = mount_geeview(FastAPI())
    c = TestClient(app)
    r = c.get("/geoview/geoview.html")
    assert r.status_code == 200 and "geoview-document" in r.text
    assert "no-store" in r.headers["cache-control"]
    assert c.get("/geoview/js/main.js").status_code == 200
    # geeViz's own files (the original skin, the run scripts) are still there
    assert c.get("/geeView/index.html").status_code == 200


def test_the_fallback_server_serves_geoview():
    import geeViz.geeView as gv
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), gv._GeeVizRequestHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        with urllib.request.urlopen(base + "/geoview/geoview.html", timeout=10) as r:
            assert r.status == 200 and b"geoview-document" in r.read()
        with urllib.request.urlopen(base + "/geoview/js/main.js", timeout=10) as r:
            assert r.status == 200
        with urllib.request.urlopen(base + "/geeView/index.html", timeout=10) as r:
            assert r.status == 200
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/geoview/../geeView.py", timeout=10)
    finally:
        srv.shutdown()
