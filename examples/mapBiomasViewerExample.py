"""
   Copyright 2024 Ian Housman

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

# An example of using geeViz to explore mapBiomas Collection 8 outputs
# Adapted from various scripts in https://gee-community-catalog.org/projects/mapbiomas/
####################################################################################################
import os, sys

sys.path.append(os.getcwd())

# Module imports
import geeViz.geeView as gv

ee = gv.ee
Map = gv.Map
Map.clearMap()
####################################################################################################
# Datasets available here: https://gee-community-catalog.org/projects/mapbiomas/

# Specify which years all datasets have
years = list(range(1985, 2021 + 1))
common_bandNames = [f"classification_{yr}" for yr in years]

# Bring in land use land cover datasets and mosaic them
paths = [
    "projects/mapbiomas-public/assets/bolivia/collection1/mapbiomas_bolivia_collection1_integration_v1",
    "projects/mapbiomas-public/assets/peru/collection1/mapbiomas_peru_collection1_integration_v1",
    "projects/mapbiomas-public/assets/colombia/collection1/mapbiomas_colombia_collection1_integration_v1",
    "projects/mapbiomas-public/assets/ecuador/collection1/mapbiomas_ecuador_collection1_integration_v1",
    "projects/mapbiomas-public/assets/venezuela/collection1/mapbiomas_venezuela_collection1_integration_v1",
    "projects/mapbiomas-public/assets/paraguay/collection1/mapbiomas_paraguay_collection1_integration_v1",
    "projects/mapbiomas-workspace/public/collection8/mapbiomas_collection80_integration_v1",
    "projects/mapbiomas-raisg/public/collection5/mapbiomas_raisg_panamazonia_collection5_integration_v1",
    "projects/MapBiomas_Pampa/public/collection3/mapbiomas_uruguay_collection1_integration_v1",
]


lulcImg = []
for path in paths:
    lulcImg.append(ee.Image(path).select(common_bandNames).byte())

lulcImg = ee.ImageCollection(lulcImg).mosaic()

# Bring in the names, values, and palette
names = [
    "6. Not Observed",
    "1.1. Forest Formation",
    "1.2. Savanna Formation",
    "1.3. Mangrove",
    "1.5. Floodable Forest",
    "3.3. Forest Plantation",
    "2.1. Wetland",
    "2.2. Grassland",
    "2.6. Other Non Forest Formations",
    "3.1 Pasture",
    "(mesma cor de 39)",
    "3.2.1.2. Sugar cane",
    "3.4. Mosaic of Uses",
    "(mesma cor de 25)",
    "4.1. Beach, Dune and Sand Spot",
    "4.2. Urban Area",
    "4.4. Other non Vegetated Areas",
    "2.4. Rocky Outcrop",
    "4.3. Mining",
    "5.2. Aquaculture",
    "2.3. Hypersaline Tidal Flat",
    "5.1. River, Lake and Ocean",
    "x.x. Glacier",
    "3.2.1.1. Soybean",
    "3.2.1.3. Rice",
    "3.2.1.5. Other Temporary Crops",
    "3.2.2.1. Pastizal abierto",
    "3.2.2.1. Pastizal cerrado",
    "3.2.2.1. Pastizal disperso ",
    "3.2.2.1. Outros",
    "3.2.2.1. Coffee",
    "3.2.2.2. Citrus",
    "3.2.2.4. Other Perennial Crops",
    "1.4. Wooded Sandbank Vegetation",
    "2.5. Herbaceous Sandbank Vegetation",
    "0.0.0.0. Área urbana (definir cores)",
    "0.0.0.0. Infraestrutura (definir cores)",
    "0.0.0.0. Outras Áreas Urbanizadas (definir cores)",
    "0.0.0.0. Reservatórios (UHE e Abastecimento) (definir cores)",
    "0.0.0.0. Lagos artificiais e Açudes (definir cores)",
    "0.0.0.0. Outros corpos d agua artificiais (definir cores)",
    "0.0.0.0. Cultivo Simple (color temp)",
    "0.0.0.0. Cultivo Múltiple (color temp)",
    "0.0.0.0. Salares",
    "3.2.1.4. Cotton",
]
values = [
    0,
    3,
    4,
    5,
    6,
    9,
    11,
    12,
    13,
    15,
    18,
    20,
    21,
    22,
    23,
    24,
    25,
    29,
    30,
    31,
    32,
    33,
    34,
    39,
    40,
    41,
    42,
    43,
    44,
    45,
    46,
    47,
    48,
    49,
    50,
    51,
    52,
    53,
    54,
    55,
    56,
    57,
    58,
    61,
    62,
]
palette = [
    "ffffff",
    "1f8d49",
    "7dc975",
    "04381d",
    "026975",
    "7a6c00",
    "519799",
    "d6bc74",
    "d89f5c",
    "edde8e",
    "f5b3c8",
    "db7093",
    "ffefc3",
    "db4d4f",
    "ffa07a",
    "d4271e",
    "db4d4f",
    "ffaa5f",
    "9c0027",
    "091077",
    "fc8114",
    "2532e4",
    "93dfe6",
    "f5b3c8",
    "c71585",
    "f54ca9",
    "cca0d4",
    "dbd26b",
    "807a40",
    "e04cfa",
    "d68fe2",
    "9932cc",
    "e6ccff",
    "02d659",
    "ad5100",
    "000000",
    "000000",
    "000000",
    "000000",
    "000000",
    "000000",
    "CC66FF",
    "FF6666",
    "f5d5d5",
    "ff69b4",
]

# View palettes source here:
# var palettes = require('users/mapbiomas/modules:Palettes.js');

# Convert image to image collection
bns = lulcImg.bandNames()

out_band_name = "lulc"


# Function to convert a given band into a time-enabled image object
def setupLulc(bn):
    bn = ee.String(bn)
    yr = ee.Number.parse(ee.String(bn).split("_").get(1))
    img = (
        lulcImg.select(bn)
        .rename([out_band_name])
        .set("system:time_start", ee.Date.fromYMD(yr, 6, 1).millis())
    )
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


# Add the collection to the map
Map.addTimeLapse(
    lulcC,
    {"canAreaChart": True, "autoViz": True, "years": years},
    "MapBiomas LULC",
)


# Set up the map
Map.turnOnAutoAreaCharting()
# Map.turnOnInspector()
Map.setCenter(-62.8, -3, 6)
Map.view()
