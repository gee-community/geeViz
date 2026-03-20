"""
20 Hard MCP Test Questions - v2
Tests advanced GEE/geeViz workflows: multi-sensor fusion, complex charting,
change detection, zonal stats, exports, and edge cases.
"""
import sys, os, asyncio, json, time, traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from geeViz.mcp.server import (
    run_code, geocode, search_datasets, inspect_asset,
    list_examples, get_example, get_api_reference, search_functions,
    view_map, extract_and_chart, get_thumbnail, get_catalog_info,
    clear_map, _TOOL_LOG_FILE,
)

results = {}
LOG_DIR = os.path.join(os.path.dirname(_TOOL_LOG_FILE))
RESULTS_FILE = os.path.join(LOG_DIR, "hard_tests_v2_results.json")
TEXT_LOG = os.path.join(LOG_DIR, "hard_tests_v2_log.txt")

# Clear text log
with open(TEXT_LOG, "w") as f:
    f.write(f"=== Hard MCP Tests v2 - {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

def log(msg):
    print(msg)
    with open(TEXT_LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


async def run_test(qnum, description, steps):
    """Run a sequence of MCP tool calls for a test question."""
    log(f"\n{'='*70}")
    log(f"Q{qnum}: {description}")
    log(f"{'='*70}")
    t0 = time.time()
    tool_calls = []
    errors = []
    outputs = []
    for step_name, fn, kwargs in steps:
        log(f"  -> {step_name}...")
        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(**kwargs)
            else:
                result = fn(**kwargs)
            preview = str(result)[:8000]
            tool_calls.append({"tool": step_name, "status": "OK", "preview": preview})
            outputs.append(preview)
            log(f"     OK ({len(str(result))} chars)")
            log(f"     Output: {str(result)[:500]}")
        except Exception as e:
            tb = traceback.format_exc()
            tool_calls.append({"tool": step_name, "status": "ERROR", "error": str(e)[:5000]})
            errors.append(f"{step_name}: {e}")
            outputs.append(f"ERROR: {e}")
            log(f"     FAIL: {e}")
            log(f"     Traceback: {tb[:500]}")
    elapsed = round(time.time() - t0, 1)
    status = "PASS" if not errors else "FAIL"
    results[qnum] = {
        "description": description,
        "status": status,
        "time": elapsed,
        "tool_calls": tool_calls,
        "errors": errors,
        "output_preview": "\n---\n".join(outputs)[:10000],
    }
    log(f"  Result: {status} ({elapsed}s)")
    return status


async def main():
    # Reset REPL
    await run_code(code="print('REPL reset')", reset=True)

    # ================================================================
    # Q1: Glacier retreat - Landsat NDSI time series, Glacier NP
    # ================================================================
    await run_test(1, "Glacier retreat NDSI time series - Glacier NP Montana", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
glacier_np = ee.Geometry.Point([-113.8, 48.75]).buffer(10000)
composites = gil.getLandsatWrapper(glacier_np, 1990, 2024, startJulian=182, endJulian=258)['processedComposites']
df, fig = cl.summarize_and_chart(composites, glacier_np, band_names=['NDSI'], scale=30, title='NDSI Trend - Glacier NP')
print('Shape:', df.shape)
print(df.to_markdown())
path = cl.save_chart_html(fig, 'glacier_ndsi.html')
print('Saved:', path)
"""}),
    ])

    # ================================================================
    # Q2: Night lights urban growth - VIIRS time series, Lagos Nigeria
    # ================================================================
    await run_test(2, "Night lights urban growth VIIRS - Lagos Nigeria", [
        ("search_datasets", search_datasets, {"query": "VIIRS nighttime lights monthly"}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
lagos = ee.Geometry.Point([3.4, 6.45]).buffer(30000)
viirs = ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG').select('avg_rad')
years = list(range(2014, 2025))
annual_imgs = []
for y in years:
    annual = viirs.filterDate(f'{y}-01-01', f'{y}-12-31').mean().rename('avg_rad')
    annual_imgs.append(annual.set('system:time_start', ee.Date(f'{y}-06-01').millis()))
viirs_ts = ee.ImageCollection(annual_imgs)
df, fig = cl.summarize_and_chart(viirs_ts, lagos, band_names=['avg_rad'], scale=500, reducer='mean', title='Night Lights - Lagos')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'lagos_nightlights.html')
"""}),
    ])

    # ================================================================
    # Q3: Mangrove extent change Sankey - Sundarbans Bangladesh
    # ================================================================
    await run_test(3, "Mangrove extent vegetation indices - Sundarbans", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
sundarbans = ee.Geometry.Point([89.2, 21.95]).buffer(10000)
# Use Landsat composites with NDVI and NDMI (not NDWI - doesn't exist in simpleAddIndices)
# Shorter time range + smaller area to avoid timeout
composites = gil.getLandsatWrapper(sundarbans, 2010, 2024, startJulian=1, endJulian=365)['processedComposites']
df, fig = cl.summarize_and_chart(composites, sundarbans, band_names=['NDVI','NDMI'], scale=30, title='Vegetation/Water Indices - Sundarbans')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'sundarbans_indices.html')
print('Saved chart')
"""}),
    ])

    # ================================================================
    # Q4: Heat island effect - Landsat LST difference urban vs rural, Phoenix
    # ================================================================
    await run_test(4, "Urban heat island LST analysis - Phoenix AZ", [
        ("search_datasets", search_datasets, {"query": "MODIS land surface temperature"}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
phoenix_urban = ee.Geometry.Point([-112.07, 33.45]).buffer(5000)
phoenix_rural = ee.Geometry.Point([-112.4, 33.3]).buffer(5000)
modis_lst = ee.ImageCollection('MODIS/061/MOD11A2').select('LST_Day_1km')
years = list(range(2003, 2025))
lst_imgs = []
for y in years:
    summer_lst = modis_lst.filterDate(f'{y}-06-01', f'{y}-09-01').mean()
    lst_k = summer_lst.multiply(0.02)  # scale factor
    lst_imgs.append(lst_k.rename('LST_K').set('system:time_start', ee.Date(f'{y}-07-01').millis()))
lst_ts = ee.ImageCollection(lst_imgs)
fc = ee.FeatureCollection([
    ee.Feature(phoenix_urban, {'name': 'Urban'}),
    ee.Feature(phoenix_rural, {'name': 'Rural'}),
])
df, fig = cl.summarize_and_chart(lst_ts, fc, band_names=['LST_K'], scale=1000, feature_label='name', title='UHI - Phoenix Urban vs Rural LST')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'phoenix_uhi.html')
"""}),
    ])

    # ================================================================
    # Q5: Snow cover duration analysis - Sierra Nevada
    # ================================================================
    await run_test(5, "Snow cover duration trend - Sierra Nevada CA", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
sierra = ee.Geometry.Point([-119.5, 37.5]).buffer(20000)
modis_snow = ee.ImageCollection('MODIS/061/MOD10A1').select('NDSI_Snow_Cover')
years = list(range(2001, 2025))
snow_imgs = []
for y in years:
    annual_snow = modis_snow.filterDate(f'{y}-01-01', f'{y}-12-31')
    snow_days = annual_snow.map(lambda img: img.gt(40).rename('snow_day')).sum().rename('snow_days')
    snow_imgs.append(snow_days.set('system:time_start', ee.Date(f'{y}-06-01').millis()))
snow_ts = ee.ImageCollection(snow_imgs)
df, fig = cl.summarize_and_chart(snow_ts, sierra, band_names=['snow_days'], scale=500, reducer='mean', title='Snow Cover Duration - Sierra Nevada')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'sierra_snow.html')
"""}),
    ])

    # ================================================================
    # Q6: Drought monitoring - PDSI time series, Great Plains
    # ================================================================
    await run_test(6, "Drought severity PDSI time series - Great Plains", [
        ("search_datasets", search_datasets, {"query": "Palmer drought severity PDSI"}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
great_plains = ee.Geometry.Point([-100.0, 38.0]).buffer(100000)
# PDSI is in GRIDMET/DROUGHT, NOT IDAHO_EPSCOR/GRIDMET
gridmet = ee.ImageCollection('GRIDMET/DROUGHT').select('pdsi')
years = list(range(2000, 2025))
pdsi_imgs = []
for y in years:
    annual = gridmet.filterDate(f'{y}-01-01', f'{y}-12-31').mean().rename('pdsi')
    pdsi_imgs.append(annual.set('system:time_start', ee.Date(f'{y}-06-01').millis()))
pdsi_ts = ee.ImageCollection(pdsi_imgs)
df, fig = cl.summarize_and_chart(pdsi_ts, great_plains, band_names=['pdsi'], scale=4000, reducer='mean', title='PDSI Drought Index - Great Plains')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'great_plains_pdsi.html')
"""}),
    ])

    # ================================================================
    # Q7: Coral reef / shallow water mapping - Sentinel-2, Florida Keys
    # ================================================================
    await run_test(7, "Shallow water bathymetry index - Florida Keys", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
keys = ee.Geometry.Point([-81.0, 24.65]).buffer(10000)
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(keys).filterDate('2023-01-01','2023-12-31').filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 5)).median()
# Ratio of blue to green as bathymetry proxy
blue = s2.select('B2').divide(10000)
green = s2.select('B3').divide(10000)
bathy_ratio = blue.log().divide(green.log()).rename('bathy_ratio')
Map.clearMap()
Map.addLayer(s2.select(['B4','B3','B2']).divide(10000).clip(keys), {'min':0, 'max':0.15}, 'True Color')
Map.addLayer(bathy_ratio.clip(keys), {'min':0, 'max':3, 'palette':['darkblue','cyan','yellow']}, 'Bathymetry Ratio')
Map.centerObject(keys, 13)
print('Bathymetry ratio computed for Florida Keys')
print('Band stats will follow...')
df, fig = cl.summarize_and_chart(bathy_ratio, keys, band_names=['bathy_ratio'], scale=10, reducer='mean', title='Bathymetry Ratio - Florida Keys')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q8: Agricultural NDVI phenology curve - single year monthly, Iowa
    # ================================================================
    await run_test(8, "Monthly NDVI phenology curve corn belt 2023 - Iowa", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
iowa = ee.Geometry.Point([-93.5, 42.0]).buffer(10000)
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
months = list(range(3, 12))  # Mar-Nov
monthly_imgs = []
for m in months:
    start = ee.Date.fromYMD(2023, m, 1)
    end = start.advance(1, 'month')
    composite = s2.filterBounds(iowa).filterDate(start, end).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).median()
    ndvi = composite.normalizedDifference(['B8','B4']).rename('NDVI')
    monthly_imgs.append(ndvi.set('system:time_start', start.millis()))
