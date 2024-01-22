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

# Example of how to utilize the Folium-based viewer
####################################################################################################
import geeViz.getImagesLib as gil
import  geeViz.foliumView as fv
ee = fv.ee
Map = fv.foliumMapper()

Map.port = 1234
Map.clearMap()
####################################################################################################
# Bring in some S2 data
studyArea = ee.Geometry.Polygon(
        [[[-113.21807278537877, 41.786028237932015],
          [-113.21807278537877, 40.595571243156144],
          [-111.82280911350377, 40.595571243156144],
          [-111.82280911350377, 41.786028237932015]]], None, False)

# Get some example images to view
s2s = gil.getProcessedSentinel2Scenes(studyArea,2022,2023,120,150)
postComposite = s2s.filter(ee.Filter.calendarRange(2023,2023,'year')).median()
Map.addLayer(postComposite,gil.vizParamsFalse,'S2 Median 2023')
preComposite = s2s.filter(ee.Filter.calendarRange(2022,2022,'year')).median()
Map.addLayer(preComposite,gil.vizParamsFalse,'S2 Median 2022',False)

# Center on the study area and view it
Map.centerObject(studyArea)
Map.addLayer(studyArea,{'strokeColor':'F00','strokeWidth':5},'Study Area')
####################################################################################################
# View the map
Map.view()

