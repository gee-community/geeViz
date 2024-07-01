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

# Example of how to visualize LandTrendr outputs using the Python visualization tools
# LANDTRENDR original paper: https://www.sciencedirect.com/science/article/pii/S0034425710002245
# LANDTRENDR in GEE paper: https://www.mdpi.com/2072-4292/10/5/691
# Takes pre-exported LT stack output and provides a visualization of loss and gain years, duration, and magnitude
# Also charts the LT output time series
####################################################################################################
import os, sys

sys.path.append(os.getcwd())

# Module imports
import geeViz.getImagesLib as gil
import geeViz.changeDetectionLib as cdl

ee = gil.ee
Map = gil.Map
Map.clearMap()
Map.port = 1234
####################################################################################################
# Define user parameters:

# Specify which years to look at
# Available years are 1984-2021
startYear = 1984
endYear = 2023

# Which property stores which band/index LandTrendr was run across
bandPropertyName = "band"

# Specify which bands to run across
# Set to None to run all available bands
# Available bands include: ['NBR', 'NDMI', 'NDSI', 'NDVI', 'blue', 'brightness', 'green', 'greenness', 'nir', 'red', 'swir1', 'swir2', 'tcAngleBG', 'wetness']
bandNames = None

# Specify if output is an array image or not
arrayMode = True
####################################################################################################
# Bring in LCMS LandTrendr outputs (see other examples that include LCMS final data)
lt = ee.ImageCollection(
    "projects/lcms-tcc-shared/assets/CONUS/Base-Learners/LandTrendr-Collection"
)
print(
    "Available bands/indices:",
    lt.aggregate_histogram(bandPropertyName).keys().getInfo(),
)

lt_props = lt.first().toDictionary().getInfo()
print(lt_props)

# Convert stacked outputs into collection of fitted, magnitude, slope, duration, etc values for each year
# Divide by 10000 (0.0001) so values are back to original values (0-1 or -1-1)
lt_fit = cdl.batchSimpleLTFit(
    lt,
    startYear,
    endYear,
    bandNames,
    bandPropertyName,
    arrayMode,
    lt_props["maxSegments"],
    0.0001,
)

# Vizualize image collection for charting (opacity set to 0 so it will chart but not be visible)
Map.addLayer(lt_fit.select(["NBR_LT_fitted"]), {"opacity": 0}, "LT Fit TS")

# Visualize single year fitted landTrendr composite
# Set to only run if no bandNames are specified
if bandNames == None:
    # Get fitted bandnames
    fitted_bns = lt_fit.select([".*_fitted"]).first().bandNames()
    out_bns = fitted_bns.map(lambda bn: ee.String(bn).split("_").get(0))

    # Filter out next to last year
    lt_synth = lt_fit.select(fitted_bns, out_bns)
    # .filter(ee.Filter.calendarRange(endYear-1,endYear-1,'year')).first()
    gil.vizParamsFalse["reducer"] = ee.Reducer.lastNonNull()
    # Visualize as you would a composite
    Map.addLayer(lt_synth, gil.vizParamsFalse, "Synthetic Composite")


# Iterate across each band to look for areas of change
if bandNames == None:
    bandNames = ["NBR"]
for bandName in bandNames:
    # Do basic change detection with raw LT output
    ltt = lt.filter(ee.Filter.eq(bandPropertyName, bandName)).mosaic()
    ltt = cdl.multLT(ltt, cdl.changeDirDict[bandName] * 0.0001)

    lossMagThresh = -0.15
    lossSlopeThresh = -0.1
    gainMagThresh = 0.1
    gainSlopeThresh = 0.1
    slowLossDurationThresh = 3
    chooseWhichLoss = "largest"
    chooseWhichGain = "largest"
    howManyToPull = 1

    lossGainDict = cdl.convertToLossGain(
        ltt,
        format="arrayLandTrendr",
        lossMagThresh=lossMagThresh,
        lossSlopeThresh=lossSlopeThresh,
        gainMagThresh=gainMagThresh,
        gainSlopeThresh=gainSlopeThresh,
        slowLossDurationThresh=slowLossDurationThresh,
        chooseWhichLoss=chooseWhichLoss,
        chooseWhichGain=chooseWhichGain,
        howManyToPull=howManyToPull,
    )
    lossGainStack = cdl.LTLossGainExportPrep(lossGainDict, indexName=bandName, multBy=1)
    cdl.addLossGainToMap(
        lossGainStack,
        startYear,
        endYear,
        lossMagThresh - 0.7,
        lossMagThresh,
        gainMagThresh,
        gainMagThresh + 0.7,
    )
####################################################################################################
####################################################################################################
# View map
Map.setQueryDateFormat("YYYY")
Map.turnOnInspector()
Map.view()
####################################################################################################
