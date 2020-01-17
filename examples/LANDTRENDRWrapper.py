#Example of how to get Landsat data using the getImagesLib and view outputs using the Python visualization tools
#Acquires Landsat data and then adds them to the viewer
####################################################################################################
import os,sys
sys.path.append(os.getcwd())

#Module imports
from  geeViz.getImagesLib import *
from geeViz.changeDetectionLib import *
Map.clearMap()
####################################################################################################
#Define user parameters:

#1. Specify study area: Study area
#Can specify a country, provide a fusion table  or asset table (must add 
#.geometry() after it), or draw a polygon and make studyArea = drawnPolygon
studyArea = ee.Feature(ee.Geometry.Polygon(\
        [[[-124.02812499999999, 43.056605431434335],\
          [-124.02812499999999, 38.259489368377466],\
          [-115.94218749999999, 38.259489368377466],\
          [-115.94218749999999, 43.056605431434335]]]))


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
startYear = 2000
endYear = 2019

#Choose band or index
#NBR, NDMI, and NDVI tend to work best
#Other good options are wetness and tcAngleBG
indexName = 'NBR'

#How many significant loss and/or gain segments to include
#Do not make less than 1
#If you only want the first loss and/or gain, choose 1
#Generally any past 2 are noise
howManyToPull = 2

#Parameters to identify suitable LANDTRENDR segments

#Thresholds to identify loss in vegetation
#Any segment that has a change magnitude or slope less than both of these thresholds is omitted
lossMagThresh = -0.15
lossSlopeThresh = -0.05


#Thresholds to identify gain in vegetation
#Any segment that has a change magnitude or slope greater than both of these thresholds is omitted
gainMagThresh = 0.1
gainSlopeThresh = 0.05

slowLossDurationThresh = 3

#Choose from: 'newest','oldest','largest','smallest','steepest','mostGradual','shortest','longest'
chooseWhichLoss = 'largest'
chooseWhichGain = 'largest'

#Define landtrendr params
run_params = { \
  'maxSegments':            6,\
  'spikeThreshold':         0.9,\
  'vertexCountOvershoot':   3,\
  'preventOneYearRecovery': True,\
  'recoveryThreshold':      0.25,\
  'pvalThreshold':          0.05,\
  'bestModelProportion':    0.75,\
  'minObservationsNeeded':  6\
}

#Whether to add outputs to map
addToMap = True
#13. Export params
#Whether to export LANDTRENDR outputs
exportLTStack = False

#Set up Names for the export
outputName = 'LT_Test'

#Provide location composites will be exported to
#This should be an asset folder, or more ideally, an asset imageCollection
exportPathRoot = 'users/iwhousman/test/ChangeCollection'



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
hansen = ee.Image('UMD/hansen/global_forest_change_2018_v1_6').select(['lossyear']).add(2000).int16()
hansen = hansen.updateMask(hansen.neq(2000).And(hansen.gte(startYear)).And(hansen.lte(endYear)))
Map.addLayer(hansen,{'min':startYear,'max':endYear,'palette':lossYearPalette},'Hansen Change Year',False);

####################################################################################################
#Call on master wrapper function to get Landat scenes and composites
allImages = getLandsatWrapper(studyArea.geometry(),startYear,endYear,startJulian,endJulian)

#Separate into scenes and composites for subsequent analysis
images = allImages[0]
composites = allImages[1]

# for year in range(startYear      ,endYear + 1  ):
#      t = processedComposites.filter(ee.Filter.calendarRange(year,year,'year')).mosaic()
#      Map.addLayer(t,vizParamsFalse,str(year),'False')
ltOut = simpleLANDTRENDR(composites,startYear,endYear,indexName, run_params,lossMagThresh,lossSlopeThresh,\
                                                gainMagThresh,gainSlopeThresh,slowLossDurationThresh,chooseWhichLoss,\
                                                chooseWhichGain,addToMap,howManyToPull)
if exportLTStack:
  ltOutStack = ltOut[1]

  #Export  stack
  exportName = outputName + '_Stack_'+indexName
  exportPath = exportPathRoot + '/'+ exportName

  #Set up proper resampling for each band
  #Be sure to change if the band names for the exported image change
  pyrObj = {'_yr_':'mode','_dur_':'mode','_mag_':'mean','_slope_':'mean'}
  possible = ['loss','gain']
  how_many_list = ee.List.sequence(1,howManyToPull).getInfo()
  outObj = {}
  for p in possible:
    for key in pyrObj.keys():
      for i in how_many_list:
        i = int(i)
        kt = indexName + '_LT_'+p + key+str(i)
        outObj[kt]= pyrObj[key]

  
  #Export output
  exportToAssetWrapper2(ltOutStack,exportName,exportPath,outObj,studyArea,scale,crs,transform)
####################################################################################################
#Load the study region
Map.addLayer(studyArea, {'palette': '0000FF'}, "Study Area", False)
Map.centerObject(studyArea)
####################################################################################################
Map.view()