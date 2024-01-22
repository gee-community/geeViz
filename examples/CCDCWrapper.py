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

#Example of how to run CCDC and view outputs using the Python visualization tools
#Acquires Landsat data, runs CCDC, and tries to add them to the viewer
#Original CCDC paper: https://www.sciencedirect.com/science/article/pii/S0034425714000248
#Since CCDC doesn't work well on-the-fly, see the CCCDCViz.py example to view outputs created with this script
#The general workflow for CCDC is to run this script, and then either utilize the harmonic model for a given date
#or to use the breaks for change detection. All of this is demonstrated in the CCDCViz.py example
####################################################################################################
import os,sys
sys.path.append(os.getcwd())

#Module imports
import geeViz.getImagesLib as getImagesLib
import geeViz.taskManagerLib as taskManagerLib
ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()
####################################################################################################
#Define user parameters:
# Define user parameters:

# Specify study area: Study area
# Can be a featureCollection, feature, or geometry
studyArea = getImagesLib.testAreas['CA']

#Update the startJulian and endJulian variables to indicate your seasonal 
#constraints. This supports wrapping for tropics and southern hemisphere.
#If using wrapping and the majority of the days occur in the second year, the system:time_start will default 
#to June 1 of that year.Otherwise, all system:time_starts will default to June 1 of the given year
#startJulian: Starting Julian date 
#endJulian: Ending Julian date
startJulian = 1
endJulian = 365 

#Specify start and end years for all analyses
#More than a 3 year span should be provided for time series methods to work 
#well. If providing pre-computed stats for cloudScore and TDOM, this does not 
#matter
startYear = 1984
endYear = 2023

#Choose whether to include Landat 7
#Generally only included when data are limited
includeSLCOffL7 = True



#Export params
#Whether to export CCDC outputs
exportCCDC = False

#Which bands/indices to export
#These will not always be used to find breaks - that is specified below in the ccdcParams
#Options are: ["blue","green","red","nir","swir1","swir2","NDVI","NBR","NDMI","NDSI","brightness","greenness","wetness","fourth","fifth","sixth","tcAngleBG"]
#Be sure that any bands in ccdcParams.breakpointBands are in this list
exportBands = ["blue","green","red","nir","swir1","swir2","NDVI"]


#Set up Names for the export
outputName = 'CCDC-Test'

#Provide location composites will be exported to
#This should be an asset folder, or more ideally, an asset imageCollection
exportPathRoot = 'users/username/someCollection'


#CRS- must be provided.  
#Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
#WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
crs = 'EPSG:5070'

#Specify transform if scale is None and snapping to known grid is needed
transform = [30,0,-2361915.0,0,-30,3177735.0]

#Specify scale if transform is None
scale = None


###############################################################
#CCDC Params
# ccdcParams ={
#   breakpointBands:['green','red','nir','swir1','swir2','NDVI'],//The name or index of the bands to use for change detection. If unspecified, all bands are used.//Can include: 'blue','green','red','nir','swir1','swir2'
#                                                               //'NBR','NDVI','wetness','greenness','brightness','tcAngleBG'
#   tmaskBands : None,//['green','swir2'],//The name or index of the bands to use for iterative TMask cloud detection. These are typically the green band and the SWIR2 band. If unspecified, TMask is not used. If specified, 'tmaskBands' must be included in 'breakpointBands'., 
#   minObservations: 6,//Factors of minimum number of years to apply new fitting.
#   chiSquareProbability: 0.99,//The chi-square probability threshold for change detection in the range of [0, 1],
#   minNumOfYearsScaler: 1.33,//Factors of minimum number of years to apply new fitting.,\
#   lambda: 0.002,//Lambda for LASSO regression fitting. If set to 0, regular OLS is used instead of LASSO
#   maxIterations : 25000, //Maximum number of runs for LASSO regression convergence. If set to 0, regular OLS is used instead of LASSO.
#   dateFormat : 1 //'fractional' (1) is the easiest to work with. It is the time representation to use during fitting: 0 = jDays, 1 = fractional years, 2 = unix time in milliseconds. The start, end and break times for each temporal segment will be encoded this way.
  
# }; 
ccdcParams ={
  'breakpointBands':['green','red','nir','swir1','swir2','NDVI'],
  'tmaskBands' : None,
  'minObservations': 6,
  'chiSquareProbability': 0.99,
  'minNumOfYearsScaler': 1.33,
  'lambda': 0.002,
  'maxIterations' : 25000,
  'dateFormat' : 1 
}; 

###############################################################
#End user parameters
###############################################################
###############################################################
###############################################################
#Start function calls
###############################################################
#Get cloud and cloud shadow masked Landsat scenes
processedScenes = getImagesLib.getProcessedLandsatScenes(studyArea = studyArea,startYear = startYear, endYear = endYear,
                                                        startJulian = startJulian,endJulian = endJulian,
                                                        includeSLCOffL7 = includeSLCOffL7).select(exportBands)


#Remove any extremely high band/index values
def removeGT1(img):
  lte1 = img.select(['blue','green','nir','swir1','swir2']).lte(1).reduce(ee.Reducer.min());
  return img.updateMask(lte1);
processedScenes = processedScenes.map(removeGT1)
Map.addLayer(processedScenes,{},'Processed Input Data',False);

#Set the scene collection in the ccdcParams
ccdcParams['collection'] = processedScenes

#Run CCDC
ccdc = ee.Image(ee.Algorithms.TemporalSegmentation.Ccdc(**ccdcParams))

#Set properties for asset
# ccdc = ccdc.copyProperties(processedScenes)
# ccdc = ccdc.setMulti(ccdcParams)
# ccdc = ee.Image(ccdc)

Map.addLayer(ccdc,{},'CCDC Output',False);

#Export output
if exportCCDC:
  print('Exporting CCDC output')

  exportName = outputName  + '_'+str(startYear) + '_' + str(endYear) + '_' + str(startJulian) + '_' + str(endJulian)
  exportPath = exportPathRoot + '/'+ exportName

  #Export output
  getImagesLib.exportToAssetWrapper(ccdc,exportName,exportPath,{'.default':'sample'},studyArea,scale,crs,transform)

####################################################################################################
#Load the study region
Map.addLayer(studyArea, {'strokeColor': '0000FF'}, "Study Area", False)
Map.centerObject(studyArea)
####################################################################################################
# View map
Map.turnOnInspector()
Map.view()
####################################################################################################
####################################################################################################
# Track the export
if exportCCDC:taskManagerLib.trackTasks2()