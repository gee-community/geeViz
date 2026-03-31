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

# Example of how to visualize WeatherNext forecast time lapses
# Shows deterministic (Graph), ensemble mean + spread (WeatherNext 2),
# and ensemble spaghetti (Gen) forecasts from the most recent model run
#
# WeatherNext collections:
#   - weathernext_2_0_0   : 64-member ensemble, 6h steps, 15-day forecast
#   - 126478713_1_0 (Gen) : 50-member ensemble, 12h steps, 15-day forecast
#   - 59572747_4_0 (Graph): Deterministic, 6h steps, 10-day forecast
####################################################################################################
import os, sys, math, datetime

sys.path.append(os.getcwd())

# Module imports
import geeViz.getImagesLib as getImagesLib
import geeViz.geePalettes as palettes

ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()
####################################################################################################
# Common settings
today = ee.Date(datetime.datetime.now())

# Show first 5 days of forecast (every 6 hours)
which_hours = list(range(6, 120 + 1, 6))

# Palettes from cmocean
cmOceanThermal = palettes.cmocean["Thermal"][7]
cmOceanSpeed = palettes.cmocean["Speed"][7]
cmOceanTempo = palettes.cmocean["Tempo"][7]
cmOceanDeep = palettes.cmocean["Deep"][7]

# Circular color ramp for wind direction
windDirectionPalette = list(cmOceanDeep) + list(reversed(cmOceanDeep))

# Precipitation palette: white -> blue -> purple
precipPalette = ["ffffff", "c6dbef", "9ecae1", "6baed6", "3182bd", "08519c", "4a1486"]

####################################################################################################
# Helper functions
####################################################################################################
def kelvin_to_celsius(img):
    """Convert 2m temperature from Kelvin to Celsius."""
    return img.select(["2m_temperature"]).subtract(273.15).rename(["Temperature_C"]).copyProperties(img, img.propertyNames())


def compute_wind_speed_direction(img, u_band, v_band, prefix=""):
    """Compute wind speed (km/h) and direction (degrees) from u/v components."""
    u = img.select([u_band])
    v = img.select([v_band])
    speed = u.hypot(v).multiply(3.6)  # m/s to km/h
    direction = u.atan2(v).divide(math.pi).add(1).multiply(180)
    name_speed = f"{prefix}Speed" if prefix else "Speed"
    name_dir = f"{prefix}Direction" if prefix else "Direction"
    return img.addBands(
        ee.Image.cat([speed, direction]).rename([name_speed, name_dir])
    ).copyProperties(img, img.propertyNames())


def prep_for_timelapse(img):
    """Set system:time_start to forecast valid time for timelapse display."""
    start = ee.Date(img.get("start_time"))
    fh = ee.Number(img.get("forecast_hour"))
    valid_time = start.advance(fh, "hour")
    return img.set("system:time_start", valid_time.millis())

####################################################################################################
# 1. WeatherNext Graph — Deterministic forecast (single run, no ensemble)
####################################################################################################
print("Loading WeatherNext Graph (deterministic)...")
graph = (
    ee.ImageCollection("projects/gcp-public-data-weathernext/assets/59572747_4_0")
    .filter(ee.Filter.gt("system:time_start", today.advance(-12, "hour").millis()))
    .filter(ee.Filter.inList("forecast_hour", which_hours))
)

# Get the most recent initialization time
graph_init = graph.aggregate_array("start_time").distinct().sort().get(-1)
graph = graph.filter(ee.Filter.eq("start_time", graph_init)).map(prep_for_timelapse)

proj = graph.first().projection().getInfo()
crs = proj["wkt"]

# Temperature (Kelvin -> Celsius)
graph_temp = graph.map(kelvin_to_celsius)

# Wind speed and direction (10m)
graph_wind = graph.map(
    lambda img: compute_wind_speed_direction(img, "10m_u_component_of_wind", "10m_v_component_of_wind")
)

# Precipitation (6-hour accumulated, in meters -> mm)
graph_precip = graph.map(
    lambda img: img.select(["total_precipitation_6hr"])
    .multiply(1000)
    .rename(["Precip_mm"])
    .copyProperties(img, img.propertyNames())
)

# Mean sea level pressure (Pa -> hPa)
graph_mslp = graph.map(
    lambda img: img.select(["mean_sea_level_pressure"])
    .divide(100)
    .rename(["MSLP_hPa"])
    .copyProperties(img, img.propertyNames())
)

