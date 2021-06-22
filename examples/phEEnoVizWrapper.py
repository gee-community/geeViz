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

import os,glob
import geeViz.phEEnoViz  as phEEnoViz
ee = phEEnoViz.ee
Map = phEEnoViz.Map
#####################################################################################
#Exports table of n day median composite values for a sample of point locations
#It then creates a hovmuller-like plot of the time series
#This is a useful tool for exploring the variability of a given band/index across space and time
#####################################################################################
##Define user parameters:
#Define location of outputs
output_table_dir = r'C:\PheenoViz_Outputs'

#Define output table name (no extension needed)
output_table_name ='Clean_OR3'
#Set up dates
#Years can range from 1984-present
#Julian days can range from 1-365
startYear = 2015
endYear = 2020
startJulian =1
endJulian = 365

#Number of samples to pull (Generally < 3000 or so will work)
nSamples = 5000

#Number of days in each median composite
compositePeriod = 30

#Which programs to include
#Options are Landsat and Sentinel 2
#E.g. ['Landsat','Sentinel2'] will include both Landsat 4-8 and Sentinel 2a and 2b TOA data
#If choosing both Landsat and Sentinel 2, available bands/indices are limited to those that can be computed
#Using bands from each (e.g. Sentinel 2 red edge bands would not be available if using only Landsat or Landsat and Sentinel 2)
programs = ['Landsat','Sentinel2']

#Bands to export. 
#Landsat and Sentinel2 combined band options include: blue, green, red, nir, swir1, swir2, NDVI, NBR, NDMI, brightness, greenness, wetness, bloom2, NDGI
#Sentinel 2 only band options include: 'cb', 'blue', 'green', 'red', 're1','re2','re3','nir', 'nir2', 'waterVapor', 'cirrus','swir1', 'swir2', NDVI, NBR, NDMI, brightness, greenness, wetness, bloom2, NDGI, NDCI
#Landsat only band options include: blue, green, red, nir, swir1, swir2, temp, NDVI, NBR, NDMI, brightness, greenness, wetness, bloom2, NDG
exportBands = ['bloom2','NDGI']#['bloom2','NDGI','NDSI','NBR','NDVI','brightness','greenness','wetness']

#Whether to apply snow mask
maskSnow = True

# How many harmonics to include in fit
# Choices are 1, 2, or 3
# 1 will only include the first harmonic (1 htz) - This is best for fitting traditional seasonality
# 2 will include the first (1 htz) and second (2 htz) harmonics
# 3 will include the first (1 htz), second (2 htz), and third (3 htz) harmonics - This is best to fit to all regular cycles in the time series
howManyHarmonics = 1

#Whether to annotate dates of peaks and troughs of harmonic curve on chart
annotate_harmonic_peaks = True

#Whether to show the study area and samples
showGEEViz = True

#Whether to show charts in an interactive, non-png version as they are being created
showChart = False

#Whether to overwrite already produced png chargs
overwriteCharts = True


##############################################################
#Set up study areas
#Generally copy and paste from the Playground
mn_test =ee.Geometry.Polygon(\
        [[[-92.40898254274096, 48.17134997592254],\
          [-92.40898254274096, 47.855327704615014],\
          [-91.66465881227221, 47.855327704615014],\
          [-91.66465881227221, 48.17134997592254]]], None, False)

dirty_billy_chinook = ee.Geometry.Polygon(\
        [[[-121.48239392202757, 44.62035796573114],\
          [-121.48239392202757, 44.509308410535326],\
          [-121.2262751476135, 44.509308410535326],\
          [-121.2262751476135, 44.62035796573114]]], None, False)
        
dirty_odell_lake = ee.Geometry.Polygon(\
        [[[-122.0549625378963, 43.59540724921347],\
          [-122.0549625378963, 43.547151047382215],\
          [-121.95436897100177, 43.547151047382215],\
          [-121.95436897100177, 43.59540724921347]]], None, False)


