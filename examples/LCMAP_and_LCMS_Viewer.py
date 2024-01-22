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

# This script provides a view of LCMAP and LCMS GEE collections to help understand the strengths of each
# It displays the land cover and land use products as well as change products from each program
####################################################################################################
import os,sys
sys.path.append(os.getcwd())

#Module imports
import geeViz.getImagesLib as getImagesLib
import geeViz.changeDetectionLib as changeDetectionLib
ee = getImagesLib.ee
Map = getImagesLib.Map
Map.clearMap()
####################################################################################################
# User Parameters

# Define the early time period 
preStartYear = 1985
preEndYear = 1990

# Define the more recent time period
postStartYear = 2020
postEndYear = 2022

# Specify whether to add time lapses of products. If True, loading the viewer will take much much much much longer
addTimelapses = False
####################################################################################################
# Bring in LCMAP outputs
# This part was adapted from info available in the awesome-gee-community-datasets
# https://samapriya.github.io/awesome-gee-community-datasets/projects/lcmap/
# Playground example: https://code.earthengine.google.com/791aa894ce0abfe1a9eb1dc478bbc5d7
# Their outputs are divided into LC (land cover) and SC (spectral change)
# More details about their different products can be found here:
# https://www.sciencedirect.com/science/article/pii/S003442571930375X
# LCMAP methods can be found here: https://www.sciencedirect.com/science/article/pii/S003442571930375X
# LCMAP data can be downloaded from: https://www.usgs.gov/core-science-systems/eros/lcmap/lcmap-data-access
# LCMAP data can also be viewed here: https://eros.usgs.gov/lcmap/viewer/
lcachg = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/LCACHG")
lcpconf = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/LCPCONF")
lcpri = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/LCPRI")
lcsconf = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/LCSCONF")
lcsec = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/LCSEC")
sclast = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/SCLAST")
scmag = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/SCMAG")
scmqa = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/SCMQA")
scstab = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/SCSTAB")
sctime = ee.ImageCollection("projects/sat-io/open-datasets/LCMAP/SCTIME")


# Manually pull in color palettes from Gena's color palette json
# palettes = require('users/gena/packages:palettes')
# Available here: https://github.com/gee-community/ee-palettes
lcpri_palette = ['E60000','A87000','E3E3C2','1D6330','476BA1','BAD9EB','FFFFFF','B3B0A3','A201FF']
lc_names = ['Developed','Cropland','Grass/Shrub','Tree Cover','Water','Wetlands','Ice/Snow','Barren','Class Change']

# Set up the LCMAP land cover legend and lookup tables
lc_legend_dict = {}
lc_lookup_dict = {}
for i in range(0,len(lc_names )):
  lc_legend_dict[str(i+1) + '- '+lc_names[i]] =lcpri_palette[i] 
  lc_lookup_dict[i+1] = str(i+1) + '- '+lc_names[i]

#Other palettes found in the Playground example script
# lcsec_palette = ['E60000','A87000','E3E3C2','1D6330','476BA1','BAD9EB','FFFFFF','B3B0A3']
lcachg_palette = ['E60000','A87000','E3E3C2','1D6330','476BA1','BAD9EB','FFFFFF','B3B0A3','A201FF']
# sclast_palette = ['FFC7AA','F87E45','CC764E','86A7B6','46A4EE','7954C8','7A24AA','432172']
# scstab_palette = ['BA4E16','EE964D','FFE29C','F4FBC1','E1F3C3','BCE6CA','46989C']
# scmqa_palette = ['000000','A900E6','DF73FF','F5F5E3','DB8A00','924900','9C9C9C','FFFFFF']

# Set up some visualization dictionaries
lc_viz = {'reducer':ee.Reducer.mode(),'min':1,'max':9,'palette':lcpri_palette,'classLegendDict':lc_legend_dict,'queryDict':lc_lookup_dict}
loss_viz = {'min':1985,'max':2022,'palette':changeDetectionLib.lossYearPalette}
gain_viz = {'min':1985,'max':2022,'palette':changeDetectionLib.gainYearPalette}
change_viz = {'min':1985,'max':2022,'palette':['00F','F0F']}

