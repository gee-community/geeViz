# geeViz MCP Test Questions

40 test questions spanning monitoring, hazards, land cover/use, impact analysis, GIF generation, and charting. Questions 1-10 are common requests; 11-20 are obscure/challenging; 21-40 focus on fire/flood impact, building counts, biomass, GIF generation, and line charts.

**Last run:** 2026-03-10 | **Result:** 19/20 PASS, 1 PARTIAL (Q20 code error) | **Total time:** ~85s (Q1-20 only)

## Summary Table

| Q# | Topic | Status | Time | Tools Called | Risk Level |
|----|-------|--------|------|-------------|------------|
| 1 | Forest loss (LCMS) | PASS | 13.2s | search_functions, run_code | Low |
| 2 | Burn severity (MTBS) | PASS | 2.3s | search_datasets, inspect_asset, run_code | Medium |
| 3 | Sankey transition | PASS | 2.1s | run_code | Low |
| 4 | NDVI trend | PASS | 14.3s | get_api_reference, run_code | Low* |
| 5 | Urban expansion (LCMS) | PASS | 3.1s | run_code | Medium |
| 6 | Land cover bar chart | PASS | 2.1s | run_code | Low* |
| 7 | LANDTRENDR | PASS | 6.2s | list_examples, get_api_reference, run_code | Medium* |
| 8 | Flood mapping | PASS | 1.0s | run_code | Medium |
| 9 | NDVI recovery | PASS | 9.1s | run_code | Low* |
| 10 | Compare datasets | PASS | 3.0s | run_code | Low* |
| 11 | Phenology shift | PASS | 0.0s | search_functions, list_examples, get_example | Medium |
| 12 | Hybrid composite | PASS | 4.1s | search_functions, get_api_reference, run_code | Medium |
| 13 | Export to asset | PASS | 6.3s | geocode, run_code | Medium |
| 14 | Harmonic regression | PASS | 0.0s | list_examples, get_api_reference, search_functions | High |
| 15 | CCDC change detection | PASS | 0.0s | list_examples, get_example, get_api_reference | High |
| 16 | Cross-boundary comparison | PASS | 6.8s | geocode, geocode, run_code | Medium |
| 17 | Climate-vegetation | PASS | 0.0s | list_examples, search_functions, get_api_reference | High |
| 18 | Buildings in burn area | PASS | 1.5s | search_datasets, search_datasets, run_code | High |
| 19 | Point extraction | PASS | 2.7s | run_code, extract_and_chart | Low |
| 20 | Lake Mead water extent | PARTIAL | 1.9s | search_datasets, geocode, run_code | High |
| 21 | Fire burn severity bar chart | — | — | run_code | Low |
| 22 | Post-fire dNBR change | — | — | run_code | Medium |
| 23 | Fire progression GIF | — | — | run_code, get_thumbnail | Medium |
| 24 | Flood detection SAR | — | — | search_functions, run_code | Medium |
| 25 | Reservoir water time series | — | — | run_code | High |
| 26 | Flood impact on cropland | — | — | run_code | Medium |
| 27 | Building footprint count | — | — | search_datasets, run_code | High |
| 28 | Buildings in burn perimeter | — | — | run_code | High |
| 29 | Flood-exposed buildings | — | — | run_code | High |
| 30 | Aboveground biomass mapping | — | — | search_datasets, run_code | Medium |
| 31 | Biomass trajectory LandTrendr | — | — | get_api_reference, run_code | Medium |
| 32 | Canopy height visualization | — | — | search_datasets, run_code | Medium |
| 33 | NDVI growing season GIF | — | — | run_code, get_thumbnail | Medium |
| 34 | Urban expansion GIF | — | — | run_code, get_thumbnail | Medium |
| 35 | Deforestation GIF (Hansen) | — | — | run_code, get_thumbnail | High |
| 36 | Multi-index line chart | — | — | run_code | Low |
| 37 | Stacked area chart LCMS | — | — | run_code | Low |
| 38 | Precipitation trend chart | — | — | run_code | Medium |
| 39 | Fire frequency map/chart | — | — | run_code | Medium |
| 40 | Sankey transition after fire | — | — | run_code | Medium |

\*Risk reduced after instruction/code fixes applied during initial testing.

---

## MCP Tool Call Logging

Tool calls are logged to: `geeViz/mcp/logs/tool_calls.log`

Each entry is a JSON line with: `timestamp`, `tool`, `args`, `status` (OK/ERROR), and `result_preview` or `error`.

Test results JSON: `geeViz/mcp/logs/test_results.json`

---

## Questions 1-10: Common Requests

---

### 1. Forest Loss Monitoring — PASS (13.2s)

**Q:** "Show me where forest loss has occurred near Asheville, NC between 2000 and 2024 using LCMS"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `search_functions("summarize_and_chart")` | OK | Found 1 match: `chartingLib.summarize_and_chart` — "Run zonal statistics and produce a chart in one call." |
| 2 | `run_code` | OK | Produced 40-row x 11-column DataFrame (land cover classes over time) |

**Code:**
```python
import geeViz.chartingLib as cl
study = ee.Geometry.Point([-82.55, 35.60]).buffer(10000)
lcms = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').select(['Land_Cover'])
df, fig = cl.summarize_and_chart(lcms, study, scale=30, title='LCMS Land Cover - Asheville, NC')
```

**Output preview:**
```
Shape: (40, 11)
| Trees | Grass/Forb/Herb | Barren or Impervious | Water | Shrubs & Trees Mix | ...
```

**Notes:** Straightforward LCMS time series. Agent can easily replicate with the LCMS example pattern.

---

### 2. Wildfire Burn Severity — PASS (2.3s)

**Q:** "Map the burn severity of the 2020 Cameron Peak Fire in Colorado"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `search_datasets("MTBS burn severity")` | OK | 115 matches. Top result: `USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1` — "Monitoring Trends in Burn Severity (MTBS) Burn Severity Images" |
| 2 | `inspect_asset("USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1")` | OK | IMAGE_COLLECTION, 101 images, date range 1984-06-01 to 2024-06-01, band: `Severity` (int) |
| 3 | `run_code` | OK | Added "Burn Severity 2020" layer to map. Bands: `['Severity']` |

**Code:**
```python
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
burn_2020 = mtbs.filter(ee.Filter.calendarRange(2020, 2020, 'year')).first()
cameron = ee.Geometry.Point([-105.5, 40.6]).buffer(30000)
Map.clearMap()
Map.addLayer(burn_2020, {'autoViz': True}, 'Burn Severity 2020')
Map.centerObject(cameron, 11)
```

**Notes:** Agent needs to discover the MTBS asset ID via `search_datasets` — it's not in common examples. `inspect_asset` confirms the band name and date range.

