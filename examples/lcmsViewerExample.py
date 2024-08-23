"""
Based on https://github.com/google/earthengine-community/blob/master/datasets/scripts/LCMS_Visualization.js
 * Copyright 2024 The Google Earth Engine Community Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * 
 * 
 * Example script for visualizing LCMS change summaries, land cover, and land use.
 * 
 * A more in-depth visualization of LCMS products is available at:
 * https://apps.fs.usda.gov/lcms-viewer/
 * 
 * Contact sm.fs.lcms@usda.gov with any questions or specific data requests.
"""

####################################################################################################
# Import modules
import os, sys

sys.path.append(os.getcwd())

import geeViz.geeView as geeView

ee = geeView.ee
Map = geeView.Map

Map.clearMap()
####################################################################################################
#############################################################################
### Define visualization parameters ###
#############################################################################
startYear = 1985
endYear = 2023
lossYearPalette = ["ffffe5", "fff7bc", "fee391", "fec44f", "fe9929", "ec7014", "cc4c02"]
gainYearPalette = ["c5ee93", "00a398"]
durationPalette = ["BD1600", "E2F400", "0C2780"]


lossYearViz = {
    "min": startYear,
    "max": endYear,
    "palette": lossYearPalette,
    "canAreaChart": True,
    "areaChartParams": {"reducer": ee.Reducer.frequencyHistogram()},
}
gainYearViz = {
    "min": startYear,
    "max": endYear,
    "palette": gainYearPalette,
    "canAreaChart": True,
    "areaChartParams": {"reducer": ee.Reducer.frequencyHistogram()},
}
durationViz = {"min": 1, "max": 5, "palette": durationPalette}
#############################################################################
### Define functions ###
#############################################################################

# Convert given code to year that number was present in the image.


def getMostRecentChange(c, code):
    def wrapper(img):
        yr = ee.Date(img.get("system:time_start")).get("year")
        return ee.Image(yr).int16().rename(["year"]).updateMask(img.eq(code)).copyProperties(img, ["system:time_start"])

    return c.map(wrapper)


#############################################################################
### Bring in LCMS annual outputs ###
#############################################################################

lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9")
bandNames = lcms.first().bandNames().getInfo()
lcms_props = lcms.first().toDictionary().getInfo()
print("Available study areas:", lcms.aggregate_histogram("study_area").keys().getInfo())
print("Available LCMS products", bandNames)
print(
    "Learn more about visualization of LCMS products here",
    "https://apps.fs.usda.gov/lcms-viewer/",
)

# Filter out study area
# lcms = lcms.filter(ee.Filter.eq('study_area','CONUS'))

# Set up time periods to compare land cover and land use
earlySpan = [startYear, startYear + 4]
lateSpan = [endYear - 4, endYear]

#############################################################################
### Add full raw model outputs ###
#############################################################################

# Separate products
raw_change = lcms.select(["Change_Raw_.*"])
raw_land_cover = lcms.select(["Land_Cover_Raw_.*"])
raw_land_use = lcms.select(["Land_Use_Raw_.*"])

# Shorten names
raw_change_bns = [bn for bn in bandNames if bn.find("Change_Raw_") > -1]
raw_land_cover_bns = [bn for bn in bandNames if bn.find("Land_Cover_Raw_") > -1]
raw_land_use_bns = [bn for bn in bandNames if bn.find("Land_Use_Raw_") > -1]

raw_change_bns_short = [i.split("_Probability_")[-1] for i in raw_change_bns]
raw_land_cover_bns_short = [i.split("_Probability_")[-1] for i in raw_land_cover_bns]
raw_land_use_bns_short = [i.split("_Probability_")[-1] for i in raw_land_use_bns]

raw_change = raw_change.select(raw_change_bns, raw_change_bns_short)
raw_land_cover = raw_land_cover.select(raw_land_cover_bns, raw_land_cover_bns_short)
raw_land_use = raw_land_use.select(raw_land_use_bns, raw_land_use_bns_short)


# Add to map
Map.addLayer(
    raw_change,
    {
        "min": 0,
        "max": 30,
        "opacity": 0,
        "addToLegend": False,
        "queryParams": {"palette": lcms_props["Change_class_palette"][1:]},
    },
    "Raw LCMS Change Model Probability",
    True,
)
Map.addLayer(
    raw_land_cover,
    {
        "min": 0,
        "max": 30,
        "opacity": 0,
        "addToLegend": False,
        "queryParams": {"palette": lcms_props["Land_Cover_class_palette"]},
    },
    "Raw LCMS Land Cover Model Probability",
    True,
)
Map.addLayer(
    raw_land_use,
    {
        "min": 0,
        "max": 30,
        "opacity": 0,
        "addToLegend": False,
        "queryParams": {"palette": lcms_props["Land_Use_class_palette"]},
    },
    "Raw LCMS Land Use Model Probability",
    True,
)

