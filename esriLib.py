"""
ArcGIS / Esri REST services client for geeViz.

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
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Known public portals
# ---------------------------------------------------------------------------

PORTALS: dict[str, str] = {
    "iipp": "https://imagery.geoplatform.gov/iipp",
    "agol": "https://www.arcgis.com",
    "usgs": "https://www.sciencebase.gov/sciencebase",
    "noaa": "https://coastalatlas.noaa.gov",
    "usfs": "https://data.fs.usda.gov/geodata",
    "nasa": "https://nasa.maps.arcgis.com",
}
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

# LOCAL PATCH retry ladder v2 (2026-09-21): a SUCCESSFUL city-scale count
# over FEMA NFHL took 18 s (measured 2026-09-21). Timing that out
# turns a slow layer into a missing one. 45 s is what esri_paging
# already allows the data path.
_TIMEOUT = 45  # seconds


def _fetch_json(url: str, params: dict | None = None) -> dict:
    """GET a URL and return parsed JSON.  Raises ``urllib.error.URLError`` on
    network failure, ``ValueError`` on non-JSON response.

    LOCAL PATCH (2026-09-01): retry transient network failures. Measured on
    hazards.fema.gov: 2 of 8 TLS handshakes were reset (WinError 10054, in
    bursts), so a single-attempt fetch loses a coin-flip fraction of map
    draws while the data path (esri_paging, which retries) succeeds on the
    same layer in the same conversation. Mirrors esri_paging: two retries,
    backoff, transient statuses only.
    """
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "geeViz/esriLib"})
    last_exc: Exception = urllib.error.URLError("no attempt made")
    # LOCAL PATCH retry ladder v2 (2026-09-21): the ladder was shorter than
    # the burst. hazards.fema.gov, 24 attempts one second apart:
    # 7 succeeded, and the longest run of consecutive failures was 7
    # attempts spanning 7.7 s. Three attempts with 1 s + 2 s of
    # backoff give up well inside that - and because a reset comes
    # back in 0.1 s, they were not waiting out anything.
    for attempt in range(5):
        if attempt:
            time.sleep(2 ** (attempt - 1))  # 1, 2, 4, 8 s
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504):
                raise
            last_exc = exc
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
            last_exc = exc
    else:
        raise last_exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Expected JSON from {url!r} but got:\n{raw[:400]}"
        ) from exc


def _build_params(base: dict, token: str | None) -> dict:
    """Merge ``token`` into a params dict if supplied."""
    if token:
        return {**base, "token": token}
    return base


def _resolve_portal(portal: str) -> str:
    """Resolve a portal argument to a base URL.

    Args:
        portal (str): Either a short name from :data:`PORTALS` (e.g.
            ``"iipp"``, ``"agol"``) or a full URL
            (e.g. ``"https://gis.myagency.gov/portal"``).

    Returns:
        str: Portal base URL with no trailing slash.

    Raises:
        KeyError: If a short name is given but not found in :data:`PORTALS`.
    """
    if portal.startswith("http://") or portal.startswith("https://"):
        return portal.rstrip("/")
    if portal in PORTALS:
        return PORTALS[portal].rstrip("/")
    known = ", ".join(f'"{k}"' for k in PORTALS)
    raise KeyError(
        f"Unknown portal short name {portal!r}.  Known names: {known}.  "
        f"Pass a full URL or add your portal to PORTALS first: "
        f'PORTALS["{portal}"] = "https://..."'
    )


# ---------------------------------------------------------------------------
# Portal search
# ---------------------------------------------------------------------------

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
    base_url = _resolve_portal(portal)
    search_url = f"{base_url}/sharing/rest/search"

    # Assemble the query string
    if raw_q is not None:
        q = raw_q
    else:
        q = query
        if data_only:
            exclusions = " ".join(f'-type:"{t}"' for t in _DATA_ONLY_EXCLUSIONS)
            q = f"{q} {exclusions}".strip()

    params: dict[str, Any] = {
        "q": q,
        "num": min(max(1, limit), 100),
        "f": "json",
        **filters,
    }
    if token:
        params["token"] = token

    try:
        data = _fetch_json(search_url, params)
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Could not reach portal at {search_url!r}: {exc}"
        ) from exc

    items = data.get("results", [])
    parsed = []
    for item in items:
        thumb = item.get("thumbnail")
        if thumb:
            thumb = f"{base_url}/sharing/rest/content/items/{item.get('id', '')}/info/{thumb}"
        parsed.append({
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "type": item.get("type", ""),
            "snippet": item.get("snippet", ""),
            "tags": item.get("tags", []),
            "url": item.get("url", ""),
            "owner": item.get("owner", ""),
            "created": item.get("created"),
            "modified": item.get("modified"),
            "thumbnail": thumb,
            "_raw": item,
        })
    return parsed


# ---------------------------------------------------------------------------
# Service metadata
# ---------------------------------------------------------------------------

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
    clean_url = url.rstrip("/")
    params = _build_params({"f": "json"}, token)
    try:
        return _fetch_json(clean_url, params)
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Could not reach service at {clean_url!r}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Service-type detection
# ---------------------------------------------------------------------------

def _detect_service_type(url: str, meta: dict | None = None) -> str:
    """Return the service type string for *url*.

    Detection order:
    1. URL path segments (fast, no HTTP call needed for clear cases).
    2. ``meta["type"]`` or ``meta["serviceDataType"]`` if caller already
       fetched metadata.
    3. Fetch ``?f=json`` and inspect the response.

    Returns one of: ``"ImageServer"``, ``"FeatureServer"``, ``"MapServer"``,
    or ``"Unknown"``.
    """
    # Normalise
    clean = url.rstrip("/").lower()

    # Canonical spellings: match URL segment (case-insensitive), return
    # the correctly-cased ArcGIS type name.
    _stype_map = {
        "imageserver": "ImageServer",
        "featureserver": "FeatureServer",
        "mapserver": "MapServer",
    }
    for lower, canonical in _stype_map.items():
        if f"/{lower}" in clean or clean.endswith(lower):
            return canonical

    # Fall back to metadata inspection
    if meta is None:
        try:
            meta = getServiceMetadata(url)
        except Exception:
            return "Unknown"

    # ArcGIS REST items carry a "type" key on the item record,
    # but service endpoint JSON uses serviceDataType or serviceType.
    for key in ("serviceDataType", "serviceType", "type"):
        val = meta.get(key, "")
        if isinstance(val, str):
            v = val.lower()
            if "image" in v:
                return "ImageServer"
            if "feature" in v:
                return "FeatureServer"
            if "map" in v:
                return "MapServer"

    # Check for fields[] → likely a FeatureServer layer
    if "fields" in meta:
        return "FeatureServer"
    # Check for bandCount → ImageServer
    if "bandCount" in meta or "pixelType" in meta:
        return "ImageServer"

    return "Unknown"


def _resolve_url(url_or_result: str | dict) -> str:
    """Extract a service URL from either a raw URL string or a
    :func:`searchPortal` result dict."""
    if isinstance(url_or_result, str):
        return url_or_result.rstrip("/")
    if isinstance(url_or_result, dict):
        # searchPortal result has a "url" key; fall back to id-based lookup
        service_url = url_or_result.get("url", "")
        if service_url:
            return service_url.rstrip("/")
        raise ValueError(
            "Portal result dict has no 'url' key.  Either the item is not a "
            "hosted service, or the portal did not return a URL for it.  "
            "Check url_or_result['_raw'] for the full item record."
        )
    raise TypeError(
        f"url_or_result must be a URL string or a searchPortal() result dict, "
        f"got {type(url_or_result).__name__!r}"
    )


# ---------------------------------------------------------------------------
# addEsriImageService
# ---------------------------------------------------------------------------

def addEsriImageService(
    url_or_result: str | dict,
    viz_params: dict | None = None,
    name: str | None = None,
    token: str | None = None,
    target_map=None
) -> None:
    """Add an ArcGIS Image Service as an XYZ tile layer to the geeViz map.

    Constructs the ArcGIS tile URL pattern
    ``<service_url>/tile/{z}/{y}/{x}`` and calls
    ``geeViz.geeView.Map.addTileLayer``.

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

    # ArcGIS Image/Map Server tile endpoint: /tile/{z}/{y}/{x}
    # Note: ArcGIS uses y then x (not the XYZ standard x then y).
    tile_url = f"{url}/tile/{{z}}/{{y}}/{{x}}"
    if token:
        tile_url = f"{tile_url}?token={urllib.parse.quote(token, safe='')}"

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
        _meta = getServiceMetadata(url, token=token)
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
    addEsriImageService(url_or_result, viz_params=viz_params, name=name, token=token, target_map=target_map)