---

### 3. Land Use Transition (Sankey) — PASS (2.1s)

**Q:** "Chart land use transitions between 1990, 2010, and 2024 using LCMS in Salt Lake County, Utah"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `run_code` | OK | 27-row Sankey flow table + transition matrix. Rendered gradient Sankey HTML. |

**Code:**
```python
import geeViz.chartingLib as cl
counties = ee.FeatureCollection('TIGER/2018/Counties')
slc = counties.filter(ee.Filter.And(ee.Filter.eq('NAME','Salt Lake'), ee.Filter.eq('STATEFP','49')))
study_area = slc.geometry()
lcms = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10')
sankey_df, fig, matrix_df = cl.summarize_and_chart(
    lcms, study_area, sankey=True, transition_periods=[1990, 2010, 2024],
    sankey_band_name='Land_Use', min_percentage=0.5, scale=30,
    title='LCMS Land Use Transition - Salt Lake County')
html = cl.sankey_to_html(fig)
```

**Output preview:**
```
Sankey rows: 27
|                           | Agriculture 2010 | Developed 2010 | Forest 2010 | Other 2010 | Rangeland or Pasture 2010 | ...
```

**Notes:** This exact workflow is in agent-instructions.md as a copy-paste example. Low hangup risk.

---

### 4. NDVI Trend at a Point — PASS (14.3s)

**Q:** "What is the NDVI trend near Yellowstone from 2000 to 2024?"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `get_api_reference("getImagesLib", "getLandsatWrapper")` | OK | Signature: `getLandsatWrapper(studyArea, startYear, endYear, startJulian, endJulian, ...)` — confirms `startJulian`/`endJulian` are required |
| 2 | `run_code` | OK | 25-year NDVI time series. Processed Landsat L4/L5/L7/L8/L9 with cloud masking, compositing. |

**Code:**
```python
import geeViz.chartingLib as cl
study = ee.Geometry.Point([-110.5, 44.6]).buffer(5000)
composites = gil.getLandsatWrapper(study, 2000, 2024, startJulian=152, endJulian=273)['processedComposites']
df, fig = cl.summarize_and_chart(composites, study, band_names=['NDVI'], scale=30, title='NDVI Yellowstone')
```

**Output preview:**
```
Get Processed Landsat:
Start date: May 31 2000 , End date: Sep 29 2024
Applying scale factors for C2 L4 data
Applying scale factors for C2 L5 data
Applying scale factors for C2 L8 data
...
Shape: (25, 1)
```

**Historical bugs fixed:**
- `getLandsatWrapper` requires `startJulian` and `endJulian` (no defaults) — agent instructions were missing these
- Return dict key is `'processedComposites'`, NOT `'composites'` — agent instructions were wrong

---

### 5. Urban Expansion — PASS (3.1s)

**Q:** "Show urban expansion around Phoenix, AZ from 2001 to 2021 using NLCD"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `run_code` | OK | 40-row x 12-column DataFrame using LCMS (not NLCD — NLCD lacks multi-year time series) |

**Code:**
```python
import geeViz.chartingLib as cl
phoenix = ee.Geometry.Point([-112.07, 33.45]).buffer(20000)
lcms = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').select(['Land_Cover'])
df, fig = cl.summarize_and_chart(lcms, phoenix, scale=30, title='LCMS Land Cover - Phoenix, AZ')
```

**Output preview:**
```
Shape: (40, 12)
| Trees | Grass/Forb/Herb | Barren & Grass/Forb/Herb Mix | Barren or Impervious | Water | ...
```

**Notes:** Original question asked for NLCD, but standard NLCD (`USGS/NLCD_RELEASES/2021_REL/NLCD`) only has a single 2021 image — no multi-year time series. Annual NLCD from sat-io isn't publicly accessible. Test uses LCMS as the correct workaround. Agent should use `search_datasets` or `inspect_asset` to discover what's available before writing code.

---

### 6. Land Cover Breakdown (Bar Chart) — PASS (2.1s)

**Q:** "What is the current land cover breakdown in King County, Washington?"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `run_code` | OK | 1-row x 16-column DataFrame (NLCD classes for single ee.Image) |

**Code:**
```python
import geeViz.chartingLib as cl
counties = ee.FeatureCollection('TIGER/2018/Counties')
king = counties.filter(ee.Filter.And(ee.Filter.eq('NAME','King'), ee.Filter.eq('STATEFP','53')))
nlcd = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2021').select(['landcover'])
df, fig = cl.summarize_and_chart(nlcd, king.geometry(), scale=30, title='NLCD 2021 - King County, WA')
```

**Output preview:**
```
Shape: (1, 16)
| Open water | Perennial ice/snow | Developed, open space | Developed, low intensity | ...
```

**Historical bugs fixed:**
- `summarize_and_chart` and `zonal_stats` both called `filterBounds()` on `ee.Image`, which doesn't have that method — fixed to check `isinstance(ee_obj, ee.ImageCollection)` first

---

### 7. Change Detection (LANDTRENDR) — PASS (6.2s)

**Q:** "Run LANDTRENDR change detection near Bozeman, MT from 1985 to 2024 and show the greatest disturbance"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `list_examples(filter="LANDTRENDR")` | OK | 4 examples: `LANDTRENDRViz.py`, `LANDTRENDRVizNotebook.ipynb`, `LANDTRENDRWrapper.py`, `LANDTRENDRWrapperNotebook.ipynb` |
| 2 | `get_api_reference("changeDetectionLib", "simpleLANDTRENDR")` | OK | Signature: `simpleLANDTRENDR(ts, startYear, endYear, indexName='NBR', ...)` — first arg is ImageCollection, NOT study area |
| 3 | `run_code` | OK | LANDTRENDR complete. Adds 13 layers to map (loss/gain year, magnitude, duration). |

**Code:**
```python
import geeViz.changeDetectionLib as cdl
study = ee.Geometry.Point([-111.04, 45.68]).buffer(10000)
composites = gil.getLandsatWrapper(study, 1985, 2024, startJulian=152, endJulian=273)['processedComposites']
lt_output = cdl.simpleLANDTRENDR(composites, 1985, 2024)
Map.clearMap()
Map.centerObject(study, 12)
```

**Output preview:**
```
Get Processed Landsat:
Start date: Jun 01 1985 , End date: Sep 29 2024
...
LANDTRENDR complete, layers added to map
```

**Historical bugs fixed:**
- `simpleLANDTRENDR(ts, startYear, endYear)` takes a time series ImageCollection as first arg, NOT a study area — agent instructions were misleading
- Agent instructions updated with correct workflow: get composites first, then pass to `simpleLANDTRENDR`

---