print(f"Graph forecast images: {graph.size().getInfo()}")

####################################################################################################
# 2. WeatherNext 2 — Ensemble mean and spread (64 members)
####################################################################################################
print("Loading WeatherNext 2 (64-member ensemble)...")
wn2 = (
    ee.ImageCollection("projects/gcp-public-data-weathernext/assets/weathernext_2_0_0")
    .filter(ee.Filter.gt("system:time_start", today.advance(-12, "hour").millis()))
    .filter(ee.Filter.inList("forecast_hour", which_hours))
)

# Get the most recent initialization time
wn2_init = wn2.aggregate_array("start_time").distinct().sort().get(-1)
wn2 = wn2.filter(ee.Filter.eq("start_time", wn2_init))


def ensemble_stats(hour):
    """Compute ensemble mean and std dev for a given forecast hour."""
    hour = ee.Number(hour)
    members = wn2.filter(ee.Filter.eq("forecast_hour", hour))
    # Temperature
    temp_members = members.map(kelvin_to_celsius)
    temp_mean = temp_members.select(["Temperature_C"]).mean().rename(["Temp_Mean"])
    temp_std = temp_members.select(["Temperature_C"]).reduce(ee.Reducer.stdDev()).rename(["Temp_Spread"])
    # Precipitation
    precip_members = members.map(
        lambda img: img.select(["total_precipitation_6hr"]).multiply(1000).rename(["Precip_mm"]).copyProperties(img, img.propertyNames())
    )
    precip_mean = precip_members.select(["Precip_mm"]).mean().rename(["Precip_Mean"])
    precip_max = precip_members.select(["Precip_mm"]).max().rename(["Precip_Max"])
    # Wind speed
    wind_members = members.map(
        lambda img: compute_wind_speed_direction(img, "10m_u_component_of_wind", "10m_v_component_of_wind")
    )
    speed_mean = wind_members.select(["Speed"]).mean().rename(["Wind_Mean"])
    speed_std = wind_members.select(["Speed"]).reduce(ee.Reducer.stdDev()).rename(["Wind_Spread"])

    # Compute valid time from init + forecast hour
    start = ee.Date(wn2_init)
    valid_time = start.advance(hour, "hour")

    return (
        ee.Image.cat([temp_mean, temp_std, precip_mean, precip_max, speed_mean, speed_std])
        .set("system:time_start", valid_time.millis())
        .set("forecast_hour", hour)
    )


wn2_stats = ee.ImageCollection(ee.List(which_hours).map(ensemble_stats))
print(f"WN2 ensemble stat images: {wn2_stats.size().getInfo()}")

####################################################################################################
# 3. Add layers to map
####################################################################################################
commonViz = {
    "dateFormat": "YY-MM-dd HH",
    "advanceInterval": "hour",
    "canAreaChart": True,
    "areaChartParams": {"scale": 27830, "crs": crs, "minZoomSpecifiedScale": 5},
    "reducer": ee.Reducer.mean(),
}

# --- Deterministic layers (Graph) ---
Map.addTimeLapse(
    graph_temp.select(["Temperature_C"]),
    {
        **commonViz,
        "min": -20,
        "max": 45,
        "palette": cmOceanThermal,
        "legendLabelLeftAfter": "C",
        "legendLabelRightAfter": "C",
    },
    "Graph: Temperature (2m)",
)

Map.addTimeLapse(
    graph_precip.select(["Precip_mm"]),
    {
        **commonViz,
        "min": 0,
        "max": 30,
        "palette": precipPalette,
        "legendLabelLeftAfter": "mm",
        "legendLabelRightAfter": "mm",
    },
    "Graph: Precipitation (6hr)",
)

Map.addTimeLapse(
    graph_wind.select(["Speed"]),
    {
        **commonViz,
        "min": 0,
        "max": 80,
        "palette": cmOceanSpeed,
        "legendLabelLeftAfter": "km/h",
        "legendLabelRightAfter": "km/h",
    },
    "Graph: Wind Speed (10m)",
)

Map.addTimeLapse(
    graph_wind.select(["Direction"]),
    {
        **commonViz,
        "min": 0,
        "max": 360,
        "palette": windDirectionPalette,
        "legendLabelLeftAfter": "deg",
        "legendLabelRightAfter": "deg",
    },
    "Graph: Wind Direction (10m)",
)

