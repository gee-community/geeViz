"""
ArcGIS / Esri REST services client for geeViz.

Bridges three Esri service types into the existing geeViz viewer with no
JavaScript changes required.  The viewer already supports both
``tileMapService`` (for raster tiles) and ``geoJSONVector`` (for vector
features) layer types.

| Service type | Mechanism |
|---|---|
| Image Service | ``Map.addTileLayer("<url>/tile/{z}/{y}/{x}")`` |
| Map Service (cached) | ``Map.addTileLayer(...)`` — same tile path |
| Feature Service (≤ max_features) | Fetch ``<url>/query?f=geojson`` → ``Map.addLayer(geojson_dict)`` |
| Feature Service (> max_features) | ``ValueError`` with remediation message |

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

_TIMEOUT = 30  # seconds


def _fetch_json(url: str, params: dict | None = None) -> dict:
    """GET a URL and return parsed JSON.  Raises ``urllib.error.URLError`` on
    network failure, ``ValueError`` on non-JSON response."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "geeViz/esriLib"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
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
    gv.Map.addTileLayer(tile_url, name=name, **kw)

def downloadImageServiceToTiff(
    url, 
    geometry=None,
    localdir=r'C:\tmp',
    localfile='outtif.tif',
    f="image", 
    format="tiff",
    geometrySR=None,
    imageSR=None,
    pixelType=None,
    pixelSize=None,
    size=None, # Add size parameter
    noData = None, 
    noDataInterpretation="esriNoDataMatchAny",
    interpolation="RSP_BilinearInterpolation",
    quiet=False,
    timeout=300
):
    import requests
    import ee
    import os

    # check url format
    url = _check_ending_export(url)
    _qprint(f"Using URL: {url}", quiet)


    # Initial Parameter Construct
    #----------------------------------------------------------#

    # Get info about image service to use to construct parameters
    info_url = url.replace('/exportImage?', '?f=json')
    response = requests.get(info_url)
    info = response.json()

    # Construct params
    params = {
        "f": f,
        "bbox": None,  # will be set below
        "bboxSR": None,  # will be set below
        "imageSR": imageSR,
        "format": format,
        "pixelType": pixelType,
        "pixelSize": pixelSize,
        "noData": noData,
        "noDataInterpretation": noDataInterpretation,
        "interpolation": interpolation
    }

    # Confirm params with information from image service
    pixel_size_service = info.get('pixelSizeX', None) or info.get('rasterInfo', {}).get('pixelSize', {}).get('x', None)
    if pixelSize is not None: 
        params['pixelSize'] = pixelSize
    if pixelSize is None and pixel_size_service is not None:
        params['pixelSize'] = pixel_size_service
    if pixelSize is None and pixel_size_service is None:
        _qprint("No pixel size provided, and native pixel size not found in service info. Using default of 30.", quiet)
        params['pixelSize'] = 30

    nodata_service = info.get('noDataValue', None) or info.get('rasterInfo', {}).get('noDataValue', None)
    if noData is not None:
        params['noData'] = noData
    if noData is None and nodata_service is not None:
        params['noData'] = nodata_service
    if noData is None and nodata_service is None:
        _qprint("No nodata value provided, and nodata value not found in service info. Using default of None.", quiet)
        params['noData'] = None

    image_sr_service = info.get('spatialReference', {}).get('latestWkid', None) or info.get('spatialReference', {}).get('wkid', None)
    if imageSR is not None:
        params['imageSR'] = imageSR
    if imageSR is None and image_sr_service is not None:
        params['imageSR'] = image_sr_service
    if imageSR is None and image_sr_service is None:
        _qprint("No imageSR provided, and spatial reference not found in service info. Using default of 4326.", quiet)
        params['imageSR'] = 4326

    pixel_type_service = info.get('pixelType', None) or info.get('rasterInfo', {}).get('pixelType', None)
    if pixelType is not None:
        params['pixelType'] = pixelType
    if pixelType is None and pixel_type_service is not None:
        params['pixelType'] = pixel_type_service
    if pixelType is None and pixel_type_service is None:
        _qprint("No pixelType provided, and pixel type not found in service info. Using default of S16.", quiet)
        params['pixelType'] = "S16"

    # Set geometry / bounding box and projection
    #----------------------------------------------------------#

    default_bbox = '-111,39,-110,40'
    default_bboxSR = 4326

    if geometry is None:
        _qprint("No geometry provided. Using default bounding box and bboxSR: " + default_bbox + ", " + str(default_bboxSR), quiet)

    else:
        _qprint(f"Using provided geometry", quiet)

        # check if geometrySR matches ImageSR
        if geometrySR is not None and params['imageSR'] is not None and geometrySR != params['imageSR']:
            _qprint(f"Warning: geometrySR ({geometrySR}) does not match imageSR ({params['imageSR']}). The server will reproject the output image.", quiet)

        # convert geometry to bounding box        
        bounds, bboxSR = geometry_to_bbox(geometry, sr=geometrySR, quiet=quiet)

        #qprint(f"Using bounding box: {bounds} with bboxSR: {bboxSR}", quiet)

        

    # Set bbox and bboxSR params
    params["bbox"] = f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
    params["bboxSR"] = bboxSR

    # Add size to params if provided
    if size:
        params["size"] = size



    # Format request
    #----------------------------------------------------------#
    try:
        response = requests.get(url, params=params, timeout=timeout)
        _qprint(f"Request URL: {response.url}", quiet)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

    except requests.exceptions.Timeout:
        _qprint(f"Request timed out after {timeout} seconds.", quiet)
        return None
    except requests.exceptions.RequestException as e:
        _qprint(f"An error occurred: {e}", quiet)
        return None

    if response.status_code != 200:
        _qprint(f"Failed to download image. HTTP Status Code: {response.status_code}", quiet)
        exit()
    else:
        file_path = f"{localdir}\\{localfile}"
        os.makedirs(localdir, exist_ok=True)
        with open(file_path, mode='wb') as localfile:
            localfile.write(response.content)
        _qprint("Image saved to " + file_path, quiet)