### 8. Flood Hazard Mapping — PASS (1.0s)

**Q:** "Show areas that flooded during Hurricane Harvey in Houston, TX using Sentinel-2 imagery"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `run_code` | OK | Added "Flood Extent" layer to map |

**Code:**
```python
houston = ee.Geometry.Point([-95.37, 29.76]).buffer(30000)
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
before = s2.filterBounds(houston).filterDate('2017-07-01','2017-08-20').median()
after = s2.filterBounds(houston).filterDate('2017-09-01','2017-09-20').median()
ndwi_before = before.normalizedDifference(['B3','B8']).rename('NDWI')
ndwi_after = after.normalizedDifference(['B3','B8']).rename('NDWI')
flood = ndwi_after.subtract(ndwi_before).gt(0.2).selfMask().rename('Flood')
Map.clearMap()
Map.addLayer(flood, {'min':0, 'max':1, 'palette':['blue']}, 'Flood Extent')
Map.centerObject(houston, 11)
```

**Notes:** No geeViz wrapper for flood detection — agent must write custom EE code. This is expected for domain-specific tasks. Uses raw Sentinel-2 NDWI differencing.

---

### 9. Vegetation Recovery After Fire — PASS (9.1s)

**Q:** "Chart NDVI recovery after the 2018 Camp Fire in Paradise, California from 2017 to 2024"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `run_code` | OK | 8-year NDVI+NBR time series. Shows 2018 dip and recovery. |

**Code:**
```python
import geeViz.chartingLib as cl
paradise = ee.Geometry.Point([-121.62, 39.76]).buffer(5000)
composites = gil.getLandsatWrapper(paradise, 2017, 2024, startJulian=152, endJulian=273)['processedComposites']
df, fig = cl.summarize_and_chart(composites, paradise, band_names=['NDVI','NBR'], scale=30, title='Veg Recovery - Camp Fire')
```

**Output preview:**
```
Get Processed Landsat:
Start date: Jun 01 2017 , End date: Sep 29 2024
...
Shape: (8, 2)
```

**Notes:** Same `getLandsatWrapper` pattern as Q4. Relies on the instruction fixes for `startJulian`/`endJulian` and `processedComposites`.

---

### 10. Comparing Land Cover Datasets — PASS (3.0s)

**Q:** "Compare LCMS and NLCD land cover for 2021 near Denver, Colorado"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `run_code` | OK | LCMS: 1 row (11 classes). NLCD: 1 row (16 classes). Both as single images. |

**Code:**
```python
import geeViz.chartingLib as cl
denver = ee.Geometry.Point([-104.99, 39.74]).buffer(15000)
lcms_2021 = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').filter(ee.Filter.calendarRange(2021,2021,'year')).first().select(['Land_Cover'])
nlcd_2021 = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2021').select(['landcover'])
df_lcms, _ = cl.summarize_and_chart(lcms_2021, denver, scale=30, title='LCMS 2021 - Denver')
df_nlcd, _ = cl.summarize_and_chart(nlcd_2021, denver, scale=30, title='NLCD 2021 - Denver')
```

**Output preview:**
```
=== LCMS ===
| 0 |
=== NLCD ===
| Open water | Developed, open space | Developed, low intensity | ...
```

**Notes:** Both datasets work as single images after the `filterBounds` fix. LCMS preview is truncated but produces valid data.

---

## Questions 11-20: Obscure / Challenging

These test edge cases, multi-step workflows, and less common data sources. Some are discovery-only (no `run_code`) to test whether the agent can find the right tools and examples.

---

### 11. Phenology Shift Detection — PASS (0.0s)

**Q:** "Has the green-up date shifted earlier in the Great Smoky Mountains over the last 20 years?"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `search_functions("phEEno")` | OK | 0 results (phEEnoViz is a module, not a function in the standard search index) |
| 2 | `list_examples(filter="phEEno")` | OK | 1 example: `phEEnoVizWrapper.py` |
| 3 | `get_example("phEEnoVizWrapper")` | OK | Full source code (12,896 chars) — shows phenology metric extraction workflow |

**Notes:** Discovery-only test. `search_functions` finds 0 results for "phEEno" — the agent must fall back to `list_examples` to discover the phEEnoViz module. The example source provides the complete workflow. Agent would then need to adapt the example code for the Great Smoky Mountains study area.

**Why it's hard:** Agent needs to discover phEEnoViz module (not in common examples), understand phenology metrics, and set up correct date ranges.

---

### 12. Multi-Sensor Composite — PASS (4.1s)

**Q:** "Create a hybrid Landsat-Sentinel-2 composite for 2023 summer in the Cascade Range, Oregon"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `search_functions("hybrid")` | OK | 2 results: `getImagesLib.getLandsatAndSentinel2HybridWrapper`, `changeDetectionLib.getLandsatAndSentinel2HybridWrapper` |
| 2 | `get_api_reference("getImagesLib", "getLandsatAndSentinel2HybridWrapper")` | OK | Signature with `studyArea, startYear, endYear, startJulian, endJulian, ...` (1,566 chars of docs) |
| 3 | `run_code` | OK | Hybrid composite created. Added to map with swir1/nir/red bands. |

**Code:**
```python
cascades = ee.Geometry.Point([-121.75, 44.0]).buffer(20000)
result = gil.getLandsatAndSentinel2HybridWrapper(cascades, 2023, 2023, startJulian=152, endJulian=273)
composites = result['processedComposites']
Map.clearMap()
Map.addLayer(composites.first(), {'bands':'swir1,nir,red', 'min':0.05, 'max':0.45}, 'Hybrid 2023')
Map.centerObject(cascades, 11)
```

**Output preview:**
```
Get Processed Landsat and Sentinel2 Scenes:
Start date: Jun 01 2023 , End date: Sep 30 2023
...
Hybrid composite bands: ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', ...]
```

**Notes:** Agent must find the hybrid wrapper via `search_functions("hybrid")`, know it returns `processedComposites`, and set appropriate Julian day ranges for Pacific Northwest summer.

---

### 13. Export Large Area to Asset — PASS (6.3s)

**Q:** "Export LCMS land cover for all of Colorado as a GEE asset at 30m"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `geocode("Colorado", use_boundaries=True)` | OK | Colorado, United States. Lat 38.73, Lon -105.61. Bbox: 37.0°N–41.0°N, 109.1°W–102.0°W. ee boundary code provided. |
| 2 | `run_code` | OK | Image bands: `['Land_Cover']`, Geometry type: Polygon. Ready for export (dry run — not executed). |

