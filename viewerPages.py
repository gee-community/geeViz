"""The viewer pages: which skins there are, and the page ``Map.export_html``
writes for each.

Kept apart from :mod:`geeViz.geeView`, which initializes Earth Engine on
import, so a host that serves saved maps (askterra) can rebuild one on
today's viewer with :func:`refresh_exported_html` without touching Earth
Engine. :mod:`geeViz.geeView` re-exports everything here.
"""
import os

_here = os.path.dirname(__file__)
template = os.path.join(_here, "geeView", "index.html")

# Viewer skins. "original" is geeView/index.html, which runs the per-session
# runGeeViz.js. "delta" is geoView, from the installed georest
# (georest.view: its page and files, served at /geoview), which reads the
# map as a document (mapper._build_document) instead of a script.
SKINS = ("original", "delta")
# The skin a Map starts with when GEEVIZ_SKIN does not name one.
DEFAULT_SKIN = "delta"
def _geoview_page():
    from georest.view import STATIC_DIR
    return os.path.join(STATIC_DIR, "geoview.html")


delta_template = _geoview_page()


def _sign_in_script(token_placeholder, token_time_placeholder, project_placeholder, auth_proxy_placeholder):
    """The Earth Engine sign-in settings an exported page carries (the host
    fills the placeholders when it serves the page)."""
    return (
        "<script>(function(){"
        "  if(typeof urlParams==='undefined'){window.urlParams={};}"
        "  urlParams.accessToken='" + token_placeholder + "';"
        "  urlParams.accessTokenCreationTime=" + token_time_placeholder + ";"
        "  urlParams.projectID='" + project_placeholder + "';"
        "  urlParams.geeAuthProxyURL='" + auth_proxy_placeholder + "';"
        "})();</script>\n"
    )


def _delta_page(doc, run_js, asset_base, placeholders):
    """The Delta skin's exported page: georest.view's page (its files under
    ``asset_base + "/geoview"``) with the map document inline, or, for a page
    saved before the document, its run script."""
    from georest.view._page import page_html
    extra = _sign_in_script(*placeholders)
    if run_js:
        extra += "<script>" + run_js + "</script>"
    key = os.environ.get("GOOGLE_MAPS_BROWSER_KEY", "").strip() or None
    return page_html(doc, asset_base.rstrip("/") + "/geoview", key, extra_head_html=extra)


def _export_page(run_js, skin, asset_base, token_placeholder, token_time_placeholder,
                 project_placeholder, auth_proxy_placeholder, doc=None):
    """The page :meth:`mapper.export_html` writes, for a run script and a skin.

    Shared with :func:`refresh_exported_html`, which rebuilds a page saved
    earlier around the run script it carries, so the two cannot drift apart.
    """
    if skin == "delta":
        return _delta_page(doc, None if doc is not None else run_js, asset_base,
                           (token_placeholder, token_time_placeholder, project_placeholder, auth_proxy_placeholder))
    with open(template, "r", encoding="utf-8") as f:
        html = f.read()

    # The template hard-codes geeViz's own Google Maps key, which is
    # HTTP-referrer-restricted to geeViz's domains (plus localhost -
    # which is why every local test passes and every OTHER deployment
    # fails with RefererNotAllowedMapError and a blank grey map). A
    # deployment supplies its own BROWSER key - referrer-restricted to
    # its sites - in GOOGLE_MAPS_BROWSER_KEY, and it is stamped in here.
    #
    # Never GOOGLE_MAPS_PLATFORM_API_KEY: that is the server's key for
    # geocoding, Places, Routes and the rest, with no referrer
    # restriction (it is called from the server, so it cannot have
    # one). This page is served to browsers, shared and downloaded, so
    # anything stamped into it is public. It stamped the server key
    # from 2026-09-11 until this was changed.
    _maps_key = os.environ.get("GOOGLE_MAPS_BROWSER_KEY", "").strip()
    if _maps_key:
        import re as _re_key  # self-contained: geeView has no module-level re
        html = _re_key.sub(
            r"(maps\.googleapis\.com/maps/api/js\?key=)AIza[\w-]+",
            r"\g<1>" + _maps_key, html)

    # Inject <base href> so any RELATIVE URLs the geeView JS injects at
    # runtime (icons, palette images, etc.) resolve to the asset base
    # rather than to the current page's path. Absolute URLs are unaffected.
    base_tag = '<base href="' + asset_base.rstrip("/") + '/">\n    '
    html = html.replace("<head>", "<head>\n    " + base_tag, 1)

    # Rewrite ./src/... references to absolute under asset_base.
    # Order matters: the inline runGeeViz must replace the script src first.
    html = html.replace(
        '<script type="text/javascript" src="./src/gee/gee-run/runGeeViz.js"></script>',
        (
            # Auth bootstrap — runs after lcms-viewer.min.js initializes
            # urlParams, before runGeeViz triggers Map.addLayer.
            # Either path works at runtime:
            #   * accessToken set + non-"None" → viewer uses token directly
            #     (legacy ``__GEEVIZ_TOKEN__`` substitution path).
            #   * accessToken == "None" / null → viewer falls through to
            #     ``urlParams.geeAuthProxyURL``, which routes EE API calls
            #     through the agent's ``/ee-api`` proxy. Agent injects the
            #     SA bearer token server-side; no EE token in the browser.
            "<script>(function(){"
            "  if(typeof urlParams==='undefined'){window.urlParams={};}"
            "  urlParams.accessToken='" + token_placeholder + "';"
            "  urlParams.accessTokenCreationTime=" + token_time_placeholder + ";"
            "  urlParams.projectID='" + project_placeholder + "';"
            "  urlParams.geeAuthProxyURL='" + auth_proxy_placeholder + "';"
            "})();</script>\n"
            # Inlined per-export runGeeViz JS
            "<script>" + run_js + "</script>"
        ),
    )
    # The Delta page's per-map run script loader (Map.view's ?run=<token>)
    # has nothing to load here: the run script is inline above. Left in, a
    # ?run= on a hosted page would load a stale file over it.
    _rl_start, _rl_end = "<!-- run-loader -->", "<!-- /run-loader -->"
    if _rl_start in html and _rl_end in html:
        _a = html.index(_rl_start)
        _b = html.index(_rl_end, _a) + len(_rl_end)
        html = html[:_a] + html[_b:]
    # Now rewrite the rest of the ./src/ asset paths
    html = html.replace('href="./src/', 'href="' + asset_base + '/src/')
    html = html.replace('src="./src/', 'src="' + asset_base + '/src/')
    # Delta skin assets (no-ops for the original page).
    html = html.replace('href="./delta/', 'href="' + asset_base + '/delta/')
    html = html.replace('src="./delta/', 'src="' + asset_base + '/delta/')
    return html


