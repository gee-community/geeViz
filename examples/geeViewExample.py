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

#Example of how to utilize the Python visualization tools
#Uses the stock GEE NLCD assets and extracts the palette, names, and values from image properties
#Then uses those to color the raster and create a legend using the autoViz option setting it to True
#Then provide a color dictionary with the format: {value:hex_color} ex({'1':'FF0','2':'F00'})
#Conversion of numbers to labels is supported with the queryDict key in the viz params
#Ex. {'1':'Water','2':'Trees'}
#Interactive time lapses can be created from most imageCollections
####################################################################################################
#Import modules
import os,sys
sys.path.append(os.getcwd())

import  geeViz.geeView as geeView
ee = geeView.ee
Map = geeView.Map

#Clear any layers added to Map object
#If map is not cleared, layers are simply appended to the existing list of layers if layers have been added previously
Map.clearMap()
####################################################################################################
#Bring in NLCD 2011
nlcd = ee.Image('USGS/NLCD_RELEASES/2016_REL/2011')

#Add the layers to the map
#If an image has class values, names, and a palette property available, use 'autoViz':True to pull those properties for first band of the image provided
#Image must be a single band for thematic visualization to work properly
#Then provide a dictionary of the values and colors ex: {value:hex_color}
#If nothing is to be added to the legend, set 'addToLegend' to False
Map.addLayer(nlcd.select(['landcover']),{'autoViz':True},'NLCD 2011 Landcover/Landuse',False)

#Images or image collections can be added.  If an image collection is added, the first non null value is displayed on the map. A time series will be displayed when the layer is queried
nlcd = ee.ImageCollection('USGS/NLCD_RELEASES/2016_REL')
nlcd = nlcd.filter(ee.Filter.calendarRange(2000,2020,'year'))
nlcd = nlcd.map(lambda img: img.set('bns',img.bandNames()))
nlcd = nlcd.filter(ee.Filter.listContains('bns','landcover')).select(['landcover'])
Map.addLayer(nlcd.sort('system:time_start'),{'autoViz':True},'NLCD Landcover/Landuse Time Series',False)

# Continuous data automatically have a legend added
nlcd = ee.Image('USGS/NLCD_RELEASES/2016_REL/2016')
Map.addLayer(nlcd.select(['percent_tree_cover']),{'min':20,'max':80,'palette':'555,0A0'},'NLCD 2016 TCC',False)

#Another example
mtbs = ee.ImageCollection('projects/gtac-mtbs/assets/burn_severity_mosaics/MTBS')
mtbs = mtbs.map(lambda img: img.updateMask(img.neq(0)).select([0],['Burn Severity']).byte())

#Set up MTBS legend and color properties manually if they are not available in the image properties
mtbsColors = ['006400','7fffd4','ffff00','ff0000','7fff00','ffffff']
mtbsLabels = ['1 Unburned to Low','2 Low','3 Moderate','4 High','5 Increased Greenness','6 Non-Processing Area Mask']
mtbsDict =  {mtbsLabels[i]: mtbsColors[i] for i in range(len(mtbsColors))}
mtbsQueryDict = {'1':'Unburned to Low','2':'Low','3':'Moderate','4':'High','5':'Increased Greenness','6':'Non-Processing Area Mask'}
severityViz = {'min':1,'max':6,'palette':mtbsColors	,'classLegendDict':mtbsDict,'queryDict':mtbsQueryDict}

#Add it to the map
Map.addLayer(mtbs.max(),severityViz,'MTBS 1984-2017 Highest Severity',True)

#Feature collections can be added to the map as well
perims = ee.FeatureCollection('projects/gtac-mtbs/assets/perimeters/mtbs_perims_DD')
Map.addLayer(perims,{'strokeColor':'00F'},'MTBS Burn Perimeters',True)

#Smaller feature collections can be added to the map as a geojson vector by specifying 'layerType':'geeVector'
#They will render more quickly than the raterized version of the vector
nps = ee.FeatureCollection('projects/USFS/LCMS-NFS/CONUS-Ancillary-Data/NPS_Boundaries').filter(ee.Filter.eq('PARKNAME','Yellowstone'))
Map.addLayer(nps,{'layerType': 'geeVector'},'Yellowstone National Park',True)

#Bring in the JRS Surface water data
water = ee.ImageCollection('JRC/GSW1_0/YearlyHistory')

#Here is another example of creating a lookup dictionary
waterColors = ['ffffff','99d9ea','0000ff']
waterLabels = ['1 Not Water','2 Seasonal Water','3 Permanent Water']
waterDict =  {waterLabels[i]: waterColors[i] for i in range(len(waterColors))}
waterQueryDict =  {str(i+1): waterLabels[i] for i in range(len(waterLabels))}

#The lookup table is applied to the image, but only a graph is created when querying the imageCollection
Map.addLayer(water,{'min':1,'max':3,'palette':waterColors,'classLegendDict':waterDict,'queryDict':waterQueryDict},'JRC Surface Water Time Series',False)
Map.addLayer(water.mode(),{'min':1,'max':3,'palette':waterColors,'classLegendDict':waterDict,'queryDict':waterQueryDict},'JRC Surface Water Mode',False)
Map.addTimeLapse(water,{'min':1,'max':3,'palette':waterColors,'classLegendDict':waterDict},'JRC Surface Water Time Lapse',False)
#The Map can be centered on featureCollections or features
Map.centerObject(nps)

#The ability to query visible map layers can be turned on manually or with the following command
Map.turnOnInspector()

#Final step is to launch the viewer
Map.view()