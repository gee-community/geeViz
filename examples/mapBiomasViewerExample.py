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
#ee.Initialize(project="lcms-292214")

# Module imports
import geeViz.geeView as gv

ee = gv.ee
Map = gv.Map
Map.clearMap()
Map.port=8000


####################################################################################################
# Datasets available here: https://gee-community-catalog.org/projects/mapbiomas/

# Specify which years to show
years = list(range(1985, 2023 + 1))
year_bandNames = [f"classification_{yr}" for yr in years]


# Specify projection to use for zonal summaries and map querying
# Be sure to leave one of scale or transform as None
crs = "EPSG:4326"
transform = None
scale = 30


Map.setQueryCRS(crs)
if transform == None:
    Map.setQueryScale(scale)
else:
    Map.setQueryTransform(transform)


# Make an empty stack to handle missing years for some areas
empty_stack = ee.ImageCollection([ee.Image().byte() for yb in year_bandNames]).toBands().rename(year_bandNames)


# Bring in land use land cover datasets and mosaic them
paths = [
    "projects/mapbiomas-public/assets/bolivia/collection2/mapbiomas_bolivia_collection2_integration_v1",        # 1985-2023
    "projects/mapbiomas-public/assets/peru/collection2/mapbiomas_peru_collection2_integration_v1",              # 1985-2022
    "projects/mapbiomas-public/assets/colombia/collection1/mapbiomas_colombia_collection1_integration_v1",      # 1985-2022
    "projects/mapbiomas-public/assets/ecuador/collection1/mapbiomas_ecuador_collection1_integration_v1",        # 1985-2022
    "projects/mapbiomas-public/assets/venezuela/collection1/mapbiomas_venezuela_collection1_integration_v1",    # 1985-2022
    "projects/mapbiomas-public/assets/paraguay/collection1/mapbiomas_paraguay_collection1_integration_v1",      # 1985-2022
    "projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1",           # 1985-2023
    "projects/mapbiomas-raisg/public/collection5/mapbiomas_raisg_panamazonia_collection5_integration_v1",       # 1985-2022
    "projects/MapBiomas_Pampa/public/collection3/mapbiomas_uruguay_collection1_integration_v1",                 # 1985-2022
    "projects/mapbiomas-public/assets/chile/collection1/mapbiomas_chile_collection1_integration_v1",            # 2000-2022
    "projects/mapbiomas-public/assets/argentina/collection1/mapbiomas_argentina_collection1_integration_v1",    # 1998-2022
]



# Bring in each area and fill in empty years
lulcImg = []
for path in paths:
    lulcImg.append(empty_stack.addBands(ee.Image(path).byte(), None, True))
print(ee.Image(paths[0]).projection().getInfo())
lulcImg = ee.ImageCollection(lulcImg).mosaic()

#Remap level 3 and 4 to level 2 classes

#Map.clearMap()
#originalClasses = [3, 4, 5, 6, 49, 45, 11, 12, 42, 43, 44, 32, 29, 50, 13, 66, 63, 15, 18, 19, 39, 20, 40, 62, 41, 57, 58, 36, 46, 47, 35, 65, 48, 9, 21, 22, 23, 24, 30, 25, 61, 33, 31, 34, 27]
#remappedClasses = [3, 4, 5, 6, 49, 45, 11, 12, 12, 12, 12, 32, 29, 50, 13, 66, 63, 15, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18, 9, 21, 22, 23, 24, 30, 25, 61, 33, 31, 34, 27]
#print(len(set(remappedClasses)))
#lulcImg = lulcImg.remap(originalClasses, remappedClasses).select(['remapped']).rename('MBremaped_2007')
#print(lulcImg.bandNames().getInfo())
#Map.addLayer(lulcImg)
#Map.view()


