#Example of how to utilize the Python visualization tools
#Uses the stock GEE NLCD assets and extracts the palette, names, and values
#Then uses those to color the raster and create a legend using the addToClassLegend option
####################################################################################################
#Import modules
import os,sys
sys.path.append(os.getcwd())

from geeViz.getImagesLib import *
####################################################################################################
#Bring in NLCD 2011
nlcd = ee.Image('USGS/NLCD/NLCD2011')

#Get the values, names, and palette
landcover_class_values = nlcd.get('landcover_class_values').getInfo();
landcover_class_names = nlcd.get('landcover_class_names').getInfo();
landcover_class_palette = nlcd.get('landcover_class_palette').getInfo();

#Zip the names and values together for the final legend names
name_values_zipped = [str(i[0]) + ' ' + i[1] for i in zip(landcover_class_values,landcover_class_names)]

#Fill any missing values in the NLCD classes so stretch is applied correctly 
landcover_class_palette_filled = []
landcover_class_labels_filled = []
for i in range(landcover_class_values[0],landcover_class_values[-1]+1):
	if i in landcover_class_values:
		landcover_class_palette_filled.append(landcover_class_palette[landcover_class_values.index(i)])
		landcover_class_labels_filled.append(name_values_zipped[landcover_class_values.index(i)])
	else:
		landcover_class_palette_filled.append('000')
		landcover_class_labels_filled.append('NA')

#Add the layers to the map
#For classes to show up in legend, need to set the min and max values in the palette
#Then provide a list of labels of the same length as palette
#Then set 'addToClassLegend' to 'true'
#If nothing is to be added to the legend, set 'addToLegend' to 'false'
Map.addLayer(nlcd.select([0]),{'min':landcover_class_values[0],'max':landcover_class_values[-1],'palette':landcover_class_palette_filled,'labels':landcover_class_labels_filled,'addToClassLegend':'true'},'NLCD 2011 Landcover/Landuse',False)

# Continuous data automatically have a legend added
Map.addLayer(nlcd.select([2]),{'min':20,'max':80,'palette':'555,0A0'},'NLCD 2011 TCC',False)

#Another example
mtbs = ee.ImageCollection('projects/USFS/LCMS-NFS/CONUS-Ancillary-Data/MTBS')
mtbs = mtbs.map(lambda img: img.updateMask(img.neq(0)).select([0],['Burn Severity']).byte())

#Set up MTBS legend and color properties
mtbsColors = ['006400','7fffd4','ffff00','ff0000','7fff00','ffffff']
mtbsLabels = ['1 Unburned to Low','2 Low','3 Moderate','4 High','5 Increased Greenness','6 Non-Processing Area Mask']

severityViz = {'min':1,'max':6,'palette':mtbsColors	,'labels':mtbsLabels, 'addToClassLegend': 'true'}

#Add it to the map
Map.addLayer(mtbs.max(),severityViz,'MTBS 1984-2016 Highest Severity',False)


#Bring in the JRS Surface water data
water = ee.ImageCollection('JRC/GSW1_0/YearlyHistory')

waterColors = ['ffffff','99d9ea','0000ff']
waterLabels = ['1 Not Water','2 Seasonal Water','3 Permanent Water']

Map.addLayer(water,{'min':1,'max':3,'palette':waterColors,'labels':waterLabels	,'addToClassLegend': 'true'},'JRC Surface Water',False)

#Final step is to launch the viewer
Map.view()