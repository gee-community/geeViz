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

# ArcGIS services in the Delta viewer, drawn by the browser the way the ArcGIS
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
# Earth Engine layer to the same services.
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
Map.setSkin("delta")

# Every time step of a time-enabled service, one frame per year. Turn it on
# in the layer list to load it; Chart area charts it over time.
Map.addTimeLapse(LCMS_CHANGE, {"canAreaChart": True, "areaChartParams": {"line": True, "sankey": True}}, "LCMS annual change")

# One year of the same service
Map.addEsriImageService(LCMS_CHANGE, name="LCMS change 2020", time=2020, viz_params={"canAreaChart": True})

# Fire perimeters since 2015, drawn with the service's renderer; Chart area
# counts them by fire type
Map.addEsriFeatureService(MTBS_FIRES, name="Fires since 2015", where="year >= 2015",
                          viz_params={"canAreaChart": True, "chartField": "fire_type"})

# Flood hazard zones only (sublayer 28); they draw from zoom 14 in
Map.addEsriMapService(FEMA_FLOOD, name="FEMA flood hazard zones", viz_params={"layers": "show:28"})

Map.addLayer(study_area, {"strokeColor": "ffffff", "strokeWeight": 2}, "Study area")

Map.setCenter(-105.65, 40.62, 11)
Map.turnOnInspector()
Map.setMapTitle("ArcGIS services, no Earth Engine")
Map.view()

####################################################################################################
# The same services with an Earth Engine layer
Map2 = gv.mapper()
Map2.setSkin("delta")
Map2.addLayer(ee.Image("USGS/SRTMGL1_003"), {"min": 1500, "max": 4000, "palette": "1a9850,fee08b,d73027"}, "SRTM elevation (Earth Engine)")
Map2.addEsriImageService(LCMS_CHANGE, name="LCMS change 2020", time=2020)
Map2.addEsriFeatureService(MTBS_FIRES, name="Fires since 2015", where="year >= 2015")
Map2.addLayer(study_area, {"strokeColor": "ffffff", "strokeWeight": 2}, "Study area")
Map2.setCenter(-105.65, 40.62, 11)
Map2.turnOnInspector()
Map2.setMapTitle("ArcGIS services with Earth Engine")
Map2.view()
