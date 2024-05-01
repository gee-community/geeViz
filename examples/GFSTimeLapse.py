"""
   Copyright 2023 Ian Housman

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

# Example of how visualize GFS time lapses
# Shows the most recent GFS forecast run
####################################################################################################
import os, sys, math, datetime

sys.path.append(os.getcwd())

# Module imports
import geeViz.getImagesLib as getImagesLib

ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()
####################################################################################################
# Find most recent forecast to show
today = ee.Date(datetime.datetime.now())

# Specify which forecasts to show (by hours from forecast time)
which_hours = list(range(0, 120 + 1, 6))
####################################################################################################
# Bring in GFS
gfs = ee.ImageCollection("NOAA/GFS0P25").filter(
    ee.Filter.gt("creation_time", today.advance(-1, "day").millis())
)

# Get the most recent run
most_recent_forecast = ee.Number.parse(
    gfs.aggregate_histogram("creation_time").keys().reduce(ee.Reducer.max())
)

# Filter to only include the most recent forecast run and the specified forecast hours
gfs = gfs.filter(ee.Filter.eq("creation_time", most_recent_forecast)).filter(
    ee.Filter.inList("forecast_hours", which_hours)
)


# Function to convert wind vectors to direction and magnitude (speed)
def getSpeedDirection(gfs):
    speed = gfs.select(["u.*"]).hypot(gfs.select(["v.*"])).divide(1000).multiply(3600)
    direction = (
        gfs.select(["u.*"])
        .atan2(gfs.select(["v.*"]))
        .divide(math.pi)
        .add(1)
        .multiply(180)
    )
    return (
        gfs.addBands(ee.Image.cat([speed, direction]).rename(["Speed", "Direction"]))
        .copyProperties(gfs)
        .set("system:time_start", gfs.get("forecast_time"))
    )


# Convert to wind vectors
gfs = gfs.map(getSpeedDirection)

# Pulled from https://github.com/gee-community/ee-palettes
cmOceanThermal = ["042333", "2c3395", "744992", "b15f82", "eb7958", "fbb43d", "e8fa5b"]
cmOceanSpeed = ["fffdcd", "e1cd73", "aaac20", "5f920c", "187328", "144b2a", "172313"]
cmOceanTempo = ["fff6f4", "c3d1ba", "7db390", "2a937f", "156d73", "1c455b", "151d44"]
cmOceanDeep = ["fdfecc", "a5dfa7", "5dbaa4", "488e9e", "3e6495", "3f396c", "281a2c"]

# Set up a circular color ramp that's appropriate for direction
windDirectionPalette = [i for i in cmOceanDeep]
cmOceanDeep.reverse()
windDirectionPalette.extend(cmOceanDeep)
cmOceanDeep.reverse()

# Add collections to the map
Map.addTimeLapse(
    gfs.select(["temperature_2m_above_ground"]),
    {
        "min": -20,
        "max": 40,
        "palette": cmOceanThermal,
        "dateFormat": "YY-MM-dd HH",
        "advanceInterval": "hour",
        "legendLabelLeftAfter": "C",
        "legendLabelRightAfter": "C",
    },
    "Temperature",
)
Map.addTimeLapse(
    gfs.select(["precipitable_water_entire_atmosphere"]),
    {
        "min": 0,
        "max": 30,
        "palette": cmOceanTempo,
        "dateFormat": "YY-MM-dd HH",
        "advanceInterval": "hour",
        "legendLabelLeftAfter": "kg/m^2",
        "legendLabelRightAfter": "kg/m^2",
    },
    "Precipitable Water",
)


Map.addTimeLapse(
    gfs.select(["Speed"]),
    {
        "min": 0,
        "max": 60,
        "palette": cmOceanSpeed,
        "dateFormat": "YY-MM-dd HH",
        "advanceInterval": "hour",
        "legendLabelLeftAfter": "km/h",
        "legendLabelRightAfter": "km/h",
    },
    "Wind Speed",
)
Map.addTimeLapse(
    gfs.select(["Direction"]),
    {
        "palette": windDirectionPalette,
        "min": 0,
        "max": 360,
        "dateFormat": "YY-MM-dd HH",
        "advanceInterval": "hour",
        "legendLabelLeftAfter": "degrees",
        "legendLabelRightAfter": "degrees",
    },
    "Wind Direction",
)

####################################################################################################
####################################################################################################
# View map
Map.setQueryDateFormat("YYYY-MM-dd HH:mm")
Map.turnOnInspector()
Map.view()
####################################################################################################
####################################################################################################
