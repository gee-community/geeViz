"""
   Copyright 2025 Ian Housman

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

# Example of how to visualize CCDC outputs using the Python visualization tools
# Adds change products and fitted harmonics from CCDC output to the viewer
# The general workflow for CCDC is to run the CCDCWrapper.py script, and then either utilize the harmonic model for a given date
# or to use the breaks for change detection. All of this is demonstrated in this example
####################################################################################################
import os, sys

sys.path.append(os.getcwd())

# Module imports
import geeViz.getImagesLib as getImagesLib
import geeViz.changeDetectionLib as changeDetectionLib

ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()
####################################################################################################
# Bring in ccdc image asset
# This is assumed to be an image of arrays that is returned from the ee.Algorithms.TemporalSegmentation.Ccdc method
ccdcBands = [
    "tStart",
    "tEnd",
    "tBreak",
    "changeProb",
    "red.*",
    "nir.*",
    "swir1.*",
    "swir2.*",
    "NDVI.*",
    "NBR.*",
]
ccdcImg1 = ee.ImageCollection("projects/lcms-292214/assets/CONUS-LCMS/Base-Learners/CCDC-Collection-1984-2022").select(ccdcBands).mosaic()
ccdcImg2 = ee.ImageCollection("projects/lcms-292214/assets/CONUS-LCMS/Base-Learners/CCDC-Feathered-Collection").select(ccdcBands).mosaic()


# Important parameters - when to feather the two together
# Has to fall within the overlapping period of the two runs
# In general, the longer the period, the better.
# Keeping it away from the very first and very last year of either of the runs is a good idea
featheringStartYear = 2014
featheringEndYear = 2021

# We will be visualizing both dense (multiple per year) and annual (one per year) outputs
# We will set up different date ranges for each of these
# Set a date range and date step (proportion of year - 1 = annual, 0.1 = 10 images per year)
# 245 is a good startJulian and endJulian if step = 1. Set startJulian to 1 and endJulian to 365 and step to 0.1 to see seasonality
annualStartYear = 1984
annualEndYear = 2024
annualStartJulian = 245
annualEndJulian = 245
annualStep = 1

denseStartYear = 2012
denseEndYear = 2024
denseStartJulian = 1
denseEndJulian = 365
denseStep = 0.1

# Specify which harmonics to use when predicting the CCDC model
# CCDC exports the first 3 harmonics (1 cycle/yr, 2 cycles/yr, and 3 cycles/yr)
# If you only want to see yearly patterns, specify [1]
# If you would like a tighter fit in the predicted value, include the second or third harmonic as well [1,2,3]
whichHarmonics = [1, 2, 3]

# Whether to fill gaps between segments' end year and the subsequent start year to the break date
fillGaps = False

# Specify which band to use for loss and gain.
# This is most important for the loss and gain magnitude since the year of change will be the same for all years
changeDetectionBandName = "NDVI"


# Choose whether to show the most recent ('mostRecent') or highest magnitude ('highestMag') CCDC break
sortingMethod = "mostRecent"
####################################################################################################

# Add the raw array image
Map.addLayer(ccdcImg1, {"opacity": 0,"addToLegend":False}, "Raw CCDC Output 1984-2022", False)
Map.addLayer(ccdcImg2, {"opacity": 0,"addToLegend":False}, "Raw CCDC Output 2014-2024", False)

# Extract the change years and magnitude
changeObj = changeDetectionLib.ccdcChangeDetection(ccdcImg1, changeDetectionBandName)

Map.addLayer(
    changeObj[sortingMethod]["loss"]["year"],
    {"min": annualStartYear, "max": annualEndYear, "palette": changeDetectionLib.lossYearPalette},
    "Loss Year",
)
Map.addLayer(
    changeObj[sortingMethod]["loss"]["mag"],
    {"min": -0.5, "max": -0.1, "palette": changeDetectionLib.lossMagPalette},
    "Loss Mag",
    False,
)
Map.addLayer(
    changeObj[sortingMethod]["gain"]["year"],
    {"min": annualStartYear, "max": annualEndYear, "palette": changeDetectionLib.gainYearPalette},
    "Gain Year",
)
Map.addLayer(
    changeObj[sortingMethod]["gain"]["mag"],
    {"min": 0.05, "max": 0.2, "palette": changeDetectionLib.gainMagPalette},
    "Gain Mag",
    False,
)

# Apply the CCDC harmonic model across a time series
# First get a time series of time images
timeImagesDense = changeDetectionLib.simpleGetTimeImageCollection(denseStartYear, denseEndYear, denseStartJulian, denseEndJulian, denseStep)
timeImagesAnnual = changeDetectionLib.simpleGetTimeImageCollection(annualStartYear, annualEndYear, annualStartJulian, annualEndJulian, annualStep)


# Choose which band to show
fitted_band = "NDVI_CCDC_fitted"


# Get fitted for early, late, and combined
annualFittedFeathered = changeDetectionLib.predictCCDC([ccdcImg1, ccdcImg2], timeImagesAnnual, fillGaps, whichHarmonics, featheringStartYear, featheringEndYear)
annualFittedEarly = changeDetectionLib.predictCCDC(ccdcImg1, timeImagesAnnual, fillGaps, whichHarmonics)
annualFittedLate = changeDetectionLib.predictCCDC(ccdcImg2, timeImagesAnnual, fillGaps, whichHarmonics)

denseFittedFeathered = changeDetectionLib.predictCCDC([ccdcImg1, ccdcImg2], timeImagesDense, fillGaps, whichHarmonics, featheringStartYear, featheringEndYear)
denseFittedEarlyAllBands = changeDetectionLib.predictCCDC(ccdcImg1, timeImagesDense, fillGaps, whichHarmonics)
denseFittedLate = changeDetectionLib.predictCCDC(ccdcImg2, timeImagesDense, fillGaps, whichHarmonics)


# Give each unique band names
annualFittedFeathered = annualFittedFeathered.select([fitted_band], [f"{fitted_band}_Combined"])
annualFittedEarly = annualFittedEarly.select([fitted_band], [f"{fitted_band}_Early"])
annualFittedLate = annualFittedLate.select([fitted_band], [f"{fitted_band}_Late"])

denseFittedFeathered = denseFittedFeathered.select([fitted_band], [f"{fitted_band}_Combined"])
denseFittedEarly = denseFittedEarlyAllBands.select([fitted_band], [f"{fitted_band}_Early"])
denseFittedLate = denseFittedLate.select([fitted_band], [f"{fitted_band}_Late"])


# Join all 3
annualJoined = annualFittedEarly.linkCollection(annualFittedLate, [f"{fitted_band}_Late"], None, "system:time_start")
annualJoined = annualJoined.linkCollection(annualFittedFeathered, [f"{fitted_band}_Combined"], None, "system:time_start")

denseJoined = denseFittedEarly.linkCollection(denseFittedLate, [f"{fitted_band}_Late"], None, "system:time_start")
denseJoined = denseJoined.linkCollection(denseFittedFeathered, [f"{fitted_band}_Combined"], None, "system:time_start")

# Show on map
Map.addLayer(annualJoined, {"reducer": ee.Reducer.mean(), "min": 0.3, "max": 0.8}, "Combined CCDC Annual", True)
Map.addLayer(denseJoined, {"reducer": ee.Reducer.mean(), "min": 0.3, "max": 0.8}, "Combined CCDC Dense", True)


# Synthetic composites visualizing
# Take common false color composite bands and visualize them for the next to the last year

# First get the bands of predicted bands and then split off the name
fittedBns = denseFittedEarlyAllBands.select([".*_fitted.*"]).first().bandNames()
bns = fittedBns.map(lambda bn: ee.String(bn).split("_").get(0))

# Filter down to the next to the last year and a summer date range
exampleYear = 2019
syntheticComposites = denseFittedEarlyAllBands.select(fittedBns, bns).filter(ee.Filter.calendarRange(exampleYear, exampleYear, "year"))
# .filter(ee.Filter.calendarRange(190,250)).first()

# Visualize output as you would a composite
getImagesLib.vizParamsFalse["dateFormat"] = "YY-MM-dd"
getImagesLib.vizParamsFalse["advanceInterval"] = "day"
Map.addTimeLapse(
    syntheticComposites,
    getImagesLib.vizParamsFalse,
    f"Synthetic Composite Time Lapse {exampleYear}",
)

####################################################################################################
Map.turnOnInspector()
Map.setCenter(-86.6, 35, 10)
Map.view()
