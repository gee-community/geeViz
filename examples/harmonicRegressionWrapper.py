"""
   Copyright 2021 Ian Housman

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

#Example of how to seasonality metrics using harmonic regression with Landsat data
#Acquires harmonic regression-based seasonality metrics
####################################################################################################
import os,sys
sys.path.append(os.getcwd())

#Module imports
import geeViz.getImagesLib as getImagesLib
ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()
####################################################################################################
####################################################################################################
# Define user parameters:

# Specify study area: Study area
# Can be a featureCollection, feature, or geometry
studyArea = getImagesLib.testAreas['CA']

# Update the startJulian and endJulian variables to indicate your seasonal 
# constraints. This supports wrapping for tropics and southern hemisphere.
# If using wrapping and the majority of the days occur in the second year, the system:time_start will default 
# to June 1 of that year.Otherwise, all system:time_starts will default to June 1 of the given year
# startJulian: Starting Julian date 
# endJulian: Ending Julian date
startJulian = 1
endJulian = 365

# Specify start and end years for all analyses
# More than a 3 year span should be provided for time series methods to work 
# well. If using Fmask as the cloud/cloud shadow masking method, or providing
# pre-computed stats for cloudScore and TDOM, this does not 
# matter
startYear = 2019
endYear = 2021

# Specify an annual buffer to include imagery from the same season 
# timeframe from the prior and following year. timeBuffer = 1 will result 
# in a 3 year moving window. If you want single-year composites, set to 0
timebuffer =1


# Export params
# Whether to export coefficients
exportCoefficients = False

# Set up Names for the export
outputName = 'Harmonic_Coefficients_'

# Provide location composites will be exported to
# This should be an asset folder, or more ideally, an asset imageCollection
exportPathRoot = 'users/iwhousman/test/coeffCollection'

# CRS- must be provided.  
# Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
# WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
crs = 'EPSG:5070'

# Specify transform if scale is null and snapping to known grid is needed
transform = [30,0,-2361915.0,0,-30,3177735.0]

# Specify scale if transform is None
scale = None


####################################################################################################
####################################################################################################
#Harmonic regression parameters

#Which harmonics to include
#Is a list of numbers of the n PI per year
#Typical assumption of 1 cycle/yr would be [2]
#If trying to overfit, or expected bimodal phenology try adding a higher frequency as well
#ex. [2,4]
whichHarmonics = [2]

#Which bands/indices to run harmonic regression across
indexNames =['swir2','nir','red','NDVI'];#,'NBR','NDMI','nir','swir1','swir2','tcAngleBG'];//['nir','swir1','swir2','NDMI','NDVI','NBR','tcAngleBG'];//['blue','green','red','nir','swir1','swir2','NDMI','NDVI','NBR','tcAngleBG'];

#Choose which band/index to use for visualizing seasonality in hue, saturation, value color space (generally NDVI works best)
seasonalityVizIndexName = 'NDVI'


#Whether to apply a linear detrending of data.  Can be useful if long-term change is not of interest
detrend = True
####################################################################################################
#Ensure seasonalityVizIndexName is included in the indexNames
if seasonalityVizIndexName not in indexNames:indexNames.append(seasonalityVizIndexName)
####################################################################################################
####################################################################################################
####################################################################################################
#Function Calls
#Get all images
allScenes = getImagesLib.getProcessedLandsatScenes(studyArea,startYear,endYear,startJulian,endJulian).select(indexNames)

# Map.addLayer(allScenes,vizParamsFalse,'median')
# Map.view()
# ////////////////////////////////////////////////////////////
# //Iterate across each time window and fit harmonic regression model
coeffCollection = [];
for yr in ee.List.sequence(startYear+timebuffer,endYear-timebuffer,1).getInfo():
  yr = int(yr)
  #Set up dates
  startYearT = yr-timebuffer
  endYearT = yr+timebuffer
  nameStart = str(startYearT) + '_'+str(endYearT)
  
  #Get scenes for those dates
  allScenesT = allScenes.filter(ee.Filter.calendarRange(startYearT,endYearT,'year'))
  print(allScenesT.size().getInfo())
  composite = allScenesT.median()
  Map.addLayer(composite,{'min':0.1,'max':0.4},nameStart+'_median_composite',False)

  seasonalityMedian = composite.select([seasonalityVizIndexName])
 
  #Fit harmonic model
  coeffsPredicted =getImagesLib.getHarmonicCoefficientsAndFit(allScenesT,indexNames,whichHarmonics,detrend)

  
  #Set some properties
  coeffs = coeffsPredicted[0]\
   .set({'system:time_start':ee.Date.fromYMD(yr,6,1).millis(),\
        'timebuffer':timebuffer,\
        'startYearT':startYearT,\
        'endYearT':endYearT,\
        }).float()
  Map.addLayer(coeffs,{},nameStart+ '_coeffs',False)

  #Get predicted values for visualization
  predicted = coeffsPredicted[1]
  Map.addLayer(predicted,{},nameStart+ '_predicted',False);
  
  #Optionally simplify coeffs to phase, amplitude, and date of peak
  if 2 in whichHarmonics :
    pap = ee.Image(getImagesLib.getPhaseAmplitudePeak(coeffs))
    
    
    vals = coeffs.select(['.*_intercept'])
    amplitudes = pap.select(['.*_amplitude'])
    phases = pap.select(['.*_phase'])
    peakJulians = pap.select(['.*peakJulianDay'])
    AUCs = pap.select(['.*AUC'])
    
    Map.addLayer(phases,{},nameStart+ '_phases',False)
    Map.addLayer(amplitudes,{'min':0,'max':0.6},nameStart+ '_amplitudes',False)
    Map.addLayer(AUCs,{'min':0,'max':0.3},nameStart+ '_AUCs',False)
    Map.addLayer(peakJulians,{'min':0,'max':365},nameStart+ '_peakJulians',False)

    #Create synthetic image for peak julian day according the the seasonalityVizIndexName band
    dateImage = ee.Image(yr).add(peakJulians.select([seasonalityVizIndexName + '_peakJulianDay']).divide(365))
    synth = getImagesLib.synthImage(coeffs,dateImage,indexNames,whichHarmonics,detrend);
    Map.addLayer(synth,{'min':0.1,'max':0.4},nameStart + '_Date_of_Max_'+seasonalityVizIndexName+'_Synth_Image',False);
    
    #Turn the HSV data into an RGB image and add it to the map.
    seasonality = ee.Image.cat(phases.select([seasonalityVizIndexName+'.*']).clamp(0,1),amplitudes.select([seasonalityVizIndexName+'.*']).unitScale(0,0.5).clamp(0,1),seasonalityMedian.unitScale(0,0.8).clamp(0,1)).hsvToRgb()
  
    Map.addLayer(seasonality, {'min':0,'max':1}, nameStart+ '_'+seasonalityVizIndexName+'_Seasonality',True);

#   }

  #Export image
  if exportCoefficients:
    if not detrend:
      coeffsOut = coeffs.multiply(1000).int16()
    else:coeffsOut = coeffs.float()

      
    coeffsOut = coeffsOut.copyProperties(coeffs).copyProperties(coeffs,['system:time_start'])


    outName = outputName + str(startYearT) + '_'+ str(endYearT)
    outPath = exportPathRoot + '/' + outName
    getImagesLib.exportToAssetWrapper(coeffs,outName,outPath,'mean',studyArea,scale,crs,transform)
  coeffCollection.append(coeffs)
####################################################################################################
#Load the study region
Map.addLayer(studyArea, {'strokeColor': '0000FF'}, "Study Area", False)
Map.centerObject(studyArea)
####################################################################################################
Map.view()  

