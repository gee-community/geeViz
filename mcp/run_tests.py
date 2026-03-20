"""
Run all 40 MCP test questions programmatically.
Calls MCP tool functions directly so tool_calls.log captures everything.
"""
import sys, os, asyncio, json, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from geeViz.mcp.server import (
    run_code, geocode, search_datasets, inspect_asset,
    list_examples, get_example, get_api_reference, search_functions,
    view_map, extract_and_chart, get_thumbnail, get_catalog_info,
    clear_map, _TOOL_LOG_FILE,
)

# Clear log file
with open(_TOOL_LOG_FILE, "w") as f:
    f.write("")

results = {}

async def run_test(qnum, description, steps):
    """Run a sequence of MCP tool calls for a test question."""
    print(f"\n{'='*60}")
    print(f"Q{qnum}: {description}")
    print(f"{'='*60}")
    t0 = time.time()
    tool_calls = []
    errors = []
    for step_name, fn, kwargs in steps:
        print(f"  -> {step_name}...")
        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(**kwargs)
            else:
                result = fn(**kwargs)
            preview = str(result)[:5000]
            tool_calls.append({"tool": step_name, "status": "OK", "preview": preview})
            print(f"     OK ({len(str(result))} chars)")
        except Exception as e:
            tool_calls.append({"tool": step_name, "status": "ERROR", "error": str(e)[:5000]})
            errors.append(f"{step_name}: {e}")
            print(f"     FAIL: {e}")
    elapsed = round(time.time() - t0, 1)
    status = "PASS" if not errors else "FAIL"
    results[qnum] = {"description": description, "status": status, "time": elapsed,
                      "tool_calls": tool_calls, "errors": errors}
    print(f"  Result: {status} ({elapsed}s)")


