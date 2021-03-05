'''
Based on https://github.com/google/earthengine-community/blob/master/datasets/scripts/LCMS_Visualization.js
 * Copyright 2021 The Google Earth Engine Community Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * 
 * 
 * Example script for visualizing LCMS change summaries, land cover, and land use.
 * 
 * A more in-depth visualization of LCMS products is available at:
 * https://apps.fs.usda.gov/lcms-viewer/
 * 
 * Contact sm.fs.lcms@usda.gov with any questions or specific data requests.
''' 
####################################################################################################
#Import modules
import os,sys
sys.path.append(os.getcwd())

from geeViz.getImagesLib import *
Map.clearMap()
####################################################################################################
#############################################################################
### Define visualization parameters ###
#############################################################################

startYear = 1985;
endYear = 2020;
lossYearPalette = ['ffffe5', 'fff7bc', 'fee391', 'fec44f', 'fe9929',
                   'ec7014', 'cc4c02']
gainYearPalette = ['c5ee93', '00a398']
durationPalette = ['BD1600', 'E2F400','0C2780']

names_values_colors = {
  'Land_Cover': {
    'names': [
       'Trees',
       'Tall Shrubs & Trees Mix',
       'Shrubs & Trees Mix',
       'Grass/Forb/Herb & Trees Mix',
       'Barren & Trees Mix',
       'Tall Shrubs',
       'Shrubs',
       'Grass/Forb/Herb & Shrubs Mix',
       'Barren & Shrubs Mix',
       'Grass/Forb/Herb',
       'Barren & Grass/Forb/Herb Mix',
       'Barren or Impervious',
       'Snow or Ice',
       'Water',
       'Non-Processing Area Mask'
    ],
    'colors': [
       '005e00',
       '008000',
       '00cc00',
       'b3ff1a',
       '99ff99',
       'b30088',
       'e68a00',
       'ffad33',
       'ffe0b3',
       'ffff00',
       'AA7700',
       'd3bf9b',
       'ffffff',
       '4780f3',
       '1B1716'
    ]
  },
  'Land_Use': {
    'names': [
       'Agriculture',
       'Developed',
       'Forest',
       'Non-Forest Wetland',
       'Other',
       'Rangeland or Pasture',
       'Non-Processing Area Mask'
    ],
    'colors': [
       'efff6b',
       'ff2ff8',
       '1b9d0c',
       '97ffff',
       'a1a1a1',
       'c2b34a',
       '1B1716'
    ]
  },
  'Change': {
    'names': [
       'Stable',
       'Slow Loss',
       'Fast Loss',
       'Gain',
       'Non-Processing Area Mask'
    ],
    'colors': [
       '3d4551',
       'f39268',
       'd54309',
       '00a398',
       '1B1716'
    ]
  }
};
lossYearViz = {'min': startYear, 'max': endYear, 'palette': lossYearPalette};
gainYearViz = {'min': startYear, 'max': endYear, 'palette': gainYearPalette};
durationViz = {'min': 1, 'max': 5, 'palette': durationPalette};


#Set up legend and query dictionaries for land cover and land use
lcDict,lcQueryDict,luDict,luQueryDict =  {},{},{},{}

for i in range(0,len(names_values_colors['Land_Cover']['names'])):
	lcDict[names_values_colors['Land_Cover']['names'][i]] = names_values_colors['Land_Cover']['colors'][i]
	lcQueryDict[str(i+1)] = names_values_colors['Land_Cover']['names'][i]
for i in range(0,len(names_values_colors['Land_Use']['names'])):
	luDict[names_values_colors['Land_Use']['names'][i]] = names_values_colors['Land_Use']['colors'][i]
	luQueryDict[str(i+1)] = names_values_colors['Land_Use']['names'][i]


lcViz = {'min': 1, 'max': 15, 'palette': names_values_colors['Land_Cover']['colors'],'addToClassLegend': True,'classLegendDict':lcDict,'queryDict':lcQueryDict};
luViz = {'min': 1, 'max': 7, 'palette': names_values_colors['Land_Use']['colors'],'addToClassLegend': True,'classLegendDict':luDict,'queryDict':luQueryDict};



#############################################################################
### Define functions ###
#############################################################################

#Convert given code to year that number was present in the image.

def getMostRecentChange(c, code):
	def wrapper(img):
		yr = ee.Date(img.get('system:time_start')).get('year')
		return ee.Image(yr).int16().rename(['year']).updateMask(img.eq(code)).copyProperties(img,['system:time_start'])
	return c.map(wrapper)
  

#############################################################################
### Bring in LCMS annual outputs ###
#############################################################################

lcms = ee.ImageCollection('USFS/GTAC/LCMS/v2020-5');
bandNames =  lcms.first().bandNames().getInfo()
print('Available study areas:', lcms.aggregate_histogram('study_area').keys().getInfo());
print('Available LCMS products',bandNames);
print('Learn more about visualization of LCMS products here', 'https://apps.fs.usda.gov/lcms-viewer/')

