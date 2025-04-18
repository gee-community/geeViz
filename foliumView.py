"""
View GEE objects using Folium.

geeViz.foliumView facilitates viewing GEE objects in Folium. Layers can be added to the map using `Map.addLayer` and then viewed using the `Map.view` method.

Example:
    from geeViz.foliumView import foliumMapper

    # Initialize the mapper
    mapper = foliumMapper()

    # Set the map center
    mapper.setCenter(-122.4194, 37.7749, 10)

    # Add a layer (example assumes you have an ee.Image object)
    mapper.addLayer(ee.Image("LANDSAT/LC08/C01/T1_SR/LC08_044034_20140318"), 
                    {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}, 
                    "Landsat Image")

    # View the map
    mapper.view()
"""

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
# Script to allow GEE objects to be viewed in folium
# Adapted from: https://colab.research.google.com/github/giswqs/qgis-earthengine-examples/blob/master/Folium/ee-api-folium-setup.ipynb
# Intended to work within the geeViz package
######################################################################
# Import modules
import geeViz.geeView as geeView
import os, sys, folium, json, numpy
from folium import plugins
from IPython.display import display, HTML

# Set up GEE and paths
ee = geeView.ee
######################################################################
# Specify location of files to run
folium_html = "foliumView.html"
folium_html_folder = os.path.join(geeView.py_viz_dir, geeView.geeViewFolder)
######################################################################
# Add custom basemaps to folium
basemaps = {
    "Google Maps": folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Maps",
        overlay=True,
        control=True,
    ),
    "Google Satellite": folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite",
        overlay=True,
        control=True,
    ),
    "Google Terrain": folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Terrain",
        overlay=True,
        control=True,
    ),
    "Google Satellite Hybrid": folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite",
        overlay=True,
        control=True,
    ),
    "Esri Satellite": folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Esri Satellite",
        overlay=True,
        control=True,
    ),
}


######################################################################
# Define a method for displaying Earth Engine image tiles on a folium map.
def add_ee_layer(self, ee_object, vis_params, name, visible):
    """
    Adds an Earth Engine object as a layer to a Folium map.

    Args:
        ee_object (ee.Image | ee.ImageCollection | ee.FeatureCollection | ee.Feature | ee.Geometry): 
            The Earth Engine object to add.
        vis_params (dict): Visualization parameters for the layer.
        name (str): Name of the layer.
        visible (bool): Whether the layer is visible by default.

    Example:
        >>> map = folium.Map(location=[37.7749, -122.4194], zoom_start=10)
        >>> map.add_ee_layer(ee.Image("LANDSAT/LC08/C01/T1_SR/LC08_044034_20140318"), 
        ...                  {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}, 
        ...                  "Landsat Image", True)
    """
    try:

        if isinstance(ee_object, ee.image.Image):
            map_id_dict = ee.Image(ee_object).getMapId(vis_params)
            folium.raster_layers.TileLayer(
                tiles=map_id_dict["tile_fetcher"].url_format,
                attr="Google Earth Engine | GeeViz",
                name=name,
                overlay=True,
                control=True,
                show=visible,
            ).add_to(self)
        # display ee.ImageCollection()
        elif isinstance(ee_object, ee.imagecollection.ImageCollection):
            ee_object_new = ee_object.mosaic()
            map_id_dict = ee.Image(ee_object_new).getMapId(vis_params)
            folium.raster_layers.TileLayer(
                tiles=map_id_dict["tile_fetcher"].url_format,
                attr="Google Earth Engine",
                name=name,
                overlay=True,
                control=True,
                show=visible,
            ).add_to(self)
        # display ee.Geometry()
        # elif isinstance(ee_object, ee.geometry.Geometry):
        #     folium.GeoJson(
        #     data = ee_object.getInfo(),
        #     name = name,
        #     overlay = True,
        #     control = True,
        #     show = visible
        # ).add_to(self)
        # display ee.FeatureCollection()
        elif isinstance(ee_object, ee.featurecollection.FeatureCollection) or isinstance(ee_object, ee.feature.Feature) or isinstance(ee_object, ee.geometry.Geometry):
            strokeWidth = 2
            strokeColor = "000"
            if "strokeWidth" in vis_params.keys():
                strokeWidth = vis_params["strokeWidth"]
            if "strokeColor" in vis_params.keys():
                strokeColor = vis_params["strokeColor"]
            vis_params["palette"] = strokeColor
            ee_object_new = ee.Image().paint(ee_object, 0, strokeWidth)
            map_id_dict = ee.Image(ee_object_new).getMapId(vis_params)
            folium.raster_layers.TileLayer(
                tiles=map_id_dict["tile_fetcher"].url_format,
                attr="Google Earth Engine",
                name=name,
                overlay=True,
                control=True,
                show=visible,
            ).add_to(self)

    except Exception as e:
        print("Could not display {}".format(name))
        print("Error:", e)


folium.Map.add_ee_layer = add_ee_layer