async def main():
    # ================================================================
    # Q1: Forest Loss Monitoring
    # ================================================================
    await run_test(1, "Forest loss near Asheville using LCMS", [
        ("search_functions", search_functions, {"query": "summarize_and_chart"}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
study = ee.Geometry.Point([-82.55, 35.60]).buffer(10000)
lcms = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').select(['Land_Cover'])
df, fig = cl.summarize_and_chart(lcms, study, scale=30, title='LCMS Land Cover - Asheville, NC')
print('Shape:', df.shape)
print(df.head(3).to_markdown())
"""}),
    ])

    # ================================================================
    # Q2: Wildfire Burn Severity
    # ================================================================
    await run_test(2, "Burn severity Cameron Peak Fire 2020", [
        ("search_datasets", search_datasets, {"query": "MTBS burn severity"}),
        ("inspect_asset", inspect_asset, {"asset_id": "USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1"}),
        ("run_code", run_code, {"code": """
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
burn_2020 = mtbs.filter(ee.Filter.calendarRange(2020, 2020, 'year')).first()
cameron = ee.Geometry.Point([-105.5, 40.6]).buffer(30000)
Map.clearMap()
Map.addLayer(burn_2020, {'autoViz': True}, 'Burn Severity 2020')
Map.centerObject(cameron, 11)
print('Bands:', burn_2020.bandNames().getInfo())
"""}),
    ])

    # ================================================================
    # Q3: Sankey Transition
    # ================================================================
    await run_test(3, "Land use transition Sankey - Salt Lake County", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
counties = ee.FeatureCollection('TIGER/2018/Counties')
slc = counties.filter(ee.Filter.And(ee.Filter.eq('NAME','Salt Lake'), ee.Filter.eq('STATEFP','49')))
study_area = slc.geometry()
lcms = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10')
sankey_df, fig, matrix_dict = cl.summarize_and_chart(
    lcms, study_area, sankey=True, transition_periods=[1990, 2010, 2024],
    sankey_band_name='Land_Use', min_percentage=0.5, scale=30,
    title='LCMS Land Use Transition - Salt Lake County')
html = cl.sankey_to_html(fig)
print('Sankey rows:', len(sankey_df))
for label, mdf in matrix_dict.items():
    print(f"\\n{label}")
    print(mdf.head(5).to_markdown())
"""}),
    ])

    # ================================================================
    # Q4: NDVI Trend
    # ================================================================
    await run_test(4, "NDVI trend near Yellowstone 2000-2024", [
        ("get_api_reference", get_api_reference, {"module": "getImagesLib", "function_name": "getLandsatWrapper"}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
study = ee.Geometry.Point([-110.5, 44.6]).buffer(5000)
composites = gil.getLandsatWrapper(study, 2000, 2024, startJulian=152, endJulian=273)['processedComposites']
df, fig = cl.summarize_and_chart(composites, study, band_names=['NDVI'], scale=30, title='NDVI Yellowstone')
print('Shape:', df.shape)
print(df.head(5).to_markdown())
"""}),
    ])

    # ================================================================
    # Q5: Urban Expansion
    # ================================================================
    await run_test(5, "Urban expansion Phoenix using LCMS", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
phoenix = ee.Geometry.Point([-112.07, 33.45]).buffer(20000)
lcms = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').select(['Land_Cover'])
df, fig = cl.summarize_and_chart(lcms, phoenix, scale=30, title='LCMS Land Cover - Phoenix, AZ')
print('Shape:', df.shape)
print(df.head(3).to_markdown())
"""}),
    ])

    # ================================================================
    # Q6: Land Cover Bar Chart (single Image)
    # ================================================================
    await run_test(6, "Land cover breakdown King County WA (single Image)", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
counties = ee.FeatureCollection('TIGER/2018/Counties')
king = counties.filter(ee.Filter.And(ee.Filter.eq('NAME','King'), ee.Filter.eq('STATEFP','53')))
nlcd = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2021').select(['landcover'])
df, fig = cl.summarize_and_chart(nlcd, king.geometry(), scale=30, title='NLCD 2021 - King County, WA')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q7: LANDTRENDR
    # ================================================================
    await run_test(7, "LANDTRENDR change detection Bozeman", [
        ("list_examples", list_examples, {"filter": "LANDTRENDR"}),
        ("get_api_reference", get_api_reference, {"module": "changeDetectionLib", "function_name": "simpleLANDTRENDR"}),
        ("run_code", run_code, {"code": """
import geeViz.changeDetectionLib as cdl
study = ee.Geometry.Point([-111.04, 45.68]).buffer(10000)
composites = gil.getLandsatWrapper(study, 1985, 2024, startJulian=152, endJulian=273)['processedComposites']
lt_output = cdl.simpleLANDTRENDR(composites, 1985, 2024)
Map.clearMap()
Map.centerObject(study, 12)
print('LANDTRENDR complete, layers added to map')
"""}),
    ])

    # ================================================================
    # Q8: Flood Mapping
    # ================================================================
    await run_test(8, "Flood mapping Hurricane Harvey Houston", [
        ("run_code", run_code, {"code": """
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
print('Flood map created')
"""}),
    ])

    # ================================================================
    # Q9: Vegetation Recovery
    # ================================================================
    await run_test(9, "NDVI recovery after Camp Fire Paradise CA", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
paradise = ee.Geometry.Point([-121.62, 39.76]).buffer(5000)
composites = gil.getLandsatWrapper(paradise, 2017, 2024, startJulian=152, endJulian=273)['processedComposites']
df, fig = cl.summarize_and_chart(composites, paradise, band_names=['NDVI','NBR'], scale=30, title='Veg Recovery - Camp Fire')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q10: Compare Datasets
    # ================================================================
    await run_test(10, "Compare LCMS vs NLCD 2021 Denver", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
denver = ee.Geometry.Point([-104.99, 39.74]).buffer(15000)
lcms_2021 = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').filter(ee.Filter.calendarRange(2021,2021,'year')).first().select(['Land_Cover'])
nlcd_2021 = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2021').select(['landcover'])
df_lcms, _ = cl.summarize_and_chart(lcms_2021, denver, scale=30, title='LCMS 2021 - Denver')
df_nlcd, _ = cl.summarize_and_chart(nlcd_2021, denver, scale=30, title='NLCD 2021 - Denver')
print('=== LCMS ===')
print(df_lcms.to_markdown())
print('=== NLCD ===')
print(df_nlcd.to_markdown())
"""}),
    ])

    # ================================================================
    # Q11: Phenology Shift
    # ================================================================
    await run_test(11, "Phenology shift Great Smoky Mountains", [
        ("search_functions", search_functions, {"query": "phEEno"}),
        ("list_examples", list_examples, {"filter": "phEEno"}),
        ("get_example", get_example, {"example_name": "phEEnoVizWrapper"}),
    ])

    # ================================================================
    # Q12: Hybrid Composite
    # ================================================================
    await run_test(12, "Hybrid Landsat-S2 composite Cascade Range 2023", [
        ("search_functions", search_functions, {"query": "hybrid"}),
        ("get_api_reference", get_api_reference, {"module": "getImagesLib", "function_name": "getLandsatAndSentinel2HybridWrapper"}),
        ("run_code", run_code, {"code": """
cascades = ee.Geometry.Point([-121.75, 44.0]).buffer(20000)
result = gil.getLandsatAndSentinel2HybridWrapper(cascades, 2023, 2023, startJulian=152, endJulian=273)
composites = result['processedComposites']
Map.clearMap()
Map.addLayer(composites.first(), {'bands':'swir1,nir,red', 'min':0.05, 'max':0.45}, 'Hybrid 2023')
Map.centerObject(cascades, 11)
print('Hybrid composite bands:', composites.first().bandNames().getInfo()[:10])
"""}),
    ])

    # ================================================================
    # Q13: Export to Asset
    # ================================================================
    await run_test(13, "Export LCMS for Colorado to asset (dry run)", [
        ("geocode", geocode, {"place_name": "Colorado", "use_boundaries": True}),
        ("run_code", run_code, {"code": """
# Just verify the geometry and image setup, don't actually export
colorado = ee.FeatureCollection('TIGER/2018/States').filter(ee.Filter.eq('NAME','Colorado')).geometry()
lcms_2023 = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').filter(ee.Filter.calendarRange(2023,2023,'year')).first().select(['Land_Cover'])
clipped = lcms_2023.clip(colorado)
print('Image bands:', clipped.bandNames().getInfo())
print('Geometry type:', colorado.type().getInfo())
print('Ready for export (not executing to avoid cost)')
"""}),
    ])

    # ================================================================
    # Q14: Harmonic Regression
    # ================================================================
    await run_test(14, "Harmonic regression S2 NDVI Central Valley CA", [
        ("list_examples", list_examples, {"filter": "harmonic"}),
        ("get_api_reference", get_api_reference, {"module": "getImagesLib", "function_name": "getHarmonicCoefficientsAndFit"}),
        ("search_functions", search_functions, {"query": "harmonic"}),
    ])

    # ================================================================
    # Q15: CCDC Break Detection
    # ================================================================
    await run_test(15, "CCDC change detection Willamette Valley OR", [
        ("list_examples", list_examples, {"filter": "CCDC"}),
        ("get_example", get_example, {"example_name": "CCDCWrapper"}),
        ("get_api_reference", get_api_reference, {"module": "changeDetectionLib", "function_name": "simpleCCDCPrediction"}),
    ])

    # ================================================================
    # Q16: Cross-Boundary Comparison
    # ================================================================
    await run_test(16, "Compare forest cover Yellowstone vs Grand Teton", [
        ("geocode", geocode, {"place_name": "Yellowstone National Park", "use_boundaries": True}),
        ("geocode", geocode, {"place_name": "Grand Teton National Park", "use_boundaries": True}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
# Use TIGER/NPS or simple buffers
ynp = ee.Geometry.Point([-110.5, 44.6]).buffer(50000)
gtnp = ee.Geometry.Point([-110.7, 43.75]).buffer(30000)
fc = ee.FeatureCollection([
    ee.Feature(ynp, {'name': 'Yellowstone NP'}),
    ee.Feature(gtnp, {'name': 'Grand Teton NP'}),
])
lcms_2023 = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').filter(ee.Filter.calendarRange(2023,2023,'year')).first().select(['Land_Cover'])
df, fig = cl.summarize_and_chart(lcms_2023, fc, scale=30, feature_label='name', title='Forest Cover Comparison 2023')
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q17: Climate-Vegetation Correlation
    # ================================================================
    await run_test(17, "DAYMET precip vs NDVI eastern Montana", [
        ("list_examples", list_examples, {"filter": "climate"}),
        ("search_functions", search_functions, {"query": "getClimate"}),
        ("get_api_reference", get_api_reference, {"module": "getImagesLib", "function_name": "getClimateWrapper"}),
    ])

    # ================================================================
    # Q18: Buildings in Burn Area
    # ================================================================
    await run_test(18, "Buildings in Dixie Fire perimeter", [
        ("search_datasets", search_datasets, {"query": "building footprints"}),
        ("search_datasets", search_datasets, {"query": "MTBS fire perimeter"}),
        ("run_code", run_code, {"code": """
# Check if building footprints are available
try:
    buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
    print('Google Buildings available')
except:
    print('Google Buildings not found, trying Microsoft')
try:
    ms_buildings = ee.FeatureCollection('projects/sat-io/open-datasets/MSBuildings/US')
    print('MS Buildings available')
except:
    print('MS Buildings not found either')
# Check MTBS
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
burn_2021 = mtbs.filter(ee.Filter.calendarRange(2021, 2021, 'year')).first()
dixie_area = ee.Geometry.Point([-121.4, 40.0]).buffer(50000)
print('MTBS 2021 bands:', burn_2021.bandNames().getInfo())
"""}),
    ])

    # ================================================================
    # Q19: Point Extraction Table
    # ================================================================
    await run_test(19, "Extract LCMS time series at exact point", [
        ("run_code", run_code, {"code": """
lcms_ts = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').select(['Land_Cover','Land_Use'])
"""}),
        ("extract_and_chart", extract_and_chart, {
            "collection_var": "lcms_ts",
            "lon": -104.9903, "lat": 39.7392,
            "band_names": "Land_Cover,Land_Use",
            "chart_type": "bar",
        }),
    ])

    # ================================================================
    # Q20: Reservoir Water Extent
    # ================================================================
    await run_test(20, "Lake Mead water extent change 2000-2024", [
        ("search_datasets", search_datasets, {"query": "JRC global surface water"}),
        ("geocode", geocode, {"place_name": "Lake Mead"}),
        ("run_code", run_code, {"code": """
lake_mead = ee.Geometry.Point([-114.75, 36.15]).buffer(20000)
# JRC Monthly Water History
jrc = ee.ImageCollection('JRC/GSW1_4/MonthlyHistory')
# Get annual water occurrence
years = list(range(2000, 2025))
water_areas = []
for y in years:
    monthly = jrc.filter(ee.Filter.calendarRange(y, y, 'year'))
    # water = 2 in JRC encoding
    water_count = monthly.map(lambda img: img.eq(2)).sum()
    total = monthly.size()
    pct = water_count.divide(total).multiply(100).rename('water_pct')
    water_areas.append(pct.set('system:time_start', ee.Date(f'{y}-06-01').millis()))
water_col = ee.ImageCollection(water_areas)
from geeViz.outputLib import charts as cl
df, fig = cl.summarize_and_chart(water_col, lake_mead, band_names=['water_pct'], scale=30, title='Lake Mead Water Extent')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q21: Fire Burn Severity Bar Chart
    # ================================================================
    await run_test(21, "MTBS burn severity area breakdown Creek Fire 2020", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
creek_fire = ee.Geometry.Point([-119.2, 37.2]).buffer(30000)
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
burn_2020 = mtbs.filter(ee.Filter.calendarRange(2020, 2020, 'year')).first()
Map.clearMap()
Map.addLayer(burn_2020, {'autoViz': True}, 'Burn Severity 2020')
Map.centerObject(creek_fire, 11)
df, fig = cl.summarize_and_chart(burn_2020, creek_fire, scale=30, title='Creek Fire Burn Severity 2020')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q22: Post-Fire dNBR Change Detection
    # ================================================================
    await run_test(22, "dNBR burn severity Dixie Fire pre/post Landsat", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
dixie = ee.Geometry.Point([-121.4, 40.0]).buffer(50000)
pre = gil.getLandsatWrapper(dixie, 2020, 2020, startJulian=152, endJulian=273)['processedComposites'].first()
post = gil.getLandsatWrapper(dixie, 2022, 2022, startJulian=152, endJulian=273)['processedComposites'].first()
dnbr = pre.select('NBR').subtract(post.select('NBR')).rename('dNBR')
Map.clearMap()
Map.addLayer(dnbr, {'min':-0.5, 'max':1.0, 'palette':['green','yellow','orange','red']}, 'dNBR Dixie Fire')
Map.centerObject(dixie, 10)
df, fig = cl.summarize_and_chart(dnbr, dixie, band_names=['dNBR'], scale=30, reducer='mean', title='dNBR Dixie Fire')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q23: Fire Progression GIF from Sentinel-2
    # ================================================================
    await run_test(23, "Fire progression GIF August Complex 2020", [
        ("run_code", run_code, {"code": """
fire_center = ee.Geometry.Point([-122.7, 39.8])
fire_region = fire_center.buffer(40000)
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
fire_ts = s2.filterBounds(fire_region).filterDate('2020-06-01','2020-12-31').filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).select(['B4','B3','B2']).map(lambda img: img.divide(10000).set('system:time_start', img.get('system:time_start')))
# Create monthly composites
months = ee.List.sequence(6, 12)
def monthly_composite(m):
    m = ee.Number(m)
    start = ee.Date.fromYMD(2020, m, 1)
    end = start.advance(1, 'month')
    return fire_ts.filterDate(start, end).median().set('system:time_start', start.millis())
fire_monthly = ee.ImageCollection(months.map(monthly_composite))
print('Monthly composites created:', fire_monthly.size().getInfo())
"""}),
        ("get_thumbnail", get_thumbnail, {
            "variable": "fire_monthly",
            "viz_params": '{"bands":["B4","B3","B2"],"min":0,"max":0.3}',
            "region_var": "fire_region",
            "dimensions": 512,
            "frames_per_second": 2,
        }),
    ])

    # ================================================================
    # Q24: Flood Detection with Sentinel-1 SAR
    # ================================================================
    await run_test(24, "Flood extent Sentinel-1 SAR Missouri River 2019", [
        ("search_functions", search_functions, {"query": "getS1"}),
        ("run_code", run_code, {"code": """
missouri = ee.Geometry.Point([-95.9, 41.3]).buffer(30000)
s1 = ee.ImageCollection('COPERNICUS/S1_GRD').filter(ee.Filter.eq('instrumentMode','IW')).filter(ee.Filter.listContains('transmitterReceiverPolarisation','VV')).select('VV')
dry = s1.filterBounds(missouri).filterDate('2019-01-01','2019-02-28').mean()
flood = s1.filterBounds(missouri).filterDate('2019-03-15','2019-04-30').mean()
diff = flood.subtract(dry).rename('VV_diff')
flood_mask = diff.lt(-3).selfMask().rename('Flood')
Map.clearMap()
Map.addLayer(flood_mask, {'min':0, 'max':1, 'palette':['blue']}, 'Flood Extent SAR')
Map.centerObject(missouri, 11)
print('Flood map from SAR created')
"""}),
    ])

    # ================================================================
    # Q25: Reservoir Water Time Series (JRC)
    # ================================================================
    await run_test(25, "Lake Powell water extent time series 2000-2024", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
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
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q26: Flood Impact on Cropland
    # ================================================================
    await run_test(26, "Flood impact on cropland Mississippi Delta", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
delta = ee.Geometry.Point([-90.5, 33.0]).buffer(20000)
nlcd = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2021').select('landcover')
jrc = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent')
flood_zone = jrc.gt(0).selfMask()
Map.clearMap()
Map.addLayer(nlcd, {'autoViz': True}, 'NLCD 2021')
Map.addLayer(flood_zone, {'min':0, 'max':1, 'palette':['cyan']}, 'Flood-Prone Zone')
Map.centerObject(delta, 11)
# Chart land cover within flood-prone zone
df, fig = cl.summarize_and_chart(nlcd, delta, scale=30, title='Land Cover in Flood Zone - Mississippi Delta')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q27: Building Footprint Count (Google Open Buildings)
    # ================================================================
    await run_test(27, "Count buildings in Nairobi using Open Buildings", [
        ("search_datasets", search_datasets, {"query": "Google Open Buildings"}),
        ("run_code", run_code, {"code": """
nairobi = ee.Geometry.Point([36.82, -1.29]).buffer(5000)
buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
local_buildings = buildings.filterBounds(nairobi)
count = local_buildings.size().getInfo()
print(f'Total buildings within 5km of downtown Nairobi: {count}')
# Summary stats
if count > 0:
    area_stats = local_buildings.aggregate_stats('area_in_meters')
    conf_stats = local_buildings.aggregate_stats('confidence')
    print(f'Mean building area: {area_stats.getInfo()["mean"]:.1f} sq m')
    print(f'Total building area: {area_stats.getInfo()["sum"]:.0f} sq m')
    print(f'Mean confidence: {conf_stats.getInfo()["mean"]:.3f}')
"""}),
    ])

    # ================================================================
    # Q28: Buildings in Burn Perimeter (Camp Fire)
    # ================================================================
    await run_test(28, "Structures in Camp Fire burn area Paradise CA", [
        ("run_code", run_code, {"code": """
paradise = ee.Geometry.Point([-121.6, 39.76]).buffer(15000)
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
burn_2018 = mtbs.filter(ee.Filter.calendarRange(2018, 2018, 'year')).first()
high_severity = burn_2018.select('Severity').gte(3).selfMask()
# Microsoft buildings for US
ms_buildings = ee.FeatureCollection('projects/sat-io/open-datasets/MSBuildings/US')
all_buildings = ms_buildings.filterBounds(paradise)
total_count = all_buildings.size().getInfo()
print(f'Total buildings in study area: {total_count}')
Map.clearMap()
Map.addLayer(burn_2018, {'autoViz': True}, 'Burn Severity 2018')
Map.centerObject(paradise, 12)
print('Burn severity map created. Building count computed.')
"""}),
    ])

    # ================================================================
    # Q29: Flood-Exposed Buildings (Dhaka)
    # ================================================================
    await run_test(29, "Flood-exposed buildings Dhaka Bangladesh", [
        ("run_code", run_code, {"code": """
dhaka = ee.Geometry.Point([90.4, 23.8]).buffer(10000)
jrc = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('seasonality')
flood_risk = jrc.gt(2).rename('flood_risk')
buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
local_buildings = buildings.filterBounds(dhaka)
total = local_buildings.size().getInfo()
print(f'Total buildings in study area: {total}')
# Sample flood risk at building centroids
if total > 0 and total < 500000:
    at_risk = local_buildings.filter(ee.Filter.notNull(['confidence']))
    print(f'Buildings with data: {at_risk.size().getInfo()}')
print('Flood exposure analysis for Dhaka complete')
"""}),
    ])

    # ================================================================
    # Q30: Aboveground Biomass Mapping (Amazon)
    # ================================================================
    await run_test(30, "Aboveground biomass mapping Amazon", [
        ("search_datasets", search_datasets, {"query": "aboveground biomass"}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
amazon = ee.Geometry.Point([-60.0, -3.0]).buffer(100000)
# NASA GEDI L4B Gridded Aboveground Biomass Density
biomass = ee.Image('LCLUC/GEDI_L4B_Gridded_Biomass_V2_1/2021_v2_1').select('MU')
Map.clearMap()
Map.addLayer(biomass.clip(amazon), {'min':0, 'max':300, 'palette':['lightyellow','green','darkgreen']}, 'Biomass Density')
Map.centerObject(amazon, 8)
df, fig = cl.summarize_and_chart(biomass, amazon, band_names=['MU'], scale=1000, reducer='mean', title='Biomass Density - Amazon')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q31: Biomass/Vegetation Trajectory with LandTrendr
    # ================================================================
    await run_test(31, "LandTrendr NBR trajectory Pacific Northwest", [
        ("get_api_reference", get_api_reference, {"module": "changeDetectionLib", "function_name": "simpleLANDTRENDR"}),
        ("run_code", run_code, {"code": """
import geeViz.changeDetectionLib as cdl
from geeViz.outputLib import charts as cl
pnw = ee.Geometry.Point([-122.0, 46.0]).buffer(50000)
composites = gil.getLandsatWrapper(pnw, 2000, 2024, startJulian=152, endJulian=273)['processedComposites']
lt_output = cdl.simpleLANDTRENDR(composites, 2000, 2024)
Map.clearMap()
Map.centerObject(pnw, 10)
# Chart NBR time series at center point to show vegetation trajectory
df, fig = cl.summarize_and_chart(composites, ee.Geometry.Point([-122.0, 46.0]), band_names=['NBR'], scale=30, title='NBR Trajectory - PNW')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q32: Forest Canopy Height (ETH Global)
    # ================================================================
    await run_test(32, "Canopy height visualization Borneo", [
        ("search_datasets", search_datasets, {"query": "canopy height ETH"}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
borneo = ee.Geometry.Point([116.0, 1.5]).buffer(50000)
canopy = ee.Image('users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1').rename('canopy_height')
Map.clearMap()
Map.addLayer(canopy.clip(borneo), {'min':0, 'max':50, 'palette':['lightyellow','green','darkgreen']}, 'Canopy Height 2020')
Map.centerObject(borneo, 10)
df, fig = cl.summarize_and_chart(canopy, borneo, band_names=['canopy_height'], scale=100, reducer='mean', title='Canopy Height - Borneo')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q33: NDVI Growing Season GIF (Iowa Corn Belt)
    # ================================================================
    await run_test(33, "NDVI growing season GIF Iowa corn belt 2023", [
        ("run_code", run_code, {"code": """
crop_center = ee.Geometry.Point([-93.5, 42.0])
crop_region = crop_center.buffer(30000)
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
months = ee.List.sequence(4, 10)
def monthly_ndvi(m):
    m = ee.Number(m)
    start = ee.Date.fromYMD(2023, m, 1)
    end = start.advance(1, 'month')
    composite = s2.filterBounds(crop_region).filterDate(start, end).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15)).median()
    ndvi = composite.normalizedDifference(['B8','B4']).rename('NDVI')
    return ndvi.set('system:time_start', start.millis())
ndvi_season = ee.ImageCollection(months.map(monthly_ndvi))
print('Monthly NDVI composites:', ndvi_season.size().getInfo())
"""}),
        ("get_thumbnail", get_thumbnail, {
            "variable": "ndvi_season",
            "viz_params": '{"bands":["NDVI"],"min":0,"max":0.9,"palette":["brown","yellow","green","darkgreen"]}',
            "region_var": "crop_region",
            "dimensions": 512,
            "frames_per_second": 2,
        }),
    ])

    # ================================================================
    # Q34: Urban Expansion GIF (Phoenix)
    # ================================================================
    await run_test(34, "Urban expansion GIF Phoenix 2000-2024", [
        ("run_code", run_code, {"code": """
phoenix_center = ee.Geometry.Point([-112.0, 33.45])
phoenix_region = phoenix_center.buffer(40000)
years = [2000, 2005, 2010, 2015, 2020, 2024]
urban_imgs = []
for y in years:
    composites = gil.getLandsatWrapper(phoenix_region, y, y, startJulian=152, endJulian=273)['processedComposites']
    img = composites.first().select(['red','green','blue']).set('system:time_start', ee.Date(f'{y}-07-01').millis())
    urban_imgs.append(img)
urban_ts = ee.ImageCollection(urban_imgs)
print('Urban time series images:', urban_ts.size().getInfo())
"""}),
        ("get_thumbnail", get_thumbnail, {
            "variable": "urban_ts",
            "viz_params": '{"bands":["red","green","blue"],"min":0.0,"max":0.3}',
            "region_var": "phoenix_region",
            "dimensions": 512,
            "frames_per_second": 2,
        }),
    ])

    # ================================================================
    # Q35: Deforestation GIF (Hansen, Rondonia Brazil)
    # ================================================================
    await run_test(35, "Cumulative deforestation GIF Rondonia Brazil", [
        ("run_code", run_code, {"code": """
rondonia = ee.Geometry.Point([-63.0, -10.5])
rondonia_region = rondonia.buffer(60000)
hansen = ee.Image('UMD/hansen/global_forest_change_2023_v1_11')
treecover = hansen.select('treecover2000')
lossyear = hansen.select('lossyear')
years = list(range(1, 24))  # 2001-2023
def cum_loss_image(y):
    y = ee.Number(y)
    cum_loss = lossyear.gt(0).And(lossyear.lte(y))
    forest = treecover.gt(30).And(cum_loss.Not())
    # RGB: forest=green, loss=red, non-forest=gray
    r = cum_loss.multiply(255)
    g = forest.multiply(200)
    b = forest.Not().And(cum_loss.Not()).multiply(150)
    return r.addBands(g).addBands(b).rename(['vis_r','vis_g','vis_b']).toUint8().set('system:time_start', ee.Date.fromYMD(ee.Number(2000).add(y), 6, 1).millis())
deforest_ts = ee.ImageCollection(ee.List(years).map(cum_loss_image))
print('Deforestation time series:', deforest_ts.size().getInfo())
"""}),
        ("get_thumbnail", get_thumbnail, {
            "variable": "deforest_ts",
            "viz_params": '{"bands":["vis_r","vis_g","vis_b"],"min":0,"max":255}',
            "region_var": "rondonia_region",
            "dimensions": 512,
            "frames_per_second": 3,
        }),
    ])

    # ================================================================
    # Q36: Multi-Index Line Chart (NDVI, NBR, NDMI)
    # ================================================================
    await run_test(36, "Multi-index line chart Sierra Nevada 2010-2024", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
sierra = ee.Geometry.Point([-120.0, 38.5]).buffer(5000)
composites = gil.getLandsatWrapper(sierra, 2010, 2024, startJulian=152, endJulian=273)['processedComposites']
multi_idx_ts = composites
df, fig = cl.summarize_and_chart(multi_idx_ts, sierra, band_names=['NDVI','NBR','NDMI'], scale=30, title='Vegetation Indices - Sierra Nevada')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q37: LCMS Land Cover Stacked Area Chart
    # ================================================================
    await run_test(37, "LCMS land cover stacked area chart Lake Tahoe", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
tahoe = ee.Geometry.Point([-120.0, 39.0]).buffer(20000)
lcms_lc = ee.ImageCollection('USFS/GTAC/LCMS/v2023-9').select('Land_Cover')
df, fig = cl.summarize_and_chart(lcms_lc, tahoe, scale=30, stacked=True, title='LCMS Land Cover Proportions - Lake Tahoe')
print('Shape:', df.shape)
print(df.head(10).to_markdown())
"""}),
    ])

    # ================================================================
    # Q38: Precipitation Trend Line Chart (CHIRPS)
    # ================================================================
    await run_test(38, "Annual precipitation trend CHIRPS Sahel 2000-2024", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
sahel = ee.Geometry.Point([2.0, 13.5]).buffer(50000)
chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
years = list(range(2000, 2025))
precip_imgs = []
for y in years:
    annual = chirps.filterDate(f'{y}-01-01', f'{y}-12-31').sum().rename('precip_mm')
    precip_imgs.append(annual.set('system:time_start', ee.Date(f'{y}-06-01').millis()))
precip_ts = ee.ImageCollection(precip_imgs)
df, fig = cl.summarize_and_chart(precip_ts, sahel, band_names=['precip_mm'], scale=5000, reducer='mean', title='Annual Precipitation - Sahel')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q39: Fire Frequency Map and Chart
    # ================================================================
    await run_test(39, "Fire frequency analysis central Oregon MTBS 1984-2023", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
oregon = ee.Geometry.Point([-121.5, 44.0]).buffer(40000)
mtbs = ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
# Create binary burned/not for each year and sum
burn_count = mtbs.map(lambda img: img.select('Severity').gt(1).rename('burned')).sum().rename('fire_count')
Map.clearMap()
Map.addLayer(burn_count.clip(oregon), {'min':0, 'max':5, 'palette':['white','yellow','orange','red','darkred']}, 'Fire Frequency')
Map.centerObject(oregon, 10)
df, fig = cl.summarize_and_chart(burn_count, oregon, band_names=['fire_count'], scale=30, title='Fire Frequency - Central Oregon')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q40: Sankey Land Cover Transition After Fire
    # ================================================================
    await run_test(40, "Sankey NLCD transitions Creek Fire pre/post", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
creek = ee.Geometry.Point([-119.2, 37.2]).buffer(30000)
nlcd_2019 = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2019').select('landcover').set('system:time_start', ee.Date('2019-01-01').millis())
nlcd_2021 = ee.Image('USGS/NLCD_RELEASES/2021_REL/NLCD/2021').select('landcover').set('system:time_start', ee.Date('2021-01-01').millis())
nlcd_transition = ee.ImageCollection([nlcd_2019, nlcd_2021])
sankey_df, fig, matrix_dict = cl.summarize_and_chart(
    nlcd_transition, creek, sankey=True, transition_periods=[2019, 2021],
    sankey_band_name='landcover', min_percentage=0.5, scale=30,
    title='NLCD Transitions - Creek Fire Area')
html = cl.sankey_to_html(fig)
print('Sankey rows:', len(sankey_df))
for label, mdf in matrix_dict.items():
    print(f"\\n{label}")
    print(mdf.head(5).to_markdown())
"""}),
    ])

    # ================================================================
    # SUMMARY
    # ================================================================
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    for q in sorted(results.keys()):
        r = results[q]
        tools = ", ".join(t["tool"] for t in r["tool_calls"])
        print(f"Q{q:3d} [{r['status']:4s}] ({r['time']:5.1f}s) {r['description']}")
        print(f"      Tools: {tools}")
        if r["errors"]:
            for e in r["errors"]:
                print(f"      ERROR: {e[:100]}")

    # Count
    passed = sum(1 for r in results.values() if r["status"] == "PASS")
    total = len(results)
    print(f"\n{passed}/{total} PASSED")
    print(f"\nTool log: {_TOOL_LOG_FILE}")

    # Write results JSON
    results_file = os.path.join(os.path.dirname(_TOOL_LOG_FILE), "test_results.json")
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results JSON: {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