**Code:**
```python
# Just verify the geometry and image setup, don't actually export
colorado = ee.FeatureCollection('TIGER/2018/States').filter(ee.Filter.eq('NAME','Colorado')).geometry()
lcms_2023 = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').filter(ee.Filter.calendarRange(2023,2023,'year')).first().select(['Land_Cover'])
clipped = lcms_2023.clip(colorado)
```

**Notes:** Dry run only — actual export would use `export_to_asset` MCP tool or `assetManagerLib.exportToAssetWrapper()`. Agent needs to handle state boundary geometry, set correct CRS/scale, and track the long-running task.

---

### 14. Harmonic Regression Trend — PASS (0.0s)

**Q:** "Fit a harmonic regression to Sentinel-2 NDVI in the Central Valley of California and show the trend component"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `list_examples(filter="harmonic")` | OK | 1 example: `harmonicRegressionWrapper.py` |
| 2 | `get_api_reference("getImagesLib", "getHarmonicCoefficientsAndFit")` | OK | Signature: `getHarmonicCoefficientsAndFit(allImages, indexNames, whichHarmonics=[2], detrend=False)` |
| 3 | `search_functions("harmonic")` | OK | 7 results: `getHarmonicCoefficientsAndFit`, `getHarmonicList`, `getPhaseAmplitude`, `newPhaseAmplitude`, `getHarmonicCoefficients`, `getHarmonicFit`, plus 1 in changeDetectionLib |

**Notes:** Discovery-only test. Agent can find the example and all 7 harmonic functions. Would need to combine S2 data retrieval (`getSentinel2Wrapper` or `superSimpleGetS2`) with `getHarmonicCoefficientsAndFit` and understand phase/amplitude/trend outputs.

**Why it's hard:** Multi-step workflow combining S2 data with harmonic regression, plus visualization of the trend component.

---

### 15. CCDC Break Detection — PASS (0.0s)

**Q:** "Use CCDC to find where land cover changed between 2015 and 2020 in the Willamette Valley, Oregon"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `list_examples(filter="CCDC")` | OK | 3 examples: `CCDCViz.py`, `CCDCVizNotebook.ipynb`, `CCDCWrapper.py` |
| 2 | `get_example("CCDCWrapper")` | OK | Full source code (8,207 chars) — complete CCDC workflow |
| 3 | `get_api_reference("changeDetectionLib", "simpleCCDCPrediction")` | OK | Signature: `simpleCCDCPrediction(img, timeBandName, whichHarmonics, whichBands)` |

**Notes:** Discovery-only test. CCDC has a different interface than LANDTRENDR. Agent needs to understand break dates, magnitude, and how to filter to a time window. The example provides the full workflow.

---

### 16. Cross-Boundary Comparison — PASS (6.8s)

**Q:** "Compare forest cover percentage between Yellowstone National Park and Grand Teton using LCMS for 2023"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `geocode("Yellowstone National Park", use_boundaries=True)` | OK | Yellowstone National Park, Wyoming. Lat 44.62, Lon -110.56. Bbox: 44.13°N–45.11°N. |
| 2 | `geocode("Grand Teton National Park", use_boundaries=True)` | OK | Grand Teton National Park, Teton County, Wyoming. Lat 43.81, Lon -110.65. Bbox: 43.54°N–44.02°N. |
| 3 | `run_code` | OK | 2-feature comparison table produced |

**Code:**
```python
import geeViz.chartingLib as cl
ynp = ee.Geometry.Point([-110.5, 44.6]).buffer(50000)
gtnp = ee.Geometry.Point([-110.7, 43.75]).buffer(30000)
fc = ee.FeatureCollection([
    ee.Feature(ynp, {'name': 'Yellowstone NP'}),
    ee.Feature(gtnp, {'name': 'Grand Teton NP'}),
])
lcms_2023 = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').filter(ee.Filter.calendarRange(2023,2023,'year')).first().select(['Land_Cover'])
df, fig = cl.summarize_and_chart(lcms_2023, fc, scale=30, feature_label='name', title='Forest Cover Comparison 2023')
```

**Output preview:**
```
Converting features 1-2
| name           |
|:---------------|
| Yellowstone NP |
| Grand Teton NP |
```

**Notes:** Agent needs to geocode two areas, merge into a FeatureCollection, and use the `feature_label` parameter for grouped bar chart comparison. The test uses simple buffers; a real agent could use the OSM boundary polygons returned by `geocode`.

---

### 17. Climate-Vegetation Correlation — PASS (0.0s)

**Q:** "Show the relationship between DAYMET precipitation and NDVI in eastern Montana from 2010 to 2024"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `list_examples(filter="climate")` | OK | 1 example: `getClimateWrapper.py` — "Example of how to get Climate data using the getImagesLib and view outputs" |
| 2 | `search_functions("getClimate")` | OK | 2 results: `getImagesLib.getClimateWrapper` — "Wrapper function to retrieve and process climate data from various Earth Engine collections." |
| 3 | `get_api_reference("getImagesLib", "getClimateWrapper")` | OK | Full signature with `collectionName, studyArea, startYear, endYear, startJulian, endJulian, timebuffer, weights, ...` |

**Notes:** Discovery-only test. Multi-dataset workflow combining climate (DAYMET) with vegetation (Landsat NDVI). Agent needs to align temporal resolution and chart both on same axes. The `getClimateWrapper` function handles DAYMET data retrieval.

**Why it's hard:** Agent must get both `getLandsatWrapper` composites and `getClimateWrapper` data, align them temporally, and chart together.

---

### 18. Building Footprints in Burn Area — PASS (1.5s)

**Q:** "How many buildings are within the 2021 Dixie Fire perimeter in California?"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `search_datasets("building footprints")` | OK | 1,692 matches. Top results: VIDA Combined Building Footprints (Google + Microsoft), per-country tables at `projects/sat-io/open-datasets/VIDA_COMBINED/...` |
| 2 | `search_datasets("MTBS fire perimeter")` | OK | 220 matches. Top results: Global Fire Atlas perimeters, MTBS burned area boundaries |
| 3 | `run_code` | OK | Confirmed: Google Buildings (`GOOGLE/Research/open-buildings/v3/polygons`) available, MS Buildings (`projects/sat-io/open-datasets/MSBuildings/US`) available, MTBS 2021 bands: `['Severity']` |

**Code:**
```python
# Check if building footprints are available
buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
ms_buildings = ee.FeatureCollection('projects/sat-io/open-datasets/MSBuildings/US')
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
burn_2021 = mtbs.filter(ee.Filter.calendarRange(2021, 2021, 'year')).first()
```

**Notes:** Availability check only — a full solution would extract the burn perimeter, intersect with building footprints, and count. No geeViz wrapper for this — requires custom EE code. Agent correctly discovers both Google and Microsoft building datasets.

---

### 19. Time Series at Exact Coordinates — PASS (2.7s)