phenology = ee.ImageCollection(monthly_imgs)
# CRITICAL: use date_format='YYYY-MM' for sub-annual data, otherwise all months collapse to one year
df, fig = cl.summarize_and_chart(phenology, iowa, band_names=['NDVI'], scale=10, reducer='mean', date_format='YYYY-MM', title='Crop Phenology - Iowa 2023')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'iowa_phenology.html')
"""}),
    ])

    # ================================================================
    # Q9: Multi-region grouped bar chart - LCMS across 4 national forests
    # ================================================================
    await run_test(9, "Grouped bar chart LCMS across 4 national forests", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
# Define 4 national forest areas as point buffers
forests = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Point([-111.0, 45.5]).buffer(20000), {'name': 'Gallatin NF'}),
    ee.Feature(ee.Geometry.Point([-116.0, 44.0]).buffer(20000), {'name': 'Boise NF'}),
    ee.Feature(ee.Geometry.Point([-121.5, 44.2]).buffer(20000), {'name': 'Deschutes NF'}),
    ee.Feature(ee.Geometry.Point([-106.5, 35.5]).buffer(20000), {'name': 'Cibola NF'}),
])
# Pass the ImageCollection directly — summarize_and_chart auto-mosaics tiled data internally
# Never use .first() on tiled collections like LCMS — it may grab a tile that doesn't cover the study area
lcms_2023 = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10').filter(ee.Filter.calendarRange(2023,2023,'year')).select(['Land_Cover'])
df, fig = cl.summarize_and_chart(lcms_2023, forests, scale=30, feature_label='name', title='LCMS Land Cover 2023 - 4 National Forests')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'four_forests_lc.html')
"""}),
    ])

    # ================================================================
    # Q10: VERDET change detection - Pacific Northwest
    # ================================================================
    await run_test(10, "VERDET vegetation change detection - PNW", [
        ("search_functions", search_functions, {"query": "VERDET"}),
        ("get_api_reference", get_api_reference, {"module": "changeDetectionLib", "function_name": "VERDETVertStack"}),
        ("run_code", run_code, {"code": """
import geeViz.changeDetectionLib as cdl
pnw = ee.Geometry.Point([-122.0, 46.0]).buffer(20000)
composites = gil.getLandsatWrapper(pnw, 2000, 2024, startJulian=152, endJulian=273)['processedComposites']
# VERDETVertStack requires (ts, indexName, ...) - indexName is required 2nd arg
verdet = cdl.VERDETVertStack(composites, 'NBR')
Map.clearMap()
Map.centerObject(pnw, 11)
print('VERDET change detection complete')
print('Type:', type(verdet))
"""}),
    ])

    # ================================================================
    # Q11: Wetland change LCMS Land_Use Sankey - Louisiana coast
    # ================================================================
    await run_test(11, "Wetland change Sankey LCMS - Louisiana coast", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
louisiana_coast = ee.Geometry.Point([-90.0, 29.5]).buffer(30000)
lcms = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10')
sankey_df, fig, matrix_dict = cl.summarize_and_chart(
    lcms, louisiana_coast, sankey=True, transition_periods=[1990, 2005, 2024],
    sankey_band_name='Land_Use', min_percentage=0.5, scale=30,
    title='LCMS Land Use Change - Louisiana Coast')
cl.save_chart_html(fig, 'louisiana_sankey.html', sankey=True)
print('Sankey rows:', len(sankey_df))
for label, mdf in matrix_dict.items():
    print(f"\\n{label}")
    print(mdf.to_markdown())
"""}),
    ])

    # ================================================================
    # Q12: Soil moisture anomaly from SMAP - California Central Valley
    # ================================================================
    await run_test(12, "Soil moisture anomaly SMAP - Central Valley CA", [
        ("search_datasets", search_datasets, {"query": "SMAP soil moisture"}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
cv = ee.Geometry.Point([-120.5, 37.0]).buffer(50000)
smap = ee.ImageCollection('NASA/SMAP/SPL4SMGP/007').select('sm_surface')
years = list(range(2015, 2025))
sm_imgs = []
for y in years:
    annual = smap.filterDate(f'{y}-06-01', f'{y}-09-01').mean().rename('soil_moisture')
    sm_imgs.append(annual.set('system:time_start', ee.Date(f'{y}-07-01').millis()))
sm_ts = ee.ImageCollection(sm_imgs)
df, fig = cl.summarize_and_chart(sm_ts, cv, band_names=['soil_moisture'], scale=9000, reducer='mean', title='Summer Soil Moisture - Central Valley')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'cv_soil_moisture.html')
"""}),
    ])

    # ================================================================
    # Q13: Population-weighted wildfire smoke exposure - MODIS AOD
    # ================================================================
    await run_test(13, "Wildfire smoke AOD trend - Western US", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
western_us = ee.Geometry.Point([-120.0, 42.0]).buffer(200000)
modis_aod = ee.ImageCollection('MODIS/061/MCD19A2_GRANULES').select('Optical_Depth_047')
years = list(range(2001, 2024))
aod_imgs = []
for y in years:
    summer_aod = modis_aod.filterDate(f'{y}-07-01', f'{y}-10-01').filterBounds(western_us).mean()
    aod_scaled = summer_aod.multiply(0.001).rename('AOD')
    aod_imgs.append(aod_scaled.set('system:time_start', ee.Date(f'{y}-08-01').millis()))
aod_ts = ee.ImageCollection(aod_imgs)
df, fig = cl.summarize_and_chart(aod_ts, western_us, band_names=['AOD'], scale=10000, reducer='mean', title='Summer AOD (Smoke) - Western US')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'western_us_aod.html')
"""}),
    ])

    # ================================================================
    # Q14: Forest fragmentation metric - Hansen forest + edge detection
    # ================================================================
    await run_test(14, "Forest fragmentation analysis - Rondonia Brazil", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
# Use smaller buffer and coarser scale to avoid timeout
rondonia = ee.Geometry.Point([-63.0, -10.5]).buffer(30000)
hansen = ee.Image('UMD/hansen/global_forest_change_2024_v1_12')
forest_2000 = hansen.select('treecover2000').gt(50).rename('forest')
loss = hansen.select('loss')
forest_now = forest_2000.And(loss.Not()).rename('forest_now')
# Edge detection for fragmentation
edges = forest_now.reduceNeighborhood(ee.Reducer.countDistinct(), ee.Kernel.square(3))
frag_index = edges.gt(1).And(forest_now).rename('fragmented')
Map.clearMap()
Map.addLayer(forest_now.clip(rondonia).selfMask(), {'min':0, 'max':1, 'palette':['green']}, 'Forest Current')
Map.addLayer(frag_index.clip(rondonia).selfMask(), {'min':0, 'max':1, 'palette':['orange']}, 'Fragmented Forest')
Map.addLayer(loss.clip(rondonia).selfMask(), {'min':0, 'max':1, 'palette':['red']}, 'Forest Loss')
Map.centerObject(rondonia, 10)
# Use scale=100 to avoid timeout on large area
df, fig = cl.summarize_and_chart(
    forest_now.addBands(frag_index).addBands(loss),
    rondonia, band_names=['forest_now','fragmented','loss'], scale=100, reducer='mean',
    title='Forest Fragmentation - Rondonia')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q15: Multi-index anomaly detection - Landsat + NDVI/NBR/NDMI zscore
    # ================================================================
    await run_test(15, "Spectral anomaly detection 2020 derecho Iowa", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
iowa_derecho = ee.Geometry.Point([-91.5, 42.0]).buffer(30000)
# Before and after composites around August 2020 derecho
pre = gil.getLandsatWrapper(iowa_derecho, 2019, 2019, startJulian=213, endJulian=273)['processedComposites'].first()
post = gil.getLandsatWrapper(iowa_derecho, 2020, 2020, startJulian=213, endJulian=273)['processedComposites'].first()
dndvi = post.select('NDVI').subtract(pre.select('NDVI')).rename('dNDVI')
dnbr = post.select('NBR').subtract(pre.select('NBR')).rename('dNBR')
dndmi = post.select('NDMI').subtract(pre.select('NDMI')).rename('dNDMI')
changes = dndvi.addBands(dnbr).addBands(dndmi)
Map.clearMap()
Map.addLayer(dndvi.clip(iowa_derecho), {'min':-0.5, 'max':0.2, 'palette':['red','white','green']}, 'dNDVI Derecho')
Map.centerObject(iowa_derecho, 10)
df, fig = cl.summarize_and_chart(changes, iowa_derecho, band_names=['dNDVI','dNBR','dNDMI'], scale=30, reducer='mean', title='Spectral Change - 2020 Derecho')
print('Shape:', df.shape)
print(df.to_markdown())
"""}),
    ])

    # ================================================================
    # Q16: Elevation-banded vegetation analysis - Mt Rainier
    # ================================================================
    await run_test(16, "Elevation-banded NDVI analysis - Mt Rainier", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
rainier = ee.Geometry.Point([-121.76, 46.85]).buffer(15000)
dem = ee.Image('USGS/SRTMGL1_003').select('elevation')
composites = gil.getLandsatWrapper(rainier, 2023, 2023, startJulian=182, endJulian=258)['processedComposites'].first()
ndvi = composites.select('NDVI')
# Create elevation zones
elev_zones = dem.expression(
    "b(0) < 1000 ? 1 : (b(0) < 1500 ? 2 : (b(0) < 2000 ? 3 : 4))"
).rename('elev_zone').toByte()
# Combine
combined = elev_zones.addBands(ndvi)
Map.clearMap()
Map.addLayer(ndvi.clip(rainier), {'min':0, 'max':0.8, 'palette':['brown','yellow','green']}, 'NDVI 2023')
Map.addLayer(elev_zones.clip(rainier), {'min':1, 'max':4, 'palette':['green','yellow','orange','white']}, 'Elevation Zones')
Map.centerObject(rainier, 12)
# Chart NDVI per zone using FeatureCollection
zones = ee.FeatureCollection([
    ee.Feature(rainier, {'name': f'Zone {i}', 'zone': i}) for i in range(1, 5)
])
print('Elevation-banded analysis complete. Map layers added.')
print('DEM range:', dem.reduceRegion(ee.Reducer.minMax(), rainier, 30).getInfo())
"""}),
    ])

    # ================================================================
    # Q17: Sea surface temperature trend - Gulf of Mexico
    # ================================================================
    await run_test(17, "Sea surface temperature trend - Gulf of Mexico", [
        ("search_datasets", search_datasets, {"query": "sea surface temperature NOAA"}),
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
gulf = ee.Geometry.Point([-90.0, 26.0]).buffer(100000)
sst = ee.ImageCollection('NOAA/CDR/OISST/V2_1').select('sst')
years = list(range(1982, 2025))
sst_imgs = []
for y in years:
    summer = sst.filterDate(f'{y}-06-01', f'{y}-09-01').mean()
    sst_scaled = summer.multiply(0.01).rename('SST_C')
    sst_imgs.append(sst_scaled.set('system:time_start', ee.Date(f'{y}-07-01').millis()))
sst_ts = ee.ImageCollection(sst_imgs)
df, fig = cl.summarize_and_chart(sst_ts, gulf, band_names=['SST_C'], scale=25000, reducer='mean', title='Summer SST - Gulf of Mexico 1982-2024')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'gulf_sst.html')
"""}),
    ])

    # ================================================================
    # Q18: CCDC-based change detection - Willamette Valley OR
    # ================================================================
    await run_test(18, "CCDC change detection workflow - Willamette Valley OR", [
        ("list_examples", list_examples, {"filter": "CCDC"}),
        ("get_api_reference", get_api_reference, {"module": "changeDetectionLib", "function_name": "ccdcChangeDetection"}),
        ("run_code", run_code, {"code": """
import geeViz.changeDetectionLib as cdl
will_valley = ee.Geometry.Point([-123.0, 44.5]).buffer(10000)
# Step 1: Get Landsat scenes (not composites) for CCDC
result = gil.getLandsatWrapper(will_valley, 2000, 2024, startJulian=152, endJulian=273)
allScenes = result['processedScenes']
# Step 2: Run CCDC algorithm (note: param is 'lambda' not 'lambda_')
ccdcParams = {
    'collection': allScenes.select(['nir','swir1','swir2','NDVI','NBR']),
    'breakpointBands': ['NDVI','NBR'],
    'minObservations': 6,
    'chiSquareProbability': 0.99,
    'minNumOfYearsScaler': 1.33,
    'dateFormat': 2,
    'maxIterations': 25000,
}
ccdc = ee.Image(ee.Algorithms.TemporalSegmentation.Ccdc(**ccdcParams))
# Step 3: Extract change
changeObj = cdl.ccdcChangeDetection(ccdc, 'NBR')
Map.clearMap()
Map.addLayer(changeObj['mostRecent']['loss']['year'], {'min':2000, 'max':2024, 'palette':cdl.lossYearPalette}, 'CCDC Loss Year')
Map.addLayer(changeObj['mostRecent']['gain']['year'], {'min':2000, 'max':2024, 'palette':cdl.gainYearPalette}, 'CCDC Gain Year')
Map.centerObject(will_valley, 12)
print('CCDC change detection complete')
print('Change keys:', list(changeObj.keys()))
"""}),
    ])

    # ================================================================
    # Q19: DEM-derived terrain metrics + hillshade
    # ================================================================
    await run_test(19, "Terrain analysis slope/aspect/hillshade - Grand Canyon", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
gc = ee.Geometry.Point([-112.1, 36.1]).buffer(20000)
dem = ee.Image('USGS/SRTMGL1_003').select('elevation')
slope = ee.Terrain.slope(dem).rename('slope')
aspect = ee.Terrain.aspect(dem).rename('aspect')
hillshade = ee.Terrain.hillshade(dem).rename('hillshade')
terrain = dem.addBands(slope).addBands(aspect).addBands(hillshade)
Map.clearMap()
Map.addLayer(hillshade.clip(gc), {'min':0, 'max':255}, 'Hillshade')
Map.addLayer(slope.clip(gc), {'min':0, 'max':45, 'palette':['green','yellow','red']}, 'Slope')
Map.addLayer(dem.clip(gc), {'min':700, 'max':2500, 'palette':['green','yellow','brown','white']}, 'Elevation')
Map.centerObject(gc, 11)
df, fig = cl.summarize_and_chart(terrain, gc, band_names=['elevation','slope','aspect'], scale=30, reducer='mean', title='Terrain Metrics - Grand Canyon')
print('Shape:', df.shape)
print(df.to_markdown())
cl.save_chart_html(fig, 'grand_canyon_terrain.html')
"""}),
    ])

    # ================================================================
    # Q20: Complex multi-step: fire -> vegetation recovery -> land cover change
    # ================================================================
    await run_test(20, "Multi-step fire->recovery->LC change - Camp Fire Paradise CA", [
        ("run_code", run_code, {"code": """
from geeViz.outputLib import charts as cl
paradise = ee.Geometry.Point([-121.6, 39.76]).buffer(15000)

# Step 1: Get composites for full period (single call, not per-year loop)
composites = gil.getLandsatWrapper(paradise, 2017, 2024, startJulian=182, endJulian=258)['processedComposites']

# Step 2: Burn severity from dNBR (2017 pre-fire vs 2019 post-fire)
pre = composites.filter(ee.Filter.calendarRange(2017, 2017, 'year')).first()
post = composites.filter(ee.Filter.calendarRange(2019, 2019, 'year')).first()
dnbr = pre.select('NBR').subtract(post.select('NBR')).rename('dNBR')
print('Step 1 - dNBR computed')

# Step 3: NDVI/NBR recovery trajectory from composites
df_recovery, fig_recovery = cl.summarize_and_chart(composites, paradise, band_names=['NDVI','NBR'], scale=30, title='Post-Fire Recovery - Camp Fire')
print('Step 2 - Recovery trajectory:')
print(df_recovery.to_markdown())

# Step 3: LCMS land cover Sankey pre/post fire
lcms = ee.ImageCollection('USFS/GTAC/LCMS/v2024-10')
sankey_df, fig_sankey, matrix_dict = cl.summarize_and_chart(
    lcms, paradise, sankey=True, transition_periods=[2017, 2023],
    sankey_band_name='Land_Cover', min_percentage=0.5, scale=30,
    title='LCMS LC Transition - Camp Fire')
print('Step 3 - Land cover transitions:')
for label, mdf in matrix_dict.items():
    print(f"\\n{label}")
    print(mdf.to_markdown())

# Map
Map.clearMap()
Map.addLayer(dnbr.clip(paradise), {'min':-0.3, 'max':0.8, 'palette':['green','yellow','orange','red']}, 'dNBR')
Map.centerObject(paradise, 11)

# Save outputs
cl.save_chart_html(fig_recovery, 'camp_fire_recovery.html')
cl.save_chart_html(fig_sankey, 'camp_fire_sankey.html', sankey=True)
print('All outputs saved.')
""", "timeout": 180}),
    ])

    # ================================================================
    # SUMMARY
    # ================================================================
    log("\n" + "="*70)
    log("FINAL RESULTS")
    log("="*70)

    for q in sorted(results.keys()):
        r = results[q]
        tools = ", ".join(t["tool"] for t in r["tool_calls"])
        status_icon = "PASS" if r["status"] == "PASS" else "FAIL"
        log(f"Q{q:3d} [{status_icon:4s}] ({r['time']:6.1f}s) {r['description']}")
        log(f"      Tools: {tools}")
        if r["errors"]:
            for e in r["errors"]:
                log(f"      ERROR: {e[:200]}")

    passed = sum(1 for r in results.values() if r["status"] == "PASS")
    total = len(results)
    log(f"\n{passed}/{total} PASSED")
    log(f"\nText log: {TEXT_LOG}")
    log(f"Results JSON: {RESULTS_FILE}")

    # Write results JSON
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
