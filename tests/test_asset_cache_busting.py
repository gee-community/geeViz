"""Shipped viewer assets must bust cache on upgrade.

geeViz cache-busts the PAGE (``geeView/?v=<timestamp>``) but that does
nothing for its sub-resources. Found the hard way: a fix to
``wind-particles.js`` did not take effect until a hard reload, and the
stale copy failed silently — the wind arrows fell through to the
viewer's default point style and rendered as dots, with no error.

Two different problems, two different answers:

* **shipped assets** change only on upgrade, so they carry
  ``?v=<geeViz version>``. Defeating caching for them would make every
  page load re-download the bundle.
* **``runGeeViz.js``** is rewritten by every ``Map.view()`` call — it is
  the layer list. It gets ``no-store`` from the request handler; a
  version stamp would be exactly wrong.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "geeViz" / "geeView" / "index.html"
GEEVIEW = ROOT / "geeViz" / "geeView.py"

#: Local assets that ship with geeViz and change only on release.
STAMPED = [
    "src/js/gena-gee-palettes.js",
    "src/js/load.min.js",
    "src/js/lcms-viewer.min.js",
    "src/js/wind-particles.js",
    "src/styles/style.min.css",
]


def _version():
    import geeViz
    return geeViz.__version__


def _html():
    return INDEX.read_text(encoding="utf-8")


@pytest.mark.parametrize("asset", STAMPED)
def test_shipped_asset_is_version_stamped(asset):
    html = _html()
    assert asset in html, f"{asset} is no longer referenced by index.html"
    m = re.search(re.escape(asset) + r"\?v=([0-9.]+)", html)
    assert m, (
        f"{asset} has no ?v= stamp — a browser will serve the previous "
        f"release's copy after an upgrade, silently")
    assert m.group(1) == _version(), (
        f"{asset} is stamped ?v={m.group(1)} but geeViz.__version__ is "
        f"{_version()} — bump the stamps when bumping the version")


def test_the_per_session_file_is_not_version_stamped():
    """runGeeViz.js changes on every Map.view(), not on release. Stamping
    it with the package version would pin the browser to the FIRST map of
    a given geeViz version and silently ignore every later one."""
    html = _html()
    assert "runGeeViz.js" in html
    assert not re.search(r"runGeeViz\.js\?v=", html), (
        "runGeeViz.js must not carry a version stamp")


def test_the_server_still_forces_no_store():
    """geeViz has ALWAYS sent no-store on every static response, and that
    is the primary defence — the version stamps are belt-and-braces for
    when these files are served by something else.

    Pinned because there must be exactly ONE ``end_headers`` on the
    handler: a second definition silently SHADOWS the first in a class
    body, and the shadowed one stops running with no error anywhere.
    That is not hypothetical — adding a second one is exactly what
    happened while writing this test.
    """
    src = GEEVIEW.read_text(encoding="utf-8")
    defs = re.findall(r"^    def end_headers\(", src, flags=re.M)
    assert len(defs) == 1, (
        f"{len(defs)} end_headers definitions on the handler — a later "
        f"one shadows the earlier, silently")
    i = src.index("def end_headers")
    body = src[i:i + 1200]
    # Anchor on the CALL's own match position. `body.index("Cache-Control")`
    # finds the docstring first — it discusses Cache-Control at length —
    # and then asserts about prose instead of code. This file's own repo
    # warns that source-grepping tests keep matching their explanations;
    # this one did it too.
    m = re.search(r"""send_header\(\s*["']Cache-Control["']\s*,\s*["']([^"']+)""",
                  body)
    assert m, "no send_header('Cache-Control', ...) call"
    assert "no-store" in m.group(1), (
        f"Cache-Control is sent as {m.group(1)!r}, not no-store")


def test_every_local_asset_is_covered_one_way_or_the_other():
    """A new local <script src="./..."> that is neither stamped nor
    no-store is a future silent-stale-cache bug. Fail here instead."""
    html = _html()
    local = set(re.findall(r'(?:src|href)="\./([^"?]+)"', html))
    # Ignore non-cacheable-by-nature assets (images/icons are fine stale).
    local = {a for a in local if a.endswith((".js", ".css"))}
    uncovered = local - set(STAMPED) - {"src/gee/gee-run/runGeeViz.js"}
    assert not uncovered, (
        f"local assets with no cache strategy: {sorted(uncovered)} — add "
        f"a ?v= stamp (shipped) or no-store (per-session)")


def test_the_proxy_serves_geeview_with_no_store():
    """``Map.view()`` rewrites ``runGeeViz.js`` in place, so the URL
    never changes while the content does.

    Starlette's ``StaticFiles`` sends ``last-modified`` and ``etag`` but
    no ``Cache-Control``, and with no explicit directive a browser may
    serve a heuristically-fresh copy without revalidating -- showing the
    PREVIOUS map, silently. geeViz's own handler forces no-store for
    exactly this reason; running behind the eeAuth proxy lost it, and
    the proxy is the default path.

    Observed before the fix, on a regenerated map:

        HTTP/1.1 200 OK
        last-modified: ...
        etag: ...
        (no Cache-Control)

    The proxy runs two ways, create_app() and ``python -m geeViz.eeAuth``
    (__main__.py); the second once mounted plain StaticFiles, so the fix
    held on one path only. Both now mount through mount_geeview, checked
    here by asking for a real file.
    """
    import re
    from pathlib import Path
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from geeViz.eeAuth.server import mount_geeview

    app = mount_geeview(FastAPI())
    r = TestClient(app).get("/geeView/delta.html")
    assert r.status_code == 200
    assert "no-store" in r.headers.get("cache-control", ""), dict(r.headers)

    root = Path(__file__).resolve().parents[2]
    for rel in ("server.py", "__main__.py"):
        src = (root / "geeViz" / "eeAuth" / rel).read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        assert re.search(r"\bmount_geeview\(app\)", code), rel + " does not mount the viewer through mount_geeview"
        assert re.search(r"\bStaticFiles\(directory=", code) is None, rel + " mounts plain StaticFiles"


def test_both_servers_agree_on_no_store():
    """geeViz can serve its own pages or sit behind the proxy. A caching
    rule that holds on one path and not the other is worse than either,
    because it only bites in one deployment."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for rel in ("geeViz/geeView.py", "geeViz/eeAuth/server.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "no-store" in src, f"{rel} does not force no-store"
