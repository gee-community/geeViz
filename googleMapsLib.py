"""
Google Maps Platform client for geeViz.

Provides functions for ground-truthing and enriching remote sensing
analysis using Google Maps Platform APIs:

- **Geocoding** — address to coordinates and reverse
- **Places** — search, nearby, details, photos
- **Street View** — static images, panoramas, AI interpretation
- **Elevation** — terrain height at any location
- **Static Maps** — basemap images for reports
- **Air Quality** — current AQI and pollutants
- **Solar** — rooftop solar potential
- **Roads** — snap GPS traces to nearest roads

**24 public functions:**

- **Geocoding**: ``geocode``, ``reverse_geocode``, ``validate_address``
- **Places**: ``search_places``, ``search_nearby``, ``get_place_photo``
- **Street View**: ``streetview_metadata``, ``streetview_image``,
  ``streetview_images_cardinal``, ``streetview_panorama``, ``streetview_html``
- **AI Analysis**: ``interpret_image``, ``label_streetview``,
  ``segment_image``, ``segment_streetview``
- **Elevation**: ``get_elevation``, ``get_elevations``,
  ``get_elevation_along_path``
- **Environment**: ``get_air_quality``, ``get_solar_insights``,
  ``get_timezone``
- **Maps**: ``get_static_map``
- **Roads**: ``snap_to_roads``, ``nearest_roads``

Quick start::

    import geeViz.googleMapsLib as gm

    # Geocode an address
    result = gm.geocode("4240 S Olympic Way, Salt Lake City, UT")

    # Street View panorama + AI interpretation
    pano = gm.streetview_panorama(-111.80, 40.68, fov=360)
    analysis = gm.interpret_image(pano)

    # Semantic segmentation (SegFormer)
    seg = gm.segment_image(pano, model_variant="b4")

    # Elevation, air quality, solar
    elev = gm.get_elevation(-111.80, 40.68)
    aq = gm.get_air_quality(-111.80, 40.68)
    solar = gm.get_solar_insights(-111.80, 40.68)

Requires a ``GOOGLE_MAPS_PLATFORM_API_KEY`` in your environment or ``.env``
file. Gemini AI features use ``GEMINI_API_KEY``.

Copyright 2026 Ian Housman

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------

_API_KEY: str | None = None

# Key names to check, in priority order
_KEY_NAMES = (
    "GOOGLE_MAPS_PLATFORM_API_KEY",
    "MAPS_PLATFORM_API_KEY",
    "GOOGLE_API_KEY",
)


def _get_api_key() -> str:
    """Resolve the Google Maps Platform API key.

    Checks environment variables and ``.env`` in priority order:
    ``MAPS_PLATFORM_API_KEY``, ``GOOGLE_API_KEY``.
    """
    global _API_KEY
    if _API_KEY:
        return _API_KEY

    # Parse .env file first (env vars may have a different project's key)
    env_keys: dict[str, str] = {}
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_keys[k.strip()] = v.strip().strip("'\"")

    # Check each key name in priority order across both sources
    for key_name in _KEY_NAMES:
        for source in (env_keys, os.environ):
            key = source.get(key_name)
            if key:
                _API_KEY = key
                return key

    raise RuntimeError(
        "No Google Maps API key found. Set GOOGLE_MAPS_PLATFORM_API_KEY "
        "in your environment or .env file."
    )


def _fetch_json(url: str, params: dict | None = None,
                method: str = "GET", body: dict | None = None,
                headers: dict | None = None) -> dict:
    """HTTP request returning parsed JSON."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body else None
    hdrs = {"User-Agent": "geeViz/googleMaps"}
    if headers:
        hdrs.update(headers)
    if data and "Content-Type" not in hdrs:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_bytes(url: str, params: dict | None = None) -> bytes:
    """HTTP GET returning raw bytes."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "geeViz/googleMaps"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


###########################################################################
#  Geocoding API
###########################################################################

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def geocode(address: str) -> dict[str, Any] | None:
    """Geocode an address to coordinates using the Google Geocoding API.

    Args:
        address (str): Street address, place name, or location description.

    Returns:
        dict or None: Result with keys:

        - ``lat`` (float): Latitude.
        - ``lon`` (float): Longitude.
        - ``formatted_address`` (str): Full formatted address.
        - ``place_id`` (str): Google Place ID.
        - ``location_type`` (str): Accuracy — ``"ROOFTOP"``,
          ``"RANGE_INTERPOLATED"``, ``"GEOMETRIC_CENTER"``, or
          ``"APPROXIMATE"``.
        - ``address_components`` (list): Decomposed address parts.

        Returns ``None`` if no results found.

    Example:
        >>> result = geocode("4240 S Olympic Way, Salt Lake City, UT")
        >>> if result:
        ...     print(f"{result['lat']}, {result['lon']}")
    """
    data = _fetch_json(_GEOCODE_URL, {
        "address": address,
        "key": _get_api_key(),
    })
    if data.get("status") != "OK" or not data.get("results"):
        return None
    r = data["results"][0]
    loc = r["geometry"]["location"]
    return {
        "lat": loc["lat"],
        "lon": loc["lng"],
        "formatted_address": r.get("formatted_address", ""),
        "place_id": r.get("place_id", ""),
        "location_type": r["geometry"].get("location_type", ""),
        "address_components": r.get("address_components", []),
    }


###########################################################################
#  Places API (New)
###########################################################################

_PLACES_BASE = "https://places.googleapis.com/v1"


def search_places(
    query: str,
    lat: float | None = None,
    lon: float | None = None,
    radius: float = 5000,
    max_results: int = 10,
    included_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search for places using the Google Places API (New) Text Search.

    Args:
        query (str): Search text (e.g. "coffee shops", "gas station",
            "Yellowstone visitor center").
        lat (float, optional): Latitude for location bias.
        lon (float, optional): Longitude for location bias.
        radius (float, optional): Bias radius in meters. Defaults to 5000.
        max_results (int, optional): Maximum results (1-20). Defaults to 10.
        included_types (list, optional): Place type filters (e.g.
            ``["restaurant"]``, ``["gas_station"]``).

    Returns:
        list of dict: Each dict has keys: ``name``, ``display_name``,
        ``address``, ``lat``, ``lon``, ``types``, ``rating``,
        ``place_id``, ``photo_name`` (first photo resource name, if any).

    Example:
        >>> places = search_places("fire station", lat=40.76, lon=-111.89)
        >>> for p in places:
        ...     print(f"{p['display_name']}: {p['address']}")
    """
    body: dict[str, Any] = {
        "textQuery": query,
        "pageSize": min(max_results, 20),
        "languageCode": "en",
    }
    if lat is not None and lon is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": radius,
            }
        }
    if included_types:
        body["includedType"] = included_types[0]  # API accepts one type

    field_mask = (
        "places.id,places.displayName,places.formattedAddress,"
        "places.location,places.types,places.rating,"
        "places.userRatingCount,places.photos"
    )

    data = _fetch_json(
        f"{_PLACES_BASE}/places:searchText",
        method="POST",
        body=body,
        headers={
            "X-Goog-Api-Key": _get_api_key(),
            "X-Goog-FieldMask": field_mask,
        },
    )

    results = []
    for p in data.get("places", []):
        loc = p.get("location", {})
        photos = p.get("photos", [])
        results.append({
            "name": p.get("id", ""),
            "display_name": p.get("displayName", {}).get("text", ""),
            "address": p.get("formattedAddress", ""),
            "lat": loc.get("latitude"),
            "lon": loc.get("longitude"),
            "types": p.get("types", []),
            "rating": p.get("rating"),
            "rating_count": p.get("userRatingCount"),
            "place_id": p.get("id", ""),
            "photo_name": photos[0].get("name") if photos else None,
        })
    return results


