"""
Generate reports from Earth Engine data with LLM-powered narratives.

``geeViz.outputLib.reports`` provides a :class:`Report` class that combines
``chartingLib.summarize_and_chart()`` results, ``thumbLib`` thumbnails,
and Gemini-generated narratives into styled HTML or Markdown reports.

All Earth Engine data requests (charts, tables, thumbnails, GIFs) **and**
LLM narratives for every section are executed in parallel using
``concurrent.futures``.  Only the executive summary waits for all sections
to finish before it is generated.

Layouts
-------
* ``"report"`` (default) — traditional multi-page portrait layout,
  sections flow vertically.
* ``"poster"`` — landscape multi-column layout, designed for large-format
  printing or screen display.  Sections tile into a responsive grid.

Themes
------
Two built-in themes match the geeView color palette:

* ``"dark"`` (default) — deep brown/black background with warm gray text
* ``"light"`` — white background with deep brown text

Example::

    import geeViz.geeView as gv
    from geeViz.outputLib import reports as rl

    ee = gv.ee
    report = rl.Report(
        title="Wasatch Front Assessment",
        theme="dark",
        layout="poster",       # landscape multi-column
    )
    report.header_text = "An analysis of land cover and fire trends."

    report.add_section(
        ee_obj=lcms.select(['Land_Cover']),
        geometry=counties,
        title="LCMS Land Cover",
        stacked=True,
        scale=60,
    )

    # PDF with static chart images
    report.generate(format="pdf", output_path="report.pdf")

    # HTML (interactive charts)
    report.generate(format="html", output_path="report.html")
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
import os
import textwrap
import threading
import traceback
from datetime import datetime

from geeViz.outputLib import charts as cl
from geeViz.outputLib import thumbs as tl
from geeViz.outputLib import themes as _themeLib
from geeViz.outputLib._templates import (
    render_report_css as _render_report_css,
    HTML_TEMPLATE as _HTML_TEMPLATE,
    PDF_HTML_TEMPLATE as _PDF_HTML_TEMPLATE,
)

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "gemini-3-flash-preview"

_SECTION_PROMPT_TEMPLATE = textwrap.dedent("""\
    You are a geospatial data analyst writing a section of a technical report.
    Write a concise 2-4 paragraph narrative interpreting the data below for
    a section titled "{title}".
    Focus on key trends, notable changes, and significant values.
    Do not repeat every number — highlight what matters.
    {tone}
    Use markdown formatting (bold, bullets) where it helps readability.
    {units_context}
    {image_context}
    {extra}

    Data:
    {table}
""")

_SUMMARY_PROMPT_TEMPLATE = textwrap.dedent("""\
    You are a geospatial data analyst writing the executive summary of a
    technical report titled "{title}".
    Below are brief summaries of each section. Write a concise 2-3 paragraph
    executive summary that ties the findings together and highlights the
    most important takeaways.
    {tone}
    Use markdown formatting.
    {extra}
    {image_note}

    Section summaries:
    {section_summaries}