clean_or_combo = ee.Geometry.MultiPolygon(\
        [[[[-122.16247277538403, 42.98060571118538],\
           [-122.16247277538403, 42.9016878744337],\
           [-122.0512362031184, 42.9016878744337],\
           [-122.0512362031184, 42.98060571118538]]],\
         [[[-122.03353176573546, 43.50210081409495],\
           [-122.03353176573546, 43.45925265588565],\
           [-121.95216427305968, 43.45925265588565],\
           [-121.95216427305968, 43.50210081409495]]],\
         [[[-122.06863020193826, 43.76538659547769],\
           [-122.06863020193826, 43.6812758137654],\
           [-122.00648878348123, 43.6812758137654],\
           [-122.00648878348123, 43.76538659547769]]]], None, False)

wy_clean_lake_combo = ee.Geometry.MultiPolygon(\
        [[[[-109.56790010304167, 42.96292917782831],\
           [-109.56790010304167, 42.953161377243354],\
           [-109.55584089131071, 42.953161377243354],\
           [-109.55584089131071, 42.96292917782831]]],\
         [[[-109.70411340565397, 42.94700466781123],\
           [-109.70411340565397, 42.92224596795357],\
           [-109.66875116200163, 42.92224596795357],\
           [-109.66875116200163, 42.94700466781123]]],\
         [[[-108.95214927727804, 42.591368975972856],\
           [-108.95214927727804, 42.57948841139656],\
           [-108.92897499138937, 42.57948841139656],\
           [-108.92897499138937, 42.591368975972856]]]], None, False)

wa_clean_lake_combo = ee.Geometry.MultiPolygon(\
        [[[[-121.32593536613808, 47.586467669618045],\
           [-121.32593536613808, 47.56342205752472],\
           [-121.27993011711465, 47.56342205752472],\
           [-121.27993011711465, 47.586467669618045]]],\
         [[[-121.39322662590371, 47.59920209760001],\
           [-121.39322662590371, 47.57685691359207],\
           [-121.37297058342324, 47.57685691359207],\
           [-121.37297058342324, 47.59920209760001]]],\
         [[[-121.33949661491738, 47.60695700338792],\
           [-121.33949661491738, 47.59723425208618],\
           [-121.32748031853066, 47.59723425208618],\
           [-121.32748031853066, 47.60695700338792]]]], None, False)


uinta_tree = ee.Geometry.Polygon(
        [[[-110.40497889529719, 40.90051259604438],
          [-110.40497889529719, 40.88260469436617],
          [-110.37871470462336, 40.88260469436617],
          [-110.37871470462336, 40.90051259604438]]], None, False)

hi_tree =  ee.Geometry.Polygon(
        [[[-159.607354826546, 22.196132168064572],
          [-159.607354826546, 21.984900822281173],
          [-159.36840218982724, 21.984900822281173],
          [-159.36840218982724, 22.196132168064572]]], None, False)
pa_test =  ee.Geometry.Polygon(
        [[[-77.94513497907685, 41.54746570321669],
          [-77.94513497907685, 41.479596644089234],
          [-77.84763131696748, 41.479596644089234],
          [-77.84763131696748, 41.54746570321669]]], None, False)

ga_test =  ee.Geometry.Polygon(
        [[[-82.3790983772916, 30.95445354200833],
          [-82.3790983772916, 30.906450132675282],
          [-82.32382341391269, 30.906450132675282],
          [-82.32382341391269, 30.95445354200833]]], None, False)

wy_shrub = ee.Geometry.Polygon(
        [[[-110.76053085702868, 41.45704904554832],
          [-110.76053085702868, 41.29732441864774],
          [-110.48037948984118, 41.29732441864774],
          [-110.48037948984118, 41.45704904554832]]], None, False)


#Can set up any mask or really any polygon you'd like to sample
#Here are some examples

#If you want to sample water, using the JRC water layers works well
startWaterYear = startYear
endWaterYear = endYear
if startYear > 2018: startWaterYear = 2018
if endYear > 2018: endWaterYear = 2018
permWater = ee.Image("JRC/GSW1_1/GlobalSurfaceWater").select([0]).gte(90).unmask(0)
tempWater =ee.ImageCollection("JRC/GSW1_1/MonthlyHistory")\
              .filter(ee.Filter.calendarRange(startWaterYear,endWaterYear,'year'))\
              .filter(ee.Filter.calendarRange(startJulian,endJulian)).mode().eq(2).unmask(0)

