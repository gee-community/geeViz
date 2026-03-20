"""
Low-level color utilities for geeViz output libraries.

Provides conversion between color formats (named, hex, RGB tuples, CSS rgba)
and basic color math (luminance, blending).
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


def resolve_color(color):
    """Convert any color specification to an ``(R, G, B)`` tuple.

    Accepts PIL/CSS named colors (``"red"``), hex strings (``"#F00"``,
    ``"#ff0000"``), and RGB tuples (pass-through).

    Args:
        color: A color name string, hex string, or ``(R, G, B)`` tuple.

    Returns:
        tuple: ``(R, G, B)`` with values 0-255.
    """
    if isinstance(color, (list, tuple)):
        return tuple(int(c) for c in color[:3])
    if isinstance(color, str):
        s = color.strip()
        # Try hex parse first (avoids PIL dependency for common cases)
        if s.startswith("#"):
            h = s[1:]
            if len(h) == 3:
                h = h[0] * 2 + h[1] * 2 + h[2] * 2
            if len(h) == 6:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        # Named color — fall back to PIL
        try:
            from PIL import ImageColor
            return ImageColor.getrgb(s)[:3]
        except Exception:
            pass
    # Fallback
    return (0, 0, 0)


def luminance(rgb):
    """BT.601 perceived luminance (0-255) from an RGB tuple."""
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def to_hex(rgb):
    """Convert ``(R, G, B)`` tuple to ``#rrggbb`` hex string."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def to_rgba(rgb, alpha=1.0):
    """Convert ``(R, G, B)`` tuple to ``rgba(r,g,b,a)`` CSS string."""
    return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha})"


def blend(c1, c2, t):
    """Linearly interpolate between two RGB tuples. t=0 -> c1, t=1 -> c2."""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
