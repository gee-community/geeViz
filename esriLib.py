"""
ArcGIS / Esri REST services client for geeViz. **DEPRECATED.**

.. deprecated::
   Use :mod:`georest` instead. This module now delegates to it and will
   be removed in a future release.

   ``georest`` is the maintained implementation of everything here that
   talks to an Esri REST endpoint, it is stdlib-only (no runtime
   dependencies), and it does considerably more than this module ever
   did — ``exportImage``, ``identifyPixelValue``, ``getSamples``,
   ``computeStatisticsHistograms``, ``queryBoundary``, and a full client
   for the USFS Enterprise Data Warehouse.

   The move, function by function::

       geeViz.esriLib.searchPortal        -> georest.restesri.portal.searchPortal
       geeViz.esriLib.getServiceMetadata  -> georest.restesri.portal.getServiceMetadata

   The signatures match, so the change is the import line.

   The ``addEsri*Service`` functions are NOT going to georest: they add
   layers to a geeViz ``Map``, which is geeViz's concern, not a REST
   client's. They stay available here (and as ``Map.addEsri*``).

   **This module is a patch over georest, not a fork of it.** What is
   left here is only what georest should not have:

   * the geeViz ``Map`` calls -- ``addLayer``, ``addTileLayer``,
     ``addDynamicMapService`` -- and the naming and viz-key handling
     around them;
   * :func:`geeViz._ssrf.check_url`, which is this package's policy and
     has to be applied on THIS side of every delegated call, because
     georest has none;
   * the exception contract callers already depend on: georest reports
     an unreachable host or a bad status as ``RuntimeError``, and this
     module has always raised ``ConnectionError``, so it translates at
     the boundary rather than rewriting what callers catch.

   Everything else delegates. ``_resolve_portal``,
   ``_detect_service_type`` and ``_resolve_url`` were byte-identical
   copies of georest's and now call them; :data:`PORTALS` is georest's
   own dict rather than a copy, so a name added at runtime through
   either module resolves in both; the feature-service count pre-flight,
   overflow guard and GeoJSON fetch are one call to
   ``georest.restesri.services.queryFeatureService``; the ``{z}/{y}/{x}``
   tile template comes from ``getImageServiceTileUrl``.

Bridges three Esri service types into the existing geeViz viewer with no
JavaScript changes required.  The viewer already supports both
``tileMapService`` (for raster tiles) and ``geoJSONVector`` (for vector
features) layer types.

======================================  ==================================================================================
Service type                            Mechanism
======================================  ==================================================================================
Image Service                           ``Map.addTileLayer("<url>/tile/{z}/{y}/{x}")``
Map Service (cached)                    ``Map.addTileLayer(...)`` — same tile path
Feature Service (≤ ``max_features``)    Fetch ``<url>/query?f=geojson`` → ``Map.addLayer(geojson_dict)``
Feature Service (> ``max_features``)    ``ValueError`` with remediation message
======================================  ==================================================================================

**Public API** — 7 functions + 1 constant::

    import geeViz.esriLib as el

    # Discover data on any ArcGIS Portal
    results = el.searchPortal("naip 2023")                  # IIPP (default)
    results = el.searchPortal("naip 2023", portal="agol")   # ArcGIS Online
    results = el.searchPortal("naip 2023",
                              portal="https://myagency.gov/portal")

    # Available portals
    el.PORTALS.keys()   # iipp, agol, usgs, noaa, usfs, nasa

    # Inspect any service
    meta = el.getServiceMetadata("https://.../ImageServer")

    # Add to the geeViz map (auto-dispatches by service type)
    el.addEsriService(result_or_url)

    # Or call the typed helpers directly
    el.addEsriImageService("https://.../ImageServer", name="NAIP 2023")
    el.addEsriFeatureService("https://.../FeatureServer/0",
                             max_features=2000, where="STATE='UT'")
    el.addEsriMapService("https://.../MapServer")

Token-gated portals::

    # Obtain a token first:
    #   POST <portal>/sharing/rest/generateToken
    #     username=...&password=...&client=requestip&expiration=60&f=json
    token = "..."
    el.searchPortal("classified data", token=token)
    el.addEsriFeatureService(url, token=token)

Copyright 2026 Ian Housman

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import json
import warnings
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from geeViz._ssrf import check_url as _check_url  # noqa: E402

# ---------------------------------------------------------------------------
# Known public portals
# ---------------------------------------------------------------------------

#: THE SAME OBJECT georest uses, not a copy of it.
#:
#: This dict is documented below as runtime-editable, and
#: ``_resolve_portal`` now delegates to georest -- so a copy would
#: mean ``esriLib.PORTALS["mine"] = ...`` was accepted and then
#: silently ignored, because the lookup happens against the other
#: dict. Aliasing keeps one source of truth and makes an edit
#: through either name work.
from georest.restesri.portal import PORTALS  # noqa: E402
"""Module-level dict mapping short names to portal base URLs.