""")

_TONES = {
    "neutral": (
        "Use a neutral, data-driven tone. State findings directly without "
        "superlatives, editorial commentary, or narrative flourishes. "
        "Let the data speak for itself."
    ),
    "informative": (
        "Use an informative, accessible tone. Briefly explain what the "
        "data shows and why it matters, but avoid superlatives or hype."
    ),
    "technical": (
        "Use a formal, technical tone appropriate for a scientific audience. "
        "Be precise with terminology and cite specific values."
    ),
}

# ---------------------------------------------------------------------------
#  Logo (lazy-loaded, base64 encoded)
# ---------------------------------------------------------------------------
_LOGO_CACHE = {}


def _get_logo_b64(variant="dark"):
    """Return a base64-encoded PNG data URI for the geeViz logo.

    Args:
        variant: ``"dark"`` or ``"light"``.
    """
    if variant in _LOGO_CACHE:
        return _LOGO_CACHE[variant]

    logo_dir = os.path.join(
        os.path.dirname(__file__), "..", "geeView", "src", "assets", "images"
    )
    logo_path = os.path.join(logo_dir, f"geeviz-logo-{variant}.png")
    if not os.path.exists(logo_path):
        _LOGO_CACHE[variant] = None
        return None

    with open(logo_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    uri = f"data:image/png;base64,{b64}"
    _LOGO_CACHE[variant] = uri
    return uri



# CSS is now generated dynamically by _render_report_css() from _templates.py


# ---------------------------------------------------------------------------
#  Internal section container
# ---------------------------------------------------------------------------
_THUMB_KEYS = frozenset({
    "thumb_format", "thumb_viz", "thumb_viz_params", "thumb_band_name",
    "thumb_dimensions", "thumb_fps", "thumb_columns", "thumb_max_frames",
    "thumb_burn_in_date", "thumb_date_format", "thumb_date_position",
    "thumb_bg_color", "thumb_geometry", "thumb_crs", "thumb_transform",
    "burn_in_legend", "legend_scale", "legend_position", "basemap",
    "burn_in_geometry", "geometry_outline_color", "geometry_fill_color",
    "geometry_outline_weight", "clip_to_geometry", "geometry_legend_label",
    "title_font_size", "label_font_size", "overlay_opacity",
    "inset_map", "inset_basemap", "inset_scale", "inset_on_map",
    "scalebar", "scalebar_units", "north_arrow", "north_arrow_style",
})
# Keys used by the report layer but not by summarize_and_chart
_REPORT_KEYS = frozenset({"chart_types"}) | _THUMB_KEYS


class _Section:
    """Holds config and results for one report section."""

    __slots__ = (
        "ee_obj", "geometry", "title", "prompt", "kwargs",
        "generate_table", "generate_chart", "thumb_format",
        "chart_types",
        "df", "fig", "sankey_fig", "extra_figs", "narrative",
        "thumb_html", "thumb_bytes", "thumb_filmstrip_html", "error",
    )

    def __init__(self, ee_obj, geometry, title, prompt, kwargs,
                 generate_table, generate_chart, thumb_format,
                 chart_types=None):
        self.ee_obj = ee_obj
        self.geometry = geometry
        self.title = title
        self.prompt = prompt
        self.kwargs = kwargs
        self.generate_table = generate_table
        self.generate_chart = generate_chart
        self.thumb_format = thumb_format
        self.chart_types = chart_types or []  # list of chart type strings
        # Populated during generate()
        self.df = None
        self.fig = None        # primary figure (first chart type)
        self.sankey_fig = None  # sankey figure if "sankey" in chart_types
        self.extra_figs = []    # additional figures beyond the first
        self.narrative = None
        self.thumb_html = None
        self.thumb_bytes = None
        self.thumb_filmstrip_html = None
        self.error = None


# ---------------------------------------------------------------------------
#  Report class
# ---------------------------------------------------------------------------
class Report:
    """Build and generate reports from Earth Engine data.

    Args:
        title (str): Report title.
        model (str): Gemini model name. Default ``"gemini-3-flash-preview"``.
        api_key (str, optional): Google API key. If not provided, loaded from
            the ``GEMINI_API_KEY`` environment variable (via ``.env``).
        prompt (str, optional): Additional guidance for the executive summary.
        header_text (str, optional): Introductory text shown below the title.
        header_icon (str, optional): Path to a PNG/JPG image for the report
            header icon. If None, uses the built-in geeViz logo (theme-aware).
            Pass ``False`` to suppress the icon entirely.
        theme (str): Color theme — ``"dark"`` or ``"light"``. Default ``"dark"``.
        layout (str): Layout mode — ``"report"`` (portrait, vertical flow) or
            ``"poster"`` (landscape, multi-column grid). Default ``"report"``.
        tone (str): Narrative tone for LLM-generated text. Built-in options:
            ``"neutral"`` (default) — data-driven, no superlatives or narrative;
            ``"informative"`` — accessible, explains significance;
            ``"technical"`` — formal, precise terminology.
            Can also be a custom string with tone instructions.
        max_workers (int): Thread pool size for parallel EE requests.
            Default 6.

    Example::

        report = Report(title="My Analysis", theme="light", layout="report")
        report.add_section(ee_obj=lcms, geometry=area, title="Land Cover")
        html = report.generate(format="html", output_path="report.html")
    """

    def __init__(self, title="Report", model=_DEFAULT_MODEL, api_key=None,
                 prompt=None, header_text=None, header_icon=None,
                 theme="dark", layout="report", tone="neutral", max_workers=6):
        self.title = title
        self.model = model
        self.prompt = prompt
        self.header_text = header_text or ""
        self.header_icon = header_icon
        self.theme = theme
        self.layout = layout
        self.tone = tone
        self.max_workers = max_workers
        self._sections = []
        self._summary = None
        self._api_key = api_key
        self._client = None
        self._computed_theme = None  # tracks theme used during thumbnail computation

    # -- Public API --------------------------------------------------------

    def add_section(self, ee_obj, geometry, title="Section", prompt=None,
                   generate_table=True, generate_chart=True,
                   thumb_format="png", chart_types=None, **kwargs):
        """Add a data section to the report.

        Args:
            ee_obj: ``ee.Image`` or ``ee.ImageCollection`` to summarize.
            geometry: ``ee.Geometry``, ``ee.Feature``, or ``ee.FeatureCollection``.
            title (str): Section heading.
            prompt (str, optional): Per-section LLM guidance for the narrative.
            generate_table (bool): Include data table. Default True.
            generate_chart (bool): Include chart. Default True.
            thumb_format (str or None): Thumbnail image format.  Default
                ``"png"`` (static thumbnail).  Options:

                * ``"png"`` — single composite thumbnail (works for both
                  ``ee.Image`` and ``ee.ImageCollection``).
                * ``"gif"`` — animated GIF with date labels
                  (``ee.ImageCollection`` only).
                * ``"filmstrip"`` — grid of individual time-step frames
                  (``ee.ImageCollection`` only).
                * ``None`` or ``False`` — no thumbnail.

            chart_types (list of str, optional): Chart types to produce
                for this section.  Each entry is a single chart type
                string passed to ``summarize_and_chart(chart_type=...)``.
                Valid values include ``"bar"``, ``"stacked_bar"``,
                ``"line+markers"``, ``"stacked_line+markers"``,
                ``"donut"``, ``"scatter"``, and ``"sankey"``.

                When ``"sankey"`` is in the list, the ``sankey``,
                ``transition_periods``, ``sankey_band_name``, and
                ``min_percentage`` kwargs are used for that chart.

                An empty list ``[]`` or ``None`` auto-detects a single
                chart type (existing behavior).  Maximum recommended
                length is 3.

                Examples::

                    chart_types=["sankey", "line+markers"]
                    chart_types=["bar", "donut"]
                    chart_types=["sankey"]  # sankey only, no line chart

            **kwargs: All other keyword arguments.  Thumbnail params
                (prefixed ``thumb_``) are extracted and forwarded to
                ``thumbLib``; remaining kwargs go to
                ``chartingLib.summarize_and_chart()``.

                Thumbnail params (all optional):
                    ``thumb_viz_params``, ``thumb_band_name``,
                    ``thumb_dimensions``, ``thumb_fps`` (gif only),
                    ``thumb_columns`` (filmstrip only),
                    ``thumb_max_frames`` (gif/filmstrip),
                    ``thumb_burn_in_date`` (gif), ``thumb_date_format``
                    (gif/filmstrip), ``thumb_date_position`` (gif),
                    ``thumb_bg_color``, ``thumb_geometry`` (override
                    clip region), ``thumb_crs``, ``thumb_transform``,
                    ``burn_in_legend``, ``legend_scale``.

                Chart params (examples):
                    ``stacked=True``, ``scale=60``,
                    ``feature_label="NAME"``, etc.

        Returns:
            Report: self (for method chaining).
        """
        # Normalize chart_types
        ct_list = list(chart_types) if chart_types else []

        self._sections.append(_Section(
            ee_obj, geometry, title, prompt, kwargs,
            generate_table, generate_chart, thumb_format,
            chart_types=ct_list,
        ))
        return self

    def metadata(self):
        """Return a summary DataFrame describing each section's generated outputs.

        Each row corresponds to one section. Columns include the section
        title, what was requested, what was produced, data dimensions,
        and any errors. Call this after :meth:`generate` to inspect results.

        Returns:
            pandas.DataFrame with one row per section.
        """
        import pandas as pd
        rows = []
        for i, sec in enumerate(self._sections):
            if sec.df is None:
                table_shape = None
            elif isinstance(sec.df, dict):
                table_shape = f"{len(sec.df)} matrices"
            else:
                table_shape = f"{sec.df.shape[0]}x{sec.df.shape[1]}"
            rows.append({
                "Section": i + 1,
                "Title": sec.title,
                "Table": table_shape,
                "Chart": sum(1 for f in [sec.fig, sec.sankey_fig] + (sec.extra_figs or []) if f is not None),
                "Thumb": f"{sec.thumb_format}: {len(sec.thumb_html):,}b" if sec.thumb_html else sec.thumb_format,
                "Narrative": f"{len(sec.narrative):,}c" if sec.narrative else None,
                "Error": sec.error,
            })
        df = pd.DataFrame(rows)
        # Add a summary row for the executive summary
        summary_row = {
            "Section": "",
            "Title": "Executive Summary",
            "Table": None,
            "Chart": False,
            "Thumbnail": None,
            "GIF": None,
            "Narrative": f"{len(self._summary):,}c" if self._summary else None,
            "Error": None,
        }
        df = pd.concat([df, pd.DataFrame([summary_row])], ignore_index=True)
        return df

    def generate(self, format="html", output_path=None):
        """Generate the report.

        All section data (charts, tables, thumbnails, GIFs) and LLM
        narratives are computed in parallel.  Only the executive summary
        waits for all sections to finish first.

        Args:
            format (str): Output format — ``"html"``, ``"md"``, or ``"pdf"``.
                PDF uses ``kaleido`` to render charts as static PNG images
                and ``pdfkit``/``wkhtmltopdf`` for the final conversion.
                If wkhtmltopdf is not installed, a print-ready HTML file
                with ``@page`` CSS directives is generated instead (open
                in a browser and Print → Save as PDF).
            output_path (str, optional): File path to write. If None, returns
                the content as a string (except for PDF which always requires
                a path).

        Returns:
            str: The report content (or the file path if ``output_path`` given).
        """
        # Only compute data once; subsequent generate() calls just re-render
        already_computed = any(
            sec.df is not None or sec.thumb_html
            for sec in self._sections
        )
        if not already_computed:
            print(f"Generating report: {self.title}")
            self._compute_all_parallel()
            self._generate_executive_summary()
        else:
            print(f"Re-rendering report: {self.title}")

        if format == "md":
            content = self._render_md()
        elif format == "pdf":
            return self._render_pdf(output_path)
        else:
            content = self._render_html()

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Report saved to: {output_path}")
            return output_path

        return content

    # -- Private: fully parallel computation -------------------------------

    def _compute_all_parallel(self):
        """Run ALL work — EE data + LLM narratives — in a single thread pool.

        Flow:
        1. Submit chart/table and thumbnail tasks for every section (all run
           in parallel).
        2. Each data task has a done-callback.  When the *last* data task for
           a section finishes, its LLM narrative is submitted immediately —
           no threads are wasted blocking/waiting.
        3. All section narratives run in parallel as soon as their data is
           ready.
        4. The executive summary is generated *after* this method returns
           (it needs all narratives + images).
        """
        # Set theme-aware defaults for thumbnail background color
        _t = _themeLib.get_theme(self.theme)
        default_bg = _t.bg_hex
        for sec in self._sections:
            sec.kwargs.setdefault("thumb_bg_color", default_bg)

        n = len(self._sections)
        lock = threading.Lock()
        section_pending = {}          # idx -> remaining data task count
        narratives_remaining = [n]    # mutable counter
        all_done = threading.Event()  # set when every narrative finishes

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:

            # -- callbacks -------------------------------------------------
            def _on_narrative_done(future):
                """Called when a narrative future completes."""
                try:
                    future.result()
                except Exception as e:
                    print(f"  Unexpected narrative error: {e}")
                    traceback.print_exc()
                with lock:
                    narratives_remaining[0] -= 1
                    if narratives_remaining[0] == 0:
                        all_done.set()

            def _on_section_ready(idx):
                """Submit the narrative now that all data for *idx* is done."""
                sec = self._sections[idx]
                nf = pool.submit(self._compute_narrative, idx, sec)
                nf.add_done_callback(_on_narrative_done)

            def _data_callback(idx, future):
                """Attached to every data future via add_done_callback."""
                with lock:
                    section_pending[idx] -= 1
                    if section_pending[idx] == 0:
                        _on_section_ready(idx)

            # -- submit data tasks ----------------------------------------
            for i, sec in enumerate(self._sections):
                futs = []
                if sec.generate_chart or sec.generate_table:
                    futs.append(pool.submit(self._compute_chart_table, i, sec))
                if sec.thumb_format:
                    futs.append(pool.submit(self._compute_thumb, i, sec))

                with lock:
                    section_pending[i] = len(futs)

                if not futs:
                    # Nothing to compute — fire narrative immediately
                    _on_section_ready(i)
                else:
                    for f in futs:
                        f.add_done_callback(
                            lambda future, idx=i: _data_callback(idx, future)
                        )

            # Block until every narrative has finished
            all_done.wait()

        self._computed_theme = self.theme

    def _compute_chart_table(self, idx, sec):
        """Compute chart(s) and table for a single section (thread-safe).

        When ``sec.chart_types`` is a non-empty list, each chart type is
        produced via a separate ``summarize_and_chart`` call.  The first
        figure goes to ``sec.fig``, sankey figures go to ``sec.sankey_fig``,
        and any extras go to ``sec.extra_figs``.

        When ``sec.chart_types`` is empty, falls back to the auto-detect
        behavior (single ``summarize_and_chart`` call).
        """
        print(f"  [{idx+1}/{len(self._sections)}] Computing chart/table: {sec.title}")
        try:
            chart_kwargs = {k: v for k, v in sec.kwargs.items()
                           if k not in _REPORT_KEYS}
            # Use section title as chart title if not explicitly set
            chart_kwargs.setdefault("title", sec.title)

            # Determine which chart types to produce
            ct_list = sec.chart_types if sec.chart_types else []

            if ct_list:
                # --- Explicit chart_types list ---
                all_figs = []  # list of (chart_type, fig)
                for ct in ct_list:
                    ct_lower = ct.lower().strip()
                    print(f"  [{idx+1}/{len(self._sections)}] Computing {ct} chart: {sec.title}")
                    try:
                        if ct_lower == "sankey":
                            # Sankey path — use chart_type='sankey'
                            sankey_kwargs = dict(chart_kwargs)
                            sankey_kwargs.pop("sankey", None)
                            sankey_kwargs["chart_type"] = "sankey"
                            result = cl.summarize_and_chart(
                                sec.ee_obj, sec.geometry, **sankey_kwargs
                            )
                            if isinstance(result, dict) and "matrix" in result:
                                sankey_df, fig, matrix_dict = result["df"], result["chart"], result["matrix"]
                                # Store sankey data (matrix_dict) as df if no df yet
                                if sec.df is None:
                                    sec.df = matrix_dict
                                all_figs.append(("sankey", fig))
                            elif isinstance(result, dict):
                                if sec.df is None:
                                    sec.df = result.get("df")
                                all_figs.append(("sankey", result.get("chart")))
                        else:
                            # Non-sankey path: strip sankey kwargs
                            non_sankey_kwargs = {k: v for k, v in chart_kwargs.items()
                                                 if k not in ("sankey", "transition_periods",
                                                               "sankey_band_name", "min_percentage")}
                            non_sankey_kwargs["chart_type"] = ct
                            result = cl.summarize_and_chart(
                                sec.ee_obj, sec.geometry, **non_sankey_kwargs
                            )
                            if isinstance(result, dict):
                                first, second = result.get("df"), result.get("chart")
                                if sec.df is None:
                                    if isinstance(first, dict):
                                        import pandas
                                        sec.df = pandas.concat(first, names=["Feature"])
                                    else:
                                        sec.df = first
                                all_figs.append((ct, second))
                    except Exception as e:
                        print(f"    {ct} chart error: {type(e).__name__}: {e}")

                # Distribute figures: first non-sankey → sec.fig,
                # sankey → sec.sankey_fig, rest → sec.extra_figs
                for ct, fig in all_figs:
                    if ct.lower().strip() == "sankey":
                        sec.sankey_fig = fig
                    elif sec.fig is None:
                        sec.fig = fig
                    else:
                        sec.extra_figs.append(fig)

            else:
                # --- Legacy auto-detect path (no chart_types list) ---
                # Convert legacy sankey=True to chart_type='sankey'
                if chart_kwargs.get("sankey"):
                    chart_kwargs.pop("sankey", None)
                    chart_kwargs["chart_type"] = "sankey"
                result = cl.summarize_and_chart(
                    sec.ee_obj, sec.geometry, **chart_kwargs
                )
                if isinstance(result, dict) and "matrix" in result:
                    # Sankey: dict with df, chart, matrix
                    sec.df = result["matrix"]
                    sec.sankey_fig = result["chart"]
                elif isinstance(result, dict):
                    first, second = result.get("df"), result.get("chart")
                    if isinstance(first, dict):
                        import pandas
                        sec.df = pandas.concat(first, names=["Feature"])
                        sec.fig = second
                    else:
                        sec.df = first
                        sec.fig = second
        except Exception as e:
            sec.error = f"{type(e).__name__}: {e}"
            print(f"    Chart/table error: {sec.error}")
            traceback.print_exc()

    def _compute_thumb(self, idx, sec):
        """Compute thumbnail image for a single section (thread-safe).

        Dispatches to ``generate_thumbs``, ``generate_gif``, or
        ``generate_filmstrip`` based on ``sec.thumb_format``.
        """
        fmt = sec.thumb_format
        kw = sec.kwargs
        label = {"png": "thumbnail", "gif": "GIF", "filmstrip": "filmstrip"}.get(fmt, fmt)
        print(f"  [{idx+1}/{len(self._sections)}] Computing {label}: {sec.title}")

        # Shared params (all formats)
        # thumb_crs/thumb_transform override section-level crs/transform/scale
        # Only pass scale/transform if crs is also provided
        geom = kw.get("thumb_geometry", sec.geometry)
        thumb_crs = kw.get("thumb_crs", kw.get("crs"))
        shared = dict(
            viz_params=kw.get("thumb_viz_params"),
            band_name=kw.get("thumb_band_name"),
            dimensions=kw.get("thumb_dimensions", 512),
            burn_in_legend=kw.get("burn_in_legend", True),
            legend_scale=kw.get("legend_scale", 1.0),
            bg_color=kw.get("thumb_bg_color", "black"),
            crs=thumb_crs,
            transform=kw.get("thumb_transform", kw.get("transform")) if thumb_crs else None,
            scale=kw.get("thumb_scale", kw.get("scale")) if thumb_crs else None,
            basemap=kw.get("basemap"),
            burn_in_geometry=kw.get("burn_in_geometry", False),
            geometry_outline_color=kw.get("geometry_outline_color"),
            geometry_fill_color=kw.get("geometry_fill_color"),
            geometry_outline_weight=kw.get("geometry_outline_weight", 2),
            clip_to_geometry=kw.get("clip_to_geometry", True),
            title_font_size=kw.get("title_font_size", 18),
            label_font_size=kw.get("label_font_size", 12),
        )

        try:
            if fmt == "gif":
                import geeViz.geeView as gv
                ee_mod = gv.ee
                if not isinstance(sec.ee_obj, ee_mod.ImageCollection):
                    print(f"    Skipping GIF: ee_obj is not an ImageCollection")
                    return
                result = tl.generate_gif(
                    sec.ee_obj, geom,
                    fps=kw.get("thumb_fps", 2),
                    burn_in_date=kw.get("thumb_burn_in_date", True),
                    date_format=kw.get("thumb_date_format", "YYYY"),
                    date_position=kw.get("thumb_date_position", "upper-left"),
                    max_frames=kw.get("thumb_max_frames", 50),
                    **shared,
                )
                sec.thumb_bytes = result.get("bytes") or _extract_image_bytes(result["html"])

                # Also generate a filmstrip for PDF (GIFs don't work in static PDF)
                try:
                    print(f"  [{idx+1}/{len(self._sections)}] Computing filmstrip (PDF fallback): {sec.title}")
                    has_legend = kw.get("burn_in_legend", True)
                    default_cols = 3 if has_legend else 4
                    fs_result = tl.generate_filmstrip(
                        sec.ee_obj, geom,
                        columns=kw.get("thumb_columns", default_cols),
                        date_format=kw.get("thumb_date_format", "YYYY"),
                        max_frames=kw.get("thumb_max_frames", 50),
                        legend_position=kw.get("legend_position", "bottom"),
                        **shared,
                    )
                    sec.thumb_filmstrip_html = fs_result["html"]
                except Exception as e:
                    print(f"    Filmstrip fallback failed: {e}")

            elif fmt == "filmstrip":
                import geeViz.geeView as gv
                ee_mod = gv.ee
                if not isinstance(sec.ee_obj, ee_mod.ImageCollection):
                    print(f"    Skipping filmstrip: ee_obj is not an ImageCollection")
                    return
                result = tl.generate_filmstrip(
                    sec.ee_obj, geom,
                    columns=kw.get("thumb_columns", 3),
                    date_format=kw.get("thumb_date_format", "YYYY"),
                    max_frames=kw.get("thumb_max_frames", 50),
                    legend_position=kw.get("legend_position", "bottom"),
                    **shared,
                )
                sec.thumb_bytes = result.get("bytes") or _extract_image_bytes(result["html"])

            else:  # "png" (default)
                result = tl.generate_thumbs(
                    sec.ee_obj, geom,
                    **shared,
                )
                sec.thumb_bytes = result.get("bytes") or _extract_image_bytes(result["html"])

            sec.thumb_html = result["html"]

        except Exception as e:
            err_msg = f"{label.title()} error: {type(e).__name__}: {e}"
            print(f"    {err_msg}")
            if sec.error:
                sec.error += f"\n{err_msg}"
            else:
                sec.error = err_msg

    def _recompute_thumbs_for_theme(self):
        """Recompute only thumbnail/GIF/filmstrip images for the current theme.

        Called when the theme has changed since the last ``_compute_all_parallel()``
        so that raster assets (which have baked-in background colors) match the
        new theme.  Charts are handled separately by ``_themed_figure()``.
        """
        _t = _themeLib.get_theme(self.theme)
        new_bg = _t.bg_hex
        print(f"  Theme changed ({self._computed_theme} -> {self.theme}); "
              f"recomputing thumbnails with bg={new_bg}")

        # Update the thumb_bg_color in each section's kwargs
        for sec in self._sections:
            sec.kwargs["thumb_bg_color"] = new_bg

        # Recompute thumbnails in parallel
        sections_with_thumbs = [
            (i, sec) for i, sec in enumerate(self._sections)
            if sec.thumb_format and sec.thumb_html
        ]
        if sections_with_thumbs:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futs = {
                    pool.submit(self._compute_thumb, i, sec): (i, sec)
                    for i, sec in sections_with_thumbs
                }
                for fut in concurrent.futures.as_completed(futs):
                    try:
                        fut.result()
                    except Exception as e:
                        i, sec = futs[fut]
                        print(f"    Thumb recompute error [{i}] {sec.title}: {e}")

        self._computed_theme = self.theme

    def _compute_narrative(self, idx, sec):
        """Generate the LLM narrative for a single section (thread-safe).

        If thumbnail or GIF images are available, they are sent to the LLM
        as inline image parts so the model can describe spatial patterns.
        """
        if sec.error and sec.df is None and not sec.thumb_bytes:
            sec.narrative = f"*Section could not be computed: {sec.error}*"
            return

        print(f"  [{idx+1}/{len(self._sections)}] Generating narrative: {sec.title}")
        table = self._df_to_table_str(sec.df)

        # Build units context from kwargs so LLM knows what the numbers mean
        units_context = self._build_units_context(sec)

        # Build image context description and collect image bytes
        image_context, images = self._build_image_context(sec)

        # Resolve tone instruction
        tone_text = _TONES.get(self.tone, self.tone) if self.tone else ""

        prompt = _SECTION_PROMPT_TEMPLATE.format(
            title=sec.title,
            tone=tone_text,
            units_context=units_context,
            image_context=image_context,
            extra=sec.prompt or "",
            table=table,
        )
        text = self._llm(prompt, images=images if images else None)
        if text:
            sec.narrative = text
        else:
            sec.narrative = self._fallback_narrative(sec)

    @staticmethod
    def _build_units_context(sec):
        """Build a units/context string for the LLM prompt from section kwargs."""
        parts = []
        area_fmt = sec.kwargs.get("area_format", "Percentage")
        is_sankey = sec.kwargs.get("sankey", False)
        scale = sec.kwargs.get("scale", 30)

        if is_sankey:
            periods = sec.kwargs.get("transition_periods", [])
            band = sec.kwargs.get("sankey_band_name", "")
            parts.append(
                f"This is a Sankey/transition analysis showing land class changes "
                f"between time periods: {periods}."
            )
            if band:
                parts.append(f"The band analyzed is '{band}'.")
            parts.append(
                f"The data table shows a transition matrix. Values represent "
                f"the area of each from-class to to-class transition in "
                f"**{area_fmt.lower()}** (at {scale}m pixel scale)."
            )
        else:
            parts.append(
                f"Numeric values in the data are in **{area_fmt.lower()}** "
                f"(at {scale}m pixel scale)."
            )

        if area_fmt == "Percentage":
            parts.append("Values sum to ~100% per time step.")
        elif area_fmt == "Hectares":
            parts.append("Values are in hectares.")
        elif area_fmt == "Acres":
            parts.append("Values are in acres.")
        elif area_fmt == "Pixels":
            parts.append(f"Values are pixel counts (each pixel = {scale}m x {scale}m).")

        ct = sec.kwargs.get("chart_type", "")
        stacked = sec.kwargs.get("stacked", False)
        if stacked or (isinstance(ct, str) and ct.startswith("stacked")):
            parts.append("The chart is a stacked area/bar chart showing composition over time.")

        return "\n".join(parts)

    @staticmethod
    def _build_image_context(sec):
        """Build image context text and collect image bytes for the LLM.

        Returns:
            tuple: (context_str, images_list) where images_list is a list
            of (bytes, mime_type) tuples, or empty list if no images.
        """
        if not sec.thumb_bytes:
            return "", []

        fmt = sec.thumb_format or "png"
        mime = "image/gif" if fmt == "gif" else "image/png"
        images = [(sec.thumb_bytes, mime)]

        descriptions = {
            "gif": (
                "An animated GIF map is attached showing the spatial output "
                "of this dataset over time, clipped to the study area. "
                "Describe any notable spatial patterns, geographic "
                "concentrations, or changes you observe across the frames."
            ),
            "filmstrip": (
                "A filmstrip grid image (PNG) is attached showing individual "
                "time-step frames arranged in a grid. Each frame is labeled "
                "with its date. Describe any temporal progression or spatial "
                "changes visible across the frames."
            ),
            "png": (
                "A map thumbnail (PNG) is attached showing the spatial "
                "output of this dataset clipped to the study area. "
                "Describe any notable spatial patterns, geographic "
                "concentrations, or distribution you observe."
            ),
        }
        context = descriptions.get(fmt, descriptions["png"])
        return context, images

    # -- Private: LLM integration ------------------------------------------

    def _get_client(self):
        """Lazy-init the Gemini client."""
        if self._client is not None:
            return self._client

        key = self._api_key
        if not key:
            try:
                import dotenv
                dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
            except ImportError:
                pass
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

        if not key:
            raise ValueError(
                "No Gemini API key found. Pass api_key= to Report() or set "
                "GEMINI_API_KEY in your environment / .env file."
            )

        from google import genai
        self._client = genai.Client(api_key=key)
        return self._client

    def _llm(self, prompt_text, images=None):
        """Call Gemini and return the response text.

        Args:
            prompt_text (str): The text prompt.
            images (list[tuple], optional): List of ``(bytes, mime_type)``
                tuples for multimodal input.  Each image is included as an
                inline data part so the model can see thumbnails/GIFs.
        """
        try:
            from google.genai import types

            client = self._get_client()

            # Build multimodal content if images are provided
            if images:
                parts = [types.Part.from_text(text=prompt_text)]
                for img_bytes, mime in images:
                    parts.append(types.Part.from_bytes(
                        data=img_bytes, mime_type=mime,
                    ))
                contents = [types.Content(parts=parts)]
            else:
                contents = prompt_text

            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return response.text
        except Exception as e:
            print(f"    LLM error: {e}")
            return None

    def _df_to_table_str(self, df, max_rows=80):
        """Convert a DataFrame or dict of DataFrames to a markdown table string."""
        if df is None:
            return "(no data)"
        if isinstance(df, dict):
            parts = []
            for label, mdf in df.items():
                parts.append(f"**{label}**\n{mdf.to_markdown()}")
            return "\n\n".join(parts) if parts else "(no data)"
        if len(df) > max_rows:
            half = max_rows // 2
            table = df.head(half).to_markdown() + "\n\n... (truncated) ...\n\n" + df.tail(half).to_markdown()
        else:
            table = df.to_markdown()
        return table

    def _generate_executive_summary(self):
        """Generate the executive summary from all sections.

        Includes all available thumbnail and GIF images so the LLM can
        reference spatial patterns in the executive summary.
        """
        print("  Generating executive summary...")
        briefs = []
        images = []
        for sec in self._sections:
            if sec.narrative and sec.narrative != self._fallback_narrative(sec):
                brief = sec.narrative[:200].replace("\n", " ")
                briefs.append(f"**{sec.title}**: {brief}...")
            elif sec.df is not None:
                if isinstance(sec.df, dict):
                    n_matrices = len(sec.df)
                    briefs.append(f"**{sec.title}**: {n_matrices} transition matrices")
                else:
                    shape = f"{len(sec.df)} rows x {len(sec.df.columns)} columns"
                    cols = ", ".join(sec.df.columns[:10])
                    briefs.append(f"**{sec.title}**: {shape}. Columns: {cols}")
            elif sec.error:
                briefs.append(f"**{sec.title}**: Error -- {sec.error}")

            # Collect images for the executive summary
            if sec.thumb_bytes:
                mime = "image/gif" if sec.thumb_format == "gif" else "image/png"
                images.append((sec.thumb_bytes, mime))

        image_note = ""
        if images:
            image_note = (
                "\nMap images from each section are attached. Reference "
                "notable spatial patterns in your summary where relevant."
            )

        tone_text = _TONES.get(self.tone, self.tone) if self.tone else ""
        prompt = _SUMMARY_PROMPT_TEMPLATE.format(
            title=self.title,
            tone=tone_text,
            extra=self.prompt or "",
            image_note=image_note,
            section_summaries="\n".join(f"- {b}" for b in briefs),
        )
        text = self._llm(prompt, images=images if images else None)
        self._summary = text or "Executive summary could not be generated."

    @staticmethod
    def _fallback_narrative(sec):
        """Simple auto-generated text when LLM is unavailable."""
        if sec.df is not None:
            if isinstance(sec.df, dict):
                return f"This section contains {len(sec.df)} transition matrices."
            return (
                f"This section contains {len(sec.df)} rows of data "
                f"across {len(sec.df.columns)} columns."
            )
        return "No data available for this section."

    # -- Private: icon helpers ---------------------------------------------

    def _get_icon_uri(self):
        """Return a base64 data URI (or None) for the header/footer icon.

        Checks ``header_icon`` first, then falls back to the built-in geeViz
        logo.  Supports file paths, URLs, and raw ``data:`` URIs.
        """
        icon = self.header_icon
        if icon is False:
            return None
        if icon and isinstance(icon, str):
            if icon.startswith("data:"):
                return icon
            # URL — fetch and embed; fall through to default on failure
            if icon.startswith(("http://", "https://")):
                result = self._fetch_icon_url(icon)
                if result:
                    return result
            # File path
            if os.path.exists(icon):
                with open(icon, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(icon)[1].lower().lstrip(".")
                mime = {"png": "image/png", "jpg": "image/jpeg",
                        "jpeg": "image/jpeg", "svg": "image/svg+xml",
                        "gif": "image/gif"}.get(ext, "image/png")
                return f"data:{mime};base64,{b64}"
        # Default: built-in geeViz logo
        _t = _themeLib.get_theme(self.theme)
        variant = "dark" if _t.is_dark else "light"
        return _get_logo_b64(variant)

    @staticmethod
    def _fetch_icon_url(url):
        """Fetch a URL and return a base64 data URI, or None on failure."""
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "geeViz"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                content_type = resp.headers.get("Content-Type", "image/png")
                # Simplify content type
                if "svg" in content_type:
                    mime = "image/svg+xml"
                elif "png" in content_type:
                    mime = "image/png"
                elif "jpeg" in content_type or "jpg" in content_type:
                    mime = "image/jpeg"
                else:
                    mime = content_type.split(";")[0].strip()
                b64 = base64.b64encode(data).decode()
                return f"data:{mime};base64,{b64}"
        except Exception as e:
            print(f"    Warning: Could not fetch icon from {url}: {e}")
            return None

    # -- Private: CSS assembly ---------------------------------------------

    def _get_css(self):
        """Build the full CSS string from theme + layout."""
        _t = _themeLib.get_theme(self.theme)
        return _render_report_css(_t, self.layout)

    # -- Private: chart theming --------------------------------------------

    def _themed_figure(self, fig):
        """Return a theme-appropriate copy of a Plotly figure.

        Charts from ``chartingLib`` are dark-themed by default.  For light
        reports this returns a deep copy with ``_apply_light_theme`` applied.
        For dark reports the original figure is returned unchanged.
        """
        _t = _themeLib.get_theme(self.theme)
        if _t.is_dark:
            return fig
        import copy
        fig_copy = copy.deepcopy(fig)
        # Preserve custom Sankey attributes (deepcopy may drop them)
        for attr in ("_gradient_color_map", "_gradient_link_opacity"):
            val = getattr(fig, attr, None)
            if val is not None:
                setattr(fig_copy, attr, val)
        _themeLib.apply_plotly_theme(fig_copy, _t)
        return fig_copy

    # -- Private: chart to static image ------------------------------------

    def _render_subplot_images(self, fig, n_subplots, width, parts):
        """Render a multi-subplot figure as separate per-row images.

        Each subplot gets its own static PNG so it can page-break
        independently in PDFs instead of being squished into one image.
        """
        import plotly.graph_objects as go

        # Get all traces and their subplot assignments
        traces_by_row = {}
        for trace in fig.data:
            # Subplot row is encoded in yaxis: "y", "y2", "y3", etc.
            yaxis = getattr(trace, "yaxis", "y") or "y"
            row = int(yaxis.replace("y", "") or "1")
            traces_by_row.setdefault(row, []).append(trace)

        # Get layout info for title
        title = ""
        if fig.layout.title and fig.layout.title.text:
            title = fig.layout.title.text

        per_h = 300  # height per subplot row
        sorted_rows = sorted(traces_by_row.keys())

        for i, row_key in enumerate(sorted_rows):
            traces = traces_by_row[row_key]
            # Build a standalone figure for this subplot
            sub_fig = go.Figure()
            for trace in traces:
                # Reset yaxis/xaxis to default for standalone figure
                new_trace = trace.to_plotly_json()
                new_trace.pop("xaxis", None)
                new_trace.pop("yaxis", None)
                sub_fig.add_trace(go.Scatter(**{
                    k: v for k, v in new_trace.items()
                    if k != "type" and v is not None
                }))

            # Get subplot title from annotations
            sub_title = ""
            for ann in (fig.layout.annotations or []):
                ann_dict = ann.to_plotly_json()
                # Subplot titles are positioned by yref
                if ann_dict.get("text"):
                    # Check if this annotation belongs to this row
                    y = ann_dict.get("y", 0)
                    expected_y_range = (1 - (i + 0.5) / n_subplots)
                    if abs(y - expected_y_range) < 0.5 / n_subplots:
                        sub_title = ann_dict["text"]
                        break

            # Apply theme
            _t = _themeLib.get_theme(self.theme)
            chart_title = sub_title or (title if i == 0 else "")
            sub_fig.update_layout(
                title=dict(text=chart_title, x=0.5) if chart_title else None,
                height=per_h, width=width,
                paper_bgcolor=_t.bg_hex,
                plot_bgcolor=_t.bg_hex,
                font=dict(color=_t.text_hex),
                margin=dict(l=60, r=20, t=40 if chart_title else 20, b=40),
                showlegend=(i == 0),
            )
            if i == 0 and fig.layout.legend:
                sub_fig.update_layout(legend=fig.layout.legend.to_plotly_json())

            img_uri = self._fig_to_static_img(sub_fig, width=width, height=per_h)
            if img_uri:
                parts.append(
                    f'<div class="chart"><img src="{img_uri}" '
                    f'style="max-width:100%;border-radius:6px;"></div>'
                )

    @staticmethod
    def _fig_to_static_img(fig, width=900, height=500):
        """Render a Plotly figure to a base64 PNG data URI using kaleido.

        Returns None if kaleido is not available.
        """
        if fig is None:
            return None
        try:
            import plotly.io as pio
            img_bytes = pio.to_image(fig, format="png", width=width, height=height)
            b64 = base64.b64encode(img_bytes).decode()
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            print(f"    Static chart export failed: {e}")
            return None

    def _sankey_to_static_img(self, fig, width=900, height=600):
        """Render a Sankey figure to a base64 PNG via headless browser screenshot.

        Delegates to :func:`~geeViz.outputLib.charts.html_to_png`.
        Falls back to kaleido if no browser is available.

        Returns a ``data:image/png;base64,...`` URI or None.
        """
        try:
            _t = _themeLib.get_theme(self.theme)
            sankey_html = cl.sankey_to_html(
                fig, bg_color=_t.bg_hex, font_color=_t.text_hex,
                renderer="d3", hide_toolbar=True,
            )
            img_bytes = cl.html_to_png(sankey_html, width=width, height=height)
            if img_bytes is not None:
                b64 = base64.b64encode(img_bytes).decode()
                return f"data:image/png;base64,{b64}"
            else:
                print(f"    Sankey screenshot failed (no browser), falling back to kaleido")
                return self._fig_to_static_img(fig, width=width, height=height)
        except Exception as e:
            print(f"    Sankey screenshot error: {e}, falling back to kaleido")
            return self._fig_to_static_img(fig, width=width, height=height)

    def _gif_to_filmstrip_html(self, sec):
        """Render a GIF section as a filmstrip grid for PDF output.

        GIFs don't render in static PDFs, so we generate a filmstrip
        (grid of PNG thumbnails) on the fly using the same parameters.
        """
        import geeViz.geeView as gv
        ee_mod = gv.ee

        if not isinstance(sec.ee_obj, ee_mod.ImageCollection):
            return sec.thumb_html  # fallback to original

        kw = sec.kwargs
        geom = kw.get("thumb_geometry", sec.geometry)
        shared = dict(
            viz_params=kw.get("thumb_viz_params"),
            band_name=kw.get("thumb_band_name"),
            dimensions=kw.get("thumb_dimensions", 512),
            burn_in_legend=kw.get("burn_in_legend", True),
            legend_scale=kw.get("legend_scale", 1.0),
            bg_color=kw.get("thumb_bg_color", "black"),
            basemap=kw.get("basemap"),
        )

        try:
            result = tl.generate_filmstrip(
                sec.ee_obj, geom,
                columns=kw.get("thumb_columns", 4),
                date_format=kw.get("thumb_date_format", "YYYY"),
                max_frames=kw.get("thumb_max_frames", 50),
                crs=kw.get("thumb_crs"),
                transform=kw.get("thumb_transform"),
                **shared,
            )
            return result["html"]
        except Exception as e:
            print(f"    GIF-to-filmstrip fallback failed: {e}")
            return sec.thumb_html  # fallback to original GIF HTML

    # -- Private: section HTML builder (shared by HTML and PDF) ------------

    def _render_section_html(self, sec, static_charts=False):
        """Render a single section to an HTML fragment.

        Args:
            sec: _Section instance.
            static_charts: If True, render charts as static PNG images
                (for PDF). If False, use interactive Plotly JS (for HTML).
        """
        import markdown

        parts = [f'<div class="section">', f'<h2>{sec.title}</h2>']

        # Narrative first — fix inline `* ` markers to proper markdown list items
        narrative_md = sec.narrative or ""
        import re as _re
        narrative_md = _re.sub(r'(?<=[.:]) \* ', r'\n* ', narrative_md)
        parts.append(
            f'<div class="narrative">{markdown.markdown(narrative_md)}</div>'
        )

        # Thumbnail / GIF / filmstrip image
        if sec.thumb_format and sec.thumb_html:
            if static_charts and sec.thumb_format == "gif":
                # GIFs don't work in PDF — use pre-computed filmstrip grid
                parts.append(sec.thumb_filmstrip_html or sec.thumb_html)
            else:
                parts.append(sec.thumb_html)

        # Charts — render sankey_fig, fig, and any extra_figs
        figs_to_render = []
        if sec.sankey_fig is not None:
            figs_to_render.append(sec.sankey_fig)
        if sec.generate_chart and sec.fig is not None:
            figs_to_render.append(sec.fig)
        for extra in (sec.extra_figs or []):
            figs_to_render.append(extra)

        for fig_obj in figs_to_render:
            # D3 sankey: already an HTML string (from chart_sankey_d3)
            if isinstance(fig_obj, str):
                parts.append(
                    f'<div class="chart"><iframe srcdoc="{_escape_attr(fig_obj)}" '
                    f'style="width:100%;height:{sec.kwargs.get("height", 600) + 50}px;border:none;overflow:hidden;"></iframe></div>'
                )
                continue

            fig_to_render = self._themed_figure(fig_obj)
            is_sankey = hasattr(fig_to_render, "_gradient_color_map")

            if static_charts:
                w = sec.kwargs.get("width", 900)
                if is_sankey:
                    h = sec.kwargs.get("height", 650)
                    img_uri = self._sankey_to_static_img(
                        fig_to_render, width=w, height=h,
                    )
                    if img_uri:
                        parts.append(
                            f'<div class="chart"><img src="{img_uri}" '
                            f'style="max-width:100%;border-radius:6px;"></div>'
                        )
                else:
                    # Use figure's own height for multi-subplot charts
                    fig_h = fig_to_render.layout.height or 500
                    h = sec.kwargs.get("height", fig_h)
                    img_uri = self._fig_to_static_img(
                        fig_to_render, width=w, height=h,
                    )
                    if img_uri:
                        # For tall charts, don't constrain width (let it scroll/flow)
                        style = 'width:100%;border-radius:6px;' if h > 800 else 'max-width:100%;border-radius:6px;'
                        parts.append(
                            f'<div class="chart"><img src="{img_uri}" '
                            f'style="{style}"></div>'
                        )
            else:
                if is_sankey:
                    _th = _themeLib.get_theme(self.theme)
                    chart_html = cl.sankey_to_html(
                        fig_to_render,
                        bg_color=_th.bg_hex,
                        font_color=_th.text_hex,
                        theme=self.theme,
                    )
                    parts.append(
                        f'<div class="chart"><iframe srcdoc="{_escape_attr(chart_html)}" '
                        f'style="width:100%;height:{sec.kwargs.get("height", 600) + 50}px;border:none;overflow:hidden;"></iframe></div>'
                    )
                else:
                    # Scale height for multi-subplot figures
                    n_rows = sum(1 for k in fig_to_render.layout.to_plotly_json()
                                 if k.startswith("yaxis"))
                    if n_rows > 1 and (fig_to_render.layout.height or 0) < 200 * n_rows:
                        fig_to_render.update_layout(height=200 * n_rows)
                    chart_div = fig_to_render.to_html(
                        full_html=False, include_plotlyjs=False,
                        config=cl._plotly_download_config(fig_to_render),
                    )
                    parts.append(f'<div class="chart">{chart_div}</div>')

        # Table
        if sec.generate_table and sec.df is not None:
            area_fmt = sec.kwargs.get("area_format", "Percentage")
            units_label = cl.AREA_FORMAT_DICT.get(area_fmt, {}).get("label", area_fmt)
            is_sankey = sec.kwargs.get("sankey", False)

            if isinstance(sec.df, dict):
                for period_label, mdf in sec.df.items():
                    table_html = self._render_transition_matrix(
                        mdf, period_label, units_label=units_label,
                    )
                    parts.append(table_html)
            else:
                # Build descriptive table title: "Section Title - Annual units"
                table_title = f'{sec.title} — Annual {units_label}'
                title_html = f'<h4 class="matrix-title">{table_title}</h4>'
                table_html = sec.df.to_html(classes="", border=0, max_rows=100)
                parts.append(f'<div class="table-wrapper">{title_html}{table_html}</div>')

        if sec.error:
            parts.append(f'<div class="error">{sec.error}</div>')

        parts.append('</div>')
        return "\n".join(parts)

    @staticmethod
    def _render_transition_matrix(mdf, period_label, units_label=""):
        """Render a transition matrix DataFrame as HTML with diagonal highlighting.

        Adds "From (year)" row header and "To (year)" column header labels,
        and highlights the diagonal cells (same-class persistence).
        """
        # Parse years from period_label like "1990 → 2024"
        parts_label = period_label.split("\u2192")
        from_year = parts_label[0].strip() if len(parts_label) == 2 else ""
        to_year = parts_label[1].strip() if len(parts_label) == 2 else ""

        class_names = list(mdf.index)
        col_names = list(mdf.columns)

        rows = []
        # Header row — rows=from, columns=to
        corner = f'{from_year} (rows) | {to_year} (columns)'
        hdr = f'<tr><th class="matrix-corner">{corner}</th>'
        for c in col_names:
            hdr += f"<th>{c}</th>"
        hdr += "</tr>"
        rows.append(hdr)

        # Data rows with diagonal highlight
        for ri, rname in enumerate(class_names):
            row = f'<tr><th>{rname}</th>'
            for ci, cname in enumerate(col_names):
                val = mdf.iloc[ri, ci]
                css_class = ' class="diag"' if ri == ci else ""
                row += f"<td{css_class}>{val}</td>"
            row += "</tr>"
            rows.append(row)

        units_html = f'<p class="table-units">Values in {units_label}</p>' if units_label else ""
        table = (
            f'<div class="table-wrapper">'
            f'<h4 class="matrix-title">{period_label}</h4>'
            f'{units_html}'
            f'<table class="transition-matrix" border="0">'
            f'<thead>{rows[0]}</thead>'
            f'<tbody>{"".join(rows[1:])}</tbody>'
            f'</table></div>'
        )
        return table

    # -- Private: rendering ------------------------------------------------

    def _build_header_footer(self):
        """Build the header block, header text, and footer HTML."""
        import markdown  # noqa: F811

        icon_uri = self._get_icon_uri()

        if icon_uri:
            header_block = (
                f'<div class="report-header">'
                f'<img src="{icon_uri}" alt="Logo">'
                f'<h1>{self.title}</h1>'
                f'</div>'
            )
        else:
            header_block = f'<h1>{self.title}</h1>'

        header_text_html = (
            f'<p class="header-text">{self.header_text}</p>'
            if self.header_text else ""
        )

        summary_md = self._summary or ""
        summary_html = (
            '<div class="summary">'
            '<h3>Executive Summary</h3>'
            f'{markdown.markdown(summary_md)}'
            '</div>'
        )

        footer_parts = ['<div class="report-footer">']
        if icon_uri:
            footer_parts.append(f'<img src="{icon_uri}" alt="geeViz">')
        footer_parts.append(
            f'Powered by: '
            f'<a href="https://geeviz.org/">geeViz.reportLib</a> | '
            f'<a href="https://gemini.google.com/">Gemini</a> {self.model} | '
            f'<a href="https://earthengine.google.com/">Earth Engine</a>'
        )
        footer_parts.append('</div>')
        footer_html = "\n".join(footer_parts)

        return header_block, header_text_html, summary_html, footer_html

    def _render_html(self):
        """Assemble the full interactive HTML report."""
        css = self._get_css()
        header_block, header_text_html, summary_html, footer_html = (
            self._build_header_footer()
        )

        section_parts = [
            self._render_section_html(sec, static_charts=False)
            for sec in self._sections
        ]

        # Wrap sections in poster grid if poster layout
        if self.layout == "poster":
            sections_html = (
                '<div class="poster-grid">\n'
                + "\n\n".join(section_parts)
                + '\n</div>'
            )
        else:
            sections_html = "\n\n".join(section_parts)

        return _HTML_TEMPLATE.format(
            title=self.title,
            css=css,
            header_block=header_block,
            header_text_html=header_text_html,
            timestamp=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            summary_html=summary_html,
            sections_html=sections_html,
            footer_html=footer_html,
        )

    def _render_md(self):
        """Render the report as Markdown (no charts, no thumbnails)."""
        lines = [f"# {self.title}", ""]
        if self.header_text:
            lines += [self.header_text, ""]
        lines += [
            "## Executive Summary", "",
            self._summary or "*(not generated)*", "",
        ]

        for sec in self._sections:
            lines += [f"## {sec.title}", ""]
            if sec.narrative:
                lines += [sec.narrative, ""]
            if sec.generate_table and sec.df is not None:
                if isinstance(sec.df, dict):
                    for label, mdf in sec.df.items():
                        lines += [f"### {label}", mdf.to_markdown(), ""]
                else:
                    lines += [sec.df.to_markdown(), ""]
            if sec.error:
                lines += [f"**Error:** {sec.error}", ""]
            lines.append("---\n")

        lines.append("")
        lines.append(
            f"*Generated using [geeViz](https://geeviz.org/) reportLib"
            f" and {self.model} for output summaries.*"
        )
        return "\n".join(lines)

    def _render_pdf(self, output_path):
        """Render the report as PDF.

        Uses kaleido to render Plotly charts as static PNG images, then
        converts to PDF using (in order of preference):

        1. Edge/Chrome headless ``--print-to-pdf`` (available on most systems)
        2. ``pdfkit`` + ``wkhtmltopdf``
        3. Fallback: saves a print-ready HTML with ``@page`` CSS directives
        """
        import shutil
        import subprocess
        import tempfile

        if not output_path:
            output_path = self.title.replace(" ", "_") + ".pdf"

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Use the theme that was active when thumbnails/GIFs were computed so
        # the CSS background matches the baked-in raster backgrounds.
        render_theme = self._computed_theme or self.theme
        saved_theme = self.theme
        self.theme = render_theme

        try:
            return self._render_pdf_inner(output_path)
        finally:
            self.theme = saved_theme

    def _render_pdf_inner(self, output_path):
        """Internal PDF rendering (called by _render_pdf with theme set)."""
        import shutil
        import subprocess
        import tempfile

        # Build HTML with static chart images (no JS needed)
        _t = _themeLib.get_theme(self.theme)
        css = self._get_css()
        # PDF overrides: full-bleed background, proper page breaks
        css += textwrap.dedent(f"""
            html, body {{
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            @page {{
                margin: 0;
                size: letter portrait;
            }}
            body {{
                padding: 0.4in 0.5in 0.4in 0.5in;
            }}
            .report-header {{
                margin: -0.4in -0.5in 16px -0.5in;
                padding: 12px 0.5in;
            }}
            .table-wrapper {{
                max-height: none !important;
                overflow-y: visible !important;
                overflow-x: visible !important;
            }}
            table {{ font-size: 9px; }}
            thead {{ display: table-header-group; }}
            tr {{ page-break-inside: avoid; }}
            h2 {{ page-break-after: avoid; }}
            .narrative {{ page-break-before: avoid; }}
            .filmstrip img {{ page-break-inside: avoid; }}
            .matrix-title {{ page-break-after: avoid; }}
            .table-units {{ page-break-after: avoid; }}
            .table-wrapper {{ page-break-before: auto; }}
            .report-footer {{ display: none; }}
            .pdf-footer-tpl {{ display: none; }}
            .pdf-page-footer {{
                display: flex; align-items: center; gap: 8px;
                position: fixed; bottom: 0; left: 0.5in; right: 0.5in;
                padding: 4px 0;
                border-top: 1px solid {_t.border_hex};
                color: {_t.muted_text_hex}; font-size: 9px;
                background: {_t.bg_hex};
                z-index: 100;
            }}
            .pdf-page-footer a {{ color: {_t.accent_hex}; text-decoration: none; }}
            .pdf-page-footer img {{ height: 16px; width: auto; max-width: 80px;
                border-radius: 3px; opacity: 0.7; }}
            .pdf-page-footer .page-num {{ margin-left: auto; }}
            /* Ensure content doesn't get hidden behind fixed footer */
            body {{ padding-bottom: 40px; }}
        """)

        header_block, header_text_html, summary_html, footer_html = (
            self._build_header_footer()
        )

        section_parts = [
            self._render_section_html(sec, static_charts=True)
            for sec in self._sections
        ]

        if self.layout == "poster":
            sections_html = (
                '<div class="poster-grid">\n'
                + "\n\n".join(section_parts)
                + '\n</div>'
            )
        else:
            sections_html = "\n\n".join(section_parts)

        # Build PDF footer template (hidden) + JS to clone per page
        icon_uri = self._get_icon_uri()
        icon_img = f'<img src="{icon_uri}" alt="geeViz"> ' if icon_uri else ''
        footer_content = (
            f'{icon_img}'
            f'Powered by: '
            f'<a href="https://geeviz.org/">geeViz.reportLib</a> | '
            f'<a href="https://gemini.google.com/">Gemini</a> {self.model} | '
            f'<a href="https://earthengine.google.com/">Earth Engine</a>'
            f'<span class="page-num"></span>'
        )
        # Fixed footer: position:fixed repeats on every printed page
        pdf_footer_html = (
            f'<div class="pdf-page-footer">{footer_content}</div>'
        )

        html = _PDF_HTML_TEMPLATE.format(
            title=self.title,
            css=css,
            header_block=header_block,
            header_text_html=header_text_html,
            timestamp=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            summary_html=summary_html,
            sections_html=sections_html,
            footer_html=footer_html,
            pdf_footer_html=pdf_footer_html,
        )

        # Strategy 1: Edge or Chrome headless --print-to-pdf
        browser = _find_browser()
        if browser:
            try:
                tmp_html = os.path.join(tempfile.gettempdir(), "geeviz_report_tmp.html")
                with open(tmp_html, "w", encoding="utf-8") as f:
                    f.write(html)

                # Build the command
                abs_pdf = os.path.abspath(output_path)
                cmd = [
                    browser, "--headless", "--disable-gpu",
                    f"--print-to-pdf={abs_pdf}",
                    "--no-pdf-header-footer",
                    "--virtual-time-budget=3000",
                ]
                if self.layout == "poster":
                    # 48x36 inch poster
                    cmd.append("--print-to-pdf-no-header")
                cmd.append(tmp_html)

                result = subprocess.run(cmd, capture_output=True, timeout=120)
                os.remove(tmp_html)

                if result.returncode == 0 and os.path.exists(abs_pdf):
                    print(f"PDF saved to: {output_path}")
                    return output_path
                else:
                    stderr = result.stderr.decode(errors="replace")[:200]
                    print(f"  Browser PDF failed: {stderr}")
            except Exception as e:
                print(f"  Browser PDF failed: {e}")

        # Strategy 2: pdfkit + wkhtmltopdf
        try:
            import pdfkit
            orientation = "Landscape" if self.layout == "poster" else "Portrait"
            options = {
                "page-size": "Letter",
                "orientation": orientation,
                "margin-top": "0.4in",
                "margin-right": "0.4in",
                "margin-bottom": "0.4in",
                "margin-left": "0.4in",
                "encoding": "UTF-8",
                "enable-local-file-access": "",
            }
            pdfkit.from_string(html, output_path, options=options)
            print(f"PDF saved to: {output_path}")
            return output_path
        except ImportError:
            pass
        except Exception as e:
            print(f"  pdfkit failed: {e}")

        # Strategy 3: Fallback — save print-ready HTML
        fallback = output_path.rsplit(".", 1)[0] + "_printable.html"
        with open(fallback, "w", encoding="utf-8") as f:
            f.write(html)
        print(
            f"PDF conversion not available.\n"
            f"Print-ready HTML saved to: {fallback}\n"
            f"Open in a browser -> Print -> Save as PDF"
        )
        return fallback


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------
def _find_browser():
    """Locate Edge or Chrome executable for headless PDF rendering.

    Delegates to :func:`~geeViz.outputLib.charts._find_browser`.
    """
    return cl._find_browser()


def _extract_image_bytes(html_str):
    """Extract raw image bytes from a base64-embedded HTML img tag.

    Looks for ``src="data:image/...;base64,..."`` in the HTML and returns
    the decoded bytes.  Returns None if no base64 image found.
    """
    import re
    m = re.search(r'src="data:image/[^;]+;base64,([^"]+)"', html_str)
    if m:
        return base64.b64decode(m.group(1))
    return None


def _escape_attr(html):
    """Escape HTML for use inside an attribute value (srcdoc)."""
    return html.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