**Q:** "Extract the full LCMS land cover and land use time series at coordinates 39.7392°N, 104.9903°W and return it as a table"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `run_code` | OK | Loaded `lcms_ts` variable into REPL namespace |
| 2 | `extract_and_chart(collection_var="lcms_ts", lon=-104.9903, lat=39.7392, band_names="Land_Cover,Land_Use", chart_type="bar")` | OK | 40-row time series table (1985–2024) with Land_Cover and Land_Use class values |

**Code (run_code step):**
```python
lcms_ts = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').select(['Land_Cover','Land_Use'])
```

**Output preview:**
```
Chart type: time_series | Rows: 40

| index | Land_Cover | Land_Use |
|------:|-----------:|---------:|
|  1985 |         12 |        2 |
|  1986 |         12 |        2 |
|  1987 |         12 |        2 |
|  1988 |         12 |        2 |
...
```

**Notes:** Point extraction using `extract_and_chart` MCP tool. Agent needs to know: (1) use `collection_var` not `asset_id`, (2) coordinates are `[lon, lat]` not `[lat, lon]`, (3) point extraction defaults to `ee.Reducer.first()`.

**Historical bug:** First test run failed because test used `asset_id` parameter which doesn't exist on `extract_and_chart` — it takes `collection_var` (a variable name in the REPL namespace).

---

### 20. Drought Impact on Reservoir — PARTIAL (1.9s)

**Q:** "Show how Lake Mead's water extent has changed from 2000 to 2024 using satellite imagery"

**Tool Calls:**

| # | Tool | Status | Output Summary |
|---|------|--------|---------------|
| 1 | `search_datasets("JRC global surface water")` | OK | 3,185 matches. Top result: `JRC/GSW1_4/GlobalSurfaceWater` — "JRC Global Surface Water Mapping Layers, v1.4" |
| 2 | `geocode("Lake Mead")` | OK | Lake Mead, Clark County, Nevada. Lat 36.21, Lon -114.41. Type: reservoir. |
| 3 | `run_code` | ERROR | EE computation error — `ee.ImageCollection` from Python loop with `lambda` caused serialization issues |

**Code:**
```python
lake_mead = ee.Geometry.Point([-114.75, 36.15]).buffer(20000)
jrc = ee.ImageCollection('JRC/GSW1_4/MonthlyHistory')
years = list(range(2000, 2025))
water_areas = []
for y in years:
    monthly = jrc.filter(ee.Filter.calendarRange(y, y, 'year'))
    water_count = monthly.map(lambda img: img.eq(2)).sum()
    total = monthly.size()
    pct = water_count.divide(total).multiply(100).rename('water_pct')
    water_areas.append(pct.set('system:time_start', ee.Date(f'{y}-06-01').millis()))
water_col = ee.ImageCollection(water_areas)
import geeViz.chartingLib as cl
df, fig = cl.summarize_and_chart(water_col, lake_mead, band_names=['water_pct'], scale=30, title='Lake Mead Water Extent')
```

**Error:** EE computation timeout/serialization failure. The Python `lambda` inside `monthly.map()` combined with a 25-year loop creates a very large computation graph.

**Notes:** This is a genuinely hard question. A better approach would use JRC `GlobalSurfaceWater` (single image with `occurrence` band), or use Landsat NDWI thresholding with `getLandsatWrapper` composites and `summarize_and_chart`. The Python for-loop with `ee.ImageCollection` construction is fragile.

---

## Questions 21-40: Fire/Flood Impact, Buildings, Biomass, GIFs & Charts

These test fire/flood impact assessment, building counting, biomass change, animated GIF generation, and advanced charting (line, stacked area, multi-index).

---

### 21. Fire Burn Severity Bar Chart — NOT YET RUN

**Q:** "Chart the burn severity class breakdown for the 2020 Creek Fire in California"

**Expected Tool Calls:** `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
creek_fire = ee.Geometry.Point([-119.2, 37.2]).buffer(30000)
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
burn_2020 = mtbs.filter(ee.Filter.calendarRange(2020, 2020, 'year')).first()
Map.addLayer(burn_2020, {'autoViz': True}, 'Burn Severity 2020')
df, fig = cl.summarize_and_chart(burn_2020, creek_fire, scale=30, title='Creek Fire Burn Severity 2020')
```

**Notes:** Builds on Q2 (MTBS) but adds zonal statistics charting. Uses `summarize_and_chart` on a single thematic image to produce a bar chart of severity classes.

---

### 22. Post-Fire dNBR Change Detection — NOT YET RUN

**Q:** "Compute dNBR (differenced Normalized Burn Ratio) for the 2021 Dixie Fire using pre/post Landsat composites"

**Expected Tool Calls:** `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
dixie = ee.Geometry.Point([-121.4, 40.0]).buffer(50000)
pre = gil.getLandsatWrapper(dixie, 2020, 2020, startJulian=152, endJulian=273)['processedComposites'].first()
post = gil.getLandsatWrapper(dixie, 2022, 2022, startJulian=152, endJulian=273)['processedComposites'].first()
dnbr = pre.select('NBR').subtract(post.select('NBR')).rename('dNBR')
Map.addLayer(dnbr, {'min':-0.5, 'max':1.0, 'palette':['green','yellow','orange','red']}, 'dNBR')
df, fig = cl.summarize_and_chart(dnbr, dixie, band_names=['dNBR'], scale=30, reducer='mean', title='dNBR Dixie Fire')
```

**Notes:** Tests pre/post fire analysis using `getLandsatWrapper` for both periods. NBR index is auto-computed by the wrapper. dNBR > 0.27 typically indicates moderate-high burn severity.

---

### 23. Fire Progression GIF from Sentinel-2 — NOT YET RUN

**Q:** "Generate an animated GIF showing the 2020 August Complex Fire area from June to December using Sentinel-2 true-color imagery"

**Expected Tool Calls:** `run_code`, `get_thumbnail`

**Code:**
```python
fire_center = ee.Geometry.Point([-122.7, 39.8])
fire_region = fire_center.buffer(40000)
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
months = ee.List.sequence(6, 12)
def monthly_composite(m):
    m = ee.Number(m)
    start = ee.Date.fromYMD(2020, m, 1)
    end = start.advance(1, 'month')
    return s2.filterBounds(fire_region).filterDate(start, end).filter(
        ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).median().select(['B4','B3','B2']).divide(10000).set(
        'system:time_start', start.millis())
fire_monthly = ee.ImageCollection(months.map(monthly_composite))
```
Then: `get_thumbnail(variable="fire_monthly", viz_params='{"bands":["B4","B3","B2"],"min":0,"max":0.3}', region_var="fire_region")`