Add your own at runtime::

    from geeViz.esriLib import PORTALS
    PORTALS["myagency"] = "https://gis.myagency.gov/portal"
"""

# Non-data item types that clutter portal search results.  Applied when
# data_only=True (the default).  This mirrors the exclusion list used by
# the IIPP search UI.
_DATA_ONLY_EXCLUSIONS: list[str] = [
    "Style",
    "Layer",
    "Map Document",
    "Map Package",
    "Basemap",
    "Mobile Basemap Package",
    "Web Scene",
    "CityEngine Web Scene",
    "Pro Map",
    "Project Package",
    "Task File",
    "Operations Dashboard Add In",
    "Application",
    "Web Mapping Application",
    "Mobile Application",
    "Code Sample",
    "Symbol Set",
    "Color Set",
    "Windows Viewer Add In",
    "Windows Viewer Configuration",
    "Map Area",
    "Insights Workbook",
    "Insights Page",
    "Insights Model",
    "Hub Initiative",
    "Hub Site Application",
    "Hub Page",
    "Hub Project",
    "Experience Builder Widget",
    "Dashboard",
    "StoryMap",
    "Survey123 Add In",
    "Compact Tile Package",
]

# ---------------------------------------------------------------------------
# HTTP helpers (no third-party dependencies — stdlib only)
# ---------------------------------------------------------------------------

_TIMEOUT = 30  # seconds


#: Functions already warned about, so a loop calling one does not emit
#: the same notice a thousand times. A deprecation is a message to the
#: person reading the code, not a running cost.
_WARNED: set[str] = set()


def _deprecated(name: str, replacement: str) -> None:
    """Warn once that ``name`` has moved to ``replacement``.

    ``DeprecationWarning`` is hidden by default in scripts, which is
    right: this must not spam a notebook that happens to call a geeViz
    map helper. Anyone running with ``-W default`` or pytest sees it.
    """
    if name in _WARNED:
        return
    _WARNED.add(name)
    warnings.warn(
        f"geeViz.esriLib.{name} is deprecated and now delegates to "
        f"{replacement}. geeViz.esriLib will be removed in a future "
        f"release; import georest directly.",
        DeprecationWarning,
        stacklevel=3,
    )


def _fetch_json(url: str, params: dict | None = None) -> dict:
    """GET a URL and return parsed JSON, via :mod:`georest`.

    The body that used to live here — urlopen, the three-attempt retry
    on transient statuses, the JSON decode with the response body in the
    error — is now georest's, and georest is the maintained copy. This
    is the same code path the retry patch of 2026-09-01 added, kept
    working for the ``addEsri*`` callers below while they still exist.

    Raises the same things it always did: ``urllib.error.URLError`` on
    network failure, ``ValueError`` on a non-JSON response.
    """
    from georest.restesri import _http as _gh

    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    # _check_url stays on this side: it is geeViz's SSRF guard, and the
    # url is fully built by the time it runs.
    _check_url(url)
    try:
        return _gh.fetch_json(url)
    except ValueError:
        # A non-JSON body. Same meaning on both sides — pass it through
        # rather than flattening it into the network case.
        raise
    except RuntimeError as exc:
        # georest reports an unreachable host or a bad HTTP status as
        # RuntimeError; this module has always documented and raised
        # ConnectionError, and callers catch that. Delegation must not
        # silently change which exception a caller has to handle, so
        # translate at the boundary rather than rewriting the contract
        # of a module people already depend on.
        raise ConnectionError(str(exc)) from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(str(exc)) from exc


def _build_params(base: dict, token: str | None) -> dict:
    """Merge ``token`` into a params dict if supplied. Delegates."""
    from georest.restesri import _http as _gh
    return _gh.build_params(base, token)


def _resolve_portal(portal: str) -> str:
    """Resolve a portal short name or URL to a base URL. Delegates.

    The body was a byte-identical copy of georest's, which is how the
    two would have drifted. :data:`PORTALS` is aliased to georest's own
    dict above, so a name added at runtime resolves here too.
    """
    from georest.restesri import portal as _gp
    return _gp._resolve_portal(portal)

def searchPortal(
    query: str,
    portal: str = "iipp",
    limit: int = 20,
    data_only: bool = True,
    raw_q: str | None = None,
    token: str | None = None,
    **filters: Any,
) -> list[dict[str, Any]]:
    """Search any ArcGIS Portal for hosted services.

    Uses the standard ``/sharing/rest/search`` endpoint present on ArcGIS
    Online, IIPP, and any ArcGIS Enterprise install.

    Args:
        query (str): Free-text search query (e.g. ``"naip 2023"``,
            ``"fire perimeter"``).
        portal (str, optional): Either a short name from :data:`PORTALS`
            (``"iipp"``, ``"agol"``, ``"usgs"``, ``"noaa"``, ``"usfs"``,
            ``"nasa"``) or a full portal base URL.  Defaults to ``"iipp"``.
        limit (int, optional): Maximum results to return (1–100).
            Defaults to 20.
        data_only (bool, optional): When ``True`` (default), appends a
            bundled exclusion list that filters out non-data items (styles,
            web apps, dashboards, etc.) so results are datasets only.
            Set to ``False`` to search without restrictions.
        raw_q (str, optional): If supplied, overrides the assembled query
            string entirely — ignores ``query``, ``data_only``, and
            ``filters``.  Use for portal query DSL power users.
        token (str, optional): ArcGIS token for secured portals.  Omit for
            public services.  Obtain via
            ``POST <portal>/sharing/rest/generateToken``.
        **filters: Extra ArcGIS search filters forwarded verbatim as query
            params (e.g. ``sortField="title"``, ``sortOrder="asc"``,
            ``bbox="-120,35,-110,42"``).

    Returns:
        list of dict: Parsed portal items.  Each dict includes:

        - ``id`` (str): Item ID.
        - ``title`` (str): Item title.
        - ``type`` (str): Esri item type (e.g. ``"Image Service"``,
          ``"Feature Service"``).
        - ``snippet`` (str): Short description.
        - ``tags`` (list of str): Associated tags.
        - ``url`` (str): Service endpoint URL (may be ``""`` if not set).
        - ``owner`` (str): Portal username of the owner.
        - ``created`` (int): Unix timestamp (ms) of item creation.
        - ``modified`` (int): Unix timestamp (ms) of last modification.
        - ``thumbnail`` (str or None): Thumbnail URL, or ``None`` if absent.
        - ``_raw`` (dict): Full raw portal item dict for advanced access.

    Example::

        import geeViz.esriLib as el

        # Search IIPP for NAIP imagery (default portal)
        results = el.searchPortal("naip 2023", limit=10)
        for r in results:
            print(r["title"], r["type"], r["url"])

        # ArcGIS Online
        results = el.searchPortal("wildfire perimeter", portal="agol")

        # Custom Enterprise portal
        results = el.searchPortal("hydrology",
                                  portal="https://gis.mystate.gov/portal")

        # Raw portal query DSL (bypasses data_only and filters)
        results = el.searchPortal("", raw_q='type:"Feature Service" owner:USGS')
    """
    _deprecated("searchPortal", "georest.restesri.portal.searchPortal")
    from georest.restesri import portal as _gp
    return _gp.searchPortal(
        query, portal=portal, limit=limit, data_only=data_only,
        raw_q=raw_q, token=token, **filters)


def getServiceMetadata(url: str, token: str | None = None) -> dict[str, Any]:
    """Fetch and return the JSON metadata for any ArcGIS REST service.

    Appends ``?f=json`` to the URL and returns the parsed response.  Works
    for ImageServer, FeatureServer, MapServer, and any sub-layer URL
    (e.g. ``/FeatureServer/0``).

    Args:
        url (str): ArcGIS service endpoint, e.g.::

            "https://naip.services.arcgis.com/.../ImageServer"
            "https://services.arcgis.com/.../FeatureServer/0"
            "https://server.arcgisonline.com/.../MapServer"

        token (str, optional): ArcGIS token for secured services.

    Returns:
        dict: Parsed service metadata.  Common keys vary by service type:

        - ``name`` (str): Service name.
        - ``type`` (str): Layer geometry type (Feature Services).
        - ``fields`` (list): Schema fields (Feature Services).
        - ``extent`` (dict): Spatial extent.
        - ``spatialReference`` (dict): Spatial reference info.
        - ``minScale``, ``maxScale`` (int): Scale range.
        - ``capabilities`` (str): Comma-separated capabilities string.

    Raises:
        ConnectionError: If the URL is unreachable.
        ValueError: If the response is not valid JSON.

    Example::

        import geeViz.esriLib as el

        meta = el.getServiceMetadata("https://.../ImageServer")
        print(meta["name"])
        print(meta["extent"])

        # FeatureServer layer 0
        meta = el.getServiceMetadata("https://.../FeatureServer/0")
        print([f["name"] for f in meta.get("fields", [])])
    """
    _deprecated("getServiceMetadata",
                "georest.restesri.portal.getServiceMetadata")
    from georest.restesri import portal as _gp
    _check_url(url)
    try:
        return _gp.getServiceMetadata(url, token=token)
    except (RuntimeError, urllib.error.URLError) as exc:
        # Same translation as _fetch_json, and for the same reason: this
        # function has always raised ConnectionError for an unreachable
        # service, and delegating must not change what a caller catches.
        raise ConnectionError(str(exc)) from exc


def _detect_service_type(url: str, meta: dict | None = None) -> str:
    """Return the ArcGIS service type for *url*. Delegates.

    ``"ImageServer"``, ``"FeatureServer"``, ``"MapServer"`` or
    ``"Unknown"``. The body was a byte-identical copy of georest's --
    URL-segment match first, then metadata keys, then the ``fields`` /
    ``bandCount`` shape sniff.
    """
    from georest.restesri import portal as _gp
    return _gp._detect_service_type(url, meta)

def _resolve_url(url_or_result: str | dict) -> str:
    """A service URL from a string or a ``searchPortal`` result. Delegates.

    Another byte-identical copy, raising the same ``TypeError`` for a
    non-string/dict and ``ValueError`` for a result with no ``url``.
    """
    from georest.restesri import portal as _gp
    return _gp._resolve_url(url_or_result)

def addEsriImageService(
    url_or_result: str | dict,
    viz_params: dict | None = None,
    name: str | None = None,
    token: str | None = None,
    target_map=None,
    _meta: dict | None = None,
) -> None:
    """Add an ArcGIS Image Service to the geeViz map.

    A CACHED service (its metadata reports ``tileInfo``) is added as an XYZ
    tile layer on ``<service_url>/tile/{z}/{y}/{x}``. An UNCACHED one --
    most of them, including every NAIP service on IIPP -- has no tiles to
    serve; every ``/tile`` request answers 404 and the layer is blank. It
    is drawn instead through ``<service_url>/exportImage``, re-rendered for
    the viewport on each pan and zoom.

    .. note::
        ArcGIS tile URLs use ``{z}/{y}/{x}`` order (y before x), not the
        XYZ standard ``{z}/{x}/{y}``.  This function emits the correct
        ArcGIS order automatically.

    Args:
        url_or_result (str or dict): Either:

            - A bare service URL, e.g.
              ``"https://naip.services.arcgis.com/.../ImageServer"``
            - A :func:`searchPortal` result dict (the ``"url"`` key is used).

        viz_params (dict, optional): Forwarded to ``addTileLayer`` as
            keyword arguments.  Supported keys: ``opacity`` (float),
            ``visible`` (bool), ``max_zoom`` (int).
        name (str, optional): Layer name shown in the geeViz layer list.
            Defaults to the last segment of the service URL.
        token (str, optional): ArcGIS token appended to tile requests as
            ``?token=<>``.

    Example::

        import geeViz.esriLib as el
        import geeViz.geeView as gv

        el.addEsriImageService(
            "https://naip.services.arcgis.com/.../ImageServer",
            name="NAIP 2022",
            viz_params={"opacity": 0.85},
        )
        gv.Map.centerObject(gv.ee.Geometry.Point([-111.89, 40.77]), 12)
        gv.Map.view()
    """
    import geeViz.geeView as gv

    url = _resolve_url(url_or_result)
    if name is None:
        name = url.rstrip("/").split("/")[-2] if url.endswith(("ImageServer", "imageserver")) else url.rstrip("/").split("/")[-1]

    # Cached or not? getImageServiceTileUrl cannot tell -- it is string
    # construction -- and an uncached service yields a well-formed
    # template whose every tile is a 404. Ask the service. A failed
    # lookup keeps the tile path, as addEsriMapService does: the caller
    # may know the service is cached.
    if _meta is None:
        try:
            from georest.restesri import portal as _gp_meta
            _meta = _gp_meta.getServiceMetadata(url, token=token)
        except Exception as _meta_err:
            print(f"WARNING: could not read service metadata for {url!r} "
                  f"({_meta_err}); assuming it is cached.")
            _meta = None
    if (_meta is not None and url.rstrip("/").lower().endswith("imageserver")
            and "tileInfo" not in _meta and not _meta.get("singleFusedMapCache")):
        print(f"Adding Esri Image Service (dynamic, exportImage): {name}")
        (target_map or gv.Map).addDynamicMapService(
            url,
            name=name,
            visible=bool((viz_params or {}).get("visible", True)),
            token=token,
        )
        return

    # The {z}/{y}/{x} template -- ArcGIS order, y before x, not the XYZ
    # standard -- and the token quoting are georest's. The body here was
    # identical to it line for line, which is the kind of copy that gets
    # a fix in one place and not the other.
    from georest.restesri import services as _gs
    tile_url = _gs.getImageServiceTileUrl(url, token=token)

    kw: dict[str, Any] = {}
    if viz_params:
        if "opacity" in viz_params:
            kw["opacity"] = float(viz_params["opacity"])
        if "visible" in viz_params:
            kw["visible"] = bool(viz_params["visible"])
        if "max_zoom" in viz_params:
            kw["max_zoom"] = int(viz_params["max_zoom"])

    print(f"Adding Esri Image Service: {name}")
    (target_map or gv.Map).addTileLayer(tile_url, name=name, **kw)


# ---------------------------------------------------------------------------
# addEsriMapService
# ---------------------------------------------------------------------------

def addEsriMapService(
    url_or_result: str | dict,
    name: str | None = None,
    token: str | None = None,
    viz_params: dict | None = None,
    target_map=None,
    visible: bool | None = None,
) -> None:
    """Add a cached ArcGIS Map Service as an XYZ tile layer to the geeViz map.

    Cached Map Services expose the same ``/tile/{z}/{y}/{x}`` tile endpoint
    as Image Services and are handled identically.  Dynamic (non-cached) Map
    Services do not serve tiles this way; for those, use
    :func:`addEsriFeatureService` on the individual sub-layer.

    Args:
        url_or_result (str or dict): Service URL or :func:`searchPortal`
            result dict.
        name (str, optional): Layer name.  Defaults to last URL segment.
        token (str, optional): ArcGIS token for secured services.
        viz_params (dict, optional): ``opacity``, ``visible``, ``max_zoom``.

    Example::

        import geeViz.esriLib as el

        el.addEsriMapService(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer",
            name="ESRI World Imagery",
        )
    """
    # Every other add* takes visible=; an agent passing it here got
    # TypeError. Folded into viz_params, which is where it was honored.
    if visible is not None:
        viz_params = {**(viz_params or {}), "visible": bool(visible)}
    # ── Preflight: cached or dynamic? Route accordingly. ──
    # CACHED MapServers (``singleFusedMapCache: true``) expose
    # ``/tile/{z}/{y}/{x}`` — same shape as an ImageServer, handled by
    # addEsriImageService below.
    # DYNAMIC MapServers (``singleFusedMapCache: false``) don't serve
    # pre-rendered tiles; they respond to ``/export?bbox=…&f=image``.
    # Route those through ``gv.Map.addDynamicMapService``, which
    # bridges to the viewer's ``addDynamicToMap`` code path (Google
    # Maps GroundOverlay per viewport). Real incident 2026-07-30: FEMA
    # NFHL is dynamic; passing it to addEsriMapService without this
    # branch broke the map silently.
    import geeViz.geeView as _gv
    url = _resolve_url(url_or_result)
    try:
        # georest DIRECTLY, not this module's public getServiceMetadata.
        #
        # That wrapper is deprecated and warns, and this is an INTERNAL
        # call on the supported path: the addEsri*Service helpers are not
        # deprecated (they add layers to a geeViz Map, which georest has
        # no business doing), so a caller of addEsriMapService -- or of
        # Map.addEsriMapService, or the MCP sandbox, which instructs
        # agents to use exactly these helpers -- got a DeprecationWarning
        # naming a function they never called and could not stop calling.
        from georest.restesri import portal as _gp_meta
        _meta = _gp_meta.getServiceMetadata(url, token=token)
    except Exception as _meta_err:
        # Metadata fetch failed — could be a bad URL, an auth wall, or
        # a transient network hiccup. Print a warning so the agent (and
        # `testLayers` output) sees WHY we can't detect cached-vs-dynamic
        # and can suggest a fix; still fall through to the tile path in
        # case the caller knows the service IS cached.
        print(
            f"WARNING: addEsriMapService could not fetch service metadata for "
            f"{url!r} ({_meta_err}). Proceeding as if cached; if the layer "
            f"fails to render, verify the URL (a common issue is a wrong "
            f"prefix like '/gis/...' vs '/arcgis/rest/services/...')."
        )
        _meta = None
    if _meta is not None and _meta.get("singleFusedMapCache") is False:
        _name = name or url.rstrip("/").split("/")[-2]
        print(f"Adding Dynamic Esri Map Service: {_name}  ({url})")
        (target_map or _gv.Map).addDynamicMapService(
            url,
            name=_name,
            visible=(viz_params or {}).get("visible", True),
            token=token,
        )
        return
    # Cached — same tile URL shape as ImageServer
    addEsriImageService(url_or_result, viz_params=viz_params, name=name, token=token,
                        target_map=target_map, _meta=_meta)


# ---------------------------------------------------------------------------
# addEsriFeatureService
# ---------------------------------------------------------------------------

_FEATURE_QUERY_SUFFIX = "/query"


# ---------------------------------------------------------------------------
# Display generalization for embedded GeoJSON
# ---------------------------------------------------------------------------
#
# A Feature Service layer is embedded in the map page as GeoJSON, every
# vertex included. Services are authored for analysis, not display: a
# USFS landtype-association layer came back as 1.76 million vertices at
# 15 decimal places, about 0.7 m apart, and made a 70.8 MB page that never
# reached the browser. These helpers thin a layer to what a screen can
# show, and only when it is too big to deliver as-is.

#: Degrees per meter, near enough for a display tolerance at any latitude
#: people map (it errs toward keeping detail in longitude at high latitude).
_DEG_PER_M = 1.0 / 111_320.0

#: Tolerances tried in order by ``simplify="auto"``, in meters. The last is
#: about one screen pixel at the zoom where a whole national forest fits.
_AUTO_TOLERANCES_M = (1, 5, 10, 20, 30, 50, 100)

#: Tolerance ``simplify="auto"`` asks the SERVER to generalize to, in
#: meters. A few pixels at street zoom, invisible below it; see
#: addEsriFeatureService for what it saves.
_SERVER_OFFSET_M_AUTO = 5


def _georest_generalizes(services_module) -> bool:
    """Whether this georest's queryFeatureService takes server-side
    generalization (added after 0.4.0)."""
    import inspect
    try:
        return "max_allowable_offset" in inspect.signature(
            services_module.queryFeatureService).parameters
    except (TypeError, ValueError):
        return False


#: Default per-layer budget. Several layers share one page, and the page as
#: a whole is refused by geeView above 25 MB.
_LAYER_BUDGET_BYTES_DEFAULT = 8 * 1024 * 1024


def _dp(pts, tol):
    """Douglas-Peucker on a list of positions; iterative (no recursion
    limit on long rings) and keeps both endpoints."""
    n = len(pts)
    if n < 3 or tol <= 0:
        return pts
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tol * tol
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a][0], pts[a][1]
        dx, dy = pts[b][0] - ax, pts[b][1] - ay
        seg2 = dx * dx + dy * dy
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i][0] - ax, pts[i][1] - ay
            if seg2:
                t = (px * dx + py * dy) / seg2
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
                ex, ey = px - t * dx, py - t * dy
            else:
                ex, ey = px, py
            d2 = ex * ex + ey * ey
            if d2 > best:
                best, idx = d2, i
        if best > tol2:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [q for q, k in zip(pts, keep) if k]


def _gen_line(pts, tol, precision, min_pts):
    out = _dp(pts, tol)
    if len(out) < min_pts:
        # Too aggressive for this ring/line: keep evenly spaced originals
        # rather than emitting something invalid.
        if len(pts) <= min_pts:
            out = pts
        else:
            step = (len(pts) - 1) / (min_pts - 1)
            out = [pts[round(i * step)] for i in range(min_pts)]
    return [[round(c[0], precision), round(c[1], precision)] for c in out]


def _gen_geom(g, tol, precision):
    if not g:
        return g
    t, c = g.get("type"), g.get("coordinates")
    if t == "LineString":
        return {"type": t, "coordinates": _gen_line(c, tol, precision, 2)}
    if t == "MultiLineString":
        return {"type": t, "coordinates": [_gen_line(l, tol, precision, 2) for l in c]}
    if t == "Polygon":
        return {"type": t, "coordinates": [_gen_line(r, tol, precision, 4) for r in c]}
    if t == "MultiPolygon":
        return {"type": t, "coordinates": [[_gen_line(r, tol, precision, 4) for r in poly]
                                           for poly in c]}
    if t == "GeometryCollection":
        return {"type": t, "geometries": [_gen_geom(x, tol, precision)
                                          for x in g.get("geometries", [])]}
    return g  # Point / MultiPoint: nothing to thin


def _generalize_geojson(gj, tolerance_m, precision=6):
    """Return a copy of *gj* simplified to *tolerance_m* and rounded to
    *precision* decimal places. Features and properties are kept as-is."""
    tol = float(tolerance_m) * _DEG_PER_M
    feats = [{**f, "geometry": _gen_geom(f.get("geometry"), tol, precision)}
             for f in gj.get("features", [])]
    return {**gj, "features": feats}


def _geojson_bytes(gj):
    return len(json.dumps(gj, separators=(",", ":")))


def _fit_geojson_for_display(gj, simplify="auto", budget_bytes=None):
    """Thin *gj* for embedding in a map page.

    Returns ``(geojson, note)`` where *note* describes what was done, or
    ``None`` if nothing was.

    * ``simplify=False`` / ``None`` -- never alter geometry.
    * ``simplify=<number>`` -- simplify to that tolerance in meters.
    * ``simplify="auto"`` -- leave a layer under *budget_bytes* exactly as
      fetched; otherwise try increasing tolerances until it fits.

    Simplifying polygons one at a time can open hairline gaps where
    neighbors share an edge. At the tolerances used here that is below a
    pixel at the zoom the layer is legible at; analysis should still run on
    the service or an EE FeatureCollection, not on the display copy.
    """
    if simplify is False or simplify is None:
        return gj, None
    budget = _LAYER_BUDGET_BYTES_DEFAULT if budget_bytes is None else int(budget_bytes)
    if isinstance(simplify, (int, float)) and not isinstance(simplify, bool):
        out = _generalize_geojson(gj, simplify)
        return out, f"simplified to ~{simplify:g} m for display"
    if simplify != "auto":
        raise ValueError(f"simplify must be 'auto', False, or a tolerance in meters; got {simplify!r}")
    before = _geojson_bytes(gj)
    if before <= budget:
        return gj, None
    out = gj
    for tol_m in _AUTO_TOLERANCES_M:
        out = _generalize_geojson(gj, tol_m)
        after = _geojson_bytes(out)
        if after <= budget:
            return out, (f"simplified to ~{tol_m} m for display "
                         f"({before / 1e6:.1f} MB -> {after / 1e6:.1f} MB)")
    return out, (f"simplified to ~{_AUTO_TOLERANCES_M[-1]} m and still "
                 f"{_geojson_bytes(out) / 1e6:.1f} MB -- filter with where= or bbox= "
                 f"to request fewer features")



def addEsriFeatureService(
    url_or_result: str | dict,
    viz_params: dict | None = None,
    name: str | None = None,
    max_features: int = 1000,
    where: str = "1=1",
    bbox: str | None = None,
    token: str | None = None,
    target_map=None,
    simplify="auto",
    max_layer_mb: float | None = None,
) -> None:
    """Fetch and add an ArcGIS Feature Service layer as a GeoJSON vector layer.

    Hits ``<url>/query?f=geojson&where=<where>&outSR=4326`` and passes the
    returned GeoJSON directly to ``geeViz.geeView.Map.addLayer``.

    .. warning::
        Always performs a ``returnCountOnly=true`` pre-flight before fetching
        geometry.  If the result count exceeds *max_features*, a
        :class:`ValueError` is raised with a concrete remediation message.

    Args:
        url_or_result (str or dict): Feature Service or sub-layer URL
            (e.g. ``".../FeatureServer/0"``), or a :func:`searchPortal`
            result dict.  If the URL points to the FeatureServer root rather
            than a specific layer, ``/0`` is appended automatically.
        viz_params (dict, optional): Passed to ``Map.addLayer`` as the ``viz``
            dict.  Supports all geeViz vector viz keys (``"color"``,
            ``"strokeColor"``, ``"fillColor"``, ``"opacity"``,
            ``"strokeWidth"``, ``"layerType"``, etc.).
        name (str, optional): Layer name.  Defaults to last URL segment.
        max_features (int, optional): Hard cap on feature count.  If the
            service has more than this many features matching *where*, a
            :class:`ValueError` is raised.  Defaults to 1000.  Increase
            with care — very large GeoJSON payloads can slow the viewer.
        where (str, optional): SQL WHERE clause sent to the service for
            server-side filtering.  Defaults to ``"1=1"`` (all features).
            Example: ``where="STATE_FIPS='06'"`` (California only).
        token (str, optional): ArcGIS token for secured services.
        simplify (str, bool or float, optional): ``"auto"`` (default)
            asks the service for geometry generalized to ~5 m -- far
            smaller and faster than full resolution -- then, if the layer
            is still over *max_layer_mb*, simplifies it further at
            increasing tolerances until it fits: the whole layer is
            embedded in the map page, and a page that is too large never
            reaches the browser. A number is a fixed tolerance in meters,
            applied by the service. ``False`` fetches and keeps the exact
            geometry.
        max_layer_mb (float, optional): Size budget for this layer in the
            page, used by ``simplify="auto"``. Defaults to 8 MB.

    Raises:
        ValueError: If the feature count exceeds *max_features*.
        ConnectionError: If the service URL is unreachable.

    Example::

        import geeViz.esriLib as el
        import geeViz.geeView as gv

        # Simple fetch — all features up to default cap
        el.addEsriFeatureService(
            "https://services.arcgis.com/.../FeatureServer/0",
            name="Wildfire Perimeters",
        )

        # Filter server-side to stay under the cap
        el.addEsriFeatureService(
            "https://services.arcgis.com/.../FeatureServer/0",
            where="YEAR_=2023 AND GIS_ACRES > 10000",
            name="Large 2023 Fires",
            max_features=500,
        )

        gv.Map.view()
    """
    import geeViz.geeView as gv

    url = _resolve_url(url_or_result)

    # Ensure we're pointing at a layer (e.g. /0), not the FeatureServer root.
    # The root URL ends in "FeatureServer" (case-insensitive); sub-layers end
    # in a digit.
    if url.lower().endswith("featureserver"):
        url = f"{url}/0"

    if name is None:
        name = url.rstrip("/").split("/")[-1]
        # If name is just "0", walk up for a more descriptive label
        if name.isdigit():
            parts = url.rstrip("/").split("/")
            name = f"{parts[-2]} ({name})" if len(parts) >= 2 else name

    # ---- count pre-flight + GeoJSON fetch, both georest's ----------
    #
    # queryFeatureService does exactly what the ~70 lines here used to:
    # a returnCountOnly pre-flight that honors the SAME spatial filter
    # as the fetch (so max_features guards the area asked about rather
    # than the whole layer -- FEMA NFHL is 5.8M features nationally and
    # 52 in a 2 km box), the overflow guard, then outSR=4326 GeoJSON.
    #
    # `bbox` stays the parameter name here because it is this module's
    # published signature; georest spells the same thing as a geometry
    # plus its type, and an envelope intersect is its default.
    from georest.restesri import services as _gs

    # geeViz's SSRF guard, which georest does not have and should not:
    # it is this package's policy, not a REST client's. It used to be
    # reached through _fetch_json; calling georest directly skips that
    # path, so it has to be applied here or delegation quietly removes
    # a security check.
    _check_url(url)

    # Let the SERVER thin the geometry. The layer is for display, and a
    # full-resolution download is most of the wait: 37 NIFC fire
    # perimeters are 34 MB / 31 s exact, 5.8 MB / 6 s at 5 m. The
    # client-side pass below still runs, and only does anything when even
    # the generalized layer is over budget. Older georest has no such
    # parameters; there the fetch is exact, as it always was.
    _gen_kw: dict[str, Any] = {}
    _offset_m = None
    if simplify == "auto":
        _offset_m = _SERVER_OFFSET_M_AUTO
    elif isinstance(simplify, (int, float)) and not isinstance(simplify, bool):
        _offset_m = float(simplify)
    if _offset_m is not None and _georest_generalizes(_gs):
        _gen_kw = {"max_allowable_offset": round(_offset_m * _DEG_PER_M, 9),
                   "geometry_precision": 6}

    try:
        geojson = _gs.queryFeatureService(
            url,
            where=where,
            geometry=bbox,
            max_features=max_features,
            token=token,
            **_gen_kw,
        )
    except ValueError:
        # An Esri error body, or the overflow guard. Both mean the same
        # on either side of the boundary -- pass them through rather
        # than flattening them into the network case.
        raise
    except RuntimeError as exc:
        # georest reports an unreachable host or a bad HTTP status as
        # RuntimeError. This module has always raised ConnectionError
        # and its callers catch that, so translate at the boundary --
        # the same thing _fetch_json does, for the same reason.
        raise ConnectionError(
            f"Could not reach Feature Service at {url!r}: {exc}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Could not reach Feature Service at {url!r}: {exc}"
        ) from exc

    actual = len(geojson.get("features", []))
    budget = None if max_layer_mb is None else int(float(max_layer_mb) * 1024 * 1024)
    geojson, note = _fit_geojson_for_display(geojson, simplify=simplify,
                                             budget_bytes=budget)
    print(f"Adding Esri Feature Service: {name} ({actual:,} features)"
          + (f" -- {note}" if note else ""))

    viz = dict(viz_params or {})
    # The viewer needs layerType=geoJSONVector; addLayer sets it automatically
    # when passed a dict, but be explicit so callers can mix it with other keys.
    viz.setdefault("layerType", "geoJSONVector")

    (target_map or gv.Map).addLayer(geojson, viz, name)


# ---------------------------------------------------------------------------
# addEsriService — auto-dispatch
# ---------------------------------------------------------------------------

def addEsriService(
    url_or_result: str | dict,
    viz_params: dict | None = None,
    name: str | None = None,
    token: str | None = None,
    max_features: int = 1000,
    where: str = "1=1",
    target_map=None,
    bbox: str | None = None,
    simplify="auto",
) -> None:
    """Auto-detect the Esri service type and call the appropriate add helper.

    Inspects the URL path (and falls back to the service metadata) to
    determine whether *url_or_result* is an Image Service, Feature Service,
    or Map Service, then delegates to :func:`addEsriImageService`,
    :func:`addEsriFeatureService`, or :func:`addEsriMapService`.

    Args:
        url_or_result (str or dict): Service URL or :func:`searchPortal`
            result dict.
        viz_params (dict, optional): Visualization parameters forwarded to
            the typed helper.
        name (str, optional): Layer name.
        token (str, optional): ArcGIS token.
        max_features (int, optional): Forwarded to :func:`addEsriFeatureService`.
        where (str, optional): SQL WHERE clause forwarded to
            :func:`addEsriFeatureService`.
        bbox (str, optional): Spatial filter forwarded to
            :func:`addEsriFeatureService`.
        simplify (optional): Forwarded to :func:`addEsriFeatureService`.

    Raises:
        ValueError: If the service type cannot be determined.

    Example::

        import geeViz.esriLib as el

        results = el.searchPortal("naip 2023", limit=5)
        for r in results:
            el.addEsriService(r)  # dispatches by type automatically
    """
    url = _resolve_url(url_or_result)
    stype = _detect_service_type(url)

    # Pass the original url_or_result so name resolution works with dicts too
    if stype == "ImageServer":
        addEsriImageService(url_or_result, viz_params=viz_params, name=name, token=token, target_map=target_map)
    elif stype == "FeatureServer":
        addEsriFeatureService(
            url_or_result,
            viz_params=viz_params,
            name=name,
            max_features=max_features,
            where=where,
            token=token,
            bbox=bbox,
            simplify=simplify,
            # Was missing: without it the layer went to the global
            # gv.Map, not the map this call was made for.
            target_map=target_map,
        )
    elif stype == "MapServer":
        addEsriMapService(url_or_result, name=name, token=token, viz_params=viz_params, target_map=target_map)
    else:
        raise ValueError(
            f"Could not determine service type for URL {url!r}.  "
            f"Use addEsriImageService / addEsriFeatureService / "
            f"addEsriMapService directly, or inspect the service manually "
            f"with getServiceMetadata()."
        )
