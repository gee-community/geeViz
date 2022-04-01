"""
   Copyright 2022 Ian Housman

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
import os,sys
sys.path.append(os.getcwd())

#Module imports
import geeViz.getImagesLib as getImagesLib
import geeViz.changeDetectionLib as changeDetectionLib

ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()
####################################################################################################
# Define user parameters:

# Specify which years to look at 
# Available years are 1984-2021
startYear = 1984
endYear = 2021

# Which property stores which band/index LandTrendr was run across
bandPropertyName = 'band'

# Specify which bands to run across
# Set to None to run all available bands
# Available bands include: ['NBR', 'NDMI', 'NDSI', 'NDVI', 'blue', 'brightness', 'green', 'greenness', 'nir', 'red', 'swir1', 'swir2', 'tcAngleBG', 'wetness']
bandNames =['NBR']
####################################################################################################
# Bring in LCMS LandTrendr outputs (see other examples that include LCMS final data)
lt = ee.ImageCollection('projects/lcms-tcc-shared/assets/LandTrendr/LandTrendr-Collection-yesL7-1984-2020');
print('Available bands/indices:',lt.aggregate_histogram(bandPropertyName).keys().getInfo())

# Convert stacked outputs into collection of fitted, magnitude, slope, duration, etc values for each year
lt_fit = changeDetectionLib.batchSimpleLTFit(lt,startYear,endYear,bandNames,bandPropertyName)

# Vizualize image collection for charting (opacity set to 0 so it will chart but not be visible)
Map.addLayer(lt_fit,{'opacity':0},'LT Fit TS')

# Iterate across each band to look for areas of change
for bandName in bandNames:
  #Convert LandTrendr stack to Loss & Gain space
  ltt = lt.filter(ee.Filter.eq(bandPropertyName,bandName)).mosaic()
  fit = ltt.select(['fit.*']).multiply(getImagesLib.changeDirDict[bandName]/10000)
  ltt = ltt.addBands(fit,None,True)
  lossGainDict = changeDetectionLib.convertToLossGain(ltt, \
                                                      format = 'vertStack',\
                                                      lossMagThresh = -0.15,\
                                                      lossSlopeThresh = -0.1,\
                                                      gainMagThresh = 0.1,\
                                                      gainSlopeThresh = 0.1,\
                                                      slowLossDurationThresh = 3,
                                                      chooseWhichLoss = 'largest', 
                                                      chooseWhichGain = 'largest', 
                                                      howManyToPull = 1)

  lossStack = lossGainDict['lossStack']
  gainStack = lossGainDict['gainStack']

 

  #Set up viz params
  vizParamsLossYear = {'min':startYear,'max':endYear,'palette':changeDetectionLib.lossYearPalette}
  vizParamsLossMag = {'min':-0.8 ,'max':-0.15,'palette':list(reversed(changeDetectionLib.lossMagPalette.split(',')))}
  
  vizParamsGainYear = {'min':startYear,'max':endYear,'palette':changeDetectionLib.gainYearPalette}
  vizParamsGainMag = {'min':0.1,'max':0.8,'palette':changeDetectionLib.gainMagPalette}
  
  vizParamsDuration = {'min':1,'max':5,'palette':changeDetectionLib.changeDurationPalette,'legendLabelLeftAfter':'year','legendLabelRightAfter':'years'}

  # Select off the first change detected and visualize outputs
  lossStackI = lossStack.select(['.*_1'])
  gainStackI = gainStack.select(['.*_1'])
 
  Map.addLayer(lossStackI.select(['loss_yr.*']),vizParamsLossYear,bandName +' Loss Year',True)
  Map.addLayer(lossStackI.select(['loss_mag.*']),vizParamsLossMag,bandName +' Loss Magnitude',False)
  Map.addLayer(lossStackI.select(['loss_dur.*']),vizParamsDuration,bandName +' Loss Duration',False)
  
  Map.addLayer(gainStackI.select(['gain_yr.*']),vizParamsGainYear,bandName +' Gain Year',False)
  Map.addLayer(gainStackI.select(['gain_mag.*']),vizParamsGainMag,bandName +' Gain Magnitude',False)
  Map.addLayer(gainStackI.select(['gain_dur.*']),vizParamsDuration,bandName +' Gain Duration',False)

####################################################################################################
####################################################################################################
# View map
Map.turnOnInspector()
Map.view()
####################################################################################################
