#Example of how to utilize the Python visualization tools
#Uses the stock GEE NLCD assets and extracts the palette, names, and values
#Then uses those to color the raster and create a legend using the addToClassLegend option setting it to True
#Then provide a color dictionary with the format: {value:hex_color} ex({'1':'FF0','2':'F00'})
#Since Python does not respect the order of keys in dictionaries, the dictionaries will be sorted by alpha/numeric order according to the keys
#Conversion of numbers to labels is supported with the queryDict key in the viz params
#Ex. {'1':'Water','2':'Trees'}
####################################################################################################
#Import modules
import os,sys
sys.path.append(os.getcwd())

from geeViz.getImagesLib import *
Map.clearMap()
####################################################################################################
#Bring in NLCD 2011
nlcd = ee.Image('USGS/NLCD/NLCD2011')

#Get the values, names, and palette
landcover_class_values = [int(i) for i in nlcd.get('landcover_class_values').getInfo()];
landcover_class_names = [i.split(' - ')[0] for i in nlcd.get('landcover_class_names').getInfo()];
landcover_class_palette = nlcd.get('landcover_class_palette').getInfo();

#Zip the names and values together for the final legend names
name_values_zipped = [str(i[0]) + ' ' + str(i[1]) for i in zip(landcover_class_values,landcover_class_names)]
nlcd_query_dict = dict(zip(landcover_class_values,landcover_class_names))
#Fill any missing values in the NLCD classes so stretch is applied correctly and construct various lookup dictionaries
landcover_class_palette_filled = []
landcover_class_labels_filled = []
landcover_class_dict = {}

for i in range(landcover_class_values[0],landcover_class_values[-1]+1):
	if i in landcover_class_values:
		landcover_class_palette_filled.append(landcover_class_palette[landcover_class_values.index(i)])
		landcover_class_labels_filled.append(name_values_zipped[landcover_class_values.index(i)])
		landcover_class_dict[name_values_zipped[landcover_class_values.index(i)]] = landcover_class_palette[landcover_class_values.index(i)]

	else:
		landcover_class_palette_filled.append('000')
		landcover_class_labels_filled.append('NA')

#Add the layers to the map
#For classes to show up in legend, need to set the 'addToClassLegend' key in the viz params to True
#Then provide a dictionary of the values and colors ex: {value:hex_color}
#If nothing is to be added to the legend, set 'addToLegend' to False
Map.addLayer(nlcd.select(['landcover']),{'min':landcover_class_values[0],'max':landcover_class_values[-1],'palette':landcover_class_palette_filled,'addToClassLegend':True,'classLegendDict':landcover_class_dict,'queryDict':nlcd_query_dict},'NLCD 2011 Landcover/Landuse',False)

# Continuous data automatically have a legend added
Map.addLayer(nlcd.select(['percent_tree_cover']),{'min':20,'max':80,'palette':'555,0A0'},'NLCD 2011 TCC',False)

#Another example
mtbs = ee.ImageCollection('projects/USFS/LCMS-NFS/CONUS-Ancillary-Data/MTBS')
mtbs = mtbs.map(lambda img: img.updateMask(img.neq(0)).select([0],['Burn Severity']).byte())

#Set up MTBS legend and color properties
mtbsColors = ['006400','7fffd4','ffff00','ff0000','7fff00','ffffff']
mtbsLabels = ['1 Unburned to Low','2 Low','3 Moderate','4 High','5 Increased Greenness','6 Non-Processing Area Mask']
mtbsDict =  {mtbsLabels[i]: mtbsColors[i] for i in range(len(mtbsColors))}
mtbsQueryDict = {'1':'Unburned to Low','2':'Low','3':'Moderate','4':'High','5':'Increased Greenness','6':'Non-Processing Area Mask'}
severityViz = {'min':1,'max':6,'palette':mtbsColors	, 'addToClassLegend': True,'classLegendDict':mtbsDict,'queryDict':mtbsQueryDict}

#Add it to the map
Map.addLayer(mtbs.max(),severityViz,'MTBS 1984-2016 Highest Severity',False)


#Bring in the JRS Surface water data
water = ee.ImageCollection('JRC/GSW1_0/YearlyHistory')

waterColors = ['ffffff','99d9ea','0000ff']
waterLabels = ['1 Not Water','2 Seasonal Water','3 Permanent Water']
waterDict =  {waterLabels[i]: waterColors[i] for i in range(len(waterColors))}
waterQueryDict =  {str(i+1): waterLabels[i] for i in range(len(waterLabels))}

Map.addLayer(water,{'min':1,'max':3,'palette':waterColors,'addToClassLegend': True,'classLegendDict':waterDict,'queryDict':waterQueryDict},'JRC Surface Water',False)

#Final step is to launch the viewer
Map.view()