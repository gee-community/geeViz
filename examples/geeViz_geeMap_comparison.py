# %% [markdown]
# # A comparison between geeViz and geeMap's map visualization capabilities
#
# * Both packages provide methods to visualize and summarize EE objects as well as non-EE-based image services
# * geeViz uses the localhost in a web server. It will run in notbooks, iPython, or a regular script
# * geeMap uses iPython widgets, and therefore needs to run from a notebook or iPython
# * geeViz uses geeMap when appropriate, but still relies on its own map visualization tool for a variety of reasons
#
# * This is intended to illustrate the basic map functionality of each package. Refer to each packages examples for more in-depth demos

# %%
import ee

import geeViz.geeView as gv
import geemap as gm



gvMap = gv.Map
gmMap = gm.Map()


# %% [markdown]
# ### First, we'll take a look at the two different map interfaces
#

# %%
# geeMap you simply call the object
gmMap

# %%
# geeViz you use the view method
gvMap.view()

# %% [markdown]
# # Some methods are similar between the methods available
#
# * addLayer
# * setCenter
# * centerObject

# %%
gmMap = gm.Map()

pt = ee.Geometry.Point([-111.92926447956665, 40.64356771453405])

gmMap.centerObject(pt, 10)
gvMap.centerObject(pt, 10)

gvMap.view()
gmMap

# %%
gmMap = gm.Map()


gmMap.setCenter(-111.92926447956665, 40.64356771453405, 10)
gvMap.setCenter(-111.92926447956665, 40.64356771453405, 10)

gvMap.view()
gmMap

# %% [markdown]
# * Adding layers is very similar
#     * geeMap makes the top layer on the map the bottom layer in the layer UI list, while geeViz they appear in the same order as on the map (you can reorder most map layers in geeViz with a drag and drop to reorder)

# %%
gmMap = gm.Map()

# Add Earth Engine dataset
dem = ee.Image("USGS/SRTMGL1_003")
landcover = ee.Image("ESA/GLOBCOVER_L4_200901_200912_V2_3").select("landcover")
landsat7 = ee.Image("LANDSAT/LE7_TOA_5YEAR/1999_2003").select(
    ["B1", "B2", "B3", "B4", "B5", "B7"]
)
states = ee.FeatureCollection("TIGER/2018/States")

# Set visualization parameters.
vis_params = {
    "min": 0,
    "max": 4000,
    "palette": ["006633", "E5FFCC", "662A00", "D8D8D8", "F5F5F5"],
}

# Add Earth Engine layers to Map
gmMap.addLayer(dem, vis_params, "SRTM DEM", True)
gmMap.addLayer(landcover, {}, "Land cover")
gmMap.addLayer(
    landsat7,
    {"bands": ["B4", "B3", "B2"], "min": 20, "max": 200, "gamma": 2.0},
    "Landsat 7",
)
gmMap.addLayer(states, {}, "US States")


gvMap.clearMap()


gvMap.addLayer(dem, vis_params, "SRTM DEM", True)
gvMap.addLayer(landcover, {}, "Land cover")
gvMap.addLayer(
    landsat7,
    {"bands": ["B4", "B3", "B2"], "min": 20, "max": 200, "gamma": 2.0},
    "Landsat 7",
)
gvMap.addLayer(states, {}, "US States")

gmMap.setCenter(-111.92926447956665, 40.64356771453405, 10)
gvMap.setCenter(-111.92926447956665, 40.64356771453405, 10)

gvMap.view()
gmMap

# %% [markdown]
# * geeMap and geeViz provide different methods creating legends
#
# * geeViz will try to populate a legend with any single-band image or imageCollection its given
#
# * If an image or imageCollection has images with _class_name, _class_value, _class_palette properties, you can use `"autoViz":True` to populate a legend
#
# * geeMap provides methods to create legends

# %%
gmMap = gm.Map()
gvMap.clearMap()

