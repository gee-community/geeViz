"""
Copyright 2025 Ian Housman

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

# Module to help with LCMS levels remap crosswalk
# Also assists with collapsing levels

# Object with all levels, class number, color, and name
all_lookup = {
    "Land_Cover": {
        "1": [1, "61BB46", "Vegetated"],
        "2": [2, "58646E", "Non-Vegetated"],
        "3": [3, "1B1716", "Non-Processing Area Mask"],
        "1-1": [1, "004E2B", "Tree Vegetated"],
        "1-2": [2, "8DA463", "Non-Tree Vegetated"],
        "2-1": [3, "893F54", "Non-Vegetated"],
        "3-1": [4, "1B1716", "Non-Processing Area Mask"],
        "1-1-1": [1, "004E2B", "Tree"],
        "1-2-1": [2, "F89A1C", "Shrub"],
        "1-2-2": [3, "E5E98A", "Grass/Forb/Herb"],
        "2-1-1": [4, "893F54", "Barren or Impervious"],
        "2-1-2": [5, "E4F5FD", "Snow or Ice"],
        "2-1-3": [6, "00B6F0", "Water"],
        "3-1-1": [7, "1B1716", "Non-Processing Area Mask"],
        "1-1-1-1": [1, "004E2B", "Tree"],
        "1-1-1-2": [2, "009344", "Tall Shrub & Tree Mix (SEAK Only)"],
        "1-1-1-3": [3, "61BB46", "Shrub & Tree Mix"],
        "1-1-1-4": [4, "ACBB67", "Grass/Forb/Herb & Tree Mix"],
        "1-1-1-5": [5, "8B8560", "Barren & Tree Mix"],
        "1-2-1-1": [6, "CAFD4B", "Tall Shrub (SEAK Only)"],
        "1-2-1-2": [7, "F89A1C", "Shrub"],
        "1-2-1-3": [8, "8FA55F", "Grass/Forb/Herb & Shrub Mix"],
        "1-2-1-4": [9, "BEBB8E", "Barren & Shrub Mix"],
        "1-2-2-1": [10, "E5E98A", "Grass/Forb/Herb"],
        "1-2-2-2": [11, "DDB925", "Barren & Grass/Forb/Herb Mix"],
        "2-1-1-1": [12, "893F54", "Barren or Impervious"],
        "2-1-2-1": [13, "E4F5FD", "Snow or Ice"],
        "2-1-3-1": [14, "00B6F0", "Water"],
        "3-1-1-1": [15, "1B1716", "Non-Processing Area Mask"],
    },
    "Change": {
        "1": [1, "3D4551", "Stable"],
        "2": [2, "D54309", "Loss"],
        "3": [3, "1B1716", "Non-Processing Area Mask"],
        "1-1": [1, "3D4551", "Stable"],
        "1-2": [2, "00A398", "Gain"],
        "2-1": [3, "D54309", "Loss"],
        "3-1": [4, "1B1716", "Non-Processing Area Mask"],
        "1-1-1": [1, "3D4551", "Stable"],
        "1-2-1": [4, "00A398", "Gain"],
        "2-1-1": [2, "F39268", "Slow Loss"],
        "2-1-2": [3, "D54309", "Fast Loss"],
        "3-1-1": [5, "1B1716", "Non-Processing Area Mask"],
    },
    "Land_Use": {
        "1": [1, "FF9EAB", "Anthropogenic"],
        "2": [2, "004E2B", "Non-Anthropogenic"],
        "3": [3, "1B1716", "Non-Processing Area Mask"],
        "1-1": [1, "FBFF97", "Agriculture"],
        "1-2": [2, "E6558B", "Developed"],
        "2-1": [3, "004E2B", "Forest"],
        "2-2": [4, "D4D4D3", "Other"],
        "2-3": [5, "A6976A", "Rangeland or Pasture"],
        "3-1": [6, "1B1716", "Non-Processing Area Mask"],
        "1-1-1": [1, "FBFF97", "Agriculture"],
        "1-2-1": [2, "E6558B", "Developed"],
        "2-1-1": [3, "004E2B", "Forest"],
        "2-2-1": [4, "36C5B2", "Non-Forest Wetland"],
        "2-2-2": [5, "D4D4D3", "Other"],
        "2-3-1": [6, "A6976A", "Rangeland or Pasture"],
        "3-1-1": [7, "1B1716", "Non-Processing Area Mask"],
    },
}

all_lookup_2024_10 = {"Land_Cover": {
      "1": [1, "61BB46", "Vegetated"],
      "2": [2, "58646E", "Non-Vegetated"],
      "3": [3, "1B1716", "Non-Processing Area Mask"],
      "1-1": [1, "004E2B", "Tree Vegetated"],
      "1-2": [2, "8DA463", "Non-Tree Vegetated"],
      "2-1": [3, "893F54", "Non-Vegetated"],
      "3-1": [4, "1B1716", "Non-Processing Area Mask"],
      "1-1-1": [1, "004E2B", "Tree"],
      "1-2-1": [2, "F89A1C", "Shrub"],
      "1-2-2": [3, "E5E98A", "Grass/Forb/Herb"],
      "2-1-1": [4, "893F54", "Barren or Impervious"],
      "2-1-2": [5, "E4F5FD", "Snow or Ice"],
      "2-1-3": [6, "00B6F0", "Water"],
      "3-1-1": [7, "1B1716", "Non-Processing Area Mask"],
      "1-1-1-1": [1, "004E2B", "Tree"],
      "1-1-1-2": [2, "009344", "Tall Shrub & Tree Mix (AK Only)"],
      "1-1-1-3": [3, "61BB46", "Shrub & Tree Mix"],
      "1-1-1-4": [4, "ACBB67", "Grass/Forb/Herb & Tree Mix"],
      "1-1-1-5": [5, "8B8560", "Barren & Tree Mix"],
      "1-2-1-1": [6, "CAFD4B", "Tall Shrub (AK Only)"],
      "1-2-1-2": [7, "F89A1C", "Shrub"],
      "1-2-1-3": [8, "8FA55F", "Grass/Forb/Herb & Shrub Mix"],
      "1-2-1-4": [9, "BEBB8E", "Barren & Shrub Mix"],
      "1-2-2-1": [10, "E5E98A", "Grass/Forb/Herb"],
      "1-2-2-2": [11, "DDB925", "Barren & Grass/Forb/Herb Mix"],
      "2-1-1-1": [12, "893F54", "Barren or Impervious"],
      "2-1-2-1": [13, "E4F5FD", "Snow or Ice"],
      "2-1-3-1": [14, "00B6F0", "Water"],
      "3-1-1-1": [15, "1B1716", "Non-Processing Area Mask"],
    },
    "Change": {
      "1": [1, "D54309", "Disturbance"],
      "2": [2, "00A398", "Vegetation Successional Growth"],
      "3": [3, "3D4551", "Stable"],
      "4": [4, "1B1716", "Non-Processing Area Mask"],

      "1-1": [1, "FF09F3", "Wind"],
      "1-2": [2, "CC982E", "Desiccation"],
      "1-3": [3, "0ADAFF", "Inundation"],
      "1-4": [4, "D54309", "Fire"],
      "1-5": [5, "FAFA4B", "Mechanical Land Transformation"],
      "1-6": [6, "AFDE1C", "Tree Removal"],
      "1-7": [7, "F39268", "Insect, Disease, or Drought Stress"],
      "1-8": [8, "C291D5", "Other Loss"],
      "2-1": [9, "00A398", "Vegetation Successional Growth"],
      "3-1": [10, "3D4551", "Stable"],
      "4-1": [11, "1B1716", "Non-Processing Area Mask"],

      "1-1-1": [1, "FF09F3", "Wind"],
      "1-1-2": [2, "541AFF", "Hurricane"],
      "1-8-2": [3, "E4F5FD", "Snow or Ice Transition"],
      "1-2-1": [4, "CC982E", "Desiccation"],
      "1-3-1": [5, "0ADAFF", "Inundation"],
      "1-4-1": [6, "A10018", "Prescribed Fire"],
      "1-4-2": [7, "D54309", "Wildfire"],
      "1-5-1": [8, "FAFA4B", "Mechanical Land Transformation"],
      "1-6-1": [9, "AFDE1C", "Tree Removal"],
      "1-7-1": [10, "FFC80D", "Defoliation"],
      "1-7-2": [11, "A64C28", "Southern Pine Beetle"],
      "1-7-3": [12, "F39268", "Insect, Disease, or Drought Stress"],
      "1-8-1": [13, "C291D5", "Other Loss"],
      "2-1-1": [14, "00A398", "Vegetation Successional Growth"],
      "3-1-1": [15, "3D4551", "Stable"],
      "4-1-1": [16, "1B1716", "Non-Processing Area Mask"],
    },

    "Land_Use": {
      "1": [1, "FF9EAB", "Anthropogenic"],
      "2": [2, "004E2B", "Non-Anthropogenic"],
      "3": [3, "1B1716", "Non-Processing Area Mask"],
      "1-1": [1, "FBFF97", "Agriculture"],
      "1-2": [2, "E6558B", "Developed"],
      "2-1": [3, "004E2B", "Forest"],
      "2-2": [4, "9DBAC5", "Other"],
      "2-3": [5, "A6976A", "Rangeland or Pasture"],
      "3-1": [6, "1B1716", "Non-Processing Area Mask"],
    }
}

# Get a lookup of MapBiomas names, values, and palette to set as properties for a given band
def getLookup(bandName, codes=all_lookup.keys(), lookup=all_lookup):
    return {
        f"{bandName}_class_names": [f"{lookup[bandName][c][2]}" for c in codes],
        f"{bandName}_class_palette": [lookup[bandName][c][1] for c in codes],
        f"{bandName}_class_values": [lookup[bandName][c][0] for c in codes],
    }


# Method to collapse to a given level (1-4), and return the remap values as well as corresponding visualization properties
def getLevelNRemap(level, bandName="Land_Cover",lookup=all_lookup):
    names = lookup[bandName].keys()
    level_below = [n for n in names if len(n.split("-")) <= level]
    level_above = [n for n in names if len(n.split("-")) > level]
    the_level = [n for n in names if len(n.split("-")) == level]

    out_remap_below = {lookup[bandName][code][0]: lookup[bandName][code][0] for code in level_below}
    out_remap_above = {lookup[bandName][code][0]: lookup[bandName]["-".join(code.split("-")[:level])][0] for code in level_above}
    out_remap_below.update(out_remap_above)
    out_remap = out_remap_below

    out_lookup = getLookup(bandName, the_level,lookup)
    return {"remap_from": list(out_remap.keys()), "remap_to": list(out_remap.values()), "viz_dict": out_lookup}


# Specify levels to show
product_levels = {"Change": [3, 2, 1], "Land_Cover": [4, 3, 2, 1], "Land_Use": [3, 2, 1]}
product_levels_2024_10 = {"Change": [3, 2, 1], "Land_Cover": [4, 3, 2, 1], "Land_Use": [ 2, 1]}

if __name__ == "__main__":
    print(getLevelNRemap(2, "Change",all_lookup_2024_10))
    print(getLevelNRemap(1, "Change",all_lookup_2024_10))
