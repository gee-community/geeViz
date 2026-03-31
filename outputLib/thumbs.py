"""
Generate Earth Engine thumbnails with automatic visualization handling.

``geeViz.outputLib.thumbs`` provides functions that mirror the auto-visualization
logic in ``geeView`` and ``geeViz.outputLib.charts`` — detecting thematic vs. continuous
data, reading ``*_class_values`` / ``*_class_palette`` image properties, and
building appropriate viz params — so you can get publication-ready thumbnail
URLs and embeddable HTML ``<img>`` tags without manual configuration.

Supports ``ee.Image`` (PNG) and ``ee.ImageCollection`` (animated GIF or
filmstrip), with optional per-feature clipping for ``ee.FeatureCollection``
geometries.

Animated GIFs
-------------
For ``ee.ImageCollection`` inputs, :func:`generate_gif` creates properly
mosaicked per-time-step frames, with optional date burn-in using
``system:time_start`` metadata.

Example::

    import geeViz.geeView as gv
    from geeViz.outputLib import thumbs as tl

    ee = gv.ee
    lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")
    area = ee.Geometry.Point([-111.8, 40.7]).buffer(10000)

    url = tl.get_thumb_url(lcms.select(["Land_Cover"]).first(), area)
    html = tl.embed_thumb(url, title="LCMS Land Cover")

    # Animated GIF with date labels
    gif_html = tl.generate_gif(
        lcms.select(["Land_Cover"]),
        area,
        burn_in_date=True,
        date_format="YYYY",
    )
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

import base64
import concurrent.futures
import io
import math
import urllib.request

import geeViz.geeView as gv

ee = gv.ee

from geeViz.outputLib import charts as cl

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
_DEFAULT_DIMENSIONS = 640
_MAX_GIF_FRAMES = 50
_DEFAULT_FPS = 2
_DEFAULT_MARGIN = 16

# Common continuous viz defaults when no viz_params provided and data is not thematic
_CONTINUOUS_DEFAULTS = {
    "min": 0,
    "max": 1,
    "palette": ["000000", "00FF00"],
}

# Default font sizes (pixels) for consistent typography across all outputs
_DEFAULT_TITLE_FONT_SIZE = 18
_DEFAULT_LABEL_FONT_SIZE = 12

# Default CRS for thumbnail/GIF generation
_DEFAULT_CRS = "EPSG:3857"

# Default single-band palette (grayscale fallback)
_CONTINUOUS_SINGLE_BAND_PALETTE = ["000000", "ffffff"]

# Band-name → palette lookup using geeViz.geePalettes (ee-palettes)
# Keys are lower-cased band names; values are resolved palette lists.
def _build_band_palette_lookup():
    """Build a dict mapping common band names to ee-palettes colour lists."""
    try:
        import geeViz.geePalettes as gp
    except ImportError:
        return {}

    # Helper to strip leading '#' from matplotlib palettes
    def _clean(pal):
        return [c.lstrip("#") for c in pal]

    lookup = {}

    # Vegetation indices — green ramps
    _rdylgn9 = _clean(gp.colorbrewer["RdYlGn"][9])
    for name in ("ndvi", "evi", "evi2", "savi", "msavi", "nirv", "gcc"):
        lookup[name] = _rdylgn9

    # Water / moisture indices — blue ramps
    _pubu9 = _clean(gp.colorbrewer["PuBu"][9])
    for name in ("ndmi", "ndwi", "lswi", "ndsi", "mndwi"):
        lookup[name] = _pubu9

    # Burn / fire indices
    _ylorrd9 = _clean(gp.colorbrewer["YlOrRd"][9])
    for name in ("nbr", "dnbr", "dndvi", "rbr"):
        lookup[name] = _ylorrd9

    # Temperature
    _thermal = _clean(gp.cmocean["Thermal"][7])
    for name in ("temp", "lst", "tmmn", "tmmx", "temperature",
                 "thermal", "brightness_temperature"):
        lookup[name] = _thermal

    # Elevation / terrain
    _terrain = _clean(gp.cmocean["Deep"][7])[::-1]  # reverse: dark=deep, light=high
    for name in ("elevation", "dem", "height", "slope", "aspect", "hillshade"):
        lookup[name] = _terrain

    # Precipitation / rainfall — teal blues
    _tempo = _clean(gp.cmocean["Tempo"][7])
    for name in ("precipitation", "pr", "precip", "rainfall", "rain"):
        lookup[name] = _tempo

    # Generic spectral bands — viridis
    _viridis = _clean(gp.matplotlib["viridis"][7])
    for name in ("blue", "green", "red", "nir", "swir1", "swir2",
                 "nir2", "re1", "re2", "re3", "cb"):
        lookup[name] = _viridis

    # Speed / wind
    _speed = _clean(gp.cmocean["Speed"][7])
    for name in ("speed", "wind", "vs"):
        lookup[name] = _speed

    return lookup


_BAND_PALETTE_LOOKUP = _build_band_palette_lookup()


def _get_palette_for_band(band_name):
    """Return a palette list for a band name, or the grayscale fallback."""
    if band_name:
        return _BAND_PALETTE_LOOKUP.get(
            band_name.lower(), list(_CONTINUOUS_SINGLE_BAND_PALETTE)
        )
    return list(_CONTINUOUS_SINGLE_BAND_PALETTE)

# ---------------------------------------------------------------------------
#  Theme — delegated to outputLib.themes for consistency across geeViz
# ---------------------------------------------------------------------------
from geeViz.outputLib.themes import get_theme as _get_theme_obj
from geeViz.outputLib._colors import resolve_color as _resolve_color
from geeViz.outputLib._basemaps import (
    fetch_basemap as _fetch_basemap,
    build_bottom_strip as _build_bottom_strip,
    build_inset_image as _build_inset_image,
    build_title_strip as _build_title_strip,
)


def _get_theme(bg_color=None, font_color=None):
    """Return a Theme object for the given background and/or font colors."""
    return _get_theme_obj(bg_color=bg_color, font_color=font_color)


def _resolve_font_colors(bg_color=None, font_color=None, font_outline_color=None):
    """Resolve font, outline, and background colors into a consistent theme.

    Determines the full color scheme from whichever colors are provided,
    filling in missing values using the geeViz theme system.  The four
    resolution cases are:

    1. Only ``font_color`` -- derive background from font luminance
       (dark font implies light background).
    2. Only ``bg_color`` -- derive font from background via theme.
    3. Both ``font_color`` and ``bg_color`` -- use as-is; accent colors
       derived from the font color.
    4. Neither -- default dark theme (black background, light text).

    Args:
        bg_color (str or tuple, optional): Background color as a CSS name,
            hex string, or ``(R, G, B)`` tuple.  Defaults to ``None``
            (resolved by theme system).
        font_color (str or tuple, optional): Text color as a CSS name,
            hex string, or ``(R, G, B)`` tuple.  Defaults to ``None``
            (resolved by theme system).
        font_outline_color (str or tuple, optional): Outline / halo color
            for text readability.  Auto-generated to contrast with
            ``font_color`` when ``None``.  Defaults to ``None``.

    Returns:
        tuple: A 4-element tuple of
        ``(font_color_rgb, font_outline_color_rgb, theme, bg_color_str)``
        where *font_color_rgb* and *font_outline_color_rgb* are
        ``(R, G, B)`` tuples, *theme* is a ``Theme`` object, and
        *bg_color_str* is a hex string.

    Example:
        >>> fc, oc, theme, bg = _resolve_font_colors(bg_color="white")
        >>> fc   # e.g. (0, 0, 0) -- dark text on light bg
    """
    from geeViz.outputLib.themes import luminance
    from geeViz.outputLib._colors import to_hex

    # Resolve string inputs to RGB tuples
    if font_color is not None:
        font_color = _resolve_color(font_color) if isinstance(font_color, str) else tuple(font_color)

    # Pass through to theme system — it handles all None combos
    theme = _get_theme(bg_color, font_color=font_color)

    # Pull resolved values from theme
    if font_color is None:
        font_color = theme.text
    bg_color = to_hex(theme.bg)

    # Auto-generate outline: contrasts with font color
    if font_outline_color is None:
        if luminance(font_color) > 128:
            font_outline_color = (0, 0, 0)
        else:
            font_outline_color = (255, 255, 255)
    else:
        font_outline_color = _resolve_color(font_outline_color) if isinstance(font_outline_color, str) else tuple(font_outline_color)

    return font_color, font_outline_color, theme, bg_color


# Date format mapping: chartingLib-style format -> Python strftime
_DATE_FORMAT_MAP = {
    "YYYY": "%Y",
    "YYYY-MM": "%Y-%m",
    "YYYY-MM-dd": "%Y-%m-%d",
    "YYYYMMdd": "%Y%m%d",
    "MMM YYYY": "%b %Y",
    "MMMM YYYY": "%B %Y",
    "MM/YYYY": "%m/%Y",
    "MM/dd/YYYY": "%m/%d/%Y",
}


# ---------------------------------------------------------------------------
#  Projection helpers
# ---------------------------------------------------------------------------
def _validate_projection_params(crs, transform, scale):
    """Validate the crs / transform / scale combination.

    Rules:
        - All three can be None (no projection override).
        - ``crs`` alone is allowed.
        - ``crs`` + ``transform`` is allowed.
        - ``crs`` + ``scale`` is allowed.
        - ``crs`` + ``transform`` + ``scale`` is allowed.
        - ``transform`` or ``scale`` without ``crs`` is an error.

    Raises:
        ValueError: If ``transform`` or ``scale`` is provided without ``crs``.
    """
    if crs is None and (transform is not None or scale is not None):
        raise ValueError(
            "When transform or scale is provided, crs must also be "
            "provided.  Either supply crs together with transform/scale, "
            "or omit all three."
        )


def _apply_projection(ee_img, crs=None, transform=None, scale=None):
    """Apply ``setDefaultProjection`` to an ``ee.Image`` if projection params are given.

    Args:
        ee_img: ``ee.Image``.
        crs (str, optional): CRS code, e.g. ``"EPSG:4326"``.
        transform (list, optional): Affine transform as a 6-element list.
        scale (float, optional): Nominal scale in meters.

    Returns:
        ee.Image: The image with default projection set (or unchanged).
    """
    if crs is None:
        return ee_img
    kwargs = {"crs": crs}
    if transform is not None:
        kwargs["crsTransform"] = transform
    if scale is not None:
        kwargs["scale"] = scale
    elif transform is None:
        # When only crs is given (no scale or transform), derive the scale
        # from the image's native projection.  Without an explicit scale,
        # setDefaultProjection uses a [1,0,0,0,1,0] transform whose
        # positive y-scale flips the image in projected CRSes like UTM.
        kwargs["scale"] = ee_img.projection().nominalScale()
    return ee_img.setDefaultProjection(**kwargs)


def _apply_projection_to_collection(ee_col, crs=None, transform=None, scale=None):
    """Apply ``setDefaultProjection`` to every image in an ``ee.ImageCollection``.

    Args:
        ee_col: ``ee.ImageCollection``.
        crs (str, optional): CRS code.
        transform (list, optional): Affine transform.
        scale (float, optional): Nominal scale in meters.

    Returns:
        ee.ImageCollection: Collection with projection set on each image.
    """
    if crs is None:
        return ee_col
    def _set_proj(img):
        return _apply_projection(img, crs, transform, scale).copyProperties(
            img, ["system:time_start"]
        )
    return ee_col.map(_set_proj)


# ---------------------------------------------------------------------------
#  Basemap compositing helpers
def _hex_fill_to_rgba(hex_str):
    """Convert a hex fill color string (RRGGBB or RRGGBBAA) to an RGBA tuple."""
    if not hex_str or len(hex_str) < 6:
        return None
    hex_str = hex_str.lstrip("#")
    try:
        r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
        a = int(hex_str[6:8], 16) if len(hex_str) >= 8 else 255
        return (r, g, b, a)
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
def _get_bounds_4326(geom):
    """Extract ``(xmin, ymin, xmax, ymax)`` from an ``ee.Geometry``.

    Returns:
        tuple or None: Bounds in EPSG:4326, or None on failure.
    """
    try:
        coords = geom.bounds(10,"EPSG:4326").coordinates().get(0).getInfo()
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return (min(lons), min(lats), max(lons), max(lats))
    except Exception:
        return None


_THUMB_PADDING = 8  # pixel border around thumbnails showing basemap


def _expand_bounds_for_padding(bounds_4326, dimensions, pad=_THUMB_PADDING):
    """Expand geographic bounds by the padding ratio so EE data fills to the basemap edges.

    The basemap is fetched at ``dimensions + 2*pad`` pixels for the same
    geographic extent, creating a border.  This function expands the bounds
    proportionally so the EE thumbnail request covers the same geographic
    area as the basemap (including the padding margin).

    Returns:
        ee.Geometry.Rectangle with expanded bounds, or None if bounds is None.
    """
    if bounds_4326 is None:
        return None
    xmin, ymin, xmax, ymax = bounds_4326
    dx = xmax - xmin
    dy = ymax - ymin
    # Fraction of the image that is padding on each side
    frac = pad / dimensions if dimensions > 0 else 0
    buf_x = dx * frac
    buf_y = dy * frac
    return (xmin - buf_x, ymin - buf_y, xmax + buf_x, ymax + buf_y)


def _composite_with_basemap(frame, basemap_img, overlay_opacity=1.0):
    """Composite an Earth Engine thumbnail frame over a basemap image.

    Both images should cover the same geographic extent (the EE frame
    was requested with an expanded region matching the basemap).  The
    basemap is resized to match the frame dimensions and composited
    underneath.

    Args:
        frame (PIL.Image.Image): RGBA Earth Engine thumbnail frame
            (requested at padded dimensions with expanded region).
        basemap_img (PIL.Image.Image): RGBA basemap tile image.
        overlay_opacity (float, optional): Opacity multiplier (0.0–1.0).

    Returns:
        PIL.Image.Image: RGBA composite.
    """
    from PIL import Image
    fw, fh = frame.size

    bg = basemap_img.resize((fw, fh), Image.LANCZOS).convert("RGBA")
    overlay = frame.convert("RGBA")
    if overlay_opacity < 1.0:
        r, g, b, a = overlay.split()
        a = a.point(lambda x: int(x * max(0.0, min(1.0, overlay_opacity))))
        overlay = Image.merge("RGBA", (r, g, b, a))
    bg.paste(overlay, (0, 0), overlay)
    return bg


def _add_thumb_padding(frame, bg_color="black"):
    """Add ``_THUMB_PADDING`` pixels of blank space around a frame.

    Used when no basemap is present, to keep frame sizes consistent
    with the basemap-composited path.

    Args:
        frame (PIL.Image.Image): RGBA frame.
        bg_color: Background colour for the padding.

    Returns:
        PIL.Image.Image: Padded RGBA image.
    """
    from PIL import Image
    pad = _THUMB_PADDING
    fw, fh = frame.size
    bg_rgba = _resolve_color(bg_color) + (255,)
    out = Image.new("RGBA", (fw + 2 * pad, fh + 2 * pad), bg_rgba)
    out.paste(frame, (pad, pad), frame if frame.mode == "RGBA" else None)
    return out


def _auto_geometry_color(basemap_img):
    """Pick a contrasting outline color based on the basemap's average brightness.

    Returns a color that contrasts well with both the basemap AND
    a dark chart background.  Uses medium-bright tones that are visible
    on both light and dark surfaces.

    Args:
        basemap_img (PIL.Image.Image): Basemap tile image (RGBA).

    Returns:
        tuple: ``(R, G, B)`` colour tuple.
    """
    if basemap_img is None:
        return (220, 220, 220)
    try:
        small = basemap_img.resize((16, 16)).convert("RGB")
        pixels = list(small.getdata())
        avg_r = sum(p[0] for p in pixels) // len(pixels)
        avg_g = sum(p[1] for p in pixels) // len(pixels)
        avg_b = sum(p[2] for p in pixels) // len(pixels)
        luminance = 0.299 * avg_r + 0.587 * avg_g + 0.114 * avg_b
        if luminance < 100:
            # Very dark basemap → bright white
            return (255, 255, 255)
        elif luminance < 170:
            # Medium basemap (hillshade) → bright color visible on both
            return (220, 220, 220)
        else:
            # Light basemap → dark but not too dark (visible on dark chart bg)
            return (80, 80, 80)
    except Exception:
        return (220, 220, 220)


def _resolve_geometry_color(geometry_outline_color, font_color, basemap, bounds):
    """Resolve the geometry outline colour.

    Priority: explicit color > auto from basemap > font_color.
    """
    if geometry_outline_color is not None:
        if isinstance(geometry_outline_color, str):
            return _resolve_color(geometry_outline_color)
        return geometry_outline_color
    if basemap is not None and bounds is not None:
        try:
            bm = _fetch_basemap(bounds, 64, 64, basemap)
            return _auto_geometry_color(bm)
        except Exception:
            pass
    return font_color or (255, 255, 255)


def _paint_boundary(ee_obj, geometry, color, viz_params=None, fill_color=None, width=2, crs=None):
    """Paint a geometry boundary outline onto an ee.Image or ee.ImageCollection.

    Uses ``FeatureCollection.style()`` to render the boundary as a styled
    RGB image, then ``.blend()`` it onto each visualized frame.  The data
    image is first visualized with *viz_params* (producing an RGB image),
    then the styled outline is blended on top.

    Args:
        ee_obj: ``ee.Image`` or ``ee.ImageCollection``.
        geometry: ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.
        color (tuple or list): ``(R, G, B)`` colour for the outline (0–255).
        viz_params (dict, optional): Visualization parameters to apply
            before blending.  When ``None`` the image is assumed to be
            already visualized or single-band.
        fill_color (str, optional): CSS fill colour for the geometry interior
            (e.g. ``"33333388"`` for semi-transparent). Default ``None`` (no fill).

    Returns:
        Same type as *ee_obj* with boundary painted on and pre-visualized
        as 3-band ``vis-red/vis-green/vis-blue``.
    """
    geom = _to_geometry(geometry)

    # Build FeatureCollection for styling (accepts geometry, Feature, or FC)
    if isinstance(geometry, ee.FeatureCollection):
        boundary_fc = geometry
    elif isinstance(geometry, (ee.Feature, ee.element.Element)):
        boundary_fc = ee.FeatureCollection([ee.Feature(geometry)])
    else:
        boundary_fc = ee.FeatureCollection([ee.Feature(geom)])

    # Convert colour to hex string for .style()
    if isinstance(color, str):
        gc = list(_resolve_color(color))
    else:
        gc = list(color)
    hex_color = "{:02x}{:02x}{:02x}".format(int(gc[0]), int(gc[1]), int(gc[2]))

    # Render styled boundary and set projection so it aligns with the data CRS
    _fill = fill_color if fill_color is not None else "00000000"
    styled_boundary = boundary_fc.style(
        color=hex_color, fillColor=_fill, width=width,
    )
    if crs is not None:
        styled_boundary = styled_boundary.setDefaultProjection(crs, None, 1)

    def _paint_img(img):
        img = ee.Image(img)
        # If image has no bands (geometry-only), return just the styled boundary
        has_bands = viz_params and any(k in viz_params for k in ("bands", "min", "max", "palette"))
        if has_bands:
            vis = img.visualize(**{k: v for k, v in viz_params.items()
                                   if k not in ("dimensions", "format", "region")})
        else:
            # No data to visualize — use styled boundary as the image
            return ee.Image(styled_boundary).copyProperties(img, ["system:time_start"])
        # Blend styled boundary on top — cast back to ee.Image
        return ee.Image(vis.blend(styled_boundary)).copyProperties(img, ["system:time_start"])

    if isinstance(ee_obj, ee.ImageCollection):
        return ee_obj.map(_paint_img)
    return ee.Image(_paint_img(ee.Image(ee_obj)))

    if isinstance(ee_obj, ee.ImageCollection):
        return ee_obj.map(_paint_img)
    return _paint_img(ee.Image(ee_obj))


def _assemble_with_cartography(frame, bounds_4326, bg_color="black",
                                font_color=None, font_outline_color=None,
                                title=None, scalebar=True,
                                scalebar_units="metric", north_arrow=True,
                                north_arrow_style="solid",
                                inset_map=True, inset_basemap=None, inset_scale=0.3,
                                inset_on_map=True,
                                inset_rect_color=None, inset_rect_fill_color=None,
                                legend_panel=None, inset_below_legend=True,
                                margin=_DEFAULT_MARGIN, crs=None):
    """Assemble a map frame with cartographic elements into a final image.

    Combines the raw EE thumbnail frame with optional cartographic
    decorations: scalebar, north arrow, inset overview map, legend panel,
    and title strip.  The layout follows these rules:

    * **Scalebar and north arrow** are drawn directly on the map image
      (lower-left and upper-right, respectively).
    * **Inset map** is placed on the map (lower-right) when
      ``inset_on_map`` is True; otherwise it is positioned below the
      legend or below the main frame.
    * **Legend panel** is appended as a right-side column.
    * **Title strip** is stacked above the entire composition.

    Args:
        frame (PIL.Image.Image): The map thumbnail frame (RGBA).
        bounds_4326 (tuple or None): Geographic bounds as
            ``(xmin, ymin, xmax, ymax)`` in EPSG:4326, used for
            scalebar distance calculation and inset generation.  Pass
            ``None`` to skip all geographic decorations.
        bg_color (str, optional): Background color name or hex string.
            Defaults to ``"black"``.
        font_color (str or tuple, optional): Text color for labels.
            Resolved via theme when ``None``.  Defaults to ``None``.
        font_outline_color (str or tuple, optional): Outline color for
            text readability.  Auto-derived when ``None``.
            Defaults to ``None``.
        title (str, optional): Title text rendered as a strip above the
            frame.  Defaults to ``None`` (no title).
        scalebar (bool, optional): Draw a scalebar on the lower-left of
            the map.  Defaults to ``True``.
        scalebar_units (str, optional): Unit system for the scalebar,
            either ``"metric"`` or ``"imperial"``.
            Defaults to ``"metric"``.
        north_arrow (bool, optional): Draw a north arrow on the
            upper-right of the map.  Defaults to ``True``.
        north_arrow_style (str, optional): Arrow style -- ``"solid"``,
            ``"classic"``, or ``"outline"``.  Defaults to ``"solid"``.
        inset_map (bool, optional): Generate and include an inset
            overview map.  Defaults to ``True``.
        inset_basemap (str or dict, optional): Basemap for the inset.
            Falls back to the main basemap when ``None``.
            Defaults to ``None``.
        inset_scale (float, optional): Relative height of the inset
            compared to the frame height.  Defaults to ``0.3``.
        inset_on_map (bool, optional): Place the inset directly on the
            map rather than below it.  Defaults to ``True``.
        legend_panel (PIL.Image.Image, optional): Pre-built legend panel
            image to attach as a right-side column.
            Defaults to ``None``.
        inset_below_legend (bool, optional): When the inset is not on
            the map and a legend is present, place the inset below the
            legend in the right column.  Defaults to ``True``.
        margin (int, optional): Internal padding in pixels used for
            spacing calculations.  Defaults to ``16``.

    Returns:
        tuple: A 2-element tuple of ``(PIL.Image.Image, bool)`` where
        the image is the assembled result and the boolean indicates
        whether a below-frame element was added (used by callers to
        adjust outer margin).

    Example:
        >>> assembled, has_bottom = _assemble_with_cartography(
        ...     frame, bounds_4326=(-111.5, 40.0, -110.5, 41.0),
        ...     title="LCMS Land Cover 2023", scalebar=True,
        ... )
    """
    from PIL import Image, ImageDraw

    bg_rgba = _resolve_color(bg_color) + (255,)
    font_color, font_outline_color, theme, bg_color = _resolve_font_colors(
        bg_color, font_color, font_outline_color)
    contrast = font_outline_color

    try:
        # --- Build inset image ---
        inset_img = None
        if inset_map and bounds_4326 is not None:
            # Compute final display size so we fetch at that resolution
            _inset_display_h = int(frame.size[1] * inset_scale)
            _inset_kw = {}
            if inset_rect_color is not None:
                _inset_kw["rect_color"] = inset_rect_color
            if inset_rect_fill_color is not None:
                _inset_kw["rect_fill_color"] = inset_rect_fill_color
            inset_img = _build_inset_image(
                bounds_4326, size=_inset_display_h,
                inset_basemap=inset_basemap, crs=crs, **_inset_kw,
            )

        # --- Draw scalebar + north arrow ON the frame (lower-left) ---
        if bounds_4326 is not None and (scalebar or north_arrow):
            _draw_scalebar_and_arrow_on_frame(
                frame, bounds_4326, scalebar=scalebar,
                scalebar_units=scalebar_units, north_arrow=north_arrow,
                north_arrow_style=north_arrow_style,
                font_color=font_color, contrast=contrast,
                accent=theme.accent, crs=crs,
            )

        # --- Place inset ON the map (lower-right) if requested ---
        if inset_on_map and inset_img is not None:
            target_h = int(frame.size[1] * inset_scale)
            src_w, src_h = inset_img.size
            aspect = src_w / src_h if src_h > 0 else 1.0
            iw = int(target_h * aspect)
            ih = target_h
            if iw > frame.size[0] // 3:
                iw = frame.size[0] // 3
                ih = int(iw / aspect)
            inset_resized = inset_img.resize((iw, ih), Image.LANCZOS)
            padding = max(6, margin // 2)
            px = frame.size[0] - iw - padding
            py = frame.size[1] - ih - padding
            frame.paste(inset_resized, (px, py),
                       inset_resized if inset_resized.mode == "RGBA" else None)
            inset_img = None  # consumed

        # --- Attach legend + inset in right column ---
        if legend_panel is not None:
            col_w = legend_panel.size[0]
            col_h = frame.size[1]

            if inset_img is not None and inset_below_legend:
                # Inset below legend in right column
                inset_pad_left = max(4, margin // 3)
                inset_target_h = int(col_h * inset_scale)
                src_w, src_h = inset_img.size
                aspect = src_w / src_h if src_h > 0 else 1.0
                max_inset_w = col_w - inset_pad_left
                iw = int(inset_target_h * aspect)
                ih = inset_target_h
                if iw > max_inset_w:
                    iw = max_inset_w
                    ih = int(max_inset_w / aspect)
                inset_resized = inset_img.resize((iw, ih), Image.LANCZOS)
                inset_img = None

                legend_h = col_h - ih
                legend_resized = legend_panel.resize((col_w, legend_h), Image.LANCZOS)

                right_col = Image.new("RGBA", (col_w, col_h), bg_rgba)
                right_col.paste(legend_resized, (0, 0),
                               legend_resized if legend_resized.mode == "RGBA" else None)
                right_col.paste(inset_resized, (inset_pad_left, col_h - ih),
                               inset_resized if inset_resized.mode == "RGBA" else None)
            else:
                right_col = Image.new("RGBA", (col_w, col_h), bg_rgba)
                right_col.paste(legend_panel, (0, 0),
                               legend_panel if legend_panel.mode == "RGBA" else None)

            combined_w = frame.size[0] + col_w
            combined = Image.new("RGBA", (combined_w, col_h), bg_rgba)
            combined.paste(frame, (0, 0))
            combined.paste(right_col, (frame.size[0], 0),
                          right_col if right_col.mode == "RGBA" else None)
            frame = combined

        # --- Place inset below frame if not consumed ---
        has_below = False
        if inset_img is not None:
            target_h = int(frame.size[1] * inset_scale)
            src_w, src_h = inset_img.size
            aspect = src_w / src_h if src_h > 0 else 1.0
            iw = int(target_h * aspect)
            ih = target_h
            if iw > frame.size[0] // 3:
                iw = frame.size[0] // 3
                ih = int(iw / aspect)
            inset_resized = inset_img.resize((iw, ih), Image.LANCZOS)

            gap_above = max(4, margin // 3)
            inset_row = Image.new("RGBA", (frame.size[0], ih), bg_rgba)
            inset_row.paste(inset_resized, (0, 0),
                           inset_resized if inset_resized.mode == "RGBA" else None)

            combined_h = frame.size[1] + gap_above + ih
            combined = Image.new("RGBA", (frame.size[0], combined_h), bg_rgba)
            combined.paste(frame, (0, 0))
            combined.paste(inset_row, (0, frame.size[1] + gap_above),
                          inset_row if inset_row.mode == "RGBA" else None)
            frame = combined
            has_below = True

        # --- Title strip ---
        title_strip = None
        if title:
            title_strip = _build_title_strip(
                frame.size[0], title, bg_color=bg_rgba,
                text_color=font_color, margin=margin,
            )

        # --- Stack: title + frame ---
        if title_strip is not None:
            total_w = max(frame.size[0], title_strip.size[0])
            total_h = frame.size[1] + title_strip.size[1]
            final = Image.new("RGBA", (total_w, total_h), bg_rgba)
            final.paste(title_strip, (0, 0),
                       title_strip if title_strip.mode == "RGBA" else None)
            final.paste(frame, (0, title_strip.size[1]),
                       frame if frame.mode == "RGBA" else None)
            return final, has_below

        return frame, has_below

    except Exception:
        return frame, False  # Never let decoration failures break thumbnail generation


def _compute_convergence(bounds_4326, crs=None):
    """Compute the grid convergence angle (degrees) at the center of bounds.

    Grid convergence is the angle between true north and grid north.
    For EPSG:4326 this is 0. For projected CRS like Albers, it varies
    with longitude relative to the central meridian.

    Uses Earth Engine to project two points (center and center+0.1 lat)
    into the target CRS and computes the angle of the projected line
    relative to the y-axis.

    Returns 0 if CRS is None, "EPSG:4326", or if computation fails.
    """
    if crs is None or crs in ("EPSG:4326", "epsg:4326"):
        return 0.0
    try:
        xmin, ymin, xmax, ymax = bounds_4326
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0
        # Project center and a point slightly north
        p1 = ee.Geometry.Point([cx, cy]).transform(crs, 1).coordinates().getInfo()
        p2 = ee.Geometry.Point([cx, cy + 0.1]).transform(crs, 1).coordinates().getInfo()
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        angle_rad = math.atan2(dx, dy)  # angle from y-axis
        return math.degrees(angle_rad)
    except Exception:
        return 0.0


def _draw_scalebar_and_arrow_on_frame(frame, bounds_4326, scalebar=True,
                                       scalebar_units="metric", north_arrow=True,
                                       north_arrow_style="solid",
                                       font_color=(255, 255, 255),
                                       contrast=(0, 0, 0), accent=(180, 180, 180),
                                       label_font_size=_DEFAULT_LABEL_FONT_SIZE,
                                       crs=None):
    """Draw a scalebar and north arrow directly onto a map frame in-place.

    The scalebar is rendered in the lower-left corner with a
    semi-transparent background and alternating color segments.  The
    north arrow is placed in the upper-right corner.  Both elements are
    sized relative to the frame dimensions and the geographic extent.

    Args:
        frame (PIL.Image.Image): RGBA map frame to draw on.  Modified
            in-place.
        bounds_4326 (tuple): Geographic bounds as
            ``(xmin, ymin, xmax, ymax)`` in EPSG:4326.  Used to
            calculate the real-world distance for the scalebar.
        scalebar (bool, optional): Whether to draw the scalebar.
            Defaults to ``True``.
        scalebar_units (str, optional): Unit system -- ``"metric"``
            (meters / km) or ``"imperial"`` (feet / miles).
            Defaults to ``"metric"``.
        north_arrow (bool, optional): Whether to draw the north arrow.
            Defaults to ``True``.
        north_arrow_style (str, optional): Arrow visual style --
            ``"solid"``, ``"classic"``, or ``"outline"``.
            Defaults to ``"solid"``.
        font_color (tuple, optional): ``(R, G, B)`` tuple for scalebar
            text and primary bar segments.
            Defaults to ``(255, 255, 255)``.
        contrast (tuple, optional): ``(R, G, B)`` tuple for the bar
            outline and alternating segments.
            Defaults to ``(0, 0, 0)``.
        accent (tuple, optional): ``(R, G, B)`` tuple for secondary bar
            segments and arrow accents.
            Defaults to ``(180, 180, 180)``.

    Returns:
        None: The frame is modified in-place.

    Example:
        >>> _draw_scalebar_and_arrow_on_frame(
            label_font_size=label_font_size,
        ...     frame, (-111.5, 40.0, -110.5, 41.0),
        ...     scalebar_units="imperial", north_arrow_style="classic",
        ... )
    """
    from PIL import Image, ImageDraw
    from geeViz.outputLib._basemaps import (
        _pick_nice_distance, _format_metric, _format_imperial,
        _get_font as _bm_get_font,
        _M_PER_DEG_LAT, _METRIC_STEPS, _IMPERIAL_STEPS_FT,
        render_north_arrow,
    )

    w, h = frame.size
    padding = max(8, w // 40)  # margin from frame edge

    xmin, ymin, xmax, ymax = bounds_4326
    mid_lat = (ymin + ymax) / 2.0
    lon_span_m = (xmax - xmin) * _M_PER_DEG_LAT * math.cos(math.radians(mid_lat))
    if lon_span_m <= 0:
        return

    draw = ImageDraw.Draw(frame)

    # --- Scalebar (lower-left) ---
    if scalebar:
        # Scale font to frame size but cap at label_font_size
        fs = min(label_font_size, max(8, w // 35))
        sfont = _get_font(fs)
        bar_h = max(3, fs // 3)

        if scalebar_units == "imperial":
            total_ft = lon_span_m * 3.28084
            bar_val = _pick_nice_distance(total_ft, _IMPERIAL_STEPS_FT)
            bar_frac = bar_val / total_ft
            label = _format_imperial(bar_val)
        else:
            bar_val = _pick_nice_distance(lon_span_m, _METRIC_STEPS)
            bar_frac = bar_val / lon_span_m
            label = _format_metric(bar_val)

        bar_px = max(20, int(w * bar_frac))
        bar_px = min(bar_px, w // 3)

        # Determine display value and unit label
        if scalebar_units == "imperial":
            if bar_val >= 5_280:
                display_val = bar_val / 5_280
                unit_str = "Miles"
            else:
                display_val = bar_val
                unit_str = "ft"
        else:
            if bar_val >= 1_000:
                display_val = bar_val / 1_000
                unit_str = "km"
            else:
                display_val = bar_val
                unit_str = "m"

        # Number of bar segments from the display value
        seg = max(2, min(int(display_val), 10))

        # Tick labels: 0, midpoint, end + unit at bar end
        tick_font_size = fs  # same as scalebar font
        tick_font = _get_font(tick_font_size)
        mid_seg = seg // 2
        mid_val = display_val * mid_seg / seg

        def _fmt_tick(v):
            return f"{v:g}"

        tick_0 = "0"
        tick_mid = _fmt_tick(mid_val)
        tick_end = _fmt_tick(display_val)

        # Measure tick height for layout
        tb = draw.textbbox((0, 0), tick_0, font=tick_font)
        tick_h = tb[3] - tb[1]
        tick_gap = 2  # gap between bar and tick labels
        unit_bb = draw.textbbox((0, 0), unit_str, font=tick_font)
        unit_w = unit_bb[2] - unit_bb[0]

        tick_mark_h = max(2, bar_h // 2)
        elem_h = bar_h + tick_gap + tick_mark_h + 1 + tick_h
        bx = padding
        by = h - padding - elem_h

        # Semi-transparent background (compact)
        bg_pad = 4
        bg_x0 = max(0, bx - bg_pad)
        bg_y0 = max(0, by - bg_pad)
        bg_x1 = min(w, bx + bar_px + bg_pad + unit_w + 6)
        bg_y1 = min(h, by + elem_h + bg_pad)
        bg_w = bg_x1 - bg_x0
        bg_h = bg_y1 - bg_y0
        if bg_w > 0 and bg_h > 0:
            bg_layer = Image.new("RGBA", (bg_w, bg_h), (0, 0, 0, 0))
            ImageDraw.Draw(bg_layer).rounded_rectangle(
                (0, 0, bg_w - 1, bg_h - 1), radius=4, fill=(0, 0, 0, 120))
            frame.paste(bg_layer, (bg_x0, bg_y0), bg_layer)
        draw = ImageDraw.Draw(frame)

        # Draw bar segments
        draw.rectangle((bx - 1, by - 1, bx + bar_px + 1, by + bar_h + 1),
                       fill=contrast)
        sw = bar_px // seg
        for si in range(seg):
            sx = bx + si * sw
            ex = bx + (si + 1) * sw if si < seg - 1 else bx + bar_px
            c = font_color if si % 2 == 0 else accent
            draw.rectangle((sx, by, ex, by + bar_h), fill=c)

        # Small vertical tick marks + labels below bar
        bar_left = bx
        bar_right = bx + bar_px
        bar_mid = bx + mid_seg * sw
        tick_top = by + bar_h + 1
        ty = tick_top + tick_mark_h + 1

        # Measure average char width for half-char offset
        _cbb = draw.textbbox((0, 0), "0", font=tick_font)
        half_char = (_cbb[2] - _cbb[0]) // 2

        tick_positions = [
            (bar_left, tick_0, "left"),
            (bar_mid, tick_mid, "center"),
            (bar_right, tick_end, "right"),
        ]
        for tx_pos, txt, align in tick_positions:
            # Vertical tick mark from bar bottom edge down
            draw.line([(tx_pos, tick_top), (tx_pos, tick_top + tick_mark_h)],
                      fill=font_color, width=1)
            # Label — offset by half a char width so the glyph edge
            # aligns with the bar edge, not the glyph center
            tbb = draw.textbbox((0, 0), txt, font=tick_font)
            ttw = tbb[2] - tbb[0]
            # Center label on tick, nudge left/right labels slightly
            lx = tx_pos - ttw // 2
            if align == "left":
                lx += 1
            elif align == "right":
                lx -= 1
            draw.text((lx, ty - tbb[1] + 1), txt, fill=font_color, font=tick_font)

        # Unit label to the right of the bar, raised 2px
        draw.text((bx + bar_px + 4, by + (bar_h - tick_h) // 2 - 2), unit_str,
                  fill=font_color, font=tick_font)

    # --- North arrow (upper-right, rotated for CRS convergence) ---
    if north_arrow:
        arrow_size = max(20, min(w, h) // 12)
        arrow_img = render_north_arrow(
            arrow_size, font_color=font_color, accent=accent,
            contrast=contrast, style=north_arrow_style,
        )

        # Compute grid convergence angle if CRS is not 4326
        convergence_deg = _compute_convergence(bounds_4326, crs=crs)
        if abs(convergence_deg) > 0.5:
            arrow_img = arrow_img.rotate(
                -convergence_deg,  # PIL rotates counter-clockwise
                resample=Image.BICUBIC,
                expand=False,
            )

        ax = w - padding - arrow_size
        ay = padding
        frame.paste(arrow_img, (ax, ay), arrow_img)


# ---------------------------------------------------------------------------
#  Auto-viz from image properties
# ---------------------------------------------------------------------------
_DEFAULT_CONTINUOUS_SCALE = 300
_DEFAULT_CONTINUOUS_TIMEOUT = 5


def auto_viz_continuous(
    image,
    geometry,
    band_names=None,
    stretch_type="percentile",
    percentiles=None,
    n_stddev=2,
    gamma=1.6,
    scale=_DEFAULT_CONTINUOUS_SCALE,
    timeout=_DEFAULT_CONTINUOUS_TIMEOUT,
    max_scale=None,
):
    """Build visualization parameters for a continuous ``ee.Image`` by sampling the region.

    Performs a ``reduceRegion`` at a coarse resolution to compute stretch
    statistics.  If the call times out the scale is doubled and retried
    until it succeeds or ``max_scale`` is exceeded.

    Args:
        image (ee.Image): Image to visualize.  Must **not** be an
            ``ee.ImageCollection`` — reduce the collection first.
        geometry: ``ee.Geometry``, ``ee.Feature``, or
            ``ee.FeatureCollection`` defining the region to sample.
        band_names (list[str], optional): Bands to visualize — length
            must be 1 or 3.  When ``None`` the first 3 bands are used
            (or first 1 if fewer than 3 exist).  Defaults to ``None``.
        stretch_type (str): One of ``"percentile"`` (default),
            ``"min-max"``, or ``"stddev"``.
        percentiles (list[int], optional): ``[lower, upper]`` percentiles
            for the ``"percentile"`` stretch.  Defaults to ``[0, 95]``.
        n_stddev (float): Number of standard deviations for the
            ``"stddev"`` stretch (symmetric around the mean).  Default 2.
        gamma (float, optional): Gamma correction applied to the
            output viz params.  Values > 1 brighten midtones (lifts
            dark pixels without blowing out highlights); values < 1
            darken midtones.  ``1.0`` means no correction.  Included
            in the returned dict as ``"gamma"`` when not ``1.0``.
            Defaults to ``1.6``.
        scale (int): Starting spatial resolution in meters for
            ``reduceRegion``.  Default 300.
        timeout (int): ``getInfo`` timeout in seconds per attempt.
            Default 5.
        max_scale (int, optional): Stop retrying when ``scale`` exceeds
            this value.  Default is ``scale * 16`` (4 doublings).

    Returns:
        dict: Visualization parameters with ``bands``, ``min``, ``max``
        keys, and ``gamma`` when gamma is not 1.0.  ``min`` / ``max``
        are scalars for single-band images and lists for 3-band images.

    Raises:
        TypeError: If *image* is an ``ee.ImageCollection``.
        ValueError: If *band_names* length is not 1 or 3, or if
            *stretch_type* is unrecognised.

    Example:
        >>> viz = auto_viz_continuous(
        ...     s2_composite, study_area,
        ...     band_names=["swir2", "nir", "red"],
        ...     stretch_type="percentile", percentiles=[0, 99],
        ... )
        >>> sorted(viz.keys())
        ['bands', 'gamma', 'max', 'min']
        >>> viz["gamma"]
        1.6
    """
    if isinstance(image, ee.ImageCollection):
        image = ee.Image(image.mosaic())

    if max_scale is None:
        max_scale = scale * 16

    if percentiles is None:
        percentiles = [0, 95]

    if stretch_type not in ("percentile", "min-max", "stddev"):
        raise ValueError(
            f"stretch_type must be 'percentile', 'min-max', or 'stddev', "
            f"got '{stretch_type}'"
        )

    # --- resolve geometry ---------------------------------------------------
    geom = _to_geometry(geometry)

    # --- resolve bands ------------------------------------------------------
    img = ee.Image(image)
    if band_names is not None:
        if len(band_names) not in (1, 3):
            raise ValueError(
                f"band_names must have length 1 or 3, got {len(band_names)}"
            )
        img = img.select(band_names)
    else:
        # Pick first 3 (or first 1) on the server side
        all_bands = img.bandNames()
        n_bands = all_bands.size()
        selected = ee.Algorithms.If(
            n_bands.gte(3), all_bands.slice(0, 3), all_bands.slice(0, 1)
        )
        img = img.select(ee.List(selected))

    # --- build reducer ------------------------------------------------------
    if stretch_type == "min-max":
        reducer = ee.Reducer.minMax()
    elif stretch_type == "stddev":
        reducer = ee.Reducer.mean().combine(
            ee.Reducer.stdDev(), sharedInputs=True
        )
    else:  # percentile
        reducer = ee.Reducer.percentile(percentiles)

    # --- reduceRegion with timeout + scale doubling -------------------------
    current_scale = scale
    stats = None
    while current_scale <= max_scale:
        try:
            reduction = img.reduceRegion(
                reducer=reducer,
                geometry=geom,
                scale=current_scale,
                bestEffort=True,
                maxPixels=1e7,
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(reduction.getInfo)
                try:
                    stats = future.result(timeout=timeout)
                except concurrent.futures.TimeoutError:
                    stats = None

            if stats is not None and any(
                v is not None for v in stats.values()
            ):
                break
            stats = None
        except Exception:
            stats = None

        current_scale *= 2

    # --- determine actual band names ----------------------------------------
    if band_names is not None:
        used_bands = list(band_names)
    else:
        try:
            used_bands = img.bandNames().getInfo()
        except Exception:
            used_bands = ["B0"]

    # --- parse stats into min / max lists -----------------------------------
    if stats is None:
        min_vals = [0] * len(used_bands)
        max_vals = [1] * len(used_bands)
    elif stretch_type == "min-max":
        min_vals = [stats.get(f"{b}_min", 0) or 0 for b in used_bands]
        max_vals = [stats.get(f"{b}_max", 1) or 1 for b in used_bands]
    elif stretch_type == "stddev":
        min_vals, max_vals = [], []
        for b in used_bands:
            mean = stats.get(f"{b}_mean", 0) or 0
            sd = stats.get(f"{b}_stdDev", 1) or 1
            min_vals.append(mean - n_stddev * sd)
            max_vals.append(mean + n_stddev * sd)
    else:  # percentile
        p_lo = f"p{percentiles[0]}"
        p_hi = f"p{percentiles[1]}"
        min_vals = [stats.get(f"{b}_{p_lo}", 0) or 0 for b in used_bands]
        max_vals = [stats.get(f"{b}_{p_hi}", 1) or 1 for b in used_bands]

    # Simplify single-band to scalar and add band-aware palette
    if len(used_bands) == 1:
        min_vals = min_vals[0]
        max_vals = max_vals[0]
        return {
            "bands": used_bands,
            "min": min_vals,
            "max": max_vals,
            "palette": _get_palette_for_band(used_bands[0]),
        }

    viz = {"bands": used_bands, "min": min_vals, "max": max_vals}
    if gamma is not None and gamma != 1.0:
        viz["gamma"] = gamma
    return viz


def auto_viz(
    ee_obj,
    band_name=None,
    geometry=None,
    stretch_type="percentile",
    percentiles=None,
    n_stddev=2,
    gamma=1.6,
    scale=_DEFAULT_CONTINUOUS_SCALE,
    timeout=_DEFAULT_CONTINUOUS_TIMEOUT,
):
    """Build visualization parameters automatically from image properties.

    For **thematic** data (images with ``{band}_class_values`` and
    ``{band}_class_palette`` properties) returns a palette-based viz dict
    mapping class values to colours.

    For **continuous** data:

    * When ``geometry`` is provided, delegates to
      :func:`auto_viz_continuous` which samples the region to compute
      data-driven min/max.
    * Otherwise falls back to hard-coded defaults.

    Args:
        ee_obj (ee.Image or ee.ImageCollection): Earth Engine object to
            inspect.
        band_name (str, optional): Specific band to visualize.
        geometry: ``ee.Geometry``, ``ee.Feature``, or
            ``ee.FeatureCollection``.  When provided continuous data is
            stretched from actual region values.
        stretch_type (str): Stretch for continuous data — ``"percentile"``
            (default), ``"min-max"``, or ``"stddev"``.
        percentiles (list[int], optional): ``[lower, upper]`` for
            percentile stretch.  Default ``[5, 95]``.
        n_stddev (float): Standard deviations for ``"stddev"`` stretch.
        gamma (float, optional): Gamma correction for continuous data.
            Values > 1 brighten midtones; < 1 darken.  Included in the
            returned dict as ``"gamma"`` when not ``1.0``.  Ignored for
            thematic data.  Defaults to ``1.6``.
        scale (int): Starting scale (m) for ``reduceRegion``.
        timeout (int): Timeout (s) per ``reduceRegion`` attempt.

    Returns:
        dict: Visualization parameters suitable for
        ``ee.Image.getThumbURL()``.  For continuous data includes
        ``bands``, ``min``, ``max``, and ``gamma`` (when not 1.0).
        For thematic data includes ``bands``, ``min``, ``max``, and
        ``palette``.

    Example:
        >>> viz = auto_viz(lcms.select(["Land_Cover"]))
        >>> viz["bands"]
        ['Land_Cover']

        >>> viz = auto_viz(s2_composite, geometry=study_area,
        ...                stretch_type="percentile", percentiles=[2, 98])
        >>> viz["gamma"]
        1.6
    """
    info = cl.get_obj_info(ee_obj, band_names=[band_name] if band_name else None)
    band_names_list = info["band_names"]

    # Detect pre-visualized RGB images (vis-red/vis-green/vis-blue only)
    # Do NOT match raw sensor band names like "red", "green", "blue" —
    # those are reflectance values that need a computed stretch.
    _VIS_RGB_NAMES = {"vis-red", "vis-green", "vis-blue", "vis_red", "vis_green", "vis_blue"}
    if len(band_names_list) == 3 and all(
        b.lower() in _VIS_RGB_NAMES for b in band_names_list
    ):
        return {"bands": band_names_list[:3], "min": 0, "max": 255}

    if info["is_thematic"] and band_names_list:
        bn = band_names_list[0]
        ci = info["class_info"].get(bn, {})
        values = ci.get("class_values", [])
        palette = ci.get("class_palette", [])
        if values and palette:
            return {
                "bands": [bn],
                "min": min(values),
                "max": max(values),
                "palette": palette,
            }

    # Continuous — if geometry provided, compute data-driven stretch
    if geometry is not None:
        band_arg = [band_name] if band_name else None
        if band_arg is None and len(band_names_list) >= 3:
            band_arg = band_names_list[:3]
        elif band_arg is None and band_names_list:
            band_arg = [band_names_list[0]]
        return auto_viz_continuous(
            ee_obj,
            geometry,
            band_names=band_arg,
            stretch_type=stretch_type,
            percentiles=percentiles,
            n_stddev=n_stddev,
            gamma=gamma,
            scale=scale,
            timeout=timeout,
        )

    # Continuous — no geometry, use defaults
    if len(band_names_list) >= 3:
        return {"bands": band_names_list[:3], "min": 0, "max": 0.4}
    elif band_names_list:
        return {"bands": [band_names_list[0]], **_CONTINUOUS_DEFAULTS}

    return _CONTINUOUS_DEFAULTS.copy()


def _complete_viz_params(viz_params, ee_obj, band_name=None, geometry=None,
                         stretch_type="percentile", percentiles=None,
                         n_stddev=2, gamma=1.6, scale=_DEFAULT_CONTINUOUS_SCALE,
                         timeout=_DEFAULT_CONTINUOUS_TIMEOUT):
    """Fill in missing ``min`` / ``max`` in partial viz_params via auto_viz.

    When the user supplies ``viz_params`` with a ``palette`` but no
    ``min`` / ``max``, runs :func:`auto_viz` to compute the stretch and
    merges the user's palette on top.  Returns *viz_params* unmodified
    when it is ``None`` or already complete.
    """
    if viz_params is None:
        return auto_viz(ee_obj, band_name=band_name, geometry=geometry,
                        stretch_type=stretch_type, percentiles=percentiles,
                        n_stddev=n_stddev, gamma=gamma, scale=scale, timeout=timeout)

    has_min = viz_params.get("min") is not None
    has_max = viz_params.get("max") is not None

    if has_min and has_max:
        return viz_params  # already complete

    # Partial — compute auto stretch then overlay user's keys
    auto = auto_viz(ee_obj, band_name=band_name, geometry=geometry,
                    stretch_type=stretch_type, percentiles=percentiles,
                    n_stddev=n_stddev, gamma=gamma, scale=scale, timeout=timeout)
    merged = {**auto, **{k: v for k, v in viz_params.items() if v is not None}}
    return merged


# ---------------------------------------------------------------------------
#  Core thumbnail URL functions
# ---------------------------------------------------------------------------
def get_thumb_url(ee_obj, geometry=None, viz_params=None, dimensions=_DEFAULT_DIMENSIONS,
                  band_name=None, crs=_DEFAULT_CRS, transform=None, scale=None,
                  burn_in_geometry=False, geometry_outline_color=None,
                  geometry_fill_color=None, geometry_outline_weight=2,
                  clip_to_geometry=True):
    """Get a PNG thumbnail URL for an Earth Engine image.

    Generates an ``ee.Image.getThumbURL()`` call with automatic
    visualization detection when ``viz_params`` is not supplied.  The
    image is optionally clipped to ``geometry`` and reprojected when
    ``crs`` is provided.  For ``ee.ImageCollection`` inputs, the
    collection is reduced to a single image (mode for thematic data,
    median for continuous).

    Args:
        ee_obj (ee.Image or ee.ImageCollection): Image to thumbnail.
            Collections are reduced to a single representative image.
        geometry (ee.Geometry or ee.Feature or ee.FeatureCollection, optional):
            Region to clip and bound the thumbnail.
            Defaults to ``None`` (full image extent).
        viz_params (dict, optional): Visualization parameters (``bands``,
            ``min``, ``max``, ``palette``, etc.).  Auto-detected via
            :func:`auto_viz` when ``None``.  Defaults to ``None``.
        dimensions (int, optional): Thumbnail width in pixels.
            Defaults to ``640``.
        band_name (str, optional): Band to visualize when using
            auto-detection.  Defaults to ``None`` (first band).
        crs (str, optional): Coordinate reference system code
            (e.g. ``"EPSG:4326"``, ``"EPSG:32612"``).  When provided,
            ``setDefaultProjection`` is applied to the image.
            Defaults to ``None``.
        transform (list, optional): Affine transform as a 6-element
            list.  Requires ``crs``.  Defaults to ``None``.
        scale (float, optional): Nominal pixel scale in meters.
            Requires ``crs``.  Defaults to ``None``.

    Returns:
        str: PNG thumbnail URL string from the Earth Engine servers.

    Raises:
        ValueError: If ``transform`` or ``scale`` is provided without
            ``crs``.

    Example:
        >>> url = get_thumb_url(
        ...     image, study_area,
        ...     {"min": 0, "max": 3000, "bands": ["swir1", "nir", "red"]},
        ... )
        >>> url[:5]
        'https'
    """
    _validate_projection_params(crs, transform, scale)

    # Allow ee_obj=None for geometry-only thumbnails (just burn in boundary)
    _is_geom_only = ee_obj is None
    if _is_geom_only:
        img = ee.Image()
        if viz_params is None:
            viz_params = {}
        burn_in_geometry = True
    else:
        img = _to_image(ee_obj)
    img = _apply_projection(img, crs, transform, scale)

    if not _is_geom_only:
        viz_params = _complete_viz_params(viz_params, img, band_name=band_name, geometry=geometry)

    params = {**viz_params, "dimensions": dimensions, "format": "png"}

    if geometry is not None:
        geom = _to_geometry(geometry)
        img = img.clip(geom)
        if burn_in_geometry:
            gc = geometry_outline_color if geometry_outline_color is not None else (255, 255, 255)
            _fill = "33333366" if _is_geom_only else None  # 0.4 opacity
            img = _paint_boundary(img, geom, gc, viz_params=viz_params, fill_color=_fill or geometry_fill_color, width=geometry_outline_weight, crs=crs)
            params = {"min": 0, "max": 255, "dimensions": dimensions, "format": "png"}
        if clip_to_geometry:
            params["region"] = geom
        else:
            params["region"] = geom.bounds()

    return img.getThumbURL(params)


def get_animation_url(ee_obj, geometry=None, viz_params=None,
                      dimensions=_DEFAULT_DIMENSIONS, fps=_DEFAULT_FPS,
                      band_name=None, max_frames=_MAX_GIF_FRAMES,
                      crs=_DEFAULT_CRS, transform=None, scale=None):
    """Get an animated GIF thumbnail URL for an ``ee.ImageCollection``.

    .. note::
        For tiled collections (LCMS, NLCD, etc.) this may produce blank
        frames.  Use :func:`generate_gif` instead, which properly mosaics
        per time step and supports date burn-in.

    Args:
        ee_obj: ``ee.ImageCollection``.
        geometry: ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.
        viz_params (dict, optional): Must include ``bands`` (3 for RGB, or
            1 + ``palette``).  Auto-detected if not provided.
        dimensions (int): Width in pixels.
        fps (int): Frames per second.  Default 2.
        band_name (str, optional): Band to visualize (for auto_viz).
        max_frames (int): Maximum frames to include.  Default 40.
        crs (str, optional): CRS code (e.g. ``"EPSG:4326"``).
        transform (list, optional): Affine transform.  Requires ``crs``.
        scale (float, optional): Nominal scale in meters.  Requires ``crs``.

    Returns:
        str: Animated GIF thumbnail URL.

    Raises:
        ValueError: If ``transform`` or ``scale`` is provided without ``crs``.
    """
    _validate_projection_params(crs, transform, scale)
    col = ee.ImageCollection(ee_obj)

    if viz_params is None:
        viz_params = auto_viz(col, band_name=band_name)

    # Mosaic per time step to handle tiled collections
    if geometry is not None:
        geom = _to_geometry(geometry)
        col = col.filterBounds(geom)

    col = _mosaic_by_date(col)
    col = _apply_projection_to_collection(col, crs, transform, scale)

    # Clip each frame to the geometry
    if geometry is not None:
        if clip_to_geometry:
            col = col.map(lambda img: img.clip(geom).copyProperties(img, ["system:time_start"]))

    params = {
        **viz_params,
        "dimensions": dimensions,
        "framesPerSecond": fps,
    }

    if geometry is not None:
        params["region"] = geom

    count = col.size().getInfo()
    if count > max_frames:
        col = col.limit(max_frames)

    return col.getVideoThumbURL(params)


def get_filmstrip_url(ee_obj, geometry=None, viz_params=None,
                      dimensions=_DEFAULT_DIMENSIONS, band_name=None,
                      max_frames=_MAX_GIF_FRAMES,
                      crs=_DEFAULT_CRS, transform=None, scale=None):
    """Get a filmstrip thumbnail URL — all frames side-by-side in one PNG.

    Args:
        ee_obj: ``ee.ImageCollection``.
        geometry: Clip region.
        viz_params (dict, optional): Auto-detected if not provided.
        dimensions (int): Width per frame.
        band_name (str, optional): Band to visualize.
        max_frames (int): Maximum frames.
        crs (str, optional): CRS code (e.g. ``"EPSG:4326"``).
        transform (list, optional): Affine transform.  Requires ``crs``.
        scale (float, optional): Nominal scale in meters.  Requires ``crs``.

    Returns:
        str: Filmstrip PNG thumbnail URL.

    Raises:
        ValueError: If ``transform`` or ``scale`` is provided without ``crs``.
    """
    _validate_projection_params(crs, transform, scale)
    col = ee.ImageCollection(ee_obj)

    if viz_params is None:
        viz_params = auto_viz(col, band_name=band_name)

    if geometry is not None:
        geom = _to_geometry(geometry)
        col = col.filterBounds(geom)

    col = _mosaic_by_date(col)
    col = _apply_projection_to_collection(col, crs, transform, scale)

    # Clip each frame to the geometry
    if geometry is not None:
        if clip_to_geometry:
            col = col.map(lambda img: img.clip(geom).copyProperties(img, ["system:time_start"]))

    count = col.size().getInfo()
    if count > max_frames:
        col = col.limit(max_frames)

    params = {**viz_params, "format": "png"}

    if geometry is not None:
        params["region"] = geom

    return col.getFilmstripThumbURL(params)


# ---------------------------------------------------------------------------
#  Animated GIF with date burn-in
# ---------------------------------------------------------------------------
def generate_gif(ee_obj, geometry, viz_params=None, band_name=None,
                 dimensions=_DEFAULT_DIMENSIONS, fps=_DEFAULT_FPS,
                 max_frames=_MAX_GIF_FRAMES,
                 burn_in_date=True, date_format="YYYY",
                 date_position="upper-left", date_font_size=None,
                 burn_in_legend=True, legend_scale=1.0,
                 bg_color=None, font_color=None,
                 font_outline_color=None, output_path=None,
                 crs=_DEFAULT_CRS, transform=None, scale=None,
                 margin=_DEFAULT_MARGIN, basemap=None,
                 overlay_opacity=None, scalebar=True,
                 scalebar_units="metric", north_arrow=True,
                 north_arrow_style="solid",
                 inset_map=True, inset_basemap=None, inset_scale=0.3,
                 inset_on_map=True, title=None,
                 title_font_size=_DEFAULT_TITLE_FONT_SIZE,
                 label_font_size=_DEFAULT_LABEL_FONT_SIZE,
                 burn_in_geometry=False, geometry_outline_color=None, geometry_fill_color=None, geometry_outline_weight=2,
                 clip_to_geometry=True):
    """Generate an animated GIF from an Earth Engine ImageCollection.

    Downloads individual frame thumbnails, properly mosaics **tiled
    collections** (LCMS, NLCD, etc.) by time step, and composites them
    into an animated GIF.  Optional cartographic elements include date
    burn-in, thematic legend panel, basemap underlay, scalebar, north
    arrow, inset overview map, and title strip.

    Args:
        ee_obj (ee.ImageCollection): Image collection to animate.
        geometry (ee.Geometry or ee.Feature or ee.FeatureCollection):
            Region to clip and bound each frame.
        viz_params (dict, optional): Visualization parameters (``bands``,
            ``min``, ``max``, ``palette``).  Auto-detected via
            :func:`auto_viz` when ``None``.  Defaults to ``None``.
        band_name (str, optional): Band to visualize when using
            auto-detection.  Defaults to ``None`` (first band).
        dimensions (int, optional): Width of each frame in pixels.
            Defaults to ``640``.
        fps (int, optional): Frames per second in the output GIF.
            Defaults to ``2``.
        max_frames (int, optional): Maximum number of frames to include.
            Defaults to ``50``.
        burn_in_date (bool, optional): Burn the date label from
            ``system:time_start`` into each frame.  Defaults to ``True``.
        date_format (str, optional): Date format string.  Supported
            values include ``"YYYY"``, ``"YYYY-MM"``,
            ``"YYYY-MM-dd"``, ``"MMM YYYY"``, ``"MMMM YYYY"``,
            ``"MM/YYYY"``, ``"MM/dd/YYYY"``.  Defaults to ``"YYYY"``.
        date_position (str, optional): Position of the date label on
            each frame -- ``"upper-left"``, ``"upper-right"``,
            ``"lower-left"``, or ``"lower-right"``.
            Defaults to ``"upper-left"``.
        date_font_size (int, optional): Font size in pixels for the
            date label.  Auto-scaled from ``dimensions`` when ``None``.
            Defaults to ``None``.
        burn_in_legend (bool, optional): Append a legend panel to the
            right side of each frame for thematic data.  Only rendered
            when class names and palette are available in image
            properties.  Defaults to ``True``.
        legend_scale (float, optional): Scale multiplier for the legend
            panel size.  Defaults to ``1.0``.
        bg_color (str or None, optional): Background color for
            transparent areas, legend panel, and margins.  Accepts CSS
            color names or hex strings.  Resolved via theme when
            ``None``.  Defaults to ``None``.
        font_color (str or tuple or None, optional): Text color for
            date labels and legend text.  Resolved via theme when
            ``None``.  Defaults to ``None``.
        font_outline_color (str or tuple or None, optional): Outline /
            halo color for text readability.  Auto-derived to contrast
            with ``font_color`` when ``None``.  Defaults to ``None``.
        output_path (str, optional): File path to save the GIF to disk.
            Parent directories are created automatically.
            Defaults to ``None`` (not saved).
        crs (str, optional): CRS code (e.g. ``"EPSG:4326"``).
            Applies ``setDefaultProjection`` to each frame.
            Defaults to ``None``.
        transform (list, optional): Affine transform as a 6-element
            list.  Requires ``crs``.  Defaults to ``None``.
        scale (float, optional): Nominal pixel scale in meters.
            Requires ``crs``.  Defaults to ``None``.
        margin (int, optional): Pixel margin on all sides of each
            frame.  Defaults to ``16``.
        basemap (str or dict or None, optional): Basemap to composite
            behind the EE data.  A preset name (e.g.
            ``"esri-satellite"``, ``"usfs-topo"``), a config dict with
            ``type`` and ``url`` keys, or a raw tile URL template.
            Defaults to ``None`` (no basemap).
        overlay_opacity (float or None, optional): Opacity of the EE
            overlay when a basemap is present (0.0 -- 1.0).  Defaults
            to ``None`` (auto: ``0.8`` with basemap, ``1.0`` without).
        scalebar (bool, optional): Draw a scalebar on each frame.
            Only rendered when ``basemap`` or ``inset_basemap`` is set
            and bounds are available.  Defaults to ``True``.
        scalebar_units (str, optional): Unit system for the scalebar --
            ``"metric"`` or ``"imperial"``.  Defaults to ``"metric"``.
        north_arrow (bool, optional): Draw a north arrow on each frame.
            Defaults to ``True``.
        north_arrow_style (str, optional): Arrow style -- ``"solid"``,
            ``"classic"``, or ``"outline"``.  Defaults to ``"solid"``.
        inset_map (bool, optional): Include an inset overview map.
            Defaults to ``True``.
        inset_basemap (str or dict or None, optional): Basemap for the
            inset.  Falls back to ``basemap`` when ``None``.
            Defaults to ``None``.
        inset_scale (float, optional): Relative height of the inset
            compared to the frame height.  Defaults to ``0.3``.
        inset_on_map (bool, optional): Place the inset directly on the
            map (lower-right) rather than below it.
            Defaults to ``True``.
        title (str, optional): Title text rendered as a strip above the
            GIF frames.  Defaults to ``None`` (no title).

    Returns:
        dict: A dictionary with the following keys:

        - ``"html"`` (str): HTML ``<figure>`` element containing the
          GIF as a base64-embedded ``<img>`` tag.
        - ``"gif_bytes"`` (bytes): Raw animated GIF byte data.

    Raises:
        ValueError: If ``transform`` or ``scale`` is provided without
            ``crs``.

    Example:
        >>> result = generate_gif(
        ...     lcms.select(["Land_Cover"]),
        ...     study_area,
        ...     burn_in_date=True,
        ...     date_format="YYYY",
        ...     basemap="esri-satellite",
        ...     title="LCMS Land Cover",
        ... )
        >>> gif_bytes = result["gif_bytes"]
        >>> html_snippet = result["html"]
    """
    _validate_projection_params(crs, transform, scale)
    col = ee.ImageCollection(ee_obj)
    geom = _to_geometry(geometry)

    viz_params = _complete_viz_params(viz_params, col, band_name=band_name, geometry=geometry)

    # Extract legend info (thematic or continuous)
    legend_info = None
    if burn_in_legend:
        legend_info = _extract_legend_info(col, band_name=band_name, viz_params=viz_params)

    # Resolve font colors early (needed for burn_in_geometry fallback)
    font_color, font_outline_color, theme, bg_color = _resolve_font_colors(
        bg_color, font_color, font_outline_color)

    # Filter to region, mosaic per time step, apply projection, and clip
    col = col.filterBounds(geom)
    col = _mosaic_by_date(col)
    col = _apply_projection_to_collection(col, crs, transform, scale)
    if clip_to_geometry:
        col = col.map(lambda img: img.clip(geom).copyProperties(img, ["system:time_start"]))

    # Burn in geometry boundary (pre-visualizes the collection)
    if burn_in_geometry:
        bounds = _get_bounds_4326(geom)
        gc = _resolve_geometry_color(geometry_outline_color, font_color, basemap, bounds)
        col = _paint_boundary(col, geom, gc, viz_params=viz_params, fill_color=geometry_fill_color, width=geometry_outline_weight, crs=crs)
        viz_params = {"min": 0, "max": 255}

    count = col.size().getInfo()
    if count > max_frames:
        col = col.limit(max_frames)
        count = max_frames

    if count == 0:
        return {"html": "<p>No images available for GIF.</p>", "gif_bytes": b""}

    # Always use the PIL path so we can return bytes
    pil_frames, date_labels = _download_frames(col, geom if clip_to_geometry else geom.bounds(), viz_params,
                                                dimensions, count, date_format)

    if not pil_frames:
        return {"html": "<p>Failed to generate GIF frames.</p>", "gif_bytes": b""}

    # Resolve overlay opacity: default 0.8 when basemap is set
    if overlay_opacity is None:
        overlay_opacity = 0.8 if basemap is not None else 1.0

    # Fetch basemap once for all frames (same geometry)
    basemap_img = None
    bounds = _get_bounds_4326(geom)
    if basemap is not None:
        if bounds is not None and pil_frames:
            fw, fh = pil_frames[0].size
            basemap_img = _fetch_basemap(bounds, fw, fh, basemap, crs=crs)

    # Auto-scale font size for date
    if date_font_size is None:
        date_font_size = label_font_size
    font = _get_font(date_font_size)

    # Build legend panel once (same for all frames)
    legend_panel = _build_legend_panel_from_info(
        legend_info, target_height=pil_frames[0].size[1],
        bg_color=bg_color, scale=legend_scale, font_color=font_color,
    )

    # Composite basemap (adds padding border) or add blank padding
    _has_inset_source = (basemap is not None or inset_basemap is not None)
    final_frames = []
    for i, frame in enumerate(pil_frames):
        if basemap_img is not None:
            frame = _composite_with_basemap(frame, basemap_img, overlay_opacity)
        else:
            frame = _add_thumb_padding(frame, bg_color=bg_color)
        if burn_in_date and i < len(date_labels) and date_labels[i]:
            _burn_in_text(frame, date_labels[i], date_position,
                          font_color, font_outline_color, font)
        # Resolve geometry colors for inset extent rectangle
        _gif_gc = gc if burn_in_geometry else (
            _resolve_geometry_color(geometry_outline_color, font_color, basemap, bounds)
            if geometry_outline_color else None)
        # Assemble with legend, inset, scalebar, north arrow, title
        frame, has_bottom = _assemble_with_cartography(
            frame, bounds,
            bg_color=bg_color, font_color=font_color,
            font_outline_color=font_outline_color,
            title=title,
            scalebar=scalebar if bounds is not None else False,
            scalebar_units=scalebar_units,
            north_arrow=north_arrow if bounds is not None else False,
            north_arrow_style=north_arrow_style,
            inset_map=inset_map if (_has_inset_source and bounds is not None) else False,
            inset_basemap=inset_basemap if inset_basemap else basemap,
            inset_scale=inset_scale, inset_on_map=inset_on_map,
            inset_rect_color=_gif_gc if _gif_gc is not None else None,
            inset_rect_fill_color=_hex_fill_to_rgba(geometry_fill_color) if geometry_fill_color else None,
            legend_panel=legend_panel, margin=margin, crs=crs,
        )
        mt = 0 if title else margin
        mb = margin // 3 if has_bottom else margin
        frame = _add_margin(frame, (mt, margin, mb, margin), bg_color=bg_color)
        final_frames.append(frame)

    gif_bytes = _frames_to_gif(final_frames, fps, bg_color=bg_color)

    if output_path:
        _write_bytes(output_path, gif_bytes)

    b64 = base64.b64encode(gif_bytes).decode("ascii")
    html = (
        f'<figure class="gif-container">'
        f'<img src="data:image/gif;base64,{b64}">'
        f'</figure>'
    )
    return {"html": html, "gif_bytes": gif_bytes}


# ---------------------------------------------------------------------------
#  Filmstrip: date-labeled grid of frames
# ---------------------------------------------------------------------------
def generate_filmstrip(ee_obj, geometry, viz_params=None, band_name=None,
                       dimensions=_DEFAULT_DIMENSIONS,
                       max_frames=_MAX_GIF_FRAMES,
                       columns=3, date_format="YYYY",
                       burn_in_legend=True, legend_scale=1.0,
                       legend_position="bottom",
                       bg_color=None, font_color=None,
                       font_outline_color=None, output_path=None,
                       crs=_DEFAULT_CRS, transform=None, scale=None,
                       margin=_DEFAULT_MARGIN, basemap=None,
                       overlay_opacity=None, scalebar=True,
                       scalebar_units="metric", north_arrow=True,
                       north_arrow_style="solid",
                       inset_map=True, inset_basemap=None, inset_scale=0.3,
                       inset_on_map=False, title=None,
                       burn_in_geometry=False, geometry_outline_color=None, geometry_fill_color=None, geometry_outline_weight=2,
                       clip_to_geometry=True,
                       geometry_legend_label="Study Area",
                       title_font_size=_DEFAULT_TITLE_FONT_SIZE,
                       label_font_size=_DEFAULT_LABEL_FONT_SIZE):
    """Generate a filmstrip grid image from an Earth Engine ImageCollection.

    Downloads individual frame thumbnails, mosaics tiled collections by
    date, labels each frame with its date, and arranges them in a grid
    layout.  Optionally composites a basemap behind the EE data and
    appends cartographic elements including a legend panel, scalebar,
    north arrow, inset overview map, and title strip.

    Args:
        ee_obj (ee.ImageCollection): Image collection to render.
        geometry (ee.Geometry or ee.Feature or ee.FeatureCollection):
            Region to clip and bound each frame.
        viz_params (dict, optional): Visualization parameters (``bands``,
            ``min``, ``max``, ``palette``).  Auto-detected via
            :func:`auto_viz` when ``None``.  Defaults to ``None``.
        band_name (str, optional): Band to visualize when using
            auto-detection.  Defaults to ``None`` (first band).
        dimensions (int, optional): Width per frame in pixels.
            Defaults to ``640``.
        max_frames (int, optional): Maximum number of frames to include
            in the grid.  Defaults to ``50``.
        columns (int, optional): Number of columns in the grid layout.
            Defaults to ``3``.
        date_format (str, optional): Date label format above each frame.
            Supports ``"YYYY"``, ``"YYYY-MM"``, ``"YYYY-MM-dd"``,
            ``"MMM YYYY"``, etc.  Defaults to ``"YYYY"``.
        burn_in_legend (bool, optional): Append a legend panel for
            thematic data.  Only rendered when class names and palette
            are available.  Defaults to ``True``.
        legend_scale (float, optional): Scale multiplier for legend
            size.  Defaults to ``1.0``.
        legend_position (str, optional): Where to place the legend
            relative to the grid -- ``"bottom"`` or ``"top"``.
            Defaults to ``"bottom"``.
        bg_color (str or None, optional): Background color for the grid,
            margins, and legend panel.  Resolved via theme when
            ``None``.  Defaults to ``None``.
        font_color (str or tuple or None, optional): Text color for
            date labels and legend text.  Resolved via theme when
            ``None``.  Defaults to ``None``.
        font_outline_color (str or tuple or None, optional): Outline /
            halo color for text readability.  Auto-derived when
            ``None``.  Defaults to ``None``.
        output_path (str, optional): File path to save the PNG.  Parent
            directories are created automatically.
            Defaults to ``None`` (not saved).
        crs (str, optional): CRS code (e.g. ``"EPSG:4326"``).
            Applies ``setDefaultProjection`` to each frame.
            Defaults to ``None``.
        transform (list, optional): Affine transform as a 6-element
            list.  Requires ``crs``.  Defaults to ``None``.
        scale (float, optional): Nominal pixel scale in meters.
            Requires ``crs``.  Defaults to ``None``.
        margin (int, optional): Pixel margin on all sides of the final
            image.  Defaults to ``16``.
        basemap (str or dict or None, optional): Basemap to composite
            behind each frame.  A preset name (e.g.
            ``"esri-satellite"``), a config dict, or a raw tile URL.
            Defaults to ``None`` (no basemap).
        overlay_opacity (float or None, optional): Opacity of the EE
            overlay when a basemap is present (0.0 -- 1.0).  Defaults
            to ``None`` (auto: ``0.8`` with basemap, ``1.0`` without).
        scalebar (bool, optional): Include a scalebar below the grid.
            Only rendered when cartographic context is available.
            Defaults to ``True``.
        scalebar_units (str, optional): Unit system for the scalebar --
            ``"metric"`` or ``"imperial"``.  Defaults to ``"metric"``.
        north_arrow (bool, optional): Include a north arrow below the
            grid.  Defaults to ``True``.
        north_arrow_style (str, optional): Arrow style -- ``"solid"``,
            ``"classic"``, or ``"outline"``.  Defaults to ``"solid"``.
        inset_map (bool, optional): Include an inset overview map below
            the grid.  Defaults to ``True``.
        inset_basemap (str or dict or None, optional): Basemap for the
            inset.  Falls back to ``basemap`` when ``None``.
            Defaults to ``None``.
        inset_scale (float, optional): Relative height of the inset
            compared to the frame height.  Defaults to ``0.3``.
        inset_on_map (bool, optional): Place the inset on the map
            rather than as a separate strip.  For filmstrips this
            controls positioning in the bottom strip area.
            Defaults to ``True``.
        title (str, optional): Title text rendered as a strip above the
            grid.  Defaults to ``None`` (no title).

    Returns:
        dict: A dictionary with the following keys:

        - ``"html"`` (str): HTML ``<figure>`` element containing the
          filmstrip as a base64-embedded PNG ``<img>`` tag.
        - ``"thumb_bytes"`` (bytes): Raw PNG byte data.

    Raises:
        ValueError: If ``transform`` or ``scale`` is provided without
            ``crs``.

    Example:
        >>> result = generate_filmstrip(
        ...     lcms.select(["Land_Cover"]),
        ...     study_area,
        ...     columns=4,
        ...     date_format="YYYY",
        ...     basemap="esri-satellite",
        ...     title="LCMS Land Cover Time Series",
        ... )
        >>> png_bytes = result["thumb_bytes"]
    """
    _validate_projection_params(crs, transform, scale)
    from PIL import Image, ImageDraw

    col = ee.ImageCollection(ee_obj)
    geom = _to_geometry(geometry)

    viz_params = _complete_viz_params(viz_params, col, band_name=band_name, geometry=geometry)

    legend_info = None
    if burn_in_legend:
        legend_info = _extract_legend_info(col, band_name=band_name, viz_params=viz_params)

    col = col.filterBounds(geom)
    col = _mosaic_by_date(col)
    col = _apply_projection_to_collection(col, crs, transform, scale)
    if clip_to_geometry:
        col = col.map(lambda img: img.clip(geom).copyProperties(img, ["system:time_start"]))

    # Resolve font/theme colors early (needed for legend, labels, dividers, boundary)
    font_color, font_outline_color, fs_theme, bg_color = _resolve_font_colors(
        bg_color, font_color, font_outline_color)

    # Burn in geometry boundary (pre-visualizes the collection)
    if burn_in_geometry:
        bounds = _get_bounds_4326(geom)
        gc = _resolve_geometry_color(geometry_outline_color, font_color, basemap, bounds)
        col = _paint_boundary(col, geom, gc, viz_params=viz_params, fill_color=geometry_fill_color, width=geometry_outline_weight, crs=crs)
        viz_params = {"min": 0, "max": 255}

    count = col.size().getInfo()
    if count > max_frames:
        col = col.limit(max_frames)
        count = max_frames

    if count == 0:
        return {"html": "<p>No images available.</p>", "thumb_bytes": b""}

    pil_frames, date_labels = _download_frames(col, geom if clip_to_geometry else geom.bounds(), viz_params,
                                                dimensions, count, date_format)

    # Resolve overlay opacity: default 0.8 when basemap is set
    if overlay_opacity is None:
        overlay_opacity = 0.8 if basemap is not None else 1.0

    # Fetch basemap once (same geometry for all frames) and composite
    bounds = _get_bounds_4326(geom)
    if basemap is not None and pil_frames:
        if bounds is not None:
            fw, fh = pil_frames[0].size
            basemap_img = _fetch_basemap(bounds, fw + 2 * _THUMB_PADDING, fh + 2 * _THUMB_PADDING, basemap, crs=crs)
            if basemap_img is not None:
                pil_frames = [_composite_with_basemap(f, basemap_img, overlay_opacity) for f in pil_frames]
            else:
                pil_frames = [_add_thumb_padding(f, bg_color=bg_color) for f in pil_frames]
    elif pil_frames:
        pil_frames = [_add_thumb_padding(f, bg_color=bg_color) for f in pil_frames]

    if not pil_frames:
        return {"html": "<p>Failed to download frames.</p>", "thumb_bytes": b""}

    # Draw scalebar + north arrow on the first frame
    if bounds is not None and (scalebar or north_arrow):
        _draw_scalebar_and_arrow_on_frame(
            pil_frames[0], bounds,
            scalebar=scalebar, north_arrow=north_arrow,
            north_arrow_style=north_arrow_style,
            font_color=font_color, contrast=font_outline_color,
            accent=fs_theme.accent,
            label_font_size=label_font_size,
            crs=crs,
        )

    # Resolve geometry colors for inset extent rectangle
    _fs_inset_gc = gc if burn_in_geometry else (
        _resolve_geometry_color(geometry_outline_color, font_color, basemap, bounds)
        if geometry_outline_color else None)
    _fs_inset_fill = _hex_fill_to_rgba(geometry_fill_color) if geometry_fill_color else None

    # Draw inset on the last frame (lower-right) only when inset_on_map
    if inset_map and inset_on_map and bounds is not None and len(pil_frames) > 0:
        _ib = inset_basemap if inset_basemap else basemap
        if _ib is not None:
            last_frame = pil_frames[-1]
            _fw, _fh = last_frame.size
            target_h = int(_fh * inset_scale)
            _fs_inset_kw = {}
            if _fs_inset_gc is not None:
                _fs_inset_kw["rect_color"] = _fs_inset_gc
            if _fs_inset_fill is not None:
                _fs_inset_kw["rect_fill_color"] = _fs_inset_fill
            inset_img = _build_inset_image(bounds, size=target_h, inset_basemap=_ib, **_fs_inset_kw)
            if inset_img is not None:
                src_w, src_h = inset_img.size
                aspect = src_w / src_h if src_h > 0 else 1.0
                iw = int(target_h * aspect)
                ih = target_h
                if iw > _fw // 3:
                    iw = _fw // 3
                    ih = int(iw / aspect)
                inset_resized = inset_img.resize((iw, ih), Image.LANCZOS)
                pad = max(4, _fw // 60)
                px = _fw - iw - pad
                py = _fh - ih - pad
                last_frame.paste(
                    inset_resized, (px, py),
                    inset_resized if inset_resized.mode == "RGBA" else None,
                )

    text_color = font_color
    panel_bg = _resolve_color(bg_color)

    fw, fh = pil_frames[0].size
    n_cols = min(columns, len(pil_frames))
    n_rows = -(-len(pil_frames) // n_cols)  # ceil division

    # Match label font size to legend font size for visual consistency
    if legend_info is not None and legend_info.get("type") == "thematic":
        n_classes = len(legend_info.get("class_names", []))
        est_grid_h = n_rows * fh
        lg_padding = max(6, int(8 * legend_scale))
        lg_usable = est_grid_h - 2 * lg_padding
        label_font_size = max(8, int(lg_usable / max(n_classes, 1) * 0.6 * legend_scale))
        label_font_size = min(label_font_size, int(16 * legend_scale))
    else:
        pass  # use provided label_font_size
    label_font = _get_font(label_font_size)
    label_h = label_font_size + 8

    cell_h = fh + label_h
    frame_gap = 3  # will be used in the loop below too
    grid_w = n_cols * fw + max(n_cols - 1, 0) * frame_gap
    grid_h = n_rows * cell_h

    # Build legend panel (placed to the right of the first row, aligned with frame)
    legend_panel_img = None
    if legend_info is not None:
        # Use frame height (fh) not cell_h, since legend starts at label_h offset
        legend_target_h = fh
        legend_panel_img = _build_legend_panel_from_info(
            legend_info, target_height=legend_target_h,
            bg_color=bg_color, scale=legend_scale, font_color=font_color,
        )

    # Build inset for right column (below legend) when inset_on_map is False
    inset_panel = None
    if inset_map and not inset_on_map and bounds is not None:
        _ib = inset_basemap if inset_basemap else basemap
        if _ib is not None:
            target_h = int(fh * 0.8)
            _fs_inset_kw2 = {}
            if _fs_inset_gc is not None:
                _fs_inset_kw2["rect_color"] = _fs_inset_gc
            if _fs_inset_fill is not None:
                _fs_inset_kw2["rect_fill_color"] = _fs_inset_fill
            inset_img = _build_inset_image(bounds, size=target_h, inset_basemap=_ib, **_fs_inset_kw2)
            if inset_img is not None:
                src_w, src_h = inset_img.size
                aspect = src_w / src_h if src_h > 0 else 1.0
                iw = int(target_h * aspect)
                ih = target_h
                inset_panel = inset_img.resize((iw, ih), Image.LANCZOS)

    # Divider line color + row padding
    divider_rgba = fs_theme.divider + (255,)
    row_pad = 4  # padding below frames before divider

    # Width: grid + legend/inset column (if present)
    legend_col_w = legend_panel_img.size[0] if legend_panel_img is not None else 0
    inset_col_w = 0
    if inset_panel is not None and n_rows == 1:
        # Single row: inset goes beside legend
        aspect = inset_panel.size[0] / inset_panel.size[1] if inset_panel.size[1] > 0 else 1.0
        inset_col_w = int(fh * aspect) + 8
    elif inset_panel is not None and n_rows > 1:
        # Multi-row: inset goes in same column, take the wider
        legend_col_w = max(legend_col_w, inset_panel.size[0] + 8)
    total_w = grid_w + legend_col_w + inset_col_w

    # Build per-row images (allows page breaks in PDF between rows)
    row_images = []
    row_h = cell_h + row_pad  # extra padding at bottom of each row

    for row_i in range(n_rows):
        is_last = (row_i == n_rows - 1)
        cur_h = cell_h if is_last else row_h  # no extra pad on last row
        row_img = Image.new("RGBA", (total_w, cur_h), panel_bg + (255,))
        row_draw = ImageDraw.Draw(row_img)
        for col_i in range(n_cols):
            idx = row_i * n_cols + col_i
            if idx >= len(pil_frames):
                break
            frame = pil_frames[idx]
            x = col_i * (fw + frame_gap)

            label = date_labels[idx] if idx < len(date_labels) else ""
            if label:
                bbox = row_draw.textbbox((0, 0), label, font=label_font)
                tw = bbox[2] - bbox[0]
                row_draw.text((x + (fw - tw) // 2, 3), label,
                              font=label_font, fill=text_color)

            row_img.paste(frame, (x, label_h))

        # Legend to the right of the first row, aligned with frame (below date label)
        if row_i == 0 and legend_panel_img is not None:
            lp_rgba = legend_panel_img.convert("RGBA")
            row_img.paste(lp_rgba, (grid_w, label_h), lp_rgba)

        # Inset in right column
        if row_i == 0 and inset_panel is not None and n_rows == 1:
            # Single row: place inset right of legend (extend right column)
            inset_pad_left = max(4, margin // 4)
            lp_w = legend_panel_img.size[0] if legend_panel_img is not None else 0
            ip_x = grid_w + lp_w + inset_pad_left
            # Scale inset to fit frame height
            ip = inset_panel
            target_h = fh
            aspect = ip.size[0] / ip.size[1] if ip.size[1] > 0 else 1.0
            iw = int(target_h * aspect)
            ip = ip.resize((iw, target_h), Image.LANCZOS)
            ip_rgba = ip.convert("RGBA")
            row_img.paste(ip_rgba, (ip_x, label_h), ip_rgba)
        elif row_i == 1 and inset_panel is not None and n_rows > 1:
            # Multi-row: place inset at row 1, aligned with frames
            inset_pad_left = max(4, margin // 4)
            avail_h = cur_h - label_h - 2
            ip = inset_panel
            if ip.size[1] > avail_h and avail_h > 20:
                aspect = ip.size[0] / ip.size[1]
                ip = ip.resize((int(avail_h * aspect), avail_h), Image.LANCZOS)
            if avail_h > 20:
                ip_rgba = ip.convert("RGBA")
                row_img.paste(ip_rgba, (grid_w + inset_pad_left, label_h), ip_rgba)

        # Horizontal divider between rows (with padding gap)
        if not is_last:
            y_line = cur_h - 1
            row_draw.line([(0, y_line), (total_w - 1, y_line)],
                          fill=divider_rgba, width=1)

        row_images.append(row_img)

    # Build combined grid for thumb_bytes
    total_h = sum(img.size[1] for img in row_images)
    grid = Image.new("RGBA", (total_w, total_h), panel_bg + (255,))
    y_offset = 0
    for row_img in row_images:
        grid.paste(row_img, (0, y_offset))
        y_offset += row_img.size[1]

    # Title strip (above grid) — font size = 1.5x the label/timestamp font
    bg_rgba = _resolve_color(bg_color) + (255,)
    if title:
        title_font = _get_font(title_font_size)
        tmp_d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        tb = tmp_d.textbbox((0, 0), title, font=title_font)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        title_pad = max(6, label_font_size // 2)
        strip_h = title_pad + th + title_pad
        title_strip = Image.new("RGBA", (total_w, strip_h), bg_rgba)
        td = ImageDraw.Draw(title_strip)
        tx = (total_w - tw) // 2
        td.text((tx, title_pad - tb[1]), title, font=title_font, fill=font_color)

        combined_h = title_strip.size[1] + grid.size[1]
        assembled = Image.new("RGBA", (total_w, combined_h), bg_rgba)
        assembled.paste(title_strip, (0, 0),
                       title_strip if title_strip.mode == "RGBA" else None)
        assembled.paste(grid, (0, title_strip.size[1]),
                       grid if grid.mode == "RGBA" else None)
        grid = assembled

    grid = _add_margin(grid, margin, bg_color=bg_color)
    rgb_grid = _rgba_to_rgb(grid, bg_color)
    buf = io.BytesIO()
    rgb_grid.save(buf, format="PNG")
    thumb_bytes = buf.getvalue()

    if output_path:
        _write_bytes(output_path, thumb_bytes)

    # Build HTML — single image for simplicity
    b64 = base64.b64encode(thumb_bytes).decode("ascii")
    html = (
        f'<figure class="filmstrip">'
        f'<img src="data:image/png;base64,{b64}" style="max-width:100%;">'
        f'</figure>'
    )

    return {"html": html, "thumb_bytes": thumb_bytes}


# ---------------------------------------------------------------------------
#  Shared frame download helper
# ---------------------------------------------------------------------------
def _download_frames(col, geom, viz_params, dimensions, count, date_format="YYYY"):
    """Download individual frames and extract date labels from a collection.

    Returns:
        tuple: ``(pil_frames, date_labels)`` — list of RGBA PIL Images and
        list of formatted date strings.
    """
    from datetime import datetime as dt
    from PIL import Image

    dates = col.aggregate_array("system:time_start").getInfo()
    py_fmt = _DATE_FORMAT_MAP.get(date_format, date_format)
    if "%" not in py_fmt:
        py_fmt = "%Y"
    date_labels = []
    for ts in dates:
        if ts is not None:
            date_labels.append(dt.fromtimestamp(ts / 1000).strftime(py_fmt))
        else:
            date_labels.append("")

    img_list = col.toList(count)
    frame_params = {**viz_params, "dimensions": dimensions, "format": "png",
                    "region": geom}

    def _get_frame(i):
        img = ee.Image(img_list.get(i))
        url = img.getThumbURL(frame_params)
        data = download_thumb(url)
        return i, data

    frames_data = [None] * count
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_get_frame, i) for i in range(count)]
        for f in concurrent.futures.as_completed(futures):
            idx, data = f.result()
            frames_data[idx] = data

    pil_frames = []
    for data in frames_data:
        if data is None:
            continue
        try:
            pil_frames.append(Image.open(io.BytesIO(data)).convert("RGBA"))
        except Exception:
            continue

    return pil_frames, date_labels


def _extract_legend_info(ee_obj, band_name=None, viz_params=None):
    """Extract legend info from an ee object — thematic or continuous.

    For **thematic** data (images with ``{band}_class_values`` and
    ``{band}_class_palette`` properties), returns a dict with
    ``class_names``, ``class_palette``, and ``"type": "thematic"``.

    For **continuous** single-band data where *viz_params* supplies a
    ``palette``, returns a dict with ``min``, ``max``, ``palette``,
    ``band_name``, and ``"type": "continuous"``.

    Returns ``None`` when no legend can be generated.
    """
    try:
        info = cl.get_obj_info(ee_obj, band_names=[band_name] if band_name else None)
    except Exception:
        info = None

    # --- Thematic path ---
    if info is not None and info.get("is_thematic"):
        band_names_list = info.get("band_names", [])
        if band_names_list:
            bn = band_names_list[0]
            ci = info.get("class_info", {}).get(bn, {})
            class_names = ci.get("class_names", [])
            class_palette = ci.get("class_palette", [])
            if class_names and class_palette:
                n = min(len(class_names), len(class_palette))
                return {
                    "type": "thematic",
                    "class_names": class_names[:n],
                    "class_palette": class_palette[:n],
                }

    # --- Fallback: pre-visualized RGB images with class properties ---
    # Check all image properties for *_class_names/*_class_palette patterns
    if info is None or not info.get("is_thematic"):
        try:
            sample = ee_obj
            if isinstance(ee_obj, ee.ImageCollection):
                sample = ee_obj.first()
            props = ee.Image(sample).getInfo().get("properties", {})
            for key in props:
                if key.endswith("_class_names"):
                    prefix = key.replace("_class_names", "")
                    cn = props.get(f"{prefix}_class_names", [])
                    cp = props.get(f"{prefix}_class_palette", [])
                    if cn and cp:
                        n = min(len(cn), len(cp))
                        return {
                            "type": "thematic",
                            "class_names": cn[:n],
                            "class_palette": cp[:n],
                        }
        except Exception:
            pass

    # --- Continuous path — single band + palette in viz_params ---
    if viz_params is not None:
        palette = viz_params.get("palette")
        bands = viz_params.get("bands", [])
        vmin = viz_params.get("min")
        vmax = viz_params.get("max")
        if palette and vmin is not None and vmax is not None:
            # Only generate for single-band (palette doesn't apply to RGB)
            if len(bands) <= 1:
                bn = bands[0] if bands else (band_name or "value")
                # Normalise min/max to scalar
                if isinstance(vmin, (list, tuple)):
                    vmin = vmin[0]
                if isinstance(vmax, (list, tuple)):
                    vmax = vmax[0]
                # Normalise palette to a list of color strings
                if isinstance(palette, str):
                    pal_list = [c.strip() for c in palette.split(",")]
                elif isinstance(palette, (list, tuple)):
                    pal_list = list(palette)
                else:
                    pal_list = [str(palette)]
                return {
                    "type": "continuous",
                    "min": vmin,
                    "max": vmax,
                    "palette": pal_list,
                    "band_name": bn,
                }

    return None


def _hex_to_rgb(hex_color):
    """Convert a hex or named color string to an (R, G, B) tuple."""
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) == 6:
        try:
            return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    # Fall back to _resolve_color for named colors
    try:
        return _resolve_color(hex_color)
    except Exception:
        return (128, 128, 128)


def _build_legend_panel(class_names, class_palette, target_height,
                         bg_color="black", scale=1.0, font_color=None):
    """Build a vertical legend panel image for thematic map data.

    Creates a PIL image with colored swatches and class labels arranged
    vertically, sized to sit alongside (or below) a map frame.  Font
    size is automatically calculated to fit all classes within the
    available height, capped at a readable maximum.

    Args:
        class_names (list[str]): Display names for each thematic class.
        class_palette (list[str]): Hex color strings (without ``#``
            prefix) corresponding to each class.
        target_height (int): Pixel height the panel must match, typically
            the height of the adjacent map frame.
        bg_color (str, optional): Background color name or hex string
            (e.g. ``"black"``, ``"white"``, ``"#1a1a2e"``).
            Defaults to ``"black"``.
        scale (float, optional): Multiplier for text and swatch size.
            Values greater than 1.0 enlarge the legend.
            Defaults to ``1.0``.
        font_color (tuple or None, optional): ``(R, G, B)`` text color.
            When ``None``, derived from the theme based on
            ``bg_color``.  Defaults to ``None``.

    Returns:
        PIL.Image.Image: RGB legend panel image with dimensions
        ``(auto_width, target_height)``.

    Example:
        >>> panel = _build_legend_panel(
        ...     ["Forest", "Water", "Urban"],
        ...     ["228B22", "4682B4", "808080"],
        ...     target_height=400,
        ... )
        >>> panel.size[1]
        400
    """
    from PIL import Image, ImageDraw

    n_classes = len(class_names)
    theme = _get_theme(bg_color)
    panel_bg = _resolve_color(bg_color)

    text_color = font_color if font_color is not None else theme.text
    divider_color = theme.divider
    swatch_outline = theme.swatch_outline

    # Compute font size: fit all classes within target_height
    pad_left = max(4, int(6 * scale))  # left padding only
    usable_h = target_height  # no top/bottom padding
    # Each row: swatch + gap; font size drives row height
    base_font = max(8, int(usable_h / n_classes * 0.6 * scale)) if n_classes > 0 else 10
    # Cap at label_font_size from theme
    base_font = min(base_font, _DEFAULT_LABEL_FONT_SIZE)

    font = _get_font(base_font)
    swatch_size = max(6, base_font)

    # Measure text widths
    tmp_img = Image.new("RGB", (1, 1))
    tmp_draw = ImageDraw.Draw(tmp_img)
    text_widths = []
    for name in class_names:
        bbox = tmp_draw.textbbox((0, 0), name, font=font)
        text_widths.append(bbox[2] - bbox[0])

    max_text_w = max(text_widths) if text_widths else 40
    gap = max(4, int(4 * scale))
    panel_w = pad_left + swatch_size + gap + max_text_w + pad_left

    # Row height: distribute evenly across usable height
    row_height = usable_h / n_classes if n_classes > 0 else usable_h

    # Build panel
    panel = Image.new("RGB", (panel_w, target_height), panel_bg)
    draw = ImageDraw.Draw(panel)

    # Draw entries starting at top (no vertical padding)
    y_start = 0
    for i, (name, hex_col) in enumerate(zip(class_names, class_palette)):
        rgb = _hex_to_rgb(hex_col)
        row_y = y_start + int(i * row_height)
        # Center swatch + text vertically within the row
        center_y = row_y + int(row_height / 2)

        # Color swatch
        sx = pad_left
        sy = center_y - swatch_size // 2
        draw.rounded_rectangle(
            [(sx, sy), (sx + swatch_size - 1, sy + swatch_size - 1)],
            radius=max(1, swatch_size // 5),
            fill=rgb,
            outline=swatch_outline,
            width=1,
        )

        # Text label — vertically centered on same center_y as swatch
        tx = sx + swatch_size + gap
        bbox = draw.textbbox((0, 0), name, font=font)
        # bbox[1] is the top offset from the anchor; account for it
        # so the visual center of the text aligns with center_y
        ty = center_y - (bbox[1] + bbox[3]) // 2
        draw.text((tx, ty), name, font=font, fill=text_color)

    return panel


def _build_continuous_legend_panel(vmin, vmax, palette, target_height,
                                    band_name="", bg_color="black",
                                    scale=1.0, font_color=None, n_ticks=5):
    """Build a vertical gradient colorbar panel for continuous data.

    Creates a PIL image with a smooth vertical gradient derived from
    ``palette`` colours, with evenly-spaced numeric tick labels running
    from ``vmax`` (top) to ``vmin`` (bottom).

    Args:
        vmin (float): Minimum value at the bottom of the bar.
        vmax (float): Maximum value at the top of the bar.
        palette (list[str]): Hex colour strings (without ``#``) defining
            the gradient from low to high.
        target_height (int): Pixel height the panel must match.
        band_name (str, optional): Band label drawn above the bar.
        bg_color (str, optional): Background colour.  Defaults to
            ``"black"``.
        scale (float, optional): Size multiplier.  Defaults to ``1.0``.
        font_color (tuple or None, optional): ``(R, G, B)`` text colour.
        n_ticks (int, optional): Number of tick labels.  Defaults to 5.

    Returns:
        PIL.Image.Image: RGB legend panel image.
    """
    from PIL import Image, ImageDraw

    theme = _get_theme(bg_color)
    panel_bg = _resolve_color(bg_color)
    text_color = font_color if font_color is not None else theme.text
    swatch_outline = theme.swatch_outline

    padding = max(8, int(10 * scale))
    base_font = max(9, int(12 * scale))
    font = _get_font(base_font)

    # Measure tick label width
    tmp = Image.new("RGB", (1, 1))
    tmp_d = ImageDraw.Draw(tmp)

    def _fmt(v):
        if abs(v) >= 1000:
            return f"{v:.0f}"
        elif abs(v) >= 1:
            return f"{v:.1f}"
        else:
            return f"{v:.3f}"

    tick_vals = [vmin + (vmax - vmin) * i / max(n_ticks - 1, 1)
                 for i in range(n_ticks)]
    tick_labels = [_fmt(v) for v in tick_vals]
    max_tw = max(
        (tmp_d.textbbox((0, 0), t, font=font)[2] for t in tick_labels),
        default=30,
    )

    bar_w = max(12, int(16 * scale))
    tick_gap = max(4, int(6 * scale))
    panel_w = padding + bar_w + tick_gap + max_tw + padding

    # Band name above the bar — 1.15x the tick font size
    name_font_size = max(base_font, int(base_font * 1.15))
    name_font = _get_font(name_font_size)
    name_h = 0
    if band_name:
        nb = tmp_d.textbbox((0, 0), band_name, font=name_font)
        name_w = nb[2] - nb[0]
        name_h = (nb[3] - nb[1]) + padding
        # Widen panel if band name is wider than bar + ticks
        panel_w = max(panel_w, padding + name_w + padding)

    bar_top = padding + name_h
    bar_bottom = target_height - padding
    bar_h = max(bar_bottom - bar_top, 20)

    panel = Image.new("RGB", (panel_w, target_height), panel_bg)
    draw = ImageDraw.Draw(panel)

    # Draw band name
    if band_name:
        draw.text((padding, padding), band_name, font=name_font, fill=text_color)

    # Build gradient column — interpolate palette colours
    pal_rgb = [_hex_to_rgb(c) for c in palette]
    n_colors = len(pal_rgb)
    for py in range(bar_h):
        # py=0 is top (max), py=bar_h-1 is bottom (min)
        frac = 1.0 - py / max(bar_h - 1, 1)  # 0 at bottom, 1 at top
        # Map frac to palette index
        idx_f = frac * (n_colors - 1)
        lo = int(idx_f)
        hi = min(lo + 1, n_colors - 1)
        t = idx_f - lo
        r = int(pal_rgb[lo][0] * (1 - t) + pal_rgb[hi][0] * t)
        g = int(pal_rgb[lo][1] * (1 - t) + pal_rgb[hi][1] * t)
        b = int(pal_rgb[lo][2] * (1 - t) + pal_rgb[hi][2] * t)
        draw.line(
            [(padding, bar_top + py), (padding + bar_w - 1, bar_top + py)],
            fill=(r, g, b),
        )

    # Bar outline
    draw.rectangle(
        [(padding, bar_top), (padding + bar_w - 1, bar_top + bar_h - 1)],
        outline=swatch_outline, width=1,
    )

    # Tick labels (evenly spaced, top = max, bottom = min)
    tx = padding + bar_w + tick_gap
    for i in range(n_ticks):
        # i=0 → min (bottom), i=n_ticks-1 → max (top)
        frac = i / max(n_ticks - 1, 1)
        py = bar_top + int((1.0 - frac) * (bar_h - 1))
        label = tick_labels[i]
        tb = draw.textbbox((0, 0), label, font=font)
        th = tb[3] - tb[1]
        draw.text((tx, py - th // 2), label, font=font, fill=text_color)
        # Small tick mark
        draw.line(
            [(padding + bar_w - 3, py), (padding + bar_w, py)],
            fill=swatch_outline, width=1,
        )

    return panel


def _build_legend_panel_from_info(legend_info, target_height,
                                   bg_color="black", scale=1.0,
                                   font_color=None):
    """Build the appropriate legend panel from a legend_info dict.

    Dispatches to :func:`_build_legend_panel` for thematic data or
    :func:`_build_continuous_legend_panel` for continuous data based
    on ``legend_info["type"]``.

    Returns ``None`` if ``legend_info`` is ``None``.
    """
    if legend_info is None:
        return None

    from PIL import Image as _PILImage, ImageDraw as _PILDraw

    # Build geometry swatch row if present (prepended above the main legend)
    geom_swatch = legend_info.get("geometry_swatch")
    geom_row = None
    geom_row_h = 0
    if geom_swatch:
        theme = _get_theme(bg_color)
        text_color = font_color if font_color is not None else theme.text
        font = _get_font(_DEFAULT_LABEL_FONT_SIZE)
        swatch_sz = max(8, _DEFAULT_LABEL_FONT_SIZE)
        pad_left = max(4, int(6 * scale))
        gap = 4
        geom_row_h = int(_DEFAULT_LABEL_FONT_SIZE * 2)

        outline_rgb = _hex_to_rgb(geom_swatch["outline_hex"])
        # Parse fill: may be None, or hex like "FFFFFF33" (RRGGBBAA with alpha)
        fill_hex = geom_swatch.get("fill_hex")
        bg_rgb = _resolve_color(bg_color)
        if fill_hex and len(fill_hex) >= 6:
            fill_rgb = _hex_to_rgb(fill_hex[:6])
            # Extract alpha if present (last 2 hex chars), default fully opaque
            fill_alpha = int(fill_hex[6:8], 16) if len(fill_hex) >= 8 else 255
            # Alpha-blend fill over background for the swatch preview
            a = fill_alpha / 255.0
            fill_blended = tuple(int(f * a + b * (1 - a)) for f, b in zip(fill_rgb, bg_rgb))
        else:
            fill_blended = bg_rgb  # match panel bg

        # Measure label width
        tmp_d = _PILDraw.Draw(_PILImage.new("RGB", (1, 1)))
        lbb = tmp_d.textbbox((0, 0), geom_swatch["label"], font=font)
        label_w = lbb[2] - lbb[0]
        row_w = pad_left + swatch_sz + gap + label_w + pad_left

        geom_row = _PILImage.new("RGB", (row_w, geom_row_h), bg_rgb)
        rd = _PILDraw.Draw(geom_row)
        cy = geom_row_h // 2
        # Draw swatch: alpha-blended fill inside, outline border
        sx, sy = pad_left, cy - swatch_sz // 2
        rd.rectangle(
            [(sx, sy), (sx + swatch_sz - 1, sy + swatch_sz - 1)],
            fill=fill_blended,
            outline=outline_rgb,
            width=2,
        )
        tbb = rd.textbbox((0, 0), geom_swatch["label"], font=font)
        ty = cy - (tbb[1] + tbb[3]) // 2
        rd.text((pad_left + swatch_sz + gap, ty), geom_swatch["label"],
                font=font, fill=text_color)

    if legend_info.get("type") == "continuous":
        colorbar_h = target_height - geom_row_h

        panel = _build_continuous_legend_panel(
            legend_info["min"],
            legend_info["max"],
            legend_info["palette"],
            target_height=max(colorbar_h, 40),
            band_name=legend_info.get("band_name", ""),
            bg_color=bg_color,
            scale=scale,
            font_color=font_color,
        )

        # Prepend geometry swatch above colorbar
        if geom_row is not None and panel is not None:
            pw = max(panel.size[0], geom_row.size[0])
            combined = _PILImage.new("RGB", (pw, geom_row_h + panel.size[1]),
                                      _resolve_color(bg_color))
            combined.paste(geom_row, (0, 0))
            combined.paste(panel, (0, geom_row_h))
            panel = combined

        return panel

    # thematic (default)
    # thematic (default)
    thematic_h = target_height - geom_row_h
    panel = _build_legend_panel(
        legend_info["class_names"],
        legend_info["class_palette"],
        target_height=max(thematic_h, 20),
        bg_color=bg_color,
        scale=scale,
        font_color=font_color,
    )

    # Prepend geometry swatch above thematic legend
    if geom_row is not None and panel is not None:
        pw = max(panel.size[0], geom_row.size[0])
        combined = _PILImage.new("RGB", (pw, geom_row_h + panel.size[1]),
                                  _resolve_color(bg_color))
        combined.paste(geom_row, (0, 0))
        combined.paste(panel, (0, geom_row_h))
        return combined

    return panel


def _build_horizontal_legend(class_names, class_palette, width,
                             bg_color="black", font_color=None, scale=1.0):
    """Build a full-width horizontal legend with wrapping rows of swatches.

    Arranges coloured swatches and labels in rows that fill the given
    *width*, wrapping to additional rows as needed.

    Args:
        class_names (list[str]): Class display names.
        class_palette (list[str]): Hex colour strings (no ``#``).
        width (int): Target width in pixels.
        bg_color (str): Background colour.
        font_color (tuple or None): ``(R, G, B)`` text colour.
        scale (float): Size multiplier.

    Returns:
        PIL.Image.Image: RGBA image spanning *width* pixels wide.
    """
    from PIL import Image, ImageDraw

    theme = _get_theme(bg_color)
    panel_bg = _resolve_color(bg_color) + (255,)
    text_color = font_color if font_color is not None else theme.text
    swatch_outline = theme.swatch_outline

    font_size = max(9, int(11 * scale))
    font = _get_font(font_size)
    swatch_sz = max(8, font_size)
    gap = max(4, int(5 * scale))
    item_gap = max(10, int(14 * scale))
    pad = max(6, int(8 * scale))

    # Measure each item width
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    items = []
    for name, hex_col in zip(class_names, class_palette):
        bbox = tmp.textbbox((0, 0), name, font=font)
        tw = bbox[2] - bbox[0]
        item_w = swatch_sz + gap + tw
        items.append((name, hex_col, item_w))

    # Layout into rows
    usable_w = width - 2 * pad
    rows = []
    cur_row = []
    cur_w = 0
    for name, hex_col, item_w in items:
        needed = item_w + (item_gap if cur_row else 0)
        if cur_row and cur_w + needed > usable_w:
            rows.append(cur_row)
            cur_row = [(name, hex_col, item_w)]
            cur_w = item_w
        else:
            cur_row.append((name, hex_col, item_w))
            cur_w += needed
    if cur_row:
        rows.append(cur_row)

    row_h = swatch_sz + pad
    total_h = pad + len(rows) * row_h + pad

    panel = Image.new("RGBA", (width, total_h), panel_bg)
    draw = ImageDraw.Draw(panel)

    for ri, row in enumerate(rows):
        # Centre the row
        total_row_w = sum(iw for _, _, iw in row) + item_gap * (len(row) - 1)
        x = (width - total_row_w) // 2
        y = pad + ri * row_h

        for name, hex_col, item_w in row:
            rgb = _hex_to_rgb(hex_col)
            # Swatch
            draw.rounded_rectangle(
                [(x, y), (x + swatch_sz - 1, y + swatch_sz - 1)],
                radius=max(1, swatch_sz // 5), fill=rgb, outline=swatch_outline, width=1,
            )
            # Label
            bbox = draw.textbbox((0, 0), name, font=font)
            ty = y + (swatch_sz - (bbox[3] - bbox[1])) // 2 - bbox[1]
            draw.text((x + swatch_sz + gap, ty), name, font=font, fill=text_color)
            x += item_w + item_gap

    return panel


def _extend_frame_with_legend(frame, legend_panel, bg_color="black"):
    """Create a new image with the frame on the left and legend on the right.

    Args:
        frame (PIL.Image.Image): The map frame (RGBA or RGB).
        legend_panel (PIL.Image.Image): The legend panel (RGB), same height.
        bg_color (str): Background color for the combined canvas.

    Returns:
        PIL.Image.Image: New RGBA image with frame + legend side by side.
    """
    from PIL import Image
    fw, fh = frame.size
    lw, lh = legend_panel.size
    bg_rgb = _resolve_color(bg_color)
    fill = bg_rgb + (255,)
    combined = Image.new("RGBA", (fw + lw, max(fh, lh)), fill)
    combined.paste(frame, (0, 0))
    combined.paste(legend_panel.convert("RGBA"), (fw, 0))
    return combined


def _burn_legend_into_url(url, legend_info, bg_color="black", scale=1.0):
    """Download a thumbnail, extend it with a legend panel, return as base64.

    Args:
        url (str): Thumbnail URL.
        legend_info (dict): Dict with ``class_names`` and ``class_palette``.
        bg_color (str): Background color for the legend panel.
        scale (float): Legend scale factor.

    Returns:
        str: Base64 data URI of the modified PNG.
    """
    from PIL import Image

    data = download_thumb(url)
    frame = Image.open(io.BytesIO(data)).convert("RGBA")

    legend_panel = _build_legend_panel_from_info(
        legend_info, target_height=frame.size[1],
        bg_color=bg_color, scale=scale,
    )
    if legend_panel is None:
        return url  # No legend to burn in
    combined = _extend_frame_with_legend(frame, legend_panel, bg_color=bg_color)

    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _get_font(size):
    """Try to load a TrueType font, falling back to default."""
    from PIL import ImageFont
    # Try common system font paths
    font_candidates = [
        "arial.ttf", "Arial.ttf",
        "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            continue
    # Fallback to default
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _burn_in_text(frame, text, position, color, outline_color, font):
    """Draw text with outline onto a PIL Image frame."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(frame)
    w, h = frame.size

    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # Calculate position
    margin = max(8, w // 40)
    if position == "upper-left":
        x, y = margin, margin
    elif position == "upper-right":
        x, y = w - tw - margin, margin
    elif position == "lower-left":
        x, y = margin, h - th - margin
    elif position == "lower-right":
        x, y = w - tw - margin, h - th - margin
    else:
        x, y = margin, margin

    # Draw outline/shadow for readability
    outline_width = max(1, font.size // 12) if hasattr(font, 'size') else 1
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)

    # Draw main text
    draw.text((x, y), text, font=font, fill=color)


def generate_map_chart(
    ee_obj,
    geometry,
    viz_params=None,
    band_name=None,
    dimensions=_DEFAULT_DIMENSIONS,
    bg_color=None,
    font_color=None,
    font_outline_color=None,
    output_path=None,
    crs=_DEFAULT_CRS,
    transform=None,
    scale=None,
    margin=_DEFAULT_MARGIN,
    basemap=None,
    overlay_opacity=None,
    scalebar=True,
    scalebar_units="metric",
    north_arrow=True,
    north_arrow_style="solid",
    inset_map=True,
    inset_basemap=None,
    inset_scale=0.25,
    title=None,
    # Chart params
    chart_type=None,
    chart_scale=30,
    area_format="Percentage",
    chart_height=None,
    legend_position="right",
    include_masked_area=True,
    burn_in_geometry=True,
    burn_in_legend=True,
    title_font_size=_DEFAULT_TITLE_FONT_SIZE,
    label_font_size=_DEFAULT_LABEL_FONT_SIZE,
    geometry_outline_color=None,
    geometry_fill_color=None,
    geometry_outline_weight=2,
    clip_to_geometry=True,
    # Multi-feature params
    feature_label=None,
    columns=2,
    thumb_width=None,
    # Scatter params
    band_names=None,
    thematic_band_name=None,
    opacity=0.7,
    # Layout
    layout="side-by-side",
):
    """Generate a combined map + chart output.

    For ``ee.Image`` inputs, produces a static PNG with a map thumbnail
    beside (or above) a chart.  For ``ee.ImageCollection`` inputs,
    automatically delegates to :func:`generate_map_chart_gif` and
    returns an animated GIF with cumulative time-series charts.

    The title appears once on the combined output — the chart itself
    has no title.  For thematic data the legend appears on the map
    thumbnail only (not duplicated on the chart).

    Supports:

    - **ee.Image + single geometry** (``ee.Geometry`` / ``ee.Feature``)
      with thematic data -> map + bar or donut chart
    - **ee.Image + single geometry** with continuous data -> map +
      horizontal bar chart of band means
    - **ee.Image + multi-feature** ``ee.FeatureCollection`` with
      thematic data -> per-feature map grid + grouped/stacked bar or
      per-feature donut chart
    - **ee.Image + multi-feature FC** with ``chart_type="scatter"``
      -> map of bounding region with sample points burned in +
      scatter plot (optionally coloured by *thematic_band_name*)
    - **ee.ImageCollection + any geometry** -> delegates to
      :func:`generate_map_chart_gif`, returning ``gif_bytes``

    Args:
        ee_obj: ``ee.Image`` or ``ee.ImageCollection``.
        geometry: ``ee.Geometry``, ``ee.Feature``, or
            ``ee.FeatureCollection``.
        viz_params (dict, optional): Visualization parameters for the
            map thumbnail.  Auto-detected via :func:`auto_viz` when
            ``None``.
        band_name (str, optional): Band to visualize on the map.
        dimensions (int, optional): Map thumbnail width in pixels.
            Defaults to ``640``.
        bg_color (str, optional): Background colour.  Dark theme when
            ``None``.
        font_color (str or tuple, optional): Font colour override.
        font_outline_color (str or tuple, optional): Font outline.
        output_path (str, optional): Save output to this path.
        crs (str, optional): Output CRS (e.g. ``"EPSG:5070"``).
            Defaults to ``"EPSG:3857"``.
        transform (list, optional): CRS transform.
        scale (int, optional): Pixel scale in metres.
        margin (int, optional): Margin around the output in pixels.
        basemap (str or dict, optional): Basemap preset name
            (e.g. ``"esri-satellite"``) or config dict.
        overlay_opacity (float, optional): Opacity of EE data over
            basemap.  Default ``0.8`` when basemap is set.
        scalebar (bool, optional): Draw scalebar.  Defaults to ``True``.
        scalebar_units (str, optional): ``"metric"`` or ``"imperial"``.
        north_arrow (bool, optional): Draw north arrow.  Defaults to
            ``True``.
        north_arrow_style (str, optional): Arrow style.
        inset_map (bool, optional): Show inset overview map.
        inset_basemap: Basemap for inset.
        inset_scale (float, optional): Inset size as fraction of frame.
        title (str, optional): Title displayed once above the combined
            map + chart output.
        chart_type (str, optional): ``"bar"`` (default for Image),
            ``"stacked_bar"``, ``"donut"``, ``"scatter"``, or any
            time-series type (``"line+markers"``, etc.).  ``None``
            auto-detects: ``"bar"`` for Image, ``"line+markers"``
            for ImageCollection.
        chart_scale (int, optional): Scale in metres for zonal stats
            ``reduceRegion``.  Defaults to ``30``.
        area_format (str, optional): ``"Percentage"`` (default),
            ``"Hectares"``, ``"Acres"``, or ``"Pixels"``.
        chart_height (int, optional): Chart height in pixels.  Defaults
            to map height for side-by-side, map width for stacked.
        legend_position (str or dict, optional): Chart legend position.
            Suppressed automatically for thematic data when
            ``burn_in_legend=True`` (legend on thumb only).
        include_masked_area (bool, optional): Include masked pixels in
            area totals.  Defaults to ``True``.
        burn_in_geometry (bool, optional): Paint geometry boundary on
            map frames.  Defaults to ``True``.
        burn_in_legend (bool, optional): Add legend panel to the map
            thumbnail.  Defaults to ``True``.
        title_font_size (int, optional): Title font size.  Default 18.
        label_font_size (int, optional): Label font size.  Default 12.
        geometry_outline_color (str, optional): Boundary colour.
        geometry_fill_color (str, optional): Boundary fill (hex+alpha).
        geometry_outline_weight (int, optional): Boundary width.
        clip_to_geometry (bool, optional): Mask data outside boundary.
        feature_label (str, optional): FC property name for per-feature
            labels (multi-feature mode).
        columns (int, optional): Columns for multi-feature grid or
            multi-feature donut subplot layout.  Defaults to ``2``.
        thumb_width (int, optional): Per-feature thumbnail width.
        band_names (list[str], optional): Bands for scatter x/y axes.
            Uses first two image bands when ``None``.
        thematic_band_name (str, optional): Thematic band name for
            colouring scatter points by class.  The image must carry
            ``{band}_class_values/names/palette`` properties.
        opacity (float, optional): Point opacity for scatter charts.
            Defaults to ``0.7``.
        layout (str, optional): ``"side-by-side"`` (default) places the
            chart to the right of the map.  ``"stacked"`` places the
            chart below the map.

    Returns:
        dict: For ``ee.Image`` inputs:
            ``{"html": str, "thumb_bytes": bytes, "df": DataFrame,
            "fig": Figure}``.
            For ``ee.ImageCollection`` inputs (delegated to GIF):
            ``{"html": str, "gif_bytes": bytes}``.
    """
    from PIL import Image, ImageDraw

    _validate_projection_params(crs, transform, scale)

    # --- Auto-detect ImageCollection and delegate to GIF version ---
    _is_ic = False
    try:
        _is_ic = isinstance(ee_obj, ee.ImageCollection) or (
            hasattr(ee_obj, "getInfo") and ee.ImageCollection(ee_obj).size().getInfo() > 0
            and not isinstance(ee_obj, ee.Image)
        )
    except Exception:
        pass
    # If user explicitly wraps as IC, detect it
    if not _is_ic:
        try:
            obj_info_check = cl.get_obj_info(ee_obj)
            _is_ic = obj_info_check["obj_type"] == "ImageCollection"
        except Exception:
            pass

    if _is_ic:
        return generate_map_chart_gif(
            ee_obj, geometry,
            viz_params=viz_params, band_name=band_name,
            dimensions=dimensions, bg_color=bg_color,
            font_color=font_color, font_outline_color=font_outline_color,
            output_path=output_path,
            crs=crs, transform=transform, scale=scale,
            margin=margin, basemap=basemap, overlay_opacity=overlay_opacity,
            scalebar=scalebar, scalebar_units=scalebar_units,
            north_arrow=north_arrow, north_arrow_style=north_arrow_style,
            inset_map=inset_map, inset_basemap=inset_basemap,
            inset_scale=inset_scale, title=title,
            chart_type=chart_type or "line+markers",
            chart_scale=chart_scale, area_format=area_format,
            chart_height=chart_height, legend_position=legend_position,
            include_masked_area=include_masked_area,
            burn_in_geometry=burn_in_geometry,
            title_font_size=title_font_size, label_font_size=label_font_size,
            geometry_outline_color=geometry_outline_color,
            geometry_fill_color=geometry_fill_color,
            geometry_outline_weight=geometry_outline_weight,
            clip_to_geometry=clip_to_geometry,
        )

    # Detect if multi-feature
    is_multi = _is_multi_feature(geometry)
    _is_scatter = str(chart_type).lower().strip() == "scatter" if chart_type else False

    # --- Detect thematic to avoid duplicate legends ---
    _is_thematic = False
    try:
        _obj_info = cl.get_obj_info(ee_obj)
        _is_thematic = _obj_info.get("is_thematic", False)
    except Exception:
        pass

    # --- Generate the map thumbnail ---
    # For thematic data, legend goes on the thumb only (not duplicated on chart)
    thumb_kwargs = dict(
        viz_params=viz_params, band_name=band_name,
        dimensions=dimensions, bg_color=bg_color,
        font_color=font_color, font_outline_color=font_outline_color,
        crs=crs, transform=transform, scale=scale,
        margin=0, basemap=basemap, overlay_opacity=overlay_opacity,
        scalebar=scalebar, scalebar_units=scalebar_units,
        north_arrow=north_arrow, north_arrow_style=north_arrow_style,
        inset_map=inset_map, inset_basemap=inset_basemap,
        inset_scale=inset_scale,
        burn_in_geometry=burn_in_geometry,
        geometry_outline_color=geometry_outline_color,
        geometry_fill_color=geometry_fill_color,
        geometry_outline_weight=geometry_outline_weight,
        clip_to_geometry=clip_to_geometry,
        title_font_size=title_font_size,
        label_font_size=label_font_size,
        burn_in_legend=burn_in_legend,
    )

    if is_multi and not _is_scatter:
        thumb_kwargs["feature_label"] = feature_label
        thumb_kwargs["columns"] = columns
        if thumb_width:
            thumb_kwargs["thumb_width"] = thumb_width

    # For scatter: use FC bounds for the map, burn in points as geometry
    _map_geometry = geometry
    if _is_scatter and is_multi:
        _map_geometry = ee.FeatureCollection(geometry).geometry().bounds()
        # Burn in the sample points on the map
        thumb_kwargs["burn_in_geometry"] = True
        thumb_kwargs["clip_to_geometry"] = False
        # Use the FC itself as the geometry overlay (shows point dots)
        _map_ee_obj = ee_obj
        # Paint points onto the image before thumbnailing
        _fc_geom = ee.FeatureCollection(geometry)
        _bounds = _get_bounds_4326(_map_geometry)
        _gc = _resolve_geometry_color(
            geometry_outline_color,
            _resolve_font_colors(bg_color, font_color, font_outline_color)[0],
            basemap, _bounds,
        )
        _img = _to_image(ee_obj)
        _img = _apply_projection(_img, crs, transform, scale)
        _vp = _complete_viz_params(viz_params, _img, band_name=band_name, geometry=_map_geometry)
        _img = _paint_boundary(_img, _fc_geom, _gc, viz_params=_vp,
                               fill_color=geometry_fill_color,
                               width=max(1, geometry_outline_weight), crs=crs)
        # Pass pre-visualized image, skip further viz
        thumb_kwargs["viz_params"] = {"min": 0, "max": 255}
        thumb_kwargs["burn_in_geometry"] = False  # already painted
        thumb_result = generate_thumbs(_img, _map_geometry, **thumb_kwargs)
    else:
        thumb_result = generate_thumbs(ee_obj, _map_geometry, **thumb_kwargs)

    map_img = Image.open(io.BytesIO(thumb_result["thumb_bytes"])).convert("RGBA")

    # --- Generate the chart ---
    chart_kwargs = dict(
        scale=chart_scale,
        area_format=area_format,
        include_masked_area=include_masked_area,
        opacity=opacity,
    )

    # For thematic data, suppress chart legend since it's on the thumb
    if _is_thematic and burn_in_legend:
        chart_kwargs["legend_position"] = {"visible": False}
    else:
        chart_kwargs["legend_position"] = legend_position

    # Auto chart_type
    if chart_type is None:
        chart_type = "bar"

    chart_kwargs["chart_type"] = chart_type

    if band_names:
        chart_kwargs["band_names"] = band_names
    if thematic_band_name:
        chart_kwargs["thematic_band_name"] = thematic_band_name
    if feature_label:
        chart_kwargs["feature_label"] = feature_label
    chart_kwargs["columns"] = columns

    result = cl.summarize_and_chart(ee_obj, geometry, **chart_kwargs)

    # Unpack (varies by chart type)
    if isinstance(result, tuple) and len(result) == 3:
        df, fig, extra = result  # sankey
    elif isinstance(result, tuple):
        df, fig = result
    else:
        df, fig = result, None

    if fig is None:
        thumb_bytes = _pil_to_png_bytes(map_img, bg_color)
        return {"html": "", "thumb_bytes": thumb_bytes, "df": df, "fig": None}

    # Suppress chart legend for thematic (already on thumb)
    if _is_thematic and burn_in_legend:
        fig.update_layout(showlegend=False)

    # Remove chart title — the combined output has its own title strip
    fig.update_layout(title=None)

    # --- Render chart to PNG ---
    mw, mh = map_img.size
    if chart_height is None:
        chart_height = mh  # match map height for side-by-side

    if layout == "side-by-side":
        chart_width = max(400, int(mw * 0.8))
    else:
        chart_width = mw

    chart_png_bytes = fig.to_image(format="png", width=chart_width, height=chart_height)
    chart_img = Image.open(io.BytesIO(chart_png_bytes)).convert("RGBA")

    # --- Compose map + chart ---
    font_color_resolved, _, theme, bg_color = _resolve_font_colors(
        bg_color, font_color, font_outline_color)
    bg_rgba = _resolve_color(bg_color) + (255,)

    if layout == "side-by-side":
        gap = max(4, margin // 2)
        total_w = mw + gap + chart_img.size[0]
        total_h = max(mh, chart_img.size[1])
        combined = Image.new("RGBA", (total_w, total_h), bg_rgba)
        combined.paste(map_img, (0, (total_h - mh) // 2),
                       map_img if map_img.mode == "RGBA" else None)
        combined.paste(chart_img, (mw + gap, (total_h - chart_img.size[1]) // 2),
                       chart_img if chart_img.mode == "RGBA" else None)
    else:  # stacked
        gap = max(4, margin // 2)
        total_w = max(mw, chart_img.size[0])
        total_h = mh + gap + chart_img.size[1]
        combined = Image.new("RGBA", (total_w, total_h), bg_rgba)
        combined.paste(map_img, ((total_w - mw) // 2, 0),
                       map_img if map_img.mode == "RGBA" else None)
        combined.paste(chart_img, ((total_w - chart_img.size[0]) // 2, mh + gap),
                       chart_img if chart_img.mode == "RGBA" else None)

    # Title
    if title:
        tfont = _get_font(title_font_size)
        tmp_d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        tb = tmp_d.textbbox((0, 0), title, font=tfont)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        tpad = max(4, title_font_size // 3)
        strip_h = tpad + th + tpad
        with_title = Image.new("RGBA", (combined.size[0], strip_h + combined.size[1]), bg_rgba)
        td = ImageDraw.Draw(with_title)
        td.text(((combined.size[0] - tw) // 2, tpad - tb[1]), title,
                font=tfont, fill=font_color_resolved)
        with_title.paste(combined, (0, strip_h), combined if combined.mode == "RGBA" else None)
        combined = with_title

    combined = _add_margin(combined, margin, bg_color=bg_color)

    thumb_bytes = _pil_to_png_bytes(combined, bg_color)
    if output_path:
        _write_bytes(output_path, thumb_bytes)

    html = _bytes_to_html_figure(thumb_bytes, "png", css_class="map-chart")
    return {"html": html, "thumb_bytes": thumb_bytes, "df": df, "fig": fig}


def generate_map_chart_gif(
    ee_obj,
    geometry,
    viz_params=None,
    band_name=None,
    dimensions=_DEFAULT_DIMENSIONS,
    fps=_DEFAULT_FPS,
    max_frames=_MAX_GIF_FRAMES,
    date_format="YYYY",
    bg_color=None,
    font_color=None,
    font_outline_color=None,
    output_path=None,
    crs=_DEFAULT_CRS,
    transform=None,
    scale=None,
    margin=_DEFAULT_MARGIN,
    basemap=None,
    overlay_opacity=None,
    scalebar=True,
    scalebar_units="metric",
    north_arrow=True,
    north_arrow_style="solid",
    inset_map=True,
    inset_basemap=None,
    inset_scale=0.25,
    title=None,
    # Chart params
    chart_type="line+markers",
    chart_scale=30,
    area_format="Percentage",
    chart_height=None,
    legend_position="bottom",
    include_masked_area=True,
    burn_in_geometry=True,
    title_font_size=_DEFAULT_TITLE_FONT_SIZE,
    label_font_size=_DEFAULT_LABEL_FONT_SIZE,
    geometry_outline_color=None,
    geometry_fill_color=None,
    geometry_outline_weight=2,
    clip_to_geometry=True,
):
    """Generate an animated GIF with map thumbnails and cumulative line charts.

    Each frame shows a map thumbnail for one time step above a chart that
    accumulates data from the first year up to the current year.  The
    chart's x-axis spans the full time range so the frame-to-frame
    progression is visually stable.  A legend is placed below the chart.

    This mirrors the layout of
    ``https://storage.googleapis.com/lcms-gifs/San_Juan_NF_Land_Cover.gif``.

    Args:
        ee_obj (ee.ImageCollection): Multi-temporal image collection.
        geometry: ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.
        viz_params (dict, optional): Viz params for the map thumbnails.
            Auto-detected when ``None``.
        band_name (str, optional): Band to visualize.
        dimensions (int): Map thumbnail width in pixels.
        fps (int): Frames per second.
        max_frames (int): Max number of frames.
        date_format (str): Date format for labels (e.g. ``"YYYY"``).
        bg_color: Background colour.
        font_color: Font colour.
        font_outline_color: Font outline colour.
        output_path (str, optional): Save GIF to this path.
        crs, transform, scale: Projection params for thumbnails.
        margin (int): Margin in pixels.
        basemap: Basemap preset for map thumbnails.
        overlay_opacity (float): Opacity of EE data over basemap.
        scalebar (bool): Draw scalebar on map.
        scalebar_units (str): ``"metric"`` or ``"imperial"``.
        north_arrow (bool): Draw north arrow on map.
        north_arrow_style (str): Arrow style.
        title (str, optional): Title above the map.
        chart_type (str): Chart type for the time series.
            Default ``"line+markers"``.
        chart_scale (int): Scale in metres for ``reduceRegion``.
        area_format (str): ``"Percentage"``, ``"Hectares"``, ``"Acres"``.
        chart_height (int, optional): Chart height in pixels.
            Default is ``dimensions * 0.6``.
        legend_position (str or dict): Legend placement on chart.

    Returns:
        dict: ``{"html": str, "gif_bytes": bytes}``
    """
    from PIL import Image, ImageDraw
    import plotly.graph_objects as go

    _validate_projection_params(crs, transform, scale)

    col = ee.ImageCollection(ee_obj)
    geom = _to_geometry(geometry)

    # Resolve viz
    viz_params = _complete_viz_params(viz_params, col, band_name=band_name, geometry=geometry)

    # Resolve colours
    font_color, font_outline_color, theme, bg_color = _resolve_font_colors(
        bg_color, font_color, font_outline_color)

    if overlay_opacity is None:
        overlay_opacity = 0.8 if basemap is not None else 1.0

    if chart_height is None:
        chart_height = max(200, int(dimensions * 0.6))

    # --- Prepare collection ---
    col = col.filterBounds(geom)
    col = _mosaic_by_date(col)
    col = _apply_projection_to_collection(col, crs, transform, scale)
    if clip_to_geometry:
        col = col.map(lambda img: img.clip(geom).copyProperties(img, ["system:time_start"]))

    # Burn in geometry boundary (pre-visualizes the collection)
    if burn_in_geometry:
        bounds = _get_bounds_4326(geom)
        gc = _resolve_geometry_color(geometry_outline_color, font_color, basemap, bounds)
        col = _paint_boundary(col, geom, gc, viz_params=viz_params, fill_color=geometry_fill_color, width=geometry_outline_weight, crs=crs)
        viz_params = {"min": 0, "max": 255}

    count = col.size().getInfo()
    if count > max_frames:
        col = col.limit(max_frames)
        count = max_frames
    if count == 0:
        return {"html": "<p>No images.</p>", "gif_bytes": b""}

    # --- Download map frames + run zonal stats in parallel ---
    bounds = _get_bounds_4326(geom)

    def _do_frames():
        return _download_frames(col, geom if clip_to_geometry else geom.bounds(), viz_params, dimensions, count, date_format)

    def _do_stats():
        return cl.zonal_stats(
            ee_obj, geometry,
            band_names=[band_name] if band_name else None,
            scale=chart_scale,
            area_format=area_format,
            date_format=date_format,
            include_masked_area=include_masked_area,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        frames_future = pool.submit(_do_frames)
        stats_future = pool.submit(_do_stats)
        pil_frames, date_labels = frames_future.result()
        df = stats_future.result()

    if not pil_frames:
        return {"html": "<p>Failed to download frames.</p>", "gif_bytes": b""}

    # Composite basemap (adds padding border) or add blank padding
    if basemap is not None and bounds is not None:
        fw0, fh0 = pil_frames[0].size
        bm = _fetch_basemap(bounds, fw0 + 2 * _THUMB_PADDING, fh0 + 2 * _THUMB_PADDING, basemap, crs=crs)
        if bm is not None:
            pil_frames = [_composite_with_basemap(f, bm, overlay_opacity) for f in pil_frames]
        else:
            pil_frames = [_add_thumb_padding(f, bg_color=bg_color) for f in pil_frames]
    else:
        pil_frames = [_add_thumb_padding(f, bg_color=bg_color) for f in pil_frames]

    # Scalebar + north arrow on all map frames
    if bounds is not None:
        for f in pil_frames:
            _draw_scalebar_and_arrow_on_frame(
                f, bounds, scalebar=scalebar, north_arrow=north_arrow,
                north_arrow_style=north_arrow_style,
                font_color=font_color, contrast=font_outline_color,
                accent=theme.accent,
                label_font_size=label_font_size,
                crs=crs,
            )

    # Resolve geometry colors for inset extent rectangle
    _mcg_gc = gc if burn_in_geometry else (
        _resolve_geometry_color(geometry_outline_color, font_color, basemap, bounds)
        if geometry_outline_color else None)
    _mcg_fill = _hex_fill_to_rgba(geometry_fill_color) if geometry_fill_color else None

    # Inset map on all frames (lower-right corner)
    if inset_map and bounds is not None and pil_frames:
        _ib = inset_basemap if inset_basemap else basemap
        if _ib is not None:
            from PIL import Image as _PILImage
            _fw, _fh = pil_frames[0].size
            target_h = int(_fh * inset_scale)
            _mcg_kw = {}
            if _mcg_gc is not None:
                _mcg_kw["rect_color"] = _mcg_gc
            if _mcg_fill is not None:
                _mcg_kw["rect_fill_color"] = _mcg_fill
            inset_img = _build_inset_image(bounds, size=target_h, inset_basemap=_ib, **_mcg_kw)
            if inset_img is not None:
                src_w, src_h = inset_img.size
                aspect = src_w / src_h if src_h > 0 else 1.0
                iw = int(target_h * aspect)
                ih = target_h
                if iw > _fw // 3:
                    iw = _fw // 3
                    ih = int(iw / aspect)
                inset_resized = inset_img.resize((iw, ih), _PILImage.LANCZOS)
                pad = max(4, _fw // 60)
                for f in pil_frames:
                    px = f.size[0] - iw - pad
                    py = f.size[1] - ih - pad
                    f.paste(inset_resized, (px, py),
                            inset_resized if inset_resized.mode == "RGBA" else None)

    obj_info = cl.get_obj_info(ee_obj, [band_name] if band_name else None)
    class_info = obj_info.get("class_info", {})
    y_label = cl.AREA_FORMAT_DICT.get(area_format, {}).get("label", area_format) if obj_info["is_thematic"] else "Mean"

    # Build a name→color lookup so colors match even when classes are masked
    _color_lookup = {}
    if class_info:
        for bn in obj_info["band_names"]:
            ci = class_info.get(bn, {})
            cn = ci.get("class_names", [])
            cp = ci.get("class_palette", [])
            for i, name in enumerate(cn):
                if i < len(cp):
                    _color_lookup[name] = cl._ensure_hex_color(cp[i])

    # Map colors to actual DataFrame columns (which may be a subset)
    columns = list(df.columns)
    colors = [_color_lookup.get(c) for c in columns] if _color_lookup else None

    # Full x range for consistent axis
    all_x = list(df.index)
    try:
        all_x_int = [int(v) for v in all_x]
    except (ValueError, TypeError):
        all_x_int = None

    plotly_mode, is_stacked = cl._parse_chart_type(chart_type)

    # --- Build legend panel from class info ---
    legend_info = _extract_legend_info(ee_obj, band_name=band_name, viz_params=viz_params)

    fw = pil_frames[0].size[0]
    fh = pil_frames[0].size[1]

    # Build full-width horizontal legend — only for classes in the data
    horiz_legend = None
    if legend_info is not None and legend_info.get("type") == "thematic":
        # Filter to classes that actually appear in the DataFrame
        data_cols = set(df.columns)
        leg_names = []
        leg_palette = []
        for name, pal in zip(legend_info["class_names"], legend_info["class_palette"]):
            if name in data_cols:
                leg_names.append(name)
                leg_palette.append(pal)
        if leg_names:
            horiz_legend = _build_horizontal_legend(
                leg_names, leg_palette,
                width=fw, bg_color=bg_color, font_color=font_color,
            )
    elif legend_info is not None:
        # Continuous — use vertical colorbar centered
        vp = _build_legend_panel_from_info(
            legend_info, target_height=max(60, chart_height // 3),
            bg_color=bg_color, scale=1.0, font_color=font_color,
        )
        if vp is not None:
            lw, lh = vp.size
            horiz_legend = Image.new("RGBA", (fw, lh), _resolve_color(bg_color) + (255,))
            horiz_legend.paste(vp.convert("RGBA"), ((fw - lw) // 2, 0), vp.convert("RGBA"))

    # --- Compute fixed y-axis range across all frames ---
    columns = list(df.columns)
    if is_stacked:
        # For stacked: sum across columns per row
        row_sums = df[columns].sum(axis=1)
        y_min_data = 0
        y_max_data = float(row_sums.max())
    else:
        y_min_data = float(df[columns].min().min())
        y_max_data = float(df[columns].max().max())

    y_span = y_max_data - y_min_data
    y_buf = y_span * 0.1
    y_range_min = 0 if y_min_data == 0 else y_min_data - y_buf
    y_range_max = 100 if 99.5 <= y_max_data <= 101 else y_max_data + y_buf

    # For single-frame data, use stacked bar instead of line
    if len(df) == 1 and plotly_mode != "bar":
        plotly_mode = "bar"
        is_stacked = True

    # --- Render per-frame chart as PNG ---
    chart_pngs = []
    for i in range(len(pil_frames)):
        # Cumulative data: rows 0..i
        sub_df = df.iloc[:i + 1]
        sub_x = list(sub_df.index)
        try:
            sub_x_plot = [int(v) for v in sub_x]
        except (ValueError, TypeError):
            sub_x_plot = sub_x

        fig = go.Figure()
        for ci_idx, col_name in enumerate(columns):
            color = colors[ci_idx] if colors and ci_idx < len(colors) else None
            if plotly_mode == "bar":
                fig.add_trace(go.Bar(
                    x=sub_x_plot, y=sub_df[col_name].values,
                    name=col_name, marker_color=color, showlegend=False,
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=sub_x_plot, y=sub_df[col_name].values,
                    mode=plotly_mode, name=col_name,
                    line=dict(color=color, width=1.5),
                    marker=dict(color=color, size=3),
                    stackgroup="one" if is_stacked else None,
                    showlegend=False,
                ))

        # Fix x-axis to full range, y-axis to fixed range
        x_kw = {"tickformat": "d"} if all_x_int else {}
        if all_x_int:
            x_kw["tickvals"] = all_x_int
            x_kw["range"] = [min(all_x_int) - 0.5, max(all_x_int) + 0.5]
        bar_mode = "stack" if is_stacked and plotly_mode == "bar" else (
            "group" if plotly_mode == "bar" else None)

        fig.update_layout(
            xaxis=dict(title="Year", **x_kw),
            yaxis=dict(title=y_label, automargin=True,
                       range=[y_range_min, y_range_max]),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Roboto", color=cl._ensure_hex_color(
                "{:02x}{:02x}{:02x}".format(*font_color))),
            width=fw, height=chart_height,
            margin=dict(l=50, r=10, b=35, t=5, pad=2),
            barmode=bar_mode,
        )
        from geeViz.outputLib import themes as _themes
        _themes.apply_plotly_theme(fig, "dark", bg_color=bg_color)

        chart_png = fig.to_image(format="png", width=fw, height=chart_height)
        chart_pngs.append(Image.open(io.BytesIO(chart_png)).convert("RGBA"))

    # --- Assemble frames: title + map + chart + legend ---
    bg_rgba = _resolve_color(bg_color) + (255,)
    assembled = []
    for i, (map_frame, chart_img) in enumerate(zip(pil_frames, chart_pngs)):
        parts = []

        # Title with year
        if title:
            label = f"{title} : {date_labels[i]}" if i < len(date_labels) else title
        else:
            label = date_labels[i] if i < len(date_labels) else ""

        if label:
            tfont = _get_font(title_font_size)
            tmp_d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
            tb = tmp_d.textbbox((0, 0), label, font=tfont)
            tw = tb[2] - tb[0]
            th = tb[3] - tb[1]
            tpad = max(4, title_font_size // 3)
            strip = Image.new("RGBA", (fw, tpad + th + tpad), bg_rgba)
            td = ImageDraw.Draw(strip)
            td.text(((fw - tw) // 2, tpad - tb[1]), label, font=tfont, fill=font_color)
            parts.append(strip)

        parts.append(map_frame)
        parts.append(chart_img)

        # Legend (full-width horizontal, below chart)
        if horiz_legend is not None:
            parts.append(horiz_legend)

        # Stack vertically
        total_h = sum(p.size[1] for p in parts)
        combined = Image.new("RGBA", (fw, total_h), bg_rgba)
        y = 0
        for p in parts:
            combined.paste(p, (0, y), p if p.mode == "RGBA" else None)
            y += p.size[1]

        # Add margin
        combined = _add_margin(combined, max(4, margin // 2), bg_color=bg_color)
        assembled.append(combined)

    gif_bytes = _frames_to_gif(assembled, fps, bg_color=bg_color)

    if output_path:
        _write_bytes(output_path, gif_bytes)

    b64 = base64.b64encode(gif_bytes).decode("ascii")
    html = f'<figure class="map-chart-gif"><img src="data:image/gif;base64,{b64}"></figure>'
    return {"html": html, "gif_bytes": gif_bytes}


def _frames_to_gif(pil_frames, fps, bg_color="black"):
    """Convert PIL frames to an animated GIF with a consistent global palette.

    Builds a single 256-color palette from all frames combined, then
    quantizes each frame with that palette so colors don't shift
    between frames.

    Args:
        pil_frames: List of RGBA PIL Images.
        fps: Frames per second.
        bg_color: Background color for transparent areas.
    """
    from PIL import Image
    # Flatten to RGB
    rgb_frames = []
    for frame in pil_frames:
        bg = Image.new("RGBA", frame.size, bg_color)
        composite = Image.alpha_composite(bg, frame)
        rgb_frames.append(composite.convert("RGB"))

    # Build a global palette by stacking all frames into one tall image
    # and quantizing it to 256 colors
    fw, fh = rgb_frames[0].size
    combined = Image.new("RGB", (fw, fh * len(rgb_frames)))
    for i, f in enumerate(rgb_frames):
        combined.paste(f, (0, i * fh))
    global_palette_img = combined.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    palette = global_palette_img.getpalette()

    # Quantize each frame using the global palette
    palette_frames = []
    for f in rgb_frames:
        # quantize() with palette= requires a P-mode image as reference
        qf = f.quantize(palette=global_palette_img, dither=Image.Dither.FLOYDSTEINBERG)
        palette_frames.append(qf)

    buf = io.BytesIO()
    duration_ms = int(1000 / fps)
    palette_frames[0].save(
        buf, format="GIF", save_all=True,
        append_images=palette_frames[1:],
        duration=duration_ms, loop=0,
    )
    return buf.getvalue()


# ---------------------------------------------------------------------------
#  Per-feature thumbnails
# ---------------------------------------------------------------------------
def get_thumb_urls_by_feature(ee_obj, features, viz_params=None,
                              dimensions=_DEFAULT_DIMENSIONS,
                              feature_label=None, band_name=None,
                              max_features=10):
    """Get thumbnail URLs for an image clipped to each feature in a collection.

    Iterates over features sequentially, clipping the image to each
    feature's geometry and generating a separate thumbnail URL.  For
    faster processing with many features, use
    :func:`get_thumb_urls_by_feature_parallel` instead.

    Args:
        ee_obj (ee.Image or ee.ImageCollection): Image to thumbnail.
            Collections are reduced to a single representative image.
        features (ee.FeatureCollection): Collection of features; each
            feature's geometry is used to clip a separate thumbnail.
        viz_params (dict, optional): Visualization parameters.
            Auto-detected via :func:`auto_viz` when ``None``.
            Defaults to ``None``.
        dimensions (int, optional): Width in pixels per thumbnail.
            Defaults to ``640``.
        feature_label (str, optional): Property name to use as a
            human-readable label for each feature.  Auto-detected
            when ``None``.  Defaults to ``None``.
        band_name (str, optional): Band to visualize when using
            auto-detection.  Defaults to ``None``.
        max_features (int, optional): Maximum number of features to
            process.  Defaults to ``10``.

    Returns:
        list[dict]: List of dictionaries, one per feature, each
        containing:

        - ``"label"`` (str): Feature label from ``feature_label``
          property.
        - ``"url"`` (str): PNG thumbnail URL.
        - ``"geometry"`` (ee.Geometry): The feature's geometry.

    Example:
        >>> results = get_thumb_urls_by_feature(
        ...     image, counties.limit(3), feature_label="NAME",
        ... )
        >>> results[0].keys()
        dict_keys(['label', 'url', 'geometry'])
    """
    img = _to_image(ee_obj)

    if viz_params is None:
        viz_params = auto_viz(img, band_name=band_name)

    if feature_label is None:
        feature_label = cl._detect_feature_label(features)

    # Get feature list
    feat_list = features.toList(max_features).getInfo()

    results = []
    for feat_dict in feat_list:
        feat = ee.Feature(feat_dict)
        geom = feat.geometry()
        label = feat_dict.get("properties", {}).get(feature_label, "unknown")

        params = {**viz_params, "dimensions": dimensions, "format": "png",
                  "region": geom}
        url = img.clip(geom).getThumbURL(params)
        results.append({"label": label, "url": url, "geometry": geom})

    return results


def get_thumb_urls_by_feature_parallel(ee_obj, features, viz_params=None,
                                       dimensions=_DEFAULT_DIMENSIONS,
                                       feature_label=None, band_name=None,
                                       max_features=10, max_workers=6,
                                       burn_in_params=None,
                                       clip_to_geometry=True):
    """Generate per-feature thumbnail URLs in parallel using a thread pool.

    Like :func:`get_thumb_urls_by_feature`, but uses
    ``concurrent.futures.ThreadPoolExecutor`` to issue multiple
    ``getThumbURL()`` requests concurrently, significantly reducing
    wall-clock time for collections with many features.

    Args:
        ee_obj (ee.Image or ee.ImageCollection): Image to thumbnail.
            Collections are reduced to a single representative image.
        features (ee.FeatureCollection): Collection of features; each
            feature's geometry is used to clip a separate thumbnail.
        viz_params (dict, optional): Visualization parameters.
            Auto-detected via :func:`auto_viz` when ``None``.
            Defaults to ``None``.
        dimensions (int, optional): Width in pixels per thumbnail.
            Defaults to ``640``.
        feature_label (str, optional): Property name to use as a
            human-readable label for each feature.  Auto-detected
            when ``None``.  Defaults to ``None``.
        band_name (str, optional): Band to visualize when using
            auto-detection.  Defaults to ``None``.
        max_features (int, optional): Maximum number of features to
            process.  Defaults to ``10``.
        max_workers (int, optional): Maximum threads in the pool.
            Defaults to ``6``.

    Returns:
        list[dict]: List of dictionaries, one per feature, each
        containing:

        - ``"label"`` (str): Feature label from ``feature_label``
          property.
        - ``"url"`` (str): PNG thumbnail URL.

    Example:
        >>> counties = ee.FeatureCollection("TIGER/2018/Counties")
        >>> results = get_thumb_urls_by_feature_parallel(
        ...     image, counties.limit(5),
        ...     feature_label="NAME",
        ... )
        >>> results[0]["label"]
        'Some County'
    """
    img = _to_image(ee_obj)

    if viz_params is None:
        viz_params = auto_viz(img, band_name=band_name)

    if feature_label is None:
        feature_label = cl._detect_feature_label(features)

    feat_list = features.toList(max_features).getInfo()

    def _get_one(feat_dict):
        feat = ee.Feature(feat_dict)
        geom = feat.geometry()
        label = feat_dict.get("properties", {}).get(feature_label, "unknown")
        _img = img
        _vp = viz_params
        # Per-feature geometry burn-in: paint only this feature's boundary
        if burn_in_params is not None:
            _img = _paint_boundary(
                _img, geom, burn_in_params["color"],
                viz_params=burn_in_params["viz_params"],
                fill_color=burn_in_params.get("fill_color"),
                width=burn_in_params.get("weight", 2),
                crs=burn_in_params.get("crs"),
            )
            _vp = {"min": 0, "max": 255}
        _out_img = _img.clip(geom) if clip_to_geometry else _img
        # Request at padded dimensions with expanded region so EE data
        # fills to the basemap edges
        _padded_dims = dimensions + 2 * _THUMB_PADDING
        _bounds = _get_bounds_4326(geom)
        if _bounds is not None:
            _expanded = _expand_bounds_for_padding(_bounds, dimensions)
            _ee_region = ee.Geometry.Rectangle(_expanded, proj=ee.Projection("EPSG:4326"), evenOdd=False)
        else:
            _ee_region = geom if clip_to_geometry else geom.bounds()
        params = {**_vp, "dimensions": _padded_dims, "format": "png",
                  "region": _ee_region}
        url = _out_img.getThumbURL(params)
        return {"label": label, "url": url, "geometry": geom}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(_get_one, feat_list))

    return results


# ---------------------------------------------------------------------------
#  Thumbnail download & embedding
# ---------------------------------------------------------------------------
def download_thumb(url, timeout=120):
    """Download raw image bytes from an Earth Engine thumbnail URL.

    Fetches the PNG or GIF data from a URL returned by
    ``ee.Image.getThumbURL()`` or ``ee.ImageCollection.getVideoThumbURL()``.

    Args:
        url (str): Thumbnail URL from ``getThumbURL()`` or
            ``getVideoThumbURL()``.
        timeout (int, optional): HTTP request timeout in seconds.
            Defaults to ``120``.

    Returns:
        bytes: Raw image data (PNG or GIF format).

    Example:
        >>> data = download_thumb("https://earthengine.googleapis.com/...")
        >>> len(data) > 0
        True
    """
    req = urllib.request.Request(url, headers={"User-Agent": "geeViz-thumbLib/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def thumb_to_base64(url, timeout=120):
    """Download a thumbnail and return it as a base64 data URI string.

    Fetches image bytes from the given URL, detects the format (PNG or
    GIF) from the magic bytes, and encodes the result as a
    ``data:image/...;base64,...`` URI suitable for embedding in HTML.

    Args:
        url (str): Thumbnail URL from ``getThumbURL()`` or
            ``getVideoThumbURL()``.
        timeout (int, optional): HTTP request timeout in seconds.
            Defaults to ``120``.

    Returns:
        str: Base64 data URI string
        (e.g. ``"data:image/png;base64,iVBOR..."``).

    Example:
        >>> data_uri = thumb_to_base64("https://earthengine.googleapis.com/...")
        >>> data_uri.startswith("data:image/")
        True
    """
    data = download_thumb(url, timeout=timeout)
    fmt = "gif" if data[:3] == b"GIF" else "png"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/{fmt};base64,{b64}"


def embed_thumb(url, title="", width=None, download=False):
    """Generate an embeddable HTML ``<figure>`` element for a thumbnail.

    Wraps a thumbnail URL (or base64 data URI) in an HTML ``<figure>``
    with an ``<img>`` tag and optional ``<figcaption>``.  When
    ``download`` is True the image bytes are fetched and embedded
    inline as a base64 data URI so the resulting HTML is fully
    self-contained.

    Args:
        url (str): Thumbnail URL from ``getThumbURL()`` or a
            ``data:image/...`` base64 data URI.
        title (str, optional): Alt text and caption for the image.
            Defaults to ``""``.
        width (int, optional): CSS width in pixels applied via an
            inline style.  Defaults to ``None`` (natural size).
        download (bool, optional): Download the image from ``url``
            and embed it as a base64 data URI for self-contained HTML.
            Defaults to ``False`` (reference the URL directly).

    Returns:
        str: HTML string containing a ``<figure>`` with ``<img>`` and
        optional ``<figcaption>`` elements.

    Example:
        >>> html = embed_thumb(
        ...     "https://earthengine.googleapis.com/...",
        ...     title="Study Area", width=400,
        ... )
        >>> "<img" in html
        True
    """
    if download:
        src = thumb_to_base64(url)
    else:
        src = url

    style = f' style="width:{width}px;"' if width else ""
    caption = f"<figcaption>{title}</figcaption>" if title else ""

    return (
        f'<figure class="thumb">'
        f'<img src="{src}" alt="{title}"{style}>'
        f'{caption}'
        f'</figure>'
    )


def embed_thumb_grid(thumb_results, columns=3, thumb_width=300, download=False):
    """Generate an HTML CSS-grid layout of multiple thumbnails.

    Takes a list of per-feature thumbnail results (from
    :func:`get_thumb_urls_by_feature` or
    :func:`get_thumb_urls_by_feature_parallel`) and assembles them into
    a responsive CSS grid ``<div>`` with labeled ``<figure>`` elements.

    Args:
        thumb_results (list[dict]): List of thumbnail result
            dictionaries, each containing ``"label"`` (str) and
            ``"url"`` (str) keys.
        columns (int, optional): Number of grid columns.
            Defaults to ``3``.
        thumb_width (int, optional): Display width in pixels for each
            thumbnail image.  Defaults to ``300``.
        download (bool, optional): Download each image and embed as
            base64 for self-contained HTML.  Defaults to ``False``.

    Returns:
        str: HTML string containing a ``<div>`` with CSS grid styling
        and one ``<figure>`` per thumbnail.

    Example:
        >>> results = get_thumb_urls_by_feature_parallel(image, counties)
        >>> grid_html = embed_thumb_grid(results, columns=4, thumb_width=250)
        >>> "thumb-grid" in grid_html
        True
    """
    items = []
    for r in thumb_results:
        items.append(embed_thumb(r["url"], title=r["label"],
                                 width=thumb_width, download=download))

    grid_css = (
        f"display:grid; grid-template-columns:repeat({columns}, 1fr); "
        f"gap:12px; margin:16px 0;"
    )
    inner = "\n".join(items)
    return f'<div class="thumb-grid" style="{grid_css}">\n{inner}\n</div>'


# ---------------------------------------------------------------------------
#  Convenience: all-in-one thumbnail section for reports
# ---------------------------------------------------------------------------
def generate_thumbs(ee_obj, geometry, viz_params=None, band_name=None,
                    dimensions=_DEFAULT_DIMENSIONS, feature_label=None,
                    max_features=6, columns=3, thumb_width=300,
                    burn_in_legend=True, legend_scale=1.0,
                    bg_color=None, font_color=None,
                    font_outline_color=None, output_path=None,
                    crs=_DEFAULT_CRS, transform=None, scale=None,
                    margin=_DEFAULT_MARGIN, basemap=None,
                    overlay_opacity=None, scalebar=True,
                    scalebar_units="metric", north_arrow=True,
                    north_arrow_style="solid",
                    inset_map=True, inset_basemap=None, inset_scale=0.3,
                    inset_on_map=False, title=None,
                    burn_in_geometry=False, geometry_outline_color=None, geometry_fill_color=None, geometry_outline_weight=2,
                    clip_to_geometry=True,
                    geometry_legend_label="Study Area",
                    title_font_size=_DEFAULT_TITLE_FONT_SIZE,
                    label_font_size=_DEFAULT_LABEL_FONT_SIZE):
    """Generate a publication-ready thumbnail PNG for a report section.

    Provides an all-in-one workflow: auto-viz detection, thumbnail URL
    generation, image download, basemap compositing, and optional
    cartographic embellishments (legend, scalebar, north arrow, inset
    map, title).

    For ``ee.FeatureCollection`` geometries with multiple features,
    produces a labeled grid of per-feature thumbnails.  For single
    geometries, produces a single thumbnail with optional cartographic
    elements.

    For ``ee.ImageCollection`` input, the collection is reduced to a
    single representative image using the temporal mode (thematic data)
    or median (continuous data).

    Args:
        ee_obj (ee.Image or ee.ImageCollection): Image to thumbnail.
            Collections are reduced to a single representative image.
        geometry (ee.Geometry or ee.Feature or ee.FeatureCollection):
            Region to clip and bound the thumbnail.  When a
            ``FeatureCollection`` with multiple features is provided,
            a per-feature grid is generated instead.
        viz_params (dict, optional): Visualization parameters (``bands``,
            ``min``, ``max``, ``palette``).  Auto-detected via
            :func:`auto_viz` when ``None``.  Defaults to ``None``.
        band_name (str, optional): Band to visualize when using
            auto-detection.  Defaults to ``None`` (first band).
        dimensions (int, optional): Thumbnail width in pixels.
            Defaults to ``640``.
        feature_label (str, optional): Property name for per-feature
            labels in grid mode.  Auto-detected when ``None``.
            Defaults to ``None``.
        max_features (int, optional): Maximum features to include in
            the grid.  Defaults to ``6``.
        columns (int, optional): Number of columns in the per-feature
            grid.  Defaults to ``3``.
        thumb_width (int, optional): Width in pixels for each cell in
            the per-feature grid.  Defaults to ``300``.
        burn_in_legend (bool, optional): Append a legend panel for
            thematic data.  Only rendered when class names and palette
            are available in image properties.  Defaults to ``True``.
        legend_scale (float, optional): Scale multiplier for the legend
            panel size.  Defaults to ``1.0``.
        bg_color (str or None, optional): Background color for margins,
            legend panel, and transparent areas.  Resolved via theme
            when ``None``.  Defaults to ``None``.
        font_color (str or tuple or None, optional): Text color for
            labels and legend text.  Resolved via theme when ``None``.
            Defaults to ``None``.
        font_outline_color (str or tuple or None, optional): Outline /
            halo color for text readability.  Auto-derived when
            ``None``.  Defaults to ``None``.
        output_path (str, optional): File path to save the PNG.  Parent
            directories are created automatically.
            Defaults to ``None`` (not saved).
        crs (str, optional): CRS code (e.g. ``"EPSG:4326"``).
            Applies ``setDefaultProjection`` to the image.
            Defaults to ``None``.
        transform (list, optional): Affine transform as a 6-element
            list.  Requires ``crs``.  Defaults to ``None``.
        scale (float, optional): Nominal pixel scale in meters.
            Requires ``crs``.  Defaults to ``None``.
        margin (int, optional): Pixel margin on all sides of the final
            image.  Defaults to ``16``.
        basemap (str or dict or None, optional): Basemap to composite
            behind the EE data.  A preset name (e.g.
            ``"esri-satellite"``, ``"usfs-topo"``), a config dict with
            ``type`` and ``url`` keys, or a raw tile URL template.
            Defaults to ``None`` (no basemap).
        overlay_opacity (float or None, optional): Opacity of the EE
            overlay when a basemap is present (0.0 -- 1.0).  Defaults
            to ``None`` (auto: ``0.8`` with basemap, ``1.0`` without).
        scalebar (bool, optional): Draw a scalebar on the thumbnail.
            Only rendered when cartographic context is available.
            Defaults to ``True``.
        scalebar_units (str, optional): Unit system for the scalebar --
            ``"metric"`` or ``"imperial"``.  Defaults to ``"metric"``.
        north_arrow (bool, optional): Draw a north arrow on the
            thumbnail.  Defaults to ``True``.
        north_arrow_style (str, optional): Arrow style -- ``"solid"``,
            ``"classic"``, or ``"outline"``.  Defaults to ``"solid"``.
        inset_map (bool, optional): Include an inset overview map.
            Defaults to ``True``.
        inset_basemap (str or dict or None, optional): Basemap for the
            inset.  Falls back to ``basemap`` when ``None``.
            Defaults to ``None``.
        inset_scale (float, optional): Relative height of the inset
            compared to the frame height.  Defaults to ``0.3``.
        inset_on_map (bool, optional): Place the inset directly on the
            map rather than below it.  Defaults to ``True``.
        title (str, optional): Title text rendered as a strip above the
            thumbnail.  Defaults to ``None`` (no title).
        burn_in_geometry (bool, optional): Paint the geometry boundary
            outline onto the image using ``FeatureCollection.style()``.
            Defaults to ``False``.
        geometry_outline_color (tuple or None, optional): ``(R, G, B)``
            colour for the boundary outline.  When ``None``, auto-detected
            from the basemap luminance.  Defaults to ``None``.
        geometry_fill_color (str or None, optional): CSS fill colour for
            the geometry interior (e.g. ``"33333366"``).  Used for
            geometry-only thumbnails (``ee_obj=None``).
            Defaults to ``None``.
        geometry_outline_weight (int, optional): Width of the boundary
            outline in pixels.  Defaults to ``2``.
        geometry_legend_label (str, optional): Label for the geometry
            swatch in the legend.  Defaults to ``"Study Area"``.
        clip_to_geometry (bool, optional): When ``True``, clip the image
            to the geometry.  When ``False``, use the geometry's bounding
            box as the region (data extends beyond boundary).
            Defaults to ``True``.
        title_font_size (int, optional): Font size in pixels for the
            title strip.  Defaults to ``18``.
        label_font_size (int, optional): Font size in pixels for date
            labels, feature labels, scalebar ticks, and legend text.
            Defaults to ``12``.

    Returns:
        dict: A dictionary with the following keys:

        - ``"html"`` (str): HTML ``<figure>`` element containing the
          thumbnail as a base64-embedded ``<img>`` tag.
        - ``"thumb_bytes"`` (bytes): Raw PNG byte data.
        - ``"is_grid"`` (bool): ``True`` if a multi-feature grid was
          produced, ``False`` for a single thumbnail.

    Raises:
        ValueError: If ``transform`` or ``scale`` is provided without
            ``crs``.

    Example:
        >>> result = generate_thumbs(
        ...     lcms.select(["Land_Cover"]).first(),
        ...     study_area,
        ...     basemap="esri-satellite",
        ...     title="LCMS Land Cover 2023",
        ... )
        >>> result["is_grid"]
        False
        >>> len(result["thumb_bytes"]) > 0
        True
    """
    _validate_projection_params(crs, transform, scale)
    from PIL import Image

    _is_geom_only = ee_obj is None
    if _is_geom_only:
        img = ee.Image()
        if viz_params is None:
            viz_params = {}
        burn_in_geometry = True
    else:
        img = _to_image(ee_obj)
    img = _apply_projection(img, crs, transform, scale)

    if not _is_geom_only:
        viz_params = _complete_viz_params(viz_params, img, band_name=band_name, geometry=geometry)

    # Resolve overlay opacity: default 0.8 when basemap is set
    if overlay_opacity is None:
        overlay_opacity = 0.8 if basemap is not None else 1.0

    # Resolve font colors from theme
    font_color, font_outline_color, theme, bg_color = _resolve_font_colors(
        bg_color, font_color, font_outline_color)

    # Extract legend info BEFORE boundary painting (which changes viz_params)
    legend_info = None
    if burn_in_legend:
        legend_info = _extract_legend_info(ee_obj if not _is_geom_only else None,
                                           band_name=band_name, viz_params=viz_params)

    # Resolve geometry color (needed for both boundary and legend)
    _resolved_gc = None
    if burn_in_geometry and geometry is not None:
        _bounds_gc = _get_bounds_4326(_to_geometry(geometry))
        _resolved_gc = _resolve_geometry_color(geometry_outline_color, font_color, basemap, _bounds_gc)

    # Add geometry outline to legend when burning in geometry
    if burn_in_geometry and burn_in_legend and geometry_legend_label and _resolved_gc is not None:
        _gc_hex = "{:02x}{:02x}{:02x}".format(int(_resolved_gc[0]), int(_resolved_gc[1]), int(_resolved_gc[2]))
        # Resolve fill color for legend swatch
        _fill_for_legend = geometry_fill_color
        if _fill_for_legend is None and _is_geom_only:
            _fill_for_legend = "33333366"
        # Store geometry swatch info for all legend types
        _geom_swatch = {
            "label": geometry_legend_label,
            "outline_hex": _gc_hex,
            "fill_hex": _fill_for_legend,  # may be None or hex string
        }
        if legend_info is not None:
            legend_info["geometry_swatch"] = _geom_swatch
        else:
            legend_info = {"type": "thematic", "class_names": [], "class_palette": [],
                           "geometry_swatch": _geom_swatch}

    is_multi = _is_multi_feature(geometry)

    # Burn in geometry boundary (pre-visualizes the image)
    # For multi-feature grids, defer to per-feature painting so each frame
    # only shows its own boundary (not all features at once).
    if burn_in_geometry and geometry is not None and _resolved_gc is not None and not is_multi:
        _fill = "33333366" if _is_geom_only else None  # 0.4 opacity
        img = _paint_boundary(img, geometry, _resolved_gc, viz_params=viz_params if not _is_geom_only else None, fill_color=_fill or geometry_fill_color, width=geometry_outline_weight, crs=crs)
        # Geometry-only: styled boundary is already visualized, no viz needed
        viz_params = {} if _is_geom_only else {"min": 0, "max": 255}

    if is_multi:
        fc = ee.FeatureCollection(geometry)
        # For multi-feature, pass burn-in params so each feature paints only its own boundary
        _burn_params = None
        if burn_in_geometry and _resolved_gc is not None:
            _burn_params = {
                "color": _resolved_gc,
                "fill_color": geometry_fill_color,
                "weight": geometry_outline_weight,
                "crs": crs,
                "viz_params": viz_params,
            }
        results = get_thumb_urls_by_feature_parallel(
            img, fc, viz_params=viz_params, dimensions=dimensions,
            feature_label=feature_label, max_features=max_features,
            burn_in_params=_burn_params,
            clip_to_geometry=clip_to_geometry,
        )
        # Download all frames and build a PIL grid
        pil_thumb = _build_thumb_grid_image(
            results, columns=columns, thumb_width=thumb_width,
            legend_info=legend_info, bg_color=bg_color,
            legend_scale=legend_scale, basemap=basemap,
            overlay_opacity=overlay_opacity,
            scalebar=scalebar, north_arrow=north_arrow,
            north_arrow_style=north_arrow_style,
            inset_map=inset_map,
            inset_basemap=inset_basemap if inset_basemap else basemap,
            inset_scale=inset_scale,
            font_color=font_color, title=title,
            title_font_size=title_font_size, label_font_size=label_font_size,
            inset_rect_color=_resolved_gc if _resolved_gc is not None else None,
            inset_rect_fill_color=_hex_fill_to_rgba(geometry_fill_color) if geometry_fill_color else None,
        )
        pil_thumb = _add_margin(pil_thumb, margin, bg_color=bg_color)
        thumb_bytes = _pil_to_png_bytes(pil_thumb, bg_color)
        if output_path:
            _write_bytes(output_path, thumb_bytes)
        html = _bytes_to_html_figure(thumb_bytes, "png", css_class="thumb-grid")
        return {"html": html, "thumb_bytes": thumb_bytes, "is_grid": True}
    else:
        geom = _to_geometry(geometry)
        bounds = _get_bounds_4326(geom)
        padded_dims = dimensions + 2 * _THUMB_PADDING

        # Expand region so EE data fills to basemap edges (including padding margin)
        if basemap is not None and bounds is not None:
            expanded = _expand_bounds_for_padding(bounds, dimensions)
            ee_region = ee.Geometry.Rectangle(expanded, proj=ee.Projection("EPSG:4326"), evenOdd=False)
            _out_img = img.clip(geom) if clip_to_geometry else img
            url = _out_img.getThumbURL({
                **viz_params, "dimensions": padded_dims,
                "format": "png", "region": ee_region,
            })
        else:
            region = geom if clip_to_geometry else geom.bounds()
            _out_img = img.clip(geom) if clip_to_geometry else img
            url = _out_img.getThumbURL({
                **viz_params, "dimensions": padded_dims,
                "format": "png", "region": region,
            })

        data = download_thumb(url)
        frame = Image.open(io.BytesIO(data)).convert("RGBA")

        # Composite basemap underneath or add blank padding
        if basemap is not None and bounds is not None:
            # Basemap at same expanded extent and size
            basemap_img = _fetch_basemap(bounds, padded_dims, padded_dims, basemap, crs=crs)
            if basemap_img is not None:
                frame = _composite_with_basemap(frame, basemap_img, overlay_opacity)

        # Use expanded bounds for inset (reflects actual visible extent)
        if basemap is not None and bounds is not None:
            bounds = _expand_bounds_for_padding(bounds, dimensions)

        # Build legend panel (used by _assemble_with_cartography)
        legend_panel = _build_legend_panel_from_info(
            legend_info, target_height=frame.size[1],
            bg_color=bg_color, scale=legend_scale, font_color=font_color,
        )

        # Assemble with cartographic elements
        # Scalebar and north arrow work whenever bounds are available (no basemap needed).
        # Inset requires a basemap tile source.
        _has_inset_source = (basemap is not None or inset_basemap is not None)
        frame, has_bottom = _assemble_with_cartography(
            frame, bounds,
            bg_color=bg_color, font_color=font_color,
            font_outline_color=font_outline_color,
            title=title,
            scalebar=scalebar if bounds is not None else False,
            scalebar_units=scalebar_units,
            north_arrow=north_arrow if bounds is not None else False,
            north_arrow_style=north_arrow_style,
            inset_map=inset_map if (_has_inset_source and bounds is not None) else False,
            inset_basemap=inset_basemap if inset_basemap else basemap,
            inset_scale=inset_scale, inset_on_map=inset_on_map,
            inset_rect_color=_resolved_gc if _resolved_gc is not None else None,
            inset_rect_fill_color=_hex_fill_to_rgba(geometry_fill_color) if geometry_fill_color else None,
            legend_panel=legend_panel, margin=margin, crs=crs,
        )

        # Title strip includes the top margin, so set top to 0
        mt = 0 if title else margin
        mb = margin // 3 if has_bottom else margin
        frame = _add_margin(frame, (mt, margin, mb, margin), bg_color=bg_color)
        thumb_bytes = _pil_to_png_bytes(frame, bg_color)
        if output_path:
            _write_bytes(output_path, thumb_bytes)
        html = _bytes_to_html_figure(thumb_bytes, "png", css_class="thumb")
        return {"html": html, "thumb_bytes": thumb_bytes, "is_grid": False}


# ---------------------------------------------------------------------------
#  Internal helpers — image byte conversion
# ---------------------------------------------------------------------------
def _add_margin(pil_img, margin, bg_color="black"):
    """Add a colored margin (border) around a PIL image.

    Creates a new image that is larger than the source by the specified
    margin amounts on each side, pastes the source image onto the
    center, and fills the margin area with the background color.

    Args:
        pil_img (PIL.Image.Image): Source image in any mode (RGB,
            RGBA, etc.).
        margin (int or tuple): Margin size in pixels.  An ``int``
            applies uniformly to all sides.  A 4-element tuple
            specifies ``(top, right, bottom, left)`` individually.
        bg_color (str, optional): Background color for the margin area,
            as a CSS color name or hex string.
            Defaults to ``"black"``.

    Returns:
        PIL.Image.Image: New image with the margin added, in the same
        mode as the input.

    Example:
        >>> from PIL import Image
        >>> img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        >>> result = _add_margin(img, 10, bg_color="white")
        >>> result.size
        (120, 120)
    """
    if isinstance(margin, (list, tuple)):
        mt, mr, mb, ml = margin
    else:
        mt = mr = mb = ml = margin
    if mt <= 0 and mr <= 0 and mb <= 0 and ml <= 0:
        return pil_img
    from PIL import Image
    bg_rgb = _resolve_color(bg_color)
    fill = bg_rgb + (255,) if pil_img.mode == "RGBA" else bg_rgb
    new_w = pil_img.size[0] + ml + mr
    new_h = pil_img.size[1] + mt + mb
    canvas = Image.new(pil_img.mode, (new_w, new_h), fill)
    canvas.paste(pil_img, (ml, mt))
    return canvas


def _rgba_to_rgb(pil_img, bg_color="black"):
    """Flatten an RGBA image to RGB with the given background color."""
    from PIL import Image
    bg = Image.new("RGBA", pil_img.size, bg_color)
    composite = Image.alpha_composite(bg, pil_img.convert("RGBA"))
    return composite.convert("RGB")


def _pil_to_png_bytes(pil_img, bg_color="black"):
    """Convert a PIL Image (RGBA or RGB) to PNG bytes."""
    rgb = _rgba_to_rgb(pil_img, bg_color) if pil_img.mode == "RGBA" else pil_img
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    return buf.getvalue()


def _write_bytes(path, data):
    """Write raw bytes to a file, creating parent directories as needed."""
    import os
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _bytes_to_html_figure(data, fmt="png", css_class="thumb"):
    """Wrap raw image bytes in an HTML ``<figure>`` with base64 src."""
    b64 = base64.b64encode(data).decode("ascii")
    return (
        f'<figure class="{css_class}">'
        f'<img src="data:image/{fmt};base64,{b64}">'
        f'</figure>'
    )


def _build_thumb_grid_image(thumb_results, columns=3, thumb_width=300,
                             legend_info=None, bg_color="black",
                             legend_scale=1.0, basemap=None,
                             overlay_opacity=1.0, gap=3,
                             scalebar=True, north_arrow=True,
                             north_arrow_style="solid",
                             inset_map=True, inset_basemap=None,
                             inset_scale=0.3, inset_on_map=False,
                             font_color=None,
                             title=None,
                             title_font_size=_DEFAULT_TITLE_FONT_SIZE,
                             label_font_size=_DEFAULT_LABEL_FONT_SIZE,
                             inset_rect_color=None, inset_rect_fill_color=None):
    """Download per-feature thumbnails and assemble into a PIL grid image.

    Args:
        thumb_results (list[dict]): Each dict has ``label``, ``url``, and
            optionally ``geometry`` (ee.Geometry for per-feature basemap).
        columns (int): Grid columns.
        thumb_width (int): Target width per cell.
        legend_info (dict | None): Legend info (thematic or continuous).
        bg_color (str): Background color.
        legend_scale (float): Legend scale.
        basemap: Basemap preset name, config dict, or URL.
        overlay_opacity (float): Overlay opacity for basemap compositing.
        gap (int): Pixel gap between frames. Default 3.
        scalebar (bool): Draw scalebar on the first frame.
        north_arrow (bool): Draw north arrow on the first frame.
        north_arrow_style (str): North arrow style.
        inset_map (bool): Draw inset overview on the last frame.
        inset_basemap: Basemap for the inset. Falls back to *basemap*.
        inset_scale (float): Inset height as fraction of frame height.
        font_color (tuple or None): Text color override.

    Returns:
        PIL.Image.Image: RGBA grid image.
    """
    from PIL import Image, ImageDraw

    theme = _get_theme(bg_color)
    text_color = font_color if font_color is not None else theme.text
    panel_bg = _resolve_color(bg_color) + (255,)
    font_outline_color = theme.divider

    # Download all thumbnails in parallel
    # EE thumbnails are already requested at padded dimensions with expanded region
    padded_width = thumb_width + 2 * _THUMB_PADDING
    def _dl(r):
        data = download_thumb(r["url"])
        frame = Image.open(io.BytesIO(data)).convert("RGBA")
        # Resize to padded target width (EE thumb was requested at padded dims)
        if frame.size[0] != padded_width:
            ratio = padded_width / frame.size[0]
            new_h = int(frame.size[1] * ratio)
            frame = frame.resize((padded_width, new_h), Image.LANCZOS)
        bounds = None
        if "geometry" in r:
            bounds = _get_bounds_4326(r["geometry"])
        if basemap is not None and bounds is not None:
            fw_p, fh_p = frame.size
            bm = _fetch_basemap(bounds, fw_p, fh_p, basemap)
            if bm is not None:
                frame = _composite_with_basemap(frame, bm, overlay_opacity)
        return frame, r.get("label", ""), bounds

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_dl, thumb_results))

    if not results:
        return Image.new("RGBA", (thumb_width, 100), panel_bg)

    # Find max width and height across all frames so all cells are uniform
    fw = max(frame.size[0] for frame, _, _ in results)
    fh = max(frame.size[1] for frame, _, _ in results)
    n_total = len(results)

    # Pad each frame to the uniform cell size (centered)
    _uniform = []
    for frame, label, bounds in results:
        if frame.size[0] != fw or frame.size[1] != fh:
            padded = Image.new("RGBA", (fw, fh), panel_bg)
            ox = (fw - frame.size[0]) // 2
            oy = (fh - frame.size[1]) // 2
            padded.paste(frame, (ox, oy), frame if frame.mode == "RGBA" else None)
            _uniform.append((padded, label, bounds))
        else:
            _uniform.append((frame, label, bounds))
    results = _uniform

    n_cols = min(columns, n_total)
    n_rows = -(-n_total // n_cols)

    # Label font
    label_font = _get_font(label_font_size)
    label_h = label_font_size + 8

    cell_h = fh + label_h

    # -- Draw scalebar + north arrow on first frame (index 0) --
    first_frame, first_label, first_bounds = results[0]
    if first_bounds is not None and (scalebar or north_arrow):
        _draw_scalebar_and_arrow_on_frame(
            first_frame, first_bounds,
            scalebar=scalebar, north_arrow=north_arrow,
            north_arrow_style=north_arrow_style,
            font_color=text_color,
            contrast=font_outline_color,
            accent=theme.accent,
            label_font_size=label_font_size,
        )

    # -- Draw inset on the last frame (only when inset_on_map) --
    last_idx = n_total - 1
    last_frame, last_label, last_bounds = results[last_idx]
    if inset_map and inset_on_map and last_bounds is not None:
        _ib = inset_basemap if inset_basemap else basemap
        if True:  # build_inset_image uses default hillshade when _ib is None
            target_h = int(fh * inset_scale)
            _grid_kw = {}
            if inset_rect_color is not None:
                _grid_kw["rect_color"] = inset_rect_color
            if inset_rect_fill_color is not None:
                _grid_kw["rect_fill_color"] = inset_rect_fill_color
            inset_img = _build_inset_image(
                last_bounds, size=target_h, inset_basemap=_ib, **_grid_kw,
            )
            if inset_img is not None:
                src_w, src_h = inset_img.size
                aspect = src_w / src_h if src_h > 0 else 1.0
                iw = int(target_h * aspect)
                ih = target_h
                if iw > fw // 3:
                    iw = fw // 3
                    ih = int(iw / aspect)
                inset_resized = inset_img.resize((iw, ih), Image.LANCZOS)
                pad = max(4, fw // 60)
                px = last_frame.size[0] - iw - pad
                py = last_frame.size[1] - ih - pad
                last_frame.paste(
                    inset_resized, (px, py),
                    inset_resized if inset_resized.mode == "RGBA" else None,
                )

    # -- Build legend panel (right of first row, aligned with frame) --
    legend_panel = None
    if legend_info is not None:
        legend_panel = _build_legend_panel_from_info(
            legend_info, target_height=fh,  # frame height, not cell_h
            bg_color=bg_color, scale=legend_scale, font_color=text_color,
        )
    legend_col_w = legend_panel.size[0] if legend_panel is not None else 0
    grid_w = n_cols * fw + (n_cols - 1) * gap
    total_w = grid_w + (legend_col_w if legend_panel else 0)

    grid = Image.new("RGBA", (total_w, n_rows * cell_h + (n_rows - 1) * gap), panel_bg)
    draw = ImageDraw.Draw(grid)

    for idx, (frame, label, _bounds) in enumerate(results):
        col_i = idx % n_cols
        row_i = idx // n_cols
        x = col_i * (fw + gap)
        y = row_i * (cell_h + gap)

        if label:
            bbox = draw.textbbox((0, 0), str(label), font=label_font)
            tw = bbox[2] - bbox[0]
            draw.text((x + (fw - tw) // 2, y + 3), str(label),
                      font=label_font, fill=text_color)

        grid.paste(frame, (x, y + label_h))

    # Legend to right of first row, aligned with frame (below feature label)
    legend_bottom_y = label_h
    if legend_panel is not None:
        lp_rgba = legend_panel.convert("RGBA")
        grid.paste(lp_rgba, (grid_w, label_h), lp_rgba)
        legend_bottom_y = label_h + legend_panel.size[1]

    # Inset in right column (when inset_on_map=False)
    # Use the union of all feature bounds for the inset overview
    if inset_map and not inset_on_map and first_bounds is not None:
        _ib = inset_basemap if inset_basemap else basemap
        # build_inset_image uses a default hillshade basemap when _ib is None
        # Compute overall bounds from all features for a better overview
        all_bounds = [b for _, _, b in results if b is not None]
        if all_bounds:
            overview_bounds = (
                min(b[0] for b in all_bounds),
                min(b[1] for b in all_bounds),
                max(b[2] for b in all_bounds),
                max(b[3] for b in all_bounds),
            )
        else:
            overview_bounds = first_bounds

        max_w = max(legend_col_w - 8, 60)

        # Determine inset placement and available space
        if n_rows > 1:
            # Multi-row: place in legend column aligned with row 2
            inset_y = cell_h + gap + label_h
            avail_h = cell_h - label_h - 4
        else:
            # Single-row: place below legend in the legend column
            avail_h = grid.size[1] - legend_bottom_y - 4

        # If not enough space in the legend column, expand the grid
        # to make room for the inset below
        target_inset_h = min(max_w, fh // 2)  # desired inset size
        if avail_h < target_inset_h and n_rows <= 1:
            expand = target_inset_h - avail_h + 8
            new_grid = Image.new("RGBA", (grid.size[0], grid.size[1] + expand), panel_bg)
            new_grid.paste(grid, (0, 0), grid if grid.mode == "RGBA" else None)
            grid = new_grid
            avail_h = target_inset_h
            inset_y = legend_bottom_y
        elif n_rows <= 1:
            inset_y = legend_bottom_y

        if avail_h < 40:
            avail_h = fh

        # Fetch inset at final display size
        _inset_display = min(avail_h, int(max_w))
        _grid_kw2 = {}
        if inset_rect_color is not None:
            _grid_kw2["rect_color"] = inset_rect_color
        if inset_rect_fill_color is not None:
            _grid_kw2["rect_fill_color"] = inset_rect_fill_color
        inset_img = _build_inset_image(overview_bounds, size=max(60, _inset_display), inset_basemap=_ib, **_grid_kw2)
        if inset_img is not None:
            src_w, src_h = inset_img.size
            aspect = src_w / src_h if src_h > 0 else 1.0
            iw = min(max_w, int(avail_h * aspect))
            ih = int(iw / aspect)
            if ih > avail_h:
                ih = max(avail_h, 30)
                iw = int(ih * aspect)
            if iw > 10 and ih > 10:
                inset_resized = inset_img.resize((iw, ih), Image.LANCZOS)
                inset_pad = max(4, 4)
                grid.paste(inset_resized.convert("RGBA"),
                           (grid_w + inset_pad, inset_y),
                           inset_resized.convert("RGBA"))

    # Title strip — font size = 1.5x the label font
    if title:
        t_font = _get_font(title_font_size)
        tmp_d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        tb = tmp_d.textbbox((0, 0), title, font=t_font)
        t_tw = tb[2] - tb[0]
        t_th = tb[3] - tb[1]
        t_pad = max(6, label_font_size // 2)
        strip_h = t_pad + t_th + t_pad
        combined_h = strip_h + grid.size[1]
        assembled = Image.new("RGBA", (total_w, combined_h), panel_bg)
        td = ImageDraw.Draw(assembled)
        tx = (total_w - t_tw) // 2
        td.text((tx, t_pad - tb[1]), title, font=t_font, fill=text_color)
        assembled.paste(grid, (0, strip_h), grid if grid.mode == "RGBA" else None)
        grid = assembled

    return grid


# ---------------------------------------------------------------------------
#  Internal helpers — EE object conversion
# ---------------------------------------------------------------------------
def _to_image(ee_obj):
    """Convert ee_obj to ee.Image (mosaic if ImageCollection)."""
    if isinstance(ee_obj, ee.ImageCollection):
        # Check if thematic — use mode; else median
        info = cl.get_obj_info(ee_obj)
        if info["is_thematic"]:
            return ee.Image(ee_obj.mode().copyProperties(ee_obj.first()))
        else:
            return ee.Image(ee_obj.median().copyProperties(ee_obj.first()))
    return ee.Image(ee_obj)


def _to_geometry(geometry):
    """Extract ee.Geometry from various geometry-like inputs."""
    if isinstance(geometry, ee.FeatureCollection):
        return geometry.geometry()
    if isinstance(geometry, (ee.Feature, ee.element.Element)):
        return ee.Feature(geometry).geometry()
    if isinstance(geometry, ee.Geometry):
        return geometry
    # Fallback: wrap in ee.Feature to handle ComputedObject results
    # (e.g. fc.first() returns ee.ComputedObject, not ee.Feature)
    try:
        return ee.Feature(geometry).geometry()
    except Exception:
        return ee.Geometry(geometry)


def _is_multi_feature(geometry):
    """Check if geometry is a multi-feature FeatureCollection."""
    if not isinstance(geometry, ee.FeatureCollection):
        return False
    try:
        return geometry.size().getInfo() > 1
    except Exception:
        return False


def _mosaic_by_date(col):
    """Mosaic a tiled ImageCollection by unique date.

    Groups images by ``system:time_start`` (truncated to day) and mosaics
    each group into a single image.  This handles tiled datasets like LCMS
    that have multiple spatial tiles per time step.

    Args:
        col: ``ee.ImageCollection``.

    Returns:
        ee.ImageCollection: One image per unique date, sorted by time.
    """
    # Get distinct dates
    def _add_date_millis(img):
        d = ee.Date(img.get("system:time_start"))
        # Truncate to start of day
        day_start = ee.Date.fromYMD(d.get("year"), d.get("month"), d.get("day"))
        return img.set("date_millis", day_start.millis())

    col = col.map(_add_date_millis)
    distinct_dates = col.aggregate_array("date_millis").distinct().sort()

    def _mosaic_date(date_millis):
        date_millis = ee.Number(date_millis)
        filtered = col.filter(ee.Filter.eq("date_millis", date_millis))
        mosaic = filtered.mosaic()
        return mosaic.set("system:time_start", date_millis) \
                      .copyProperties(filtered.first())

    return ee.ImageCollection(distinct_dates.map(_mosaic_date))

clip_to_geometry=True,