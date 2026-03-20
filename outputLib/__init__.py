"""
Output sub-package for geeViz.

Provides charting, thumbnails, reports, and theming for Earth Engine
analysis outputs.

Modules:
    charts  — Zonal summary & charting (summarize_and_chart, chart_sankey, etc.)
    thumbs  — Thumbnails, GIFs, filmstrips (generate_gif, generate_thumbs, etc.)
    reports — HTML/PDF report generation (Report class)
    themes  — Unified theme system (Theme, get_theme, apply_plotly_theme)

Usage::

    from geeViz.outputLib import charts as cl
    from geeViz.outputLib import thumbs as tl
    from geeViz.outputLib import reports as rl
    from geeViz.outputLib.themes import get_theme

    # Or import specific functions directly:
    from geeViz.outputLib.charts import summarize_and_chart, save_chart_html
    from geeViz.outputLib.themes import get_theme, Theme
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
