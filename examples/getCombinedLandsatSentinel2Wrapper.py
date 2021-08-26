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

#Example of how to get Landsat data using the getImagesLib and view outputs using the Python visualization tools
#Acquires Landsat data and then adds them to the viewer
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
#Define user parameters:

# Specify study area: Study area
# Can be a featureCollection, feature, or geometry
studyArea = getImagesLib.testAreas['CA']

# Update the startJulian and endJulian variables to indicate your seasonal 
# constraints. This supports wrapping for tropics and southern hemisphere.
# If using wrapping and the majority of the days occur in the second year, the system:time_start will default 
# to June 1 of that year.Otherwise, all system:time_starts will default to June 1 of the given year
# startJulian: Starting Julian date 
# endJulian: Ending Julian date
startJulian = 152
endJulian = 273

# Specify start and end years for all analyses
# More than a 3 year span should be provided for time series methods to work 
# well. If providing pre-computed stats for cloudScore and TDOM, this does not 
# matter
startYear = 2018
endYear = 2021

# Specify an annual buffer to include imagery from the same season 
# timeframe from the prior and following year. timeBuffer = 1 will result 
# in a 3 year moving window. If you want single-year composites, set to 0
timebuffer =0

# Specify the weights to be used for the moving window created by timeBuffer
# For example- if timeBuffer is 1, that is a 3 year moving window
# If the center year is 2000, then the years are 1999,2000, and 2001
# In order to overweight the center year, you could specify the weights as
# [1,5,1] which would duplicate the center year 5 times and increase its weight for
# the compositing method. If timeBuffer = 0, set to [1]
weights = [1]

# Choose medoid or median compositing method. 
# Median tends to be smoother, while medoid retains 
# single date of observation across all bands
# The date of each pixel is stored if medoid is used. This is not done for median
# If not exporting indices with composites to save space, medoid should be used
compositingMethod = 'medoid'

# Choose Top of Atmospheric (TOA) or Surface Reflectance (SR)
# Use caution when combining Landsat and S2 SR data since S2 SR data had terrain correction performed 
toaOrSR = 'TOA'

# Whether to convert S2 images from the military grid reference system(MGRS) tiles to daily mosaics to avoid arbitrary
# MGRS tile artifacts or not. In most cases, it is best to set this to true.
convertToDailyMosaics = True


# Choose whether to include Landat 7
# Generally only included when data are limited
includeSLCOffL7 = True

# Whether to defringe L4 and L5
# Landsat 4 and 5 data have fringes on the edges that can introduce anomalies into 
# the analysis.  This method removes them, but is somewhat computationally expensive
defringeL5 = True

# Choose cloud/cloud shadow masking method
#  Choices are a series of booleans for cloudScore, TDOM, and elements of Fmask
# Fmask masking options will run fastest since they're precomputed
# Fmask cloud mask is generally very good, while the fMask cloud shadow
# mask isn't great. TDOM tends to perform better than the Fmask cloud shadow mask. cloudScore 
# is usually about as good as the Fmask cloud mask overall, but each failes in different instances.
# CloudScore runs pretty quickly, but does look at the time series to find areas that 
# always have a high cloudScore to reduce commission errors- this takes some time
# and needs a longer time series (>5 years or so)
# TDOM also looks at the time series and will need a longer time series
# If pre-computed cloudScore offsets and/or TDOM stats are provided below, cloudScore
# and TDOM will run quite quickly

#CloudScore and TDOM switches- for both Sentinel 2 and Landsat separately
#We generally use cloudScore for Landsat, but not Sentinel 2
applyCloudScoreLandsat = True
applyCloudScoreSentinel2 = False

applyTDOMLandsat = True
applyTDOMSentinel2 = True

#S2 only cloud/cloud shadow masking methods switches- generally do not use these
#QA band method is fast but is generally awful- don't use if you like good composites
#Shadow shift is intended if you don't have a time series to use for TDOM or just want individual images
#It will commit any dark area that the cloud mask is cast over (water, hill shadows, etc)
applyQABand = False
applyShadowShift = False
#Height of clouds to use to project cloud shadows
cloudHeights = ee.List.sequence(500,10000,500)

#Whether to use the pre-computed cloud probabilities to mask
#clouds for Sentinel 2
#This method works really well
applyCloudProbability = True

#If cloudProbability is chosen, choose a threshold 
#(generally somewhere around 40-60 works well)
cloudProbThresh = 40

#Fmask switches- only for Landsat
#Generally we do use these
applyFmaskCloudMask = True
applyFmaskCloudShadowMask = True
applyFmaskSnowMask = False

# Cloud and cloud shadow masking parameters.
# If cloudScore  is chosen
# cloudScoreThresh: If using the cloudScore or cloudProbability method-Threshold for cloud 
#    masking (lower number masks more clouds.  Between 10 and 30 generally 
#    works best)
cloudScoreThresh = 20

#Whether to find if an area typically has a high cloudScore
#If an area is always cloudy, this will result in cloud masking omission
#For bright areas that may always have a high cloudScore
#but not actually be cloudy, this will result in a reduction of commission errors
#This procedure needs at least 5 years of data to work well
performCloudScoreOffset = True

# If performCloudScoreOffset = true:
#Percentile of cloud score to pull from time series to represent a minimum for 
# the cloud score over time for a given pixel. Reduces comission errors over 
# cool bright surfaces. Generally between 5 and 10 works well. 0 generally is a
# bit noisy but may be necessary in persistently cloudy areas
cloudScorePctl = 10

# zScoreThresh: Threshold for cloud shadow masking- lower number masks out 
#    less. Between -0.8 and -1.2 generally works well
zScoreThresh = -1

