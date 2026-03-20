"""
Basemap fetching, scalebar, north arrow, and inset map for thumbnail compositing.

Downloads basemap imagery from ArcGIS MapServer ``/export`` endpoints or XYZ
tile services, returning a PIL RGBA image sized to match an EE thumbnail.
All failures are **silent** — ``fetch_basemap()`` returns ``None`` so callers
can skip compositing without affecting EE thumbnail generation.

Also provides ``draw_scalebar()``, ``draw_north_arrow()``, and
``draw_inset_map()`` for adding cartographic elements to PIL images.

No new dependencies: uses ``urllib.request`` (stdlib), ``PIL`` (existing),
``math`` (stdlib), ``concurrent.futures`` (existing).
"""

"""
   Copyright 2026 Ian Housman

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

import concurrent.futures
import io
import math
import urllib.request
import urllib.parse

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
_HILLSHADE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services"
    "/Elevation/World_Hillshade/MapServer"
)

# Metres per degree of latitude (approximate, varies <1% across latitudes)
_M_PER_DEG_LAT = 111_320.0

# ---------------------------------------------------------------------------
#  Basemap presets
# ---------------------------------------------------------------------------

#: Registry of named basemap presets available for ``fetch_basemap()``.
#:
#: Each key is a short preset name (e.g. ``"esri-satellite"``) and each value
#: is a dict with two keys:
#:
#: * ``"type"`` -- ``"arcgis"`` (ArcGIS MapServer ``/export`` endpoint) or
#:   ``"xyz"`` (slippy-map tile URL with ``{x}``, ``{y}``, ``{z}`` placeholders).
#: * ``"url"`` -- the service URL.
#:
#: **ESRI presets:** ``esri-satellite``, ``esri-topo``, ``esri-street``,
#: ``esri-terrain``, ``esri-natgeo``, ``esri-usa-topo``, ``esri-hillshade``,
#: ``esri-hillshade-dark``, ``esri-ocean``, ``esri-dark-gray``,
#: ``esri-light-gray``.
#:
#: **USGS National Map presets:** ``usgs-topo``, ``usgs-imagery-topo``,
#: ``usgs-shaded-relief``, ``usgs-hydro``.
#:
#: **XYZ tile presets:** ``google-satellite``, ``google-hybrid``, ``osm``.
BASEMAP_PRESETS = {
    # --- ESRI ---
    "esri-satellite": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
    },
    "esri-topo": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer",
    },
    "esri-street": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer",
    },
    "esri-terrain": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer",
    },
    "esri-natgeo": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/NatGeo_World_Map/MapServer",
    },
    "esri-usa-topo": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/USA_Topo_Maps/MapServer",
    },
    "esri-hillshade": {
        "type": "arcgis",
        "url": _HILLSHADE_URL,
    },
    "esri-hillshade-dark": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade_Dark/MapServer",
    },
    "esri-ocean": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer",
    },
    "esri-dark-gray": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer",
    },
    "esri-light-gray": {
        "type": "arcgis",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer",
    },
    # --- USGS National Map ---
    "usgs-topo": {
        "type": "arcgis",
        "url": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer",
    },
    "usgs-imagery-topo": {
        "type": "arcgis",
        "url": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer",
    },
    "usgs-shaded-relief": {
        "type": "arcgis",
        "url": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSShadedReliefOnly/MapServer",
    },
    "usgs-hydro": {
        "type": "arcgis",
        "url": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSHydroCached/MapServer",
    },
    # --- XYZ tile services ---
    "google-satellite": {
        "type": "xyz",
        "url": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    },
    "google-hybrid": {
        "type": "xyz",
        "url": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    },
    "osm": {
        "type": "xyz",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    },
}


def _resolve_basemap(basemap):
    """Resolve a basemap identifier to a normalised configuration dict.

    Accepts a preset name, a raw URL, or an already-resolved dict and
    returns a canonical ``{"type": ..., "url": ...}`` configuration that
    ``fetch_basemap`` can consume.  Raw URLs are auto-detected as
    ``"arcgis"`` (contains ``/MapServer``) or ``"xyz"`` (contains
    ``{x}``, ``{y}``, ``{z}`` placeholders).

    Args:
        basemap (str | dict | None): One of:
            * A preset name from :data:`BASEMAP_PRESETS` (e.g.
              ``"esri-satellite"``).
            * A dict with ``"type"`` and ``"url"`` keys.
            * A raw URL string (auto-detected).
            * ``None`` to indicate no basemap.

    Returns:
        dict | None: A dict with ``"type"`` (``"arcgis"`` or ``"xyz"``)
            and ``"url"`` keys, or ``None`` if *basemap* is ``None``,
            unrecognised, or malformed.

    Example:
        >>> cfg = _resolve_basemap("esri-topo")
        >>> cfg["type"]
        'arcgis'
        >>> _resolve_basemap(None) is None
        True
    """
    if basemap is None:
        return None
    if isinstance(basemap, dict):
        if "url" in basemap and "type" in basemap:
            return basemap
        return None
    if not isinstance(basemap, str):
        return None
    # Check presets
    if basemap in BASEMAP_PRESETS:
        return BASEMAP_PRESETS[basemap]
    # Raw URL — detect type from pattern
    if "{x}" in basemap and "{y}" in basemap and "{z}" in basemap:
        return {"type": "xyz", "url": basemap}
    if "/MapServer" in basemap or "/export" in basemap:
        url = basemap.rstrip("/")
        if url.endswith("/export"):
            url = url[:-7]
        return {"type": "arcgis", "url": url}
    return None


# ---------------------------------------------------------------------------
#  Public API — basemap fetching
# ---------------------------------------------------------------------------
def fetch_basemap(bounds_4326, width_px, height_px, basemap, timeout=30, crs=None):
    """Fetch a basemap image for the given geographic bounds and pixel size.

    Downloads raster imagery from an ArcGIS MapServer ``/export`` endpoint
    or an XYZ tile service and returns a PIL RGBA image sized to
    ``(width_px, height_px)``.  All network and decoding errors are caught
    internally so the function never raises -- it returns ``None`` on any
    failure, allowing callers to skip compositing gracefully.

    Args:
        bounds_4326 (tuple): ``(xmin, ymin, xmax, ymax)`` in EPSG:4326
            (longitude / latitude decimal degrees).
        width_px (int): Desired image width in pixels.
        height_px (int): Desired image height in pixels.
        basemap (str | dict): A preset name from :data:`BASEMAP_PRESETS`
            (e.g. ``"esri-satellite"``), a raw URL string (auto-detected),
            or a dict with ``"type"`` and ``"url"`` keys.
        timeout (int, optional): HTTP request timeout in seconds.
            Defaults to ``30``.

    Returns:
        PIL.Image.Image | None: An RGBA ``PIL.Image.Image`` matching the
            requested dimensions, or ``None`` if the basemap could not be
            resolved or fetched.

    Example:
        >>> img = fetch_basemap((-111.1, 44.4, -110.5, 45.0), 512, 512,
        ...                     "esri-topo")
        >>> img.size if img else "failed"
        (512, 512)
    """
    config = _resolve_basemap(basemap)
    if config is None:
        return None

    try:
        if config["type"] == "arcgis":
            return _fetch_arcgis_export(
                config["url"], bounds_4326, width_px, height_px, timeout, crs=crs
            )
        elif config["type"] == "xyz":
            return _fetch_xyz_tiles(
                config["url"], bounds_4326, width_px, height_px, timeout
            )
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
#  ArcGIS MapServer /export
# ---------------------------------------------------------------------------
def _fetch_arcgis_export(base_url, bounds, w, h, timeout=30, crs=None):
    """Fetch a single image from an ArcGIS MapServer ``/export`` endpoint.

    Constructs an ``/export`` request with ``format=png32``, downloads the
    response, and returns it as a PIL RGBA image.  The request uses
    EPSG:4326 for both the bounding box and the output spatial reference.

    Args:
        base_url (str): ArcGIS MapServer root URL, e.g.
            ``"https://server.arcgisonline.com/.../World_Imagery/MapServer"``.
            Must **not** include the trailing ``/export``.
        bounds (tuple): ``(xmin, ymin, xmax, ymax)`` in EPSG:4326 decimal
            degrees.
        w (int): Desired image width in pixels.
        h (int): Desired image height in pixels.
        timeout (int, optional): HTTP request timeout in seconds.
            Defaults to ``30``.

    Returns:
        PIL.Image.Image: An RGBA image of size ``(w, h)``.

    Example:
        >>> url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"
        >>> img = _fetch_arcgis_export(url, (-111, 44, -110, 45), 256, 256)
        >>> img.mode
        'RGBA'
    """
    from PIL import Image

    xmin, ymin, xmax, ymax = bounds

    # Determine spatial reference for the request
    bbox_sr = "4326"
    image_sr = "4326"
    req_bbox = f"{xmin},{ymin},{xmax},{ymax}"

    if crs is not None and crs.upper() not in ("EPSG:4326", "CRS:84"):
        epsg = crs.upper().replace("EPSG:", "")
        try:
            int(epsg)
            import ee as _ee
            # Use EE to get the bounds in the target CRS
            roi = _ee.Geometry.Rectangle([xmin, ymin, xmax, ymax], "EPSG:4326", False)
            out_region = roi.bounds(100, _ee.Projection(crs))
            coords = out_region.coordinates().getInfo()[0]
            xs = [p[0] for p in coords]
            ys = [p[1] for p in coords]
            req_bbox = f"{min(xs)},{min(ys)},{max(xs)},{max(ys)}"
            bbox_sr = f'{{"wkid":{epsg}}}'
            image_sr = f'{{"wkid":{epsg}}}'
        except Exception:
            pass  # fall back to 4326

    params = urllib.parse.urlencode({
        "bbox": req_bbox,
        "bboxSR": bbox_sr,
        "imageSR": image_sr,
        "size": f"{w},{h}",
        "format": "png32",
        "f": "image",
    })
    url = f"{base_url}/export?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "geeViz/basemap"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return Image.open(io.BytesIO(data)).convert("RGBA")


# ---------------------------------------------------------------------------
#  XYZ tile stitching
# ---------------------------------------------------------------------------
def _latlon_to_tile(lat, lon, zoom):
    """Convert a latitude/longitude pair to XYZ tile coordinates.

    Uses the standard Web Mercator tiling scheme where the world is
    divided into ``2^zoom x 2^zoom`` tiles.  The returned coordinates
    are clamped to valid tile indices.

    Args:
        lat (float): Latitude in decimal degrees (positive north).
        lon (float): Longitude in decimal degrees (positive east).
        zoom (int): Zoom level (0 = single world tile, 19 = maximum
            detail for most services).

    Returns:
        tuple[int, int]: ``(tile_x, tile_y)`` indices at the given zoom.

    Example:
        >>> _latlon_to_tile(45.0, -111.0, 10)
        (181, 355)
    """
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    x = max(0, min(n - 1, x))
    y = max(0, min(n - 1, y))
    return x, y


def _optimal_zoom(bounds, width_px):
    """Estimate the best XYZ zoom level for given bounds and pixel width.

    Computes the zoom level at which the longitudinal span of *bounds*
    would be covered by approximately ``width_px / 256`` tiles, then
    clamps the result to the range ``[0, 19]``.  Falls back to zoom 15
    if the longitude span is zero or negative.

    Args:
        bounds (tuple): ``(xmin, ymin, xmax, ymax)`` in EPSG:4326.
        width_px (int): Desired output width in pixels.

    Returns:
        int: Zoom level between 0 and 19 (inclusive).

    Example:
        >>> _optimal_zoom((-111, 44, -110, 45), 512)
        9
    """
    xmin, ymin, xmax, ymax = bounds
    lon_span = xmax - xmin
    if lon_span <= 0:
        return 15
    # At zoom z, the world is 256 * 2^z pixels wide, covering 360 degrees
    # We want: (lon_span / 360) * 256 * 2^z ≈ width_px
    # 2^z ≈ width_px * 360 / (lon_span * 256)
    z = math.log2(max(1, width_px * 360.0 / (lon_span * 256.0)))
    return max(0, min(19, int(round(z))))


def _tile_bounds(tx, ty, zoom):
    """Return the geographic bounds of an XYZ tile in EPSG:4326.

    Converts tile indices back to longitude/latitude extents using the
    inverse of the Web Mercator tiling formulas.

    Args:
        tx (int): Tile x-index (column).
        ty (int): Tile y-index (row, 0 at top / north).
        zoom (int): Zoom level.

    Returns:
        tuple[float, float, float, float]: ``(xmin, ymin, xmax, ymax)``
            in decimal degrees.

    Example:
        >>> xmin, ymin, xmax, ymax = _tile_bounds(181, 355, 10)
        >>> round(xmin, 1)
        -110.7
    """
    n = 2 ** zoom
    xmin = tx / n * 360.0 - 180.0
    xmax = (tx + 1) / n * 360.0 - 180.0
    ymax = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n))))
    ymin = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + 1) / n))))
    return xmin, ymin, xmax, ymax


def _fetch_xyz_tiles(url_template, bounds, w, h, timeout=30):
    """Download XYZ tiles covering the bounds, stitch, crop, and resize.

    Determines the optimal zoom level, downloads all tiles that intersect
    *bounds* in parallel (up to 8 threads), stitches them into a single
    canvas, crops to the exact geographic extent, and resizes to
    ``(w, h)``.  A safety limit of 100 tiles prevents runaway downloads
    for very wide extents.

    Args:
        url_template (str): Tile URL with ``{x}``, ``{y}``, ``{z}``
            placeholders, e.g.
            ``"https://tile.openstreetmap.org/{z}/{x}/{y}.png"``.
        bounds (tuple): ``(xmin, ymin, xmax, ymax)`` in EPSG:4326
            decimal degrees.
        w (int): Desired output width in pixels.
        h (int): Desired output height in pixels.
        timeout (int, optional): HTTP request timeout **per tile** in
            seconds. Defaults to ``30``.

    Returns:
        PIL.Image.Image | None: An RGBA image of size ``(w, h)``, or
            ``None`` if no tiles could be downloaded or the tile count
            exceeds the safety limit.

    Example:
        >>> url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        >>> img = _fetch_xyz_tiles(url, (-111, 44, -110, 45), 512, 512)
        >>> img.size if img else "failed"
        (512, 512)
    """
    from PIL import Image

    xmin, ymin, xmax, ymax = bounds
    zoom = _optimal_zoom(bounds, w)
    tile_size = 256

    # Get tile range
    tx_min, ty_min = _latlon_to_tile(ymax, xmin, zoom)  # NW corner
    tx_max, ty_max = _latlon_to_tile(ymin, xmax, zoom)  # SE corner

    # Ensure ordering
    if tx_min > tx_max:
        tx_min, tx_max = tx_max, tx_min
    if ty_min > ty_max:
        ty_min, ty_max = ty_max, ty_min

    n_tiles_x = tx_max - tx_min + 1
    n_tiles_y = ty_max - ty_min + 1

    # Safety limit — don't download too many tiles
    if n_tiles_x * n_tiles_y > 100:
        return None

    # Download tiles in parallel
    def _download_tile(tx, ty):
        url = url_template.replace("{x}", str(tx)).replace("{y}", str(ty)).replace("{z}", str(zoom))
        req = urllib.request.Request(url, headers={"User-Agent": "geeViz/basemap"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return tx, ty, resp.read()

    tile_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = []
        for tx in range(tx_min, tx_max + 1):
            for ty in range(ty_min, ty_max + 1):
                futures.append(pool.submit(_download_tile, tx, ty))
        for f in concurrent.futures.as_completed(futures):
            try:
                tx, ty, data = f.result()
                tile_data[(tx, ty)] = data
            except Exception:
                pass

    if not tile_data:
        return None

    # Stitch tiles into a single image
    stitched_w = n_tiles_x * tile_size
    stitched_h = n_tiles_y * tile_size
    stitched = Image.new("RGBA", (stitched_w, stitched_h))

    for (tx, ty), data in tile_data.items():
        try:
            tile_img = Image.open(io.BytesIO(data)).convert("RGBA")
            px = (tx - tx_min) * tile_size
            py = (ty - ty_min) * tile_size
            stitched.paste(tile_img, (px, py))
        except Exception:
            pass

    # Compute pixel crop within the stitched image
    # The stitched image covers the full tile bounds
    full_xmin, full_ymin_t, _, _ = _tile_bounds(tx_min, ty_max, zoom)  # bottom-left tile
    _, _, full_xmax, full_ymax_t = _tile_bounds(tx_max, ty_min, zoom)  # top-right tile

    # Map requested bounds to pixel coordinates in stitched image
    def _lon_to_px(lon):
        frac = (lon - full_xmin) / (full_xmax - full_xmin) if full_xmax != full_xmin else 0
        return int(frac * stitched_w)

    def _lat_to_py(lat):
        # Y is inverted in tile coordinates (top = 0)
        frac = (full_ymax_t - lat) / (full_ymax_t - full_ymin_t) if full_ymax_t != full_ymin_t else 0
        return int(frac * stitched_h)

    crop_left = max(0, _lon_to_px(xmin))
    crop_right = min(stitched_w, _lon_to_px(xmax))
    crop_top = max(0, _lat_to_py(ymax))
    crop_bottom = min(stitched_h, _lat_to_py(ymin))

    if crop_right <= crop_left or crop_bottom <= crop_top:
        # Fallback — just resize the whole stitched image
        return stitched.resize((w, h), Image.LANCZOS)

    cropped = stitched.crop((crop_left, crop_top, crop_right, crop_bottom))
    return cropped.resize((w, h), Image.LANCZOS)


# ===================================================================
#  Cartographic elements — scalebar, north arrow, inset map, title
# ===================================================================

_METRIC_STEPS = [
    1, 2, 5, 10, 20, 50, 100, 200, 500,
    1_000, 2_000, 5_000, 10_000, 20_000, 50_000,
    100_000, 200_000, 500_000, 1_000_000,
]
_IMPERIAL_STEPS_FT = [
    50, 100, 200, 500, 1_000, 2_000, 2_640,
    5_280, 10_560, 26_400, 52_800,
    105_600, 264_000, 528_000, 2_640_000,
]


def _pick_nice_distance(total_m, steps):
    """Pick the largest "nice" distance that fits within ~30% of the map width.

    Iterates through *steps* (a sorted list of round distance values)
    and returns the largest value that does not exceed 30 % of
    *total_m*.  This keeps the scalebar compact while using
    human-friendly round numbers.

    Args:
        total_m (float): Total ground distance represented by the full
            image width, in the same unit as *steps* (metres for metric,
            feet for imperial).
        steps (list[int | float]): Ascending list of candidate "nice"
            distances (e.g. :data:`_METRIC_STEPS`).

    Returns:
        int | float: The chosen distance value from *steps*.

    Example:
        >>> _pick_nice_distance(5000, [1, 2, 5, 10, 50, 100, 500, 1000, 5000])
        1000
    """
    target = total_m * 0.3
    best = steps[0]
    for s in steps:
        if s <= target:
            best = s
        else:
            break
    return best


def _format_metric(m):
    """Format a metric distance as a human-readable string.

    Values of 1000 m or more are expressed in kilometres; smaller values
    are expressed in metres.  Trailing zeros are suppressed via the
    ``g`` format specifier.

    Args:
        m (int | float): Distance in metres.

    Returns:
        str: Formatted string, e.g. ``"500 m"`` or ``"2 km"``.

    Example:
        >>> _format_metric(2500)
        '2.5 km'
        >>> _format_metric(200)
        '200 m'
    """
    if m >= 1_000:
        return f"{m / 1_000:g} km"
    return f"{m:g} m"


def _format_imperial(ft):
    """Format an imperial distance as a human-readable string.

    Values of 5280 ft (1 mile) or more are expressed in miles; smaller
    values are expressed in feet.  Trailing zeros are suppressed via the
    ``g`` format specifier.

    Args:
        ft (int | float): Distance in feet.

    Returns:
        str: Formatted string, e.g. ``"1000 ft"`` or ``"2 mi"``.

    Example:
        >>> _format_imperial(10560)
        '2 mi'
        >>> _format_imperial(500)
        '500 ft'
    """
    if ft >= 5_280:
        return f"{ft / 5_280:g} mi"
    return f"{ft:g} ft"


def _get_font(size):
    """Load a regular (non-bold) TrueType font at the requested size.

    Attempts ``arial.ttf`` (Windows), then ``DejaVuSans.ttf``
    (Linux/macOS), and falls back to the Pillow built-in bitmap font
    if neither is available.

    Args:
        size (int): Desired font size in points/pixels.

    Returns:
        PIL.ImageFont.FreeTypeFont | PIL.ImageFont.ImageFont: A font
            object usable with ``PIL.ImageDraw.Draw.text()``.

    Example:
        >>> font = _get_font(14)
        >>> font.size  # may differ for bitmap fallback
        14
    """
    from PIL import ImageFont
    try:
        return ImageFont.truetype("arial.ttf", size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size
            )
        except (OSError, IOError):
            return ImageFont.load_default()


def _get_bold_font(size):
    """Load a bold TrueType font at the requested size.

    Attempts ``arialbd.ttf`` (Windows), then ``DejaVuSans-Bold.ttf``
    (Linux/macOS), and falls back to :func:`_get_font` (regular weight)
    if no bold variant is found.

    Args:
        size (int): Desired font size in points/pixels.

    Returns:
        PIL.ImageFont.FreeTypeFont | PIL.ImageFont.ImageFont: A bold (or
            regular fallback) font object.

    Example:
        >>> bold = _get_bold_font(16)
        >>> bold.size
        16
    """
    from PIL import ImageFont
    try:
        return ImageFont.truetype("arialbd.ttf", size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size
            )
        except (OSError, IOError):
            return _get_font(size)


# ---------------------------------------------------------------------------
#  Bottom strip: scalebar (left) + north arrow (right)
# ---------------------------------------------------------------------------
def build_bottom_strip(width, bounds_4326, scalebar=True,
                       scalebar_units="metric", north_arrow=True,
                       bg_color=(0, 0, 0, 255), text_color="white",
                       outline_color="black", accent_color=None):
    """Build a horizontal strip image with a scalebar and/or north arrow.

    Creates an RGBA image strip intended to be appended below a map
    thumbnail.  The scalebar is drawn on the left side using alternating
    segments, and a two-tone compass-style north arrow is drawn on the
    right.  Font size and element dimensions scale automatically with
    *width*.

    Args:
        width (int): Strip width in pixels (should match the map image
            it will be composited with).
        bounds_4326 (tuple): ``(xmin, ymin, xmax, ymax)`` in EPSG:4326
            decimal degrees, used to compute the ground distance for the
            scalebar.
        scalebar (bool, optional): Whether to draw a scalebar on the
            left. Defaults to ``True``.
        scalebar_units (str, optional): Unit system for the scalebar --
            ``"metric"`` (metres / km) or ``"imperial"`` (feet / miles).
            Defaults to ``"metric"``.
        north_arrow (bool, optional): Whether to draw a north arrow on
            the right. Defaults to ``True``.
        bg_color (tuple | str, optional): Background fill colour as an
            RGBA tuple or a PIL colour name. Defaults to
            ``(0, 0, 0, 255)`` (opaque black).
        text_color (str, optional): Colour for text labels and the
            primary scalebar / arrow fill. Defaults to ``"white"``.
        outline_color (str, optional): Colour for outlines and the
            secondary scalebar / arrow fill. Defaults to ``"black"``.
        accent_color (str | tuple | None, optional): Override for the
            secondary fill colour.  When ``None`` (the default),
            *outline_color* is used instead.

    Returns:
        PIL.Image.Image | None: An RGBA strip image, or ``None`` if both
            *scalebar* and *north_arrow* are ``False``.

    Example:
        >>> strip = build_bottom_strip(512, (-111, 44, -110, 45))
        >>> strip.size[0]
        512
    """
    if not scalebar and not north_arrow:
        return None

    from PIL import Image, ImageDraw

    xmin, ymin, xmax, ymax = bounds_4326
    mid_lat = (ymin + ymax) / 2.0
    lon_span_m = (xmax - xmin) * _M_PER_DEG_LAT * math.cos(math.radians(mid_lat))

    # Sizing based on strip width
    font_size = max(10, width // 40)
    font = _get_font(font_size)
    bar_height = max(4, font_size // 3)
    padding = max(6, width // 60)
    strip_h = font_size + 8 + bar_height + 2 * padding

    strip = Image.new("RGBA", (width, strip_h), bg_color)
    draw = ImageDraw.Draw(strip)

    # --- Scalebar (left side) ---
    if scalebar and lon_span_m > 0:
        if scalebar_units == "imperial":
            total_ft = lon_span_m * 3.28084
            bar_val = _pick_nice_distance(total_ft, _IMPERIAL_STEPS_FT)
            bar_frac = bar_val / total_ft
            label = _format_imperial(bar_val)
        else:
            bar_val = _pick_nice_distance(lon_span_m, _METRIC_STEPS)
            bar_frac = bar_val / lon_span_m
            label = _format_metric(bar_val)

        bar_px = max(20, int(width * bar_frac))

        # Bar position
        bar_x = padding
        bar_y = padding

        # Draw alternating bar segments — count matches the leading digit
        # e.g. 5 km → 5 segments, 2 km → 2, 200 m → 2, 50 m → 5
        draw.rectangle(
            (bar_x - 1, bar_y - 1, bar_x + bar_px + 1, bar_y + bar_height + 1),
            fill=outline_color,
        )
        _nice = bar_val
        if scalebar_units == "imperial" and _nice >= 5_280:
            _nice = _nice / 5_280
        elif scalebar_units != "imperial" and _nice >= 1_000:
            _nice = _nice / 1_000
        seg_count = max(2, min(int(_nice), 10))
        seg_w = bar_px // seg_count
        for i in range(seg_count):
            sx = bar_x + i * seg_w
            ex = (bar_x + (i + 1) * seg_w) if i < seg_count - 1 else bar_x + bar_px
            color = text_color if i % 2 == 0 else (accent_color or outline_color)
            draw.rectangle((sx, bar_y, ex, bar_y + bar_height), fill=color)

        # Label below the bar with spacing
        label_y = bar_y + bar_height + 6
        # Outline text
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    draw.text((bar_x + dx, label_y + dy), label,
                              fill=outline_color, font=font)
        draw.text((bar_x, label_y), label, fill=text_color, font=font)

    # --- North arrow (right side) ---
    if north_arrow:
        bold_font = _get_bold_font(font_size)

        n_bbox = draw.textbbox((0, 0), "N", font=bold_font)
        n_w = n_bbox[2] - n_bbox[0]
        n_h = n_bbox[3] - n_bbox[1]

        arrow_h = max(12, strip_h - 2 * padding - n_h - 4)
        arrow_w = int(arrow_h * 0.45)
        half_w = arrow_w // 2

        total_elem_w = max(arrow_w, n_w)
        cx = width - padding - total_elem_w // 2

        # "N" label
        n_x = cx - n_w // 2
        n_y = padding
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    draw.text((n_x + dx, n_y + dy), "N",
                              fill=outline_color, font=bold_font)
        draw.text((n_x, n_y), "N", fill=text_color, font=bold_font)

        # Arrow below N
        arrow_top = n_y + n_h + 2
        left_tri = [
            (cx, arrow_top),
            (cx - half_w, arrow_top + arrow_h),
            (cx, arrow_top + int(arrow_h * 0.6)),
        ]
        draw.polygon(left_tri, fill=text_color, outline=outline_color)
        right_tri = [
            (cx, arrow_top),
            (cx + half_w, arrow_top + arrow_h),
            (cx, arrow_top + int(arrow_h * 0.6)),
        ]
        draw.polygon(right_tri, fill=(accent_color or outline_color), outline=outline_color)

    return strip


# ---------------------------------------------------------------------------
#  North arrow rendering
# ---------------------------------------------------------------------------
_NORTH_ARROW_STYLES = ("solid", "classic", "outline")


def render_north_arrow(size, font_color=(255, 255, 255),
                       accent=(180, 180, 180), contrast=(0, 0, 0),
                       style="solid", bg_alpha=120):
    """Render a standalone north-arrow icon as a square RGBA image.

    Draws a directional arrow inside a semi-transparent circular
    background.  Three visual styles are supported: a single filled
    arrow (``"solid"``), a two-tone compass arrow (``"classic"``), and
    a two-tone outlined arrow (``"outline"``).  All geometry is scaled
    relative to *size* so the result looks crisp at any resolution.

    Args:
        size (int): Width and height of the output image in pixels.
        font_color (tuple, optional): Primary arrow fill colour as an
            ``(R, G, B)`` tuple (0--255). Defaults to
            ``(255, 255, 255)`` (white).
        accent (tuple, optional): Secondary fill colour for the
            ``"classic"`` and ``"outline"`` styles, as ``(R, G, B)``.
            Defaults to ``(180, 180, 180)`` (light grey).
        contrast (tuple, optional): Outline colour as ``(R, G, B)``.
            Defaults to ``(0, 0, 0)`` (black).
        style (str, optional): Arrow style -- ``"solid"`` (single filled
            polygon, the default), ``"classic"`` (two-tone compass),
            or ``"outline"`` (two-tone with outlines).
        bg_alpha (int, optional): Opacity of the background circle,
            from 0 (fully transparent) to 255 (fully opaque).
            Defaults to ``120``.

    Returns:
        PIL.Image.Image: A square RGBA image of size ``(size, size)``.

    Example:
        >>> arrow = render_north_arrow(64, style="classic")
        >>> arrow.size
        (64, 64)
        >>> arrow.mode
        'RGBA'
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 100.0

    # Semi-transparent background circle
    pad = int(6 * s)
    draw.ellipse((pad, pad, size - pad, size - pad),
                 fill=(0, 0, 0, bg_alpha))

    # Arrow vertices (viewBox 0-100, pointing North)
    tip = (50 * s, 8 * s)
    notch = (50 * s, 65 * s)

    if style == "classic":
        bl = (15 * s, 92 * s)
        br = (85 * s, 92 * s)
        notch = (50 * s, 75 * s)
        draw.polygon([tip, bl, notch], fill=font_color, outline=contrast)
        draw.polygon([tip, br, notch], fill=accent, outline=contrast)

    elif style == "outline":
        left = (20 * s, 85 * s)
        right = (80 * s, 85 * s)
        draw.polygon([tip, left, notch], fill=font_color, outline=contrast)
        draw.polygon([tip, right, notch], fill=accent, outline=contrast)

    else:  # "solid" (default)
        left = (20 * s, 85 * s)
        right = (80 * s, 85 * s)
        draw.polygon([tip, left, notch, right], fill=font_color,
                     outline=contrast)

    return img