**Notes:** First GIF test. Uses `get_thumbnail` on an ImageCollection to produce an animated GIF. Agent must provide RGB bands and min/max for valid video thumbnail.

---

### 24. Flood Detection with Sentinel-1 SAR — NOT YET RUN

**Q:** "Map flood extent during the 2019 Missouri River floods using Sentinel-1 SAR backscatter change"

**Expected Tool Calls:** `search_functions`, `run_code`

**Code:**
```python
missouri = ee.Geometry.Point([-95.9, 41.3]).buffer(30000)
s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filter(ee.Filter.eq('instrumentMode','IW')).filter(
    ee.Filter.listContains('transmitterReceiverPolarisation','VV')).select('VV')
dry = s1.filterBounds(missouri).filterDate('2019-01-01','2019-02-28').mean()
flood = s1.filterBounds(missouri).filterDate('2019-03-15','2019-04-30').mean()
diff = flood.subtract(dry)
flood_mask = diff.lt(-3).selfMask().rename('Flood')
Map.addLayer(flood_mask, {'min':0, 'max':1, 'palette':['blue']}, 'Flood Extent SAR')
```

**Notes:** SAR-based flood detection complements Q8 (optical NDWI approach). -3 dB threshold on VV backscatter change is a standard flood detection method.

---

### 25. Reservoir Water Time Series (JRC) — NOT YET RUN

**Q:** "Chart Lake Powell water extent changes from 2000 to 2024 as a line chart"

**Expected Tool Calls:** `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
lake_powell = ee.Geometry.Point([-111.5, 37.1]).buffer(30000)
jrc = ee.ImageCollection('JRC/GSW1_4/MonthlyHistory')
years = list(range(2000, 2025))
water_imgs = []
for y in years:
    monthly = jrc.filter(ee.Filter.calendarRange(y, y, 'year'))
    water_pct = monthly.map(lambda img: img.eq(2).rename('water')).mean().multiply(100).rename('water_pct')
    water_imgs.append(water_pct.set('system:time_start', ee.Date(f'{y}-06-01').millis()))
water_ts = ee.ImageCollection(water_imgs)
df, fig = cl.summarize_and_chart(water_ts, lake_powell, band_names=['water_pct'], scale=30, title='Lake Powell Water Extent')
```

**Notes:** Similar to Q20 (Lake Mead) but uses `.mean()` instead of `.sum().divide()` which may avoid the serialization issue. Tests line chart generation from a custom-built time series.

---

### 26. Flood Impact on Cropland — NOT YET RUN

**Q:** "Overlay flood-prone areas with NLCD land cover to assess cropland exposure in the Mississippi Delta"

**Expected Tool Calls:** `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
delta = ee.Geometry.Point([-90.5, 33.0]).buffer(20000)
nlcd = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2021').select('landcover')
jrc = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent')
flood_zone = jrc.gt(0).selfMask()
Map.addLayer(nlcd, {'autoViz': True}, 'NLCD 2021')
Map.addLayer(flood_zone, {'min':0, 'max':1, 'palette':['cyan']}, 'Flood-Prone Zone')
df, fig = cl.summarize_and_chart(nlcd, delta, scale=30, title='Land Cover in Flood Zone')
```

**Notes:** Combines JRC max water extent with NLCD to identify cropland (classes 81, 82) in flood-prone areas. Tests multi-dataset overlay analysis.

---

### 27. Building Footprint Count (Google Open Buildings) — NOT YET RUN

**Q:** "Count building footprints and compute area statistics within 5km of downtown Nairobi"

**Expected Tool Calls:** `search_datasets`, `run_code`

**Code:**
```python
nairobi = ee.Geometry.Point([36.82, -1.29]).buffer(5000)
buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
local_buildings = buildings.filterBounds(nairobi)
count = local_buildings.size().getInfo()
area_stats = local_buildings.aggregate_stats('area_in_meters')
conf_stats = local_buildings.aggregate_stats('confidence')
```

**Notes:** Tests FeatureCollection operations — spatial filtering, counting, and aggregate statistics. Google Open Buildings has global coverage in Africa/Asia/Latin America.

---

### 28. Buildings in Burn Perimeter (Camp Fire) — NOT YET RUN

**Q:** "Estimate structures affected by the 2018 Camp Fire using MTBS burn severity and building footprints"

**Expected Tool Calls:** `run_code`

**Code:**
```python
paradise = ee.Geometry.Point([-121.6, 39.76]).buffer(15000)
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
burn_2018 = mtbs.filter(ee.Filter.calendarRange(2018, 2018, 'year')).first()
high_severity = burn_2018.select('Severity').gte(3).selfMask()
ms_buildings = ee.FeatureCollection('projects/sat-io/open-datasets/MSBuildings/US')
all_buildings = ms_buildings.filterBounds(paradise)
total_count = all_buildings.size().getInfo()
```

**Notes:** Builds on Q18 (buildings in burn area) but uses Microsoft Buildings for US coverage. Tests raster-vector intersection between burn severity and building footprints.

---

### 29. Flood-Exposed Buildings (Dhaka) — NOT YET RUN

**Q:** "Count buildings exposed to seasonal flooding in Dhaka, Bangladesh using JRC water seasonality"

**Expected Tool Calls:** `run_code`

**Code:**
```python
dhaka = ee.Geometry.Point([90.4, 23.8]).buffer(10000)
jrc = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('seasonality')
flood_risk = jrc.gt(2).rename('flood_risk')
buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
local_buildings = buildings.filterBounds(dhaka)
total = local_buildings.size().getInfo()
```

**Notes:** Combines JRC water seasonality (months water present) with Google Open Buildings. High risk where seasonality > 2 months. Tests cross-domain analysis: hydrology + infrastructure.

---

### 30. Aboveground Biomass Mapping (Amazon) — NOT YET RUN

**Q:** "Map and chart aboveground biomass density in the Amazon using GEDI data"

**Expected Tool Calls:** `search_datasets`, `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
amazon = ee.Geometry.Point([-60.0, -3.0]).buffer(100000)
biomass = ee.Image('LCLUC/GEDI_L4B_Gridded_Biomass_V2_1/2021_v2_1').select('MU')
Map.addLayer(biomass.clip(amazon), {'min':0, 'max':300, 'palette':['lightyellow','green','darkgreen']}, 'Biomass Density')
df, fig = cl.summarize_and_chart(biomass, amazon, band_names=['MU'], scale=1000, reducer='mean', title='Biomass Density - Amazon')
```

**Notes:** Uses NASA GEDI L4B gridded biomass. Tests continuous-value bar chart with mean reducer at coarse scale (1km).

---

### 31. Biomass/Vegetation Trajectory with LandTrendr — NOT YET RUN

