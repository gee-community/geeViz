"""
Unified theme system for geeViz output libraries.

Provides a :class:`Theme` class that holds all resolved color values for
backgrounds, text, accents, borders, and chart styling.  Used by
``charts``, ``thumbs``, and ``reports`` for consistent colors.

Usage::

    from geeViz.outputLib.themes import get_theme

    # Named presets
    dark  = get_theme("dark")
    light = get_theme("light")
    teal  = get_theme("teal")

    # Auto-generate from a single color
    red_bg = get_theme(bg_color="#F00")           # dark text auto-picked
    custom = get_theme(bg_color="#1a1a2e", font_color="#eee")

    # Access colors in different formats
    dark.bg_hex          # '#272822'
    dark.bg_rgb          # (39, 40, 34)
    dark.text_hex        # '#f8f8f2'
    dark.is_dark         # True
    dark.grid_rgba       # 'rgba(248,248,242,0.15)'
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

from geeViz.outputLib._colors import resolve_color, luminance, to_hex, to_rgba, blend

import colorsys


# ---------------------------------------------------------------------------
#  Color derivation helpers
# ---------------------------------------------------------------------------
def _rgb_to_hsl(rgb):
    """Convert an RGB color tuple to HSL representation.

    Converts a color from the ``(R, G, B)`` color space (each component
    in the 0--255 range) to ``(H, S, L)`` where H is in degrees (0--360)
    and S and L are floating-point values in the 0--1 range.  Internally
    delegates to :func:`colorsys.rgb_to_hls` with appropriate rescaling.

    Args:
        rgb (tuple): An ``(R, G, B)`` tuple with integer values in the
            range 0--255.

    Returns:
        tuple: A ``(H, S, L)`` tuple where *H* is a float in 0--360 and
        *S* and *L* are floats in 0--1.

    Example:
        >>> _rgb_to_hsl((255, 0, 0))
        (0.0, 1.0, 0.5)
    """
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, s, l


def _hsl_to_rgb(h, s, l):
    """Convert an HSL color to an RGB tuple.

    Converts from the ``(H, S, L)`` color space back to ``(R, G, B)``
    with integer components in the 0--255 range.  Internally delegates
    to :func:`colorsys.hls_to_rgb` with appropriate rescaling.

    Args:
        h (float): Hue in degrees, 0--360.
        s (float): Saturation, 0--1.
        l (float): Lightness, 0--1.

    Returns:
        tuple: An ``(R, G, B)`` tuple with integer values in the range
        0--255.

    Example:
        >>> _hsl_to_rgb(0.0, 1.0, 0.5)
        (255, 0, 0)
    """
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l, s)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def _is_grayscale(rgb):
    """Check whether a color is approximately grayscale.

    A color is considered grayscale when the difference between its
    maximum and minimum RGB channel values is less than 20.  This is
    used by the accent/highlight derivation helpers to decide whether
    to preserve a neutral palette or introduce chromatic shifts.

    Args:
        rgb (tuple): An ``(R, G, B)`` tuple with integer values in the
            range 0--255.

    Returns:
        bool: ``True`` if the color is roughly grayscale (i.e.,
        ``max(R, G, B) - min(R, G, B) < 20``), ``False`` otherwise.

    Example:
        >>> _is_grayscale((128, 130, 126))
        True
        >>> _is_grayscale((255, 0, 0))
        False
    """
    return max(rgb) - min(rgb) < 20


def _derive_accent(bg, text, is_dark):
    """Generate an accent color from background and text colors.

    For **grayscale** text the accent stays grayscale -- just a shade
    closer to the background (e.g. white text becomes a light gray accent,
    black text becomes a dark gray accent).  This is achieved by blending
    30 % toward the background color.

    For **chromatic** text the accent keeps the same hue but is pushed to
    higher saturation and a mid-range lightness suitable for headings or
    links.

    Args:
        bg (tuple): Background color as an ``(R, G, B)`` tuple (0--255).
        text (tuple): Primary text color as an ``(R, G, B)`` tuple (0--255).
        is_dark (bool): ``True`` if the background is dark, which
            influences the target lightness of the accent.

    Returns:
        tuple: An ``(R, G, B)`` accent color tuple (0--255).

    Example:
        >>> _derive_accent((39, 40, 34), (248, 248, 242), True)
        (185, 186, 180)
    """
    if _is_grayscale(text):
        # Grayscale path: blend 30% toward bg
        return blend(text, bg, 0.30)

    text_h, text_s, text_l = _rgb_to_hsl(text)
    accent_h = text_h
    accent_s = max(0.75, min(0.95, text_s + 0.55))
    if is_dark:
        accent_l = max(0.45, min(0.60, 0.55))
    else:
        accent_l = max(0.35, min(0.50, 0.42))
    return _hsl_to_rgb(accent_h, accent_s, accent_l)


def _derive_highlight(bg, text, is_dark, accent):
    """Generate a highlight color from background, text, and accent colors.

    The highlight is a subtler, brighter variant of the accent color used
    for emphasis elements such as hover states or secondary headings.

    For **grayscale** text the highlight is a smaller step toward the
    background than the accent (15 % blend vs. 30 %), keeping it closer
    to the original font color.

    For **chromatic** text the highlight takes the accent's hue and
    increases its lightness and saturation slightly.

    Args:
        bg (tuple): Background color as an ``(R, G, B)`` tuple (0--255).
        text (tuple): Primary text color as an ``(R, G, B)`` tuple (0--255).
        is_dark (bool): ``True`` if the background is dark, which
            influences the target lightness of the highlight.
        accent (tuple): The previously derived accent color as an
            ``(R, G, B)`` tuple (0--255).

    Returns:
        tuple: An ``(R, G, B)`` highlight color tuple (0--255).

    Example:
        >>> accent = _derive_accent((39, 40, 34), (248, 248, 242), True)
        >>> _derive_highlight((39, 40, 34), (248, 248, 242), True, accent)
        (217, 217, 211)
    """
    if _is_grayscale(text):
        # Grayscale path: blend 15% toward bg (subtler than accent)
        return blend(text, bg, 0.15)

    acc_h, acc_s, acc_l = _rgb_to_hsl(accent)
    highlight_h = acc_h
    highlight_s = min(1.0, acc_s + 0.08)
    if is_dark:
        highlight_l = min(0.78, acc_l + 0.18)
    else:
        highlight_l = min(0.62, acc_l + 0.14)
    return _hsl_to_rgb(highlight_h, highlight_s, highlight_l)


# ---------------------------------------------------------------------------
#  Theme class
# ---------------------------------------------------------------------------
class Theme:
    """Resolved color theme for geeViz visualizations.

    A ``Theme`` holds all of the resolved color values needed to style
    charts, thumbnails, reports, and other geeViz outputs consistently.
    All colors are stored internally as ``(R, G, B)`` tuples with integer
    components in the 0--255 range.  Convenience properties provide
    hex-string, RGB-tuple, and RGBA-string formats for direct use in
    Plotly layouts, HTML/CSS, and Pillow operations.

    Colors that are not explicitly provided to the constructor are
    automatically derived from the ``bg`` and ``text`` colors using
    perceptually reasonable blending and HSL manipulation.

    Attributes:
        bg (tuple): Background color as an ``(R, G, B)`` tuple.
        text (tuple): Primary text/foreground color as an ``(R, G, B)`` tuple.
        accent (tuple): Accent color for headings and links as an
            ``(R, G, B)`` tuple.  Derived from ``text`` if not provided.
        highlight (tuple): Highlight/emphasis color as an ``(R, G, B)``
            tuple.  Derived from ``accent`` if not provided.
        surface (tuple): Card or panel background color, slightly offset
            from ``bg``, as an ``(R, G, B)`` tuple.
        border (tuple): Border and table-line color as an ``(R, G, B)``
            tuple.
        divider (tuple): Subtle separator/divider color as an ``(R, G, B)``
            tuple.
        swatch_outline (tuple): Legend swatch outline color as an
            ``(R, G, B)`` tuple.
        muted_text (tuple): Secondary/caption text color as an
            ``(R, G, B)`` tuple.
        is_dark (bool): ``True`` if this is a dark-background theme
            (background luminance < 128).

    Example:
        >>> from geeViz.outputLib.themes import Theme
        >>> t = Theme(bg=(39, 40, 34), text=(248, 248, 242))
        >>> t.is_dark
        True
        >>> t.bg_hex
        '#272822'
    """

    __slots__ = (
        "bg", "text", "accent", "highlight", "surface", "border",
        "divider", "swatch_outline", "muted_text", "is_dark",
        "title_font_size", "label_font_size", "font_family",
    )

    def __init__(self, bg, text, accent=None, highlight=None,
                 surface=None, border=None, divider=None,
                 swatch_outline=None, muted_text=None, is_dark=None,
                 title_font_size=18, label_font_size=12,
                 font_family="Roboto Condensed"):
        """Initialize a Theme with explicit or auto-derived colors.

        Any color parameter that is ``None`` will be automatically
        derived from ``bg`` and ``text`` using perceptually reasonable
        defaults (blending, HSL shifts, etc.).

        Args:
            bg (tuple): Background color as an ``(R, G, B)`` tuple or
                list with integer values 0--255.
            text (tuple): Primary text color as an ``(R, G, B)`` tuple or
                list with integer values 0--255.
            accent (tuple, optional): Accent color for headings/links.
                Defaults to ``None`` (auto-derived from ``text``).
            highlight (tuple, optional): Highlight/emphasis color.
                Defaults to ``None`` (auto-derived from ``accent``).
            surface (tuple, optional): Card/panel background color.
                Defaults to ``None`` (auto-derived by blending ``bg``
                slightly toward white or black).
            border (tuple, optional): Border/table-line color. Defaults
                to ``None`` (30 % blend of ``bg`` toward ``text``).
            divider (tuple, optional): Subtle separator color. Defaults
                to ``None`` (15 % blend of ``bg`` toward ``text``).
            swatch_outline (tuple, optional): Legend swatch outline color.
                Defaults to ``None`` (25 % blend of ``bg`` toward ``text``).
            muted_text (tuple, optional): Secondary/caption text color.
                Defaults to ``None`` (55 % blend of ``bg`` toward ``text``).
            is_dark (bool, optional): Force dark/light classification.
                Defaults to ``None`` (auto-detected from ``bg`` luminance).

        Returns:
            Theme: A fully resolved theme instance.

        Example:
            >>> t = Theme(bg=(0, 0, 0), text=(255, 255, 255))
            >>> t.is_dark
            True
            >>> t.border  # auto-derived
            (77, 77, 77)
        """
        self.bg = tuple(bg)
        self.text = tuple(text)
        self.is_dark = luminance(self.bg) < 128 if is_dark is None else is_dark

        # Defaults derived from bg/text
        white = (255, 255, 255)
        black = (0, 0, 0)

        if accent is not None:
            self.accent = tuple(accent)
        else:
            self.accent = _derive_accent(self.bg, self.text, self.is_dark)

        if highlight is not None:
            self.highlight = tuple(highlight)
        else:
            self.highlight = _derive_highlight(self.bg, self.text, self.is_dark, self.accent)

        if surface is not None:
            self.surface = tuple(surface)
        else:
            # Slightly offset from bg
            self.surface = blend(self.bg, white, 0.06) if self.is_dark else blend(self.bg, black, 0.04)

        if border is not None:
            self.border = tuple(border)
        else:
            self.border = blend(self.bg, self.text, 0.3)

        if divider is not None:
            self.divider = tuple(divider)
        else:
            self.divider = blend(self.bg, self.text, 0.15)

        if swatch_outline is not None:
            self.swatch_outline = tuple(swatch_outline)
        else:
            self.swatch_outline = blend(self.bg, self.text, 0.25)

        if muted_text is not None:
            self.muted_text = tuple(muted_text)
        else:
            self.muted_text = blend(self.bg, self.text, 0.55)

        # Font sizing
        self.title_font_size = title_font_size
        self.label_font_size = label_font_size
        self.font_family = font_family

    # --- Font convenience properties --------------------------------------
    @property
    def legend_title_font_size(self):
        """Legend title font size (1.15x label size)."""
        return max(self.label_font_size, int(self.label_font_size * 1.15))

    # --- Hex properties ---------------------------------------------------
    @property
    def bg_hex(self):
        """Return the background color as a hex string.

        Returns:
            str: Background color in ``'#RRGGBB'`` format.

        Example:
            >>> Theme(bg=(39, 40, 34), text=(248, 248, 242)).bg_hex
            '#272822'
        """
        return to_hex(self.bg)

    @property
    def text_hex(self):
        """Return the text color as a hex string.

        Returns:
            str: Text color in ``'#RRGGBB'`` format.

        Example:
            >>> Theme(bg=(39, 40, 34), text=(248, 248, 242)).text_hex
            '#f8f8f2'
        """
        return to_hex(self.text)

    @property
    def accent_hex(self):
        """Return the accent color as a hex string.

        Returns:
            str: Accent color in ``'#RRGGBB'`` format.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255), accent=(0, 191, 165)).accent_hex
            '#00bfa5'
        """
        return to_hex(self.accent)

    @property
    def highlight_hex(self):
        """Return the highlight color as a hex string.

        Returns:
            str: Highlight color in ``'#RRGGBB'`` format.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255), highlight=(255, 131, 76)).highlight_hex
            '#ff834c'
        """
        return to_hex(self.highlight)

    @property
    def surface_hex(self):
        """Return the surface/panel color as a hex string.

        Returns:
            str: Surface color in ``'#RRGGBB'`` format.

        Example:
            >>> Theme(bg=(255, 255, 255), text=(0, 0, 0)).surface_hex
            '#f5f5f5'
        """
        return to_hex(self.surface)

    @property
    def border_hex(self):
        """Return the border color as a hex string.

        Returns:
            str: Border color in ``'#RRGGBB'`` format.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).border_hex
            '#4d4d4d'
        """
        return to_hex(self.border)

    @property
    def divider_hex(self):
        """Return the divider color as a hex string.

        Returns:
            str: Divider color in ``'#RRGGBB'`` format.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).divider_hex
            '#262626'
        """
        return to_hex(self.divider)

    @property
    def muted_text_hex(self):
        """Return the muted text color as a hex string.

        Returns:
            str: Muted text color in ``'#RRGGBB'`` format.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).muted_text_hex
            '#8c8c8c'
        """
        return to_hex(self.muted_text)

    @property
    def swatch_outline_hex(self):
        """Return the swatch outline color as a hex string.

        Returns:
            str: Swatch outline color in ``'#RRGGBB'`` format.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).swatch_outline_hex
            '#404040'
        """
        return to_hex(self.swatch_outline)

    # --- RGB aliases (explicit for readability) ----------------------------
    @property
    def bg_rgb(self):
        """Return the background color as an RGB tuple.

        This is an alias for the :attr:`bg` attribute, provided for
        symmetry with the ``*_hex`` properties.

        Returns:
            tuple: Background color as ``(R, G, B)`` with values 0--255.

        Example:
            >>> Theme(bg=(39, 40, 34), text=(248, 248, 242)).bg_rgb
            (39, 40, 34)
        """
        return self.bg

    @property
    def text_rgb(self):
        """Return the text color as an RGB tuple.

        This is an alias for the :attr:`text` attribute, provided for
        symmetry with the ``*_hex`` properties.

        Returns:
            tuple: Text color as ``(R, G, B)`` with values 0--255.

        Example:
            >>> Theme(bg=(39, 40, 34), text=(248, 248, 242)).text_rgb
            (248, 248, 242)
        """
        return self.text

    # --- RGBA convenience --------------------------------------------------
    @property
    def grid_rgba(self):
        """Return a chart gridline color with appropriate alpha.

        Uses an alpha of 0.15 for dark themes and 0.1 for light themes
        to keep gridlines subtle against the background.

        Returns:
            str: RGBA color string, e.g. ``'rgba(248,248,242,0.15)'``.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).grid_rgba
            'rgba(255,255,255,0.15)'
        """
        a = 0.15 if self.is_dark else 0.1
        return to_rgba(self.text, a)

    @property
    def line_rgba(self):
        """Return a chart axis line color with appropriate alpha.

        Uses an alpha of 0.25 for dark themes and 0.2 for light themes.

        Returns:
            str: RGBA color string, e.g. ``'rgba(248,248,242,0.25)'``.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).line_rgba
            'rgba(255,255,255,0.25)'
        """
        a = 0.25 if self.is_dark else 0.2
        return to_rgba(self.text, a)

    @property
    def zeroline_rgba(self):
        """Return a chart zero-line color with appropriate alpha.

        Uses an alpha of 0.2 for dark themes and 0.15 for light themes.

        Returns:
            str: RGBA color string, e.g. ``'rgba(248,248,242,0.2)'``.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).zeroline_rgba
            'rgba(255,255,255,0.2)'
        """
        a = 0.2 if self.is_dark else 0.15
        return to_rgba(self.text, a)

    @property
    def surface_rgba(self):
        """Return the surface color with alpha for table row striping.

        Uses an alpha of 0.5 for dark themes and 0.3 for light themes
        so that alternating rows are visible but not overpowering.

        Returns:
            str: RGBA color string for the surface, e.g.
            ``'rgba(55,46,44,0.5)'``.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).surface_rgba
            'rgba(15,15,15,0.5)'
        """
        a = 0.5 if self.is_dark else 0.3
        return to_rgba(self.surface, a)

    @property
    def error_bg_rgba(self):
        """Return an error-box background color with appropriate alpha.

        Uses the highlight color with an alpha of 0.1 for dark themes
        and 0.08 for light themes, producing a tinted but unobtrusive
        error background.

        Returns:
            str: RGBA color string for the error background.

        Example:
            >>> t = Theme(bg=(0, 0, 0), text=(255, 255, 255),
            ...           highlight=(255, 0, 0))
            >>> t.error_bg_rgba
            'rgba(255,0,0,0.1)'
        """
        a = 0.1 if self.is_dark else 0.08
        return to_rgba(self.highlight, a)

    @property
    def tooltip_bg_rgba(self):
        """Return a tooltip background as a semi-transparent inverse of bg.

        Dark themes get a near-black tooltip (``rgba(0,0,0,0.85)``);
        light themes get a near-white tooltip (``rgba(255,255,255,0.92)``).

        Returns:
            str: RGBA color string for tooltip backgrounds.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).tooltip_bg_rgba
            'rgba(0,0,0,0.85)'
        """
        if self.is_dark:
            return "rgba(0,0,0,0.85)"
        return "rgba(255,255,255,0.92)"

    @property
    def button_bg_rgba(self):
        """Return a toolbar button background color.

        Uses the muted text color at 15 % opacity.

        Returns:
            str: RGBA color string for button backgrounds.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).button_bg_rgba
            'rgba(140,140,140,0.15)'
        """
        return to_rgba(self.muted_text, 0.15)

    @property
    def button_hover_rgba(self):
        """Return a toolbar button hover background color.

        Uses the muted text color at 30 % opacity.

        Returns:
            str: RGBA color string for button hover backgrounds.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).button_hover_rgba
            'rgba(140,140,140,0.3)'
        """
        return to_rgba(self.muted_text, 0.3)

    @property
    def button_border_rgba(self):
        """Return a toolbar button border color.

        Uses the muted text color at 30 % opacity.

        Returns:
            str: RGBA color string for button borders.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).button_border_rgba
            'rgba(140,140,140,0.3)'
        """
        return to_rgba(self.muted_text, 0.3)

    @property
    def link_stroke_rgba(self):
        """Return a Sankey link stroke color for gradient edges.

        Dark themes use a faint white stroke (``rgba(255,255,255,0.15)``);
        light themes use a faint black stroke (``rgba(0,0,0,0.08)``).

        Returns:
            str: RGBA color string for Sankey link strokes.

        Example:
            >>> Theme(bg=(0, 0, 0), text=(255, 255, 255)).link_stroke_rgba
            'rgba(255,255,255,0.15)'
        """
        if self.is_dark:
            return "rgba(255,255,255,0.15)"
        return "rgba(0,0,0,0.08)"

    def __repr__(self):
        """Return a human-readable string representation of the theme.

        Returns:
            str: A string of the form
            ``Theme(bg='#272822', text='#f8f8f2', is_dark=True)``.

        Example:
            >>> repr(Theme(bg=(39, 40, 34), text=(248, 248, 242)))
            "Theme(bg='#272822', text='#f8f8f2', is_dark=True)"
        """
        return f"Theme(bg={self.bg_hex!r}, text={self.text_hex!r}, is_dark={self.is_dark})"


# ---------------------------------------------------------------------------
#  Preset themes
# ---------------------------------------------------------------------------
_PRESETS = {}


def register_preset(name, theme):
    """Register a named theme preset for later retrieval via :func:`get_theme`.

    Presets are stored in a module-level dictionary keyed by the
    lower-cased name.  Calling this function with a name that already
    exists will overwrite the previous preset.

    Args:
        name (str): Preset name (e.g. ``"dark"``, ``"ocean"``).  Stored
            in lower case.
        theme (Theme): A :class:`Theme` instance to register.

    Returns:
        None

    Example:
        >>> t = Theme(bg=(0, 0, 0), text=(255, 255, 255))
        >>> register_preset("midnight", t)
        >>> get_theme("midnight").bg_hex
        '#000000'
    """
    _PRESETS[name.lower()] = theme


# Monokai dark (matches original geeViz dark theme)
register_preset("dark", Theme(
    bg=(39, 40, 34),            # #272822
    text=(248, 248, 242),       # #f8f8f2
    accent=(0, 191, 165),       # teal_80
    highlight=(255, 131, 76),   # orange
    surface=(55, 46, 44),       # brown_100
    border=(111, 98, 89),       # brown_80
    divider=(64, 64, 58),
    swatch_outline=(90, 90, 82),
    muted_text=(150, 139, 131), # brown_50
))

# Clean light
register_preset("light", Theme(
    bg=(255, 255, 255),         # #ffffff
    text=(55, 46, 44),          # #372e2c (brown_100)
    accent=(0, 137, 123),       # teal_100
    highlight=(255, 103, 0),    # orange_100
    surface=(245, 243, 240),    # #f5f3f0
    border=(214, 209, 202),     # brown_10
    divider=(210, 210, 210),
    swatch_outline=(180, 180, 180),
    muted_text=(150, 139, 131), # brown_50
))

# Teal dark
register_preset("teal", Theme(
    bg=(0, 51, 43),             # deep teal
    text=(178, 236, 228),       # teal_30
    accent=(128, 223, 210),     # teal_50
    highlight=(255, 146, 72),   # orange_80
    surface=(0, 77, 64),        # darker teal
    border=(0, 120, 100),
    divider=(0, 90, 75),
    swatch_outline=(0, 110, 92),
    muted_text=(100, 180, 168),
))


# ---------------------------------------------------------------------------
#  Auto-derive a theme from a single color
# ---------------------------------------------------------------------------
def _auto_theme(bg_color=None, font_color=None):
    """Build a Theme by auto-deriving missing colors from those provided.

    This function implements the automatic color derivation logic used
    when :func:`get_theme` is called without a preset name.  It follows
    these rules:

    - **Both given**: Use ``bg_color`` and ``font_color`` as-is; derive
      accent, highlight, surface, border, etc. via the :class:`Theme`
      constructor defaults.
    - **Only** ``bg_color``: Pick dark or light text based on the
      background luminance.
    - **Only** ``font_color``: Pick a dark or light background based on
      the font luminance.
    - **Neither**: Return a fresh :class:`Theme` using the ``"dark"``
      preset's background and text (accent/highlight are re-derived).

    Args:
        bg_color (str or tuple, optional): Background color in any format
            accepted by :func:`resolve_color` (hex string, color name,
            or ``(R, G, B)`` tuple). Defaults to ``None``.
        font_color (str or tuple, optional): Text/font color in any format
            accepted by :func:`resolve_color`. Defaults to ``None``.

    Returns:
        Theme: A fully resolved :class:`Theme` instance.

    Example:
        >>> t = _auto_theme(bg_color="#1a1a2e")
        >>> t.is_dark
        True
        >>> t = _auto_theme(font_color="yellow")
        >>> t.is_dark
        True
    """
    if bg_color is None and font_color is None:
        # Default dark — derive accent/highlight from the default text
        p = _PRESETS["dark"]
        return Theme(bg=p.bg, text=p.text)

    if bg_color is not None:
        bg = resolve_color(bg_color)
    else:
        # Derive bg from font_color: opposite luminance
        fc = resolve_color(font_color)
        bg = (20, 20, 20) if luminance(fc) >= 128 else (250, 250, 250)

    if font_color is not None:
        text = resolve_color(font_color)
    else:
        # Derive text from bg: high contrast
        text = (248, 248, 242) if luminance(bg) < 128 else (55, 46, 44)

    return Theme(bg=bg, text=text)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------
def get_theme(theme=None, bg_color=None, font_color=None):
    """Resolve a :class:`Theme` from a preset name, instance, or custom colors.

    This is the main entry point for obtaining a theme.  It accepts a
    preset name (``"dark"``, ``"light"``, ``"teal"``), a :class:`Theme`
    instance (pass-through), a color string or tuple (treated as
    ``bg_color``), or ``None``.  When ``bg_color`` and/or ``font_color``
    are also supplied alongside a preset, they override the preset's
    background and text colors respectively, and accent/highlight are
    re-derived from the new colors.

    Args:
        theme (str or Theme or tuple or None, optional): A preset name
            (``"dark"``, ``"light"``, ``"teal"``), a :class:`Theme`
            instance (returned as-is unless overrides are given), a color
            string or ``(R, G, B)`` tuple (treated as ``bg_color``), or
            ``None``. Defaults to ``None``.
        bg_color (str or tuple, optional): Background color override in
            any format accepted by :func:`resolve_color`. Overrides the
            preset's background when combined with ``theme``. Defaults
            to ``None``.
        font_color (str or tuple, optional): Text/font color override in
            any format accepted by :func:`resolve_color`. Overrides the
            preset's text when combined with ``theme``. Defaults to
            ``None``.

    Returns:
        Theme: A fully resolved :class:`Theme` instance.

    Example:
        >>> get_theme("dark").bg_hex
        '#272822'
        >>> get_theme("light").is_dark
        False
        >>> get_theme(bg_color="#F00").is_dark
        True
        >>> get_theme("dark", font_color="yellow").text_hex
        '#ffff00'
    """
    # If theme is already a Theme instance, optionally override colors
    if isinstance(theme, Theme):
        base = theme
    elif isinstance(theme, str):
        key = theme.lower()
        if key in _PRESETS:
            base = _PRESETS[key]
        else:
            # Treat as a bg_color string
            return _auto_theme(bg_color=theme, font_color=font_color)
    elif isinstance(theme, (list, tuple)):
        # Treat as bg_color tuple
        return _auto_theme(bg_color=theme, font_color=font_color)
    elif theme is None:
        return _auto_theme(bg_color=bg_color, font_color=font_color)
    else:
        return _auto_theme(bg_color=bg_color, font_color=font_color)

    # Apply overrides to a preset — re-derive accent/highlight from new colors
    if bg_color is not None or font_color is not None:
        bg = resolve_color(bg_color) if bg_color is not None else base.bg
        text = resolve_color(font_color) if font_color is not None else base.text
        return Theme(bg=bg, text=text)

    return base


# ---------------------------------------------------------------------------
#  Plotly integration
# ---------------------------------------------------------------------------
def apply_plotly_theme(fig, theme=None, bg_color=None, font_color=None):
    """Apply a theme's colors to a Plotly figure in-place.

    Resolves a :class:`Theme` from the provided arguments (using
    :func:`get_theme`) and then updates the figure's layout -- including
    paper/plot background, font colors, axis grid/line/zeroline colors,
    title, legend, and annotation colors -- to match the theme.

    Args:
        fig (plotly.graph_objects.Figure): The Plotly figure to style.
            Modified in-place.
        theme (str or Theme or tuple or None, optional): Preset name,
            :class:`Theme` instance, or color string/tuple.  Passed
            through to :func:`get_theme`. Defaults to ``None``.
        bg_color (str or tuple, optional): Background color override.
            Defaults to ``None``.
        font_color (str or tuple, optional): Font color override.
            Defaults to ``None``.

    Returns:
        plotly.graph_objects.Figure: The same figure, modified in-place,
        for method chaining convenience.

    Example:
        >>> import plotly.graph_objects as go
        >>> fig = go.Figure(data=[go.Bar(x=[1, 2], y=[3, 4])])
        >>> fig = apply_plotly_theme(fig, "dark")
        >>> fig.layout.paper_bgcolor
        '#272822'
    """
    t = get_theme(theme, bg_color=bg_color, font_color=font_color)

    fig.update_layout(
        paper_bgcolor=t.bg_hex,
        plot_bgcolor=t.bg_hex,
        font=dict(color=t.text_hex),
    )

    axis_kwargs = dict(
        gridcolor=t.grid_rgba,
        linecolor=t.line_rgba,
        zerolinecolor=t.zeroline_rgba,
        tickfont=dict(color=t.text_hex),
        title_font=dict(color=t.text_hex),
    )
    fig.update_xaxes(**axis_kwargs)
    fig.update_yaxes(**axis_kwargs)

    # Update title, legend, and annotations
    if fig.layout.title and fig.layout.title.text:
        fig.update_layout(title_font_color=t.text_hex)
    fig.update_layout(legend=dict(font=dict(color=t.text_hex)))

    for ann in fig.layout.annotations or []:
        ann.font.color = t.text_hex

    return fig
