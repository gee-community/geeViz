"""
Example: Generate reports with geeViz outputLib.reports.

Demonstrates building a multi-section report with:
  - Thumbnails (auto-visualized via outputLib.thumbnails, clipped to study area)
  - Animated GIF time-lapses (LCMS Land Cover + MTBS burn severity)
  - Stacked area charts and Sankey transition diagrams
  - Charts and data tables (via outputLib.charting)
  - LLM-generated narratives (via Gemini)
  - Fully parallel EE data + narrative requests
  - Dark and light themes
  - HTML, PDF, and Markdown output formats

Requirements:
  - geeViz with outputLib (reports, thumbnails, charting)
  - GOOGLE_API_KEY in environment or geeViz/.env
  - For PDF: pip install pdfkit + wkhtmltopdf installed

Copyright 2026 Ian Housman

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
"""
# %%
import os
import time

import geeViz.geeView as gv
import geeViz.getImagesLib as gil
import geeViz.getSummaryAreasLib as sal
from geeViz.outputLib import reports as rl

ee = gv.ee
Map = gv.Map
# ---------------------------------------------------------------------------
#  Study area and datasets
# ---------------------------------------------------------------------------
study_area = sal.getUSCounties(
    ee.Geometry.Point([-111.8910, 40.7608])
)
name = ' | '.join(study_area.aggregate_histogram('NAMELSAD').keys().getInfo())


# %%
# LCMS — filter out non-processing and stable classes for cleaner charts
lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")

# MTBS burn severity — select by index and rename for consistent band naming
mtbs = ee.ImageCollection("USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1").select(
    [0], ["Severity"]
)

# Classes to hide in charts (background, non-processing, stable)
HIDDEN_CLASSES = {
    "Background": False,
    "Non-Processing Area Mask": False,
    "Stable": False,
    "Slow Loss": False,
}

startYear = 1990
endYear = 2024

# Sentinel-2 summer composite
s2 = gil.superSimpleGetS2(study_area, "2023-06-01", "2023-09-30")

print("Datasets loaded")

# ---------------------------------------------------------------------------
#  Build the report
# ---------------------------------------------------------------------------
report = rl.Report(
    title=f"{name} Land Assessment",
    header_text="Automated analysis of land cover, land use, and burn severity.",
    theme="dark",
)

# Section 1: LCMS Land Cover — stacked time series + GIF
report.add_section(
    ee_obj=lcms.select(["Land_Cover"]).filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title=f"{name} - LCMS Land Cover",
    chart_types=["stacked_line+markers"],
    class_visible=HIDDEN_CLASSES,
    scale=60,
    thumb_format="gif",
    thumb_dimensions=400,
    thumb_fps=2,
    thumb_burn_in_date=True,
    thumb_date_format="YYYY",
    thumb_date_position="upper-left",
)

# Section 2: LCMS Land Cover Sankey + time series
report.add_section(
    ee_obj=lcms.select(["Land_Cover"]).filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title=f"{name} - LCMS Land Cover Transitions",
    chart_types=["sankey", "stacked_line+markers"],
    class_visible=HIDDEN_CLASSES,
    transition_periods=[1990, 2000, 2010, 2024],
    sankey_band_name="Land_Cover",
    scale=60,
    thumb_format=None,
)

# Section 3: LCMS Land Use — stacked chart (no thumb)
report.add_section(
    ee_obj=lcms.select(["Land_Use"]).filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title=f"{name} - LCMS Land Use",
    chart_types=["stacked_line+markers"],
    class_visible=HIDDEN_CLASSES,
    scale=60,
    thumb_format=None,
)

# Section 4: LCMS Land Use Sankey
report.add_section(
    ee_obj=lcms.select(["Land_Use"]).filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title=f"{name} - LCMS Land Use Transitions",
    chart_types=["sankey"],
    transition_periods=[1990, 2000, 2010, 2024],
    sankey_band_name="Land_Use",
    scale=60,
    thumb_format=None,
)

