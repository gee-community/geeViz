# geeViz.outputLib — publication-ready output pipeline for Earth Engine

Four cohesive modules that turn raw `ee.Image` / `ee.ImageCollection` / `ee.FeatureCollection` inputs into finished, sharable outputs — charts, thumbnails, animated GIFs, and multi-section reports — with automatic thematic-vs.-continuous detection, unified theming across all outputs, and parallel Earth Engine data fetching.

Everything here is importable standalone; the geeViz Agent's MCP server also exposes these as pre-loaded aliases (`cl`, `tl`, `rl`, and `themes` via `apply_theme`) inside `run_code`.

## Modules at a glance

| Module | Purpose |
|---|---|
| `charts.py` | Zonal statistics + Plotly time series / bar / donut / scatter / D3 Sankey charts. Auto-detects thematic vs. continuous data; picks the right reducer; returns a pandas DataFrame + Plotly figure in one call. |
| `thumbs.py` | Publication-ready PNG thumbnails and animated GIFs. Auto-viz detection, basemap compositing, projected-CRS support (Albers/UTM/any EPSG), scalebars, north arrows, inset locator maps, thematic legends with auto-truncated labels, per-frame date burn-in. |
| `reports.py` | Multi-section reports combining charts, thumbnails, Sankey diagrams, data tables, and Gemini-generated narratives. All EE fetches run in parallel via `concurrent.futures`. HTML, Markdown, and PDF output; dark/light themes; portrait "report" and landscape "poster" layouts. |
| `themes.py` | Unified `Theme` class shared across charts, thumbs, and reports. Named presets (`dark`, `light`, `teal`) or auto-derive from a single background color. Applies to Plotly (`apply_plotly_theme`), Matplotlib (`apply_matplotlib_theme`), or polymorphically (`apply_theme`). |

## Design principles

- **Auto-visualization.** If an image has `<band>_class_values` / `_class_names` / `_class_palette` properties, `charts` and `thumbs` treat it as thematic and use those for the legend and colors. Otherwise it's treated as continuous and mapped via `min` / `max` / `palette`. Same logic the interactive `geeView` uses — so a script and a browser tab render identically.
- **One shared theme.** A chart, a thumbnail, and a report generated in the same session all read colors from the same `Theme` object. Change the theme once at the top of a notebook and everything downstream matches.
- **Parallel by default.** `reports.Report.render()` fans out to every section's chart / thumbnail / narrative call at once via a thread pool — the wall-clock is roughly the slowest single call, not the sum.
- **Both users and agents.** Every top-level function accepts either explicit dicts (agent-friendly, deterministic) or the terse geeViz idioms (`Map.addLayer`-style viz params). The MCP server calls the same functions the docstring examples show.

## Quick starts

### Charts

```python
import geeViz.geeView as gv
from geeViz.outputLib import charts as cl

ee = gv.ee
roi = ee.Geometry.Rectangle([-106, 39.5, -105, 40.5])
lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10").select("Land_Cover")

df, fig = cl.summarize_and_chart(lcms, roi, stacked=True)
fig.write_html("landcover.html", include_plotlyjs="cdn")
```

Sankey diagrams (class transitions across time): pass `chart_type='sankey'` and `transition_periods=[year1, year2, ...]`.

Multi-ROI fan-out: `cl.summarize_and_chart_many(collection, roi_list, ...)` runs one EE job per ROI concurrently and returns a list of (df, fig) tuples.

### Thumbnails and GIFs

```python
from geeViz.outputLib import thumbs as tl

# Single image → PNG with auto-viz, basemap, and scalebar
tl.generate_thumbs(
    dem := ee.Image("USGS/SRTMGL1_003"),
    geometry=roi,
    filename="srtm.png",
    dimensions=1000,
)

# ImageCollection → animated GIF, one frame per time step
tl.generate_gif(
    lcms,
    geometry=roi,
    filename="landcover.gif",
    fps=2,
    burn_in_date=True,
)
```

### Reports

```python
from geeViz.outputLib import reports as rl

report = rl.Report(
    title="Watershed Change 2018–2024",
    theme="dark",
    layout="report",
)
report.add_section(
    "Land cover trends",
    charts=[(lcms, roi, {"stacked": True})],
    thumbnails=[(lcms.first(), roi, {"dimensions": 800})],
    narrative_prompt="Summarize the land cover trends visible in the chart.",
)
# One .render() call fans out every EE request and LLM call in parallel.
report.render("report.html")
```

PDF output: `report.render("report.pdf")`. Markdown: `.render("report.md")`.

### Themes

```python
from geeViz.outputLib.themes import get_theme, apply_theme

theme = get_theme("dark")                       # named preset
theme = get_theme(bg_color="#1a1a2e")           # auto-derive from a bg color

# Any Plotly or Matplotlib object:
apply_theme(fig, theme=theme)
```

Register your own preset once, use everywhere:

```python
from geeViz.outputLib.themes import Theme, register_preset
register_preset("company", Theme(bg=(0, 20, 40), text=(230, 235, 240)))
```

## Where to look next

- **Full API reference** — see the [module docs](https://geeviz.org/overview.html) or run `search_geeviz(module="outputLib.charts")` (etc.) in the geeViz MCP server.
- **Example notebooks** — `geeViz/examples/`:
  - `areaChart_examples.ipynb` — time series and bar charts
  - `getSummaryAreas_thumb_and_chartingLib_examples.ipynb` — end-to-end with summary areas
  - `thumbLib_examples.ipynb` — thumbnail + GIF options in detail
  - `report_generation_examples.ipynb` — full report walkthrough

## Related packages

- **`geeViz.geeView`** — the interactive browser-based map viewer these outputs' auto-viz logic mirrors. See [`../geeView/README.md`](../geeView/README.md).
- **`geeViz.eeAuth`** — the multi-tenant EE auth proxy that `Map.view()` uses. See [`../eeAuth/README.md`](../eeAuth/README.md).
- **`geeViz.mcp`** — the MCP server that exposes `outputLib` to AI coding assistants via `cl`, `tl`, `rl` aliases. See [`../mcp/README.md`](../mcp/README.md).