# shadowSumThresh: Sum of IR bands to include as shadows within TDOM and the 
#    shadow shift method (lower number masks out less)
shadowSumThresh = 0.35

# contractPixels: The radius of the number of pixels to contract (negative 
#    buffer) clouds and cloud shadows by. Intended to eliminate smaller cloud 
#    patches that are likely errors
# (1.5 results in a -1 pixel buffer)(0.5 results in a -0 pixel buffer)
# (1.5 or 2.5 generally is sufficient)
contractPixels = 1.5

# dilatePixels: The radius of the number of pixels to dilate (buffer) clouds 
#    and cloud shadows by. Intended to include edges of clouds/cloud shadows 
#    that are often missed
# (1.5 results in a 1 pixel buffer)(0.5 results in a 0 pixel buffer)
# (2.5 or 3.5 generally is sufficient)
dilatePixels = 2.5

# Choose the resampling method: 'aggregate','near', 'bilinear', or 'bicubic'
# Defaults to 'aggregate' for Sentinel 2 and 'near' for Landsat

# Aggregate is generally useful for aggregating pixels when reprojecting instead of resampling
# A good example would be reprojecting S2 data to 30 m

# If method other than 'near' is chosen, any map drawn on the fly that is not
# reprojected, will appear blurred or not really represented properly
# Use .reproject to view the actual resulting image (this will slow it down)
landsatResampleMethod = 'near'

sentinel2ResampleMethod = 'aggregate'

# Choose whether to use the Chastain et al 2019(https://www.sciencedirect.com/science/article/pii/S0034425718305212)
# harmonization method
# All harmonization models apply a rather small correction and are likely not needed
#Only runs if toaOrSR = 'TOA'
runChastainHarmonization = True

# If available, bring in preComputed cloudScore offsets and TDOM stats
# Set to null if computing on-the-fly is wanted
# These have been pre-computed for all CONUS for Landsat and Setinel 2 (separately)
# and are appropriate to use for any time period within the growing season
# The cloudScore offset is generally some lower percentile of cloudScores on a pixel-wise basis
preComputedCloudScoreOffset = getImagesLib.getPrecomputedCloudScoreOffsets(cloudScorePctl)
preComputedLandsatCloudScoreOffset = preComputedCloudScoreOffset['landsat']
preComputedSentinel2CloudScoreOffset = preComputedCloudScoreOffset['sentinel2']

# The TDOM stats are the mean and standard deviations of the two bands used in TDOM
# By default, TDOM uses the nir and swir1 bands
preComputedTDOMStats = getImagesLib.getPrecomputedTDOMStats()
preComputedLandsatTDOMIRMean = preComputedTDOMStats['landsat']['mean']
preComputedLandsatTDOMIRStdDev = preComputedTDOMStats['landsat']['stdDev']

preComputedSentinel2TDOMIRMean = preComputedTDOMStats['sentinel2']['mean']
preComputedSentinel2TDOMIRStdDev = preComputedTDOMStats['sentinel2']['stdDev']


# Export params
# Whether to export composites
exportComposites = False

#Set up Names for the export
outputName = 'Landsat_Sentinel2_Hybrid'

# Provide location composites will be exported to
# This should be an asset folder, or more ideally, an asset imageCollection
exportPathRoot = 'users/iwhousman/test/compositeCollection'



# CRS- must be provided.  
# Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
# WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
crs = 'EPSG:5070'

# Specify transform if scale is null and snapping to known grid is needed
transform = [10,0,-2361915.0,0,-10,3177735.0]

# Specify scale if transform is null
scale = None
####################################################################################################
#End user parameters
####################################################################################################
####################################################################################################
####################################################################################################
#Start function calls
####################################################################################################
####################################################################################################
processedAndComposites = getImagesLib.getLandsatAndSentinel2HybridWrapper(studyArea,startYear,endYear,startJulian,endJulian,
  timebuffer,weights,compositingMethod,toaOrSR,includeSLCOffL7,defringeL5,
  applyQABand,applyCloudProbability,applyShadowShift,applyCloudScoreLandsat,applyCloudScoreSentinel2,applyTDOMLandsat,applyTDOMSentinel2,applyFmaskCloudMask,applyFmaskCloudShadowMask,applyFmaskSnowMask,
  cloudHeights,cloudScoreThresh,performCloudScoreOffset,cloudScorePctl,
  zScoreThresh,shadowSumThresh,contractPixels,dilatePixels,['nir','swir1'],landsatResampleMethod,sentinel2ResampleMethod,convertToDailyMosaics,runChastainHarmonization,
  False,250,
  exportComposites,outputName,exportPathRoot,crs,transform,scale,
  preComputedLandsatCloudScoreOffset,preComputedLandsatTDOMIRMean,preComputedLandsatTDOMIRStdDev,preComputedSentinel2CloudScoreOffset,preComputedSentinel2TDOMIRMean,preComputedSentinel2TDOMIRStdDev,
  cloudProbThresh);

#Separate into scenes and composites for subsequent analysis
processedScenes = processedAndComposites['processedScenes']
processedComposites = processedAndComposites['processedComposites']

# Map.addLayer(processedComposites.select(['NDVI','NBR']),{'addToLegend':'false'},'Time Series (NBR and NDVI)',False)
for year in range(startYear + timebuffer      ,endYear + 1 - timebuffer ):
     t = processedComposites.filter(ee.Filter.calendarRange(year,year,'year')).mosaic()
     Map.addLayer(t.float(),getImagesLib.vizParamsFalse,str(year),False)
####################################################################################################
#Load the study region
Map.addLayer(studyArea, {'strokeColor': '0000FF'}, "Study Area", True)
Map.centerObject(studyArea)
####################################################################################################
####################################################################################################
Map.view()