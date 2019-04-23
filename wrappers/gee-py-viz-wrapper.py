import os,sys
sys.path.append(os.getcwd())

from getImagesLib import *

nlcd = ee.Image('USGS/NLCD/NLCD2011')
landcover_class_values = nlcd.get('landcover_class_values').getInfo();
landcover_class_names = nlcd.get('landcover_class_names').getInfo();
name_values_zipped = [str(i[0]) + ' ' + i[1] for i in zip(landcover_class_values,landcover_class_names)]
landcover_class_palette = nlcd.get('landcover_class_palette').getInfo();
landcover_class_palette_filled = []
for i in range(landcover_class_values[0],landcover_class_values[-1]+1):
	if i in landcover_class_values:
		landcover_class_palette_filled.append(landcover_class_palette[landcover_class_values.index(i)])
	else:landcover_class_palette_filled.append('000')


classLegendDict = dict(zip(name_values_zipped, landcover_class_palette))


mtbs = ee.ImageCollection('projects/USFS/LCMS-NFS/CONUS-Ancillary-Data/MTBS')
# print(landcover_class_values[0],landcover_class_values[-1])
Map.addLayer(nlcd.select([0]),{'min':landcover_class_values[0],'max':landcover_class_values[-1],'palette':','.join(landcover_class_palette_filled),'addToClassLegend':'true','classLegendDict':classLegendDict},'NLCD 2016 Landcover/Landuse',True)
Map.addLayer(nlcd.select([2]),{'min':20,'max':80,'palette':'555,0A0'},'NLCD 2016 TCC',True)

# print(nlcd.getInfo())
# tcc = ee.Image('USGS/NLCD/NLCD2011').select([2])
# tcc = tcc.add(10).divide(10).divide(2)
studyArea = ee.Geometry.Polygon(\
        [[[-111.7654963662082, 41.06903449786562],\
          [-111.7654963662082, 40.18520498309448],\
          [-111.0074397255832, 40.18520498309448],\
          [-111.0074397255832, 41.06903449786562]]])
# studyArea = ee.Geometry.Point([-142.99413098899095, 60.1571492360815])

startYear = 2016
endYear = 2018
# tsNear  = ee.ImageCollection(getLandsatWrapper(studyArea,startYear,endYear,190,250,1,[1],performCloudScoreOffset = False,resampleMethod = 'near')[1])
# tsBilinear  = ee.ImageCollection(getLandsatWrapper(studyArea,startYear,endYear,190,250,1,[1],performCloudScoreOffset = False,resampleMethod = 'bilinear')[1])
# tsCubic  = ee.ImageCollection(getLandsatWrapper(studyArea,startYear,endYear,190,250,1,[1],performCloudScoreOffset = False,resampleMethod = 'bicubic')[1])


tsNear  = getModisData(startYear,endYear,190,250,resampleMethod = 'near')
tsBilinear  = getModisData(startYear,endYear,190,250,resampleMethod = 'bilinear')
tsCubic  = getModisData(startYear,endYear,190,250,resampleMethod = 'bicubic')

# out =  getSentinel2Wrapper(studyArea,startYear,endYear,190,250,1,[1,5,1],performCloudScoreOffset = False,resampleMethod = 'near')
# ts = ee.ImageCollection(out[1])


for yr in range(startYear,endYear+1):
    near = tsNear.filter(ee.Filter.calendarRange(yr,yr,'year')).median()
    bilinear = tsBilinear.filter(ee.Filter.calendarRange(yr,yr,'year')).median().reproject('EPSG:5070',None,250)
    cubic = tsCubic.filter(ee.Filter.calendarRange(yr,yr,'year')).median().reproject('EPSG:5070',None,250)
    # Map.addLayer(ee.Image(tcc),{},str(yr),False)
    Map.addLayer(near,vizParamsFalse,'Near Raw ' +str(yr),False)
    Map.addLayer(near.reproject('EPSG:5070',None,250),vizParamsFalse,'Near ' +str(yr),False)
    Map.addLayer(bilinear,vizParamsFalse,'Bilinear ' +str(yr),False)
    Map.addLayer(cubic,vizParamsFalse,'Cubic ' +str(yr),False)
Map.launchGEEVisualization()