# ---------------------------------------------------------------------------
# addEsriFeatureService
# ---------------------------------------------------------------------------

_FEATURE_QUERY_SUFFIX = "/query"

# ---------------------------------------------------------------------------
# LOCAL PATCH esri paging v1 (2026-09-21)
# ---------------------------------------------------------------------------
#: Hard stop on the paging loop. 200 pages at a 2,000 maxRecordCount is
#: 400,000 features - far past anything this viewer can draw, so reaching it
#: means the server is misbehaving and the loop must not run forever.
_MAX_PAGES = 200

#: LOCAL PATCH esri paging v2 (2026-09-21): how many pages of one
#: layer to fetch at the same time. Four, not more: the gain is in
#: not waiting on round trips, and hazards.fema.gov already resets
#: about a third of our handshakes without being crowded.
_PAGE_WORKERS = 4


def _exceeded_transfer(payload: dict) -> bool:
    """True when ArcGIS says it withheld rows.

    The flag sits at the top level of a GeoJSON response and under
    ``properties`` in the Esri JSON one. Both shapes reach here, because
    ``f=geojson`` is not honoured by every service version.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("exceededTransferLimit"):
        return True
    props = payload.get("properties")
    return bool(isinstance(props, dict) and props.get("exceededTransferLimit"))


#: LOCAL PATCH esri paging v3 (2026-09-21): one layer's metadata, fetched once.
#: A classed source draws one sub-layer per class - six, for FEMA flood
#: zones - and every one of them was asking the SAME layer the same
#: question. Keyed on the URL and whether a token was used, never on the
#: token itself.
_CAPS_CACHE: dict = {}


def _paging_caps(layer_url: str, token: str | None) -> dict:
    """``{"paginates", "orders", "oid", "max_record"}`` for a layer.

    ``objectIdField`` is present on FeatureServer layers and often absent on
    MapServer ones, so the OID field is also looked for by TYPE. Without an
    OID neither paging strategy is safe and the caller reports partial.

    ``max_record`` is the server's own page size, which lets the caller skip
    a fetch it would only discard - see LOCAL PATCH esri paging v3 (2026-09-21).
    """
    cache_key = (layer_url, bool(token))
    if cache_key in _CAPS_CACHE:
        return _CAPS_CACHE[cache_key]
    caps = {"paginates": False, "orders": True, "oid": None,
            "max_record": None}
    try:
        meta = _fetch_json(layer_url, _build_params({"f": "json"}, token))
    except Exception:                                    # noqa: BLE001
        return caps
    if not isinstance(meta, dict) or "error" in meta:
        return caps
    adv = meta.get("advancedQueryCapabilities") or {}
    caps["paginates"] = bool(adv.get("supportsPagination"))
    caps["orders"] = bool(adv.get("supportsOrderBy", True))
    oid = meta.get("objectIdField")
    if not oid:
        for field in meta.get("fields") or []:
            if (field or {}).get("type") == "esriFieldTypeOID":
                oid = field.get("name")
                break
    caps["oid"] = oid
    try:
        caps["max_record"] = int(meta.get("maxRecordCount") or 0) or None
    except (TypeError, ValueError):
        caps["max_record"] = None
    _CAPS_CACHE[cache_key] = caps
    return caps


def _feature_id(feat: dict, oid: str | None):
    """A feature's stable identity, or None when it has none.

    GeoJSON from ArcGIS carries the OID as ``id``; when ``outFields`` brought
    the field back it is in ``properties`` too. Either will do - what matters
    is that repeated rows can be recognised, because a server that ignores
    the paging parameters answers every page identically.
    """
    fid = feat.get("id")
    if fid is None and oid:
        fid = (feat.get("properties") or {}).get(oid)
    return fid


def _page_features(query_url: str, params: dict, matched: int,
                   layer_url: str, token: str | None, first_page: list) -> list:
    """Every feature the query matches, or as many as can be paged safely.

    Returns ``first_page`` unchanged when no safe strategy exists - the
    caller then names the layer as partial rather than drawing a slice that
    looks whole.
    """
    caps = _paging_caps(layer_url, token)
    oid = caps["oid"]
    if not oid or not caps["orders"]:
        return first_page
    strategy = "offset" if caps["paginates"] else "oid_window"

    # The first page was fetched with NO orderByFields, so its row order is
    # whatever the server felt like. Offsetting into a different order skips
    # and repeats rows, so that page is thrown away and paging restarts at 0
    # under an explicit ORDER BY. One wasted request buys a correct layer.
    base_where = params.get("where") or "1=1"
    features: list = []
    seen: set = set()
    last = None

    def _harvest(rows) -> int:
        """Add the rows that are new. Returns how many, or -1 when the rows
        carry no identity - a server ignoring the paging parameters cannot
        be told from one honouring them, so that case must stop the loop
        rather than collect duplicates as if complete."""
        nonlocal last
        added = 0
        for feat in rows:
            fid = _feature_id(feat, oid)
            if fid is None:
                return -1
            if fid in seen:
                continue
            seen.add(fid)
            last = fid
            features.append(feat)
            added += 1
        return added

    def _page(extra: dict):
        page = dict(params)
        page["orderByFields"] = oid
        page.update(extra)
        try:
            got = _fetch_json(query_url, page)
        except Exception:                                # noqa: BLE001
            return None
        if not isinstance(got, dict) or "error" in got:
            return None
        return got.get("features") or []

    # LOCAL PATCH esri paging v2 (2026-09-21): the pages are independent
    # under offset paging, and waiting for each in turn was the whole cost -
    # measured over the Houston urban area, 16 geometry pages took 62.9 s of
    # a 71.5 s draw, about 4 s per request whatever its size. Once the first
    # page has shown how big a page is, the remaining offsets are arithmetic
    # and can be fetched at the same time. Four at a time: the point is to
    # stop waiting on round trips, not to hammer a federal server that
    # already resets about a third of our handshakes.
    # The first page carries `resultOffset` only under offset paging. A
    # layer without `supportsPagination` IGNORES the parameter, and sending
    # it there would hide that fact from anyone reading the requests.
    rows = _page({"resultOffset": "0"} if strategy == "offset" else {})
    if not rows:
        return first_page
    page_size = len(rows)
    if _harvest(rows) < 0:
        return features or first_page

    if strategy == "offset" and page_size and len(features) < matched:
        offsets = list(range(page_size, min(matched, page_size * _MAX_PAGES),
                             page_size))
        if offsets:
            try:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=_PAGE_WORKERS) as pool:
                    for got in pool.map(
                            lambda off: _page({"resultOffset": str(off)}),
                            offsets):
                        if not got:
                            continue
                        if _harvest(got) < 0:
                            break
            except Exception:                            # noqa: BLE001
                # Threads unavailable or the pool blew up: fall through to
                # the sequential loop below, which finishes the job slowly
                # rather than returning a layer that looks whole.
                pass

    # Sequential finish. It completes an OID-window layer, and it also picks
    # up anything the parallel pass missed - a page that failed every retry
    # leaves a hole, and a hole is exactly what must not be drawn as whole.
    for _ in range(_MAX_PAGES):
        if len(features) >= matched:
            break
        if strategy == "offset":
            extra = {"resultOffset": str(len(features))}
        elif last is not None:
            extra = {"where": f"({base_where}) AND {oid} > {last}"}
        else:
            extra = {}
        rows = _page(extra)
        if not rows:
            break
        added = _harvest(rows)
        if added <= 0:
            break
    # Paging that went backwards is a bug, not an improvement.
    return features if len(features) >= len(first_page) else first_page



def addEsriFeatureService(
    url_or_result: str | dict,
    viz_params: dict | None = None,
    name: str | None = None,
    max_features: int = 1000,
    where: str = "1=1",
    bbox: str | None = None,
    token: str | None = None,
    # LOCAL PATCH esri generalise v1 (2026-09-17): server-side geometry
    # thinning, in the units of outSR. None keeps every vertex.
    max_allowable_offset: float | None = None,
    # LOCAL PATCH readable popup v1 (2026-09-21): which fields to fetch, and
    # the words to show them under. None keeps outFields="*" and the
    # service's own field names, which is what every earlier caller
    # gets. A 469-field layer makes an unreadable popup otherwise.
    out_fields: str | None = None,
    field_labels: dict | None = None,
    # LOCAL PATCH layer visible v1 (2026-09-21): added to the map switched
    # off. Three stacked translucent polygon layers is a brown wash in
    # which none of them can be read; the layer still has to BE there,
    # so it is added and left for the viewer to switch on.
    visible: bool = True,
    target_map=None
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

    # ---- Pre-flight: count only ----
    count_params: dict[str, Any] = {
        "where": where,
        "returnCountOnly": "true",
        "f": "json",
    }
    # LOCAL PATCH (2026-08-28): area filter. Applied to the COUNT as well as
    # the fetch, so max_features guards the area asked about rather than the
    # whole layer - FEMA NFHL is 5.8M features nationally, 52 in a 2 km box.
    _bbox_params = {}
    if bbox:
        _bbox_params = {
            "geometry": bbox,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        }
        count_params.update(_bbox_params)
    if token:
        count_params["token"] = token

    count_url = f"{url}{_FEATURE_QUERY_SUFFIX}"
    try:
        count_resp = _fetch_json(count_url, count_params)
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Could not reach Feature Service at {count_url!r}: {exc}"
        ) from exc

    # Esri may return {"count": N} or {"error": {...}}
    if "error" in count_resp:
        err = count_resp["error"]
        raise ValueError(
            f"Feature Service returned an error: "
            f"{err.get('code')} — {err.get('message', str(err))}"
        )

    feature_count = count_resp.get("count", 0)

    if feature_count > max_features:
        raise ValueError(
            f"Feature service has {feature_count:,} features "
            f"(max_features={max_features:,}).\n"
            f"Increase max_features OR pass a `where` clause to filter, "
            f"e.g. where=\"STATE_FIPS='06'\", "
            f"OR set chunk_size= to paginate (future extension)."
        )

    # ---- Fetch GeoJSON ----
    query_params: dict[str, Any] = {
        "where": where,
        # LOCAL PATCH readable popup v1 (2026-09-21)
        "outFields": out_fields or "*",
        "outSR": "4326",           # always WGS84 so the viewer renders it natively
        "f": "geojson",
    }
    query_params.update(_bbox_params)
    # LOCAL PATCH esri generalise v1 (2026-09-17): only when asked. The
    # count query above is deliberately left alone - it returns no
    # geometry, so there is nothing to thin.
    if max_allowable_offset:
        query_params["maxAllowableOffset"] = str(max_allowable_offset)
    if token:
        query_params["token"] = token

    # LOCAL PATCH esri paging v3 (2026-09-21): when the count already exceeds
    # the server's own page size, this fetch returns one page that the
    # paging below immediately discards - it is unordered, so offsetting
    # into it would skip and repeat rows. Measured: two of every five round
    # trips a classed city-scale draw made were this and the metadata
    # lookup. Skipping it is safe only when the layer HAS said what its
    # page size is and can be paged; otherwise the original path runs.
    _caps = _paging_caps(url, token)
    _skip_first = bool(
        _caps.get("max_record") and feature_count > _caps["max_record"]
        and _caps.get("oid") and _caps.get("orders"))
    if _skip_first:
        # `exceededTransferLimit` is the honest description of what this
        # stands in for: the whole layer is known not to fit in one
        # response, which is exactly what the flag means.
        geojson = {"type": "FeatureCollection", "features": [],
                   "exceededTransferLimit": True}
    else:
        try:
            geojson = _fetch_json(count_url, query_params)
        except urllib.error.URLError as exc:
            raise ConnectionError(
                f"Could not fetch features from {count_url!r}: {exc}"
            ) from exc

    if "error" in geojson:
        err = geojson["error"]
        raise ValueError(
            f"Feature Service query returned an error: "
            f"{err.get('code')} — {err.get('message', str(err))}"
        )

    # LOCAL PATCH esri paging v1 (2026-09-21): ArcGIS caps ONE response at the
    # layer's maxRecordCount (2,000 on every service this project maps),
    # and this drew whatever came back. Measured on the shipped statewide
    # fault draw: 10,245 matched, 2,000 drawn, exceededTransferLimit true
    # in the response and nothing reading it. Page, and when paging still
    # cannot finish, put the shortfall in the LAYER NAME - the legend is
    # where a person at the booth would see it, not the console.
    features = geojson.get("features") or []
    if _exceeded_transfer(geojson) or 0 < len(features) < feature_count:
        features = _page_features(count_url, query_params, feature_count,
                                  url, token, features)
        geojson["features"] = features

    actual = len(features)
    if actual < feature_count:
        name = f"{name} - {actual:,} of {feature_count:,} drawn"
        print(f"Adding Esri Feature Service: {name} (PARTIAL - the "
              f"service would not return the rest)")
    else:
        print(f"Adding Esri Feature Service: {name} ({actual:,} features)")

    # LOCAL PATCH readable popup v1 (2026-09-21): the viewer's popup prints
    # property NAMES, so renaming them here is the only way a click
    # can say "Hurricane" rather than "HRCN_RISKR". Applied in the
    # order given, so the field that matters reaches the top of the
    # popup; anything unlabelled keeps its name and follows.
    if field_labels:
        for feature in geojson.get("features") or []:
            props = feature.get("properties")
            if not isinstance(props, dict):
                continue
            renamed = {}
            for field, label in field_labels.items():
                if field in props:
                    renamed[label] = props.pop(field)
            renamed.update(props)
            feature["properties"] = renamed

    viz = dict(viz_params or {})
    # The viewer needs layerType=geoJSONVector; addLayer sets it automatically
    # when passed a dict, but be explicit so callers can mix it with other keys.
    viz.setdefault("layerType", "geoJSONVector")

    # LOCAL PATCH layer visible v1 (2026-09-21)
    (target_map or gv.Map).addLayer(geojson, viz, name, visible)


# ---------------------------------------------------------------------------
# addEsriService — auto-dispatch
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# LOCAL PATCH classed fetch v1 (2026-09-21)
# ---------------------------------------------------------------------------
def _class_row_matches(props: dict, match: dict) -> bool:
    """Does one feature satisfy one class spec?

    Mirrors `agent_tools._row_matches`. The NULL rules are the whole reason
    this is written out rather than done with a set membership test: FEMA
    encodes the regulatory floodway as a SUBTYPE of Zone AE, so an ordinary
    AE polygon carries ZONE_SUBTY NULL and IS the row that the "everything
    except the floodway" class has to keep.
    """
    for field, rule in (match or {}).items():
        value = props.get(field)
        text = None if value is None else str(value)
        wanted = rule.get("in") if isinstance(rule, dict) else rule
        unwanted = rule.get("not_in") if isinstance(rule, dict) else None
        if unwanted is not None:
            if text is None:
                if None in unwanted or "null" in [str(u).lower()
                                                  for u in unwanted]:
                    return False
            elif text in [str(u) for u in unwanted]:
                return False
        if wanted is not None:
            allow_null = any(w is None for w in wanted)
            if text is None:
                if not allow_null:
                    return False
            elif text not in [str(w) for w in wanted if w is not None]:
                return False
    return True


def addEsriFeatureServiceClassed(
    url: str,
    classes: list,
    bbox: str | None = None,
    where: str = "1=1",
    other: dict | None = None,
    out_fields: str | None = None,
    field_labels: dict | None = None,
    max_allowable_offset: float | None = None,
    max_features: int = 1000,
    token: str | None = None,
    target_map=None,
) -> None:
    """Fetch a layer ONCE and add one map layer per class.

    Every class asks the same layer over the same box, so asking six times
    is six count preflights, six metadata lookups and six paging runs.
    Measured over the Houston urban area: 79.0 s that way, 27.7 s this way,
    the same features either way.

    Args:
        classes: ``[{"name", "viz", "match", "visible"}]``. `match` is the
            JSON form described in the patch docstring.
        other: optional ``{"name", "viz", "visible"}`` for rows matching no
            class. Without it those rows are DROPPED and the count is
            reported, because a class we have not modelled must never
            vanish in silence.
        where: the outer filter - typically the source's exclude clause.
    """
    import geeViz.geeView as gv

    url = _resolve_url(url)
    if url.lower().endswith("featureserver"):
        url = f"{url}/0"

    count_params: dict[str, Any] = {"where": where, "returnCountOnly": "true",
                                    "f": "json"}
    bbox_params: dict[str, Any] = {}
    if bbox:
        bbox_params = {"geometry": bbox, "geometryType": "esriGeometryEnvelope",
                       "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"}
        count_params.update(bbox_params)
    if token:
        count_params["token"] = token

    query_url = f"{url}{_FEATURE_QUERY_SUFFIX}"
    count_resp = _fetch_json(query_url, count_params)
    if "error" in count_resp:
        err = count_resp["error"]
        raise ValueError(f"Feature Service returned an error: "
                         f"{err.get('code')} - {err.get('message', str(err))}")
    matched = count_resp.get("count", 0)
    if matched > max_features:
        raise ValueError(
            f"Feature service has {matched:,} features "
            f"(max_features={max_features:,}). Increase max_features OR "
            f"narrow `where`.")

    query_params: dict[str, Any] = {
        "where": where, "outFields": out_fields or "*", "outSR": "4326",
        "f": "geojson"}
    query_params.update(bbox_params)
    if max_allowable_offset:
        query_params["maxAllowableOffset"] = str(max_allowable_offset)
    if token:
        query_params["token"] = token

    caps = _paging_caps(url, token)
    if (caps.get("max_record") and matched > caps["max_record"]
            and caps.get("oid") and caps.get("orders")):
        features = _page_features(query_url, query_params, matched, url,
                                  token, [])
    else:
        payload = _fetch_json(query_url, query_params)
        if "error" in payload:
            err = payload["error"]
            raise ValueError(f"Feature Service query returned an error: "
                             f"{err.get('code')} - {err.get('message')}")
        features = payload.get("features") or []
        if _exceeded_transfer(payload) or 0 < len(features) < matched:
            features = _page_features(query_url, query_params, matched, url,
                                      token, features)

    if field_labels:
        for feature in features:
            props = feature.get("properties")
            if not isinstance(props, dict):
                continue
            renamed = {}
            for field, label in field_labels.items():
                if field in props:
                    renamed[label] = props.pop(field)
            renamed.update(props)
            feature["properties"] = renamed

    # Split. One pass, first matching class wins, exactly as the per-class
    # SQL did - the classes are written to be disjoint and the floodway
    # deliberately sits last so it beats the AE it is inside.
    buckets = [[] for _ in classes]
    leftovers = []
    for feature in features:
        props = feature.get("properties") or {}
        for index, spec in enumerate(classes):
            if _class_row_matches(props, spec.get("match") or {}):
                buckets[index].append(feature)
                break
        else:
            leftovers.append(feature)

    short = len(features) < matched
    for spec, rows in zip(classes, buckets):
        name = spec.get("name") or "layer"
        if short:
            name = f"{name} - {len(features):,} of {matched:,} drawn"
        viz = dict(spec.get("viz") or {})
        viz.setdefault("layerType", "geoJSONVector")
        print(f"Adding Esri Feature Service: {name} ({len(rows):,} features)")
        (target_map or gv.Map).addLayer(
            {"type": "FeatureCollection", "features": rows}, viz, name,
            bool(spec.get("visible", True)))

    if leftovers:
        if other:
            viz = dict(other.get("viz") or {})
            viz.setdefault("layerType", "geoJSONVector")
            name = other.get("name") or "Other classes"
            print(f"Adding Esri Feature Service: {name} "
                  f"({len(leftovers):,} features)")
            (target_map or gv.Map).addLayer(
                {"type": "FeatureCollection", "features": leftovers}, viz,
                name, bool(other.get("visible", True)))
        else:
            print(f"WARNING: {len(leftovers):,} features matched no class and "
                  f"were NOT drawn - pass `other=` to keep them.")


def addEsriService(
    url_or_result: str | dict,
    viz_params: dict | None = None,
    name: str | None = None,
    token: str | None = None,
    max_features: int = 1000,
    where: str = "1=1",
    target_map=None
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