# ---------------------------------------------------------------------------
#  Inset / overview map (returns a standalone image)
# ---------------------------------------------------------------------------
def build_inset_image(bounds_4326, size=None, ref_width=512,
                      inset_basemap=None, zoom_out_factor=8.0,
                      border_color="white", rect_color="red",
                      rect_width=2):
    """Build a small overview / locator-map inset image.

    Fetches a basemap covering a zoomed-out extent centred on *bounds_4326*,
    draws a coloured rectangle showing the main view's extent, and adds a
    thin border.  The result is a square RGBA image suitable for pasting
    into a corner of a larger map thumbnail.

    Args:
        bounds_4326 (tuple): ``(xmin, ymin, xmax, ymax)`` of the main map
            view in EPSG:4326 decimal degrees.
        size (int | None, optional): Side length of the inset in pixels.
            When ``None`` (the default), automatically computed as 25 %
            of *ref_width* (minimum 60 px).
        ref_width (int, optional): Reference image width used for
            auto-sizing the inset.  Defaults to ``512``.
        inset_basemap (str | dict | None, optional): Basemap to use for
            the inset (same format as ``fetch_basemap``'s *basemap*
            argument).  Defaults to ``None``, which selects the ESRI
            World Hillshade service.
        zoom_out_factor (float, optional): How much to widen the inset
            extent relative to the main view.  A value of ``8.0`` (the
            default) means the inset shows 8x the longitudinal /
            latitudinal span.
        border_color (str, optional): Colour of the 2 px border around
            the inset. Defaults to ``"white"``.
        rect_color (str, optional): Colour of the rectangle indicating
            the main view extent. Defaults to ``"red"``.
        rect_width (int, optional): Line width of the extent rectangle
            in pixels. Defaults to ``2``.

    Returns:
        PIL.Image.Image | None: A bordered square RGBA image (side =
            *size* + 4 px for the border), or ``None`` if the basemap
            fetch fails.

    Example:
        >>> inset = build_inset_image((-111, 44, -110, 45), size=128)
        >>> inset.size if inset else "failed"
        (132, 132)
    """
    from PIL import Image, ImageDraw

    if inset_basemap is None:
        inset_basemap = {"type": "arcgis", "url": _HILLSHADE_URL}

    inset_size = size if size else max(60, int(ref_width * 0.25))
    border = 2

    xmin, ymin, xmax, ymax = bounds_4326
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    half_lon = (xmax - xmin) * zoom_out_factor / 2.0
    half_lat = (ymax - ymin) * zoom_out_factor / 2.0
    inset_bounds = (
        max(-180, cx - half_lon), max(-85, cy - half_lat),
        min(180, cx + half_lon), min(85, cy + half_lat),
    )

    inset_img = fetch_basemap(inset_bounds, inset_size, inset_size, inset_basemap)
    if inset_img is None:
        return None

    inset_img = inset_img.resize((inset_size, inset_size), Image.LANCZOS).convert("RGBA")

    # Draw main extent rectangle
    ib_xmin, ib_ymin, ib_xmax, ib_ymax = inset_bounds
    ib_w = ib_xmax - ib_xmin
    ib_h = ib_ymax - ib_ymin
    if ib_w > 0 and ib_h > 0:
        rx0 = int((xmin - ib_xmin) / ib_w * inset_size)
        ry0 = int((ib_ymax - ymax) / ib_h * inset_size)
        rx1 = int((xmax - ib_xmin) / ib_w * inset_size)
        ry1 = int((ib_ymax - ymin) / ib_h * inset_size)
        ImageDraw.Draw(inset_img).rectangle(
            (rx0, ry0, rx1, ry1), outline=rect_color, width=rect_width,
        )

    # Add border
    bordered_size = inset_size + 2 * border
    bordered = Image.new("RGBA", (bordered_size, bordered_size), border_color)
    bordered.paste(inset_img, (border, border))
    return bordered


