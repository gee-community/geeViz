"""
   Copyright 2026 Ian Housman

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

# ArcGIS services in geoView, geeViz's default viewer, drawn by the browser the way the ArcGIS
# JS API draws them, with nothing fetched in Python:
#   - a dynamic map service (FEMA flood zones) drawn by export, its legend
#     from the service, and the Query tool asking it with identify
#   - a time-enabled image service (LCMS annual change) played as a timelapse,
#     queried for its values over time, and charted over time with a Sankey
#   - a feature layer (MTBS fire perimeters) fetched for the view and drawn
#     with the service's own renderer, its features counted by Chart area
#   - a GeoJSON layer, queryable by clicking it
# The first map has no Earth Engine layers, so the viewer never loads Earth
# Engine; its elevation readout comes from USGS 3DEP. The second adds an
# Earth Engine layer to the same services. examples/addLayerInputsExample.py
# shows every kind of input addLayer takes.
# Without geeViz or Earth Engine, georest.view's Map takes the same calls
# (pip install georest; see georest's examples/view_example.py).
####################################################################################################
import os, sys

sys.path.append(os.getcwd())

import geeViz.geeView as gv

ee = gv.ee

FEMA_FLOOD = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
LCMS_CHANGE = "https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_LCMS_AnnualChange_CONUS/ImageServer"
MTBS_FIRES = "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer/63"

# A study area west of Fort Collins, Colorado, as GeoJSON
study_area = {
    "type": "Feature",
    "properties": {"name": "Cameron Peak study area"},
    "geometry": {"type": "Polygon", "coordinates": [[[-105.9, 40.5], [-105.5, 40.5], [-105.5, 40.75], [-105.9, 40.75], [-105.9, 40.5]]]},
}

####################################################################################################
# No Earth Engine
Map = gv.mapper()
Map.setSkin("geoview")

# Every time step of a time-enabled service, one frame per year. Turn it on
# in the layer list to load it; Chart area charts it over time.
Map.addTimeLapse(LCMS_CHANGE, {"canAreaChart": True, "areaChartParams": {"line": True, "sankey": True}}, "LCMS annual change")

# One year of the same service. addLayer tells an image service, a map
# service and a feature layer apart by the URL; their options go in viz.
Map.addLayer(LCMS_CHANGE, {"time": 2020, "canAreaChart": True}, "LCMS change 2020")

# Fire perimeters since 2015, drawn with the service's renderer; Chart area
# counts them by fire type
Map.addLayer(MTBS_FIRES, {"where": "year >= 2015", "canAreaChart": True, "chartField": "fire_type"}, "Fires since 2015")

# Flood hazard zones only (sublayer 28); they draw from zoom 14 in
Map.addLayer(FEMA_FLOOD, {"layers": "show:28"}, "FEMA flood hazard zones")

Map.addLayer(study_area, {"strokeColor": "ffffff", "strokeWeight": 2}, "Study area")

Map.setCenter(-105.65, 40.62, 11)
Map.turnOnInspector()
Map.setMapTitle("ArcGIS services, no Earth Engine")
Map.view()

####################################################################################################
# The same services with an Earth Engine layer
Map2 = gv.mapper()
Map2.setSkin("geoview")
Map2.addLayer(ee.Image("USGS/SRTMGL1_003"), {"min": 1500, "max": 4000, "palette": "1a9850,fee08b,d73027"}, "SRTM elevation (Earth Engine)")
Map2.addLayer(LCMS_CHANGE, {"time": 2020}, "LCMS change 2020")
Map2.addLayer(MTBS_FIRES, {"where": "year >= 2015"}, "Fires since 2015")
Map2.addLayer(study_area, {"strokeColor": "ffffff", "strokeWeight": 2}, "Study area")
Map2.setCenter(-105.65, 40.62, 11)
Map2.turnOnInspector()
Map2.setMapTitle("ArcGIS services with Earth Engine")
Map2.view()
