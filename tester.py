from getImagesLib import *
studyArea = ee.Geometry.Polygon(\
        [[[-124.02812499999999, 43.056605431434335],\
          [-124.02812499999999, 38.259489368377466],\
          [-115.94218749999999, 38.259489368377466],\
          [-115.94218749999999, 43.056605431434335]]])

# ls = getProcessedLandsatScenes(studyArea,2018,2018,190,250)
# print(ls.first().getInfo())
Map.addLayer(ee.Image('UMD/hansen/global_forest_change_2018_v1_6'),{},'test')
Map.view()