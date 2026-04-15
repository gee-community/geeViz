"""
Zonal Summary & Charting Library for GEE

geeViz.outputLib.charts provides a Python pipeline for running zonal statistics on
ee.Image / ee.ImageCollection objects and producing Plotly charts (time series,
bar, sankey). It mirrors the logic in the geeView JS frontend so that both
human users and AI agents have a clean, efficient API for this common workflow.

Quick start:

>>> import geeViz.geeView as gv
>>> from geeViz.outputLib import charts as cl
>>> ee = gv.ee
>>> study_area = ee.Geometry.Polygon(
...     [[[-106, 39.5], [-105, 39.5], [-105, 40.5], [-106, 40.5]]]
... )
>>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")
>>> df, fig = cl.summarize_and_chart(
...     lcms.select(['Land_Cover']),
...     study_area,
...     stacked=True,
... )
>>> print(df.to_markdown())
>>> fig.write_html("chart.html", include_plotlyjs="cdn")

See :func:`summarize_and_chart` for the full API and more examples.
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

# --------------------------------------------------------------------------
#  Zonal summary + charting pipeline (ported from area-charting.js)
# --------------------------------------------------------------------------

import math
import os
import ee
import pandas
import plotly.graph_objects as go
from geeViz.gee2Pandas import robust_featureCollection_to_df


###########################################################################
#                              Constants
###########################################################################

SPLIT_STR = "----"
SANKEY_TRANSITION_SEP = "0990"

DEFAULT_PLOT_BGCOLOR = "rgba(0,0,0,0)"
DEFAULT_PLOT_FONT = "Roboto"
DEFAULT_CHART_WIDTH = 800
DEFAULT_CHART_HEIGHT = 600

#: Valid chart type strings for ``chart_type`` / ``chart_types`` parameters.
#: Use these in ``summarize_and_chart(chart_type=...)`` or
#: ``Report.add_section(chart_types=[...])``.
CHART_TYPES = [
    "bar",
    "stacked_bar",
    "line",
    "line+markers",
    "stacked_line",
    "stacked_line+markers",
    "donut",
    "scatter",
    "sankey",
]


def _legend_kwargs(legend_position):
    """Return Plotly legend layout dict.

    Args:
        legend_position: Either a dict of raw Plotly legend properties
            (e.g. ``{"orientation": "h", "x": 0.5, "y": -0.1}``),
            or ``None`` for Plotly defaults.

    Returns:
        dict: Plotly ``legend`` layout dict.
    """
    if legend_position is None or legend_position == "right":
        return {}
    if isinstance(legend_position, dict):
        return dict(legend_position)
    return {}


AREA_FORMAT_DICT = {
    "Percentage": {"mult": None, "label": "% Area", "places": 2, "scale": 30},
    "Hectares": {"mult": 0.09, "label": "ha", "places": 0, "scale": 30},
    "Acres": {"mult": 0.222395, "label": "Acres", "places": 0, "scale": 30},
    "Pixels": {"mult": 1.0, "label": "Pixels", "places": 0, "scale": 30},
}


###########################################################################
#                          Private helpers
###########################################################################

# Unified chart_type values and parser
_VALID_CHART_TYPES = {
    "bar", "stacked_bar",
    "line", "stacked_line",
    "line+markers", "stacked_line+markers",
}


def _parse_chart_type(chart_type):
    """Parse a unified *chart_type* string into ``(plotly_mode, is_stacked)``.

    Args:
        chart_type (str): One of ``"bar"``, ``"stacked_bar"``, ``"line"``,
            ``"stacked_line"``, ``"line+markers"``,
            ``"stacked_line+markers"``.

    Returns:
        tuple: ``(plotly_mode, is_stacked)`` where *plotly_mode* is
        ``"bar"``, ``"lines"``, or ``"lines+markers"`` and *is_stacked* is
        a bool.
    """
    ct = str(chart_type).lower().strip()

    # Backward compat: old values without stacked_ prefix
    # "lines" -> "line", "lines+markers" -> "line+markers"
    if ct == "lines":
        ct = "line"
    elif ct == "lines+markers":
        ct = "line+markers"

    is_stacked = ct.startswith("stacked_")
    base = ct.removeprefix("stacked_")

    mode_map = {"bar": "bar", "line": "lines", "line+markers": "lines+markers"}
    plotly_mode = mode_map.get(base, "lines+markers")
    return plotly_mode, is_stacked


def _ensure_hex_color(color):
    """Prepend '#' if missing from a hex color string."""
    if color is None:
        return None
    color = str(color)
    if not color.startswith("#"):
        color = "#" + color
    return color


def _title_to_filename(title):
    """Convert a chart title to a safe filename (no extension)."""
    import re
    if not title:
        return "chart"
    return re.sub(r'[^a-zA-Z0-9_-]', '_', title).strip('_')[:80] or "chart"


def _plotly_download_config(fig):
    """Build Plotly config dict with download filename derived from chart title."""
    title = ""
    if fig.layout.title and fig.layout.title.text:
        title = fig.layout.title.text
    fname = _title_to_filename(title)
    return {"toImageButtonOptions": {"filename": fname}}


def _set_download_filename(fig):
    """Patch a Plotly figure so ``fig.show()`` and ``fig.to_html()`` use the title as download filename.

    Wraps both methods to inject ``config={'toImageButtonOptions': {'filename': ...}}``
    automatically, so users don't need to pass config manually.
    """
    _orig_show = fig.show
    _orig_to_html = fig.to_html

    def _patched_show(*args, **kwargs):
        if "config" not in kwargs:
            kwargs["config"] = _plotly_download_config(fig)
        else:
            cfg = kwargs["config"]
            if "toImageButtonOptions" not in cfg:
                cfg["toImageButtonOptions"] = _plotly_download_config(fig)["toImageButtonOptions"]
        return _orig_show(*args, **kwargs)

    def _patched_to_html(*args, **kwargs):
        if "config" not in kwargs:
            kwargs["config"] = _plotly_download_config(fig)
        else:
            cfg = kwargs["config"]
            if "toImageButtonOptions" not in cfg:
                cfg["toImageButtonOptions"] = _plotly_download_config(fig)["toImageButtonOptions"]
        return _orig_to_html(*args, **kwargs)

    fig.show = _patched_show
    fig.to_html = _patched_to_html
    return fig


def _thin_tick_vals(tick_vals, max_ticks=10):
    """Return a subset of *tick_vals* so that at most *max_ticks* are shown.

    Chooses a stride of 1, 2, 5, 10, 20, 50, … (the smallest that keeps
    the count at or below *max_ticks*), always including the first and last
    values.  Returns ``None`` when no thinning is needed.
    """
    if max_ticks is None or max_ticks <= 0 or len(tick_vals) <= max_ticks:
        return None  # no thinning needed
    n = len(tick_vals)
    # Generate nice strides: 1, 2, 5, 10, 20, 50, 100, 200, 500, …
    magnitude = 1
    while magnitude < n:
        for base in [1, 2, 5]:
            stride = base * magnitude
            # Ticks: always include first & last, plus every stride-th index
            kept = [tick_vals[0]] + [tick_vals[i] for i in range(stride, n - 1, stride)] + [tick_vals[-1]]
            if len(kept) <= max_ticks:
                return kept
        magnitude *= 10
    # Fallback: just first and last
    return [tick_vals[0], tick_vals[-1]]


def _interpolate_palette(palette, n):
    """Interpolate a color palette to *n* colors (continuous ramp).

    Given a list of hex color stops, linearly interpolate between them to
    produce exactly *n* evenly-spaced colors.  Matches the JS min/max/palette
    ramp behaviour for ordinal-thematic bar charts.
    """
    if not palette or n <= 0:
        return []
    palette = [_ensure_hex_color(c) for c in palette]
    if n == 1:
        return [palette[0]]
    if len(palette) >= n:
        # Down-sample evenly
        return [palette[round(i * (len(palette) - 1) / (n - 1))] for i in range(n)]

    out = []
    for i in range(n):
        t = i / (n - 1)  # 0 … 1
        pos = t * (len(palette) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(palette) - 1)
        frac = pos - lo
        c_lo = palette[lo].lstrip("#")
        c_hi = palette[hi].lstrip("#")
        # Expand 3-char hex to 6-char
        if len(c_lo) == 3:
            c_lo = "".join(ch * 2 for ch in c_lo)
        if len(c_hi) == 3:
            c_hi = "".join(ch * 2 for ch in c_hi)
        r = int(int(c_lo[0:2], 16) * (1 - frac) + int(c_hi[0:2], 16) * frac)
        g = int(int(c_lo[2:4], 16) * (1 - frac) + int(c_hi[2:4], 16) * frac)
        b = int(int(c_lo[4:6], 16) * (1 - frac) + int(c_hi[4:6], 16) * frac)
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return out


def _format_period(period):
    """Format a transition period list like [1985,1987] -> '1985-1987' or '1985' if equal."""
    if isinstance(period, (list, tuple)) and len(period) == 2:
        if period[0] == period[1]:
            return str(period[0])
        return f"{period[0]}-{period[1]}"
    return str(period)


from geeViz.outputLib import themes as _themes
from geeViz.outputLib._templates import (
    render_chart_style as _render_chart_style,
    render_d3_sankey as _render_d3_sankey,
)


_PLOTLY_CDN_URL = "https://cdnjs.cloudflare.com/ajax/libs/plotly.js/1.33.1/plotly.min.js"


def save_chart_html(fig, filename, include_plotlyjs=_PLOTLY_CDN_URL, sankey=False,
                    theme="dark", bg_color=None, font_color=None, **kwargs):
    """Save a chart to an HTML file.

    Accepts either a Plotly ``Figure`` or an HTML string (from
    ``summarize_and_chart(chart_type='sankey')``).  Applies a theme so
    all chart types have a consistent look.  Works both inside and
    outside the MCP sandbox.

    Args:
        fig: ``plotly.graph_objects.Figure`` or ``str`` (D3 sankey HTML
            from ``summarize_and_chart(chart_type='sankey')``).
        filename (str): Output filename (e.g. ``"chart.html"``). In the
            MCP sandbox, files are saved to ``generated_outputs/``.
        include_plotlyjs: How to include Plotly.js. Default ``"cdn"``.
        sankey (bool): Deprecated — ignored.  Sankey charts are now
            returned as HTML strings and detected automatically.
        theme: Theme preset name, :class:`~geeViz.outputLib.themes.Theme`
            instance, or color string. Default ``"dark"``.
        bg_color: Background color override.
        font_color: Font/text color override.

    Returns:
        str: Path to the saved file.

    Examples:
        >>> path = cl.save_chart_html(fig, "ndvi_trend.html")
        >>> path = cl.save_chart_html(sankey_html, "sankey.html")
        >>> path = cl.save_chart_html(fig, "chart.html", theme="light")
    """
    _t = _themes.get_theme(theme, bg_color=bg_color, font_color=font_color)
    # If fig is already an HTML string (from chart_sankey_d3), save directly
    if isinstance(fig, str):
        html = fig
    else:
        # Apply theme to a copy so we don't mutate the caller's figure
        import copy
        themed_fig = copy.deepcopy(fig)
        _themes.apply_plotly_theme(themed_fig, _t)
        html = themed_fig.to_html(
            full_html=True, include_plotlyjs=include_plotlyjs,
            config=_plotly_download_config(themed_fig),
        )
        # Inject body background style
        _chart_style = _render_chart_style(_t)
        if "</head>" in html:
            html = html.replace("</head>", _chart_style + "</head>")
        elif "<body>" in html:
            html = html.replace("<body>", "<body>" + _chart_style)

    # Try MCP sandbox save_file first, fall back to direct write
    import builtins as _builtins
    _save_fn = _builtins.__dict__.get("save_file") if hasattr(_builtins, "__dict__") else None
    if _save_fn is None:
        # Check if save_file is in the caller's globals (MCP REPL injects it)
        import inspect
        frame = inspect.currentframe()
        try:
            caller_globals = frame.f_back.f_globals if frame.f_back else {}
            _save_fn = caller_globals.get("save_file")
        finally:
            del frame

    if _save_fn is not None:
        return _save_fn(filename, html)
    else:
        # Outside MCP sandbox — direct file write
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
        return filename


def _find_browser():
    """Locate Edge or Chrome executable for headless screenshot rendering.

    Returns the path string if found, otherwise None.
    """
    import shutil
    import sys

    # Check PATH first (works cross-platform)
    for name in ("msedge", "microsoft-edge", "google-chrome", "chrome", "chromium"):
        path = shutil.which(name)
        if path:
            return path

    # Common install locations by platform
    if sys.platform == "win32":
        candidates = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/microsoft-edge",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]

    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _autocrop_png(png_bytes, padding=10):
    """Crop empty space from the bottom of a PNG image.

    Detects the background color from the bottom-left pixel and trims
    rows that are entirely that color. Adds ``padding`` pixels below
    the last content row.

    Args:
        png_bytes (bytes): Raw PNG data.
        padding (int): Pixels of padding to keep below content.

    Returns:
        bytes: Cropped PNG data.
    """
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(png_bytes))
        pixels = img.load()
        w, h = img.size

        # Sample background color from the bottom-left corner
        bg_color = pixels[0, h - 1]

        # Find the last row that has non-background content
        last_content_row = h - 1
        for y in range(h - 1, -1, -1):
            row_is_bg = all(pixels[x, y] == bg_color for x in range(0, w, 4))
            if not row_is_bg:
                last_content_row = y
                break

        crop_h = min(last_content_row + padding, h)
        if crop_h < h - 10:  # only crop if saving at least 10px
            img = img.crop((0, 0, w, crop_h))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return png_bytes  # fail-safe: return uncropped


def screenshot_url(url, width=1280, height=900, wait_seconds=12):
    """Capture a screenshot of a URL via headless Chrome using the DevTools Protocol (CDP).

    Unlike the simple ``--screenshot`` flag, this function connects to Chrome's
    DevTools WebSocket and collects:

    * JS console errors and warnings (``console.error`` / ``console.warn``)
    * Network failures (``net::ERR_*`` for any request)
    * HTTP 4xx / 5xx responses on EE tile URLs (the most common map-layer bug)

    Then takes a screenshot via ``Page.captureScreenshot`` after ``wait_seconds``
    so that async tile requests have time to complete.

    Args:
        url (str): URL to load (``http://`` or ``file:///``).
        width (int): Viewport width in pixels.
        height (int): Viewport height in pixels.
        wait_seconds (int): Seconds to wait after page load before screenshotting.
            Longer values allow more EE tiles to load.

    Returns:
        tuple[bytes | None, list[str]]:
            * PNG bytes (or ``None`` if screenshot failed / no browser found)
            * List of console/network error strings for debugging

    Requires ``websocket-client`` (``pip install websocket-client``).
    Falls back to the simple ``--screenshot`` approach (no console capture)
    if ``websocket-client`` is not installed.
    """
    import base64
    import json as _json
    import subprocess
    import time
    import urllib.request

    browser = _find_browser()
    if not browser:
        return None, ["No Chrome/Edge browser found."]

    # Try CDP approach first
    try:
        import websocket as _ws  # websocket-client
    except ImportError:
        # Fallback: simple headless screenshot, no console capture
        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="geeviz_map_")
        tmp_png = os.path.join(tmp_dir, "map_screenshot.png")
        cmd = [
            browser, "--headless", "--disable-gpu",
            f"--screenshot={tmp_png}",
            f"--window-size={width},{height}",
            "--hide-scrollbars", "--no-sandbox",
            "--disable-web-security", "--allow-file-access-from-files",
            f"--timeout={wait_seconds * 1000}",
            url,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=wait_seconds + 20)
            if os.path.exists(tmp_png) and os.path.getsize(tmp_png) > 1000:
                with open(tmp_png, "rb") as f:
                    return f.read(), ["Note: install websocket-client for JS console capture."]
        except Exception as exc:
            pass
        return None, [f"Screenshot failed. Install websocket-client for full CDP support: {exc}"]

    # -----------------------------------------------------------------------
    # CDP approach
    # -----------------------------------------------------------------------
    dbg_port = None
    proc = None

    try:
        cmd = [
            browser, "--headless", "--disable-gpu",
            "--remote-debugging-port=0",   # OS picks a free port
            "--remote-allow-origins=*",    # allow CDP WebSocket from any origin
            f"--window-size={width},{height}",
            "--no-sandbox", "--disable-web-security",
            "--allow-file-access-from-files",
            "--disable-extensions",
            "about:blank",
        ]
        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
        )

        # Chrome prints: DevTools listening on ws://127.0.0.1:PORT/devtools/browser/UUID
        deadline = time.time() + 10
        ws_browser_url = None
        while time.time() < deadline:
            line = proc.stderr.readline().decode(errors="replace").strip()
            if "DevTools listening on" in line:
                ws_browser_url = line.split("DevTools listening on", 1)[1].strip()
                break

        if not ws_browser_url:
            return None, ["Chrome did not output a DevTools URL within 10 s."]

        # Extract host:port from the browser-level WS URL
        # ws://127.0.0.1:PORT/devtools/browser/UUID  →  http://127.0.0.1:PORT/json/list
        host_port = ws_browser_url.split("//", 1)[1].split("/")[0]
        json_url = f"http://{host_port}/json/list"

        # Fetch the list of open pages/targets
        page_ws_url = None
        for _ in range(10):
            try:
                with urllib.request.urlopen(json_url, timeout=2) as resp:
                    targets = _json.loads(resp.read())
                for t in targets:
                    if t.get("type") == "page":
                        page_ws_url = t["webSocketDebuggerUrl"]
                        break
                if page_ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.3)

        if not page_ws_url:
            return None, ["Could not find a page target in Chrome DevTools."]

        # Connect to the page target
        ws = _ws.create_connection(page_ws_url, timeout=15)
        _id = [0]
        console_msgs = []
        network_errors = []

        def _send(method, params=None):
            _id[0] += 1
            ws.send(_json.dumps({"id": _id[0], "method": method, "params": params or {}}))
            return _id[0]

        def _recv_until(target_id, timeout=5):
            ws.settimeout(timeout)
            deadline2 = time.time() + timeout
            while time.time() < deadline2:
                try:
                    msg = _json.loads(ws.recv())
                    _process(msg)
                    if msg.get("id") == target_id:
                        return msg
                except _ws.WebSocketTimeoutException:
                    break
                except Exception:
                    break
            return {}

        page_loaded = [False]
        # Track requestId -> URL; Network.loadingFailed doesn't include the URL
        _req_urls = {}

        def _process(msg):
            method = msg.get("method", "")
            params = msg.get("params", {})
            if method in ("Page.loadEventFired", "Page.domContentEventFired"):
                page_loaded[0] = True
            elif method == "Network.requestWillBeSent":
                rid = params.get("requestId", "")
                req_url = params.get("request", {}).get("url", "")
                if rid and req_url:
                    _req_urls[rid] = req_url
            elif method == "Console.messageAdded":
                m = params.get("message", {})
                lvl = m.get("level", "")
                text = m.get("text", "")
                # Filter known-benign Google Maps API warnings that appear every session
                _gmaps_noise = ("loading=async", "SearchBox is not available")
                if lvl in ("error", "warning") and not any(n in text for n in _gmaps_noise):
                    console_msgs.append(f"[{lvl.upper()}] {text}")
            elif method == "Runtime.consoleAPICalled":
                t = params.get("type", "")
                if t in ("error", "warning"):
                    args = params.get("args", [])
                    text = " ".join(
                        str(a.get("value", a.get("description", "")))
                        for a in args
                    )
                    _gmaps_noise = ("loading=async", "SearchBox is not available")
                    if not any(n in text for n in _gmaps_noise):
                        console_msgs.append(f"[{t.upper()}] {text}")
            elif method == "Network.loadingFailed":
                rid = params.get("requestId", "")
                req_url = _req_urls.get(rid, "")
                err = params.get("errorText", "")
                canceled = params.get("canceled", False)
                # Skip canceled/aborted requests — these are normal during page nav
                # Only report real failures, especially on EE tile URLs
                if canceled or "ERR_ABORTED" in err:
                    return
                if req_url and ("earthengine" in req_url or "googleapis" in req_url):
                    network_errors.append(f"LOAD FAIL: {req_url[:120]} — {err}")
                elif req_url:
                    network_errors.append(f"LOAD FAIL: {req_url[:120]} — {err}")
            elif method == "Network.responseReceived":
                resp = params.get("response", {})
                status = resp.get("status", 0)
                resp_url = resp.get("url", "")
                if status >= 400 and ("earthengine" in resp_url or "googleapis" in resp_url):
                    network_errors.append(f"HTTP {status}: {resp_url[:120]}")

        # Enable CDP domains
        _send("Console.enable")
        _send("Runtime.enable")
        _send("Network.enable")
        _send("Page.enable")

        # Set viewport explicitly
        _send("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height,
            "deviceScaleFactor": 1, "mobile": False,
        })

        # Navigate
        nav_id = _send("Page.navigate", {"url": url})

        # Phase 1: wait for page load event (up to 15 s)
        ws.settimeout(1.0)
        load_deadline = time.time() + 15
        while time.time() < load_deadline and not page_loaded[0]:
            try:
                msg = _json.loads(ws.recv())
                _process(msg)
            except _ws.WebSocketTimeoutException:
                pass
            except Exception:
                break

        # Phase 2: additional wait for EE tile requests to complete
        ws.settimeout(1.0)
        tile_deadline = time.time() + wait_seconds
        while time.time() < tile_deadline:
            try:
                msg = _json.loads(ws.recv())
                _process(msg)
            except _ws.WebSocketTimeoutException:
                pass
            except Exception:
                break

        # Capture screenshot
        scr_id = _send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        png_b64 = None
        ws.settimeout(10)
        deadline4 = time.time() + 10
        while time.time() < deadline4:
            try:
                msg = _json.loads(ws.recv())
                _process(msg)
                if msg.get("id") == scr_id:
                    png_b64 = msg.get("result", {}).get("data")
                    break
            except _ws.WebSocketTimeoutException:
                break
            except Exception:
                break

        ws.close()
        png_bytes = base64.b64decode(png_b64) if png_b64 else None
        all_msgs = console_msgs + network_errors
        return png_bytes, all_msgs

    except Exception as exc:
        return None, [f"CDP screenshot failed: {exc}"]
    finally:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass


def html_to_png(html, width=900, height=1200, autocrop=True):
    """Render an HTML string to PNG bytes via headless Chrome/Edge screenshot.

    Uses a tall viewport and auto-crops empty space at the bottom so
    the output fits the actual content height.

    Args:
        html (str): Full HTML document string.
        width (int): Viewport width in pixels.
        height (int): Viewport height in pixels (tall default to avoid cutoff).
        autocrop (bool): Trim empty space from the bottom of the image.

    Returns:
        bytes: PNG image bytes, or None if no browser is available.
    """
    import subprocess
    import tempfile

    browser = _find_browser()
    if not browser:
        return None

    tmp_dir = tempfile.mkdtemp(prefix="geeviz_chart_")
    tmp_html = os.path.join(tmp_dir, "chart.html")
    tmp_png = os.path.join(tmp_dir, "chart.png")

    try:
        with open(tmp_html, "w", encoding="utf-8") as f:
            f.write(html)

        file_uri = "file:///" + tmp_html.replace(os.sep, "/")
        cmd = [
            browser, "--headless", "--disable-gpu",
            f"--screenshot={tmp_png}",
            f"--window-size={width},{height}",
            "--hide-scrollbars",
            "--virtual-time-budget=5000",
            file_uri,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)

        if result.returncode == 0 and os.path.exists(tmp_png) and os.path.getsize(tmp_png) > 1000:
            with open(tmp_png, "rb") as f:
                png_bytes = f.read()
            if autocrop:
                png_bytes = _autocrop_png(png_bytes)
            return png_bytes
        return None
    except Exception:
        return None
    finally:
        for p in (tmp_png, tmp_html):
            if os.path.exists(p):
                os.remove(p)
        if os.path.isdir(tmp_dir):
            os.rmdir(tmp_dir)


def save_chart_png(fig, filename, width=900, height=600,
                   theme="dark", bg_color=None, font_color=None):
    """Save a Plotly chart or D3 sankey HTML string as a PNG image.

    Accepts either a Plotly ``Figure`` (exported via kaleido) or an HTML
    string (from ``summarize_and_chart(chart_type='sankey')``), which is
    rendered via headless Chrome/Edge screenshot.

    Args:
        fig: ``plotly.graph_objects.Figure`` or ``str`` (D3 sankey HTML).
        filename (str): Output filename (e.g. ``"chart.png"``).
        width (int): Image width in pixels.
        height (int): Image height in pixels.
        theme: Theme preset name or :class:`~geeViz.outputLib.themes.Theme`.
        bg_color: Background color override.
        font_color: Font/text color override.

    Returns:
        str: Path to the saved file.

    Examples:
        >>> path = cl.save_chart_png(fig, "ndvi_trend.png")
        >>> path = cl.save_chart_png(sankey_html, "transitions.png")
    """
    _t = _themes.get_theme(theme, bg_color=bg_color, font_color=font_color)

    if isinstance(fig, str):
        # D3 sankey or other HTML string — use headless browser screenshot
        # Apply theme and hide toolbar
        themed_html = sankey_to_html(
            fig, bg_color=_t.bg_hex, font_color=_t.text_hex,
            renderer="d3", hide_toolbar=True,
        )
        img_bytes = html_to_png(themed_html, width=width, height=height)
        if img_bytes is None:
            raise RuntimeError(
                "Cannot render HTML chart to PNG: no browser (Chrome/Edge) found. "
                "Install Chrome or Edge for headless screenshot support."
            )
    else:
        # Plotly figure — use kaleido
        import plotly.io as pio
        import copy

        themed_fig = copy.deepcopy(fig)
        _themes.apply_plotly_theme(themed_fig, _t)
        img_bytes = pio.to_image(themed_fig, format="png", width=width, height=height)

    # Try MCP sandbox save_file first, fall back to direct write
    import builtins as _builtins
    _save_fn = _builtins.__dict__.get("save_file") if hasattr(_builtins, "__dict__") else None
    if _save_fn is None:
        import inspect
        frame = inspect.currentframe()
        try:
            caller_globals = frame.f_back.f_globals if frame.f_back else {}
            _save_fn = caller_globals.get("save_file")
        finally:
            del frame

    if _save_fn is not None:
        return _save_fn(filename, img_bytes, mode="wb")
    else:
        with open(filename, "wb") as f:
            f.write(img_bytes)
        return filename


def sankey_to_html(fig, full_html=True, include_plotlyjs=_PLOTLY_CDN_URL, renderer="d3",
                   theme="dark", bg_color=None, font_color=None,
                   hide_toolbar=False):
    """Return sankey HTML, accepting either a raw HTML string or legacy Plotly figure.

    Sankey charts from ``summarize_and_chart(chart_type='sankey')`` are
    now returned as D3 HTML strings directly.  This function is kept for
    backward compatibility — it passes HTML strings through unchanged.

    Args:
        fig: D3 HTML string (preferred) or legacy Plotly ``Figure``.
        full_html (bool): Ignored for HTML strings.
        include_plotlyjs: Ignored for HTML strings.
        renderer (str): Ignored (always D3).
        theme: Theme preset for legacy Plotly figures.
        bg_color: Background color override.
        font_color: Font/text color override.
        hide_toolbar (bool): Hide the download button.

    Returns:
        str: HTML string.
    """
    if isinstance(fig, str):
        html = fig
        if hide_toolbar:
            html = html.replace(
                '<div id="toolbar">',
                '<div id="toolbar" style="display:none">',
            )
        return html
    # Legacy path: Plotly figure with _gradient_color_map
    _t = _themes.get_theme(theme, bg_color=bg_color, font_color=font_color)
    return _sankey_plotly_fig_to_d3(fig, theme=_t, hide_toolbar=hide_toolbar)


def _sankey_plotly_fig_to_d3(fig, theme=None, hide_toolbar=False):
    """D3.js / d3-sankey based Sankey HTML with native SVG gradients."""
    import json as _json
    _t = theme if theme is not None else _themes.get_theme("dark")

    # Extract data from the Plotly figure
    trace = fig.data[0]
    node_labels = list(trace.node.label)
    node_colors_raw = list(trace.node.color)
    link_sources = list(trace.link.source)
    link_targets = list(trace.link.target)
    link_values = list(trace.link.value)

    # Get gradient color map for source/target hex colors
    gradient_map = getattr(fig, "_gradient_color_map", {})
    opacity = getattr(fig, "_gradient_link_opacity", 0.9)

    # Build link colors from gradient map or fall back to node colors
    link_colors = []
    link_colors_raw = list(trace.link.color) if trace.link.color else []
    for i in range(len(link_sources)):
        src_idx = link_sources[i]
        tgt_idx = link_targets[i]
        # Try to find source/target hex from gradient map
        if i < len(link_colors_raw):
            raw = link_colors_raw[i]
            import re
            m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', raw)
            if m:
                key = f"{m.group(1)},{m.group(2)},{m.group(3)}"
                if key in gradient_map:
                    link_colors.append(gradient_map[key])
                    continue
        # Fallback: use node colors
        sc = node_colors_raw[src_idx] if src_idx < len(node_colors_raw) else "#888"
        tc = node_colors_raw[tgt_idx] if tgt_idx < len(node_colors_raw) else "#888"
        link_colors.append([sc, tc])

    # Resolve node colors to hex (they may be rgba strings)
    node_colors_hex = []
    for c in node_colors_raw:
        if c.startswith("rgba"):
            import re
            m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', c)
            if m:
                node_colors_hex.append(
                    f"#{int(m.group(1)):02x}{int(m.group(2)):02x}{int(m.group(3)):02x}"
                )
                continue
        node_colors_hex.append(c)

    # Extract layout info
    layout = fig.layout
    title = layout.title.text if layout.title and layout.title.text else ""
    width = layout.width or 800
    height = layout.height or 600
    node_thickness = trace.node.thickness or 20
    node_pad = trace.node.pad or 15

    # Filter out nodes that have no links (0-value orphans clutter the chart)
    used_indices = set()
    for i in range(len(link_sources)):
        if link_values[i] > 0:
            used_indices.add(link_sources[i])
            used_indices.add(link_targets[i])

    # Build old→new index mapping for used nodes only
    old_to_new = {}
    new_idx = 0
    for old_idx in range(len(node_labels)):
        if old_idx in used_indices:
            old_to_new[old_idx] = new_idx
            new_idx += 1

    # Build JSON data for the D3 template
    d3_data = {
        "nodes": [
            {"name": node_labels[i], "color": node_colors_hex[i]}
            for i in range(len(node_labels))
            if i in used_indices
        ],
        "links": [
            {
                "source": old_to_new[link_sources[i]],
                "target": old_to_new[link_targets[i]],
                "value": link_values[i],
                "sourceColor": link_colors[i][0],
                "targetColor": link_colors[i][1],
            }
            for i in range(len(link_sources))
            if link_values[i] > 0 and link_sources[i] in old_to_new and link_targets[i] in old_to_new
        ],
    }

    d3_config = {
        "title": title,
        "width": width,
        "height": height,
        "nodeWidth": node_thickness,
        "nodePadding": node_pad,
        "opacity": opacity,
        "bgColor": _t.bg_hex,
        "textColor": _t.text_hex,
    }
    # render_d3_sankey fills CSS color placeholders; we still need data/config
    html = _render_d3_sankey(_t)
    result = html.replace(
        "__D3_DATA_JSON__", _json.dumps(d3_data)
    ).replace(
        "__D3_CONFIG_JSON__", _json.dumps(d3_config)
    )
    if hide_toolbar:
        result = result.replace(
            '<div id="toolbar">',
            '<div id="toolbar" style="display:none">',
        )
    return result


def _expand_thematic_reduce_regions(df, band_names, class_info, area_format, scale, split_str):
    """Expand histogram dict columns from reduceRegions into class-name columns."""
    scale_mult = (scale / AREA_FORMAT_DICT["Hectares"]["scale"]) ** 2

    out_rows = []
    for _, row in df.iterrows():
        out_row = {}
        # preserve any non-histogram columns (e.g. label/id)
        for col in df.columns:
            if col not in band_names:
                out_row[col] = row[col]

        for bn in band_names:
            histogram = row.get(bn)
            if histogram is None or not isinstance(histogram, dict):
                continue

            # For stacked band names like "2020----Land_Cover", look up class_info
            # by the original band name (the part after the SPLIT_STR prefix).
            original_bn = bn.split(split_str, 1)[-1] if split_str in bn else bn
            info = class_info.get(original_bn, {})
            class_values = info.get("class_values", [])
            class_names = info.get("class_names", [])
            value_to_name = dict(zip([str(v) for v in class_values], class_names))

            pixel_total = sum(histogram.values()) or 1

            for str_val, count in histogram.items():
                name = value_to_name.get(str_val, str_val)
                col_name = f"{bn}{split_str}{name}" if len(band_names) > 1 else name
                if area_format == "Percentage":
                    out_row[col_name] = round((count / pixel_total) * 100, 2)
                elif area_format == "Pixels":
                    out_row[col_name] = count
                else:
                    mult = AREA_FORMAT_DICT[area_format]["mult"] * scale_mult
                    out_row[col_name] = round(count * mult, AREA_FORMAT_DICT[area_format]["places"])

        out_rows.append(out_row)

    return pandas.DataFrame(out_rows)


def _pivot_multi_feature_timeseries(df, x_axis_labels, obj_info, feature_label, split_str=SPLIT_STR):
    """Pivot a multi-feature reduceRegions DataFrame (with stacked band columns) into per-feature time-series DataFrames.

    After ``reduceRegions`` on a stacked image, the DataFrame has one row per
    feature and columns like ``2020----Land_Cover----Trees`` (thematic) or
    ``2020----NDVI`` (continuous).  This function restructures each row into a
    time-series DataFrame where the index is the time label and the columns are
    the class names (thematic) or band names (continuous).

    Args:
        df (pandas.DataFrame): Output of ``zonal_stats`` for multi-feature +
            ImageCollection.  Must already have ``feature_label`` as a column
            or index.
        x_axis_labels (list): Time-step labels (e.g. ``['2020', '2021', ...]``).
        obj_info (dict): Output of :func:`get_obj_info`.
        feature_label (str): Column/index name identifying each feature.
        split_str (str, optional): Band name separator.

    Returns:
        dict: ``{feature_name: pandas.DataFrame}`` where each DataFrame has
            index = time labels, columns = class/band names.
    """
    band_names = obj_info["band_names"]
    class_info = obj_info["class_info"]
    is_thematic = obj_info["is_thematic"]

    # Ensure feature_label is a column (not the index)
    if feature_label not in df.columns and df.index.name == feature_label:
        df = df.reset_index()

    result = {}
    for _, row in df.iterrows():
        feat_name = str(row.get(feature_label, row.name))

        rows_out = []
        for x_label in x_axis_labels:
            ts_row = {"x": x_label}

            if is_thematic:
                # Columns are like "2020----Land_Cover----Trees"
                for bn in band_names:
                    info = class_info.get(bn, {})
                    class_names = info.get("class_names", [])
                    for cn in class_names:
                        # Multi-band: "2020----Land_Cover----Trees"
                        # Single-band: "2020----Land_Cover----Trees" still, because
                        # _expand_thematic_reduce_regions uses stack_bands which
                        # include the x_label prefix
                        col = f"{x_label}{split_str}{bn}{split_str}{cn}"
                        if col in row.index:
                            ts_row[cn] = row[col]
                        else:
                            ts_row[cn] = 0
            else:
                # Columns are like "2020----NDVI"
                for bn in band_names:
                    col = f"{x_label}{split_str}{bn}"
                    if col in row.index:
                        ts_row[bn] = row[col]
                    else:
                        ts_row[bn] = None

            rows_out.append(ts_row)

        feat_df = pandas.DataFrame(rows_out).set_index("x")
        feat_df.index.name = None
        result[feat_name] = feat_df

    return result


def chart_multi_feature_timeseries(
    per_feature_dfs,
    colors=None,
    chart_type="line+markers",
    title="Time Series by Feature",
    x_label="Year",
    y_label=None,
    width=DEFAULT_CHART_WIDTH,
    height=None,
    columns=2,
    legend_position="bottom",
    line_width=2,
    marker_size=5,
    max_x_tick_labels=10,
    max_y_tick_labels=None,
):
    """Create a subplot figure with one time-series chart per feature.

    Features are arranged in a grid with *columns* columns (default 2).
    Each subplot gets ``height`` pixels tall (total height scales with
    number of rows).  The legend defaults to ``"bottom"``.

    Args:
        per_feature_dfs (dict): ``{feature_name: DataFrame}`` from
            :func:`_pivot_multi_feature_timeseries`.
        colors (list, optional): Hex color strings for each column.
        chart_type (str, optional): ``"line+markers"`` (default), ``"line"``,
            ``"bar"``, ``"stacked_line"``, ``"stacked_line+markers"``, or
            ``"stacked_bar"``.
        title (str, optional): Overall chart title.
        x_label (str, optional): X-axis label.
        y_label (str, optional): Y-axis label.
        width (int, optional): Chart width in pixels.
        height (int, optional): Total chart height.  When ``None`` each
            subplot gets 400 px.
        legend_position (dict or str, optional): Legend layout.
            Default ``"bottom"``.
        line_width (int or float, optional): Line width in pixels.
            Defaults to ``2``.
        marker_size (int or float, optional): Marker diameter in pixels.
            Defaults to ``5``.
        max_x_tick_labels (int, optional): Maximum number of x-axis tick
            labels per subplot. Labels are thinned to every 2nd, 5th,
            10th, etc. value when exceeded. Defaults to ``10``.
            Set to ``None`` or ``0`` to disable.
        max_y_tick_labels (int, optional): Maximum number of y-axis tick
            labels per subplot. Uses Plotly's ``nticks``.
            Defaults to ``None`` (automatic).

    Returns:
        plotly.graph_objects.Figure
    """
    from plotly.subplots import make_subplots

    plotly_mode, is_stacked = _parse_chart_type(chart_type)

    n = len(per_feature_dfs)
    if n == 0:
        return go.Figure()

    n_cols = min(columns, n)
    n_rows = -(-n // n_cols)  # ceil division

    # height/width are per-cell; scale to full grid
    cell_h = height if height is not None else 400
    cell_w = width if width is not None else DEFAULT_CHART_WIDTH
    height = n_rows * cell_h
    width = n_cols * cell_w

    feature_names = list(per_feature_dfs.keys())
    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        subplot_titles=feature_names,
        shared_xaxes=False,
        vertical_spacing=max(0.02, 0.10 / max(n_rows, 1)),
        horizontal_spacing=max(0.03, 0.08 / max(n_cols, 1)),
    )

    # Track which legend entries we've already added so we only show each once
    legend_added = set()

    for feat_idx, (feat_name, feat_df) in enumerate(per_feature_dfs.items()):
        row_idx = feat_idx // n_cols + 1
        col_idx_grid = feat_idx % n_cols + 1

        x_values = list(feat_df.index)
        try:
            x_values = [int(v) for v in x_values]
        except (ValueError, TypeError):
            pass

        for col_idx, col in enumerate(feat_df.columns):
            color = None
            if colors and col_idx < len(colors):
                color = _ensure_hex_color(colors[col_idx])

            show_legend = col not in legend_added
            legend_added.add(col)

            if plotly_mode == "bar":
                fig.add_trace(
                    go.Bar(
                        x=x_values,
                        y=feat_df[col].values,
                        name=col,
                        marker_color=color,
                        showlegend=show_legend,
                        legendgroup=col,
                    ),
                    row=row_idx, col=col_idx_grid,
                )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=feat_df[col].values,
                        mode=plotly_mode,
                        name=col,
                        line=dict(color=color, width=line_width),
                        marker=dict(color=color, size=marker_size),
                        stackgroup="one" if is_stacked else None,
                        showlegend=show_legend,
                        legendgroup=col,
                    ),
                    row=row_idx, col=col_idx_grid,
                )

    bar_mode = "stack" if is_stacked and plotly_mode == "bar" else ("group" if plotly_mode == "bar" else None)

    # Legend: "bottom" → horizontal below chart
    legend_kw = _legend_kwargs(legend_position)
    if legend_position == "bottom":
        legend_kw = {"orientation": "h", "yanchor": "top", "y": -0.05,
                     "xanchor": "center", "x": 0.5}

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        legend=legend_kw,
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=width,
        height=height,
        barmode=bar_mode,
        hovermode="x unified",
    )

    # Fix x-axis ticks: only show actual data values, no interpolated ticks
    sample_idx = list(per_feature_dfs.values())[0].index if per_feature_dfs else []
    is_int_axis = all(str(v).lstrip("-").isdigit() for v in sample_idx)
    if is_int_axis:
        all_tick_vals = sorted(set(int(v) for v in sample_idx))
        tick_vals = all_tick_vals
    else:
        all_tick_vals = None
        tick_vals = None
    # Thin x-axis ticks if too many
    if tick_vals is not None:
        thinned = _thin_tick_vals(tick_vals, max_x_tick_labels)
        if thinned is not None:
            tick_vals = thinned
    for r in range(1, n_rows + 1):
        for c in range(1, n_cols + 1):
            kw = {}
            if tick_vals is not None:
                kw["tickvals"] = tick_vals
                kw["tickformat"] = "d"
                # Constrain range to full data extent to eliminate dead space
                kw["range"] = [min(all_tick_vals) - 0.5, max(all_tick_vals) + 0.5]
            if r == n_rows:
                kw["title_text"] = x_label
            fig.update_xaxes(row=r, col=c, **kw)

    # Label left column y-axes; add '%' suffix for percentage labels
    y_kw = {}
    if y_label and "%" in y_label:
        y_kw["ticksuffix"] = "%"
    if max_y_tick_labels is not None and max_y_tick_labels > 0:
        y_kw["nticks"] = max_y_tick_labels
    for r in range(1, n_rows + 1):
        if y_label:
            fig.update_yaxes(title_text=y_label, row=r, col=1, **y_kw)
        elif y_kw:
            fig.update_yaxes(row=r, col=1, **y_kw)

    _themes.apply_plotly_theme(fig, "dark")
    return fig


###########################################################################
#                       Data pipeline functions
###########################################################################


def get_obj_info(ee_obj, band_names=None):
    """
    Detect the type of a GEE object and read its thematic class metadata.

    Args:
        ee_obj (ee.Image or ee.ImageCollection): The GEE object to inspect.
        band_names (list, optional): Override the band names to use.

    Returns:
        dict: Keys ``obj_type``, ``band_names``, ``is_thematic``, ``class_info``, ``size``.
              ``class_info`` is ``{band_name: {class_values, class_names, class_palette}}``

    Examples:
        Inspect LCMS to see its thematic class metadata:

        >>> import geeViz.geeView as gv
        >>> from geeViz.outputLib import charts as cl
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")
        >>> info = cl.get_obj_info(lcms.select(['Land_Cover']))
        >>> print(info['is_thematic'])
        True
        >>> print(info['class_info']['Land_Cover']['class_names'])
        ['Trees', 'Tall Shrubs & Trees Mix (AK Only)', ...]
    """
    obj_type = type(ee_obj).__name__

    if obj_type == "ImageCollection":
        first_img = ee.Image(ee_obj.first())
        size = ee_obj.size().getInfo()
    else:
        first_img = ee.Image(ee_obj)
        size = 1

    if band_names is None:
        band_names = first_img.bandNames().getInfo()

    # Read class metadata from image properties
    props = first_img.toDictionary().getInfo()
    class_info = {}
    is_thematic = False

    for bn in band_names:
        values_key = f"{bn}_class_values"
        names_key = f"{bn}_class_names"
        palette_key = f"{bn}_class_palette"

        if values_key in props and names_key in props:
            is_thematic = True
            class_info[bn] = {
                "class_values": props[values_key],
                "class_names": props[names_key],
                "class_palette": props.get(palette_key, []),
            }

    return {
        "obj_type": obj_type,
        "band_names": band_names,
        "is_thematic": is_thematic,
        "class_info": class_info,
        "size": size,
    }


def _detect_feature_label(fc):
    """Auto-detect a suitable label property from an ee.FeatureCollection.

    Looks for a property containing 'name' (case-insensitive), excluding
    system properties. Falls back to ``'system:index'``.

    Args:
        fc: ee.FeatureCollection.

    Returns:
        str: Property name to use as feature label.
    """
    try:
        props = fc.first().propertyNames().getInfo()
        # Filter out system/geometry properties
        candidates = [p for p in props if not p.startswith("system:") and p != "geo"]
        # Prefer properties with "name" in them (case-insensitive)
        name_props = [p for p in candidates if "name" in p.lower()]
        if name_props:
            return name_props[0]
    except Exception:
        pass
    return "system:index"


def detect_geometry_type(geometry):
    """
    Determine whether the input geometry represents a single region or multiple.

    Args:
        geometry: An ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.

    Returns:
        tuple: ``(geo_type, geometry)`` where geo_type is ``'single'`` or ``'multi'``,
               and geometry is an ``ee.Geometry`` (single) or ``ee.FeatureCollection`` (multi).
    """
    if isinstance(geometry, ee.Geometry):
        return ("single", geometry)

    if isinstance(geometry, ee.Feature):
        return ("single", geometry.geometry())

    if isinstance(geometry, ee.FeatureCollection):
        size = geometry.size().getInfo()
        if size <= 1:
            return ("single", geometry.geometry())
        return ("multi", geometry)

    # Fallback: ee.Element (from fc.first()) or other ComputedObject
    # Wrap in ee.Feature to extract geometry safely
    try:
        return ("single", ee.Feature(geometry).geometry())
    except Exception:
        return ("single", ee.Geometry(geometry))


def prepare_for_reduction(ee_obj, obj_info, x_axis_property="system:time_start", date_format="YYYY"):
    """
    Prepare a GEE object for reduction by stacking an ImageCollection into a
    single multi-band image.

    Args:
        ee_obj: ``ee.Image`` or ``ee.ImageCollection``.
        obj_info (dict): Output of :func:`get_obj_info`.
        x_axis_property (str, optional): Property name to use for x-axis labels.
        date_format (str, optional): Earth Engine date format string (e.g. ``'YYYY'``).

    Returns:
        tuple: ``(stacked_image, stack_band_names, x_axis_labels)``
    """
    band_names = obj_info["band_names"]

    if obj_info["obj_type"] == "ImageCollection":
        ic = ee_obj

        # Tag images with x_axis_property if it's a date-derived field
        if x_axis_property in ("year", "date", "system:time_start"):
            ic = ic.map(lambda img: img.set("year", img.date().format(date_format)))
            if x_axis_property in ("date", "system:time_start"):
                x_axis_property = "year"

        # Get the x-axis labels
        x_axis_labels = ic.aggregate_histogram(x_axis_property).keys().getInfo()

        # Select only the bands we care about
        ic = ic.select(band_names)

        # Group by x_axis_property - if multiple images per label, mosaic them
        label_counts = ic.aggregate_histogram(x_axis_property).getInfo()
        needs_mosaic = any(v > 1 for v in label_counts.values())

        if needs_mosaic:
            print("Auto-mosaicking ImageCollection for x-axis labels...")
            def _mosaic_for_label(label):
                label = ee.String(label)
                filtered = ic.filter(ee.Filter.eq(x_axis_property, label))
                return filtered.mosaic().copyProperties(filtered.first()).set(x_axis_property, label)

            ic = ee.ImageCollection(ee.List(x_axis_labels).map(_mosaic_for_label))
        
        # Stack into single image with band names like "2020----forest"
        def _rename_bands(img):
            label = ee.String(img.get(x_axis_property))
            new_names = ee.List(band_names).map(
                lambda bn: label.cat(SPLIT_STR).cat(ee.String(bn))
            )
            return img.select(band_names).rename(new_names)

        # Pre-compute expected band names: "label----band" for each label × band
        expected_names = []
        for x_label in x_axis_labels:
            for bn in band_names:
                expected_names.append(f"{x_label}{SPLIT_STR}{bn}")

        ic = ic.map(_rename_bands)
        stacked = ic.toBands()

        # toBands() prefixes each band with the image's system:index + "_".
        # For programmatically-built collections (e.g. from the mosaic branch)
        # this is "0_", "1_", etc.  But for collections with original system:index
        # values (e.g. "LC09_038029_20230613") the prefix is unpredictable.
        # Instead of trying to strip the prefix, rename to the expected names
        # we already know.
        stacked = stacked.rename(expected_names)
        return (stacked, expected_names, x_axis_labels)

    else:
        # Single image - pass through
        return (ee.Image(ee_obj).select(band_names), band_names, [])


def reduce_region(image, geometry, reducer, scale=30, crs=None, transform=None, tile_scale=4):
    """
    Run ``image.reduceRegion`` with sensible defaults.

    If both ``scale`` and ``transform`` are provided, ``scale`` is set to None
    (transform takes precedence in GEE).

    Args:
        image (ee.Image): The image to reduce.
        geometry: An ``ee.Geometry`` or ``ee.Feature``.
        reducer (ee.Reducer): The reducer to apply.
        scale (int, optional): Pixel scale in meters. Defaults to 30.
        crs (str, optional): CRS string. Defaults to None.
        transform (list, optional): Affine transform. Defaults to None.
        tile_scale (int, optional): Tile scale for parallelism. Defaults to 4.

    Returns:
        dict: The reduction result dictionary.
    """
    if transform is not None and scale is not None:
        scale = None

    return image.reduceRegion(
        reducer=reducer,
        geometry=geometry,
        scale=scale,
        crs=crs,
        crsTransform=transform,
        bestEffort=True,
        maxPixels=1e13,
        tileScale=tile_scale,
    ).getInfo()


def reduce_regions(image, features, reducer, scale=30, crs=None, transform=None, tile_scale=4):
    """
    Run ``image.reduceRegions`` and return the result as a DataFrame.

    Args:
        image (ee.Image): The image to reduce.
        features (ee.FeatureCollection): The zones.
        reducer (ee.Reducer): The reducer to apply.
        scale (int, optional): Pixel scale in meters. Defaults to 30.
        crs (str, optional): CRS string. Defaults to None.
        transform (list, optional): Affine transform. Defaults to None.
        tile_scale (int, optional): Tile scale for parallelism. Defaults to 4.

    Returns:
        pandas.DataFrame: The reduction results.
    """
    if transform is not None and scale is not None:
        scale = None

    result = image.reduceRegions(
        collection=features,
        reducer=reducer,
        scale=scale,
        crs=crs,
        crsTransform=transform,
        tileScale=tile_scale,
    )
    return robust_featureCollection_to_df(result)


def parse_thematic_results(raw_dict, obj_info, x_axis_labels, area_format="Percentage", scale=30, split_str=SPLIT_STR):
    """
    Parse frequency histogram reduction results into a DataFrame with class names as columns.

    Args:
        raw_dict (dict): Output of :func:`reduce_region` using ``frequencyHistogram``.
        obj_info (dict): Output of :func:`get_obj_info`.
        x_axis_labels (list): Labels for the x-axis (e.g. years).
        area_format (str, optional): One of ``'Percentage'``, ``'Hectares'``, ``'Acres'``, ``'Pixels'``.
        scale (int, optional): Pixel scale used in reduction.
        split_str (str, optional): Band name separator.

    Returns:
        pandas.DataFrame: Rows are x-axis labels (or a single row for Image),
                          columns are class names.
    """
    class_info = obj_info["class_info"]
    band_names = obj_info["band_names"]
    scale_mult = (scale / AREA_FORMAT_DICT["Hectares"]["scale"]) ** 2

    if x_axis_labels:
        # ImageCollection path - histogram keys are like "2020----Land_Cover"
        rows = []
        for x_label in x_axis_labels:
            row = {"x": x_label}
            for bn in band_names:
                key = f"{x_label}{split_str}{bn}"
                histogram = raw_dict.get(key, {})
                if histogram is None:
                    histogram = {}

                info = class_info.get(bn, {})
                class_values = info.get("class_values", [])
                class_names = info.get("class_names", [])
                value_to_name = dict(zip([str(v) for v in class_values], class_names))

                pixel_total = sum(histogram.values()) or 1

                for str_val, count in histogram.items():
                    name = value_to_name.get(str_val, str_val)
                    col_name = f"{bn}{split_str}{name}" if len(band_names) > 1 else name
                    if area_format == "Percentage":
                        row[col_name] = round((count / pixel_total) * 100, 2)
                    elif area_format == "Pixels":
                        row[col_name] = count
                    else:
                        mult = AREA_FORMAT_DICT[area_format]["mult"] * scale_mult
                        row[col_name] = round(count * mult, AREA_FORMAT_DICT[area_format]["places"])

            rows.append(row)

        df = pandas.DataFrame(rows).set_index("x")
        df.index.name = None
        df = df.fillna(0)
        return df

    else:
        # Single Image path - histogram keys are band names directly
        row = {}
        for bn in band_names:
            histogram = raw_dict.get(bn, {})
            if histogram is None:
                histogram = {}

            info = class_info.get(bn, {})
            class_values = info.get("class_values", [])
            class_names = info.get("class_names", [])
            value_to_name = dict(zip([str(v) for v in class_values], class_names))

            pixel_total = sum(histogram.values()) or 1

            for str_val, count in histogram.items():
                name = value_to_name.get(str_val, str_val)
                col_name = f"{bn}{split_str}{name}" if len(band_names) > 1 else name
                if area_format == "Percentage":
                    row[col_name] = round((count / pixel_total) * 100, 2)
                elif area_format == "Pixels":
                    row[col_name] = count
                else:
                    mult = AREA_FORMAT_DICT[area_format]["mult"] * scale_mult
                    row[col_name] = round(count * mult, AREA_FORMAT_DICT[area_format]["places"])

        df = pandas.DataFrame([row])
        df = df.fillna(0)
        return df


def parse_continuous_results(raw_dict, obj_info, x_axis_labels, split_str=SPLIT_STR):
    """
    Parse continuous (mean/median/etc.) reduction results into a DataFrame.

    Args:
        raw_dict (dict): Output of :func:`reduce_region`.
        obj_info (dict): Output of :func:`get_obj_info`.
        x_axis_labels (list): Labels for the x-axis.
        split_str (str, optional): Band name separator.

    Returns:
        pandas.DataFrame: Rows are x-axis labels (or single row), columns are band names.
    """
    band_names = obj_info["band_names"]

    if x_axis_labels:
        rows = []
        for x_label in x_axis_labels:
            row = {"x": x_label}
            for bn in band_names:
                key = f"{x_label}{split_str}{bn}"
                row[bn] = raw_dict.get(key)
            rows.append(row)

        df = pandas.DataFrame(rows).set_index("x")
        df.index.name = None
        return df

    else:
        row = {bn: raw_dict.get(bn) for bn in band_names}
        return pandas.DataFrame([row])


def zonal_stats(
    ee_obj,
    geometry,
    band_names=None,
    reducer=None,
    scale=30,
    crs=None,
    transform=None,
    tile_scale=4,
    area_format="Percentage",
    x_axis_property="system:time_start",
    date_format="YYYY",
    include_masked_area=True,
):
    """
    Compute zonal statistics for a GEE Image or ImageCollection over a geometry.

    This is the main entry point for the data pipeline. It auto-detects the
    object type, whether data is thematic or continuous, the appropriate reducer,
    and the geometry type.

    Args:
        ee_obj: ``ee.Image`` or ``ee.ImageCollection``.
        geometry: ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.
        band_names (list, optional): Bands to include. Auto-detected if None.
        reducer (ee.Reducer, optional): Override the auto-selected reducer.
        scale (int, optional): Pixel scale in meters. Defaults to 30.
        crs (str, optional): CRS string.
        transform (list, optional): Affine transform.
        tile_scale (int, optional): Tile scale for parallelism. Defaults to 4.
        area_format (str, optional): Area unit for thematic data. One of
            ``'Percentage'``, ``'Hectares'``, ``'Acres'``, ``'Pixels'``.
        x_axis_property (str, optional): Property for x-axis labels (ImageCollection).
        date_format (str, optional): Date format string for x-axis labels.

    Returns:
        pandas.DataFrame: The zonal statistics table.

    Examples:
        Get just the data (no chart) for an LCMS land cover time series:

        >>> import geeViz.geeView as gv
        >>> from geeViz.outputLib import charts as cl
        >>> ee = gv.ee
        >>> study_area = ee.Geometry.Polygon(
        ...     [[[-106, 39.5], [-105, 39.5], [-105, 40.5], [-106, 40.5]]]
        ... )
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")
        >>> df = cl.zonal_stats(
        ...     lcms.select(['Land_Cover']),
        ...     study_area,
        ...     area_format='Percentage',
        ... )
        >>> print(df.to_markdown())

        Continuous data with a custom reducer:

        >>> df = cl.zonal_stats(
        ...     lcms.select(['Change_Raw_Probability_Slow_Loss']),
        ...     study_area,
        ...     reducer=ee.Reducer.mean(),
        ... )
    """
    # filterBounds only applies to ImageCollections, not single Images
    if isinstance(ee_obj, ee.ImageCollection):
        ee_obj = ee_obj.filterBounds(geometry)

    obj_info = get_obj_info(ee_obj, band_names)
    geo_type, geo = detect_geometry_type(geometry)

    # Choose reducer
    if reducer is None:
        if obj_info["is_thematic"]:
            reducer = ee.Reducer.frequencyHistogram()
        else:
            reducer = ee.Reducer.mean()

    # Determine if using frequency histogram
    is_histogram = False
    try:
        reducer_type = reducer.getInfo()["type"]
        is_histogram = "frequencyHistogram" in reducer_type
    except Exception:
        pass

    # When include_masked_area=True and using histogram reducer, unmask
    # with a sentinel value (0) so masked pixels count toward the total
    # area denominator.  The sentinel class is removed from results after.
    _unmask_sentinel = None
    if include_masked_area and is_histogram:
        _unmask_sentinel = 0
        if isinstance(ee_obj, ee.ImageCollection):
            ee_obj = ee_obj.map(lambda img: img.unmask(_unmask_sentinel).copyProperties(img, ["system:time_start"]))
        else:
            ee_obj = ee.Image(ee_obj).unmask(_unmask_sentinel)
        # Re-get obj_info after unmask (band structure unchanged)
        obj_info = get_obj_info(ee_obj, band_names)

    # Prepare image
    stacked, stack_bands, x_axis_labels = prepare_for_reduction(
        ee_obj, obj_info, x_axis_property, date_format
    )

    def _strip_sentinel_cols(df):
        """Remove sentinel unmask class columns (0, 0.0) from results."""
        if _unmask_sentinel is not None:
            drop = [c for c in df.columns if str(c).strip() in ("0", "0.0")]
            if drop:
                df = df.drop(columns=drop)
        return df

    if geo_type == "single":
        raw = reduce_region(stacked, geo, reducer, scale, crs, transform, tile_scale)

        if is_histogram:
            return _strip_sentinel_cols(
                parse_thematic_results(raw, obj_info, x_axis_labels, area_format, scale))
        else:
            return parse_continuous_results(raw, obj_info, x_axis_labels)

    else:
        # Multi-region: reduceRegions
        if is_histogram:
            # frequencyHistogram + reduceRegions requires special handling:
            # 1. For single-band images, EE names the output "histogram" instead
            #    of the band name. Use setOutputs() to force band-name keys.
            #    For multi-band images (stacked ImageCollections), EE already
            #    names outputs by band name, and setOutputs() would fail.
            # 2. robust_featureCollection_to_df flattens nested dicts, destroying
            #    the histogram structure. Get features directly to preserve dicts.
            if len(stack_bands) == 1:
                hist_reducer = reducer.setOutputs(stack_bands)
            else:
                hist_reducer = reducer
            if transform is not None and scale is not None:
                scale = None
            fc_result = stacked.reduceRegions(
                collection=geo,
                reducer=hist_reducer,
                scale=scale,
                crs=crs,
                crsTransform=transform,
                tileScale=tile_scale,
            )
            # Fetch features preserving nested histogram dicts.
            # Batch in chunks of 5000 to avoid EE's feature limit.
            n_features = fc_result.size().getInfo()
            rows = []
            fc_list = fc_result.toList(n_features)
            batch_size = 5000
            for start in range(0, n_features, batch_size):
                end = min(start + batch_size, n_features)
                batch = ee.FeatureCollection(fc_list.slice(start, end))
                features = batch.getInfo()["features"]
                for f in features:
                    rows.append(f.get("properties", {}))
            df = pandas.DataFrame(rows)
            return _strip_sentinel_cols(_expand_thematic_reduce_regions(
                df, stack_bands, obj_info["class_info"], area_format, scale, SPLIT_STR
            ))
        else:
            df = reduce_regions(stacked, geo, reducer, scale, crs, transform, tile_scale)
            return df


def prepare_sankey_data(
    ee_collection,
    band_name,
    transition_periods,
    class_info,
    geometry,
    scale=30,
    crs=None,
    transform=None,
    tile_scale=4,
    area_format="Percentage",
    min_percentage=0.2,
):
    """
    Build a Sankey diagram dataset from class transitions across time periods.

    For each consecutive pair of periods, this function:
    1. Filters the collection to each period
    2. Computes the mode for each period
    3. Creates a transition image encoding ``{from}0990{to}``
    4. Runs ``frequencyHistogram`` to count transitions
    5. Parses results into both a source/target/value DataFrame and a
       transition matrix DataFrame

    Args:
        ee_collection (ee.ImageCollection): The input collection.
        band_name (str): The thematic band to analyze.
        transition_periods (list): List of ``[start_year, end_year]`` pairs.
        class_info (dict): Class info dict for the band (from :func:`get_obj_info`).
        geometry: ``ee.Geometry`` or ``ee.Feature``.
        scale (int, optional): Pixel scale in meters.
        crs (str, optional): CRS string.
        transform (list, optional): Affine transform.
        tile_scale (int, optional): Tile scale for parallelism.
        area_format (str, optional): Area unit.
        min_percentage (float, optional): Minimum percentage threshold for including a
            flow in the source-target table. The transition matrix always
            includes all observed transitions regardless of this threshold.

    Returns:
        tuple: ``(sankey_df, matrix_dict)``

        - **sankey_df** (``pandas.DataFrame``): Source-target-value table with
          columns ``source``, ``target``, ``value``, ``source_name``,
          ``target_name``, ``source_color``, ``target_color``, ``period``.
          Flows below ``min_percentage`` are excluded.
        - **matrix_dict** (``dict[str, pandas.DataFrame]``): One transition
          matrix per consecutive period pair, keyed by
          ``"{from_period} \u2192 {to_period}"``. Each DataFrame has class
          names as both row and column labels, with values as converted
          counts.

    Examples:
        Typically called via ``summarize_and_chart(chart_type='sankey')``, but can
        be used directly for custom sankey workflows:

        >>> import geeViz.geeView as gv
        >>> from geeViz.outputLib import charts as cl
        >>> ee = gv.ee
        >>> study_area = ee.Geometry.Polygon(
        ...     [[[-106, 39.5], [-105, 39.5], [-105, 40.5], [-106, 40.5]]]
        ... )
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")
        >>> info = cl.get_obj_info(lcms.select(['Land_Use']))
        >>> sankey_df, matrix_dict = cl.prepare_sankey_data(
        ...     lcms.select(['Land_Use']),
        ...     'Land_Use',
        ...     transition_periods=[[1990, 2000], [2000, 2010], [2010, 2023]],
        ...     class_info=info['class_info']['Land_Use'],
        ...     geometry=study_area,
        ...     scale=30,
        ... )
        >>> print(sankey_df.head().to_markdown())
        >>> for label, mdf in matrix_dict.items():
        ...     print(f"\\n{label}")
        ...     print(mdf.to_markdown())
    """
    _, geo = detect_geometry_type(geometry)

    info = class_info.get(band_name, class_info.get(list(class_info.keys())[0], {}))
    class_values = info.get("class_values", [])
    class_names = info.get("class_names", [])
    class_palette = info.get("class_palette", [])

    value_to_idx = {v: i for i, v in enumerate(class_values)}
    idx_to_name = {i: n for i, n in enumerate(class_names)}
    idx_to_color = {i: _ensure_hex_color(c) for i, c in enumerate(class_palette)}
    num_classes = len(class_values)

    scale_mult = (scale / AREA_FORMAT_DICT["Hectares"]["scale"]) ** 2

    all_rows = []
    transition_band_names = []

    # Build transition images for each consecutive period pair
    transition_images = []
    period_labels = []

    for i in range(len(transition_periods) - 1):
        p1 = transition_periods[i]
        p2 = transition_periods[i + 1]

        p1_start, p1_end = (p1, p1) if not isinstance(p1, (list, tuple)) else (p1[0], p1[-1])
        p2_start, p2_end = (p2, p2) if not isinstance(p2, (list, tuple)) else (p2[0], p2[-1])

        # Filter and compute mode for each period
        filtered1 = ee_collection.filter(
            ee.Filter.calendarRange(int(p1_start), int(p1_end), "year")
        ).select([band_name])
        filtered2 = ee_collection.filter(
            ee.Filter.calendarRange(int(p2_start), int(p2_end), "year")
        ).select([band_name])

        mode1 = filtered1.mode().rename(["from"])
        mode2 = filtered2.mode().rename(["to"])

        # Encode transition: from_class * 10000 + 9900 + to_class
        combined = mode1.addBands(mode2)
        transition = (
            combined.select("from").multiply(10000)
            .add(9900)
            .add(combined.select("to"))
            .rename([f"{_format_period(p1)}---{_format_period(p2)}"])
        )

        transition_images.append(transition)
        transition_band_names.append(f"{_format_period(p1)}---{_format_period(p2)}")
        period_labels.append((_format_period(p1), _format_period(p2)))

    # Stack all transition images
    if len(transition_images) == 1:
        stacked = transition_images[0]
    else:
        stacked = transition_images[0]
        for t_img in transition_images[1:]:
            stacked = stacked.addBands(t_img)

    # Run frequency histogram
    raw = reduce_region(
        stacked.toInt(), geo, ee.Reducer.frequencyHistogram(), scale, crs, transform, tile_scale
    )

    # Parse results — build both the source-target table and per-period matrices
    matrix_dict = {}  # {period_label: DataFrame} — one matrix per transition pair

    for ti, t_bn in enumerate(transition_band_names):
        histogram = raw.get(t_bn, {})
        if histogram is None:
            histogram = {}

        pixel_total = sum(histogram.values()) or 1
        p1_label, p2_label = period_labels[ti]
        offset1 = ti * num_classes
        offset2 = (ti + 1) * num_classes

        # Build count_lookup: (from_idx, to_idx) -> display_val for ALL transitions
        count_lookup = {}
        for encoded_str, count in histogram.items():
            encoded = int(float(encoded_str))
            from_class = encoded // 10000
            to_class = encoded % 10000 - 9900

            from_idx = value_to_idx.get(from_class)
            to_idx = value_to_idx.get(to_class)
            if from_idx is None or to_idx is None:
                continue

            # Compute display value
            pct = (count / pixel_total) * 100
            if area_format == "Percentage":
                display_val = round(pct, 2)
            elif area_format == "Pixels":
                display_val = count
            else:
                mult = AREA_FORMAT_DICT[area_format]["mult"] * scale_mult
                display_val = round(count * mult, AREA_FORMAT_DICT[area_format]["places"])

            count_lookup[(from_idx, to_idx)] = display_val

            # Source-target table: only include flows above min_percentage
            if pct >= min_percentage:
                all_rows.append(
                    {
                        "source": from_idx + offset1,
                        "target": to_idx + offset2,
                        "value": display_val,
                        "source_name": f"{p1_label} {idx_to_name.get(from_idx, str(from_class))}",
                        "target_name": f"{p2_label} {idx_to_name.get(to_idx, str(to_class))}",
                        "source_color": idx_to_color.get(from_idx, "#888888"),
                        "target_color": idx_to_color.get(to_idx, "#888888"),
                        "period": f"{p1_label} -> {p2_label}",
                    }
                )

        # Build transition matrix for this period pair
        # Columns are "to" class names, rows are "from" class names
        period_rows = []
        for fi in range(num_classes):
            row_label = idx_to_name.get(fi, str(fi))
            row_data = {"": row_label}
            for ti2 in range(num_classes):
                col_label = idx_to_name.get(ti2, str(ti2))
                row_data[col_label] = count_lookup.get((fi, ti2), 0)
            period_rows.append(row_data)

        period_key = f"{p1_label} \u2192 {p2_label}"
        if period_rows:
            mdf = pandas.DataFrame(period_rows).set_index("")
            mdf.index.name = None
            matrix_dict[period_key] = mdf

    # Build sankey_df
    empty_cols = ["source", "target", "value", "source_name", "target_name", "source_color", "target_color", "period"]
    if not all_rows:
        sankey_df = pandas.DataFrame(columns=empty_cols)
    else:
        sankey_df = pandas.DataFrame(all_rows)

    return (sankey_df, matrix_dict)


###########################################################################
#                          Chart functions
###########################################################################


def chart_time_series(
    df,
    colors=None,
    chart_type="line+markers",
    title="Time Series",
    x_label="Year",
    y_label=None,
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    label_max_length=30,
    legend_position="right",
    line_width=2,
    marker_size=5,
    max_x_tick_labels=10,
    max_y_tick_labels=None,
):
    """
    Create a Plotly time series chart from a zonal stats DataFrame.

    Args:
        df (pandas.DataFrame): Output of :func:`zonal_stats` for an ImageCollection.
            Index = x-axis labels, columns = data series.
        colors (list, optional): Hex color strings for each column.
        chart_type (str, optional): ``"line+markers"`` (default), ``"line"``,
            ``"bar"``, ``"stacked_line"``, ``"stacked_line+markers"``, or
            ``"stacked_bar"``.
        title (str, optional): Chart title.
        x_label (str, optional): X-axis label.
        y_label (str, optional): Y-axis label.
        width (int, optional): Chart width in pixels.
        height (int, optional): Chart height in pixels.
        label_max_length (int, optional): Max characters for legend labels.
        legend_position (dict or str, optional): Plotly legend layout dict
            (e.g. ``{"orientation": "h", "x": 0.5, "y": -0.1}``), or
            ``"right"``/``None`` for the Plotly default.
        line_width (int or float, optional): Line width in pixels for
            line/scatter traces. Defaults to ``2``.
        marker_size (int or float, optional): Marker diameter in pixels
            for traces that include markers. Defaults to ``5``.
        max_x_tick_labels (int, optional): Maximum number of x-axis tick
            labels to display. When the number of x values exceeds this,
            labels are thinned to every 2nd, 5th, 10th, etc. value.
            Defaults to ``10``.  Set to ``None`` or ``0`` to disable.
        max_y_tick_labels (int, optional): Maximum number of y-axis tick
            labels. Uses Plotly's ``nticks``. Defaults to ``None``
            (automatic).

    Returns:
        plotly.graph_objects.Figure

    Examples:
        Build a time series chart from a zonal_stats DataFrame:

        >>> import geeViz.geeView as gv
        >>> from geeViz.outputLib import charts as cl
        >>> ee = gv.ee
        >>> study_area = ee.Geometry.Polygon(
        ...     [[[-106, 39.5], [-105, 39.5], [-105, 40.5], [-106, 40.5]]]
        ... )
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")
        >>> # Step 1: get the data
        >>> info = cl.get_obj_info(lcms.select(['Land_Cover']))
        >>> df = cl.zonal_stats(
        ...     lcms.select(['Land_Cover']), study_area,
        ... )
        >>> # Step 2: chart it with class colors
        >>> colors = info['class_info']['Land_Cover']['class_palette']
        >>> fig = cl.chart_time_series(
        ...     df, colors=colors,
        ...     title='LCMS Land Cover',
        ...     y_label='% Area',
        ... )
        >>> fig.show()
    """
    plotly_mode, is_stacked = _parse_chart_type(chart_type)
    fig = go.Figure()

    x_values = list(df.index)
    # Convert pure-integer labels (e.g. years) to int so Plotly uses a
    # linear axis with automatic tick spacing instead of a categorical axis
    # that crams every label together.  Mirrors the JS parseInt() logic.
    try:
        x_values = [int(v) for v in x_values]
    except (ValueError, TypeError):
        pass
    columns = list(df.columns)

    for i, col in enumerate(columns):
        color = None
        if colors and i < len(colors):
            color = _ensure_hex_color(colors[i])

        label = col[:label_max_length]

        if plotly_mode == "bar":
            fig.add_trace(
                go.Bar(
                    x=x_values,
                    y=df[col].values,
                    name=label,
                    marker_color=color,
                )
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=df[col].values,
                    mode=plotly_mode,
                    name=label,
                    line=dict(color=color, width=line_width),
                    marker=dict(color=color, size=marker_size),
                    stackgroup="one" if is_stacked else None,
                )
            )

    bar_mode = "stack" if is_stacked and plotly_mode == "bar" else ("group" if plotly_mode == "bar" else None)

    # Determine x tick values — thin if there are too many
    is_int_x = all(isinstance(v, int) for v in x_values)
    x_tick_vals = x_values if is_int_x else None
    if x_tick_vals is not None:
        thinned = _thin_tick_vals(x_tick_vals, max_x_tick_labels)
        if thinned is not None:
            x_tick_vals = thinned

    # Y-axis: add '%' suffix when label indicates percentage
    y_kw = dict(title=y_label, automargin=True)
    if y_label and "%" in y_label:
        y_kw["ticksuffix"] = "%"
    if max_y_tick_labels is not None and max_y_tick_labels > 0:
        y_kw["nticks"] = max_y_tick_labels

    # Build x-axis kwargs — constrain range to eliminate dead space
    x_kw = dict(title=x_label, tickangle=45, tickvals=x_tick_vals,
                tickformat="d" if is_int_x else None)
    if is_int_x and x_values:
        x_kw["range"] = [min(x_values) - 0.5, max(x_values) + 0.5]

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        xaxis=x_kw,
        yaxis=y_kw,
        legend=_legend_kwargs(legend_position),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=width,
        height=height,
        margin=dict(l=35, r=25, b=50, t=50, pad=5),
        barmode=bar_mode,
        hovermode="x unified",
    )

    _themes.apply_plotly_theme(fig, "dark")
    return fig


def chart_bar(
    df,
    colors=None,
    title="Class Distribution",
    y_label=None,
    max_classes=30,
    chart_type="bar",
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    legend_position="right",
):
    """
    Create a Plotly bar chart from a single-Image zonal stats DataFrame.

    Automatically chooses horizontal or vertical orientation based on label length.

    Args:
        df (pandas.DataFrame): Output of :func:`zonal_stats` for a single Image.
            Single row, columns = class names.
        colors (list, optional): Hex color strings for each bar.
        title (str, optional): Chart title.
        y_label (str, optional): Value axis label.
        max_classes (int, optional): Maximum number of classes to display.
        width (int, optional): Chart width in pixels.
        height (int, optional): Chart height in pixels.
        legend_position (dict or str, optional): Plotly legend layout dict
            (e.g. ``{"orientation": "h", "x": 0.5, "y": -0.1}``), or
            ``"right"``/``None`` for the Plotly default.

    Returns:
        plotly.graph_objects.Figure

    Examples:
        Bar chart of NLCD land cover for a single image:

        >>> import geeViz.geeView as gv
        >>> from geeViz.outputLib import charts as cl
        >>> ee = gv.ee
        >>> study_area = ee.Geometry.Polygon(
        ...     [[[-106, 39.5], [-105, 39.5], [-105, 40.5], [-106, 40.5]]]
        ... )
        >>> nlcd = ee.ImageCollection(
        ...     "USGS/NLCD_RELEASES/2021_REL/NLCD"
        ... ).select(['landcover']).mode().set(
        ...     ee.ImageCollection("USGS/NLCD_RELEASES/2021_REL/NLCD")
        ...     .first().toDictionary()
        ... )
        >>> info = cl.get_obj_info(nlcd)
        >>> df = cl.zonal_stats(nlcd, study_area)
        >>> colors = info['class_info']['landcover']['class_palette']
        >>> fig = cl.chart_bar(
        ...     df, colors=colors, title='NLCD Land Cover',
        ... )
        >>> fig.show()
    """
    # Flatten to series
    if len(df) == 1:
        values = df.iloc[0]
    else:
        values = df.sum()

    labels = list(values.index)
    vals = list(values.values)

    # Cap at max_classes (keep top N by value)
    if len(labels) > max_classes:
        sorted_pairs = sorted(zip(vals, labels, range(len(labels))), reverse=True)
        sorted_pairs = sorted_pairs[:max_classes]
        sorted_pairs.sort(key=lambda x: x[2])  # restore original order
        vals = [p[0] for p in sorted_pairs]
        labels = [p[1] for p in sorted_pairs]
        # Also filter colors
        if colors:
            idxs = [p[2] for p in sorted_pairs]
            colors = [_ensure_hex_color(colors[i]) for i in idxs if i < len(colors)]

    if colors:
        if len(colors) < len(labels):
            # Interpolate palette as a continuous ramp (matches JS min/max/palette)
            colors = _interpolate_palette(colors, len(labels))
        else:
            colors = [_ensure_hex_color(c) for c in colors[:len(labels)]]

    _, is_stacked = _parse_chart_type(chart_type)

    # Determine orientation
    max_label_len = max((len(str(l)) for l in labels), default=0)
    orientation = "h" if max_label_len > max(len(labels), 6) else "v"

    fig = go.Figure()

    if is_stacked:
        # Stacked bar: one trace per class so barmode="stack" works
        for i, (lbl, val) in enumerate(zip(labels, vals)):
            color = colors[i] if colors and i < len(colors) else None
            if orientation == "h":
                fig.add_trace(go.Bar(
                    y=[""], x=[val], name=str(lbl), orientation="h",
                    marker_color=color,
                ))
            else:
                fig.add_trace(go.Bar(
                    x=[""], y=[val], name=str(lbl),
                    marker_color=color,
                ))
        barmode = "stack"
    else:
        # Standard: single trace with per-bar colors
        if orientation == "h":
            fig.add_trace(go.Bar(
                y=labels, x=vals, orientation="h", marker_color=colors,
            ))
        else:
            fig.add_trace(go.Bar(
                x=labels, y=vals, orientation="v", marker_color=colors,
            ))
        barmode = None

    if orientation == "h":
        fig.update_layout(
            xaxis=dict(title=y_label, automargin=True),
            yaxis=dict(automargin=True),
            margin=dict(l=80, r=25, b=30, t=50, pad=5),
        )
    else:
        fig.update_layout(
            xaxis=dict(tickangle=45, automargin=True),
            yaxis=dict(title=y_label, automargin=True),
            margin=dict(l=35, r=25, b=80, t=50, pad=5),
        )

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        legend=_legend_kwargs(legend_position),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=width,
        height=height,
        barmode=barmode,
        hovermode="closest",
    )

    _themes.apply_plotly_theme(fig, "dark")
    return fig


# ---------------------------------------------------------------------------
#  Donut chart
# ---------------------------------------------------------------------------
def chart_donut(
    df,
    colors=None,
    title="Class Distribution",
    max_classes=30,
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    legend_position="right",
    hole=0.45,
):
    """Create a Plotly donut chart from a single-Image zonal stats DataFrame.

    Only valid for **thematic** (categorical) data from a single
    ``ee.Image``.  Raises ``ValueError`` for continuous data or
    ``ee.ImageCollection`` inputs.

    Args:
        df (pandas.DataFrame): Output of :func:`zonal_stats` for a single
            Image.  Single row, columns = class names, values = area/%.
        colors (list, optional): Hex colour strings, one per class.
        title (str, optional): Chart title.
        max_classes (int, optional): Maximum number of classes to display.
            Smaller classes are grouped into "Other".  Defaults to ``30``.
        width (int, optional): Chart width in pixels.
        height (int, optional): Chart height in pixels.
        legend_position (dict or str, optional): Plotly legend dict or
            ``"right"`` / ``"bottom"``.
        hole (float, optional): Size of the centre hole (0–1).
            Defaults to ``0.45``.

    Returns:
        plotly.graph_objects.Figure
    """
    import plotly.graph_objects as go

    # Flatten to series
    if len(df) == 1:
        values = df.iloc[0]
    else:
        values = df.sum()

    labels = list(values.index)
    vals = list(values.values)

    # Cap at max_classes — group the rest into "Other"
    if len(labels) > max_classes:
        sorted_pairs = sorted(zip(vals, labels, range(len(labels))), reverse=True)
        top = sorted_pairs[:max_classes]
        other_val = sum(p[0] for p in sorted_pairs[max_classes:])
        top.sort(key=lambda x: x[2])  # restore original order
        vals = [p[0] for p in top] + [other_val]
        labels = [p[1] for p in top] + ["Other"]
        if colors:
            idxs = [p[2] for p in top]
            colors = [_ensure_hex_color(colors[i]) for i in idxs if i < len(colors)] + ["#888888"]

    if colors:
        if len(colors) < len(labels):
            colors = _interpolate_palette(colors, len(labels))
        else:
            colors = [_ensure_hex_color(c) for c in colors[:len(labels)]]

    # Filter out zero-value slices
    filtered = [(l, v, c) for l, v, c in zip(labels, vals, colors or [None] * len(labels)) if v > 0]
    if filtered:
        labels, vals, _colors = zip(*filtered)
        labels, vals = list(labels), list(vals)
        if colors:
            colors = list(_colors)

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=vals,
        hole=hole,
        marker=dict(colors=colors) if colors else {},
        textinfo="percent",
        hoverinfo="label+value+percent",
        textfont=dict(size=12),
    )])

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        legend=_legend_kwargs(legend_position),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=width,
        height=height,
        margin=dict(l=10, r=10, b=10, t=40, pad=0),
    )

    _themes.apply_plotly_theme(fig, "dark")
    return fig


def chart_donut_multi_feature(
    df,
    colors=None,
    title="Class Distribution by Feature",
    max_classes=30,
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    columns=2,
    legend_position="bottom",
    hole=0.45,
):
    """Create a subplot grid of donut charts, one per feature.

    For multi-feature ``reduceRegions`` output where the DataFrame index
    is the feature label and columns are class names.

    Args:
        df (pandas.DataFrame): Output of :func:`zonal_stats` with
            ``feature_label`` set.  Index = feature names, columns =
            class names, values = area/%.
        colors (list, optional): Hex colour strings, one per class.
        title (str, optional): Overall chart title.
        max_classes (int, optional): Max classes per donut.
        width (int, optional): Chart width in pixels.
        height (int, optional): Chart height in pixels.
        columns (int, optional): Number of subplot columns.
        legend_position (dict or str, optional): Legend position.
        hole (float, optional): Centre hole size.

    Returns:
        plotly.graph_objects.Figure
    """
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    feature_names = list(df.index)
    n_features = len(feature_names)
    n_cols = min(columns, n_features)
    n_rows = -(-n_features // n_cols)  # ceil division

    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        specs=[[{"type": "pie"}] * n_cols for _ in range(n_rows)],
        subplot_titles=feature_names,
    )

    class_labels = list(df.columns)

    # Prepare colors
    pal = None
    if colors:
        if len(colors) < len(class_labels):
            pal = _interpolate_palette(colors, len(class_labels))
        else:
            pal = [_ensure_hex_color(c) for c in colors[:len(class_labels)]]

    for idx, feat_name in enumerate(feature_names):
        row_i = idx // n_cols + 1
        col_i = idx % n_cols + 1
        vals = list(df.loc[feat_name])

        # Filter zero-value slices
        filtered = [(l, v, c) for l, v, c in zip(class_labels, vals, pal or [None] * len(class_labels)) if v > 0]
        if filtered:
            f_labels, f_vals, f_colors = zip(*filtered)
            f_labels, f_vals = list(f_labels), list(f_vals)
            if pal:
                f_colors = list(f_colors)
            else:
                f_colors = None
        else:
            f_labels, f_vals, f_colors = class_labels, vals, pal

        fig.add_trace(
            go.Pie(
                labels=f_labels,
                values=f_vals,
                hole=hole,
                marker=dict(colors=f_colors) if f_colors else {},
                textinfo="percent",
                hoverinfo="label+value+percent",
                textfont=dict(size=11),
                showlegend=(idx == 0),  # legend from first trace only
                name=feat_name,
            ),
            row=row_i, col=col_i,
        )

    # Scale figure size by grid
    fig_w = width * n_cols
    fig_h = height * n_rows

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        legend=_legend_kwargs(legend_position),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=fig_w,
        height=fig_h,
    )

    _themes.apply_plotly_theme(fig, "dark")
    return fig


# ---------------------------------------------------------------------------
#  Scatter chart
# ---------------------------------------------------------------------------
def chart_scatter(
    df,
    x_band,
    y_band,
    feature_label=None,
    title="Scatter Plot",
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    legend_position="right",
    trendline=True,
    opacity=0.7,
    show_labels=None,
    thematic_col=None,
    class_names=None,
    class_palette=None,
    class_values=None,
):
    """Create a scatter plot of two bands across features.

    Each point represents one feature (e.g. a county, fire perimeter, or
    watershed).  The x- and y-axes show the mean (or other reduced) value
    of two image bands over that feature.

    When *thematic_col* is provided, points are colored by the thematic
    class value in that column, using the class palette and names from
    image properties.

    Args:
        df (pandas.DataFrame): DataFrame with at least two numeric
            columns for the x and y bands.  Optionally a *thematic_col*
            column with integer class values.
        x_band (str): Column name for the x-axis.
        y_band (str): Column name for the y-axis.
        feature_label (str, optional): Name of the index (used in hover).
        title (str, optional): Chart title.
        width (int, optional): Chart width in pixels.
        height (int, optional): Chart height in pixels.
        legend_position (dict or str, optional): Legend position.
        trendline (bool, optional): Draw a linear trendline.
            Defaults to ``True``.
        opacity (float, optional): Point opacity (0-1).  Lower values
            help visualize overlapping points.  Defaults to ``0.7``.
        show_labels (bool, optional): Label each point with the feature
            name.  When ``None`` (default), labels are shown only when
            the DataFrame has fewer than 30 rows.
        thematic_col (str, optional): Column containing thematic class
            values used to color each point.  Defaults to ``None``.
        class_names (list, optional): Class name strings matching
            *class_values*.
        class_palette (list, optional): Hex colour strings matching
            *class_values*.
        class_values (list, optional): Integer class values that map
            to *class_names* and *class_palette*.

    Returns:
        plotly.graph_objects.Figure
    """
    import plotly.graph_objects as go
    import numpy as np

    x_vals = df[x_band].values.astype(float)
    y_vals = df[y_band].values.astype(float)
    labels = list(df.index)

    # Auto-decide whether to show text labels
    if show_labels is None:
        show_labels = len(df) < 30

    mode = "markers+text" if show_labels else "markers"
    marker_size = 8 if len(df) > 50 else 10

    fig = go.Figure()

    # --- Thematic color: one trace per class for legend ---
    if thematic_col is not None and thematic_col in df.columns:
        cat_vals = df[thematic_col].values
        # Build lookup: class_value -> (name, color)
        _val_to_name = {}
        _val_to_color = {}
        if class_values and class_names:
            for v, n in zip(class_values, class_names):
                _val_to_name[v] = n
        if class_values and class_palette:
            for v, c in zip(class_values, class_palette):
                _val_to_color[v] = _ensure_hex_color(c)

        unique_classes = sorted(set(int(v) for v in cat_vals if np.isfinite(v)))

        for cls_val in unique_classes:
            mask = cat_vals == cls_val
            cls_name = _val_to_name.get(cls_val, str(cls_val))
            cls_color = _val_to_color.get(cls_val, None)

            cls_x = x_vals[mask]
            cls_y = y_vals[mask]
            cls_labels = [labels[i] for i, m in enumerate(mask) if m]

            hover_parts = []
            if show_labels:
                hover_parts.append("<b>%{text}</b><br>")
            hover_parts.append(
                f"{x_band}: %{{x:.2f}}<br>"
                f"{y_band}: %{{y:.2f}}<br>"
                f"{thematic_col}: {cls_name}"
                "<extra></extra>"
            )

            fig.add_trace(go.Scatter(
                x=cls_x,
                y=cls_y,
                mode=mode,
                name=cls_name,
                text=cls_labels if show_labels else None,
                textposition="top center" if show_labels else None,
                textfont=dict(size=9) if show_labels else None,
                marker=dict(
                    size=marker_size,
                    color=cls_color,
                    opacity=opacity,
                    line=dict(width=0.5, color="#333"),
                ),
                hovertemplate="".join(hover_parts),
                legendgroup=cls_name,
            ))

    else:
        # --- Single color (no thematic) ---
        hover_parts = []
        if show_labels:
            hover_parts.append("<b>%{text}</b><br>")
        else:
            hover_parts.append("<b>Point %{pointNumber}</b><br>")
        hover_parts.append(
            f"{x_band}: %{{x:.2f}}<br>"
            f"{y_band}: %{{y:.2f}}"
            "<extra></extra>"
        )

        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode=mode,
            text=labels if show_labels else None,
            textposition="top center" if show_labels else None,
            textfont=dict(size=10) if show_labels else None,
            marker=dict(
                size=marker_size,
                color="#66c2a5",
                opacity=opacity,
                line=dict(width=0.5, color="#333"),
            ),
            hovertemplate="".join(hover_parts),
            showlegend=False,
        ))

    # Trendline
    if trendline and len(x_vals) > 1:
        mask = np.isfinite(x_vals) & np.isfinite(y_vals)
        if mask.sum() > 1:
            coeffs = np.polyfit(x_vals[mask], y_vals[mask], 1)
            x_line = np.linspace(x_vals[mask].min(), x_vals[mask].max(), 50)
            y_line = np.polyval(coeffs, x_line)
            r_sq = np.corrcoef(x_vals[mask], y_vals[mask])[0, 1] ** 2
            fig.add_trace(go.Scatter(
                x=x_line, y=y_line,
                mode="lines",
                line=dict(color="#fc8d62", width=2, dash="dash"),
                name=f"R\u00b2 = {r_sq:.3f}",
                showlegend=True,
            ))

    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        xaxis_title=x_band,
        yaxis_title=y_band,
        legend=_legend_kwargs(legend_position),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=width,
        height=height,
        hovermode="closest",
    )

    _themes.apply_plotly_theme(fig, "dark")
    return fig


def chart_grouped_bar(
    df,
    colors=None,
    title="Zonal Summary by Feature",
    y_label=None,
    chart_type="bar",
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    legend_position="right",
):
    """
    Create a grouped (or stacked) bar chart for multi-feature zonal stats.

    Each group on the x-axis is a feature (row) and each bar/segment within the
    group is a class (column). This is the natural chart type when
    ``reduceRegions`` returns one row per zone.

    Args:
        df (pandas.DataFrame): Rows = features (index used as labels),
            columns = class names, values = numeric area/percentage.
        colors (list, optional): Hex color strings, one per column (class).
        title (str, optional): Chart title.
        y_label (str, optional): Y-axis label.
        stacked (bool, optional): Stack bars instead of grouping. Defaults to False.
        width (int, optional): Chart width in pixels.
        height (int, optional): Chart height in pixels.
        legend_position (dict or str, optional): Plotly legend layout dict
            (e.g. ``{"orientation": "h", "x": 0.5, "y": -0.1}``), or
            ``"right"``/``None`` for the Plotly default.

    Returns:
        plotly.graph_objects.Figure

    Examples:
        Compare land cover across the 5 largest MTBS fire perimeters:

        >>> import geeViz.geeView as gv
        >>> from geeViz.outputLib import charts as cl
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")
        >>> fires = ee.FeatureCollection(
        ...     "USFS/GTAC/MTBS/burned_area_boundaries/v1"
        ... ).sort("BurnBndAc", False).limit(5)
        >>> lc_mode = lcms.select(["Land_Cover"]).mode().set(
        ...     lcms.first().toDictionary()
        ... )
        >>> # summarize_and_chart handles reduceRegions + grouped bar:
        >>> df, fig = cl.summarize_and_chart(
        ...     lc_mode, fires,
        ...     feature_label="Incid_Name",
        ...     title="Land Cover — 5 Largest Fires",
        ...     stacked=True, width=800,
        ... )
        >>> fig.show()
    """
    fig = go.Figure()
    feature_labels = [str(v) for v in df.index]

    for i, col in enumerate(df.columns):
        color = None
        if colors and i < len(colors) and colors[i] is not None:
            color = _ensure_hex_color(colors[i])

        fig.add_trace(
            go.Bar(
                name=str(col),
                x=feature_labels,
                y=df[col].values,
                marker_color=color,
            )
        )

    fig.update_layout(
        barmode="stack" if chart_type in ("stacked_bar", "stacked") else "group",
        title=dict(text=title, x=0.5, xanchor="center"),
        xaxis=dict(title="Feature", tickangle=45, automargin=True),
        yaxis=dict(title=y_label or "", automargin=True),
        legend=_legend_kwargs(legend_position),
        plot_bgcolor=DEFAULT_PLOT_BGCOLOR,
        paper_bgcolor=DEFAULT_PLOT_BGCOLOR,
        font=dict(family=DEFAULT_PLOT_FONT),
        width=width,
        height=height,
        margin=dict(l=35, r=25, b=80, t=50, pad=5),
        hovermode="x unified",
    )

    _themes.apply_plotly_theme(fig, "dark")
    return fig


def chart_sankey_d3(
    sankey_df,
    class_names,
    class_palette,
    transition_periods,
    title="Class Transitions",
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    node_thickness=20,
    node_pad=15,
    opacity=0.9,
    theme="dark",
    bg_color=None,
    font_color=None,
    hide_toolbar=False,
):
    """Create a D3 Sankey diagram directly from transition data — no Plotly.

    Builds a self-contained HTML string with native SVG ``linearGradient``
    elements so each link fades from its source node color to its target
    node color.  Uses ``d3-sankey`` for layout.

    This is the preferred rendering path for Sankey charts.  Unlike
    :func:`chart_sankey` (which builds a Plotly figure that must be
    post-processed by :func:`sankey_to_html` for gradients), this function
    goes straight from the raw ``sankey_df`` to D3 HTML.

    Args:
        sankey_df (pandas.DataFrame): Output of :func:`prepare_sankey_data`.
            Columns: ``source``, ``target``, ``value``, ``source_name``,
            ``target_name``, ``source_color``, ``target_color``.
        class_names (list): List of class names.
        class_palette (list): List of hex color strings.
        transition_periods (list): Period list (for node labeling).
        title (str, optional): Chart title. Defaults to ``"Class Transitions"``.
        width (int, optional): Chart width in pixels.
        height (int, optional): Chart height in pixels.
        node_thickness (int, optional): Sankey node bar thickness.
        node_pad (int, optional): Padding between Sankey nodes.
        opacity (float, optional): Link opacity (0-1). Defaults to 0.9.
        theme (str, optional): Theme preset. Defaults to ``"dark"``.
        bg_color (str, optional): Background color override.
        font_color (str, optional): Font color override.
        hide_toolbar (bool, optional): Hide the download button.

    Returns:
        str: Self-contained HTML string with embedded D3 Sankey chart.

    Examples:
        >>> sankey_df, matrix_dict = cl.prepare_sankey_data(
        ...     lcms.select(['Land_Use']), 'Land_Use',
        ...     transition_periods=[1990, 2005, 2023],
        ...     class_info=info['class_info'], geometry=study_area,
        ... )
        >>> html = cl.chart_sankey_d3(
        ...     sankey_df, info['class_info']['Land_Use']['class_names'],
        ...     info['class_info']['Land_Use']['class_palette'],
        ...     transition_periods=[1990, 2005, 2023],
        ... )
    """
    import json as _json

    _t = _themes.get_theme(theme, bg_color=bg_color, font_color=font_color)

    if sankey_df.empty:
        return f"<html><body style='background:{_t.bg_hex};color:{_t.text_hex}'><p>No transitions found</p></body></html>"

    # Build node labels and hex colors for all period slots
    num_classes = len(class_names)
    labels = []
    node_colors_hex = []
    for p in transition_periods:
        p_label = _format_period(p)
        for i, name in enumerate(class_names):
            labels.append(f"{p_label} {name}")
            node_colors_hex.append(
                _ensure_hex_color(class_palette[i]) if i < len(class_palette) else "#888888"
            )

    # Build used-node set and remap indices (skip orphan nodes)
    used_indices = set()
    for _, row in sankey_df.iterrows():
        if row["value"] > 0:
            used_indices.add(int(row["source"]))
            used_indices.add(int(row["target"]))

    old_to_new = {}
    new_idx = 0
    for old_idx in range(len(labels)):
        if old_idx in used_indices:
            old_to_new[old_idx] = new_idx
            new_idx += 1

    d3_data = {
        "nodes": [
            {"name": labels[i], "color": node_colors_hex[i]}
            for i in range(len(labels))
            if i in used_indices
        ],
        "links": [
            {
                "source": old_to_new[int(row["source"])],
                "target": old_to_new[int(row["target"])],
                "value": float(row["value"]),
                "sourceColor": _ensure_hex_color(row.get("source_color", "#888")),
                "targetColor": _ensure_hex_color(row.get("target_color", "#888")),
            }
            for _, row in sankey_df.iterrows()
            if row["value"] > 0
            and int(row["source"]) in old_to_new
            and int(row["target"]) in old_to_new
        ],
    }

    d3_config = {
        "title": title,
        "width": width,
        "height": height,
        "nodeWidth": node_thickness,
        "nodePadding": node_pad,
        "opacity": opacity,
        "bgColor": _t.bg_hex,
        "textColor": _t.text_hex,
    }

    html = _render_d3_sankey(_t)
    result = html.replace(
        "__D3_DATA_JSON__", _json.dumps(d3_data)
    ).replace(
        "__D3_CONFIG_JSON__", _json.dumps(d3_config)
    )
    if hide_toolbar:
        result = result.replace(
            '<div id="toolbar">',
            '<div id="toolbar" style="display:none">',
        )
    return result


def sankey_iframe(sankey_html, width=None, height=None):
    """Wrap sankey D3 HTML in an iframe for Jupyter notebook display.

    Jupyter sanitizes ``<script>`` tags in ``display(HTML(...))``, so
    D3 sankey charts must be embedded in an iframe.  Uses a
    ``data:text/html;base64`` src for maximum compatibility across
    Jupyter environments (classic notebook, JupyterLab, VS Code).

    Args:
        sankey_html (str): Full HTML string from :func:`chart_sankey_d3`
            or ``summarize_and_chart(chart_type='sankey')``.
        width (int, optional): Iframe width in pixels. Auto-detected
            from the HTML when ``None``.
        height (int, optional): Iframe height in pixels. Auto-detected
            from the HTML when ``None``.

    Returns:
        str: HTML ``<iframe>`` element suitable for
        ``display(HTML(...))``.

    Example:
        >>> from IPython.display import HTML, display
        >>> display(HTML(cl.sankey_iframe(sankey_html)))
    """
    import base64, re
    if width is None:
        m = re.search(r'"width"\s*:\s*(\d+)', sankey_html)
        width = int(m.group(1)) + 50 if m else 900
    if height is None:
        m = re.search(r'"height"\s*:\s*(\d+)', sankey_html)
        height = int(m.group(1)) + 80 if m else 650
    b64 = base64.b64encode(sankey_html.encode("utf-8")).decode("ascii")
    return (
        f'<iframe src="data:text/html;base64,{b64}" '
        f'style="width:{width}px;height:{height}px;border:none;overflow:hidden;">'
        f'</iframe>'
    )


###########################################################################
#                        Convenience function
###########################################################################


def summarize_and_chart(
    ee_obj,
    geometry,
    band_names=None,
    reducer=None,
    scale=30,
    crs=None,
    transform=None,
    tile_scale=4,
    area_format="Percentage",
    x_axis_property="system:time_start",
    date_format="YYYY",
    title=None,
    chart_type=None,
    sankey=False,
    transition_periods=None,
    sankey_band_name=None,
    min_percentage=0.2,
    palette=None,
    feature_label=None,
    width=DEFAULT_CHART_WIDTH,
    height=DEFAULT_CHART_HEIGHT,
    opacity=0.9,
    legend_position="right",
    columns=2,
    include_masked_area=True,
    stacked=None,  # deprecated — use chart_type instead
    thematic_band_name=None,
    line_width=2,
    marker_size=5,
    class_visible=None,
    max_x_tick_labels=10,
    max_y_tick_labels=None,
):
    """
    Run zonal statistics and produce a chart in one call.

    Orchestrates :func:`zonal_stats` (or :func:`prepare_sankey_data`) and the
    appropriate chart function. The chart type is chosen automatically:

    * **ee.ImageCollection** -> **line chart** (default ``"line+markers"``).
    * **ee.Image** -> **bar chart** (default ``"bar"``).
    * **chart_type="donut"** -> **donut chart** (Image + thematic only).
    * **chart_type="scatter"** -> **scatter plot** (Image +
      FeatureCollection only; uses 2 continuous bands as x/y axes,
      optionally coloured by *thematic_band_name*).
    * **chart_type="sankey"** -> **Sankey transition diagram**.
    * **feature_label** + ``ee.FeatureCollection`` + ``ee.Image`` ->
      **grouped bar** or **per-feature donut** chart.
    * **feature_label** + ``ee.FeatureCollection`` + ``ee.ImageCollection``
      -> **per-feature time series subplots**.

    Args:
        ee_obj: ``ee.Image`` or ``ee.ImageCollection``.
        geometry: ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.
        band_names (list, optional): Bands to include.
        reducer (ee.Reducer, optional): Override the auto-selected reducer.
        scale (int, optional): Pixel scale in meters.
        crs (str, optional): CRS string.
        transform (list, optional): Affine transform.
        tile_scale (int, optional): Tile scale for parallelism.
        area_format (str, optional): Area unit for thematic data.
        x_axis_property (str, optional): Property for x-axis labels.
        date_format (str, optional): Date format string.
        title (str, optional): Chart title. Auto-generated if None.
        chart_type (str, optional): Chart type.  One of ``"bar"``,
            ``"stacked_bar"``, ``"donut"`` (Image + thematic only),
            ``"scatter"`` (Image + FeatureCollection only),
            ``"sankey"`` (ImageCollection + thematic, requires
            ``transition_periods``),
            ``"line"``, ``"stacked_line"``, ``"line+markers"``
            (default for ImageCollection), or
            ``"stacked_line+markers"``.  Defaults to ``"bar"`` for
            single ``ee.Image``, ``"line+markers"`` for
            ``ee.ImageCollection``.
        stacked (bool, optional): **Deprecated** — use ``chart_type``
            instead.  When ``True``, prepends ``"stacked_"`` to
            ``chart_type``.  Defaults to ``None``.
        sankey (bool, optional): Deprecated — use
            ``chart_type='sankey'`` instead.  Still accepted for
            backward compatibility.
        transition_periods (list, optional): Period list for Sankey.
        sankey_band_name (str, optional): Band for Sankey analysis.
        min_percentage (float, optional): Minimum percentage for Sankey flows.
        palette (list, optional): Hex color strings for each series/band.
            Overrides auto-detected class palette when provided.
        feature_label (str, optional): Property name to use as row labels when
            the geometry is a multi-feature ``ee.FeatureCollection``. Triggers
            the ``reduceRegions`` path. For ``ee.Image`` input produces a
            grouped bar chart; for ``ee.ImageCollection`` input produces
            per-feature time series subplots.
        width (int, optional): Chart width in pixels (per cell for
            multi-feature subplots).
        height (int, optional): Chart height in pixels (per cell for
            multi-feature subplots).
        opacity (float, optional): Opacity for Sankey nodes and links (0-1).
            Defaults to 0.9.
        legend_position (dict or str, optional): Plotly legend layout dict for
            non-Sankey charts (e.g. ``{"orientation": "h", "x": 0.5, "y": -0.1}``),
            or ``"right"``/``None`` for the Plotly default.
        columns (int, optional): Number of subplot columns for multi-feature
            time series.  Total width/height scale to
            ``n_cols * width`` / ``n_rows * height``.  Defaults to 2.
        include_masked_area (bool, optional): When ``True`` (default) and
            using the histogram reducer, unmasked pixels with value 0 are
            included so percentages are relative to the total area, not
            just the unmasked portion.  The sentinel class is removed
            from results.
        thematic_band_name (str, optional): For ``chart_type="scatter"``
            only.  Name of a thematic band in the image whose mode value
            per feature is used to colour each scatter point.  The image
            must carry ``{band}_class_values``, ``{band}_class_names``,
            and ``{band}_class_palette`` properties for the colours and
            legend entries.  Defaults to ``None`` (single-colour points).
        line_width (int or float, optional): Line width in pixels for
            time series traces. Defaults to ``2``.
        marker_size (int or float, optional): Marker diameter in pixels
            for time series traces. Defaults to ``5``.
        class_visible (dict, optional): Per-class visibility control.
            Maps class names to booleans. Classes set to ``False`` are
            toggled off in the chart legend (set to ``"legendonly"``).
            The traces remain in the figure — users can click the legend
            to re-enable them. Useful for hiding background, no-data, or
            stable classes by default.  Works for all chart paths
            including single-geometry, multi-feature time series
            subplots, and multi-feature bar/donut charts.  Example::

                class_visible={
                    "Non-Processing Area Mask": False,
                    "Stable": False,
                    "Background": False,
                }

            When ``None`` (default), all classes are visible.
        max_x_tick_labels (int, optional): Maximum number of x-axis tick
            labels. When the data has more x values than this, tick
            labels are thinned to every 2nd, 5th, 10th, etc. value.
            Defaults to ``10``.  Set to ``None`` or ``0`` to show all.
        max_y_tick_labels (int, optional): Maximum number of y-axis tick
            labels. Passed as Plotly's ``nticks``. Defaults to ``None``
            (Plotly automatic).

    Returns:
        tuple: Depends on chart type:

        * **Standard (single geometry):** ``(DataFrame, Figure)``
        * **Sankey:** ``(sankey_df, sankey_html, matrix_dict)`` where
          ``sankey_html`` is a D3 HTML string (display with
          ``display(HTML(cl.sankey_iframe(sankey_html)))``),
          and ``matrix_dict`` is ``{period_label: DataFrame}``
        * **Multi-feature + ee.Image (bar/donut):** ``(DataFrame, Figure)``
        * **Multi-feature + ee.ImageCollection:** ``(dict, Figure)`` where
          ``dict`` is ``{feature_name: DataFrame}``
        * **Scatter:** ``(DataFrame, Figure)`` where the DataFrame has
          columns for the two bands (and optionally the thematic band)

    Examples:
        Stacked time series of thematic land cover (auto-detects class
        properties from the image collection):

        >>> import geeViz.geeView as gv
        >>> from geeViz.outputLib import charts as cl
        >>> ee = gv.ee
        >>> study_area = ee.Geometry.Polygon(
        ...     [[[-106, 39.5], [-105, 39.5], [-105, 40.5], [-106, 40.5]]]
        ... )
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")
        >>> df, fig = cl.summarize_and_chart(
        ...     lcms.select(['Land_Cover']),
        ...     study_area,
        ...     title='LCMS Land Cover',
        ...     stacked=True,
        ... )
        >>> print(df.to_markdown())
        >>> fig.write_html("lcms_land_cover.html", include_plotlyjs="cdn")

        Sankey transition diagram with D3 gradient-colored links:

        >>> df, sankey_html, matrix = cl.summarize_and_chart(
        ...     lcms.select(['Land_Use']),
        ...     study_area,
        ...     chart_type='sankey',
        ...     transition_periods=[1990, 2000, 2024],
        ...     sankey_band_name='Land_Use',
        ...     min_percentage=0.5,
        ... )
        >>> # In notebooks: display(HTML(cl.sankey_iframe(sankey_html)))
        >>> # Save to file:
        >>> cl.save_chart_html(sankey_html, "land_use_transitions.html")

        Bar chart for a single image at a point (use ``ee.Reducer.first()``):

        >>> nlcd = ee.Image("USGS/NLCD_RELEASES/2021_REL/NLCD/2021")
        >>> point = ee.Geometry.Point([-104.99, 39.74])
        >>> df, fig = cl.summarize_and_chart(
        ...     nlcd,
        ...     point,
        ...     reducer=ee.Reducer.first(),
        ...     scale=30,
        ...     title='NLCD Land Cover',
        ... )

        Continuous time series (non-thematic bands auto-select
        ``ee.Reducer.mean()``):

        >>> import geeViz.getImagesLib as gil
        >>> composites = gil.getLandsatWrapper(
        ...     study_area, 2000, 2024
        ... )['composites']
        >>> df, fig = cl.summarize_and_chart(
        ...     composites,
        ...     study_area,
        ...     band_names=['nir', 'swir1', 'swir2'],
        ...     title='Spectral Band Means',
        ...     palette=['D0D', '0DD', 'DD0'],
        ... )

        Grouped bar chart comparing multiple features (uses reduceRegions
        internally):

        >>> fires = ee.FeatureCollection(
        ...     "USFS/GTAC/MTBS/burned_area_boundaries/v1"
        ... )
        >>> top5 = fires.sort("BurnBndAc", False).limit(5)
        >>> lc_mode = lcms.select(["Land_Cover"]).mode().set(
        ...     lcms.first().toDictionary()
        ... )
        >>> df, fig = cl.summarize_and_chart(
        ...     lc_mode,
        ...     top5,
        ...     feature_label="Incid_Name",
        ...     title="Land Cover — 5 Largest MTBS Fires",
        ...     stacked=True,
        ...     width=800,
        ... )

        Thematic data without class properties — force frequencyHistogram
        or set properties on-the-fly:

        >>> lcpri = ee.ImageCollection(
        ...     "projects/sat-io/open-datasets/LCMAP/LCPRI"
        ... ).select(['b1'], ['LC'])
        >>> # Force thematic (class values used as labels):
        >>> df, fig = cl.summarize_and_chart(
        ...     lcpri,
        ...     study_area,
        ...     reducer=ee.Reducer.frequencyHistogram(),
        ...     title='LCMAP LC Primary',
        ... )
        >>> # Or set properties for proper names and colors:
        >>> lcpri_named = lcpri.map(lambda img: img.set({
        ...     'LC_class_values': list(range(1, 10)),
        ...     'LC_class_names': ['Developed', 'Cropland', 'Grass/Shrub',
        ...         'Tree Cover', 'Water', 'Wetlands', 'Ice/Snow',
        ...         'Barren', 'Class Change'],
        ...     'LC_class_palette': ['E60000', 'A87000', 'E3E3C2', '1D6330',
        ...         '476BA1', 'BAD9EB', 'FFFFFF', 'B3B0A3', 'A201FF'],
        ... }))
        >>> df, fig = cl.summarize_and_chart(
        ...     lcpri_named, study_area, stacked=True,
        ... )

        Switch area format to hectares or acres:

        >>> df_ha, fig_ha = cl.summarize_and_chart(
        ...     lcms.select(['Land_Cover']),
        ...     study_area,
        ...     area_format='Hectares',
        ...     title='LCMS Land Cover (Hectares)',
        ... )
    """
    # filterBounds only applies to ImageCollections, not single Images
    if isinstance(ee_obj, ee.ImageCollection):
        ee_obj = ee_obj.filterBounds(geometry)
    obj_info = get_obj_info(ee_obj, band_names)
    class_info = obj_info["class_info"]
    if obj_info["is_thematic"]:
        y_label = AREA_FORMAT_DICT.get(area_format, {}).get("label", area_format)
    else:
        # Auto-derive y_label from reducer for continuous data
        _reducer_labels = {
            "mean": "Mean", "median": "Median", "mode": "Mode",
            "sum": "Sum", "min": "Min", "max": "Max",
            "first": "Value", "stddev": "Std Dev",
            "count": "Count", "variance": "Variance",
        }
        y_label = None
        if reducer is not None:
            try:
                r_str = str(reducer.serialize()).lower()
                for key, label in _reducer_labels.items():
                    if key in r_str:
                        y_label = label
                        break
            except Exception:
                pass
        if y_label is None:
            # Default reducer is mean for continuous data
            y_label = "Mean"

    # --- Resolve chart_type ---
    # Backward compat: if old `stacked=True` was passed, merge into chart_type
    if stacked is not None and stacked and chart_type is None:
        chart_type = "stacked_line+markers"
    elif stacked is not None and stacked and chart_type is not None:
        # stacked=True + explicit chart_type → prepend stacked_ if not already
        ct = str(chart_type)
        if not ct.startswith("stacked_"):
            chart_type = f"stacked_{ct}"

    # Default chart_type based on object type
    if chart_type is None:
        if obj_info["obj_type"] == "ImageCollection":
            chart_type = "line+markers"
        else:
            chart_type = "bar"

    # Donut validation — Image-only and thematic-only
    if str(chart_type).lower().strip() == "donut":
        if obj_info["obj_type"] == "ImageCollection":
            raise ValueError(
                "chart_type='donut' is only supported for ee.Image inputs, "
                "not ee.ImageCollection. Use chart_type='bar', 'stacked_bar', 'line', 'line+markers', 'stacked_line' or 'stacked_line+markers' for "
                "ImageCollections."
            )
        if not obj_info.get("is_thematic") and not class_info:
            raise ValueError(
                "chart_type='donut' is only supported for thematic "
                "(categorical) data with class names and palette properties. "
                "Use chart_type='bar', 'stacked_bar', 'line', 'line+markers', 'stacked_line' or 'stacked_line+markers' for continuous data."
            )

    # Scatter validation — Image + FeatureCollection only
    if str(chart_type).lower().strip() == "scatter":
        if obj_info["obj_type"] == "ImageCollection":
            raise ValueError(
                "chart_type='scatter' is only supported for ee.Image inputs, "
                "not ee.ImageCollection."
            )
        geo_type_check, _ = detect_geometry_type(geometry)
        if geo_type_check != "multi":
            raise ValueError(
                "chart_type='scatter' requires a multi-feature "
                "ee.FeatureCollection as the geometry input (one point per "
                "feature). Pass a FeatureCollection with multiple features."
            )

    # Sankey path — chart_type='sankey' (preferred) or legacy sankey=True
    if str(chart_type).lower().strip() == "sankey":
        sankey = True
    if sankey and obj_info["obj_type"] == "ImageCollection" and class_info:
        bn = sankey_band_name or obj_info["band_names"][0]
        if transition_periods is None:
            raise ValueError("transition_periods is required for Sankey charts")

        if title is None:
            title = f"{bn} Class Transitions"

        sankey_df, matrix_dict = prepare_sankey_data(
            ee_obj,
            bn,
            transition_periods,
            class_info,
            geometry,
            scale=scale,
            crs=crs,
            transform=transform,
            tile_scale=tile_scale,
            area_format=area_format,
            min_percentage=min_percentage,
        )

        info = class_info.get(bn, {})
        sankey_html = chart_sankey_d3(
            sankey_df,
            class_names=info.get("class_names", []),
            class_palette=info.get("class_palette", []),
            transition_periods=transition_periods,
            title=title,
            width=width,
            height=height,
            opacity=opacity,
        )
        return (sankey_df, sankey_html, matrix_dict)

    # Multi-feature path: reduceRegions
    geo_type, _ = detect_geometry_type(geometry)

    # --- Scatter path: Image + FeatureCollection + 2 bands ---
    # Handled before feature_label gate since scatter works without labels.
    if geo_type == "multi" and str(chart_type).lower().strip() == "scatter":
        # Resolve the two bands to plot
        all_bands = obj_info["band_names"]
        if band_names and len(band_names) >= 2:
            x_band, y_band = band_names[0], band_names[1]
        elif len(all_bands) >= 2:
            x_band, y_band = all_bands[0], all_bands[1]
        else:
            raise ValueError(
                "chart_type='scatter' requires at least 2 bands. "
                f"Image only has: {all_bands}"
            )

        # Use mean reducer for scatter (continuous per-feature values)
        _scatter_reducer = reducer if reducer is not None else ee.Reducer.first()

        fc = ee.FeatureCollection(geometry)

        # Reduce continuous bands
        continuous_img = ee.Image(ee_obj).select([x_band, y_band])
        reduced = continuous_img.reduceRegions(
            collection=fc,
            reducer=_scatter_reducer,
            scale=scale,
            crs=crs,
            crsTransform=transform,
            tileScale=tile_scale,
        )

        # If thematic band requested, reduce it separately with mode()
        # and join the result onto the continuous FC
        if thematic_band_name:
            thematic_img = ee.Image(ee_obj).select([thematic_band_name])
            reduced_thematic = thematic_img.reduceRegions(
                collection=fc,
                reducer=ee.Reducer.mode(),
                scale=scale,
                crs=crs,
                crsTransform=transform,
                tileScale=tile_scale,
            )
            # Add the mode column to each feature via zip
            reduced_list = reduced.toList(reduced.size())
            thematic_list = reduced_thematic.toList(reduced_thematic.size())
            def _merge(i):
                i = ee.Number(i).int()
                f = ee.Feature(reduced_list.get(i))
                t = ee.Feature(thematic_list.get(i))
                return f.set(thematic_band_name, t.get("mode"))
            reduced = ee.FeatureCollection(
                ee.List.sequence(0, reduced.size().subtract(1)).map(_merge)
            )

        # Convert to DataFrame
        import geeViz.gee2Pandas as g2p
        scatter_df = g2p.robust_featureCollection_to_df(reduced)

        # Set index to feature label if available
        if feature_label and feature_label in scatter_df.columns:
            scatter_df = scatter_df.set_index(feature_label)

        # Ensure the two band columns exist
        if x_band not in scatter_df.columns or y_band not in scatter_df.columns:
            raise ValueError(
                f"Reduced DataFrame missing expected band columns. "
                f"Expected '{x_band}' and '{y_band}', got: {list(scatter_df.columns)}"
            )

        if title is None:
            title = f"{y_band} vs {x_band}"

        # Resolve thematic class info for coloring
        _thematic_col = None
        _class_names = None
        _class_palette = None
        _class_values = None
        if thematic_band_name:
            if thematic_band_name in scatter_df.columns:
                _thematic_col = thematic_band_name

            # Get class metadata from the image
            if _thematic_col and class_info and thematic_band_name in class_info:
                ci = class_info[thematic_band_name]
                _class_names = ci.get("class_names", [])
                _class_palette = ci.get("class_palette", [])
                _class_values = ci.get("class_values", [])
            elif _thematic_col:
                # Try reading from image properties directly
                try:
                    props = ee.Image(ee_obj).getInfo().get("properties", {})
                    _class_values = props.get(f"{thematic_band_name}_class_values")
                    _class_names = props.get(f"{thematic_band_name}_class_names")
                    _class_palette = props.get(f"{thematic_band_name}_class_palette")
                except Exception:
                    pass

        # Build output columns
        out_cols = [x_band, y_band]
        if _thematic_col and _thematic_col in scatter_df.columns:
            out_cols.append(_thematic_col)

        fig = chart_scatter(
            scatter_df,
            x_band=x_band,
            y_band=y_band,
            feature_label=feature_label,
            title=title,
            width=width,
            height=height,
            legend_position=legend_position,
            opacity=opacity,
            thematic_col=_thematic_col,
            class_names=_class_names,
            class_palette=_class_palette,
            class_values=_class_values,
        )
        return (scatter_df[[c for c in out_cols if c in scatter_df.columns]], _set_download_filename(fig))

    # Auto-detect feature_label for multi-feature FeatureCollections
    if geo_type == "multi" and not feature_label:
        feature_label = _detect_feature_label(geometry)

    if geo_type == "multi" and feature_label:

        df = zonal_stats(
            ee_obj,
            geometry,
            band_names=band_names,
            reducer=reducer,
            scale=scale,
            crs=crs,
            transform=transform,
            tile_scale=tile_scale,
            area_format=area_format,
            x_axis_property=x_axis_property,
            date_format=date_format,
            include_masked_area=include_masked_area,
        )

        # Build color list from class_info (shared by both sub-paths)
        colors = palette
        if colors is None and class_info:
            color_lookup = {}
            for bn in obj_info["band_names"]:
                info = class_info.get(bn, {})
                cn = info.get("class_names", [])
                cp = info.get("class_palette", [])
                for i, name in enumerate(cn):
                    if i < len(cp):
                        color_lookup[name] = cp[i]
            if color_lookup:
                # Will be applied per-column below
                pass
            else:
                color_lookup = {}
        else:
            color_lookup = {}

        # --- ImageCollection + multi-feature: per-feature time series ---
        if obj_info["obj_type"] == "ImageCollection":
            # Recover x_axis_labels from prepare_for_reduction
            # (zonal_stats already called it internally; we re-derive from column names)
            x_axis_labels = []
            seen = set()
            for col in df.columns:
                if SPLIT_STR in col:
                    prefix = col.split(SPLIT_STR)[0]
                    if prefix not in seen:
                        seen.add(prefix)
                        x_axis_labels.append(prefix)

            per_feature_dfs = _pivot_multi_feature_timeseries(
                df, x_axis_labels, obj_info, feature_label, SPLIT_STR
            )

            # Build color list matching column order of per-feature DataFrames
            if per_feature_dfs:
                sample_cols = list(next(iter(per_feature_dfs.values())).columns)
                if colors is None and color_lookup:
                    colors = [_ensure_hex_color(color_lookup.get(c)) if color_lookup.get(c) else None for c in sample_cols]
                elif colors is None:
                    colors = None

            if title is None:
                title = "Time Series by Feature"

            # Pass per-cell width/height — chart_multi_feature_timeseries
            # scales to n_cols * width, n_rows * height internally
            fig = chart_multi_feature_timeseries(
                per_feature_dfs,
                colors=colors,
                chart_type=chart_type,
                title=title,
                x_label=(
                    "Date"
                    if x_axis_property == "system:time_start"
                    else (x_axis_property.replace("_", " ").title() if x_axis_property != "year" else "Year")
                ),
                y_label=y_label,
                width=width,
                height=height,
                columns=columns,
                legend_position=legend_position,
                line_width=line_width,
                marker_size=marker_size,
                max_x_tick_labels=max_x_tick_labels,
                max_y_tick_labels=max_y_tick_labels,
            )
            # Apply class_visible to multi-feature time series subplots
            if class_visible is not None and isinstance(class_visible, dict):
                hidden = {name for name, vis in class_visible.items() if not vis}
                if hidden:
                    for trace in fig.data:
                        trace_name = trace.name or ""
                        if (trace_name in hidden
                                or any(trace_name.endswith(SPLIT_STR + h) for h in hidden)
                                or any(trace_name.replace(SPLIT_STR, " ").strip() in hidden for _ in [0])):
                            trace.visible = "legendonly"

            return (per_feature_dfs, _set_download_filename(fig))

        # --- ee.Image + multi-feature: grouped bar chart (existing behavior) ---
        # Set index to feature label column
        if feature_label in df.columns:
            df = df.set_index(feature_label)

        # Identify class columns from class_info
        class_cols = []
        if class_info:
            for bn in obj_info["band_names"]:
                info = class_info.get(bn, {})
                for name in info.get("class_names", []):
                    col_name = f"{bn}{SPLIT_STR}{name}" if len(obj_info["band_names"]) > 1 else name
                    if col_name in df.columns:
                        class_cols.append(col_name)

        # Fallback: prefer columns matching image band names (avoids picking
        # up feature properties like ALAND, AWATER from reduceRegions output)
        if not class_cols:
            band_col_set = set(obj_info["band_names"])
            class_cols = [c for c in df.columns if c in band_col_set]

        # Last resort: keep all numeric columns that aren't geometry/system properties
        if not class_cols:
            class_cols = [
                c for c in df.columns
                if pandas.api.types.is_numeric_dtype(df[c])
                and not c.startswith("geometry")
                and c not in ("system:index",)
            ]

        chart_df = df[class_cols].fillna(0)

        # Build colors for grouped bar
        if colors is None and class_info:
            bar_color_lookup = {}
            for bn in obj_info["band_names"]:
                info = class_info.get(bn, {})
                cn = info.get("class_names", [])
                cp = info.get("class_palette", [])
                for i, name in enumerate(cn):
                    col_name = f"{bn}{SPLIT_STR}{name}" if len(obj_info["band_names"]) > 1 else name
                    if i < len(cp):
                        bar_color_lookup[col_name] = cp[i]
            if bar_color_lookup:
                colors = [bar_color_lookup.get(col) for col in chart_df.columns]

        if title is None:
            title = "Zonal Summary by Feature"

        if str(chart_type).lower().strip() == "donut":
            fig = chart_donut_multi_feature(
                chart_df,
                colors=colors,
                title=title,
                width=width,
                height=height,
                columns=columns,
                legend_position=legend_position,
            )
        else:
            fig = chart_grouped_bar(
                chart_df,
                colors=colors,
                title=title,
                y_label=y_label,
                chart_type=chart_type,
                width=width,
                height=height,
                legend_position=legend_position,
            )
        # Apply '%' ticksuffix and max_y_tick_labels for multi-feature bar/donut
        y_kw = {}
        if y_label and "%" in y_label:
            y_kw["ticksuffix"] = "%"
        if max_y_tick_labels is not None and max_y_tick_labels > 0:
            y_kw["nticks"] = max_y_tick_labels
        if y_kw:
            fig.update_yaxes(**y_kw)

        # Apply class_visible to multi-feature bar/donut charts
        if class_visible is not None and isinstance(class_visible, dict):
            hidden = {name for name, vis in class_visible.items() if not vis}
            if hidden:
                for trace in fig.data:
                    trace_name = trace.name or ""
                    if (trace_name in hidden
                            or any(trace_name.endswith(SPLIT_STR + h) for h in hidden)
                            or any(trace_name.replace(SPLIT_STR, " ").strip() in hidden for _ in [0])):
                        trace.visible = "legendonly"

        return (chart_df, _set_download_filename(fig))

    # Standard single-region zonal stats path
    # Safety fallback: dissolve multi-feature FCs without a label (shouldn't
    # happen after auto-detection above, but guards against edge cases).
    if geo_type == "multi" and not feature_label:
        geometry = geometry.geometry()

    df = zonal_stats(
        ee_obj,
        geometry,
        band_names=band_names,
        reducer=reducer,
        scale=scale,
        crs=crs,
        transform=transform,
        tile_scale=tile_scale,
        area_format=area_format,
        x_axis_property=x_axis_property,
        date_format=date_format,
        include_masked_area=include_masked_area,
    )

    df_full = df

    # Extract colors from class info (unless caller provided palette).
    # Build the color list to match actual DataFrame column order so that
    # multi-band thematic charts (e.g. Change + Land_Cover + Land_Use)
    # assign the correct color to each class.
    colors = palette
    if colors is None and class_info:
        # Build a lookup: column_name -> hex color
        color_lookup = {}
        for bn in obj_info["band_names"]:
            info = class_info.get(bn, {})
            class_names = info.get("class_names", [])
            class_palette = info.get("class_palette", [])
            for i, name in enumerate(class_names):
                col_name = f"{bn}{SPLIT_STR}{name}" if len(obj_info["band_names"]) > 1 else name
                if i < len(class_palette):
                    color_lookup[col_name] = class_palette[i]
        # Map each DataFrame column to its color (fall back to None)
        if color_lookup:
            colors = [color_lookup.get(col) for col in df.columns]

    # Pick chart type
    if obj_info["obj_type"] == "ImageCollection":
        if title is None:
            title = "Zonal Summary"
        fig = chart_time_series(
            df,
            colors=colors,
            chart_type=chart_type,
            title=title,
            x_label=(
                "Date"
                if x_axis_property == "system:time_start"
                else (x_axis_property.replace("_", " ").title() if x_axis_property != "year" else "Year")
            ),
            y_label=y_label,
            width=width,
            height=height,
            legend_position=legend_position,
            line_width=line_width,
            marker_size=marker_size,
            max_x_tick_labels=max_x_tick_labels,
            max_y_tick_labels=max_y_tick_labels,
        )
    else:
        if title is None:
            title = "Class Distribution"
        if str(chart_type).lower().strip() == "donut":
            fig = chart_donut(
                df,
                colors=colors,
                title=title,
                width=width,
                height=height,
                legend_position=legend_position,
            )
        else:
            fig = chart_bar(
                df,
                colors=colors,
                title=title,
                y_label=y_label,
                chart_type=chart_type,
                width=width,
                height=height,
                legend_position=legend_position,
            )

    # For thematic data with first() reducer, map numeric class values
    # to class names on the y-axis.  Other reducers (histogram, mean, etc.)
    # produce area/count values that need standard numeric y-axis ticks.
    _is_first_reducer = (
        reducer is not None
        and hasattr(reducer, "getInfo")
        and "first" in str(reducer.serialize()).lower()
    )
    if _is_first_reducer and obj_info["is_thematic"] and class_info:
        for bn in obj_info["band_names"]:
            info = class_info.get(bn, {})
            vals = info.get("class_values", [])
            names = info.get("class_names", [])
            if vals and names and len(vals) == len(names):
                fig.update_yaxes(
                    tickvals=vals,
                    ticktext=names,
                )
                break

    # Apply '%' ticksuffix and max_y_tick_labels for bar/donut charts
    # (time series charts handle this internally)
    if obj_info["obj_type"] != "ImageCollection":
        y_kw = {}
        if y_label and "%" in y_label:
            y_kw["ticksuffix"] = "%"
        if max_y_tick_labels is not None and max_y_tick_labels > 0:
            y_kw["nticks"] = max_y_tick_labels
        if y_kw:
            fig.update_yaxes(**y_kw)

    # Apply class_visible: toggle trace visibility in the figure.
    # Traces remain in the chart (user can click legend to re-enable).
    if class_visible is not None and isinstance(class_visible, dict):
        hidden = {name for name, vis in class_visible.items() if not vis}
        if hidden:
            for trace in fig.data:
                trace_name = trace.name or ""
                # Check if trace name matches a hidden class (with or without band prefix)
                if (trace_name in hidden
                        or any(trace_name.endswith(SPLIT_STR + h) for h in hidden)
                        or any(trace_name.replace(SPLIT_STR, " ").strip() in hidden for _ in [0])):
                    trace.visible = "legendonly"

    return (df_full, _set_download_filename(fig))
