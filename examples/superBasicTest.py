# This is a super basic geeViz test script

import geeViz.getImagesLib as getImagesLib

ee = getImagesLib.ee
Map = getImagesLib.Map

# Clear map
Map.clearMap()

# Add California test area from built-in test areas
studyArea = getImagesLib.testAreas["CA"]

# Create a simple NDVI image for demonstration
simple_img = getImagesLib.superSimpleGetS2(studyArea,startDate="2020-07-01",endDate="2020-09-30")

# Add image and boundary to the map
Map.addLayer(simple_img, getImagesLib.vizParamsFalse10k, "Simple S2")
Map.addLayer(studyArea, {"color": "blue"}, "CA Study Area", False)

Map.centerObject(studyArea, 6)
Map.turnOnInspector()

# Show map
# Map.view(True)
Map.view(open_iframe=True, open_browser=False)