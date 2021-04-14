from geeViz.phEEnoViz  import *
#####################################################################################
#Exports table of n day median composite values for a sample of point locations
#It then creates a hovmuller-like plot of the time series
#This is a useful tool for exploring the variability of a given band/index across space and time
#####################################################################################
##Define user parameters:
#Define location of outputs
output_table_dir = r'C:\PheenoViz_Outputs'

#Define output table name (no extension needed)
output_table_name ='GA_Test2'
#Set up dates
#Years can range from 1984-present
#Julian days can range from 1-365
startYear = 2010
endYear = 2020
startJulian =1
endJulian = 365

#Number of samples to pull (Generally < 3000 or so will work)
nSamples = 2500

#Number of days in each median composite
compositePeriod = 16

#Bands to export. Can include: blue, green, red, nir, swir1, swir2, NDVI, NBR, NDMI, brightness, greenness, wetness, bloom2, NDGI
exportBands = ['NBR','NDVI','brightness','greenness','wetness']#['bloom2','NDGI','NDSI','NBR','NDVI','brightness','greenness','wetness']

#Whether to apply snow mask
maskSnow = True

# How many harmonics to include in fit
# Choices are 1, 2, or 3
# 1 will only include the first harmonic (1 htz) - This is best for fitting traditional seasonality
# 2 will include the first (1 htz) and second (2 htz) harmonics
# 3 will include the first (1 htz), second (2 htz), and third (3 htz) harmonics - This is best to fit to all regular cycles in the time series
howManyHarmonics = 1


#Whether to show the study area and samples
showGEEViz = False

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


clean_crescent_lake = ee.Geometry.Polygon(\
        [[[-122.05255927861896, 43.51304992163878],\
          [-122.05255927861896, 43.446285403511645],\
          [-121.93308296025958, 43.446285403511645],\
          [-121.93308296025958, 43.51304992163878]]], None, False)


clean_waldo_lake = ee.Geometry.Polygon(\
        [[[-122.08516666791367, 43.770494425923616],\
          [-122.08516666791367, 43.67621099378742],\
          [-122.0041424979918, 43.67621099378742],\
          [-122.0041424979918, 43.770494425923616]]], None, False)

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
permWater = ee.Image("JRC/GSW1_1/GlobalSurfaceWater").select([0]).gte(90).unmask(0)
tempWater =ee.ImageCollection("JRC/GSW1_1/MonthlyHistory")\
              .filter(ee.Filter.calendarRange(startYear,endYear,'year'))\
              .filter(ee.Filter.calendarRange(startJulian,endJulian)).mode().eq(2).unmask(0)

water_mask = permWater.Or(tempWater).selfMask()
studyArea = water_mask.clip(dirty_odell_lake).reduceToVectors(scale = 30)

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
lcmsLC = ee.ImageCollection("USFS/GTAC/LCMS/v2020-5").select(['Land_Cover']).mode()
lcmsTreeMask = lcmsLC.eq(1).selfMask()
studyArea = lcmsTreeMask.clip(uinta_tree).reduceToVectors(scale = 30)

#Can also look at other land cover classes
#This will look at grasses and shrubs
lcmsShrubMask = lcmsLC.eq(7).Or(lcmsLC.eq(10)).selfMask()
studyArea = lcmsShrubMask.clip(wy_shrub).reduceToVectors(scale = 90)

#Or you could use the NLCD Tree Canopy Cover layer to get a tree mask
nlcdTCC =  ee.ImageCollection("USGS/NLCD_RELEASES/2016_REL")\
              .filter(ee.Filter.calendarRange(2016,2016,'year'))\
              .select(['percent_tree_cover']).mosaic()
tccTreeMask = nlcdTCC.gte(30).selfMask()
studyArea = tccTreeMask.clip(ga_test).reduceToVectors(scale = 30)


#You can also just pass a feature collection (keeping the area relatively small helps ensure it will run)
states = ee.FeatureCollection("TIGER/2018/States")
studyArea = states.filter(ee.Filter.eq('STUSPS','VI'))
#Or also apply a mask to it as well
studyArea = tccTreeMask.clip(states.filter(ee.Filter.eq('STUSPS','VI')).geometry()).reduceToVectors(scale = 300)

studyArea = ga_test
######################################################################################
#Main function calls
if __name__ == '__main__':
  #Set up output directories
  table_dir = os.path.join(output_table_dir,output_table_name,'tables')
  chart_dir = os.path.join(output_table_dir,output_table_name)
  
  #Get raw json table of samples of time series across provided area
  if not os.path.exists(output_table_name):
    getTimeSeriesSample(startYear,endYear,startJulian,endJulian,compositePeriod,exportBands,studyArea,nSamples,os.path.join(table_dir,output_table_name+'.json',),showGEEViz = showGEEViz,maskSnow = maskSnow)


  #Create plots for each band
  #Get a list of csvs for the specified parameters
  csvs = glob.glob(os.path.join(table_dir,'*{}-{}_{}_{}*.csv'.format(startJulian,endJulian,compositePeriod,nSamples)))
  csvs = [i for i in csvs if int(os.path.splitext(os.path.basename(i))[0].split('_')[-5]) in range(startYear,endYear+1)]

  #Create plots
  chartTimeSeriesDistributions(csvs,chart_dir,output_table_name + '_{}-{}_{}-{}_{}_{}'.format(startYear,endYear,startJulian,endJulian,compositePeriod,nSamples),overwrite = overwriteCharts,howManyHarmonics = howManyHarmonics,showChart =showChart)