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
#Uses the several stock GEE assets to show time series as a time lapse
#Then uses those to color the raster and create a legend using the addToClassLegend option setting it to True
#Then provide a color dictionary with the format: {value:hex_color} ex({'1':'FF0','2':'F00'})
#Since Python does not respect the order of keys in dictionaries, the dictionaries will be sorted by alpha/numeric order according to the keys
#Conversion of numbers to labels is supported with the queryDict key in the viz params
#Ex. {'1':'Water','2':'Trees'}
####################################################################################################
#Import modules
import os,sys
sys.path.append(os.getcwd())

import geeViz.getImagesLib as getImagesLib
ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()
####################################################################################################
#Bring in pre-defined area
cambodia = ee.Feature(ee.Geometry.Polygon(\
        [[[104.48008284838329, 13.365070792606891],\
          [104.48008284838329, 12.218730827637675],\
          [106.08683333666454, 12.218730827637675],\
          [106.08683333666454, 13.365070792606891]]], None, False))
gsl = ee.Feature(ee.Geometry.Polygon(\
        [[[-113.2053895191826, 41.82208938845069],\
          [-113.2053895191826, 40.5655604972739],\
          [-111.7002625660576, 40.5655604972739],\
          [-111.7002625660576, 41.82208938845069]]], None, False))
rio = ee.Feature(ee.Geometry.Polygon(\
        [[[-107.5198171213165, 38.080864394376015],\
          [-107.5198171213165, 37.40759534811328],\
          [-106.6189382150665, 37.40759534811328],\
          [-106.6189382150665, 38.080864394376015]]], None, False))
conus = ee.Feature(ee.Geometry.Polygon(\
        [
    [
      [
        -124.85720095425737,
        24.959288058753405
      ],
      [
        -66.97879243191109,
        24.959288058753405
      ],
      [
        -66.97879243191109,
        49.632344931561455
      ],
      [
        -124.85720095425737,
        49.632344931561455
      ],
      [
        -124.85720095425737,
        24.959288058753405
      ]
    ]
  ], None, False))
Map.addLayer(conus,{'layerType':'geeVector'},'Conterminous United States for PDSI Time Lapse (double click to zoom to)',False);
Map.addLayer(gsl,{'layerType':'geeVector'},'Great Salt Lake Example Area for JRC Water Time Lapse (double click to zoom to)',False);
Map.addLayer(cambodia,{'layerType':'geeVector'},'Cambodia Example Area for Hansen Loss Time Lapse (double click to zoom to)',False);
Map.addLayer(rio,{'layerType':'geeVector'},'Rio Grande National Forest Example Area for LCMS Loss Time Lapse (double click to zoom to)',True);

#The Map can be centered on featureCollections, features, or geometry
Map.centerObject(rio)

#Bring in the JRC Surface water data
water = ee.ImageCollection('JRC/GSW1_0/YearlyHistory')

#Here is an example of creating a lookup dictionary
waterColors = ['ffffff','99d9ea','0000ff']
waterLabels = ['1 Not Water','2 Seasonal Water','3 Permanent Water']
waterDict =  {waterLabels[i]: waterColors[i] for i in range(len(waterColors))}
waterQueryDict =  {str(i+1): waterLabels[i] for i in range(len(waterLabels))}

Map.addTimeLapse(water,{'min':1,'max':3,'palette':waterColors,'addToClassLegend': True,'classLegendDict':waterDict,'queryDict':waterQueryDict},'JRC Surface Water Time Lapse',False)

#Bring in Hansen loss
declineYearPalette = 'ffffe5,fff7bc,fee391,fec44f,fe9929,ec7014,cc4c02'
hansen = ee.Image("UMD/hansen/global_forest_change_2020_v1_8")

hansenLoss = hansen.select(['lossyear']).add(2000).int16()
hansenStartYear = 2001
hansenEndYear = 2020

hansenYears = ee.List.sequence(hansenStartYear,hansenEndYear)

#Convert to an image collection of the year of loss
def hansenFun(yr):
	yr = ee.Number(yr)
	t = ee.Image(yr).updateMask(hansenLoss.eq(yr)).set('system:time_start',ee.Date.fromYMD(yr,6,1).millis())
	return t
hansenC =ee.ImageCollection.fromImages(hansenYears.map(hansenFun))

#Add time lapse to map
hansenYearsCli = hansenYears.getInfo()
Map.addTimeLapse(hansenC,{'min':hansenStartYear,'max':hansenEndYear,'palette':declineYearPalette,'years':hansenYearsCli},'Hansen Loss Time Lapse')
  
#Bring in LCMS
lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2020-5").select(['Change'])
lcmsStartYear = 1985
lcmsEndYear = 2020
lcmsYears = ee.List.sequence(lcmsStartYear,lcmsEndYear)

def lcmsFun(yr):
  yr = ee.Number(yr).int16()
  lcmsT = lcms.filter(ee.Filter.calendarRange(yr,yr,'year')).mosaic()
  change = lcmsT.eq(2).Or(lcmsT.eq(3))
  yrImg = ee.Image.constant(yr).updateMask(change).int16()
  return yrImg.set('system:time_start',ee.Date.fromYMD(yr,6,1).millis())

lcms = ee.ImageCollection.fromImages(lcmsYears.map(lcmsFun))

# Map.addLayer(lcms)
Map.addTimeLapse(lcms,{'min':lcmsStartYear,'max':lcmsEndYear,'palette':declineYearPalette,'years':lcmsYears.getInfo()},'LCMS Loss Time Lapse')

#Add PDSI time lapse
pdsiStartYear = 2016
pdsiEndYear = 2020
pdsi = ee.ImageCollection("GRIDMET/DROUGHT")\
    .filter(ee.Filter.calendarRange(pdsiStartYear,pdsiEndYear,'year')).select(['pdsi'])

#Convert 5 day PDSI values into 8 week composites (median)
pdsi = getImagesLib.nDayComposites(pdsi,pdsiStartYear,pdsiEndYear,1,365,56)

#Add PDSI time lapse
#This example isn't annual, so the dateFormat and advanceInterval are changed
Map.addTimeLapse(pdsi,{'min':-5,'max':5,'palette':'F00,888,00F','dateFormat':'YYYYMMdd','advanceInterval':'day'},'PDSI Time Lapse')

#Final step is to launch the viewer
Map.view()