#Example of how to get Landsat data using the getImagesLib and view outputs using the Python visualization tools
#Acquires Landsat data and then adds them to the viewer
####################################################################################################
import os,sys
sys.path.append(os.getcwd())

#Module imports
from  geeViz.getImagesLib import *
Map.clearMap()
####################################################################################################
#Define user parameters:

#1. Specify study area: Study area
#Can specify a country, provide a fusion table  or asset table (must add 
#.geometry() after it), or draw a polygon and make studyArea = drawnPolygon
studyArea =  ee.Feature(ee.Geometry.Polygon(\
        [[[-121.72925686636518, 39.25666609688575],\
          [-121.72925686636518, 39.00526300299732],\
          [-121.09204983511518, 39.00526300299732],\
          [-121.09204983511518, 39.25666609688575]]]))

#2. Update the startJulian and endJulian variables to indicate your seasonal 
#constraints. This supports wrapping for tropics and southern hemisphere.
#startJulian: Starting Julian date 
#endJulian: Ending Julian date
startJulian = 190
endJulian = 250

#3. Specify start and end years for all analyses
#More than a 3 year span should be provided for time series methods to work 
#well. If using Fmask as the cloud/cloud shadow masking method, this does not 
#matter
startYear = 2012
endYear = 2019

#4. Specify an annual buffer to include imagery from the same season 
#timeframe from the prior and following year. timeBuffer = 1 will result 
#in a 3 year moving window
timebuffer = 1

# 5. Specify the weights to be used for the moving window created by timeBuffer
#For example- if timeBuffer is 1, that is a 3 year moving window
#If the center year is 2000, then the years are 1999,2000, and 2001
#In order to overweight the center year, you could specify the weights as
#[1,5,1] which would duplicate the center year 5 times and increase its weight for
#the compositing method
weights = [1,5,1]



#6. Choose medoid or median compositing method. 
#Median tends to be smoother, while medoid retains 
#single date of observation across all bands
#If not exporting indices with composites to save space, medoid should be used
compositingMethod = 'medoid'

#7. Choose Top of Atmospheric (TOA) or Surface Reflectance (SR) 
#Specify TOA or SR
#Current implementation does not support Fmask for TOA
toaOrSR = 'SR'

#8. Choose whether to include Landat 7
#Generally only included when data are limited
includeSLCOffL7 = False

#9. Whether to defringe L5
#Landsat 5 data has fringes on the edges that can introduce anomalies into 
#the analysis.  This method removes them, but is somewhat computationally expensive
defringeL5 = False

# 10. Choose cloud/cloud shadow masking method
# Choices are a series of booleans for cloudScore, TDOM, and elements of Fmask
#Fmask masking options will run fastest since they're precomputed
#CloudScore runs pretty quickly, but does look at the time series to find areas that 
#always have a high cloudScore to reduce comission errors- this takes some time
#and needs a longer time series (>5 years or so)
#TDOM also looks at the time series and will need a longer time series
applyCloudScore = False
applyFmaskCloudMask = True

applyTDOM = False
applyFmaskCloudShadowMask = True

applyFmaskSnowMask = False

#11. Cloud and cloud shadow masking parameters.
#If cloudScoreTDOM is chosen
#cloudScoreThresh: If using the cloudScoreTDOMShift method-Threshold for cloud 
#   masking (lower number masks more clouds.  Between 10 and 30 generally 
#   works best)
cloudScoreThresh = 20

#Whether to find if an area typically has a high cloudScore
#If an area is always cloudy, this will result in cloud masking omission
#For bright areas that may always have a high cloudScore
#but not actually be cloudy, this will result in a reduction of commission errors
#This procedure needs at least 5 years of data to work well
performCloudScoreOffset = False

#If performCloudScoreOffset = true:
#ercentile of cloud score to pull from time series to represent a minimum for 
#the cloud score over time for a given pixel. Reduces comission errors over 
#cool bright surfaces. Generally between 5 and 10 works well. 0 generally is a
#bit noisy but may be necessary in persistently cloudy areas
cloudScorePctl = 10

#zScoreThresh: Threshold for cloud shadow masking- lower number masks out 
#less. Between -0.8 and -1.2 generally works well
zScoreThresh = -1

#shadowSumThresh: Sum of IR bands to include as shadows within TDOM and the 
#   shadow shift method (lower number masks out less)
shadowSumThresh = 0.35

#contractPixels: The radius of the number of pixels to contract (negative 
#   buffer) clouds and cloud shadows by. Intended to eliminate smaller cloud 
#   patches that are likely errors
#(1.5 results in a -1 pixel buffer)(0.5 results in a -0 pixel buffer)
#(1.5 or 2.5 generally is sufficient)
contractPixels = 1.5

#dilatePixels: The radius of the number of pixels to dilate (buffer) clouds 
#   and cloud shadows by. Intended to include edges of clouds/cloud shadows 
#   that are often missed
#(1.5 results in a 1 pixel buffer)(0.5 results in a 0 pixel buffer)
#(2.5 or 3.5 generally is sufficient)
dilatePixels = 2.5

#Choose the resampling method: 'near', 'bilinear', or 'bicubic'
#Defaults to 'near'
#If method other than 'near' is chosen, any map drawn on the fly that is not
#reprojected, will appear blurred
#Use .reproject to view the actual resulting image (this will slow it down)
resampleMethod = 'near'

#12. correctIllumination: Choose if you want to correct the illumination using
#Sun-Canopy-Sensor+C correction. Additionally, choose the scale at which the
#correction is calculated in meters.
correctIllumination = False
correctScale = 250#Choose a scale to reduce on- 250 generally works well

#13. Export params
#Whether to export composites
exportComposites = False

#Set up Names for the export
outputName = 'Landsat'

#Provide location composites will be exported to
#This should be an asset folder, or more ideally, an asset imageCollection
exportPathRoot = 'users/ianhousman/test/changeCollection'



#CRS- must be provided.  
#Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
#WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
crs = 'EPSG:5070'

#Specify transform if scale is None and snapping to known grid is needed
transform = [30,0,-2361915.0,0,-30,3177735.0]

#Specify scale if transform is None
scale = None
####################################################################################################
#End user parameters
####################################################################################################
####################################################################################################
####################################################################################################
#Start function calls
####################################################################################################
####################################################################################################
#Call on master wrapper function to get Landat scenes and composites
lsAndTs = getLandsatWrapper(studyArea.geometry(),startYear,endYear,startJulian,endJulian,\
  timebuffer,weights,compositingMethod,\
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,\
  applyFmaskCloudShadowMask,applyFmaskSnowMask,\
  cloudScoreThresh,performCloudScoreOffset,cloudScorePctl,\
  zScoreThresh,shadowSumThresh,\
  contractPixels,dilatePixels,\
  correctIllumination,correctScale,\
  exportComposites,outputName,exportPathRoot,crs,transform,scale,resampleMethod)

#Separate into scenes and composites for subsequent analysis
processedScenes = lsAndTs[0]
processedComposites = lsAndTs[1]
Map.addLayer(processedComposites.select(['NDVI','NBR']),{'addToLegend':'false'},'Time Series (NBR and NDVI)',False)
for year in range(startYear + timebuffer      ,endYear + 1 - timebuffer ):
     t = processedComposites.filter(ee.Filter.calendarRange(year,year,'year')).mosaic()
     Map.addLayer(t,vizParamsFalse,str(year),'False')

####################################################################################################
#Load the study region
Map.addLayer(studyArea, {'palette': '0000FF'}, "Study Area", False)
Map.centerObject(studyArea)
####################################################################################################
####################################################################################################
Map.view()