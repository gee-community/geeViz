"""
   Copyright 2024 Ian Housman, Maria Olga Borja

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

# An example of using geeViz to explore the MapBiomas latest Collection outputs
# Adapted from various scripts in https://gee-community-catalog.org/projects/mapbiomas/
####################################################################################################
import os, sys

sys.path.append(os.getcwd())

import ee

# ee.Initialize(project="lcms-292214")

# Module imports
import geeViz.geeView as gv

# Module to help with class codes, names, colors and collapsing levels of MapBiomas data
import geeViz.examples.mapBiomasLookup as mbl

ee = gv.ee
Map = gv.Map
Map.clearMap()
Map.port = 8000


####################################################################################################
# Datasets available here: https://gee-community-catalog.org/projects/mapbiomas/

# Specify which years to show
years = list(range(1985, 2023 + 1))


# Specify projection to use for zonal summaries and map querying
# Be sure to leave one of scale or transform as None
crs = "EPSG:4326"
transform = None
scale = 30

# Choose which level to show (1-4)
# Only 1 and 2 work with on-the-fly Sankey charts
remap_level = 4


Map.setQueryCRS(crs)
if transform == None:
    Map.setQueryScale(scale)
else:
    Map.setQueryTransform(transform)


# Bring in land use land cover datasets and mosaic them
paths = [
    "projects/mapbiomas-public/assets/bolivia/collection2/mapbiomas_bolivia_collection2_integration_v1",  # 1985-2023
    "projects/mapbiomas-public/assets/peru/collection2/mapbiomas_peru_collection2_integration_v1",  # 1985-2022
    "projects/mapbiomas-public/assets/colombia/collection1/mapbiomas_colombia_collection1_integration_v1",  # 1985-2022
    "projects/mapbiomas-public/assets/ecuador/collection1/mapbiomas_ecuador_collection1_integration_v1",  # 1985-2022
    "projects/mapbiomas-public/assets/venezuela/collection1/mapbiomas_venezuela_collection1_integration_v1",  # 1985-2022
    "projects/mapbiomas-public/assets/paraguay/collection1/mapbiomas_paraguay_collection1_integration_v1",  # 1985-2022
    "projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1",  # 1985-2023
    "projects/mapbiomas-raisg/public/collection5/mapbiomas_raisg_panamazonia_collection5_integration_v1",  # 1985-2022
    "projects/MapBiomas_Pampa/public/collection3/mapbiomas_uruguay_collection1_integration_v1",  # 1985-2022
    "projects/mapbiomas-public/assets/chile/collection1/mapbiomas_chile_collection1_integration_v1",  # 2000-2022
    "projects/mapbiomas-public/assets/argentina/collection1/mapbiomas_argentina_collection1_integration_v1",  # 1998-2022
]

stack = ee.ImageCollection([ee.Image(p).byte() for p in paths]).toBands()

# View palettes source here:
# var palettes = require('users/mapbiomas/modules:Palettes.js');


out_band_name = "lulc"


# Bring in the names, values, and palette
remap_info = mbl.getLevelNRemap(remap_level, out_band_name)


# Function to convert a given band into a time-enabled image object
def setupLulc(yr):

    img = stack.select([f".*_{yr}"]).reduce(ee.Reducer.firstNonNull()).remap(remap_info["remap_from"], remap_info["remap_to"]).rename([out_band_name]).set("system:time_start", ee.Date.fromYMD(yr, 6, 1).millis())
    img = img.set(remap_info["viz_dict"])
    return img


# Convert the image stack into an image collection
lulcC = ee.ImageCollection([setupLulc(yr) for yr in years])

# Only allow Sankey charts for levels <=2
sankey = True
if remap_level > 2:
    sankey = False

# Add the collection to the map
Map.addTimeLapse(lulcC, {"canAreaChart": True, "autoViz": True, "years": years, "areaChartParams": {"line": True, "sankey": sankey, "crs": crs, "transform": transform, "scale": scale}}, "MapBiomas LULC")

# Add layers to summarize by
countries = ee.FeatureCollection("FAO/GAUL_SIMPLIFIED_500m/2015/level0")
Map.addSelectLayer(countries, {}, "Global Country Boundaries")

assetTerritories = ee.FeatureCollection("users/joaovsiqueira1/MAPBIOMAS/ti_uc")
Map.addSelectLayer(assetTerritories, {}, "MapBiomas Territories")


## Set up the map
Map.turnOnAutoAreaCharting()
Map.turnOffLayersWhenTimeLapseIsOn = False
# Map.turnOnInspector()
Map.setCenter(-62.8, -3, 4)

Map.view()