# Map.addLayer(sctime.max(),{'min':100,'max':292,'palette':['151d44', '156c72', '7eb390', 'fdf5f4', 'db8d77', '9c3060', '340d35']},'SCTIME',True)
# Map.addLayer(scmag.max(),{'min':651,'max':3700,'palette':['d7f9d0', 'a2d595', '64b463', '129450', '126e45', '1a482f', '122414']},'SCMAG',True)
# Map.addLayer(ee.Image(sclast.sort('system:time_start',false).first()).mask(ee.Image(sclast.sort('system:time_start',false).first()).gt(0)),{min:518,max:4600,palette:sclast_palette},'SCLAST',false)
# Map.addLayer(scstab.sort('system:time_start',false).first(),{min:70,max:13000,palette:scstab_palette},'SCSTAB',false)
# Map.addLayer(scmqa.sort('system:time_start',false).first().remap([0,4,6,8,14,24,44,54],[0,1,2,3,4,5,6,7]).mask(ee.Image(scmqa.sort('system:time_start',false).first()).gt(0)),{min:0,max:7,palette:scmqa_palette},'SCMQA',false)
####################################################################################################
# Bring in LCMS GEE collection over CONUS
# LCMS' homepage can be found here: https://data.fs.usda.gov/geodata/rastergateway/LCMS/index.php
# LCMS methods are described here: https://data.fs.usda.gov/geodata/rastergateway/LCMS/LCMS_v2021-7_Methods.pdf
# LCMS data can also be viewed and downloaded here: https://apps.fs.usda.gov/lcms-viewer
# LCMS GEE data collections are available at:
  # https://developers.google.com/earth-engine/datasets/catalog/USFS_GTAC_LCMS_v20201-7 (CONUS and Southeastern AK)
  # https://developers.google.com/earth-engine/datasets/catalog/USFS_GTAC_LCMS_v2020-6 (Puerto Rico and US Virgin Islands
# An in-depth look at the model predictor variables that go into making LCMS maps can be found here:https://apps.fs.usda.gov/lcms-viewer/lcms-base-learner.html
lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2022-8").filter(ee.Filter.eq('study_area','CONUS'))
####################################################################################################

####################################################################################################
#This section adds the land cover and land use maps from LCMAP and LCMS

# Pull the LCMAP pre and post land cover data
lcmap_pre = lcpri.filter(ee.Filter.calendarRange(preStartYear,preEndYear,'year'))
lcmap_post = lcpri.filter(ee.Filter.calendarRange(postStartYear,postEndYear,'year'))

# Pull the LCMS pre and post land cover data
lcms_pre = lcms.filter(ee.Filter.calendarRange(preStartYear,preEndYear,'year'))
lcms_post = lcms.filter(ee.Filter.calendarRange(postStartYear,postEndYear,'year'))



# Add time lapses of LCMAP and LCMS land cover products if specified
if addTimelapses:
  Map.addTimeLapse(lcachg,lc_viz,'LCMAP LC Change')
  Map.addTimeLapse(lcpri,lc_viz,'LCMAP Primary Land Cover')
  Map.addTimeLapse(lcsec,lc_viz,'LCMAP Secondary Land Cover')
  Map.addTimeLapse(lcms.select(['Land_Cover']),{'autoViz':True},'LCMS Land Cover')
  Map.addTimeLapse(lcms.select(['Land_Use']),{'autoViz':True},'LCMS Land Use')

# Add the early and recent land cover and land use mode maps
# LCMAP's LC outputs combine land cover and land use, so cross-walking these non-mutually exclusive classes to those of LCMS can pose challenges
# However, take note how well LCMAP maps agriculture and developed areas - it is much cleaner and seems much more accurate than LCMS.
# LCMAP does about as well as LCMS at mapping trees. They both do fairly well in sparse tree cover areas.
# Since wetlands are not exclusive of any land cover or land use, it is difficult to tell what land cover is over areas classified by LCMAP as wetland
# This is also true of LCMS' non forest wetland land use class - there are areas of rangeland and agriculture that could fall into non forest wetland
# One area the LCMS land cover maps do better is with water. 
# LCMAP LC outputs tend to not change the water extent of fluctuating waterbodies very quickly
Map.addLayer(lcmap_pre,lc_viz, 'LCMAP LC {}-{} mode'.format(preStartYear,preEndYear),False)
Map.addLayer(lcmap_post,lc_viz, 'LCMAP LC {}-{} mode'.format(postStartYear,postEndYear),False)

