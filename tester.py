from getImagesLib import *
studyArea = ee.Geometry.Polygon(\
        [[[-124.02812499999999, 43.056605431434335],\
          [-124.02812499999999, 38.259489368377466],\
          [-115.94218749999999, 38.259489368377466],\
          [-115.94218749999999, 43.056605431434335]]])

ls = getProcessedLandsatScenes(studyArea,2018,2018,190,250)
# print(ee.Image(ls.first()).bandNames().getInfo())
medoid = medoidMosaicMSD(ls,['nir','swir1','swir2'])
# print(ls.first().getInfo())
Map.addLayer(medoid,vizParamsFalse,'test')
medoid = medoidMosaicMSD(ls,['blue','green','red','nir','swir1','swir2'])
# print(ls.first().getInfo())
Map.addLayer(medoid,vizParamsFalse,'test2')
Map.view()