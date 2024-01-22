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

#Example of how to get Climate data using the getImagesLib and view outputs using the Python visualization tools
#Acquires DAYMET V4 data and then adds them to the viewer
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

# Specify study area: Study area
# Can be a featureCollection, feature, or geometry
studyArea = getImagesLib.testAreas['CA']

# Update the startJulian and endJulian variables to indicate your seasonal 
# constraints. This supports wrapping for tropics and southern hemisphere.
# If using wrapping and the majority of the days occur in the second year, the system:time_start will default 
# to June 1 of that year.Otherwise, all system:time_starts will default to June 1 of the given year
# startJulian: Starting Julian date 
# endJulian: Ending Julian date
startJulian = 274
endJulian = 273

# Specify start and end years for all analyses
# More than a 3 year span should be provided for time series methods to work 
# well. If providing pre-computed stats for cloudScore and TDOM, this does not 
# matter
startYear = 2016
endYear = 2023

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

# Choose reducer to use for summarizing each year
# Common options are ee.Reducer.mean() and ee.Reducer.median()
compositingReducer = ee.Reducer.mean()

# Choose collection to use
# Supports:
# NASA/ORNL/DAYMET_V3
# NASA/ORNL/DAYMET_V4
# UCSB-CHG/CHIRPS/DAILY (precipitation only)
collectionName = 'NASA/ORNL/DAYMET_V4'



# Export params
# Whether to export climate composites
exportComposites = False


# Provide location composites will be exported to
# This should be an asset folder, or more ideally, an asset imageCollection
exportPathRoot = 'users/username/someCollection'

# users/username/someCollection
# Specify which bands to export
# If not sure or want all bands, just set to None
exportBands = ['prcp.*','tmax.*','tmin.*']

# CRS- must be provided.  
# Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
# WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
crs = 'EPSG:5070'

# Specify transform if scale is null and snapping to known grid is needed
transform = [1000,0,-2361915.0,0,-1000,3177735.0]

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
#Call on master wrapper function to get climate composites
climateComposites = getImagesLib.getClimateWrapper(collectionName,studyArea,startYear,endYear,startJulian,endJulian,timebuffer,weights,compositingReducer,exportComposites,exportPathRoot,crs,transform,scale,exportBands)

Map.addTimeLapse(climateComposites.select(exportBands),{},'Climate Composite Time Lapse')

####################################################################################################
#Load the study region
Map.addLayer(studyArea, {'strokeColor': '0000FF'}, "Study Area", True)
Map.centerObject(studyArea)
####################################################################################################
####################################################################################################
# View map
Map.turnOnInspector()
Map.view()
####################################################################################################
####################################################################################################
# If exporting composites, track the exports
if exportComposites:taskManagerLib.trackTasks2()