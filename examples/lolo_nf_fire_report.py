"""
Report: Lolo National Forest Fire Trends (1985-2024)

Analyzes fire activity over the Lolo National Forest using:
  - LCMS Change (fast loss / slow loss / gain)
  - LCMS Land Cover (annual stacked chart + GIF)
  - MTBS Burn Severity (annual chart + GIF)
  - Sentinel-2 recent summer composite (thumbnail)
"""
import os
import time

import geeViz.geeView as gv
import geeViz.getImagesLib as gil
import geeViz.getSummaryAreasLib as sal
from geeViz.outputLib import reports as rl

ee = gv.ee

# ---------------------------------------------------------------------------
#  Study area — Lolo National Forest boundary
# ---------------------------------------------------------------------------
lolo_point = ee.Geometry.Point([-113.1569104, 47.1517137])
study_area = sal.getUSFSForests(lolo_point)
thumb_geometry = study_area.geometry().bounds(500)
name = "Lolo National Forest"

# UTM CRS for this location (NAD83 since it's CONUS)
crs = gil.getUTMEpsg(lolo_point, datum="NAD83")
print(f"Using CRS: {crs}")

startYear = 1985
endYear = 2024

# ---------------------------------------------------------------------------
#  Datasets
# ---------------------------------------------------------------------------
# LCMS
lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")

# MTBS burn severity — select by index and rename for consistent band naming
# MTBS burn severity — select by index and rename for consistent band naming
mtbs = ee.ImageCollection("USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1").select(
    [0], ["Severity"]
)

# Classes to hide in charts
HIDDEN_CLASSES = {
    "Background": False,
    "Non-Processing Area Mask": False,
    "Stable": False,
}

# Sentinel-2 summer composite for context thumbnail
s2 = gil.superSimpleGetS2(study_area, "2023-06-01", "2023-09-30")

print("Datasets loaded")

# ---------------------------------------------------------------------------
#  Build the report
# ---------------------------------------------------------------------------
report = rl.Report(
    title=f"{name} — Fire Trends (1985-2024)",
    header_text="Analysis of fire activity, land cover change, and burn severity over the Lolo National Forest.",
    theme="dark",
    tone="neutral",
)

# Section 1: LCMS Change — stacked chart + GIF showing fast/slow loss and gain
report.add_section(
    ee_obj=lcms.select(["Change"]).filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title="LCMS Change (1985-2024)",
    chart_types=["stacked_line+markers"],
    class_visible=HIDDEN_CLASSES,
    scale=60,
    crs=crs,
    thumb_format="gif",
    thumb_geometry=thumb_geometry,
    thumb_dimensions=400,
    thumb_fps=4,
    thumb_burn_in_date=True,
    thumb_date_format="YYYY",
    thumb_date_position="upper-left",
)

# Section 2: LCMS Land Cover — how land cover has shifted over time
report.add_section(
    ee_obj=lcms.select(["Land_Cover"]).filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title="LCMS Land Cover (1985-2024)",
    chart_types=["stacked_line+markers"],
    class_visible=HIDDEN_CLASSES,
    scale=60,
    crs=crs,
    thumb_format="gif",
    thumb_geometry=thumb_geometry,
    thumb_dimensions=400,
    thumb_fps=4,
    thumb_burn_in_date=True,
    thumb_date_format="YYYY",
    thumb_date_position="upper-left",
)

# Section 3: LCMS Land Cover Sankey — transitions at key fire years
report.add_section(
    ee_obj=lcms.select(["Land_Cover"]).filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title="LCMS Land Cover Transitions",
    chart_types=["sankey"],
    transition_periods=[1985, 2000, 2010, 2024],
    sankey_band_name="Land_Cover",
    scale=60,
    crs=crs,
    thumb_format=None,
)

# Section 4: MTBS Burn Severity — annual chart + GIF
report.add_section(
    ee_obj=mtbs.filter(ee.Filter.calendarRange(startYear, endYear, "year")),
    geometry=study_area,
    title="MTBS Burn Severity (1985-2024)",
    scale=30,
    crs=crs,
    thumb_format="gif",
    thumb_geometry=thumb_geometry,
    thumb_dimensions=400,
    thumb_fps=4,
    thumb_burn_in_date=True,
    thumb_date_format="YYYY",
    thumb_date_position="upper-left",
)

# Section 5: Sentinel-2 Composite — recent context thumbnail
report.add_section(
    ee_obj=s2,
    geometry=study_area,
    title=f"{name} — Sentinel-2 Summer 2023",
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
#  Generate outputs
# ---------------------------------------------------------------------------
output_dir = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(output_dir, exist_ok=True)

# Dark HTML report
start = time.time()
html_path = report.generate(
    format="html",
    output_path=os.path.join(output_dir, "lolo_nf_fire_report_dark.html"),
)
print(f"\nHTML (dark) generated in {time.time() - start:.1f}s")

# Light HTML report
start = time.time()
report.theme = "light"
html_light_path = report.generate(
    format="html",
    output_path=os.path.join(output_dir, "lolo_nf_fire_report_light.html"),
)
print(f"HTML (light) generated in {time.time() - start:.1f}s")

# PDF report
start = time.time()
report.theme = "light"
pdf_path = report.generate(
    format="pdf",
    output_path=os.path.join(output_dir, "lolo_nf_fire_report.pdf"),
)
print(f"PDF generated in {time.time() - start:.1f}s")

# ---------------------------------------------------------------------------
#  Summary
# ---------------------------------------------------------------------------
meta = report.metadata()
print("\n" + "=" * 60)
print("Report generation complete!")
print("=" * 60)
print(meta.to_string(index=False))

print(f"\nOutputs:")
print(f"  Dark HTML:  {html_path}")
print(f"  Light HTML: {html_light_path}")
print(f"  PDF:        {pdf_path}")