mtbsBoundaries = ee.FeatureCollection("USFS/GTAC/MTBS/burned_area_boundaries/v1")
mtbsBoundaries = mtbsBoundaries.map(lambda f: f.set("system:time_start", f.get("Ig_Date")))

# For area charting you can select areas to chart a number of ways. One method is using a map layer that is selectable by clicking on each feature.
Map.addSelectLayer(
    mtbsBoundaries,
    {
        # "strokeColor": "00F",
        # "layerType": "geeVectorImage",
        # "selectLayerNameProperty": "Incid_Name",
    },
    "MTBS Fire Boundaries",
)

#############################################################################
### Visualize Land Use change ###
#############################################################################
# Copy properties from original image after reducing collection to retain visualization properties
lu = lcms.select(["Land_Use"])
Map.addLayer(
    lu,
    {
        "autoViz": True,
        "reducer": ee.Reducer.mode(),
        "canAreaChart": True,
        "areaChartParams": {"sankey": True, "line": True},
    },
    "Land Use",
    False,
)
#############################################################################
### Visualize Land Cover change ###
#############################################################################
# Copy properties from original image after reducing collection to retain visualization properties
# Or you can provide a reducer to be applied for map visualization and still be able to query all values of the collection
lc = lcms.select(["Land_Cover"])

Map.addLayer(
    lc,
    {
        "autoViz": True,
        "canAreaChart": True,
        "areaChartParams": {"sankey": True, "line": True},
    },
    "Land Cover",
    False,
)
#############################################################################
### Visualize Change products ###
#############################################################################


# Show LCMS probability composite as an RGB to illustrate where Tree and non tree loss and gain have occured
Map.addLayer(
    lcms.select([".*Probability.*"]),
    {
        "reducer": ee.Reducer.max(),
        "min": 0,
        "max": 30,
        "classLegendDict": {
            "Non-Tree No Change": "000",
            "Tree No Change": "0E0",
            "Non-Tree Fast Loss": "E00",
            "Tree Gain": "0FF",
            "Tree Fast Loss": "FF0",
            "Tree Fast Loss + Gain": "FFF",
        },
        "queryParams": {"palette": lcms_props["Change_class_palette"][1:-1] + lcms_props["Land_Cover_class_palette"][:-1] + lcms_props["Land_Use_class_palette"][:-1]},
        "bands": "Change_Raw_Probability_Fast_Loss,Land_Cover_Raw_Probability_Trees,Change_Raw_Probability_Gain",
    },
    "LCMS Change Composite",
    False,
)


# Select the change band. Land_Cover and Land_Use are also available.
change = lcms.select(["Change"])

# Convert to year collection for a given code.
slowLossYears = getMostRecentChange(change, 2)
fastLossYears = getMostRecentChange(change, 3)
gainYears = getMostRecentChange(change, 4)

# Find the most recent year.
mostRecentSlowLossYear = slowLossYears.max()
mostRecentFastLossYear = fastLossYears.max()
mostRecentGainYear = gainYears.max()

# Find the duration.
slowLossDuration = slowLossYears.count()
fastLossDuration = fastLossYears.count()
gainDuration = gainYears.count()

# Add year summaries to the map.
Map.addLayer(mostRecentSlowLossYear, lossYearViz, "Most Recent Slow Loss Year", True)
Map.addLayer(mostRecentFastLossYear, lossYearViz, "Most Recent Fast Loss Year", True)
Map.addLayer(mostRecentGainYear, gainYearViz, "Most Recent Gain Year", True)

# Add durations to the map.
Map.addLayer(slowLossDuration, durationViz, "Slow Loss Duration", False)
Map.addLayer(fastLossDuration, durationViz, "Fast Loss Duration", False)
Map.addLayer(gainDuration, durationViz, "Gain Duration", False)

justChange = change.map(lambda img: img.updateMask(ee.Image(img.gt(1).And(img.lt(5))).copyProperties(lcms.first())))
# Map.addTimeLapse(
# justChange, {"autoViz": True, "mosaic": True}, "LCMS Change Time Lapse", False
# )


##############################################################################
#### Map setup ###
##############################################################################
Map.centerObject(lcms.filter(ee.Filter.eq("study_area", "CONUS")).first().geometry())
# Map.turnOnInspector()
# Map.setQueryToInfoWindow()
Map.turnOnAutoAreaCharting()
Map.view()