water_mask = permWater.Or(tempWater).selfMask()
studyArea = water_mask.clip(clean_or_combo).reduceToVectors(scale = 30)
# studyArea = dirty_odell_lake
#If you would like to visualize phenology of trees, the LCMS tree layer works well
#LCMS land cover classes are as follows:
# 1: Trees
# 2: Tall Shrubs & Trees Mix (SEAK Only)
# 3: Shrubs & Trees Mix
# 4: Grass/Forb/Herb & Trees Mix
# 5: Barren & Trees Mix
# 6: Tall Shrubs (SEAK Only)
# 7: Shrubs
# 8: Grass/Forb/Herb & Shrubs Mix
# 9: Barren & Shrubs Mix
# 10: Grass/Forb/Herb
# 11: Barren & Grass/Forb/Herb Mix
# 12: Barren or Impervious
# 13: Snow or Ice
# 14: Water
# 15: Non-Processing Area Mask
# lcmsLC = ee.ImageCollection("USFS/GTAC/LCMS/v2020-5").select(['Land_Cover']).mode()
# lcmsTreeMask = lcmsLC.eq(1).selfMask()
# studyArea = lcmsTreeMask.clip(uinta_tree).reduceToVectors(scale = 30)

# #Can also look at other land cover classes
# #This will look at grasses and shrubs
# lcmsShrubMask = lcmsLC.eq(7).Or(lcmsLC.eq(10)).selfMask()
# studyArea = lcmsShrubMask.clip(wy_shrub).reduceToVectors(scale = 90)

# #Or you could use the NLCD Tree Canopy Cover layer to get a tree mask
# nlcdTCC =  ee.ImageCollection("USGS/NLCD_RELEASES/2016_REL")\
#               .filter(ee.Filter.calendarRange(2016,2016,'year'))\
#               .select(['percent_tree_cover']).mosaic()
# tccTreeMask = nlcdTCC.gte(30).selfMask()
# studyArea = tccTreeMask.clip(ga_test).reduceToVectors(scale = 30)


# #You can also just pass a feature collection (keeping the area relatively small helps ensure it will run)
# states = ee.FeatureCollection("TIGER/2018/States")
# studyArea = states.filter(ee.Filter.eq('STUSPS','VI'))
#Or also apply a mask to it as well
# studyArea = tccTreeMask.clip(states.filter(ee.Filter.inList('STUSPS',['PR','VI'])).geometry()).reduceToVectors(scale = 300)

# studyArea = ga_test#states.filter(ee.Filter.inList('STUSPS',['PR','VI']))
######################################################################################
#Main function calls
if __name__ == '__main__':
  #Set up output directories
  table_dir = os.path.join(output_table_dir,output_table_name,'tables')
  chart_dir = os.path.join(output_table_dir,output_table_name)
  
  #Get raw json table of samples of time series across provided area
  if not os.path.exists(output_table_name):
    phEEnoViz.getTimeSeriesSample(startYear,endYear,startJulian,endJulian,compositePeriod,exportBands,studyArea,nSamples,os.path.join(table_dir,output_table_name+'.json',),showGEEViz = showGEEViz,maskSnow = maskSnow,programs = programs)


  #Create plots for each band
  #Get a list of csvs for the specified parameters
  csvs = glob.glob(os.path.join(table_dir,'*{}*_{}-{}_{}_{}*.csv'.format('-'.join(programs),startJulian,endJulian,compositePeriod,nSamples)))
  csvs = [i for i in csvs if int(os.path.splitext(os.path.basename(i))[0].split('_')[-5]) in range(startYear,endYear+1)]
  # print(csvs)
  #Create plots
  phEEnoViz.chartTimeSeriesDistributions(csvs,chart_dir,output_table_name + '_{}_{}-{}_{}-{}_{}_{}'.format('-'.join(programs),startYear,endYear,startJulian,endJulian,compositePeriod,nSamples),overwrite = overwriteCharts,howManyHarmonics = howManyHarmonics,showChart =showChart,annotate_harmonic_peaks = annotate_harmonic_peaks)