# ---------------------------------------------------------------------------
# addEsriMapService
# ---------------------------------------------------------------------------

def addEsriMapService(
    url_or_result: str | dict,
    name: str | None = None,
    token: str | None = None,
    viz_params: dict | None = None,
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
    # Map Service tile URL is the same shape as ImageServer
    addEsriImageService(url_or_result, viz_params=viz_params, name=name, token=token)


# ---------------------------------------------------------------------------
# addEsriFeatureService
# ---------------------------------------------------------------------------

_FEATURE_QUERY_SUFFIX = "/query"


def addEsriFeatureService(
    url_or_result: str | dict,
    viz_params: dict | None = None,
    name: str | None = None,
    max_features: int = 1000,
    where: str = "1=1",
    token: str | None = None,
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

    # ---- Fetch GeoJSON via queryFeatureService (handles pagination + cleanup) ----
    geojson = queryFeatureService(url, where=where, outSR=4326, token=token, quiet=True)

    actual = len(geojson.get("features", []))
    print(f"Adding Esri Feature Service: {name} ({actual:,} features)")

    viz = dict(viz_params or {})
    # The viewer needs layerType=geoJSONVector; addLayer sets it automatically
    # when passed a dict, but be explicit so callers can mix it with other keys.
    viz.setdefault("layerType", "geoJSONVector")

    gv.Map.addLayer(geojson, viz, name)


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
        addEsriImageService(url_or_result, viz_params=viz_params, name=name, token=token)
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
        addEsriMapService(url_or_result, name=name, token=token, viz_params=viz_params)
    else:
        raise ValueError(
            f"Could not determine service type for URL {url!r}.  "
            f"Use addEsriImageService / addEsriFeatureService / "
            f"addEsriMapService directly, or inspect the service manually "
            f"with getServiceMetadata()."
        )
# ------------------------------------------------------------------------------
# For querying feature service data
#-----------------------------------------------------------------------------

def queryFeatureService(url, 
                           f = "geojson", 
                           where = "1=1", 
                           outFields = "*", 
                           returnGeometry = "true", 
                           outSR = None,
                           geometry = None,   
                           geometryType = None,
                           geometrySR = None,
                           spatialRel = "esriSpatialRelIntersects",  # esriSpatialRelIntersects, esriSpatialRelContains, etc.
                           token = None,
                           quiet = False ):
    """
    Query a FeatureService and return the results as a GeoJSON FeatureCollection and the ESRI JSON geometry as ee.Geometry.

    Args:
        url: str, URL of the FeatureService layer.
        f: str, output format (default "geojson").
        where: str, SQL where clause to filter features.
        outFields: str, fields to return (default "*").
        returnGeometry: str, "true" or "false" to return geometry.
        outSR: int or None, output spatial reference (EPSG code).
        geometry: various types, geometry to filter features spatially.
        geometryType: str or None, type of geometry provided.
        spatialRel: str, spatial relationship for filtering.
        quiet: bool, if True suppresses print statements.
    """
    import requests
    import json
    import time


    meta = getServiceMetadata(url.rstrip('/'))
    sr = meta.get('spatialReference', {})
    epsg = sr.get('latestWkid') or sr.get('wkid')
    max_records = meta.get('maxRecordCount', 500)


    # Construct params
    base_params = {
        "f": f,
        "where": where,
        "outFields": outFields,
        "returnGeometry": returnGeometry,
        "outSR": outSR,
        "resultOffset": 0,
        "resultRecordCount": max_records,
    }
    if token:
        base_params["token"] = token

    final_geom = None

    if geometry is not None:
        try:
            if geometrySR is None:
                geometrySR = epsg
            geo_obj = geom_to_esri_json(geometry, outSR=geometrySR)
            g_json = geo_obj["geometry"]
            print("ESRI geometry for filter:", g_json)
            base_params["geometry"] = json.dumps(g_json) if not isinstance(g_json, str) else g_json
            base_params["geometryType"] = geometryType or geo_obj.get("geometryType")
            base_params["spatialRel"] = spatialRel
            final_geom = geo_obj
        except Exception as e:
            raise ValueError(f"Failed to convert geometry to ESRI JSON: {e}")   

    # Params to determine how many features there are in the service
    count_params = {
        "f": "json",
        "where": where,
        "returnCountOnly": "true",
        "outFields": None,
        "returnGeometry": None
    }

    # Fetch the data
    all_features = []
    total_features_retrieved = 0

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    while True:
        try:
            response = requests.get(f"{url.rstrip('/')}/query", params=base_params, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"Error querying feature service at offset {base_params['resultOffset']}: {e}"
            if 'response' in locals() and response is not None:
                try:
                    error_msg += f"\nServer Response: {response.text}"
                except:
                    pass
            raise RuntimeError(error_msg)
        except json.JSONDecodeError:
            raise RuntimeError(f"Failed to decode JSON from response: {response.text}")

        features = data.get('features', [])
        if not features:
            break  # No more features to fetch

        all_features.extend(features)
        num_fetched = len(features)
        total_features_retrieved += num_fetched
        _qprint(f"Retrieved {num_fetched} features... (Total: {total_features_retrieved})", quiet)

        if num_fetched < max_records:
            # This was the last page
            break
        else:
            # Prepare for the next page
            base_params["resultOffset"] += max_records
            time.sleep(0.1) # Small delay to be polite to the server

    _qprint(f"Total features retrieved: {len(all_features)}", quiet)

    # Clean up properties that can cause issues in GEE
    for feature in all_features:
        props = feature.get('properties', {})
        if 'SHAPE.AREA' in props:
            del props['SHAPE.AREA']
        if 'SHAPE.LEN' in props:
            del props['SHAPE.LEN']

    features_out = {
        "type": "FeatureCollection",
        "features": all_features
    }
    return features_out

#---------------
# Zonal Stats
#---------------

def zonalStatsForPolygon(
    raster_path,
    polygon,
    polygon_id=None
):
    """
    Calculates zonal stats for a single polygon from a local raster file.
    Ignores NAs or no data values in the raster.
    Ensures the CRS of the polygon matches the raster; reprojects if needed.
    """
    import rasterio
    import rasterio.mask
    import numpy as np
    from shapely.geometry import mapping
    from rasterstats import zonal_stats
    
    try:
        with rasterio.open(raster_path) as src:
            raster_crs = src.crs

            # Reproject polygon to raster CRS if needed
            try:
                import geopandas as gpd
                if hasattr(polygon, 'crs') and polygon.crs is not None and polygon.crs != raster_crs:
                    polygon = gpd.GeoSeries([polygon], crs=polygon.crs).to_crs(raster_crs).iloc[0]
                    print(f"Reprojected polygon to match raster CRS: {raster_crs}")
            except ImportError:
                pass  # If geopandas is not available, assume polygon is already in correct CRS

            shapes = [mapping(polygon)]
            out_image, out_transform = rasterio.mask.mask(src, shapes, crop=True)
            out_image = out_image[0]

            nodata = src.nodata if src.nodata is not None else np.nan # Use NaN if no nodata is set

            # Mask out nodata and NaN values
            mask = (out_image != nodata) & (~np.isnan(out_image))
            if not np.any(mask):
                # All values are nodata or NaN
                results = {
                    'min': None, 'max': None, 'mean': None, 'median': None,
                    'std': None, 'count': 0, 'majority': None, 'polygon_id': polygon_id
                }
                return results

            # Only use valid data for stats
            valid_data = out_image[mask]

            # Compute stats manually to ensure nodata/NaN are ignored
            results = {
                'min': float(np.min(valid_data)) if valid_data.size > 0 else None,
                'max': float(np.max(valid_data)) if valid_data.size > 0 else None,
                'mean': float(np.mean(valid_data)) if valid_data.size > 0 else None,
                'median': float(np.median(valid_data)) if valid_data.size > 0 else None,
                'std': float(np.std(valid_data)) if valid_data.size > 0 else None,
                'count': int(valid_data.size),
                'majority': float(np.bincount(valid_data.astype(int)).argmax()) if valid_data.size > 0 else None,
                'polygon_id': polygon_id
            }

            return results

    except Exception as e:
        print(f"Error processing polygon: {e}")
        return {
            'min': None, 'max': None, 'mean': None, 'median': None,
            'std': None, 'count': 0, 'majority': None, 'polygon_id': polygon_id
        }

def zonalStatsFromImageService(
    image_service_url,
    polygons_gdf,
    polygon_id_field=None,
    geometry=None,
    tmp_dir='.',        
    geometrySR=None,
    imageSR=None,
    pixelSize=30,
    format='tiff',
    pixelType="S16",
    noData = None,
    noDataInterpretation="esriNoDataMatchAny",
    interpolation="RSP_BilinearInterpolation",
    resample=True,
    quiet=False,
    cleanup =True
):
    """
    For each polygon in polygons_gdf, calculates a zonal histogram from an ArcGIS ImageServer.
    If geometry is provided, downloads a single raster for the bbox of the geometry and crops to each polygon. Only suggested for smaller areas to avoid resampling errors based on resampling.
    If bbox is not provided, downloads a raster for each polygon's bounding box.

    polygons_gdf: GeoDataFrame with polygons to calculate zonal stats for.
    cleanup: if True, deletes downloaded rasters after processing to save space.
    """
    import os
    import rasterio
    import rasterio.mask
    import numpy as np
    from shapely.geometry import mapping

    os.makedirs(tmp_dir, exist_ok=True)
    results = {}

    # check that polygons_gdf is a gdf and not empty
    try:
        import geopandas as gpd
        if not isinstance(polygons_gdf, gpd.GeoDataFrame):
            raise TypeError("polygons_gdf must be a GeoDataFrame.")
        if polygons_gdf.empty:
            raise ValueError("polygons_gdf is empty.")

    except Exception as e:
        print(f"Error checking polygons_gdf: {e}")
        return {}

    # Define default keys for stats
    default_keys = ['min', 'max', 'mean', 'median', 'std', 'count', 'majority', 'polygon_id']

    def default_result(polygon_id):
        return {k: None for k in default_keys[:-1]} | {'polygon_id': polygon_id}

    if geometry is not None:
        print(f"Using provided geometry for initial raster download")

        # Convert geometry to bounding box
        bbox, bboxSR = geometry_to_bbox(geometry, sr=geometrySR, quiet=quiet)

        # Download single raster for the bounding box
        raster_path = os.path.join(tmp_dir, "bbox_img.tif")
        downloadImageServiceToTiff(
            url=image_service_url,
            geometry=bbox,
            localdir=tmp_dir,
            localfile="bbox_img.tif",
            f="image",
            format=format,
            geometrySR=geometrySR,
            imageSR=imageSR,
            pixelType=pixelType,
            pixelSize=pixelSize,
            noData=noData,
            noDataInterpretation=noDataInterpretation,
            interpolation=interpolation,
            quiet=True
        )

        # Resample raster to desired pixel size if needed
        if resample:
            message = f"Checking if resampling is needed for raster at {raster_path} with desired pixel size {pixelSize}"
            with rasterio.open(raster_path) as src:
                native_pixel_size_x = src.transform.a
                native_pixel_size_y = -src.transform.e
                if pixelSize is not None and (abs(native_pixel_size_x - pixelSize) > 1e-6 or abs(native_pixel_size_y - pixelSize) > 1e-6):
                    print(f"Resampling raster from native pixel size ({native_pixel_size_x}, {native_pixel_size_y}) to desired pixel size ({pixelSize}, {pixelSize})")
                    from rasterio.warp import calculate_default_transform, reproject, Resampling

                    dst_transform, width, height = calculate_default_transform(
                        src.crs, src.crs, src.width, src.height, *src.bounds, resolution=pixelSize
                    )
                    dst_kwargs = src.meta.copy()
                    dst_kwargs.update({
                        'crs': src.crs,
                        'transform': dst_transform,
                        'width': width,
                        'height': height
                    })

                    resampled_raster_path = os.path.join(tmp_dir, "bbox_resampled.tif")
                    with rasterio.open(resampled_raster_path, 'w', **dst_kwargs) as dst:
                        for i in range(1, src.count + 1):
                            reproject(
                                source=rasterio.band(src, i),
                                destination=rasterio.band(dst, i),
                                src_transform=src.transform,
                                src_crs=src.crs,
                                dst_transform=dst_transform,
                                dst_crs=src.crs,
                                resampling=Resampling.bilinear
                            )
                    raster_path = resampled_raster_path
                else:
                    print("No resampling needed; using downloaded raster as-is.")

        # Crop the raster to each polygon and calculate zonal stats
        total_polygons = len(polygons_gdf)
        for idx, row in polygons_gdf.iterrows():
            # Print progress: if > 200 polys, print every nth, otherwise print every time.
            print_index = 100
            if total_polygons > 200:
                if (idx + 1) % print_index == 0 or (idx + 1) == 1:
                    print(f"Processing polygon {idx + 1}/{total_polygons}")
            else:
                print(f"Processing polygon {idx + 1}/{total_polygons}")
            
            polygon = row.geometry
            # Always use the polygon_id from the input row
            polygon_id = row[polygon_id_field] if polygon_id_field in row else idx
            try:
                results_poly = zonalStatsForPolygon(raster_path, polygon, polygon_id=polygon_id)
                if results_poly is None:
                    results[idx] = default_result(polygon_id)
                else:
                    results[idx] = results_poly
            except Exception as e:
                print(f"Error processing polygon {idx}: {e}")
                results[idx] = default_result(polygon_id)

        if cleanup:
            # delete the raster to save space
            os.remove(raster_path)

    else:
        print("No bounding box provided. Downloading raster for each polygon.")

        # get sr of polygons if not provided
        if hasattr(polygons_gdf, 'crs') and polygons_gdf.crs is not None:
            polySR = polygons_gdf.crs.to_epsg()

        # Process each polygon individually
        for idx, row in polygons_gdf.iterrows():
            print(f"Processing polygon {idx+1}/{len(polygons_gdf)}")
            polygon = row.geometry

            # convert polygon to bounding box
            bbox, bboxSR = geometry_to_bbox(polygon, sr = polySR, quiet=quiet)

            raster_path = os.path.join(tmp_dir, f"subset_{idx}.tif")

            try:
                downloadImageServiceToTiff(
                    url=image_service_url,
                    geometry=bbox,
                    localdir=tmp_dir,
                    localfile=f"subset_{idx}.tif",
                    f="image",
                    format=format,
                    geometrySR=bboxSR,
                    imageSR=imageSR,
                    pixelType=pixelType,
                    pixelSize=pixelSize,
                    noData=noData,
                    noDataInterpretation=noDataInterpretation,
                    interpolation=interpolation,
                    quiet=quiet
                )
                results_poly = zonalStatsForPolygon(raster_path, polygon, polygon_id=idx)
                if results_poly is None:
                    results[idx] = default_result(idx)
                else:
                    results[idx] = results_poly
                if cleanup:
                    # delete the raster to save space
                    os.remove(raster_path)
            except Exception as e:
                _qprint(f"Error processing polygon {idx}: {e}", quiet)
                results[idx] = default_result(idx)

    return results


# ---------------------------------------------------------------------------
# Geometry support
#-----------------------------------------------------------------------------
def geom_to_esri_json(obj, outSR = 4326):
    """Convert various geometry types to ESRI geometry dict and reproject to outSR.

    The function accepts:
      - bbox tuple/list (minx,miny,maxx,maxy)
      - comma-separated bbox string
      - GeoJSON-like dict
      - shapely geometry
      - geopandas GeoDataFrame / GeoSeries
      - ee.Geometry

    It reprojects geometries to `outSR` (EPSG code int) where possible using pyproj + shapely.
    If the input contains a CRS (GeoDataFrame, GeoSeries), that CRS is used as the source CRS.
    For ee.Geometry and plain GeoJSON/shapely inputs without a CRS, EPSG:4326 is assumed.

    Usage: 

    """

    import json
    import ee

    try:
        import geopandas as gpd
        from shapely.geometry import mapping, shape
        from shapely.ops import transform as shapely_transform
        import pyproj
    except Exception:
        gpd = None
        mapping = None
        shape = None
        shapely_transform = None
        pyproj = None
    
    def _is_esri_geometry_json(obj):
        if not isinstance(obj, dict):
            return False
        # Polygon
        if "rings" in obj and "spatialReference" in obj:
            return True
        # Point
        if "x" in obj and "y" in obj and "spatialReference" in obj:
            return True
        # Envelope
        if all(k in obj for k in ["xmin", "ymin", "xmax", "ymax"]) and "spatialReference" in obj:
            return True
        return False

    def _to_shapely_and_src_epsg(o):
        """Return (shapely_geom, src_epsg) or (None, None) if not convertible."""
        # GeoDataFrame / GeoSeries
        if gpd and isinstance(o, gpd.GeoDataFrame):
            if o.crs is None:
                src = 4326
            else:
                src = int(o.crs.to_epsg())
            geom = o.unary_union
            return geom, src
        if gpd and isinstance(o, gpd.GeoSeries):
            if o.crs is None:
                src = 4326
            else:
                src = int(o.crs.to_epsg())
            geom = o.unary_union
            return geom, src

        # shapely geometry
        if shape and hasattr(o, '__geo_interface__'):
            # try to read .crs if user attached one (non-standard)
            src = getattr(o, 'crs', None) or 4326
            return o, int(src)

        # GeoJSON-like dict
        if isinstance(o, dict) and 'type' in o and 'coordinates' in o:
            geom = shape(o)
            # no CRS encoded in simple GeoJSON -> assume 4326
            return geom, 4326

        # ee.Geometry
        if 'ee' in globals() and hasattr(ee, 'Geometry') and isinstance(o, ee.Geometry):
            geojson = o.getInfo()
            geom = shape(geojson)
            return geom, 4326

        return None, None

    def _reproject_shapely(geom, src_epsg, dst_epsg):
        if src_epsg is None:
            src_epsg = 4326
        if dst_epsg is None:
            dst_epsg = 4326
        if src_epsg == dst_epsg:
            return geom
        if pyproj is None or shapely_transform is None:
            raise RuntimeError('pyproj and shapely are required for reprojection')
        transformer = pyproj.Transformer.from_crs(int(src_epsg), int(dst_epsg), always_xy=True)
        return shapely_transform(transformer.transform, geom)

    # bbox tuple/list -> envelope (assume coords already in outSR)
    if isinstance(obj, (list, tuple)) and len(obj) == 4:
        minx, miny, maxx, maxy = obj
        return {"geometry": {"xmin": minx, "ymin": miny, "xmax": maxx, "ymax": maxy, "spatialReference": {"wkid": int(outSR)}},
                "geometryType": "esriGeometryEnvelope"}

    # JSON string -> dict or bbox string
    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            return geom_to_esri_json(parsed, outSR=outSR)
        except Exception:
            parts = obj.split(',')
            if len(parts) == 4:
                try:
                    nums = list(map(float, parts))
                    return geom_to_esri_json(nums, outSR=outSR)
                except Exception:
                    pass

    # If it's already an ESRI JSON dict with spatialReference matching outSR, return as-is (or reproject coords below)
    if isinstance(obj, dict) and _is_esri_geometry_json(obj):
        # If geometry is envelope, point, or rings, try to convert to shapely and reproject to outSR
        try:
            # Build a GeoJSON-like dict from ESRI JSON to reuse code
            esri = obj
            if 'rings' in esri:
                geojson = {'type': 'Polygon', 'coordinates': esri['rings']}
            elif 'x' in esri and 'y' in esri:
                geojson = {'type': 'Point', 'coordinates': [esri['x'], esri['y']]}
            elif all(k in esri for k in ['xmin', 'ymin', 'xmax', 'ymax']):
                # envelope -> polygon
                xmin = esri['xmin']; ymin = esri['ymin']; xmax = esri['xmax']; ymax = esri['ymax']
                coords = [[ [xmin, ymin], [xmin, ymax], [xmax, ymax], [xmax, ymin], [xmin, ymin] ]]
                geojson = {'type': 'Polygon', 'coordinates': coords}
            else:
                geojson = None
            if geojson:
                geom_shp, src_epsg = _to_shapely_and_src_epsg(geojson)
                if geom_shp is None:
                    geom_shp = shape(geojson)
                    src_epsg = esri.get('spatialReference', {}).get('wkid', outSR) or outSR
                geom_reproj = _reproject_shapely(geom_shp, src_epsg, outSR)
                geo_map = mapping(geom_reproj)
                # construct ESRI JSON polygon rings
                if geo_map['type'] == 'Point':
                    x, y = geo_map['coordinates']
                    return {"geometry": {"x": x, "y": y, "spatialReference": {"wkid": int(outSR)}}, "geometryType": "esriGeometryPoint"}
                if geo_map['type'] in ('Polygon', 'MultiPolygon'):
                    # ensure rings are in ESRI format (list of linear rings)
                    if geo_map['type'] == 'Polygon':
                        rings = geo_map['coordinates']
                    else:
                        rings = [ring for poly in geo_map['coordinates'] for ring in poly]
                    return {"geometry": {"rings": rings, "spatialReference": {"wkid": int(outSR)}}, "geometryType": "esriGeometryPolygon"}
        except Exception:
            # fallback to returning the input object with requested spatialReference
            obj['spatialReference'] = {'wkid': int(outSR)}
            return {"geometry": obj, "geometryType": None}

    # Try to convert GeoDataFrame/GeoSeries/shapely/ee/geojson to shapely + source epsg
    geom_shp, src_epsg = _to_shapely_and_src_epsg(obj)
    if geom_shp is not None:
        geom_reproj = _reproject_shapely(geom_shp, src_epsg, outSR)
        geo_map = mapping(geom_reproj)
        gtype = geo_map['type']
        coords = geo_map['coordinates']
        if gtype == 'Point':
            return {"geometry": {"x": coords[0], "y": coords[1], "spatialReference": {"wkid": int(outSR)}},
                    "geometryType": "esriGeometryPoint"}
        if gtype == 'Polygon':
            return {"geometry": {"rings": coords, "spatialReference": {"wkid": int(outSR)}},
                    "geometryType": "esriGeometryPolygon"}
        if gtype == 'MultiPolygon':
            rings = [ring for poly in coords for ring in poly]
            return {"geometry": {"rings": rings, "spatialReference": {"wkid": int(outSR)}},
                    "geometryType": "esriGeometryPolygon"}

    # GeoJSON-like dict last attempt
    if isinstance(obj, dict) and 'type' in obj and 'coordinates' in obj:
        geom_shp = shape(obj)
        geom_reproj = _reproject_shapely(geom_shp, 4326, outSR)
        geo_map = mapping(geom_reproj)
        if geo_map['type'] == 'Point':
            x, y = geo_map['coordinates']
            return {"geometry": {"x": x, "y": y, "spatialReference": {"wkid": int(outSR)}}, "geometryType": "esriGeometryPoint"}
        if geo_map['type'] in ('Polygon', 'MultiPolygon'):
            if geo_map['type'] == 'Polygon':
                rings = geo_map['coordinates']
            else:
                rings = [ring for poly in geo_map['coordinates'] for ring in poly]
            return {"geometry": {"rings": rings, "spatialReference": {"wkid": int(outSR)}}, "geometryType": "esriGeometryPolygon"}

    raise TypeError("Unsupported geometry type for geometry filter or failed to convert/reproject the input geometry.")

def geometry_to_bbox(geometry, sr = None, quiet=False):

    try:
            import geopandas as gpd
            from shapely.geometry import Polygon
            import ee
    except ImportError:
        gpd = None
        Polygon = None
        ee = None
    
    bounds = None

    # GeoDataFrame
    if gpd and isinstance(geometry, gpd.GeoDataFrame):
        if geometry.empty:
            raise ValueError("Provided GeoDataFrame is empty.")
        bounds = geometry.total_bounds
        _qprint(f"Extracted bounds from GeoDataFrame: {bounds}", quiet)
        if sr is None and geometry.crs is not None:
            bboxSR = int(geometry.crs.to_epsg())
            _qprint(f"Using sr from GeoDataFrame CRS: {sr}", quiet)
        elif sr is None:
            raise ValueError("No CRS found in GeoDataFrame and no 'sr' parameter was provided.")
    
    # Shapely Polygon
    elif Polygon and isinstance(geometry, Polygon):
        bounds = geometry.bounds
        _qprint(f"Extracted bounds from Shapely Polygon: {bounds}", quiet)
        if sr is None and hasattr(geometry, 'crs') and geometry.crs is not None:
            sr = int(geometry.crs.to_epsg())
            _qprint(f"Using bboxSR from Polygon CRS: {sr}", quiet)
        elif sr is None:
            raise ValueError("No CRS present Polygon and no 'sr' parameter was provided.")
    # GeoSeries
    elif gpd and isinstance(geometry, gpd.GeoSeries):
        bounds = geometry.total_bounds
        _qprint(f"Extracted bounds from GeoSeries: {bounds}", quiet)
        if sr is None and geometry.crs is not None:
            sr = int(geometry.crs.to_epsg())
            _qprint(f"Using bboxSR from GeoSeries CRS: {sr}", quiet)
        elif sr is None:
            raise ValueError("No CRS found in GeoSeries and no 'sr' parameter was provided.")
    
    # ee.Geometry
    elif isinstance(geometry, ee.Geometry):
        bounds_info = geometry.bounds().getInfo()
        coords = bounds_info['coordinates'][0]
        minx, miny = coords[0]
        maxx, maxy = coords[2]
        bounds = (minx, miny, maxx, maxy)
        _qprint(f"Extracted bounds from ee.Geometry: {bounds}", quiet)
        if sr is None:
            sr = 4326  # Earth Engine geometries are usually EPSG:4326
            _qprint(f"Using default bboxSR for ee.Geometry: {sr}", quiet)

    # List or tuple
    elif isinstance(geometry, (list, tuple)) and len(geometry) == 4:
        bounds = geometry
        _qprint(f"Using provided bounds list/tuple: {bounds}", quiet)
        if sr is None:
            raise ValueError("No 'sr' parameter was provided for bounding box list/tuple.")
    # String
    elif isinstance(geometry, str):
        bounds = geometry
        _qprint(f"Using provided bounds string: {bounds}", quiet)
        if sr is None:
            raise ValueError("No 'sr' parameter was provided for bounding box string.")
    # None
    elif geometry is None:
        raise ValueError("No geometry provided to extract bounding box.")

    else:
        raise TypeError("Unsupported geometry type for 'geometry' parameter.")
    
    return bounds, sr

def _qprint(msg, quiet=False):
    if not quiet:
        print(msg)

def _check_ending_slash(url):
    if not url.endswith('/'):
        url += '/'
    return url

def _check_ending_export(url):
    if not url.endswith('/exportImage?'):
        if url.endswith('/exportImage'):
            url += '?'
        else:
            url = _check_ending_slash(url)
            url += 'exportImage?'
    return url