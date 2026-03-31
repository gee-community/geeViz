"""
Report: Great Salt Lake Land Cover Change Analysis

Compares LCMS Land Cover and Annual NLCD over the Great Salt Lake area
from 1985-2024. Includes annual stacked charts, animated GIFs, and
Sankey transition diagrams for 1985, 2000, and 2024.
"""
import os
import time

import geeViz.geeView as gv
import geeViz.getImagesLib as gil
from geeViz.outputLib import reports as rl

ee = gv.ee

# ---------------------------------------------------------------------------
#  Study area
# ---------------------------------------------------------------------------
study_area = ee.Geometry.Rectangle(
    [-112.9495548, 40.6773759, -112.1536083, 41.6576681]
)

# ---------------------------------------------------------------------------
#  Datasets
# ---------------------------------------------------------------------------
startYear = 1985
endYear = 2024

# LCMS Land Cover
lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2024-10")

# Annual NLCD Land Cover
nlcd_lc = ee.ImageCollection("projects/sat-io/open-datasets/USGS/ANNUAL_NLCD/LANDCOVER")
nlcd_viz_props = {
    "LC_class_values": [11, 12, 21, 22, 23, 24, 31, 41, 42, 43, 52, 71, 81, 82, 90, 95],
    "LC_class_palette": [
        "466b9f", "d1def8", "dec5c5", "d99282", "eb0000", "ab0000",
        "b3ac9f", "68ab5f", "1c5f2c", "b5c58f", "ccb879", "dfdfc2",
        "dcd939", "ab6c28", "b8d9eb", "6c9fb8",
    ],
    "LC_class_names": [
        "Open Water", "Perennial Ice/Snow", "Developed, Open Space",
        "Developed, Low Intensity", "Developed, Medium Intensity",
        "Developed, High Intensity", "Barren Land", "Deciduous Forest",
        "Evergreen Forest", "Mixed Forest", "Shrub/Scrub",
        "Grassland/Herbaceous", "Pasture/Hay", "Cultivated Crops",
        "Woody Wetlands", "Emergent Herbaceous Wetlands",
    ],
}
nlcd_lc = nlcd_lc.map(lambda img: img.rename("LC").set(nlcd_viz_props))

print("Datasets loaded")

# ---------------------------------------------------------------------------
#  Build the report
# ---------------------------------------------------------------------------
report = rl.Report(
    title="Great Salt Lake Land Cover Change",
    header_text="Comparing LCMS and NLCD land cover products from 1985-2024 over the Great Salt Lake region.",
    theme="dark",
    tone="neutral",
)

# Section 1: LCMS Land Cover - annual stacked chart + GIF
report.add_section(
    ee_obj=lcms.select(["Land_Cover"]).filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title="LCMS Land Cover (1985-2024)",
    chart_types=["stacked_line+markers"],
    scale=60,
    thumb_format="gif",
    thumb_dimensions=400,
    thumb_fps=4,
)

# Section 2: LCMS Land Cover Sankey - transitions at 1985, 2000, 2024
report.add_section(
    ee_obj=lcms.select(["Land_Cover"]).filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title="LCMS Land Cover Transitions",
    chart_types=["sankey"],
    transition_periods=[1985, 2000, 2024],
    sankey_band_name="Land_Cover",
    scale=60,
    thumb_format=None,
)

# Section 3: NLCD Land Cover - annual stacked chart + GIF
report.add_section(
    ee_obj=nlcd_lc.filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title="NLCD Land Cover (1985-2024)",
    chart_types=["stacked_line+markers"],
    scale=30,
    thumb_format="gif",
    thumb_dimensions=400,
    thumb_fps=4,
)

# Section 4: NLCD Land Cover Sankey - transitions at 1985, 2000, 2024
report.add_section(
    ee_obj=nlcd_lc.filter(
        ee.Filter.calendarRange(startYear, endYear, "year")
    ),
    geometry=study_area,
    title="NLCD Land Cover Transitions",
    chart_types=["sankey"],
    transition_periods=[1985, 2000, 2024],
    sankey_band_name="LC",
    scale=30,
    thumb_format=None,
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
    output_path=os.path.join(output_dir, "great_salt_lake_report_dark.html"),
)
print(f"\nHTML (dark) generated in {time.time() - start:.1f}s")

# Light HTML report
start = time.time()
report.theme = "light"
html_light_path = report.generate(
    format="html",
    output_path=os.path.join(output_dir, "great_salt_lake_report_light.html"),
)
print(f"HTML (light) generated in {time.time() - start:.1f}s")

# PDF report
start = time.time()
report.theme = "light"
pdf_path = report.generate(
    format="pdf",
    output_path=os.path.join(output_dir, "great_salt_lake_report.pdf"),
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