# Bring in the names, values, and palette
names = [
    # "1. Forest"
    "1.1. Forest Formation",
    "1.2. Savanna Formation",
    "1.3. Mangrove",
    "1.4. Floodable Forest",
    "1.5. Wooded Sandbank Vegetation",
    "1.6. Sparse Woodland",
    # "2. Non Forest Formations"
    "2.1. Wetland",
    "2.2. Grassland",
    #"2.1.1. Open Grassland",
    #"2.1.2. Closed Grassland",
    #"2.1.3. Sparse Grassland",
    "2.3. Hypersaline Tidal Flat",
    "2.4. Rocky Outcrop",
    "2.5. Herbaceous Sandbank Vegetation",
    "2.6. Other Non Forest Formations",
    "2.7. Shrubland",
    "2.8. Steppe",
    # "3. Farming"
    "3.1. Pasture",
    "3.2. Agriculture",
    #"3.2.1. Temporary Crop",
    #"3.2.1.1. Soybean",
    #"3.2.1.2. Sugar cane",
    #"3.2.1.3. Rice",
    #"3.2.1.4. Cotton (beta)",
    #"3.2.1.5. Other Temporary Crops",
    #"3.2.1.6. Single Crop",
    #"3.2.1.7. Multiple Crops",
    #"3.2.2 Perennial Crop",
    #"3.2.2.1. Coffee",
    #"3.2.2.2. Citrus",
    #"3.2.2.3. Palm Oil (beta)",
    #"3.2.2.4. Tea",
    #"3.2.2.5. Other Perennial Crops",
    "3.3. Forest Plantation",
    "3.4. Mosaic of Uses",
    # "4. Non Vegetated Areas"
    "4. Non vegetated area",
    "4.1. Beach, Dune and Sand Spot",
    "4.2. Urban Area",
    "4.3. Mining",
    "4.4. Other non Vegetated Areas",
    "2.4. Salt Flat",
    # "5. Water"
    "5.1. River, Lake and Ocean",
    "5.2. Aquaculture",
    "5.3. Glacier",
    # "6. Not Observed"
    "6. Not Observed"
    
]
values = [
    # "1. Forest"
    3,
    4,
    5,
    6,
    49,
    45,
    # "2. Non Forest Formations"
    11,
    12,
    #42,
    #43,
    #44,
    32,
    29,
    50,
    13,
    66,
    63,
    # "3. Farming"
    15,
    18,
    #19,
    #39,
    #20,
    #40,
    #62,
    #41,
    #57,
    #58,
    #36,
    #46,
    #47,
    #35,
    #65,
    #48,
    9,
    21,
 # "4. Non Vegetated Areas"   
    22,
    23,
    24,
    30,
    25,
    61,
    # "5. Water"
    33,
    31,
    34,
    # "6. Not Observed"
    27
]

palette = [
    # "1. Forest"
    "1f8d49",
    "7dc975",
    "04381d",
    "007785",
    "02d659",
    "807a40",
    # "2. Non Forest Formations"
    "519799",
    "d6bc74",
    #"a5b35b",
    #"c2d26b",
    #"cbe286",
    "fc8114",
    "ffaa5f",
    "ad5100",
    "d89f5c",
    "a89358",
    "ebf8b5",
    # "3. Farming"
    "edde8e",
    "E974ED",
    #"C27BA0",
    #"f5b3c8",
    #"db7093",
    #"c71585",    
    #"ff69b4",   
    #"f54ca9",  
    #"f99fff",
    #"d84690",  
    #"d082de",
    #"d68fe2",
    #"9932cc",
    #"9065d0",
    #"b9158a",
    #"e6ccff",
    "7a5900",
    "ffefc3",
    # "4. Non Vegetated Areas"  
    "d4271e",
    "ffa07a",
    "d4271e",
    "9c0027",
    "db4d4f",
    "f5d5d5",
    # "5. Water"
    "2532e4",
    "091077",
    "93dfe6",
    # "6. Not Observed"
    "ffffff"
]


print(len(names))
print(len(palette))
print(len(values))

# View palettes source here:
# var palettes = require('users/mapbiomas/modules:Palettes.js');

# Convert image to image collection
bns = lulcImg.bandNames()

out_band_name = "lulc"


# Function to convert a given band into a time-enabled image object
def setupLulc(bn):
    bn = ee.String(bn)
    yr = ee.Number.parse(ee.String(bn).split("_").get(1))
    img = lulcImg.select(bn).rename([out_band_name]).set("system:time_start", ee.Date.fromYMD(yr, 6, 1).millis())
    img = img.set(
        {
            f"{out_band_name}_class_names": names,
            f"{out_band_name}_class_palette": palette,
            f"{out_band_name}_class_values": values,
        }
    )
    return img


# Convert the image stack into an image collection
lulcC = ee.ImageCollection(bns.map(setupLulc))

print(lulcC.first().bandNames().getInfo())

# Add the collection to the map
Map.addTimeLapse(lulcC, {"canAreaChart": True, "autoViz": True, "years": years, "areaChartParams": {"line": True, "sankey": True, "crs": crs, "transform": transform, "scale": scale}}, "MapBiomas LULC")
#Map.addLayer(lulcC, {"canAreaChart": True, "autoViz": True, "years": years, "areaChartParams": {"line": True, "sankey": False, "crs": crs, "transform": transform, "scale": scale}}, "MapBiomas LULC")

countries = ee.FeatureCollection("FAO/GAUL_SIMPLIFIED_500m/2015/level0")
Map.addSelectLayer(countries, {}, "Global Country Boundaries")
## Set up the map
Map.turnOnAutoAreaCharting()
Map.turnOffLayersWhenTimeLapseIsOn = False
# Map.turnOnInspector()
#Map.setCenter(-62.8, -3, 4)

Map.view()

