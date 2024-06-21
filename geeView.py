"""
View GEE objects using Python

geeViz.geeView is the core module for managing GEE objects on the geeViz mapper object. geeViz instantiates an instance of the `mapper` class as `Map` by default. Layers can be added to the map using `Map.addLayer` or `Map.addTimeLapse` and then viewed using the `Map.view` method. 

"""

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

# Script to allow GEE objects to be viewed in a web viewer
# Intended to work within the geeViz package
######################################################################
# Import modules
import ee, sys, os, webbrowser, json, socket, subprocess, site, time, requests, google
from google.auth.transport import requests as gReq
from google.oauth2 import service_account

from threading import Thread
from urllib.parse import urlparse
from IPython.display import IFrame, display, HTML

if sys.version_info[0] < 3:
    import SimpleHTTPServer, SocketServer
else:
    import http.server, socketserver
creds_path = ee.oauth.get_credentials_path()
creds_dir = os.path.dirname(creds_path)
if not os.path.exists(creds_dir):
    os.makedirs(creds_dir)

IS_COLAB = ee.oauth.in_colab_shell()  # "google.colab" in sys.modules
IS_WORKBENCH = os.getenv("DL_ANACONDA_HOME") != None
if IS_COLAB:
    from google.colab.output import eval_js

######################################################################
# Functions to handle various initialization/authentication workflows to try to get a user an initialized instance of ee


# Function to have user input a project id if one is still needed
def setProject(id):
    global project_id
    project_id = id
    ee.data.setCloudApiUserProject(project_id)


def getProject(overwrite=False):
    """
    Tries to find the current Google Cloud Platform project id

    Args:
        overwrite (bool, optional): Whether or not to overwrite a cached project ID file

    Returns:
        str: The currently selected Google Cloud Platform project id
    """
    global project_id
    provided_project = "{}.proj_id".format(creds_path)
    provided_project = os.path.normpath(provided_project)

    current_project = ee.data._cloud_api_user_project

    if (current_project == None and not os.path.exists(provided_project)) or overwrite:

        project_id = input("Please enter GEE project ID: ")

        print("You entered: {}".format(project_id))
        o = open(provided_project, "w")
        o.write(project_id)
        o.close()

    if current_project != None:
        project_id = current_project
    elif os.path.exists(provided_project):
        o = open(provided_project, "r")
        project_id = o.read()
        print("Cached project id file path: {}".format(provided_project))
        print("Cached project id: {}".format(project_id))
        o.close()
    ee.data.setCloudApiUserProject(project_id)

    return project_id


######################################################################
def verified_initialize(project=None):
    ee.Initialize(project=project)
    z = ee.Number(1).getInfo()
    print("Successfully initialized")


# Function to handle various exceptions to initializing to GEE
def robustInitializer():
    global project_id

    try:
        z = ee.Number(1).getInfo()
    except:
        print("Initializing GEE")
        if not ee.oauth._valid_credentials_exist():
            ee.Authenticate()
        try:
            verified_initialize(project=ee.data._cloud_api_user_project)
        except Exception as E:
            # print(E)
            if str(E).find("Reauthentication is needed") > -1:
                ee.Authenticate(force=True)

            if (
                str(E).find("no project found. Call with project")
                or str(E).find("project is not registered") > -1
                or str(E).find(" quota project, which is not set by default") > -1
            ):
                project_id = getProject()

            else:
                project_id = None
            try:
                verified_initialize(project=project_id)
            except Exception as E:
                print(E)
                try:
                    project_id = getProject(overwrite=True)
                    verified_initialize(project=project_id)
                except Exception as E:
                    print(E)

        ee.data.setCloudApiUserProject(project_id)


setProject(ee.data._cloud_api_user_project)
robustInitializer()
######################################################################
# Set up GEE and paths
# robustInitializer()
geeVizFolder = "geeViz"
geeViewFolder = "geeView"
# Set up template web viewer
# Do not change
cwd = os.getcwd()

paths = sys.path

# gee_py_modules_dir = site.getsitepackages()[-1]
# py_viz_dir = os.path.join(gee_py_modules_dir,geeVizFolder)
py_viz_dir = os.path.dirname(__file__)
# os.chdir(py_viz_dir)
print("geeViz package folder:", py_viz_dir)

# Specify location of files to run
template = os.path.join(py_viz_dir, geeViewFolder, "index.html")
ee_run_dir = os.path.join(py_viz_dir, geeViewFolder, "src/gee/gee-run/")
if os.path.exists(ee_run_dir) == False:
    os.makedirs(ee_run_dir)


######################################################################
######################################################################
# Functions


######################################################################
# Linear color gradient functions
##############################################################
##############################################################
def color_dict_maker(gradient):
    """Takes in a list of RGB sub-lists and returns dictionary of
    colors in RGB and hex form for use in a graphing function
    defined later on"""
    return {
        "hex": [RGB_to_hex(RGB) for RGB in gradient],
        "r": [RGB[0] for RGB in gradient],
        "g": [RGB[1] for RGB in gradient],
        "b": [RGB[2] for RGB in gradient],
    }