def _resolve_skin(skin=None):
    """``skin`` if given, else ``GEEVIZ_SKIN`` when it names one, else ``DEFAULT_SKIN``."""
    if skin is None:
        skin = os.environ.get("GEEVIZ_SKIN", "").strip().lower()
        return skin if skin in SKINS else DEFAULT_SKIN
    if skin not in SKINS:
        raise ValueError("Unknown skin {!r}; choose one of: {}".format(skin, ", ".join(SKINS)))
    return skin


def refresh_exported_html(html: str, skin: str | None = None) -> str:
    """Rebuild a page :meth:`mapper.export_html` wrote, on today's viewer.

    An exported map freezes two things: its layers and map calls (the run
    script, which runs in every skin) and the page around them (which skin,
    and that skin's markup as it was then). This keeps the first and
    rebuilds the second, as ``export_html`` would write it now: no Earth
    Engine call is made and no Python session is needed, so a map saved
    long ago, or by a process that has since exited, moves to the current
    viewer (or another skin) as it is. Its asset base and auth placeholders
    are kept as saved.

    What it cannot update is anything the run script itself carries:
    layers and visualization parameters computed in Python when the map
    was made. Those change only by running that code again.

    Args:
        html (str): A page written by ``export_html``.
        skin (str, optional): ``"original"`` or ``"delta"``. Defaults to
            the skin a new ``Map`` starts with (``GEEVIZ_SKIN``, else
            ``DEFAULT_SKIN``).

    Returns:
        str: The rebuilt page.

    Raises:
        ValueError: If ``html`` is not a page ``export_html`` wrote, or the
            skin is unknown.
    """
    import re as _re  # self-contained: geeView has no module-level re

    skin = _resolve_skin(skin)
    head = _re.search(
        r"<script>\(function\(\)\{\s*if\(typeof urlParams==='undefined'\)\{window\.urlParams=\{\};\}\s*"
        r"urlParams\.accessToken='(?P<token>[^']*)';\s*"
        r"urlParams\.accessTokenCreationTime=(?P<time>[^;]*);\s*"
        r"urlParams\.projectID='(?P<project>[^']*)';\s*"
        r"urlParams\.geeAuthProxyURL='(?P<proxy>[^']*)';\s*"
        r"\}\)\(\);</script>\s*<script>",
        html,
    )
    base = _re.search(r'<base href="([^"]*)">', html)
    doc_m = _re.search(r'<script type="application/json" id="geoview-document">(\{.*?)</script>', html, _re.S)
    if not head:
        # a Delta page with the map document: the sign-in block has no run script after it
        head = _re.search(
            r"<script>\(function\(\)\{\s*if\(typeof urlParams==='undefined'\)\{window\.urlParams=\{\};\}\s*"
            r"urlParams\.accessToken='(?P<token>[^']*)';\s*"
            r"urlParams\.accessTokenCreationTime=(?P<time>[^;]*);\s*"
            r"urlParams\.projectID='(?P<project>[^']*)';\s*"
            r"urlParams\.geeAuthProxyURL='(?P<proxy>[^']*)';\s*"
            r"\}\)\(\);</script>",
            html,
        )
    if not head or not base:
        raise ValueError("Not a map page written by Map.export_html: its run script or <base> was not found.")
    asset_base = base.group(1).rstrip("/")
    if asset_base.endswith("/geoview"):
        asset_base = asset_base[: -len("/geoview")]
    placeholders = (head.group("token"), head.group("time"), head.group("project"), head.group("proxy"))
    if doc_m:
        if skin != "delta":
            raise ValueError("This page carries a map document, which only the Delta skin reads.")
        import json as _json
        return _export_page(None, skin, asset_base, *placeholders, doc=_json.loads(doc_m.group(1)))
    end = html.find("</script>", head.end())
    run_js = html[head.end():end] if end > -1 else ""
    if "function runGeeViz(" not in run_js:
        raise ValueError("Not a map page written by Map.export_html: it has no runGeeViz script.")
    return _export_page(run_js, skin, asset_base, *placeholders)