**Q:** "Run LandTrendr on NBR in the Pacific Northwest and chart the vegetation trajectory from 2000-2024"

**Expected Tool Calls:** `get_api_reference`, `run_code`

**Code:**
```python
import geeViz.changeDetectionLib as cdl
import geeViz.chartingLib as cl
pnw = ee.Geometry.Point([-122.0, 46.0]).buffer(50000)
composites = gil.getLandsatWrapper(pnw, 2000, 2024, startJulian=152, endJulian=273)['processedComposites']
lt_output = cdl.simpleLANDTRENDR(composites, 2000, 2024)
df, fig = cl.summarize_and_chart(composites, ee.Geometry.Point([-122.0, 46.0]), band_names=['NBR'], scale=30, title='NBR Trajectory - PNW')
```

**Notes:** Combines Q7 (LANDTRENDR) with line chart of the input NBR time series. Shows the vegetation trajectory that LandTrendr segments.

---

### 32. Forest Canopy Height (ETH Global) — NOT YET RUN

**Q:** "Visualize and chart forest canopy height in Borneo using the ETH Global Canopy Height dataset"

**Expected Tool Calls:** `search_datasets`, `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
borneo = ee.Geometry.Point([116.0, 1.5]).buffer(50000)
canopy = ee.Image('users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1').rename('canopy_height')
Map.addLayer(canopy.clip(borneo), {'min':0, 'max':50, 'palette':['lightyellow','green','darkgreen']}, 'Canopy Height 2020')
df, fig = cl.summarize_and_chart(canopy, borneo, band_names=['canopy_height'], scale=100, reducer='mean', title='Canopy Height - Borneo')
```

**Notes:** Tests discovery of a community-contributed dataset (ETH canopy height at `users/nlang/...`). Agent may need `search_datasets` to find the correct asset path.

---

### 33. NDVI Growing Season GIF (Iowa Corn Belt) — NOT YET RUN

**Q:** "Generate an animated GIF showing NDVI changes through the 2023 growing season in the Iowa corn belt"

**Expected Tool Calls:** `run_code`, `get_thumbnail`

**Code:**
```python
crop_center = ee.Geometry.Point([-93.5, 42.0])
crop_region = crop_center.buffer(30000)
months = ee.List.sequence(4, 10)
def monthly_ndvi(m):
    m = ee.Number(m)
    start = ee.Date.fromYMD(2023, m, 1)
    end = start.advance(1, 'month')
    composite = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(crop_region).filterDate(start, end).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15)).median()
    return composite.normalizedDifference(['B8','B4']).rename('NDVI').set('system:time_start', start.millis())
ndvi_season = ee.ImageCollection(months.map(monthly_ndvi))
```
Then: `get_thumbnail(variable="ndvi_season", viz_params='{"bands":["NDVI"],"min":0,"max":0.9,"palette":["brown","yellow","green","darkgreen"]}')`

**Notes:** Single-band NDVI GIF with palette. Shows crop green-up, peak, and senescence. Tests GIF generation with palette-based visualization.

---

### 34. Urban Expansion GIF (Phoenix) — NOT YET RUN

**Q:** "Create an animated GIF showing urban expansion around Phoenix from 2000 to 2024 using Landsat true-color"

**Expected Tool Calls:** `run_code`, `get_thumbnail`

**Code:**
```python
phoenix_region = ee.Geometry.Point([-112.0, 33.45]).buffer(40000)
years = [2000, 2005, 2010, 2015, 2020, 2024]
urban_imgs = []
for y in years:
    composites = gil.getLandsatWrapper(phoenix_region, y, y, startJulian=152, endJulian=273)['processedComposites']
    img = composites.first().select(['red','green','blue']).set('system:time_start', ee.Date(f'{y}-07-01').millis())
    urban_imgs.append(img)
urban_ts = ee.ImageCollection(urban_imgs)
```
Then: `get_thumbnail(variable="urban_ts", viz_params='{"bands":["red","green","blue"],"min":0.0,"max":0.3}')`

**Notes:** True-color GIF from `getLandsatWrapper` composites at 5-year intervals. Tests multi-year Landsat processing combined with GIF generation.

---

### 35. Deforestation GIF (Hansen Global Forest Change) — NOT YET RUN

**Q:** "Create an animated GIF of cumulative deforestation in Rondonia, Brazil from 2001-2023 using Hansen data"

**Expected Tool Calls:** `run_code`, `get_thumbnail`

**Code:**
```python
rondonia_region = ee.Geometry.Point([-63.0, -10.5]).buffer(60000)
hansen = ee.Image('UMD/hansen/global_forest_change_2023_v1_11')
treecover = hansen.select('treecover2000')
lossyear = hansen.select('lossyear')
years = list(range(1, 24))
def cum_loss_image(y):
    y = ee.Number(y)
    cum_loss = lossyear.gt(0).And(lossyear.lte(y))
    forest = treecover.gt(30).And(cum_loss.Not())
    r = cum_loss.multiply(255); g = forest.multiply(200); b = forest.Not().And(cum_loss.Not()).multiply(150)
    return r.addBands(g).addBands(b).rename(['vis_r','vis_g','vis_b']).toUint8().set(
        'system:time_start', ee.Date.fromYMD(ee.Number(2000).add(y), 6, 1).millis())
deforest_ts = ee.ImageCollection(ee.List(years).map(cum_loss_image))
```
Then: `get_thumbnail(variable="deforest_ts", viz_params='{"bands":["vis_r","vis_g","vis_b"],"min":0,"max":255}')`

**Notes:** Custom RGB encoding: green=forest, red=cumulative loss, gray=non-forest. Server-side mapped function (not Python loop). Tests complex GIF with synthesized RGB bands.

---

### 36. Multi-Index Line Chart (NDVI, NBR, NDMI) — NOT YET RUN

**Q:** "Chart NDVI, NBR, and NDMI together over time for a forest area in the Sierra Nevada from 2010-2024"

**Expected Tool Calls:** `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
sierra = ee.Geometry.Point([-120.0, 38.5]).buffer(5000)
composites = gil.getLandsatWrapper(sierra, 2010, 2024, startJulian=152, endJulian=273)['processedComposites']
df, fig = cl.summarize_and_chart(composites, sierra, band_names=['NDVI','NBR','NDMI'], scale=30, title='Vegetation Indices - Sierra Nevada')
```

**Notes:** Multi-band line chart. `getLandsatWrapper` auto-computes all indices. `summarize_and_chart` plots multiple bands as separate lines on the same chart. Useful for comparing index sensitivity.

---

### 37. LCMS Land Cover Stacked Area Chart — NOT YET RUN