######################################################################
# Set up map object
# Intended to be similar to geeView mapper object
class foliumMapper:
    """
    A class for managing and visualizing Earth Engine objects using Folium.

    Example:
        >>> mapper = foliumMapper()
        >>> mapper.setCenter(-122.4194, 37.7749, 10)
        >>> mapper.addLayer(ee.Image("LANDSAT/LC08/C01/T1_SR/LC08_044034_20140318"),
        ...                 {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000},
        ...                 "Landsat Image")
        >>> mapper.view()
    """
    def __init__(self, port=8001):
        """
        Initializes the foliumMapper.

        Args:
            port (int): The port for the local web server. Default is 8001.

        Example:
            >>> mapper = foliumMapper(port=8001)
        """
        self.port = port
        self.isNotebook = geeView.is_notebook()
        self.mapArgs = {}
        self.idDictList = []
        self.layerNumber = 1
        self.mapBounds = None

    def clearMap(self):
        """
        Clears all layers and resets the map state.

        Example:
            >>> mapper.clearMap()
        """
        self.layerNumber = 1
        self.idDictList = []
        self.mapBounds = None

    def setMapArg(self, key, value):
        """
        Sets a map argument.

        Args:
            key (str): The argument key.
            value: The argument value.

        Example:
            >>> mapper.setMapArg("zoom_start", 10)
        """
        self.mapArgs[key] = value

    def turnOnInspector(self):
        """
        Prints a message indicating that only GEE map objects are supported.

        Example:
            >>> mapper.turnOnInspector()
        """
        print("Folium Viewer currently only supports viewing of GEE map objects")

    def setCenter(self, lon, lat, zoom=None):
        """
        Sets the center of the map.

        Args:
            lon (float): Longitude of the center.
            lat (float): Latitude of the center.
            zoom (int, optional): Zoom level. Default is None.

        Example:
            >>> mapper.setCenter(-122.4194, 37.7749, 10)
        """
        self.setMapArg("location", [lat, lon])
        if zoom != None:
            self.setMapArg("zoom_start", zoom)

    def centerObject(self, ee_object):
        """
        Centers the map on an Earth Engine object.

        Args:
            ee_object (ee.FeatureCollection | ee.Feature | ee.Geometry): The object to center on.

        Example:
            >>> mapper.centerObject(ee.FeatureCollection("FAO/GAUL/2015/level1"))
        """
        if isinstance(ee_object, ee.featurecollection.FeatureCollection) or isinstance(ee_object, ee.feature.Feature):
            ee_object = ee_object.geometry()
        bounds = ee_object.bounds(500, "EPSG:4326").coordinates().getInfo()[0]
        xs = [i[0] for i in bounds]
        ys = [i[1] for i in bounds]
        self.mapBounds = [
            [numpy.min(ys), numpy.min(xs)],
            [numpy.max(ys), numpy.max(xs)],
        ]

    def addLayer(self, eeObject, viz={}, name=None, visible=True):
        """
        Adds a layer to the map.

        Args:
            eeObject: The Earth Engine object to add.
            viz (dict): Visualization parameters.
            name (str, optional): Name of the layer. Default is None.
            visible (bool): Whether the layer is visible by default.

        Example:
            >>> mapper.addLayer(ee.Image("LANDSAT/LC08/C01/T1_SR/LC08_044034_20140318"),
            ...                {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000},
            ...                "Landsat Image")
        """
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding layer: " + name)
        # Get the id and populate dictionary
        idDict = {}  # image.getMapId()
        idDict["item"] = eeObject
        idDict["name"] = name
        idDict["visible"] = visible
        idDict["viz"] = viz

        self.idDictList.append(idDict)

    def turnOffAllLayers(self):
        """
        Turns off visibility for all layers.

        Example:
            >>> mapper.turnOffAllLayers()
        """
        update = {"visible": False}
        self.idDictList = [{**d, **update} for d in self.idDictList]

    def turnOnAllLayers(self):
        """
        Turns on visibility for all layers.

        Example:
            >>> mapper.turnOnAllLayers()
        """
        update = {"visible": True}
        self.idDictList = [{**d, **update} for d in self.idDictList]

    def view(self, open_browser=True, open_iframe=False, iframe_height=525):
        """
        Displays the map.

        Args:
            open_browser (bool): Whether to open the map in a browser. Default is True.
            open_iframe (bool): Whether to display the map in an iframe. Default is False.
            iframe_height (int): Height of the iframe. Default is 525.

        Example:
            >>> mapper.view()
        """
        self.Map = folium.Map(**self.mapArgs)
        # Add custom basemaps
        if self.mapBounds != None:
            self.Map.fit_bounds(self.mapBounds)

        basemaps["Google Maps"].add_to(self.Map)
        basemaps["Google Satellite Hybrid"].add_to(self.Map)

        for idDict in self.idDictList:
            self.Map.add_ee_layer(idDict["item"], idDict["viz"], idDict["name"], idDict["visible"])

        self.Map.add_child(folium.LayerControl(collapsed=False, autoZIndex=False))

        # Add fullscreen button
        plugins.Fullscreen().add_to(self.Map)

        if not self.isNotebook:
            self.Map.save(os.path.join(folium_html_folder, folium_html))
            if not geeView.isPortActive(self.port):
                print("Starting local web server at: http://localhost:{}/{}/".format(self.port, geeView.geeViewFolder))
                geeView.run_local_server(self.port)
                print("Done")
            else:
                print("Local web server at: http://localhost:{}/{}/ already serving.".format(self.port, geeView.geeViewFolder))
            if open_browser:
                geeView.webbrowser.open(
                    "http://localhost:{}/{}/{}".format(self.port, geeView.geeViewFolder, folium_html),
                    new=1,
                )

        else:
            display(self.Map)