Map.addTimeLapse(
    graph_mslp.select(["MSLP_hPa"]),
    {
        **commonViz,
        "min": 980,
        "max": 1040,
        "palette": ["08306b", "2171b5", "6baed6", "c6dbef", "fcbba1", "fb6a4a", "cb181d", "67000d"],
        "legendLabelLeftAfter": "hPa",
        "legendLabelRightAfter": "hPa",
    },
    "Graph: Sea Level Pressure",
)

# --- Ensemble mean layers (WeatherNext 2, 64-member) ---
Map.addTimeLapse(
    wn2_stats.select(["Temp_Mean"]),
    {
        **commonViz,
        "min": -20,
        "max": 45,
        "palette": cmOceanThermal,
        "legendLabelLeftAfter": "C",
        "legendLabelRightAfter": "C",
    },
    "WN2 Ensemble: Temperature Mean",
)

Map.addTimeLapse(
    wn2_stats.select(["Temp_Spread"]),
    {
        **commonViz,
        "min": 0,
        "max": 8,
        "palette": ["000004", "420a68", "932667", "dd513a", "fca50a", "fcffa4"],
        "legendLabelLeftAfter": "C",
        "legendLabelRightAfter": "C",
    },
    "WN2 Ensemble: Temperature Spread (StdDev)",
)

Map.addTimeLapse(
    wn2_stats.select(["Precip_Mean"]),
    {
        **commonViz,
        "min": 0,
        "max": 30,
        "palette": precipPalette,
        "legendLabelLeftAfter": "mm",
        "legendLabelRightAfter": "mm",
    },
    "WN2 Ensemble: Precip Mean (6hr)",
)

Map.addTimeLapse(
    wn2_stats.select(["Precip_Max"]),
    {
        **commonViz,
        "min": 0,
        "max": 50,
        "palette": precipPalette,
        "legendLabelLeftAfter": "mm",
        "legendLabelRightAfter": "mm",
    },
    "WN2 Ensemble: Precip Max (worst-case)",
)

Map.addTimeLapse(
    wn2_stats.select(["Wind_Mean"]),
    {
        **commonViz,
        "min": 0,
        "max": 80,
        "palette": cmOceanSpeed,
        "legendLabelLeftAfter": "km/h",
        "legendLabelRightAfter": "km/h",
    },
    "WN2 Ensemble: Wind Speed Mean",
)

Map.addTimeLapse(
    wn2_stats.select(["Wind_Spread"]),
    {
        **commonViz,
        "min": 0,
        "max": 15,
        "palette": ["000004", "420a68", "932667", "dd513a", "fca50a", "fcffa4"],
        "legendLabelLeftAfter": "km/h",
        "legendLabelRightAfter": "km/h",
    },
    "WN2 Ensemble: Wind Speed Spread (StdDev)",
)

####################################################################################################
# Upper-atmosphere layers (500 hPa geopotential height)
####################################################################################################
# 500 hPa geopotential height is key for synoptic meteorology
# Dividing geopotential by g (9.80665) gives geopotential height in meters
graph_z500 = graph.map(
    lambda img: img.select(["500_geopotential"])
    .divide(9.80665)
    .rename(["Z500_m"])
    .copyProperties(img, img.propertyNames())
)

Map.addTimeLapse(
    graph_z500.select(["Z500_m"]),
    {
        **commonViz,
        "min": 4800,
        "max": 5900,
        "palette": ["08306b", "2171b5", "6baed6", "c6dbef", "fee0d2", "fc9272", "de2d26", "a50f15"],
        "legendLabelLeftAfter": "m",
        "legendLabelRightAfter": "m",
    },
    "Graph: 500 hPa Height",
)

####################################################################################################
# Sea surface temperature
####################################################################################################
graph_sst = graph.map(
    lambda img: img.select(["sea_surface_temperature"])
    .subtract(273.15)
    .rename(["SST_C"])
    .copyProperties(img, img.propertyNames())
)

Map.addTimeLapse(
    graph_sst.select(["SST_C"]),
    {
        **commonViz,
        "min": -2,
        "max": 32,
        "palette": ["03045e", "0077b6", "00b4d8", "90e0ef", "caf0f8", "fef9ef", "fed9b7", "f07167", "d62828"],
        "legendLabelLeftAfter": "C",
        "legendLabelRightAfter": "C",
    },
    "Graph: Sea Surface Temperature",
)

####################################################################################################
# View map
####################################################################################################
Map.setQueryDateFormat("YYYY-MM-dd HH:mm")
Map.turnOnInspector()
Map.view()