# Section 5: MTBS Burn Severity — GIF + chart
report.add_section(
    ee_obj=mtbs.filter(ee.Filter.calendarRange(startYear, endYear, "year")),
    geometry=study_area,
    title=f"{name} - MTBS Burn Severity",
    chart_types=["stacked_bar"],
    scale=30,
    generate_table=False,
    thumb_format="gif",
    thumb_dimensions=400,
    thumb_fps=4,
    thumb_burn_in_date=True,
    thumb_date_format="YYYY",
    thumb_date_position="upper-left",
)

# Section 6: Sentinel-2 Composite — thumb only (no chart, no table)
report.add_section(
    ee_obj=s2,
    geometry=study_area,
    title=f"{name} - Sentinel-2 Summer 2023",
    generate_chart=False,
    generate_table=False,
    thumb_viz_params=gil.vizParamsFalse10k,
    thumb_dimensions=400,
)

print(f"\nReport: {report.title}")
print(f"Sections: {len(report._sections)}")
for i, sec in enumerate(report._sections):
    print(
        f"  {i + 1}. {sec.title} "
        f"(table={sec.generate_table}, chart={sec.generate_chart}, "
        f"thumb_format={sec.thumb_format})"
    )

# ---------------------------------------------------------------------------
#  Generate HTML — report layout (dark theme)
# ---------------------------------------------------------------------------
start = time.time()

output_dir = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(output_dir, exist_ok=True)

html_path = report.generate(
    format="html",
    output_path=os.path.join(output_dir, f"{name}_report_dark.html"),
)
print(f"\nHTML (dark, report) generated in {time.time() - start:.1f}s")

# ---------------------------------------------------------------------------
#  Generate HTML — poster layout (dark theme, landscape multi-column)
# ---------------------------------------------------------------------------
start = time.time()
report.layout = "poster"
poster_path = report.generate(
    format="html",
    output_path=os.path.join(output_dir, f"{name}_poster_dark.html"),
)
print(f"HTML (dark, poster) generated in {time.time() - start:.1f}s")

# ---------------------------------------------------------------------------
#  Generate HTML — report layout (light theme)
# ---------------------------------------------------------------------------
start = time.time()
report.theme = "light"
report.layout = "report"
html_light_path = report.generate(
    format="html",
    output_path=os.path.join(output_dir, f"{name}_report_light.html"),
)
print(f"HTML (light, report) generated in {time.time() - start:.1f}s")

# ---------------------------------------------------------------------------
#  Generate Markdown
# ---------------------------------------------------------------------------
start = time.time()
md_path = report.generate(
    format="md",
    output_path=os.path.join(output_dir, f"{name}_report.md"),
)
print(f"Markdown generated in {time.time() - start:.1f}s")

# ---------------------------------------------------------------------------
#  Generate PDF — report layout (static charts via kaleido)
# ---------------------------------------------------------------------------
start = time.time()
report.theme = "light"
report.layout = "report"
pdf_path = report.generate(
    format="pdf",
    output_path=os.path.join(output_dir, f"{name}_report.pdf"),
)
print(f"PDF (report) generated in {time.time() - start:.1f}s")

# ---------------------------------------------------------------------------
#  Generate PDF — poster layout (landscape)
# ---------------------------------------------------------------------------
start = time.time()
report.layout = "poster"
pdf_poster_path = report.generate(
    format="pdf",
    output_path=os.path.join(output_dir, f"{name}_poster.pdf"),
)
print(f"PDF (poster) generated in {time.time() - start:.1f}s")

# ---------------------------------------------------------------------------
#  Summary
# ---------------------------------------------------------------------------
meta = report.metadata()
print("\n" + "=" * 60)
print("Report generation complete!")
print("=" * 60)
print(meta.to_string(index=False))

print(f"\nOutputs:")
print(f"  Dark HTML (report): {html_path}")
print(f"  Dark HTML (poster): {poster_path}")
print(f"  Light HTML:         {html_light_path}")
print(f"  Markdown:           {md_path}")
print(f"  PDF (report):       {pdf_path}")
print(f"  PDF (poster):       {pdf_poster_path}")