for t in ['Cover','Use']:
  Map.addLayer(lcms_pre.select(['Land_{}'.format(t)]),{'reducer':ee.Reducer.mode(),'autoViz':True}, 'LCMS L{} {}-{} mode'.format(t[0],preStartYear,preEndYear),False)
  Map.addLayer(lcms_post.select(['Land_{}'.format(t)]),{'reducer':ee.Reducer.mode(),'autoViz':True}, 'LCMS L{} {}-{} mode'.format(t[0],postStartYear,postEndYear),False)

####################################################################################################
# This section adds the change maps from LCMAP and LCMS

# Function for getting a precise change break date from CCDC-based outputs
def getYrMskPrecise(img):
  yr = ee.Date(img.get('system:time_start')).get('year')
  return ee.Image(yr).add(img.divide(365)).float().updateMask(img.mask())

# Function for getting a more general integer year date of change
def getYrMsk(img):
  yr = ee.Date(img.get('system:time_start')).get('year')
  return ee.Image(yr).int16().updateMask(img.mask())

# Find the most recent LCMAP spectral change date (YYYY.dd where .dd is the fraction of the year the break occurred)
lcmap_change_yr  = sctime.map(getYrMskPrecise).max()

# Pull apart LCMS fast and slow loss and find the most recent year of each 
lcms_fast_loss_yr = lcms.select(['Change']).map(lambda img:getYrMsk(img.updateMask(img.eq(3)))).max()
lcms_slow_loss_yr = lcms.select(['Change']).map(lambda img:getYrMsk(img.updateMask(img.eq(2)))).max()
lcms_gain_yr = lcms.select(['Change']).map(lambda img:getYrMsk(img.updateMask(img.eq(4)))).max()


# As of version 2020.5, LCMS produces vegetation cover slow loss, fast loss, and gain change outputs. 
# LCMAP version 1.0 produces several change outputs based on the spectral change detected by CCDC
# The most analagous change product is the spectral change time (SCTIME)
Map.addLayer(lcms_fast_loss_yr,loss_viz,'LCMS Most Recent Fast Loss Year',False)
Map.addLayer(lcms_slow_loss_yr,loss_viz,'LCMS Most Recent Slow Loss Year',False)
Map.addLayer(lcms_gain_yr,gain_viz,'LCMS Most Recent Gain Year',False)

Map.addLayer(lcmap_change_yr,change_viz,'LCMAP Most Recent SC Date',True)

####################################################################################################
# Since LCMAP is largely based on CCDC, understanding how the delivered change outputs relate to raw CCDC outputs helps 
# identify the strengths and weaknesses of the approach

# Bring in the LCMS CCDC output that is similar to what LCMAP uses
ccdcImg = ee.ImageCollection('projects/lcms-292214/assets/CONUS-LCMS/Base-Learners/CCDC-Collection-1984-2022')\
          .select(['tStart','tEnd','tBreak','changeProb','red.*','nir.*','swir1.*','swir2.*','NDVI.*']).mosaic()

# Pull out the most recent date of change
changeObj = changeDetectionLib.ccdcChangeDetection(ccdcImg,'NDVI');
Map.addLayer(ccdcImg,{'opacity':0},'RAW CCDC Output',False)
Map.addLayer(changeObj['mostRecent']['loss']['year'],loss_viz,'LCMS CCDC Most Recent Loss Year')
Map.addLayer(changeObj['mostRecent']['gain']['year'],gain_viz,'LCMS CCDC Most Recent Gain Year')


# This produces a chart of the harmonic models from CCDC and the breaks to help further understand how the outputs are created
# Apply the CCDC harmonic model across a time series
# First get a time series of time images 
yearImages = changeDetectionLib.getTimeImageCollection(1984,2022,1,365,0.1)

#Then predict the CCDC models
fitted = changeDetectionLib.predictCCDC(ccdcImg,yearImages,False,[1,2,3])

Map.addLayer(fitted.select(['NDVI_CCDC_fitted']),{'opacity':0},'Fitted CCDC NDVI',True);
####################################################################################################
Map.setTitle('LCMAP LCMS Viewer')
Map.turnOnInspector()
Map.setQueryDateFormat('YYYY')
Map.view()