legend_dict = {
    "11 Open Water": "466b9f",
    "12 Perennial Ice/Snow": "d1def8",
    "21 Developed, Open Space": "dec5c5",
    "22 Developed, Low Intensity": "d99282",
    "23 Developed, Medium Intensity": "eb0000",
    "24 Developed High Intensity": "ab0000",
    "31 Barren Land (Rock/Sand/Clay)": "b3ac9f",
    "41 Deciduous Forest": "68ab5f",
    "42 Evergreen Forest": "1c5f2c",
    "43 Mixed Forest": "b5c58f",
    "51 Dwarf Scrub": "af963c",
    "52 Shrub/Scrub": "ccb879",
    "71 Grassland/Herbaceous": "dfdfc2",
    "72 Sedge/Herbaceous": "d1d182",
    "73 Lichens": "a3cc51",
    "74 Moss": "82ba9e",
    "81 Pasture/Hay": "dcd939",
    "82 Cultivated Crops": "ab6c28",
    "90 Woody Wetlands": "b8d9eb",
    "95 Emergent Herbaceous Wetlands": "6c9fb8",
}

landcover = ee.Image("USGS/NLCD/NLCD2016").select("landcover")
gmMap.addLayer(landcover, {}, "NLCD Land Cover")

gmMap.add_legend(legend_title="NLCD Land Cover", legend_dict=legend_dict)


gvMap.addLayer(landcover, {"classLegendDict": legend_dict}, "NLCD Land Cover")

gvMap.view()
gmMap

# %%
gmMap = gm.Map()
gvMap.clearMap()

ee_class_table = """

Value	Color	Description
0	1c0dff	Water
1	05450a	Evergreen needleleaf forest
2	086a10	Evergreen broadleaf forest
3	54a708	Deciduous needleleaf forest
4	78d203	Deciduous broadleaf forest
5	009900	Mixed forest
6	c6b044	Closed shrublands
7	dcd159	Open shrublands
8	dade48	Woody savannas
9	fbff13	Savannas
10	b6ff05	Grasslands
11	27ff87	Permanent wetlands
12	c24f44	Croplands
13	a5a5a5	Urban and built-up
14	ff6d4c	Cropland/natural vegetation mosaic
15	69fff8	Snow and ice
16	f9ffa4	Barren or sparsely vegetated
254	ffffff	Unclassified

"""

landcover = ee.Image("MODIS/051/MCD12Q1/2013_01_01").select("Land_Cover_Type_1")

proj = landcover.projection().getInfo()
gmMap.setCenter(6.746, 46.529, 2)
gmMap.addLayer(landcover, {}, "MODIS Land Cover")

legend_dict = gm.legend_from_ee(ee_class_table)
gmMap.add_legend(legend_title="MODIS Global Land Cover", legend_dict=legend_dict)

gvMap.setCenter(6.746, 46.529, 2)
gvMap.addLayer(
    landcover,
    {
        "autoViz": True,
        "canAreaChart": True,
        "areaChartParams": {
            "crs": proj["crs"],
            "transform": proj["transform"],
            "minZoomSpecifiedScale": 5,
        },
    },
    "MODIS Land Cover",
)

gvMap.turnOnAutoAreaCharting()
gvMap.view()
gmMap

# %% [markdown]
# # Using geeMap and geeViz together
#
# * Currently, geeViz is integrating the broad functionality of geeMap where appropriate.
# * We feel that many of the conversion functions and data extraction functions work well in a regular Python script, as well as in notebooks in iPython, so we can use them in geeViz as they are
# * As such, geeViz is building dependencies on geeMap

# %%
shp = "data/gadm41_CHE_shp/gadm41_CHE_0.shp"

ch = gm.shp_to_ee(shp)

gmMap = gm.Map()
gvMap.clearMap()

gvMap.addLayer(ch, {}, "Switzerland")
gmMap.addLayer(ch, {}, "Switzerland")

gmMap.centerObject(ch)
gvMap.centerObject(ch)
gvMap.view()
gmMap

# %%
