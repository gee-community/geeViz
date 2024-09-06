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

# Module to help with the many MapBiomas classes/colors/codes
# Also assists with collapsing levels
# Adapted from various scripts in https://gee-community-catalog.org/projects/mapbiomas/
####################################################################################################
mapBiomasLookup = [
    [1, "1f8d49", "1", "Forest"],
    [3, "1f8d49", "1.1", "Forest Formation"],
    [4, "7dc975", "1.2", "Savanna Formation"],
    [5, "04381d", "1.3", "Mangrove"],
    [6, "007785", "1.4", "Floodable Forest"],
    [49, "02d659", "1.5", "Wooded Sandbank Vegetation"],
    [45, "807a40", "1.6", "Sparse Woodland"],
    [10, "d6bc74", "2", "Non Forest Formations"],
    [11, "519799", "2.1", "Wetland"],
    [12, "d6bc74", "2.2", "Grassland"],
    [42, "a5b35b", "2.1.1", "Open Grassland"],
    [43, "c2d26b", "2.1.2", "Closed Grassland"],
    [44, "cbe286", "2.1.3", "Sparse Grassland"],
    [32, "fc8114", "2.3", "Hypersaline Tidal Flat"],
    [29, "ffaa5f", "2.4", "Rocky Outcrop"],
    [50, "ad5100", "2.5", "Herbaceous Sandbank Vegetation"],
    [13, "d89f5c", "2.6", "Other Non Forest Formations"],
    [66, "a89358", "2.7", "Shrubland"],
    [63, "ebf8b5", "2.8", "Steppe"],
    [14, "ffefc3", "3", "Farming"],
    [15, "edde8e", "3.1", "Pasture"],
    [18, "E974ED", "3.2", "Agriculture"],
    [19, "C27BA0", "3.2.1", "Temporary Crop"],
    [39, "f5b3c8", "3.2.1.1", "Soybean"],
    [20, "db7093", "3.2.1.2", "Sugar cane"],
    [40, "c71585", "3.2.1.3", "Rice"],
    [62, "ff69b4", "3.2.1.4", "Cotton (beta)"],
    [41, "f54ca9", "3.2.1.5", "Other Temporary Crops"],
    [57, "f99fff", "3.2.1.6", "Single Crop"],
    [58, "d84690", "3.2.1.7", "Multiple Crops"],
    [36, "d082de", "3.2.2", "Perennial Crop"],
    [46, "d68fe2", "3.2.2.1", "Coffee"],
    [47, "9932cc", "3.2.2.2", "Citrus"],
    [35, "9065d0", "3.2.2.3", "Palm Oil (beta)"],
    [65, "b9158a", "3.2.2.5", "Tea"],
    [48, "e6ccff", "3.2.2.4", "Other Perennial Crops"],
    [9, "7a5900", "3.3", "Forest Plantation"],
    [21, "ffefc3", "3.4", "Mosaic of Uses"],
    [22, "d4271e", "4", "Non vegetated area"],
    [23, "ffa07a", "4.1", "Beach, Dune and Sand Spot"],
    [24, "d4271e", "4.2", "Urban Area"],
    [30, "9c0027", "4.3", "Mining"],
    [25, "db4d4f", "4.4", "Other non Vegetated Areas"],
    [61, "f5d5d5", "4.5", "Salt Flat"],
    [26, "2532e4", "5", "Water"],
    [33, "2532e4", "5.1", "River, Lake and Ocean"],
    [31, "091077", "5.2", "Aquaculture"],
    [34, "93dfe6", "5.3", "Glacier"],
    [27, "ffffff", "6", "Not Observed"],
]

all_lookup = {i[2]: [i[0], i[1], i[3]] for i in mapBiomasLookup}


# Get a lookup of MapBiomas names, values, and palette to set as properties for a given band
def getLookup(bandName, codes=all_lookup.keys()):
    return {
        f"{bandName}_class_names": [f"{c} - {all_lookup[c][2]}" for c in codes],
        f"{bandName}_class_palette": [all_lookup[c][1] for c in codes],
        f"{bandName}_class_values": [all_lookup[c][0] for c in codes],
    }


# Method to collapse to a given level (1-4), and return the remap values as well as corresponding visualization properties
def getLevelNRemap(level, bandName="lulc"):
    names = all_lookup.keys()
    level_below = [n for n in names if len(n.split(".")) <= level]
    level_above = [n for n in names if len(n.split(".")) > level]
    out_remap_below = {all_lookup[code][0]: all_lookup[code][0] for code in level_below}
    out_remap_above = {all_lookup[code][0]: all_lookup[".".join(code.split(".")[:level])][0] for code in level_above}
    out_remap_below.update(out_remap_above)
    out_remap = out_remap_below

    out_lookup = getLookup(bandName, level_below)
    return {"remap_from": list(out_remap.keys()), "remap_to": list(out_remap.values()), "viz_dict": out_lookup}