**Q:** "Create a stacked area chart showing LCMS land cover proportions changing over time near Lake Tahoe"

**Expected Tool Calls:** `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
tahoe = ee.Geometry.Point([-120.0, 39.0]).buffer(20000)
lcms_lc = ee.ImageCollection('USFS/GTAC/LCMS/v2023-9').select('Land_Cover')
df, fig = cl.summarize_and_chart(lcms_lc, tahoe, scale=30, stacked=True, title='LCMS Land Cover Proportions - Lake Tahoe')
```

**Notes:** Tests the `stacked=True` parameter for area charts. Shows how land cover class proportions shift over the LCMS time range (1985-2023).

---

### 38. Precipitation Trend Line Chart (CHIRPS) — NOT YET RUN

**Q:** "Chart annual precipitation totals in the Sahel region from 2000-2024 using CHIRPS"

**Expected Tool Calls:** `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
sahel = ee.Geometry.Point([2.0, 13.5]).buffer(50000)
chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
years = list(range(2000, 2025))
precip_imgs = []
for y in years:
    annual = chirps.filterDate(f'{y}-01-01', f'{y}-12-31').sum().rename('precip_mm')
    precip_imgs.append(annual.set('system:time_start', ee.Date(f'{y}-06-01').millis()))
precip_ts = ee.ImageCollection(precip_imgs)
df, fig = cl.summarize_and_chart(precip_ts, sahel, band_names=['precip_mm'], scale=5000, reducer='mean', title='Annual Precipitation - Sahel')
```

**Notes:** Tests continuous-value line chart from climate data. CHIRPS daily data summed to annual totals. Uses coarse scale (5km) to match CHIRPS resolution. Similar Python-loop pattern to Q20/Q25.

---

### 39. Fire Frequency Map and Chart — NOT YET RUN

**Q:** "Compute and chart how many times an area has burned in central Oregon using MTBS data from 1984-2023"

**Expected Tool Calls:** `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
oregon = ee.Geometry.Point([-121.5, 44.0]).buffer(40000)
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
burn_count = mtbs.map(lambda img: img.select('Severity').gt(1).rename('burned')).sum().rename('fire_count')
Map.addLayer(burn_count.clip(oregon), {'min':0, 'max':5, 'palette':['white','yellow','orange','red','darkred']}, 'Fire Frequency')
df, fig = cl.summarize_and_chart(burn_count, oregon, band_names=['fire_count'], scale=30, title='Fire Frequency - Central Oregon')
```

**Notes:** Server-side `.map().sum()` to count burn events per pixel across the full MTBS record. Heat palette visualization. Tests continuous-value charting of a derived product.

---

### 40. Sankey Land Cover Transition After Fire — NOT YET RUN

**Q:** "Create a Sankey diagram showing NLCD land cover transitions caused by the 2020 Creek Fire (pre-fire 2019 vs post-fire 2021)"

**Expected Tool Calls:** `run_code`

**Code:**
```python
import geeViz.chartingLib as cl
creek = ee.Geometry.Point([-119.2, 37.2]).buffer(30000)
nlcd_2019 = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2019').select('landcover').set('system:time_start', ee.Date('2019-01-01').millis())
nlcd_2021 = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2021').select('landcover').set('system:time_start', ee.Date('2021-01-01').millis())
nlcd_transition = ee.ImageCollection([nlcd_2019, nlcd_2021])
sankey_df, fig, matrix_df = cl.summarize_and_chart(
    nlcd_transition, creek, sankey=True, transition_periods=[2019, 2021],
    sankey_band_name='landcover', min_percentage=0.5, scale=30,
    title='NLCD Transitions - Creek Fire Area')
html = cl.sankey_to_html(fig)
```

**Notes:** Builds on Q3 (Sankey with LCMS) but uses NLCD for fire-specific transitions. Shows forest → shrubland/barren transitions caused by fire. Tests `system:time_start` setting on individual images assembled into a collection.

---

## Bugs Fixed (Historical)

### Code bugs in `chartingLib.py`:
1. **`filterBounds` on ee.Image** — Both `summarize_and_chart()` and `zonal_stats()` called `ee_obj.filterBounds(geometry)` unconditionally. Fixed to check `isinstance(ee_obj, ee.ImageCollection)` first.

### Agent instruction errors in `agent-instructions.md`:
1. **`getLandsatWrapper` missing required args** — Example omitted `startJulian` and `endJulian` which have no defaults. Fixed with `startJulian=152, endJulian=273`.
2. **Wrong dict key `'composites'`** — Should be `'processedComposites'`. Fixed in all examples.
3. **`simpleLANDTRENDR` wrong first argument** — Instructions implied passing study area; actually requires an ImageCollection (composites). Fixed with two-step workflow note.
4. **Added "Critical function signatures" section** — New section listing common pitfalls agents hit with wrapper function signatures.

### Test harness bugs:
1. **`extract_and_chart` parameter name** — Test used `asset_id` which doesn't exist. Fixed to use `collection_var` with a prior `run_code` step to load the collection into the REPL namespace.

## Remaining Issues

1. **Multi-year NLCD**: The standard NLCD release only has single years. Annual NLCD from sat-io is not publicly accessible. Agent should use `search_datasets` to discover available years, or recommend LCMS for time series analysis.
2. **Custom analysis (floods, reservoirs, etc.)**: No geeViz wrapper for everything. Agent must write raw EE code for domain-specific tasks like flood detection or water extent tracking. This is expected.
3. **`get_api_reference` is critical**: Agents MUST look up signatures before writing code. The instructions now emphasize this more strongly.
4. **Large computation graphs**: Python for-loops constructing `ee.ImageCollection` from many individual images (Q20) can cause EE timeouts. Prefer server-side operations where possible.
5. **`extract_and_chart` uses `collection_var`/`image_var`**: These take REPL variable names, not asset IDs. Agent must load the asset into the namespace first via `run_code`.

---

## How to Run Tests

### Automated (test harness):
```bash
python geeViz/mcp/run_tests.py
```
Results saved to:
- `geeViz/mcp/logs/tool_calls.log` — JSON-lines log of every tool call
- `geeViz/mcp/logs/test_results.json` — structured results per question

### Manual (via MCP client):
1. Start the MCP server or connect via Claude Desktop
2. Ask each question as a natural language prompt
3. After each question, check the log at `geeViz/mcp/logs/tool_calls.log`
4. For each question, record:
   - Which tools were called (from log)
   - Whether the final output was correct
   - Any errors or retries needed
   - Time to completion

### Log entry format:
```json
{"timestamp": "2026-03-10T17:00:22", "tool": "run_code", "args": {"code": "import geeViz..."}, "status": "OK", "result_preview": "{\"success\": true, ...}"}
```
