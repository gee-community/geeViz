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

# Map.addLayer takes anything, and works out what it was given:
#   - an Earth Engine object, or an Earth Engine asset id as a plain string
#   - an ArcGIS feature layer, map service or image service URL, with its
#     options in viz (where, layers, time, reducer, ...)
#   - an XYZ tile URL; Query shows the color under the click, and the
#     classLegendDict class it matches
#   - GeoJSON as a URL, as text, or as a dict
# Map.addTimeLapse does the same for time series: an image collection (object
# or asset id) or a time-enabled ArcGIS service, one frame per time step.
# The specific methods (addEsriFeatureService, addTileLayer, ...) still work.
####################################################################################################
import json
import os
import sys

sys.path.append(os.getcwd())

import geeViz.geeView as gv

ee = gv.ee
Map = gv.mapper()
Map.setSkin("delta")

####################################################################################################
# Earth Engine: an object, and an asset id as a string (an image here; an
# image collection or a table id works the same way)
Map.addLayer(ee.Image("USGS/SRTMGL1_003").gt(2500).selfMask(), {"palette": "ffffff"}, "Above 2,500 m (ee object)", False)
Map.addLayer("USGS/SRTMGL1_003", {"min": 1400, "max": 3200, "palette": "1a9850,fee08b,d73027"}, "Elevation (asset id)", False)

# Earth Engine time lapse from an image collection asset id: JRC yearly
# surface water, 1984 to 2021 (its class names and colors are in the data)
Map.addTimeLapse("JRC/GSW1_4/YearlyHistory", {"autoViz": True}, "Surface water by year (asset id time lapse)", False)

####################################################################################################
# ArcGIS: the URL says which kind of service it is
# A feature layer (MTBS fire perimeters), filtered in viz
Map.addLayer("https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer/63",
             {"where": "year >= 2015", "chartField": "fire_type", "canAreaChart": True}, "Fires since 2015 (feature layer)")

# A map service, one sublayer (FEMA flood hazard zones; they draw from zoom 14 in)
Map.addLayer("https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer", {"layers": "show:28"}, "Flood hazard (map service)")

# An image service with a reducer: every Landsat scene from summer 2020,
# combined per pixel by the minimum (clouds, the brightest pixels, drop out).
# The reducer can be a name ("first", "last", "min", "max", "mean", "sum",
# "blend") or the matching ee.Reducer.
Map.addLayer(
    "https://landsat2.arcgis.com/arcgis/rest/services/Landsat/MS/ImageServer",
    {"time": ("2020-06-01", "2020-09-30"), "reducer": ee.Reducer.min(), "renderingRule": {"rasterFunction": "Natural Color with DRA"}},
    "Landsat summer 2020, min (image service)",
    False,
)

# A time-enabled image service as a time lapse: use addTimeLapse, not addLayer
Map.addTimeLapse(
    "https://imagery.geoplatform.gov/iipp/rest/services/Vegetation/USFS_EDW_LCMS_AnnualChange_CONUS/ImageServer",
    {"canAreaChart": True, "areaChartParams": {"line": True, "sankey": True}},
    "LCMS annual change (ArcGIS time lapse)",
    False,
)

####################################################################################################
# XYZ tiles: Query reads the color under the click. With classLegendDict,
# it names the class whose color is nearest; without it, the color itself.
Map.addLayer(
    "https://basemap.nationalmap.gov/arcgis/rest/services/USGSHydroCached/MapServer/tile/{z}/{y}/{x}",
    {"classLegendDict": {"Water body": "cbe6ff", "Stream or river": "78b0f0"}, "maxZoom": 16},
    "USGS hydrography (tiles, with a legend)",
)

####################################################################################################
# GeoJSON: a URL (loaded by the viewer), text, or a dict
Map.addLayer("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson",
             {"strokeColor": "d62728", "pointRadius": 6}, "Earthquakes this week (GeoJSON URL)", False)

study_area = {
    "type": "Feature",
    "properties": {"name": "Cameron Peak study area"},
    "geometry": {"type": "Polygon", "coordinates": [[[-105.9, 40.5], [-105.5, 40.5], [-105.5, 40.75], [-105.9, 40.75], [-105.9, 40.5]]]},
}
Map.addLayer(study_area, {"strokeColor": "ffffff", "strokeWeight": 2}, "Study area (GeoJSON dict)")
Map.addLayer(json.dumps({"type": "Feature", "properties": {"name": "Horsetooth Reservoir"},
                         "geometry": {"type": "Point", "coordinates": [-105.16208, 40.56226]}}),
             {"strokeColor": "1f77b4"}, "A point (GeoJSON text)")

Map.setCenter(-105.4, 40.6, 11)
Map.turnOnInspector()
Map.setMapTitle("Everything addLayer takes")
Map.view()