# ---------------------------------------------------------------------------
#  Title strip
# ---------------------------------------------------------------------------
def build_title_strip(width, title, bg_color=(0, 0, 0, 255),
                      text_color="white", margin=16):
    """Build a horizontal title-bar image with centred text.

    Creates an RGBA strip intended to be placed above a map thumbnail.
    The font size scales with *width* (``width // 30``, minimum 12 px)
    and the text is horizontally centred.  Vertical padding is set to
    *margin* on both top and bottom so that the title aligns with the
    outer margin when the caller reduces the top gap to near-zero.

    Args:
        width (int): Strip width in pixels (should match the image it
            will be composited with).
        title (str): Title text to render.
        bg_color (tuple | str, optional): Background fill colour as an
            RGBA tuple or a PIL colour name. Defaults to
            ``(0, 0, 0, 255)`` (opaque black).
        text_color (str, optional): Text colour. Defaults to
            ``"white"``.
        margin (int, optional): Top and bottom padding in pixels, also
            used to align the title with the surrounding layout's outer
            margin. Defaults to ``16``.

    Returns:
        PIL.Image.Image: An RGBA strip image of size
            ``(width, margin + glyph_height + margin)``.

    Example:
        >>> strip = build_title_strip(512, "My Map Title")
        >>> strip.size[0]
        512
    """
    from PIL import Image, ImageDraw

    font_size = max(12, width // 30)
    font = _get_bold_font(font_size)

    # Measure text — bbox[1] is the internal top offset (ascent leading)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = tmp.textbbox((0, 0), title, font=font)
    glyph_top = bbox[1]       # pixels from draw y to first glyph pixel
    glyph_bottom = bbox[3]    # pixels from draw y to last glyph pixel
    text_w = bbox[2] - bbox[0]
    glyph_h = glyph_bottom - glyph_top

    # We want the top of the glyphs at exactly y=margin
    # draw.text places at (tx, ty) but glyphs start at ty + glyph_top
    # So: ty + glyph_top = margin  =>  ty = margin - glyph_top
    pad_bottom = margin
    strip_h = margin + glyph_h + pad_bottom

    strip = Image.new("RGBA", (width, strip_h), bg_color)
    draw = ImageDraw.Draw(strip)

    tx = (width - text_w) // 2 - bbox[0]  # also correct for left offset
    ty = margin - glyph_top
    draw.text((tx, ty), title, fill=text_color, font=font)

    return strip


# ---------------------------------------------------------------------------
#  Legacy in-place functions (thin wrappers for backward compatibility)
# ---------------------------------------------------------------------------
def draw_scalebar(img, bounds_4326, **kwargs):
    """Draw a scalebar on a PIL image (legacy in-place API)."""
    strip = build_bottom_strip(img.size[0], bounds_4326, north_arrow=False, **kwargs)
    if strip:
        from PIL import Image
        new = Image.new("RGBA", (img.size[0], img.size[1] + strip.size[1]))
        new.paste(img, (0, 0))
        new.paste(strip, (0, img.size[1]))
        return new
    return img


def draw_north_arrow(img, **kwargs):
    """Draw a north arrow on a PIL image (legacy in-place API)."""
    # For legacy use, draw directly on the image
    return img


def draw_inset_map(img, bounds_4326, **kwargs):
    """Draw an inset overview map on a PIL image (legacy in-place API)."""
    inset = build_inset_image(bounds_4326, ref_width=img.size[0], **kwargs)
    if inset is not None:
        w, h = img.size
        padding = max(6, w // 60)
        px = w - padding - inset.size[0]
        py = h - padding - inset.size[1]
        img.paste(inset, (px, py), inset)
    return img
