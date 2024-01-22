"""
   Copyright 2024 Ian Housman

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

# Example of how to use a local shapefile in geeViz workflows
# This uses geemap to convert the shapefile to geojson and then an ee object 
####################################################################################################
import geemap
import geeViz.getImagesLib as gil
Map = gil.Map
ee = gil.ee

# Specify dates to make an image composite
startYear = 2023
endYear = 2023
startJulian = 150
endJulian = 250

# Provide a shapefile
shp = gil.os.path.join(gil.sys.path[0],"data/gadm41_CHE_shp/gadm41_CHE_0.shp")

# Convert it to an ee object
studyArea = geemap.shp_to_ee(shp)

# Get some images (use the bounds to avoid memory errors)
s2s = gil.getProcessedSentinel2Scenes(studyArea.geometry().bounds(),startYear,endYear,startJulian,endJulian)

# Add the composite and study area to the map
Map.addLayer(s2s.median(),gil.vizParamsFalse,'Composite')


Map.addLayer(studyArea,{'strokeColor':'0FF','strokeWeight':3},'Study Area')

Map.centerObject(studyArea)
Map.turnOnInspector()
Map.view()