#Set up time periods to compare land cover and land use
earlySpan = [startYear, startYear+4]
lateSpan = [endYear-4, endYear]

#############################################################################
### Add full raw model outputs ###
#############################################################################

#Separate products
raw_change = lcms.select(['Change_Raw_.*'])
raw_land_cover = lcms.select(['Land_Cover_Raw_.*'])
raw_land_use = lcms.select(['Land_Use_Raw_.*'])

#Shorten names
raw_change_bns = [bn for bn in bandNames if bn.find('Change_Raw_') > -1]
raw_land_cover_bns = [bn for bn in bandNames if bn.find('Land_Cover_Raw_') > -1]
raw_land_use_bns = [bn for bn in bandNames if bn.find('Land_Use_Raw_') > -1]

raw_change_bns_short = [i.split('_Probability_')[-1] for i in raw_change_bns]
raw_land_cover_bns_short = [i.split('_Probability_')[-1] for i in raw_land_cover_bns]
raw_land_use_bns_short = [i.split('_Probability_')[-1] for i in raw_land_use_bns]

raw_change = raw_change.select(raw_change_bns,raw_change_bns_short)
raw_land_cover = raw_land_cover.select(raw_land_cover_bns,raw_land_cover_bns_short)
raw_land_use = raw_land_use.select(raw_land_use_bns,raw_land_use_bns_short)


#Add to map
Map.addLayer(raw_change,{'min':0,'max':30,'opacity':0,'addToLegend':False},'Raw LCMS Change Model Probability',True) 
Map.addLayer(raw_land_cover,{'min':0,'max':30,'opacity':0,'addToLegend':False},'Raw LCMS Land Cover Model Probability',True) 
Map.addLayer(raw_land_use,{'min':0,'max':30,'opacity':0,'addToLegend':False},'Raw LCMS Land Use Model Probability',True) 

#############################################################################
### Visualize Land Use change ###
#############################################################################

lu = lcms.select(['Land_Use'])
earlyLu = lu.filter(ee.Filter.calendarRange(earlySpan[0], earlySpan[1], 'year')).mode()
lateLu = lu.filter(ee.Filter.calendarRange(lateSpan[0], lateSpan[1], 'year')).mode()
Map.addLayer(earlyLu, luViz, 'Early Land Use Mode ({}-{})'.format(earlySpan[0],earlySpan[1]), False)
Map.addLayer(lateLu, luViz, 'Recent Land Use Mode ({}-{})'.format(lateSpan[0],lateSpan[1]), False);



#############################################################################
### Visualize Land Cover change ###
#############################################################################

lc = lcms.select(['Land_Cover'])
earlyLc = lc.filter(ee.Filter.calendarRange(earlySpan[0], earlySpan[1], 'year')).mode()
lateLc = lc.filter(ee.Filter.calendarRange(lateSpan[0], lateSpan[1], 'year')).mode()
Map.addLayer(earlyLc, lcViz, 'Early Land Cover Mode ({}-{})'.format(earlySpan[0],earlySpan[1]), False);
Map.addLayer(lateLc, lcViz, 'Recent Land Cover Mode ({}-{})'.format(lateSpan[0],lateSpan[1]), False);



#############################################################################
### Visualize Change products ###
#############################################################################

#Select the change band. Land_Cover and Land_Use are also available.
change = lcms.select(['Change'])

#Convert to year collection for a given code.
slowLossYears = getMostRecentChange(change, 2)
fastLossYears = getMostRecentChange(change, 3)
gainYears = getMostRecentChange(change, 4)

#Find the most recent year.
mostRecentSlowLossYear = slowLossYears.max()
mostRecentFastLossYear = fastLossYears.max()
mostRecentGainYear = gainYears.max()

#Find the duration.
slowLossDuration = slowLossYears.count()
fastLossDuration = fastLossYears.count()
gainDuration = gainYears.count()

#Add year summaries to the map.
Map.addLayer(mostRecentSlowLossYear, lossYearViz, 'Most Recent Slow Loss Year', True)
Map.addLayer(mostRecentFastLossYear, lossYearViz, 'Most Recent Fast Loss Year', True)
Map.addLayer(mostRecentGainYear, gainYearViz, 'Most Recent Gain Year', True)

#Add durations to the map.
Map.addLayer(slowLossDuration,durationViz, 'Slow Loss Duration', False);
Map.addLayer(fastLossDuration,durationViz, 'Fast Loss Duration', False);
Map.addLayer(gainDuration,durationViz, 'Gain Duration', False);



##############################################################################
#### Map setup ###
##############################################################################
Map.centerObject(lcms.filter(ee.Filter.eq('study_area', 'CONUS')).first().geometry())
Map.view()