def search_nearby(
    lat: float,
    lon: float,
    radius: float = 1000,
    included_types: list[str] | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Search for places near a location using Nearby Search (New).

    Args:
        lat (float): Latitude.
        lon (float): Longitude.
        radius (float, optional): Search radius in meters (max 50000).
            Defaults to 1000.
        included_types (list, optional): Place type filters (e.g.
            ``["restaurant"]``).
        max_results (int, optional): Maximum results (1-20). Defaults to 10.

    Returns:
        list of dict: Same format as :func:`search_places`.

    Example:
        >>> nearby = search_nearby(40.76, -111.89, radius=2000,
        ...     included_types=["park"])
    """
    body: dict[str, Any] = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": min(radius, 50000),
            }
        },
        "maxResultCount": min(max_results, 20),
        "languageCode": "en",
    }
    if included_types:
        body["includedTypes"] = included_types

    field_mask = (
        "places.id,places.displayName,places.formattedAddress,"
        "places.location,places.types,places.rating,"
        "places.userRatingCount,places.photos"
    )

    data = _fetch_json(
        f"{_PLACES_BASE}/places:searchNearby",
        method="POST",
        body=body,
        headers={
            "X-Goog-Api-Key": _get_api_key(),
            "X-Goog-FieldMask": field_mask,
        },
    )

    results = []
    for p in data.get("places", []):
        loc = p.get("location", {})
        photos = p.get("photos", [])
        results.append({
            "name": p.get("id", ""),
            "display_name": p.get("displayName", {}).get("text", ""),
            "address": p.get("formattedAddress", ""),
            "lat": loc.get("latitude"),
            "lon": loc.get("longitude"),
            "types": p.get("types", []),
            "rating": p.get("rating"),
            "rating_count": p.get("userRatingCount"),
            "place_id": p.get("id", ""),
            "photo_name": photos[0].get("name") if photos else None,
        })
    return results


def get_place_photo(photo_name: str, max_width: int = 400,
                    max_height: int = 400) -> bytes | None:
    """Fetch a place photo by its resource name.

    Photo names come from :func:`search_places` or :func:`search_nearby`
    results (the ``photo_name`` field).

    Args:
        photo_name (str): Photo resource name from a Places API response.
        max_width (int, optional): Maximum width in pixels (1-4800).
        max_height (int, optional): Maximum height in pixels (1-4800).

    Returns:
        bytes or None: JPEG/PNG image bytes, or ``None`` on error.

    Example:
        >>> places = search_places("Arches National Park visitor center")
        >>> if places and places[0]['photo_name']:
        ...     photo = get_place_photo(places[0]['photo_name'])
    """
    if not photo_name:
        return None
    try:
        return _fetch_bytes(
            f"{_PLACES_BASE}/{photo_name}/media",
            {"key": _get_api_key(),
             "maxWidthPx": str(max_width),
             "maxHeightPx": str(max_height)},
        )
    except Exception:
        return None


###########################################################################
#  Street View Static API
###########################################################################

_SV_STATIC_URL = "https://maps.googleapis.com/maps/api/streetview"
_SV_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
_SV_DEFAULT_SIZE = "640x480"
_SV_DEFAULT_FOV = 90


def streetview_metadata(
    lon: float,
    lat: float,
    radius: int = 50,
    source: str = "default",
) -> dict[str, Any]:
    """Check if Street View imagery exists at a location.

    This is a free call (no quota consumed).

    Args:
        lon (float): Longitude in decimal degrees.
        lat (float): Latitude in decimal degrees.
        radius (int, optional): Search radius in meters. Defaults to 50.
        source (str, optional): ``"default"`` or ``"outdoor"``.

    Returns:
        dict: Keys: ``status``, ``pano_id``, ``location``, ``date``,
        ``copyright``.

    Example:
        >>> meta = streetview_metadata(-111.89, 40.76)
        >>> if meta['status'] == 'OK':
        ...     print(f"Imagery from {meta['date']}")
    """
    return _fetch_json(_SV_METADATA_URL, {
        "location": f"{lat},{lon}",
        "radius": str(radius),
        "source": source,
        "key": _get_api_key(),
    })


def streetview_image(
    lon: float,
    lat: float,
    heading: float = 0,
    pitch: float = 0,
    fov: float = _SV_DEFAULT_FOV,
    size: str = _SV_DEFAULT_SIZE,
    radius: int = 50,
    source: str = "default",
) -> bytes | None:
    """Fetch a Street View static image as JPEG bytes.

    Returns ``None`` if no imagery exists (checks metadata first).

    Args:
        lon (float): Longitude.
        lat (float): Latitude.
        heading (float, optional): Compass heading (0=N, 90=E, 180=S, 270=W).
        pitch (float, optional): Camera pitch (positive=up).
        fov (float, optional): Field of view (1-120). Defaults to 90.
        size (str, optional): Image size. Defaults to ``"640x480"``.
        radius (int, optional): Search radius. Defaults to 50.
        source (str, optional): ``"default"`` or ``"outdoor"``.

    Returns:
        bytes or None: JPEG image bytes.
    """
    meta = streetview_metadata(lon, lat, radius=radius, source=source)
    if meta.get("status") != "OK":
        return None
    try:
        return _fetch_bytes(_SV_STATIC_URL, {
            "location": f"{lat},{lon}",
            "size": size,
            "heading": str(heading),
            "pitch": str(pitch),
            "fov": str(fov),
            "radius": str(radius),
            "source": source,
            "return_error_code": "true",
            "key": _get_api_key(),
        })
    except urllib.error.HTTPError:
        return None


def streetview_images_cardinal(
    lon: float,
    lat: float,
    pitch: float = 0,
    fov: float = _SV_DEFAULT_FOV,
    size: str = _SV_DEFAULT_SIZE,
    radius: int = 50,
    source: str = "default",
) -> dict[str, bytes] | None:
    """Fetch Street View images looking N, E, S, and W.

    Returns ``None`` if no imagery exists.

    Args:
        lon, lat, pitch, fov, size, radius, source: See :func:`streetview_image`.

    Returns:
        dict or None: ``{"N": bytes, "E": bytes, "S": bytes, "W": bytes}``.
    """
    meta = streetview_metadata(lon, lat, radius=radius, source=source)
    if meta.get("status") != "OK":
        return None
    results = {}
    for label, heading in {"N": 0, "E": 90, "S": 180, "W": 270}.items():
        img = streetview_image(lon, lat, heading=heading, pitch=pitch, fov=fov,
                               size=size, radius=radius, source=source)
        if img:
            results[label] = img
    return results if results else None


def streetview_panorama(
    lon: float,
    lat: float,
    heading: float = 0,
    fov: float = 360,
    pitch: float = 0,
    size: str = _SV_DEFAULT_SIZE,
    radius: int = 50,
    source: str = "default",
) -> bytes | None:
    """Fetch a wide-angle or full 360° Street View panorama as a stitched image.

    The Google Street View Static API caps FOV at 120°.  This function
    automatically splits wider requests into multiple 120° frames and
    stitches them horizontally using PIL.

    Args:
        lon (float): Longitude.
        lat (float): Latitude.
        heading (float, optional): Center compass heading of the panorama
            (0=North). The panorama spans ``heading - fov/2`` to
            ``heading + fov/2``.  Defaults to ``0``.
        fov (float, optional): Total horizontal field of view in degrees
            (1–360).  Values ≤ 120 are handled in a single frame.
            Defaults to ``360``.
        pitch (float, optional): Camera pitch. Defaults to ``0``.
        size (str, optional): Per-frame size as ``"WxH"``.
            Defaults to ``"640x480"``.
        radius (int, optional): Search radius. Defaults to ``50``.
        source (str, optional): ``"default"`` or ``"outdoor"``.

    Returns:
        bytes or None: JPEG bytes of the stitched panorama, or ``None``
        if no imagery exists.

    Example:
        >>> pano = streetview_panorama(-111.80, 40.68, heading=0, fov=360)
        >>> if pano:
        ...     with open("panorama_360.jpg", "wb") as f:
        ...         f.write(pano)
    """
    from PIL import Image
    import io as _io

    meta = streetview_metadata(lon, lat, radius=radius, source=source)
    if meta.get("status") != "OK":
        return None

    fov = max(1, min(fov, 360))

    # Single frame if within API limit
    if fov <= 120:
        return streetview_image(lon, lat, heading=heading, pitch=pitch,
                                fov=fov, size=size, radius=radius, source=source)

    # Multiple frames: split into chunks ≤120°, fetch in parallel.
    # Each frame's FOV = step size so the frames tile exactly.
    # When pitch ≠ 0, we alpha-blend a thin seam zone to smooth
    # exposure differences between adjacent frames.
    import concurrent.futures
    import numpy as np

    _MAX_FRAME_FOV = 120
    n_frames = max(2, -(-int(fov) // _MAX_FRAME_FOV))  # ceil division
    frame_fov = fov / n_frames  # per-frame FOV = angular step
    start_heading = (heading - fov / 2 + frame_fov / 2) % 360
    headings = [(start_heading + i * frame_fov) % 360 for i in range(n_frames)]

    def _fetch_frame(h):
        """Fetch a single frame (metadata already verified)."""
        try:
            return _fetch_bytes(_SV_STATIC_URL, {
                "location": f"{lat},{lon}",
                "size": size,
                "heading": str(h),
                "pitch": str(pitch),
                "fov": str(frame_fov),
                "radius": str(radius),
                "source": source,
                "return_error_code": "true",
                "key": _get_api_key(),
            })
        except Exception:
            return None

    # Fetch all frames simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_frames) as pool:
        raw_frames = list(pool.map(_fetch_frame, headings))

    frames = []
    for img_bytes in raw_frames:
        if img_bytes:
            frames.append(Image.open(_io.BytesIO(img_bytes)).convert("RGB"))

    if not frames:
        return None

    # Blend width: proportional to |pitch|, 0 at pitch=0
    # At pitch=30 ~8% of frame width, at pitch=45 ~12%
    blend_px = int(frames[0].size[0] * min(0.15, abs(pitch) / 300.0)) if abs(pitch) > 5 else 0

    fw, fh = frames[0].size
    total_w = fw * len(frames)
    pano = Image.new("RGB", (total_w, fh))

    # Place first frame
    pano.paste(frames[0], (0, 0))

    for i in range(1, len(frames)):
        x = fw * i
        curr = frames[i]

        if blend_px > 0:
            # Alpha-blend a thin strip at the left seam of this frame
            left_arr = np.array(pano.crop((x - blend_px, 0, x, fh))).astype(np.float32)
            right_arr = np.array(curr.crop((0, 0, blend_px, fh))).astype(np.float32)
            alpha = np.linspace(1, 0, blend_px).reshape(1, -1, 1)
            blended = (left_arr * alpha + right_arr * (1 - alpha)).astype(np.uint8)
            pano.paste(Image.fromarray(blended), (x - blend_px, 0))
            # Paste remainder of frame after blend zone
            pano.paste(curr.crop((blend_px, 0, curr.size[0], fh)), (x, 0))
        else:
            pano.paste(curr, (x, 0))

    buf = _io.BytesIO()
    pano.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def interpret_image(
    image_bytes: bytes,
    prompt: str | None = None,
    model: str = "gemini-3-flash-preview",
    context: str | None = None,
) -> dict[str, Any]:
    """Interpret a Street View or satellite image using Google Gemini.

    Sends the image to Gemini with instructions to identify and count
    all notable features. Returns a structured description with a
    tabular object inventory.

    Args:
        image_bytes (bytes): JPEG or PNG image bytes.
        prompt (str, optional): Custom prompt to override the default.
            When ``None``, uses a built-in prompt that asks for feature
            identification and a tabular count.
        model (str, optional): Gemini model name. Defaults to
            ``"gemini-3-flash-preview"``.
        context (str, optional): Additional context to include in the
            prompt (e.g. location, date, purpose). Defaults to ``None``.

    Returns:
        dict: Keys:

        - ``description`` (str): Full text description of the image.
        - ``object_counts`` (str): Markdown table of object counts.
        - ``raw_response`` (str): Complete Gemini response text.

    Example:
        >>> img = streetview_image(-111.80, 40.68, heading=0)
        >>> result = interpret_image(img)
        >>> print(result['description'])
        >>> print(result['object_counts'])
    """
    from google import genai
    from google.genai import types

    api_key = _get_gemini_key()
    client = genai.Client(api_key=api_key)

    if prompt is None:
        prompt = (
            "This is a Google Street View image. Analyze it thoroughly.\n\n"
            "1. **Description**: Describe the scene in 2-3 sentences — "
            "the setting, land use, vegetation, infrastructure, and any "
            "notable features.\n\n"
            "2. **Object Inventory**: List every distinct object or feature "
            "you can identify with a count. Format as a markdown table with "
            "columns: | Object | Count | Notes |\n"
            "Include items like: buildings, houses, vehicles, trees, signs, "
            "driveways, fences, utility poles, sidewalks, mailboxes, etc. "
            "Be specific (e.g. 'brick ranch house' not just 'building').\n\n"
            "3. **Land Cover Assessment**: Estimate the approximate percentage "
            "of the visible area that is: impervious surface (road, driveway, "
            "roof), vegetation (lawn, trees), bare soil, sky."
        )
        if context:
            prompt = f"Location context: {context}\n\n{prompt}"

    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    response = client.models.generate_content(
        model=model,
        contents=[prompt, image_part],
        config=types.GenerateContentConfig(temperature=0.2),
    )

    raw = response.text

    # Parse out sections
    description = ""
    object_counts = ""
    lines = raw.split("\n")
    in_table = False
    desc_lines = []
    table_lines = []

    for line in lines:
        if "|" in line and ("Object" in line or "Count" in line or "---" in line):
            in_table = True
        if in_table:
            if "|" in line:
                table_lines.append(line)
            elif line.strip() == "":
                if table_lines:
                    in_table = False
            else:
                in_table = False
        elif not line.strip().startswith("#") and not line.strip().startswith("**Object"):
            desc_lines.append(line)

    description = "\n".join(desc_lines).strip()
    object_counts = "\n".join(table_lines).strip()

    return {
        "description": description,
        "object_counts": object_counts,
        "raw_response": raw,
    }


def _get_gemini_key() -> str:
    """Get the Gemini API key, separate from Maps Platform key."""
    _env = {}
    _env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(_env_path):
        with open(_env_path) as _f:
            for _line in _f:
                _line = _line.strip()
                if "=" in _line and not _line.startswith("#"):
                    _k, _v = _line.split("=", 1)
                    _env[_k.strip()] = _v.strip().strip("'\"")
    # Check Gemini-specific key first, then general Google key
    for key_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        for source in (_env, os.environ):
            val = source.get(key_name)
            if val:
                return val
    return _get_api_key()  # last resort: use Maps Platform key


def label_streetview(
    lon: float,
    lat: float,
    prompt: str | None = None,
    heading: float = 0,
    fov: float = 360,
    pitch: float = 0,
    size: str = _SV_DEFAULT_SIZE,
    radius: int = 50,
    source: str = "default",
    model: str = "gemini-3-flash-preview",
    max_labels: int = 30,
    font_size: int = 12,
) -> dict[str, Any] | None:
    """Fetch a Street View panorama and label detected objects with bounding boxes.

    Uses Gemini's vision model to detect objects and return bounding
    boxes, then draws labeled boxes on the panorama.

    Args:
        lon (float): Longitude.
        lat (float): Latitude.
        prompt (str, optional): Custom detection prompt. The location
            context header and JSON format footer are always included.
        heading (float, optional): Center heading. Defaults to ``0``.
        fov (float, optional): Field of view (1-360). Defaults to ``360``.
        pitch (float, optional): Camera pitch. Defaults to ``0``.
        size (str, optional): Per-frame size. Defaults to ``"640x480"``.
        radius (int, optional): Search radius. Defaults to ``50``.
        source (str, optional): ``"default"`` or ``"outdoor"``.
        model (str, optional): Gemini model. Defaults to
            ``"gemini-3-flash-preview"``.
        max_labels (int, optional): Maximum objects. Defaults to ``30``.
        font_size (int, optional): Label font size. Defaults to ``12``.

    Returns:
        dict or None: Keys: ``image``, ``detections``, ``summary``,
        ``original``, ``location``.

    Example:
        >>> result = label_streetview(-111.80, 40.68, fov=360)
        >>> if result:
        ...     with open("labeled.jpg", "wb") as f:
        ...         f.write(result['image'])
        ...     print(result['summary'])
    """
    from PIL import Image, ImageDraw, ImageFont
    import io as _io
    from google import genai
    from google.genai import types

    # Fetch the panorama
    pano_bytes = streetview_panorama(
        lon, lat, heading=heading, fov=fov, pitch=pitch,
        size=size, radius=radius, source=source,
    )
    if pano_bytes is None:
        return None

    pano_img = Image.open(_io.BytesIO(pano_bytes)).convert("RGB")
    img_w, img_h = pano_img.size

    # Get location info
    meta = streetview_metadata(lon, lat, radius=radius, source=source)
    location_str = ""
    if meta.get("status") == "OK":
        addr = reverse_geocode(lon, lat)
        location_str = addr.get("formatted_address", "") if addr else f"({lat:.4f}, {lon:.4f})"

    # Build prompt: header + body + footer
    _header = f"This is a Google Street View panorama image at {location_str}.\n"
    if prompt is None:
        _body = (
            f"Detect and label the {max_labels} most noteworthy features and objects.\n"
            "Be specific with labels (e.g. 'white SUV' not just 'car').\n"
        )
    else:
        _body = prompt + "\n"
    _footer = (
        "\nFor each detection, return the object label and its bounding box "
        "as [y_min, x_min, y_max, x_max] normalized to 0-1000.\n"
        "Do NOT identify or label Google watermarks, copyright text, or UI overlays.\n"
        "Return ONLY valid JSON:\n"
        '{"detections": [{"label": "object name", "box_2d": [y_min, x_min, y_max, x_max]}]}\n'
    )

    # Call Gemini
    api_key = _get_gemini_key()
    client = genai.Client(api_key=api_key)
    image_part = types.Part.from_bytes(data=pano_bytes, mime_type="image/jpeg")

    response = client.models.generate_content(
        model=model,
        contents=[_header + _body + _footer, image_part],
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    # Parse
    import json as _json
    try:
        detections = _json.loads(response.text.strip()).get("detections", [])
    except (_json.JSONDecodeError, AttributeError):
        detections = []

    # One color per unique label
    import random as _rand, colorsys as _cs
    _rand.seed(42)
    unique_labels = list(dict.fromkeys(d.get("label", "?") for d in detections))
    label_colors: dict[str, tuple] = {}
    for i, lbl in enumerate(unique_labels):
        hue = (i / max(len(unique_labels), 1) + _rand.uniform(-0.03, 0.03)) % 1.0
        r, g, b = _cs.hsv_to_rgb(hue, 0.9, 0.95)
        label_colors[lbl] = (int(r * 255), int(g * 255), int(b * 255))

    # Draw boxes
    draw = ImageDraw.Draw(pano_img)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.load_default(size=font_size)
        except TypeError:
            font = ImageFont.load_default()

    parsed = []
    for det in detections:
        label = det.get("label", "?")
        box = det.get("box_2d", [])
        if len(box) != 4:
            continue
        color = label_colors.get(label, (0, 255, 100))
        y0, x0, y1, x1 = box
        px_x0 = int(x0 / 1000 * img_w)
        px_y0 = int(y0 / 1000 * img_h)
        px_x1 = int(x1 / 1000 * img_w)
        px_y1 = int(y1 / 1000 * img_h)

        # Dashed box
        for edge in [[(px_x0,px_y0),(px_x1,px_y0)], [(px_x1,px_y0),(px_x1,px_y1)],
                     [(px_x1,px_y1),(px_x0,px_y1)], [(px_x0,px_y1),(px_x0,px_y0)]]:
            (sx,sy),(ex,ey) = edge
            dx, dy = ex-sx, ey-sy
            length = max(1, (dx**2+dy**2)**0.5)
            for d in range(int(length/13)+1):
                sf = d*13/length
                ef = min((d*13+8)/length, 1.0)
                draw.line([(int(sx+dx*sf),int(sy+dy*sf)),
                           (int(sx+dx*ef),int(sy+dy*ef))], fill=color, width=2)

        # Label
        tb = draw.textbbox((0,0), label, font=font)
        tw, th = tb[2]-tb[0], tb[3]-tb[1]
        ly = max(0, px_y0-th-4)
        draw.rectangle([px_x0, ly, px_x0+tw+6, ly+th+4], fill=(0,0,0))
        draw.text((px_x0+3, ly+1), label, fill=color, font=font)

        parsed.append({"label": label, "box": [px_x0,px_y0,px_x1,px_y1], "color": color})

    # Summary
    lines = ["| # | Object | Box |", "|---|---|---|"]
    for i, d in enumerate(parsed):
        b = d["box"]
        lines.append(f"| {i+1} | {d['label']} | ({b[0]},{b[1]},{b[2]},{b[3]}) |")

    buf = _io.BytesIO()
    pano_img.save(buf, format="JPEG", quality=92)

    return {
        "image": buf.getvalue(),
        "detections": parsed,
        "summary": "\n".join(lines),
        "original": pano_bytes,
        "location": location_str,
    }


def streetview_html(
    lon: float,
    lat: float,
    headings: list[float] | None = None,
    pitch: float = 0,
    fov: float = _SV_DEFAULT_FOV,
    size: str = "400x300",
    radius: int = 50,
    source: str = "default",
    title: str | None = None,
) -> str | None:
    """Generate an HTML panel with embedded Street View images.

    Args:
        lon, lat: Coordinates.
        headings (list, optional): Compass headings. Defaults to [0,90,180,270].
        pitch, fov, size, radius, source: See :func:`streetview_image`.
        title (str, optional): Title text. Auto-generated if None.

    Returns:
        str or None: Self-contained HTML string, or None if no imagery.
    """
    meta = streetview_metadata(lon, lat, radius=radius, source=source)
    if meta.get("status") != "OK":
        return None
    if headings is None:
        headings = [0, 90, 180, 270]
    dir_labels = {0: "N", 45: "NE", 90: "E", 135: "SE",
                  180: "S", 225: "SW", 270: "W", 315: "NW"}
    if title is None:
        loc = meta.get("location", {})
        title = f"Street View at ({loc.get('lat', lat):.4f}, {loc.get('lng', lon):.4f}) — {meta.get('date', '?')}"
    tags = []
    for h in headings:
        img = streetview_image(lon, lat, heading=h, pitch=pitch, fov=fov,
                               size=size, radius=radius, source=source)
        if img:
            b64 = base64.b64encode(img).decode("ascii")
            label = dir_labels.get(int(h) % 360, f"{h}°")
            tags.append(
                f'<div style="text-align:center;margin:4px;">'
                f'<img src="data:image/jpeg;base64,{b64}" style="border-radius:4px;max-width:100%;"/>'
                f'<div style="font-size:12px;color:#aaa;">{label} ({h}°)</div></div>'
            )
    if not tags:
        return None
    cols = min(len(tags), 2)
    return (
        f'<div style="background:#1e1e1e;padding:12px;border-radius:8px;max-width:900px;font-family:sans-serif;">'
        f'<div style="color:#eee;font-size:14px;font-weight:bold;margin-bottom:8px;">{title}</div>'
        f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:6px;">{"".join(tags)}</div>'
        f'<div style="color:#666;font-size:10px;margin-top:6px;">{meta.get("copyright", "© Google")}</div></div>'
    )


###########################################################################
#  Elevation API
###########################################################################

_ELEVATION_URL = "https://maps.googleapis.com/maps/api/elevation/json"


def get_elevation(lon: float, lat: float) -> float | None:
    """Get elevation in meters at a geographic location.

    Args:
        lon (float): Longitude.
        lat (float): Latitude.

    Returns:
        float or None: Elevation in meters above sea level,
        or ``None`` on error.

    Example:
        >>> elev = get_elevation(-111.80, 40.68)
        >>> print(f"{elev:.0f} meters")
    """
    data = _fetch_json(_ELEVATION_URL, {
        "locations": f"{lat},{lon}",
        "key": _get_api_key(),
    })
    if data.get("status") == "OK" and data.get("results"):
        return data["results"][0].get("elevation")
    return None


def get_elevations(points: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Get elevations for multiple locations in one request.

    Args:
        points (list): List of ``(lon, lat)`` tuples. Max ~500 per request.

    Returns:
        list of dict: Each dict has ``lon``, ``lat``, ``elevation`` (meters),
        and ``resolution`` (meters).

    Example:
        >>> pts = [(-111.80, 40.68), (-111.81, 40.69), (-111.82, 40.70)]
        >>> elevs = get_elevations(pts)
        >>> for e in elevs:
        ...     print(f"{e['lat']:.4f}: {e['elevation']:.0f}m")
    """
    locations = "|".join(f"{lat},{lon}" for lon, lat in points)
    data = _fetch_json(_ELEVATION_URL, {
        "locations": locations,
        "key": _get_api_key(),
    })
    results = []
    if data.get("status") == "OK":
        for r in data.get("results", []):
            loc = r.get("location", {})
            results.append({
                "lon": loc.get("lng"),
                "lat": loc.get("lat"),
                "elevation": r.get("elevation"),
                "resolution": r.get("resolution"),
            })
    return results


def get_elevation_along_path(
    points: list[tuple[float, float]],
    samples: int = 100,
) -> list[dict[str, Any]]:
    """Get elevation profile along a path.

    Samples evenly-spaced points along the path defined by the
    input waypoints.

    Args:
        points (list): Path waypoints as ``(lon, lat)`` tuples.
        samples (int, optional): Number of sample points. Defaults to 100.

    Returns:
        list of dict: Sampled points with ``lon``, ``lat``, ``elevation``,
        ``resolution``.

    Example:
        >>> path = [(-111.80, 40.68), (-111.85, 40.72)]
        >>> profile = get_elevation_along_path(path, samples=50)
    """
    path_str = "|".join(f"{lat},{lon}" for lon, lat in points)
    data = _fetch_json(_ELEVATION_URL, {
        "path": path_str,
        "samples": str(samples),
        "key": _get_api_key(),
    })
    results = []
    if data.get("status") == "OK":
        for r in data.get("results", []):
            loc = r.get("location", {})
            results.append({
                "lon": loc.get("lng"),
                "lat": loc.get("lat"),
                "elevation": r.get("elevation"),
                "resolution": r.get("resolution"),
            })
    return results


###########################################################################
#  Static Maps API
###########################################################################

_STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"


def get_static_map(
    lon: float,
    lat: float,
    zoom: int = 14,
    size: str = "640x480",
    maptype: str = "satellite",
    markers: list[tuple[float, float]] | None = None,
    path_points: list[tuple[float, float]] | None = None,
    path_color: str = "red",
    format: str = "png",
) -> bytes | None:
    """Get a static map image centered on a location.

    Args:
        lon (float): Center longitude.
        lat (float): Center latitude.
        zoom (int, optional): Zoom level (1-21). Defaults to 14.
        size (str, optional): Image size. Defaults to ``"640x480"``.
        maptype (str, optional): ``"satellite"``, ``"roadmap"``,
            ``"terrain"``, or ``"hybrid"``. Defaults to ``"satellite"``.
        markers (list, optional): List of ``(lon, lat)`` marker positions.
        path_points (list, optional): List of ``(lon, lat)`` for a path overlay.
        path_color (str, optional): Path line color. Defaults to ``"red"``.
        format (str, optional): ``"png"`` or ``"jpg"``. Defaults to ``"png"``.

    Returns:
        bytes or None: Image bytes.

    Example:
        >>> img = get_static_map(-111.80, 40.68, zoom=16, maptype="hybrid")
        >>> with open("map.png", "wb") as f:
        ...     f.write(img)
    """
    params: dict[str, str] = {
        "center": f"{lat},{lon}",
        "zoom": str(zoom),
        "size": size,
        "maptype": maptype,
        "format": format,
        "key": _get_api_key(),
    }
    if markers:
        marker_str = "|".join(f"{la},{lo}" for lo, la in markers)
        params["markers"] = marker_str
    if path_points:
        path_str = "|".join(f"{la},{lo}" for lo, la in path_points)
        params["path"] = f"color:{path_color}|weight:3|{path_str}"

    try:
        return _fetch_bytes(_STATIC_MAP_URL, params)
    except Exception:
        return None


###########################################################################
#  Air Quality API
###########################################################################

_AQ_BASE = "https://airquality.googleapis.com/v1"


def get_air_quality(
    lon: float,
    lat: float,
) -> dict[str, Any] | None:
    """Get current air quality conditions at a location.

    Args:
        lon (float): Longitude.
        lat (float): Latitude.

    Returns:
        dict or None: Keys: ``aqi`` (US AQI), ``category``,
        ``dominant_pollutant``, ``pollutants`` (list), ``date``.

    Example:
        >>> aq = get_air_quality(-111.89, 40.76)
        >>> if aq:
        ...     print(f"AQI: {aq['aqi']} ({aq['category']})")
    """
    try:
        data = _fetch_json(
            f"{_AQ_BASE}/currentConditions:lookup",
            method="POST",
            body={
                "location": {"latitude": lat, "longitude": lon},
                "extraComputations": ["DOMINANT_POLLUTANT_CONCENTRATION"],
                "languageCode": "en",
            },
            headers={
                "X-Goog-Api-Key": _get_api_key(),
                "Content-Type": "application/json",
            },
        )
    except Exception:
        return None

    indexes = data.get("indexes", [])
    us_aqi = next((i for i in indexes if i.get("code") == "uaqi"), None)
    if not us_aqi:
        us_aqi = indexes[0] if indexes else {}

    pollutants = []
    for p in data.get("pollutants", []):
        pollutants.append({
            "code": p.get("code"),
            "name": p.get("displayName"),
            "concentration": p.get("concentration", {}).get("value"),
            "units": p.get("concentration", {}).get("units"),
        })

    return {
        "aqi": us_aqi.get("aqi"),
        "category": us_aqi.get("category"),
        "dominant_pollutant": us_aqi.get("dominantPollutant"),
        "color": us_aqi.get("color"),
        "pollutants": pollutants,
        "date": data.get("dateTime"),
    }


###########################################################################
#  Solar API
###########################################################################

_SOLAR_BASE = "https://solar.googleapis.com/v1"


def get_solar_insights(
    lon: float,
    lat: float,
    quality: str = "MEDIUM",
) -> dict[str, Any] | None:
    """Get rooftop solar potential for the nearest building.

    Args:
        lon (float): Longitude.
        lat (float): Latitude.
        quality (str, optional): Image quality — ``"LOW"``, ``"MEDIUM"``,
            or ``"HIGH"``. Defaults to ``"MEDIUM"``.

    Returns:
        dict or None: Keys: ``max_panels``, ``max_capacity_watts``,
        ``max_annual_kwh``, ``roof_area_m2``, ``max_sunshine_hours``,
        ``carbon_offset_kg``.

    Example:
        >>> solar = get_solar_insights(-111.80, 40.68)
        >>> if solar:
        ...     print(f"Capacity: {solar['max_capacity_watts']:.0f}W")
        ...     print(f"Annual: {solar['max_annual_kwh']:.0f} kWh")
    """
    try:
        data = _fetch_json(
            f"{_SOLAR_BASE}/buildingInsights:findClosest",
            {
                "location.latitude": str(lat),
                "location.longitude": str(lon),
                "requiredQuality": quality,
                "key": _get_api_key(),
            },
        )
    except Exception:
        return None

    if "error" in data:
        return None

    solar_info = data.get("solarPotential", {})
    panels = solar_info.get("solarPanelConfigs", [])
    best = panels[-1] if panels else {}

    return {
        "max_panels": best.get("panelsCount", 0),
        "max_capacity_watts": solar_info.get("maxArrayPanelsCount", 0) * solar_info.get("panelCapacityWatts", 400),
        "max_annual_kwh": best.get("yearlyEnergyDcKwh", 0),
        "roof_area_m2": solar_info.get("wholeRoofStats", {}).get("areaMeters2", 0),
        "max_sunshine_hours": solar_info.get("maxSunshineHoursPerYear", 0),
        "carbon_offset_kg": solar_info.get("carbonOffsetFactorKgPerMwh", 0) * best.get("yearlyEnergyDcKwh", 0) / 1000,
        "panel_capacity_watts": solar_info.get("panelCapacityWatts", 0),
        "imagery_date": data.get("imageryDate", {}),
    }


###########################################################################
#  Roads API
###########################################################################

_ROADS_BASE = "https://roads.googleapis.com/v1"


def snap_to_roads(
    points: list[tuple[float, float]],
    interpolate: bool = False,
) -> list[dict[str, Any]]:
    """Snap GPS points to the nearest road segments.

    Args:
        points (list): GPS trace as ``(lon, lat)`` tuples. Max 100 points.
        interpolate (bool, optional): If True, interpolate additional
            points along the road between snapped locations.
            Defaults to ``False``.

    Returns:
        list of dict: Snapped points with ``lon``, ``lat``, ``place_id``,
        and ``original_index`` (which input point this snapped from).

    Example:
        >>> gps = [(-111.80, 40.68), (-111.81, 40.69), (-111.82, 40.70)]
        >>> snapped = snap_to_roads(gps)
        >>> for s in snapped:
        ...     print(f"({s['lat']:.5f}, {s['lon']:.5f})")
    """
    path = "|".join(f"{lat},{lon}" for lon, lat in points)
    data = _fetch_json(f"{_ROADS_BASE}/snapToRoads", {
        "path": path,
        "interpolate": str(interpolate).lower(),
        "key": _get_api_key(),
    })
    results = []
    for pt in data.get("snappedPoints", []):
        loc = pt.get("location", {})
        results.append({
            "lon": loc.get("longitude"),
            "lat": loc.get("latitude"),
            "place_id": pt.get("placeId"),
            "original_index": pt.get("originalIndex"),
        })
    return results


def nearest_roads(
    lon: float,
    lat: float,
) -> list[dict[str, Any]]:
    """Find the nearest road segments to a point.

    Args:
        lon (float): Longitude.
        lat (float): Latitude.

    Returns:
        list of dict: Nearby road points with ``lon``, ``lat``,
        ``place_id``.

    Example:
        >>> roads = nearest_roads(-111.80, 40.68)
        >>> for r in roads:
        ...     print(f"Road at ({r['lat']:.5f}, {r['lon']:.5f})")
    """
    data = _fetch_json(f"{_ROADS_BASE}/nearestRoads", {
        "points": f"{lat},{lon}",
        "key": _get_api_key(),
    })
    results = []
    for pt in data.get("snappedPoints", []):
        loc = pt.get("location", {})
        results.append({
            "lon": loc.get("longitude"),
            "lat": loc.get("latitude"),
            "place_id": pt.get("placeId"),
        })
    return results


###########################################################################
#  Address Validation API
###########################################################################

_ADDR_VALIDATION_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"


def validate_address(address: str, region_code: str = "US") -> dict[str, Any] | None:
    """Validate and standardize an address.

    Args:
        address (str): Address to validate.
        region_code (str, optional): ISO country code. Defaults to ``"US"``.

    Returns:
        dict or None: Keys: ``formatted_address``, ``lat``, ``lon``,
        ``verdict`` (address quality), ``components`` (parsed parts),
        ``usps_data`` (USPS-standardized for US addresses).

    Example:
        >>> result = validate_address("4240 olympic way, slc ut")
        >>> print(result['formatted_address'])
    """
    try:
        data = _fetch_json(
            _ADDR_VALIDATION_URL,
            method="POST",
            body={
                "address": {"addressLines": [address], "regionCode": region_code},
            },
            headers={
                "X-Goog-Api-Key": _get_api_key(),
                "Content-Type": "application/json",
            },
        )
    except Exception:
        return None

    r = data.get("result", {})
    addr = r.get("address", {})
    geo = r.get("geocode", {})
    loc = geo.get("location", {})
    verdict = r.get("verdict", {})
    usps = r.get("uspsData", {})

    return {
        "formatted_address": addr.get("formattedAddress"),
        "lat": loc.get("latitude"),
        "lon": loc.get("longitude"),
        "verdict": {
            "input_granularity": verdict.get("inputGranularity"),
            "validation_granularity": verdict.get("validationGranularity"),
            "address_complete": verdict.get("addressComplete", False),
            "has_inferred_components": verdict.get("hasInferredComponents", False),
        },
        "components": [
            {
                "type": c.get("componentType"),
                "value": c.get("componentName", {}).get("text"),
                "confirmed": c.get("confirmationLevel") == "CONFIRMED",
            }
            for c in addr.get("addressComponents", [])
        ],
        "usps_data": {
            "standardized_address": usps.get("standardizedAddress", {}),
            "delivery_point_code": usps.get("deliveryPointCode"),
        } if usps else None,
        "place_id": geo.get("placeId"),
    }


###########################################################################
#  Time Zone API
###########################################################################

_TIMEZONE_URL = "https://maps.googleapis.com/maps/api/timezone/json"


def get_timezone(lon: float, lat: float, timestamp: int = 0) -> dict[str, Any] | None:
    """Get timezone information for a location.

    Args:
        lon (float): Longitude.
        lat (float): Latitude.
        timestamp (int, optional): Unix timestamp for DST calculation.
            Defaults to ``0`` (current time).

    Returns:
        dict or None: Keys: ``timezone_id``, ``timezone_name``,
        ``utc_offset_seconds``, ``dst_offset_seconds``.

    Example:
        >>> tz = get_timezone(-111.80, 40.68)
        >>> print(tz['timezone_id'])  # 'America/Denver'
    """
    import time as _time
    if timestamp == 0:
        timestamp = int(_time.time())
    data = _fetch_json(_TIMEZONE_URL, {
        "location": f"{lat},{lon}",
        "timestamp": str(timestamp),
        "key": _get_api_key(),
    })
    if data.get("status") != "OK":
        return None
    return {
        "timezone_id": data.get("timeZoneId"),
        "timezone_name": data.get("timeZoneName"),
        "utc_offset_seconds": data.get("rawOffset"),
        "dst_offset_seconds": data.get("dstOffset"),
    }


###########################################################################
#  Reverse Geocoding
###########################################################################


def reverse_geocode(lon: float, lat: float) -> dict[str, Any] | None:
    """Convert coordinates to an address (reverse geocoding).

    Args:
        lon (float): Longitude.
        lat (float): Latitude.

    Returns:
        dict or None: Keys: ``formatted_address``, ``place_id``,
        ``types``, ``address_components``.

    Example:
        >>> result = reverse_geocode(-111.80, 40.68)
        >>> print(result['formatted_address'])
    """
    data = _fetch_json(_GEOCODE_URL, {
        "latlng": f"{lat},{lon}",
        "key": _get_api_key(),
    })
    if data.get("status") != "OK" or not data.get("results"):
        return None
    r = data["results"][0]
    return {
        "formatted_address": r.get("formatted_address", ""),
        "place_id": r.get("place_id", ""),
        "types": r.get("types", []),
        "address_components": r.get("address_components", []),
    }


###########################################################################
#  Semantic Segmentation (SegFormer)
###########################################################################

# ADE20K class names (150 classes)
_ADE20K_CLASSES = [
    "wall", "building", "sky", "floor", "tree", "ceiling", "road", "bed",
    "windowpane", "grass", "cabinet", "sidewalk", "person", "earth",
    "door", "table", "mountain", "plant", "curtain", "chair", "car",
    "water", "painting", "sofa", "shelf", "house", "sea", "mirror",
    "rug", "field", "armchair", "seat", "fence", "desk", "rock",
    "wardrobe", "lamp", "bathtub", "railing", "cushion", "base",
    "box", "column", "signboard", "chest of drawers", "counter",
    "sand", "sink", "skyscraper", "fireplace", "refrigerator", "grandstand",
    "path", "stairs", "runway", "case", "pool table", "pillow", "screen door",
    "stairway", "river", "bridge", "bookcase", "blind", "coffee table",
    "toilet", "flower", "book", "hill", "bench", "countertop", "stove",
    "palm", "kitchen island", "computer", "swivel chair", "boat", "bar",
    "arcade machine", "hovel", "bus", "towel", "light", "truck", "tower",
    "chandelier", "awning", "streetlight", "booth", "television", "airplane",
    "dirt track", "apparel", "pole", "land", "bannister", "escalator",
    "ottoman", "bottle", "buffet", "poster", "stage", "van", "ship",
    "fountain", "conveyer belt", "canopy", "washer", "plaything",
    "swimming pool", "stool", "barrel", "basket", "waterfall", "tent",
    "bag", "minibike", "cradle", "oven", "ball", "food", "step", "tank",
    "trade name", "microwave", "pot", "animal", "bicycle", "lake",
    "dishwasher", "screen", "blanket", "sculpture", "hood", "sconce",
    "vase", "traffic light", "tray", "ashcan", "fan", "pier", "crt screen",
    "plate", "monitor", "bulletin board", "shower", "radiator", "glass",
    "clock", "flag",
]

# Broad category mapping for land cover analysis
_ADE20K_LAND_COVER = {
    "sky": ["sky"],
    "vegetation": ["tree", "grass", "plant", "flower", "palm", "field", "hill"],
    "impervious": ["road", "sidewalk", "path", "floor", "runway", "dirt track"],
    "building": ["building", "house", "wall", "skyscraper", "tower", "hovel",
                  "booth", "awning", "canopy"],
    "vehicle": ["car", "bus", "truck", "van", "boat", "ship", "airplane",
                "bicycle", "minibike"],
    "water": ["water", "sea", "river", "lake", "swimming pool", "fountain",
              "waterfall"],
    "person": ["person"],
    "terrain": ["mountain", "rock", "earth", "sand", "land"],
    "furniture": ["fence", "railing", "bench", "pole", "streetlight",
                  "signboard", "traffic light", "flag"],
}

# Cached model/processor
_segformer_model = None
_segformer_processor = None


def segment_image(
    image_bytes: bytes,
    model_variant: str = "b4",
    broad_categories: bool = False,
) -> dict[str, Any]:
    """Perform pixel-level semantic segmentation using SegFormer.

    Uses NVIDIA's SegFormer model pre-trained on ADE20K (150 classes).
    Downloads the model on first use (~64 MB for B4).

    Args:
        image_bytes (bytes): JPEG or PNG image bytes.
        model_variant (str, optional): SegFormer size — ``"b0"`` (fast,
            3.8M params), ``"b1"``, ``"b2"``, ``"b3"``, ``"b4"``
            (balanced, 64M params), or ``"b5"`` (best, 82M params).
            Defaults to ``"b4"``.
        broad_categories (bool, optional): If True, merge the 150 ADE20K
            classes into broad land cover categories (sky, vegetation,
            impervious, building, vehicle, water, terrain, etc.).
            Defaults to ``False``.

    Returns:
        dict: Keys:

        - ``class_map`` (numpy.ndarray): ``(H, W)`` array of class IDs.
        - ``class_names`` (list): Class name for each ID.
        - ``colored_image`` (bytes): JPEG with colored overlay.
        - ``legend`` (dict): ``{class_name: hex_color}`` for classes present.
        - ``summary`` (str): Markdown table of area percentages.
        - ``area_pct`` (dict): ``{class_name: float}`` area percentages.

    Example:
        >>> pano = streetview_panorama(-111.80, 40.68, fov=360)
        >>> seg = segment_image(pano)
        >>> print(seg['summary'])
        >>> with open("segmented.jpg", "wb") as f:
        ...     f.write(seg['colored_image'])
    """
    import numpy as np
    from PIL import Image
    import io as _io

    global _segformer_model, _segformer_processor

    # Lazy-load model
    if _segformer_model is None or model_variant not in str(getattr(_segformer_model, 'name_or_path', '')):
        from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation
        import torch

        # B5 uses 640x640 resolution, others use 512x512
        _res = "640-640" if model_variant == "b5" else "512-512"
        model_id = f"nvidia/segformer-{model_variant}-finetuned-ade-{_res}"
        _segformer_processor = AutoImageProcessor.from_pretrained(model_id)
        _segformer_model = AutoModelForSemanticSegmentation.from_pretrained(model_id)
        _segformer_model.eval()

        # Use GPU if available
        if torch.cuda.is_available():
            _segformer_model = _segformer_model.to("cuda")

    import torch

    # Load image
    image = Image.open(_io.BytesIO(image_bytes)).convert("RGB")
    img_w, img_h = image.size

    # Run inference
    inputs = _segformer_processor(images=image, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.to("cuda") for k, v in inputs.items()}

    with torch.no_grad():
        outputs = _segformer_model(**inputs)

    # Post-process to original image size
    class_map = _segformer_processor.post_process_semantic_segmentation(
        outputs, target_sizes=[(img_h, img_w)]
    )[0].cpu().numpy()

    # Build class name list and optional broad-category remapping
    if broad_categories:
        # Build reverse lookup: ADE20K class index -> broad category
        _reverse = {}
        for cat, ade_names in _ADE20K_LAND_COVER.items():
            for name in ade_names:
                if name in _ADE20K_CLASSES:
                    _reverse[_ADE20K_CLASSES.index(name)] = cat

        # Remap class_map
        broad_names = sorted(set(_ADE20K_LAND_COVER.keys()) | {"other"})
        broad_id_map = {name: i for i, name in enumerate(broad_names)}
        remapped = np.full_like(class_map, broad_id_map["other"])
        for ade_idx, cat in _reverse.items():
            remapped[class_map == ade_idx] = broad_id_map[cat]
        class_map = remapped
        class_names = broad_names
    else:
        class_names = _ADE20K_CLASSES

    # Calculate area percentages
    total_px = class_map.size
    unique, counts = np.unique(class_map, return_counts=True)
    area_pct = {}
    for cls_id, count in zip(unique, counts):
        if cls_id < len(class_names):
            name = class_names[cls_id]
            pct = (count / total_px) * 100
            if pct > 0.1:  # skip tiny classes
                area_pct[name] = round(pct, 1)

    # Sort by area descending
    area_pct = dict(sorted(area_pct.items(), key=lambda x: -x[1]))

    # Generate colored overlay
    # Use a fixed color palette for broad categories
    _CATEGORY_COLORS = {
        "sky": (135, 206, 235),
        "vegetation": (34, 139, 34),
        "impervious": (128, 128, 128),
        "building": (178, 102, 51),
        "vehicle": (220, 20, 60),
        "water": (30, 144, 255),
        "person": (255, 165, 0),
        "terrain": (139, 119, 101),
        "furniture": (160, 82, 165),
        "other": (80, 80, 80),
    }

    if not broad_categories:
        # Sensible colors for ADE20K 150 classes — keyed by class name
        _ADE20K_COLOR_MAP = {
            # Sky & atmosphere
            "sky": (135, 206, 250), "ceiling": (200, 200, 220),
            # Vegetation
            "tree": (34, 139, 34), "grass": (124, 252, 0), "plant": (0, 128, 0),
            "flower": (255, 105, 180), "palm": (50, 160, 50), "field": (144, 238, 144),
            "hill": (107, 142, 35),
            # Ground / impervious
            "road": (128, 128, 128), "sidewalk": (180, 180, 190),
            "floor": (190, 180, 170), "path": (160, 160, 150),
            "runway": (100, 100, 100), "dirt track": (139, 119, 101),
            "earth": (155, 118, 83), "sand": (238, 214, 175),
            "rock": (136, 138, 133), "land": (170, 140, 100),
            # Buildings & structures
            "building": (178, 102, 51), "house": (188, 120, 65),
            "wall": (190, 153, 107), "fence": (139, 90, 43),
            "skyscraper": (105, 105, 120), "tower": (120, 110, 130),
            "bridge": (150, 140, 130), "door": (120, 80, 50),
            "windowpane": (173, 216, 230), "stairs": (160, 150, 140),
            "railing": (110, 100, 90), "awning": (180, 160, 140),
            "canopy": (160, 180, 140),
            # Vehicles
            "car": (220, 20, 60), "bus": (255, 140, 0), "truck": (200, 60, 60),
            "van": (230, 100, 50), "boat": (65, 105, 225), "ship": (50, 80, 180),
            "airplane": (180, 180, 200), "bicycle": (255, 215, 0),
            "minibike": (255, 165, 0), "train": (160, 32, 240),
            # Water
            "water": (30, 144, 255), "sea": (0, 80, 160), "river": (50, 120, 200),
            "lake": (70, 130, 180), "swimming pool": (64, 164, 223),
            "fountain": (100, 180, 255), "waterfall": (80, 160, 220),
            # People & furniture
            "person": (255, 105, 0), "bench": (139, 90, 60),
            "chair": (160, 82, 45), "table": (139, 69, 19),
            "signboard": (255, 255, 100), "pole": (100, 100, 80),
            "streetlight": (255, 230, 130), "traffic light": (255, 60, 60),
            "lamp": (255, 240, 180), "flag": (200, 50, 50),
            # Terrain
            "mountain": (119, 136, 153), "countertop": (180, 170, 160),
            # Default
            "cabinet": (150, 130, 110), "bed": (180, 140, 160),
            "sofa": (160, 140, 130), "curtain": (180, 160, 180),
            "rug": (160, 120, 100), "mirror": (200, 220, 240),
        }
        _colors = np.zeros((150, 3), dtype=np.uint8)
        for i, name in enumerate(_ADE20K_CLASSES):
            _colors[i] = _ADE20K_COLOR_MAP.get(name, (
                # Fallback: deterministic color from class index
                int(80 + (i * 137) % 160),
                int(80 + (i * 89) % 160),
                int(80 + (i * 53) % 160),
            ))
    else:
        _colors = np.zeros((len(class_names), 3), dtype=np.uint8)
        for i, name in enumerate(class_names):
            _colors[i] = _CATEGORY_COLORS.get(name, (80, 80, 80))

    # Create colored mask
    color_mask = _colors[class_map]  # (H, W, 3)
    color_img = Image.fromarray(color_mask.astype(np.uint8), "RGB")

    # Blend with original image
    blended = Image.blend(image, color_img, alpha=0.45)

    # Add legend text
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except (OSError, IOError):
        try:
            font = ImageFont.load_default(size=13)
        except TypeError:
            font = ImageFont.load_default()

    # Build legend as a separate panel to the right of the image
    legend_w = 200
    row_h = 20
    n_entries = len(area_pct)
    legend_content_h = n_entries * row_h + 16

    legend_panel = Image.new("RGB", (legend_w, img_h), (20, 20, 20))
    ld = ImageDraw.Draw(legend_panel)

    ly = 8
    legend = {}
    for name, pct in area_pct.items():
        cls_id = class_names.index(name) if name in class_names else 0
        color = tuple(_colors[cls_id].tolist())
        legend[name] = "#{:02x}{:02x}{:02x}".format(*color)
        ld.rectangle([8, ly + 2, 22, ly + 14], fill=color)
        ld.text((28, ly), f"{name}: {pct:.1f}%", fill=(230, 230, 230), font=font)
        ly += row_h

    # Combine: image + legend panel side by side
    combined = Image.new("RGB", (img_w + legend_w, img_h), (20, 20, 20))
    combined.paste(blended, (0, 0))
    combined.paste(legend_panel, (img_w, 0))

    # Encode
    buf = _io.BytesIO()
    combined.save(buf, format="JPEG", quality=92)

    # Build summary table
    summary_lines = ["| Category | Area (%) |", "|---|---|"]
    for name, pct in area_pct.items():
        summary_lines.append(f"| {name} | {pct:.1f}% |")

    return {
        "class_map": class_map,
        "class_names": class_names,
        "colored_image": buf.getvalue(),
        "legend": legend,
        "summary": "\n".join(summary_lines),
        "area_pct": area_pct,
    }


def segment_streetview(
    lon: float,
    lat: float,
    heading: float = 0,
    fov: float = 360,
    pitch: float = 0,
    size: str = _SV_DEFAULT_SIZE,
    radius: int = 50,
    source: str = "default",
    model_variant: str = "b4",
    broad_categories: bool = True,
) -> dict[str, Any] | None:
    """Fetch a Street View panorama and segment it with SegFormer.

    Convenience wrapper that combines :func:`streetview_panorama` and
    :func:`segment_image`.

    Args:
        lon, lat: Coordinates.
        heading, fov, pitch, size, radius, source: See
            :func:`streetview_panorama`.
        model_variant (str, optional): SegFormer size. Defaults to ``"b4"``.
        broad_categories (bool, optional): Merge into land cover categories.
            Defaults to ``True``.

    Returns:
        dict or None: Same as :func:`segment_image` plus ``original``
        (raw panorama bytes) and ``location`` (address string).
        Returns ``None`` if no Street View coverage.

    Example:
        >>> result = segment_streetview(-111.80, 40.68, fov=360)
        >>> if result:
        ...     print(result['summary'])
        ...     with open("segmented.jpg", "wb") as f:
        ...         f.write(result['colored_image'])
    """
    pano = streetview_panorama(
        lon, lat, heading=heading, fov=fov, pitch=pitch,
        size=size, radius=radius, source=source,
    )
    if pano is None:
        return None

    result = segment_image(pano, model_variant=model_variant,
                           broad_categories=broad_categories)

    # Add location info
    addr = reverse_geocode(lon, lat)
    result["original"] = pano
    result["location"] = addr.get("formatted_address", "") if addr else f"({lat:.4f}, {lon:.4f})"

    return result