# color functions adapted from bsou.io/posts/color-gradients-with-python
def hex_to_rgb(value):
    """Return (red, green, blue) for the color given as #rrggbb."""
    value = value.lstrip("#")
    lv = len(value)
    if lv == 3:
        lv = 6
        value = f"{value[0]}{value[0]}{value[1]}{value[1]}{value[2]}{value[2]}"

    return tuple(int(value[i : i + lv // 3], 16) for i in range(0, lv, lv // 3))


def RGB_to_hex(RGB):
    """[255,255,255] -> "#FFFFFF" """
    # Components need to be integers for hex to make sense
    RGB = [int(x) for x in RGB]
    return "#" + "".join(
        ["0{0:x}".format(v) if v < 16 else "{0:x}".format(v) for v in RGB]
    )


def linear_gradient(start_hex, finish_hex="#FFFFFF", n=10):
    """returns a gradient list of (n) colors between
    two hex colors. start_hex and finish_hex
    should be the full six-digit color string,
    inlcuding the number sign ("#FFFFFF")"""
    # Starting and ending colors in RGB form
    s = hex_to_rgb(start_hex)
    f = hex_to_rgb(finish_hex)
    # Initilize a list of the output colors with the starting color
    RGB_list = [s]
    # Calcuate a color at each evenly spaced value of t from 1 to n
    for t in range(1, n):
        # Interpolate RGB vector for color at the current value of t
        curr_vector = [
            int(s[j] + (float(t) / (n - 1)) * (f[j] - s[j])) for j in range(3)
        ]
        # Add it to our list of output colors
        RGB_list.append(curr_vector)

    # print(RGB_list)
    return color_dict_maker(RGB_list)


def polylinear_gradient(colors, n):
    """returns a list of colors forming linear gradients between
    all sequential pairs of colors. "n" specifies the total
    number of desired output colors"""
    # The number of colors per individual linear gradient
    n_out = int(float(n) / (len(colors) - 1)) + 1
    # print(('n',n))
    # print(('n_out',n_out))
    # If we don't have an even number of color values, we will remove equally spaced values at the end.
    apply_offset = False
    if n % n_out != 0:
        apply_offset = True
        n_out = n_out + 1
        # print(('new n_out',n_out))

    # returns dictionary defined by color_dict()
    gradient_dict = linear_gradient(colors[0], colors[1], n_out)

    if len(colors) > 1:
        for col in range(1, len(colors) - 1):
            next = linear_gradient(colors[col], colors[col + 1], n_out)
            for k in ("hex", "r", "g", "b"):
                # Exclude first point to avoid duplicates
                gradient_dict[k] += next[k][1:]

    # Remove equally spaced values here.
    if apply_offset:
        # indList = list(range(len(gradient_dict['hex'])))
        offset = len(gradient_dict["hex"]) - n
        sliceval = []
        # print(('len(gradient_dict)',len(gradient_dict['hex'])))
        # print(('offset',offset))

        for i in range(1, offset + 1):
            sliceval.append(int(len(gradient_dict["hex"]) * i / float(offset + 2)))
        print(gradient_dict["hex"])
        print(("sliceval", sliceval))
        for k in ("hex", "r", "g", "b"):
            gradient_dict[k] = [
                i for j, i in enumerate(gradient_dict[k]) if j not in sliceval
            ]
        # print(('new len dict', len(gradient_dict['hex'])))
    print(gradient_dict["hex"], len(gradient_dict["hex"]))
    return gradient_dict


def get_poly_gradient_ct(palette, min, max):
    """
    Take a palette and a set of min and max stretch values to get a 1:1 value to color hex list

    Args:
        palette (list): A list of hex code colors that will be interpolated

        min (int): The min value for the stretch

        max (int): The max value for the stretch

    Returns:
        list: A list of linearly interpolated hex codes where there is 1:1 color to value from min-max (inclusive)
    """
    ramp = polylinear_gradient(palette, max - min + 1)
    return ramp["hex"]


# print(get_poly_gradient_ct(["#FFFF00", "00F", "0FF", "FF0000"], 1, 2))


##############################################################
######################################################################
# Function to check if being run inside a notebook
# Taken from: https://stackoverflow.com/questions/15411967/how-can-i-check-if-code-is-executed-in-the-ipython-notebook
def is_notebook():
    return ee.oauth._in_jupyter_shell()


######################################################################
# Function for cleaning trailing .... in accessToken
def cleanAccessToken(accessToken):
    """
    Remove trailing '....' in generated access token

    Args:
        accessToken (str): Raw access token

    Returns:
        str: Given access token without trailing '....'
    """
    while accessToken[-1] == ".":
        accessToken = accessToken[:-1]
    return accessToken


######################################################################
# Function to get domain base without any folders
def baseDomain(url):
    """
    Get root domain for a given url

    Args:
        url (str): URL to find the base domain of

    Returns:
        str: domain of given URL
    """
    url_parts = urlparse(url)
    return f"{url_parts.scheme}://{url_parts.netloc}"


######################################################################
# Function for using default GEE refresh token to get an access token for geeView
# Updated 12/23 to reflect updated auth methods for GEE
def refreshToken():
    credentials = ee.data.get_persistent_credentials()
    credentials.refresh(gReq.Request())
    accessToken = credentials.token
    # print(credentials.to_json())
    accessToken = cleanAccessToken(accessToken)
    return accessToken


######################################################################
# Function for using a GEE white-listed service account key to get an access token for geeView
def serviceAccountToken(service_key_file_path):
    try:
        credentials = service_account.Credentials.from_service_account_file(
            service_key_file_path, scopes=ee.oauth.SCOPES
        )
        credentials.refresh(gReq.Request())
        accessToken = credentials.token
        accessToken = cleanAccessToken(accessToken)
        return accessToken
    except Exception as e:
        print(e)
        print("Failed to utilize service account key file.")
        return None


######################################################################
# Function for running local web server
def run_local_server(port=8001):
    if sys.version[0] == "2":
        server_name = "SimpleHTTPServer"
    else:
        server_name = "http.server"
    cwd = os.getcwd()
    os.chdir(py_viz_dir)
    # print('cwd',os.getcwd())
    python_path = sys.executable
    if python_path.find("pythonw") > -1:
        python_path = python_path.replace("pythonw", "python")
    c = '"{}" -m {}  {}'.format(python_path, server_name, port)
    print("HTTP server command:", c)
    subprocess.Popen(c, shell=True)
    os.chdir(cwd)


######################################################################
# Function to see if port is active
def isPortActive(port=8001):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)  # 2 Second Timeout
    result = sock.connect_ex(("localhost", port))
    if result == 0:
        return True
    else:
        return False


######################################################################
######################################################################
######################################################################
# Set up mapper object
class mapper:
    """Primary geeViz map setup and manipulation object

    Map object that is used to manage layers, activated user input methods, and launching the map viewer user interface

    Attributes:
        port (int, optional): Which port to user for web server. Sometimes a port will become "stuck," so this will need set to some other number than what it was set at in previous runs of a given session.
    """

    def __init__(self, port=8001):
        self.port = port
        self.layerNumber = 1
        self.idDictList = []
        self.mapCommandList = []
        self.ee_run_name = "runGeeViz"

        self.typeLookup = {
            "Image": "geeImage",
            "ImageCollection": "geeImageCollection",
            "Feature": "geeVectorImage",
            "FeatureCollection": "geeVectorImage",
            "Geometry": "geeVectorImage",
            "dict": "geoJSONVector",
        }
        try:
            self.isNotebook = ee.oauth._in_jupyter_shell()
        except:
            self.isNotebook = ee.oauth.in_jupyter_shell()
        try:
            self.isColab = ee.oauth._in_colab_shell()
        except:
            self.isColab = ee.oauth.in_colab_shell()

        self.proxy_url = None

        self.refreshTokenPath = ee.oauth.get_credentials_path()
        self.serviceKeyPath = None
        self.queryWindowMode = "sidePane"
        self.project = project_id

    ######################################################################
    # Function for adding a layer to the map
    def addLayer(self, image, viz={}, name=None, visible=True):
        """
        Adds GEE object to the mapper object that will then be added to the map user interface with a `view` call.

        Args:
            image (ImageCollection, Image, Feature, FeatureCollection, Geometry): ee object to add to the map UI.
            viz (dict): Primary set of parameters for map visualization, querying, charting, etc. In addition to the parameters supported by the addLayer function in the GEE Code Editor, there are several additional parameters available to help facilitate legend generation, querying, and area summaries. The accepted keys are:

                {
                    "min" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00.,

                    "max" (int, list, or comma-separated numbers): One numeric value or one per band to map onto FF,

                    "gain" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00-FF.,

                    "bias" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00-FF.,

                    "gamma" (int, list, or comma-separated numbers): Gamma correction factor. One numeric value or one per band.,

                    "palette" (str, list, or comma-separated strings): List of CSS-style color strings (single-band previews only).,

                    "opacity" (float): a number between 0 and 1 for initially set opacity.,

                    "layerType" (str, one of geeImage, geeImageCollection, geeVector, geeVectorImage, geoJSONVector): Optional parameter. For vector data ("featureCollection", "feature", or "geometry"), you can spcify "geeVector" if you would like to force the vector to be an actual vector object on the client. This can be slow if the ee object is large and/or complex. Otherwise, any "featureCollection", "feature", or "geometry" will default to "geeVectorImage" where the vector is rasterized on-the-fly for map rendering. Any querying of the vector will query the underlying vector data though. To add a geojson vector as json, just add the json as the image parameter.,

                    "reducer" (Reducer, default 'ee.Reducer.lastNonNull()'): If an ImageCollection is provided, how to reduce it to create the layer that is shown on the map. Defaults to ee.Reducer.lastNonNull(),

                    "autoViz" (bool): Whether to take image bandName_class_values, bandName_class_names, bandName_class_palette properties to visualize, create a legend (populates `classLegendDict`), and apply class names to any query functions (populates `queryDict`),

                    "canQuery" (bool, default True): Whether a layer can be queried when visible.,

                    "addToLegend" (bool, default True): Whether geeViz should try to create a legend for this layer. Sometimes setting it to `False` is useful for continuous multi-band inputs.,

                    "classLegendDict" (dict): A dictionary with a key:value of the name:color(hex) to include in legend. This is auto-populated when `autoViz` : True,

                    "queryDict" (dict): A dictionary with a key:value of the queried number:label to include if queried numeric values have corresponding label names. This is auto-populated when `autoViz` : True,

                    "queryParams" (dict, optional): Dictionary of additional parameters for querying visible map layers:

                        {
                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart.
                        }

                    "legendLabelLeftBefore" (str) : Label for continuous legend on the left before the numeric component,

                    "legendLabelLeftAfter" (str) : Label for continuous legend on the left after the numeric component,

                    "legendLabelRightBefore" (str) : Label for continuous legend on the right before the numeric component,

                    "legendLabelRightAfter" (str) : Label for continuous legend on the right after the numeric component,

                    "canAreaChart" (bool): whether to include this layer for area charting. If the layer is complex, area charting can be quite slow,

                    "areaChartParams" (dict, optional): Dictionary of additional parameters for area charting:

                        {
                            "reducer" (Reducer, default `ee.Reducer.mean()` if no bandName_class_values, bandName_class_names, bandName_class_palette properties are available. `ee.Reducer.frequencyHistogram` if those are available or `thematic`:True (see below)): The reducer used to compute zonal summary statistics.,

                            "crs" (str, default "EPSG:5070"): the coordinate reference system string to use for are chart zonal stats,

                            "transform" (list, default [30, 0, -2361915, 0, -30, 3177735]): the transform to snap to for zonal stats,

                            "scale" (int, default None): The spatial resolution to use for zonal stats. Only specify if transform : None.

                            "line" (bool, default True): Whether to create a line chart,

                            "sankey" (bool, default False): Whether to create Sankey charts - only available for thematic (discrete) inputs that have a `system:time_start` property set for each image,

                            "sankeyTransitionPeriods" (list of lists, default None): The years to use as transition periods for sankey charts (e.g. [[1985,1987],[2000,2002],[2020,2022]]). If not provided, users can enter years in the map user interface under `Area Tools -> Transition Charting Periods`. These will automatically be used for any layers where no sankeyTransitionPeriods were provided. If years are provided, the years in the user interface will not be used for that layer.

                            "sankeyMinPercentage" (float, default 0.5): The minimum percentage a given class has to be to be shown in the sankey chart.

                            "thematic" (bool): Whether input has discrete values or not. If True, it forces the reducer to `ee.Reducer.frequencyHistogram()` even if not specified and even if bandName_class_values, bandName_class_names, bandName_class_palette properties are not available,

                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart,

                            "showGrid" (bool, default True): Whether to show the grid lines on the line or bar graph,

                            "rangeSlider" (bool,default False): Whether to include the x-axis range selector on the bottom of each graph (`https://plotly.com/javascript/range-slider/`)


                        }

                }
            name (str): Descriptive name for map layer that will be shown on the map UI
            visible (bool, optional): Whether layer should be visible when map UI loads

        >>> Map.addLayer(ee.Image(1),{'min':0,'max':1,'palette':'000,FFF},"Example Map Layer",True)


        """
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding layer: " + name)

        # Handle reducer if ee object is given
        if "reducer" in viz.keys():

            try:
                viz["reducer"] = viz["reducer"].serialize()
            except Exception as e:
                try:
                    viz["reducer"] = eval(viz["reducer"]).serialize()
                except Exception as e:  # Most likely it's already serialized
                    e = e
        if "areaChartParams" in viz.keys():

            if "reducer" in viz["areaChartParams"].keys():
                try:
                    viz["areaChartParams"]["reducer"] = viz["areaChartParams"][
                        "reducer"
                    ].serialize()
                except Exception as e:
                    try:
                        viz["areaChartParams"]["reducer"] = eval(
                            viz["areaChartParams"]["reducer"]
                        ).serialize()
                    except Exception as e:  # Most likely it's already serialized
                        e = e

        # Get the id and populate dictionarye
        idDict = {}
        imageType = type(image).__name__
        layerType = self.typeLookup[imageType]
        if "layerType" not in viz.keys():
            viz["layerType"] = layerType
        print("Type:", imageType, viz["layerType"])
        if not isinstance(image, dict):
            image = image.serialize()
            idDict["item"] = image
            idDict["function"] = "addSerializedLayer"
        # Handle passing in geojson vector layers
        else:
            idDict["item"] = json.dumps(image)
            viz["layerType"] = "geoJSONVector"
            idDict["function"] = "addLayer"
        idDict["objectName"] = "Map"
        idDict["name"] = name
        idDict["visible"] = str(visible).lower()
        idDict["viz"] = json.dumps(viz, sort_keys=False)

        self.idDictList.append(idDict)

    ######################################################################
    # Function for adding a layer to the map
    def addTimeLapse(self, image, viz={}, name=None, visible=True):
        """
        Adds GEE ImageCollection object to the mapper object that will then be added as an interactive time lapse in the map user interface with a `view` call.

        Args:
            image (ImageCollection): ee ImageCollecion object to add to the map UI.
            viz (dict): Primary set of parameters for map visualization, querying, charting, etc. These are largely the same as the `addLayer` function. Keys unique to `addTimeLapse` are provided here first. In addition to the parameters supported by the `addLayer` function in the GEE Code Editor, there are several additional parameters available to help facilitate legend generation, querying, and area summaries. The accepted keys are:

                {
                    "mosaic" (bool, default False): If an ImageCollection with multiple images per time step is provided, how to reduce it to create the layer that is shown on the map. Uses ee.Reducer.lastNonNull() if True or ee.Reducer.first() if False,

                    "dateFormat" (str, default "YYYY"): The format of the date to show in the slider. E.g. if your data is annual, generally "YYYY" is best. If it's monthly, generally "YYYYMM" is best. Daily, generally "YYYYMMdd"...etc.,

                    "advanceInterval" (str, default 'year'): How much to advance each frame when creating each individual mosaic. One of 'year', 'month' 'week', 'day', 'hour', 'minute', or 'second'.


                    "min" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00.,

                    "max" (int, list, or comma-separated numbers): One numeric value or one per band to map onto FF,

                    "gain" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00-FF.,

                    "bias" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00-FF.,

                    "gamma" (int, list, or comma-separated numbers): Gamma correction factor. One numeric value or one per band.,

                    "palette" (str, list, or comma-separated strings): List of CSS-style color strings (single-band previews only).,

                    "opacity" (float): a number between 0 and 1 for initially set opacity.,

                    "autoViz" (bool): Whether to take image bandName_class_values, bandName_class_names, bandName_class_palette properties to visualize, create a legend (populates `classLegendDict`), and apply class names to any query functions (populates `queryDict`),

                    "canQuery" (bool, default True): Whether a layer can be queried when visible.,

                    "addToLegend" (bool, default True): Whether geeViz should try to create a legend for this layer. Sometimes setting it to `False` is useful for continuous multi-band inputs.,

                    "classLegendDict" (dict): A dictionary with a key:value of the name:color(hex) to include in legend. This is auto-populated when `autoViz` : True,

                    "queryDict" (dict): A dictionary with a key:value of the queried number:label to include if queried numeric values have corresponding label names. This is auto-populated when `autoViz` : True,

                    "queryParams" (dict, optional): Dictionary of additional parameters for querying visible map layers:

                        {
                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart.
                        }

                    "legendLabelLeftBefore" (str) : Label for continuous legend on the left before the numeric component,

                    "legendLabelLeftAfter" (str) : Label for continuous legend on the left after the numeric component,

                    "legendLabelRightBefore" (str) : Label for continuous legend on the right before the numeric component,

                    "legendLabelRightAfter" (str) : Label for continuous legend on the right after the numeric component,

                    "canAreaChart" (bool): whether to include this layer for area charting. If the layer is complex, area charting can be quite slow,

                    "areaChartParams" (dict, optional): Dictionary of additional parameters for area charting:

                        {
                            "reducer" (Reducer, default `ee.Reducer.mean()` if no bandName_class_values, bandName_class_names, bandName_class_palette properties are available. `ee.Reducer.frequencyHistogram` if those are available or `thematic`:True (see below)): The reducer used to compute zonal summary statistics.,

                            "line" (bool, default True): Whether to create a line chart,

                            "sankey" (bool, default False): Whether to create Sankey charts - only available for thematic (discrete) inputs that have a `system:time_start` property set for each image,

                            "sankeyTransitionPeriods" (list of lists, default None): The years to use as transition periods for sankey charts (e.g. [[1985,1987],[2000,2002],[2020,2022]]). If not provided, users can enter years in the map user interface under `Area Tools -> Transition Charting Periods`. These will automatically be used for any layers where no sankeyTransitionPeriods were provided. If years are provided, the years in the user interface will not be used for that layer.

                            "sankeyMinPercentage" (float, default 0.5): The minimum percentage a given class has to be to be shown in the sankey chart.

                            "thematic" (bool): Whether input has discrete values or not. If True, it forces the reducer to `ee.Reducer.frequencyHistogram()` even if not specified and even if bandName_class_values, bandName_class_names, bandName_class_palette properties are not available,

                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart,

                            "showGrid" (bool, default True): Whethe to show the grid lines on the line or bar graph,

                            "rangeSlider" (bool,default False): Whether to include the x-axis range selector on the bottom of each graph (`<https://plotly.com/javascript/range-slider/>`)


                        }

                }
            name (str): Descriptive name for map layer that will be shown on the map UI
            visible (bool, optional): Whether layer should be visible when map UI loads

        >>> Map.addTimeLapse(ee.Image(1),{'min':0,'max':1,'palette':'000,FFF},"Example Map Layer",True)


        """
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding layer: " + name)

        # Handle reducer if ee object is given - delete it
        if "reducer" in viz.keys():
            del viz["reducer"]

        # Handle area charting reducer
        if "areaChartParams" in viz.keys():

            if "reducer" in viz["areaChartParams"].keys():
                try:
                    viz["areaChartParams"]["reducer"] = viz["areaChartParams"][
                        "reducer"
                    ].serialize()
                except Exception as e:
                    try:
                        viz["areaChartParams"]["reducer"] = eval(
                            viz["areaChartParams"]["reducer"]
                        ).serialize()
                    except Exception as e:  # Most likely it's already serialized
                        e = e
        viz["layerType"] = "ImageCollection"
        # Get the id and populate dictionary
        idDict = {}  # image.getMapId()
        idDict["objectName"] = "Map"
        idDict["item"] = image.serialize()
        idDict["name"] = name
        idDict["visible"] = str(visible).lower()
        idDict["viz"] = json.dumps(viz, sort_keys=False)
        idDict["function"] = "addSerializedTimeLapse"
        self.idDictList.append(idDict)

    ######################################################################
    # Function for adding a select layer to the map
    def addSelectLayer(self, featureCollection, viz={}, name=None):
        """
        Adds GEE featureCollection to the mapper object that will then be added as an interactive selection layer in the map user interface with a `view` call. This layer will be availble for selecting areas to include in area summary charts.

        Args:
            featureCollection (FeatureCollection): ee FeatureCollecion object to add to the map UI as a selectable layer, where each feature is selectable by clicking on it.
            viz (dict, optional): Primary set of parameters for map visualization and specifying which feature attribute to use as the feature name (selectLayerNameProperty), etc. In addition to the parameters supported by the `addLayer` function in the GEE Code Editor, there are several additional parameters available to help facilitate legend generation, querying, and area summaries. The accepted keys are:

                {
                    "strokeColor" (str, default random color): The color of the selection layer on the map,

                    "strokeWeight" (int, default 3): The thickness of the polygon outlines,

                    "selectLayerNameProperty" (str, default first feature attribute with "name" in it or "system:index"): The attribute name to show when a user selects a feature.



                }
            name (str, default None): Descriptive name for map layer that will be shown on the map UI. Will be auto-populated with `Layer N` if not specified

        """
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding layer: " + name)

        # Get the id and populate dictionary
        idDict = {}  # image.getMapId()
        idDict["objectName"] = "Map"
        idDict["item"] = featureCollection.serialize()
        idDict["name"] = name
        idDict["visible"] = str(False).lower()
        idDict["viz"] = json.dumps(viz, sort_keys=False)
        idDict["function"] = "addSerializedSelectLayer"
        self.idDictList.append(idDict)

    ######################################################################
    # Function for setting the map zoom
    def setZoom(self, zoom):
        """
        Set the map zoom level

        Args:
            zoom (int): The zoom level to set the map to on loading.
        """
        self.mapCommandList.append(f"map.setZoom({zoom})")

    ######################################################################
    # Function for centering on a GEE object that has a geometry
    def centerObject(self, feature, zoom=None):
        """
        Center the map on an object on loading

        Args:
            feature (Feature, FeatureCollection, or Geometry): The object to center the map on
            zoom (int, optional): If provided, will force the map to zoom to this level after centering it on the object. If not provided, the highest zoom level that allows the feature to be viewed fully will be used.
        """
        try:
            bounds = json.dumps(feature.geometry().bounds(100, "EPSG:4326").getInfo())
        except Exception as e:
            bounds = json.dumps(feature.bounds(100, "EPSG:4326").getInfo())
        command = "synchronousCenterObject(" + bounds + ")"

        self.mapCommandList.append(command)

        if zoom != None:
            self.setZoom(zoom)

    ######################################################################
    # Function for launching the web map after all adding to the map has been completed
    def view(self, open_browser=None, open_iframe=None, iframe_height=525):
        """
        Compiles all map objects and commands and starts the map server

        Args:
            open_browser (bool): Whether or not to open the browser. If unspecified, will automatically be selected depending on whether geeViz is being used in a notebook (False) or not (True).

            open_iframe (bool): Whether or not to open an iframe. If unspecified, will automatically be selected depending on whether geeViz is being used in a notebook (True) or not (False).

            iframe_height (int, default 525): The height of the iframe shown if running inside a notebook
        """
        print("Starting webmap")

        # Get access token
        if self.serviceKeyPath == None:
            print("Using default refresh token for geeView")
            self.accessToken = refreshToken()
        else:
            print("Using service account key for geeView:", self.serviceKeyPath)
            self.accessToken = serviceAccountToken(self.serviceKeyPath)
            if self.accessToken == None:
                print("Trying to authenticate to GEE using persistent refresh token.")
                self.accessToken = refreshToken(self.refreshTokenPath)
        # Set up js code to populate
        lines = "var layerLoadErrorMessages=[];showMessage('Loading',staticTemplates.loadingModal[mode]);\nfunction runGeeViz(){\n"

        # Iterate across each map layer to add js code to
        for idDict in self.idDictList:
            t = "{}.{}({},{},'{}',{});".format(
                idDict["objectName"],
                idDict["function"],
                idDict["item"],
                idDict["viz"],
                idDict["name"],
                str(idDict["visible"]).lower(),
            )
            # t = (
            #     "try{\n\t"
            #     + t
            #     + '\n}catch(err){\n\tlayerLoadErrorMessages.push("Error loading: '
            #     + idDict["name"]
            #     + '<br>GEE "+err);}\n'
            # )

            lines += t
        lines += 'if(layerLoadErrorMessages.length>0){showMessage("Map.addLayer Error List",layerLoadErrorMessages.join("<br>"));}\n'
        lines += "setTimeout(function(){if(layerLoadErrorMessages.length===0){$('#close-modal-button').click();}}, 2500);\n"

        # Iterate across each map command
        for mapCommand in self.mapCommandList:
            lines += mapCommand + "\n"

        # Set location of query outputs
        lines += 'queryWindowMode = "{}"\n'.format(self.queryWindowMode)

        lines += "}"

        # Write out js file
        self.ee_run = os.path.join(ee_run_dir, "{}.js".format(self.ee_run_name))
        oo = open(self.ee_run, "w")
        oo.writelines(lines)
        oo.close()
        # time.sleep(5)

        # if not self.isNotebook:
        #     self.Map.save(os.path.join(folium_html_folder,folium_html))
        #     if not geeView.isPortActive(self.port):
        #         print('Starting local web server at: http://localhost:{}/{}/'.format(self.port,geeView.geeViewFolder))
        #         geeView.run_local_server(self.port)
        #         print('Done')
        #     else:
        #         print('Local web server at: http://localhost:{}/{}/ already serving.'.format(self.port,geeView.geeViewFolder))
        #     if open_browser:
        #         geeView.webbrowser.open('http://localhost:{}/{}/{}'.format(self.port,geeView.geeViewFolder,folium_html),new = 1)

        # else:
        #     display(self.Map)

        if not isPortActive(self.port):
            print(
                "Starting local web server at: http://localhost:{}/{}/".format(
                    self.port, geeViewFolder
                )
            )
            run_local_server(self.port)
            print("Done")

        else:
            print(
                "Local web server at: http://localhost:{}/{}/ already serving.".format(
                    self.port, geeViewFolder
                )
            )
            # print('Refresh browser instance')

        print("cwd", os.getcwd())
        if IS_COLAB:
            proxy_js = "google.colab.kernel.proxyPort({})".format(self.port)
            proxy_url = eval_js(proxy_js)
            geeView_proxy_url = "{}geeView/?projectID={}&accessToken={}".format(
                proxy_url, self.project, self.accessToken
            )
            print("Colab Proxy URL:", geeView_proxy_url)
            viewerFrame = IFrame(
                src=geeView_proxy_url, width="100%", height="{}px".format(iframe_height)
            )
            display(viewerFrame)
        elif IS_WORKBENCH:
            if self.proxy_url == None:
                self.proxy_url = input(
                    "Please enter current URL Workbench Notebook is running from (e.g. https://code-dot-region.notebooks.googleusercontent.com/): "
                )
            self.proxy_url = baseDomain(self.proxy_url)
            geeView_proxy_url = (
                "{}/proxy/{}/geeView/?projectID={}&accessToken={}".format(
                    self.proxy_url, self.port, self.project, self.accessToken
                )
            )
            print("Workbench Proxy URL:", geeView_proxy_url)
            viewerFrame = IFrame(
                src=geeView_proxy_url, width="100%", height="{}px".format(iframe_height)
            )
            display(viewerFrame)
        else:
            url = "http://localhost:{}/{}/?projectID={}&accessToken={}".format(
                self.port, geeViewFolder, self.project, self.accessToken
            )
            print("geeView URL:", url)
            if not self.isNotebook or open_browser:
                webbrowser.open(url, new=1)
            elif open_browser == False and open_iframe:
                self.IFrame = IFrame(
                    src=url, width="100%", height="{}px".format(iframe_height)
                )
            else:
                self.IFrame = IFrame(
                    src=url, width="100%", height="{}px".format(iframe_height)
                )
                display(self.IFrame)

    ######################################################################
    def clearMap(self):
        """
        Removes all map layers and commands - useful if running geeViz in a notebook and don't want layers/commands from a prior code block to still be included.
        """
        self.layerNumber = 1
        self.idDictList = []
        self.mapCommandList = []

    ######################################################################
    def setMapTitle(self, title):
        """
        Set the title that appears in the left sidebar header and the page title

        Args:
            title (str, default geeViz Data Explorer): The title to appear in the header on the left sidebar as well as the title of the viewer webpage.
        """
        title_command = f'Map.setTitle("{title}")'
        if title_command not in self.mapCommandList:
            self.mapCommandList.append(title_command)

    ######################################################################
    def setTitle(self, title):
        """
        Set the title that appears in the left sidebar header and the page title

        Args:
            title (str, default geeViz Data Explorer): The title to appear in the header on the left sidebar as well as the title of the viewer webpage.
        """
        self.setMapTitle(title)

    ######################################################################
    # Functions to set various click query properties
    def setQueryCRS(self, crs):
        """
        The coordinate reference system string to query layers with

        Args:
            crs (str, default "EPSG:5070"): Which projection (CRS) to use for querying map layers.
        """
        print("Setting click query crs to: {}".format(crs))
        cmd = f'Map.setQueryCRS("{crs}");'
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryScale(self, scale):
        """
        What scale to query map layers with. Will also update the size of the box drawn on the map query layers are queried.

        Args:
            scale (int, default None): The spatial resolution to use for querying map layers in meters. If set, the query transform will be set to None in the map viewer.
        """
        print("Setting click query scale to: {}".format(scale))
        cmd = f"Map.setQueryScale({scale});"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryTransform(self, transform):
        """
        What transform to query map layers with. Will also update the size of the box drawn on the map query layers are queried.

        Args:
            transform (list, default [30, 0, -2361915, 0, -30, 3177735]): The snap to grid to use for querying layers on the map. If set, the query scale will be set to None in the map viewer.
        """
        print("Setting click query transform to: {}".format(transform))
        cmd = f"Map.setQueryTransform({transform});"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryPrecision(self, chartPrecision=3, chartDecimalProportion=0.25):
        """
        What level of precision to show for queried layers. This avoids showing too many digits after the decimal.

        Args:
            chartPrecision (int, default 3): Will show the larger of `chartPrecision` decimal places or ceiling(`chartDecimalProportion` * total decimal places). E.g. if the number is 1.12345678, 0.25 of 8 decimal places is 2, so 3 will be used and yield 1.123.
            chartDecimalProportion (float, default 0.25): Will show the larger of `chartPrecision` decimal places or `chartDecimalProportion` * total decimal places. E.g. if the number is 1.1234567891234, ceiling(0.25 of 13) decimal places is 4, so 4 will be used and yield 1.1235.
        """
        print("Setting click query precision to: {}".format(chartPrecision))
        cmd = f"Map.setQueryPrecision({chartPrecision},{chartDecimalProportion});"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryDateFormat(self, defaultQueryDateFormat="YYYY-MM-dd"):
        """
        Set the date format to be used for any dates when querying.

        Args:
            defaultQueryDateFormat (str, default "YYYY-MM-dd"): The date format string to use for query outputs with dates. To simplify date outputs, "YYYY" is often used instead of the default.
        """
        print("Setting default query date format to: {}".format(defaultQueryDateFormat))
        cmd = f'Map.setQueryDateFormat("{defaultQueryDateFormat}");'
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryBoxColor(self, color):
        """
        Set the color of the query box to something other than yellow

        Args:
            color (str, default "FFFF00"): Set the default query box color shown on the map by providing a hex color.
        """
        print("Setting click query box color to: {}".format(color))
        cmd = f'Map.setQueryBoxColor("{color}");'
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    # Functions to handle location of query outputs
    def setQueryWindowMode(self, mode):
        self.queryWindowMode = mode

    def setQueryToInfoWindow(self):
        """
        Set the location of query outputs to an info window popup over the map
        """
        self.setQueryWindowMode("infoWindow")

    def setQueryToSidePane(self):
        """
        Set the location of query outputs to the right sidebar above the legend
        """
        self.setQueryWindowMode("sidePane")

    ######################################################################
    # Turn on query inspector
    def turnOnInspector(self):
        """
        Turn on the query inspector tool upon map loading. This is used frequently so map layers can be queried as soon as the map viewer loads.
        """
        query_command = "Map.turnOnInspector();"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    # Turn on area charting
    def turnOnAutoAreaCharting(self):
        """
        Turn on automatic area charting upon map loading. This will automatically update charts by summarizing any visible layers with "canAreaChart" : True any time the map finishes panning or zooming.
        """
        query_command = "Map.turnOnAutoAreaCharting();"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def turnOnUserDefinedAreaCharting(self):
        """
        Turn on area charting by a user defined area upon map loading. This will update charts by summarizing any visible layers with "canAreaChart" : True when the user draws an area to summarize and hits the `Chart Selected Areas` button in the user interface under `Area Tools -> User-Defined Area`.
        """
        query_command = "Map.turnOnUserDefinedAreaCharting();"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def turnOnSelectionAreaCharting(self):
        """
        Turn on area charting by a user selected area upon map loading. This will update charts by summarizing any visible layers with "canAreaChart" : True when the user selects selection areas to summarize and hits the `Chart Selected Areas` button in the user interface under `Area Tools -> Select an Area on Map`.
        """
        query_command = "Map.turnOnSelectionAreaCharting();"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def addAreaChartLayer(self, image, params={}, name=None, shouldChart=True):
        """
        Use this method to add a layer for area charting that you do not want as a map layer as well. Once you add all area chart layers to the map, you can turn them on using the `Map.populateAreaChartLayerSelect` method. This will create a selection menu inside the `Area Tools -> Area Tools Parameters` menu. You can then turn layers to include in any area charts on and off from that menu.

        Args:
            image (ImageCollection, Image): ee Image or ImageCollection to add to include in area charting.
            params (dict): Primary set of parameters for charting setup (colors, chart types, etc), charting, etc. The accepted keys are:

                {

                    "reducer" (Reducer, default `ee.Reducer.mean()` if no bandName_class_values, bandName_class_names, bandName_class_palette properties are available. `ee.Reducer.frequencyHistogram` if those are available or `thematic`:True (see below)): The reducer used to compute zonal summary statistics.,

                    "crs" (str, default "EPSG:5070"): the coordinate reference system string to use for are chart zonal stats,

                    "transform" (list, default [30, 0, -2361915, 0, -30, 3177735]): the transform to snap to for zonal stats,

                    "scale" (int, default None): The spatial resolution to use for zonal stats. Only specify if transform : None.

                    "line" (bool, default True): Whether to create a line chart,

                    "sankey" (bool, default False): Whether to create Sankey charts - only available for thematic (discrete) inputs that have a `system:time_start` property set for each image,

                    "sankeyTransitionPeriods" (list of lists, default None): The years to use as transition periods for sankey charts (e.g. [[1985,1987],[2000,2002],[2020,2022]]). If not provided, users can enter years in the map user interface under `Area Tools -> Transition Charting Periods`. These will automatically be used for any layers where no sankeyTransitionPeriods were provided. If years are provided, the years in the user interface will not be used for that layer.

                    "sankeyMinPercentage" (float, default 0.5): The minimum percentage a given class has to be to be shown in the sankey chart.

                    "thematic" (bool): Whether input has discrete values or not. If True, it forces the reducer to `ee.Reducer.frequencyHistogram()` even if not specified and even if bandName_class_values, bandName_class_names, bandName_class_palette properties are not available,

                    "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart.

                }
            name (str): Descriptive name for map layer that will be shown on the map UI
            visible (bool, optional): Whether layer should be visible when map UI loads

        """
        if name == None:
            name = "Area Chart Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding area chart layer: " + name)

        # Handle reducer if ee object is given
        if "reducer" in params.keys():

            try:
                params["reducer"] = params["reducer"].serialize()
            except Exception as e:
                try:
                    params["reducer"] = eval(params["reducer"]).serialize()
                except Exception as e:  # Most likely it's already serialized
                    e = e

        # Get the id and populate dictionary
        idDict = {}

        if not isinstance(image, dict):
            params["serialized"] = True
            params["layerType"] = type(image).__name__
            image = image.serialize()

        idDict["item"] = image
        idDict["function"] = "addLayer"
        idDict["objectName"] = "areaChart"
        idDict["name"] = name
        idDict["visible"] = str(shouldChart).lower()
        idDict["viz"] = json.dumps(params, sort_keys=False)

        self.idDictList.append(idDict)

    def populateAreaChartLayerSelect(self):
        """
        Once you add all area chart layers to the map, you can turn them on using this method- `Map.populateAreaChartLayerSelect`. This will create a selection menu inside the `Area Tools -> Area Tools Parameters` menu. You can then turn layers to include in any area charts on and off from that menu.
        """
        query_command = "areaChart.populateChartLayerSelect();"

        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    # Functions to handle setting query output y labels
    def setYLabelMaxLength(self, maxLength):
        command = f"yLabelMaxLength = {maxLength}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelBreakLength(self, maxLength):
        command = f"yLabelBreakLength = {maxLength}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelMaxLines(self, maxLines):
        """
        Set the max number of lines each y-axis label can have.

        Args:
            maxLines (int, default 5): The maximum number of lines each y-axis label can have. Will simply exclude any remaining lines.
        """
        command = f"yLabelMaxLines = {maxLines}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelFontSize(self, fontSize):
        """
        Set the size of the font on the y-axis labels. Useful when y-axis labels are too large to fit on the chart.

        Args:
            fontSize (int, default 10): The font size used on the y-axis labels for query charting.
        """
        command = f"yLabelFontSize = {fontSize}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    # Specify whether layers can be re-ordered by the user
    def setCanReorderLayers(self, canReorderLayers):
        """
        Set whether layers can be reordered by dragging layer user interface objects. By default all non timelapse and non geojson layers can be reordereed by dragging.

        Args:
            canReorderLayers (bool): Set whether layers can be reordered by dragging layer user interface objects. By default all non timelapse and non geojson layers can be reordereed by dragging.
        """
        command = f"Map.canReorderLayers = {str(canReorderLayers).lower()};"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    # Functions to handle batch layer toggling
    def turnOffAllLayers(self):
        """
        Turn off all layers added to the mapper object
        """
        update = {"visible": "false"}
        self.idDictList = [{**d, **update} for d in self.idDictList]

    def turnOnAllLayers(self):
        """
        Turn on all layers added to the mapper object
        """
        update = {"visible": "true"}
        self.idDictList = [{**d, **update} for d in self.idDictList]


# Instantiate Map object
Map = mapper()
