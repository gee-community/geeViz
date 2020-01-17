#Example of how to seasonality metrics using harmonic regression with Landsat data
#Acquires harmonic regression-based seasonality metrics
####################################################################################################
import os,sys
sys.path.append(os.getcwd())

#Module imports
from  geeViz.getImagesLib import *
Map.clearMap()
####################################################################################################
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
startJulian = 1
endJulian = 365

#3. Specify start and end years for all analyses
#More than a 3 year span should be provided for time series methods to work 
#well. If using Fmask as the cloud/cloud shadow masking method, this does not 
#matter
startYear = 2017
endYear = 2019

#4. Specify an annual buffer to include imagery from the same season 
#timeframe from the prior and following year. timeBuffer = 1 will result 
#in a 3 year moving window
timebuffer = 1


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

applyFmaskSnowMask = True

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


#Percentile of cloud score to pull from time series to represent a minimum for 
#the cloud score over time for a given pixel. Reduces comission errors over 
#cool bright surfaces. Generally between 5 and 10 works well. 0 generally is a
#bit noisy
cloudScorePctl = 10

#zScoreThresh: Threshold for cloud shadow masking- lower number masks out 
#   less. Between -0.8 and -1.2 generally works well
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

#12. correctIllumination: Choose if you want to correct the illumination using
#Sun-Canopy-Sensor+C correction. Additionally, choose the scale at which the
#correction is calculated in meters.
correctIllumination = False
correctScale = 250#Choose a scale to reduce on- 250 generally works well

#13. Export params
#Whether to export coefficients
exportCoefficients = False

#Set up Names for the export
outputName = 'Harmonic_Coefficients_'

#Provide location composites will be exported to
#This should be an asset folder, or more ideally, an asset imageCollection
exportPathRoot = 'users/iwhousman/test/coeffCollection'

#CRS- must be provided.  
#Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
#WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
crs = 'EPSG:5070'

#Specify transform if scale is null and snapping to known grid is needed
transform = [30,0,-2361915.0,0,-30,3177735.0]

#Specify scale if transform is None
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
allScenes = getProcessedLandsatScenes(studyArea.geometry(),startYear,endYear,startJulian,endJulian,\
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,\
  applyFmaskCloudShadowMask,applyFmaskSnowMask,\
  cloudScoreThresh,performCloudScoreOffset,cloudScorePctl,\
  zScoreThresh,shadowSumThresh,\
  contractPixels,dilatePixels\
  ).select(indexNames)

# Map.addLayer(allScenes.median(),vizParamsFalse,'median')
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
  
  composite = allScenesT.median()
  Map.addLayer(composite,{'min':0.1,'max':0.4},nameStart+'_median_composite',False)

  seasonalityMedian = composite.select([seasonalityVizIndexName])
 
  #Fit harmonic model
  coeffsPredicted =getHarmonicCoefficientsAndFit(allScenesT,indexNames,whichHarmonics,detrend)

  
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
    pap = ee.Image(getPhaseAmplitudePeak(coeffs))
    
    
    vals = coeffs.select(['.*_intercept'])
    amplitudes = pap.select(['.*_amplitude'])
    phases = pap.select(['.*_phase'])
    peakJulians = pap.select(['.*peakJulianDay'])
    AUCs = pap.select(['.*AUC'])
    
    Map.addLayer(phases,{},nameStart+ '_phases',False)
    Map.addLayer(amplitudes,{'min':0,'max':0.6},nameStart+ '_amplitudes',False)
    Map.addLayer(AUCs,{'min':0,'max':0.3},nameStart+ '_AUCs',False)
    Map.addLayer(peakJulians,{'min':0,'max':365},nameStart+ '_peakJulians',False)

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
    exportToAssetWrapper(coeffs,outName,outPath,'mean',studyArea,scale,crs,transform)
  coeffCollection.append(coeffs)
####################################################################################################
#Load the study region
Map.addLayer(studyArea, {'palette': '0000FF'}, "Study Area", False)
Map.centerObject(studyArea)
####################################################################################################
Map.view()  

# Map.setOptions('HYBRID');
coeffCollection = ee.ImageCollection(coeffCollection)
# // // Map.addLayer(coeffCollection);

# ///////////////////////////////////////////////////////////////////////