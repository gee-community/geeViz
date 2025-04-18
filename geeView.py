"""
View GEE objects using Python

geeViz.geeView is the core module for managing GEE objects on the geeViz mapper object. geeViz instantiates an instance of the `mapper` class as `Map` by default. Layers can be added to the map using `Map.addLayer` or `Map.addTimeLapse` and then viewed using the `Map.view` method.

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

# Script to allow GEE objects to be viewed in a web viewer
# Intended to work within the geeViz package
######################################################################
# Import modules
import ee, sys, os, webbrowser, json, socket, subprocess, site, datetime, requests, google
from google.auth.transport import requests as gReq
from google.oauth2 import service_account

from threading import Thread
from urllib.parse import urlparse
from IPython.display import IFrame, display, HTML

if sys.version_info[0] < 3:
    import SimpleHTTPServer, SocketServer
else:
    import http.server, socketserver


IS_COLAB = ee.oauth.in_colab_shell()  # "google.colab" in sys.modules
IS_WORKBENCH = os.getenv("DL_ANACONDA_HOME") != None
if IS_COLAB:
    from google.colab.output import eval_js

######################################################################
# Functions to handle various initialization/authentication workflows to try to get a user an initialized instance of ee


# Function to have user input a project id if one is still needed
def setProject(id):
    """
    Sets the project id of an instance of ee

    Args:
        id (str): Google Cloud Platform project id to use

    """
    
   
    ee.data.setCloudApiUserProject(id)

def simpleSetProject(overwrite=False,verbose=False):
    """
    Tries to find the current Google Cloud Platform project id and set it

    Args:
    overwrite (bool, optional): Whether or not to overwrite a cached project ID file

    """

    creds_path = ee.oauth.get_credentials_path()
    creds_dir = os.path.dirname(creds_path)
    if not os.path.exists(creds_dir):os.makedirs(creds_dir)

    provided_project = "{}.proj_id".format(creds_path)
    provided_project = os.path.normpath(provided_project)

    if not os.path.exists(provided_project) or overwrite:
        project_id = input("Please enter GEE project ID: ")

        print("You entered: {}".format(project_id))
        o = open(provided_project, "w")
        o.write(project_id)
        o.close()
    else:
        o = open(provided_project, "r")
        project_id = o.read()
        if verbose:
            print("Cached project id file path: {}".format(provided_project))
            print("Cached project id: {}".format(project_id))
        o.close()
    setProject(project_id)
    

def robustInitializer(verbose: bool = False):
    """
    A method that tries to authenticate and/or initialize GEE if it isn't already successfully initialized. This method tries to handle many different scenarios, but often fails. It is best to authenticate and initialize to a project prior to importing geeViz
    """

    try:
        z = ee.Number(1).getInfo()
        project_id = ee.data._cloud_api_user_project
        if verbose:
            print('Found project id set to:',project_id)
    except Exception as e:
        print('Earth Engine not initialized. Current Earth Engine best practices recommend running: `ee.Authenticate()`,`ee.Initialize(project="someProjectID")`, before importing geeViz.\ngeeViz will try to authenticate (if needed) and initialize automatically now. If this fails, please run these commands manually.')
        if verbose:
            print('EE error:',e)
            print("Will try authenticating and initializing GEE")
        try:
            ee.Authenticate()
            ee.Initialize(project=ee.data._cloud_api_user_project)
            print('Successfully initialized GEE')
        except Exception as e:
            if verbose:
                print('EE error:',e)
            simpleSetProject(False)

            try:
                ee.Initialize(project=ee.data._cloud_api_user_project)
                z = ee.Number(1).getInfo()
                print('Successfully initialized GEE')
            except Exception as e:
                if verbose:
                    print('EE error:',e)
                    print('Will ask for a different project id')
                simpleSetProject(True)
                ee.Initialize(project=ee.data._cloud_api_user_project)
                z = ee.Number(1).getInfo()
                print('Successfully initialized GEE')

robustInitializer()
######################################################################
# Set up GEE and paths
geeVizFolder = "geeViz"
geeViewFolder = "geeView"

# Set up template web viewer
# Do not change
cwd = os.getcwd()

paths = sys.path

py_viz_dir = os.path.dirname(__file__)

# print("geeViz package folder:", py_viz_dir)

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
def color_dict_maker(gradient: list[list[int]]) -> dict:
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
def hex_to_rgb(value: str) -> tuple:
    """Return (red, green, blue) for the color given as #rrggbb."""
    value = value.lstrip("#")
    lv = len(value)
    if lv == 3:
        lv = 6
        value = f"{value[0]}{value[0]}{value[1]}{value[1]}{value[2]}{value[2]}"

    return tuple(int(value[i : i + lv // 3], 16) for i in range(0, lv, lv // 3))


def RGB_to_hex(RGB: list[int]) -> str:
    """[255,255,255] -> "#FFFFFF" """
    # Components need to be integers for hex to make sense
    RGB = [int(x) for x in RGB]
    return "#" + "".join(["0{0:x}".format(v) if v < 16 else "{0:x}".format(v) for v in RGB])


def linear_gradient(start_hex: str, finish_hex: str = "#FFFFFF", n: int = 10) -> dict:
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
        curr_vector = [int(s[j] + (float(t) / (n - 1)) * (f[j] - s[j])) for j in range(3)]
        # Add it to our list of output colors
        RGB_list.append(curr_vector)

    # print(RGB_list)
    return color_dict_maker(RGB_list)


def polylinear_gradient(colors: list[str], n: int):
    """returns a list of colors forming linear gradients between
    all sequential pairs of colors. "n" specifies the total
    number of desired output colors"""
    # The number of colors per individual linear gradient
    n_out = int(float(n) / (len(colors) - 1)) + 1

    # If we don't have an even number of color values, we will remove equally spaced values at the end.
    apply_offset = False
    if n % n_out != 0:
        apply_offset = True
        n_out = n_out + 1

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
        offset = len(gradient_dict["hex"]) - n
        sliceval = []

        for i in range(1, offset + 1):
            sliceval.append(int(len(gradient_dict["hex"]) * i / float(offset + 2)))

        for k in ("hex", "r", "g", "b"):
            gradient_dict[k] = [i for j, i in enumerate(gradient_dict[k]) if j not in sliceval]

    return gradient_dict


def get_poly_gradient_ct(palette: list[str], min: int, max: int) -> list[str]:
    """
    Take a palette and a set of min and max stretch values to get a 1:1 value to color hex list

    Args:
        palette (list): A list of hex code colors that will be interpolated

        min (int): The min value for the stretch

        max (int): The max value for the stretch

    Returns:
        list: A list of linearly interpolated hex codes where there is 1:1 color to value from min-max (inclusive)

    >>> import geeViz.geeView as gv
    >>> viz = {"palette": ["#FFFF00", "00F", "0FF", "FF0000"], "min": 1, "max": 20}
    >>> color_ramp = gv.get_poly_gradient_ct(viz["palette"], viz["min"], viz["max"])
    >>> print("Color ramp:", color_ramp)

    """
    ramp = polylinear_gradient(palette, max - min + 1)
    return ramp["hex"]


##############################################################
######################################################################
# Function to check if being run inside a notebook
# Taken from: https://stackoverflow.com/questions/15411967/how-can-i-check-if-code-is-executed-in-the-ipython-notebook
def is_notebook():
    """
    Check if inside Jupyter shell


    Returns:
        bool: Whether inside Jupyter shell or not
    """
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
    """
    Get a refresh token from currently authenticated ee instance

    Returns:
        str: temporary access token
    """
    credentials = ee.data.get_persistent_credentials()
    credentials.refresh(gReq.Request())
    accessToken = credentials.token
    # print(credentials.to_json())
    accessToken = cleanAccessToken(accessToken)
    return accessToken


######################################################################
# Function for using a GEE white-listed service account key to get an access token for geeView
def serviceAccountToken(service_key_file_path):
    """
    Get a refresh token from service account key file credentials

    Returns:
        str: temporary access token
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(service_key_file_path, scopes=ee.oauth.SCOPES)
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
def run_local_server(port: int = 8001):
    """
    Start a local webserver using the Python http.server

    Args:
        port (int): Port number to run local server at

    """
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
def isPortActive(port: int = 8001):
    """
    See if a given port number is currently active

    Args:
        port (int): Port number to check status of

    Returns:
        bool: Whether or not the port is already active
    """
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

    Args:
        port (int, default 8001): Which port to user for web server. Sometimes a port will become "stuck," so this will need set to some other number than what it was set at in previous runs of a given session.
    Attributes:
        port (int, default 8001): Which port to user for web server. Sometimes a port will become "stuck," so this will need set to some other number than what it was set at in previous runs of a given session.

        proxy_url (str, default None): The proxy url the web server runs through for either Google Colab or Vertex AI Workbench. This is automatically specified in Google Colab, but in Vertex AI Workbench, the `Map.proxy_url` must be specified as the current URL Workbench Notebook is running from (e.g. https://code-dot-region.notebooks.googleusercontent.com/).

        refreshTokenPath (str, default ee.oauth.get_credentials_path()): Refresh token credentials file path

        serviceKeyPath (str, default None): Location of a service account key json. If provided, this will be used for authentication inside geeView instead of the refresh token

        project (str, default  ee.data._cloud_api_user_project): Can override which project geeView will use for authentication. While geeViz will try to find a project if ee.data._cloud_api_user_project isn't already set (usually by `ee.Initialize(project="someProjectID")`) by prompting the user to enter one, in some builds, this does not work. Set this attribute manually if the URL say `project=None` when launching geeView using `Map.view()`.

        turnOffLayersWhenTimeLapseIsOn (bool, default True): Whether all other layers should be turned off when a time lapse is turned on. This is set to True by default to avoid confusing layer order rendering that can occur when time lapses and non-time lapses are visible at the same time. Often this confusion is fine and visualizing time lapses and other layers is desired. Set `Map.turnOffLayersWhenTimeLapseIsOn` to False in this instance.
    """

    def __init__(self, port: int = 8001):
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
        self.project = ee.data._cloud_api_user_project
        self.turnOffLayersWhenTimeLapseIsOn = True

    ######################################################################
    # Function for adding a layer to the map
    def addLayer(self, image: ee.Image | ee.ImageCollection | ee.Geometry | ee.Feature | ee.FeatureCollection, viz: dict = {}, name: str | None = None, visible: bool = True):
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

                    "includeClassValues" (bool, default True): Whether to include the numeric value of each class in the legend when `"autoViz":True`.

                    "canQuery" (bool, default True): Whether a layer can be queried when visible.,

                    "addToLegend" (bool, default True): Whether geeViz should try to create a legend for this layer. Sometimes setting it to `False` is useful for continuous multi-band inputs.,

                    "classLegendDict" (dict): A dictionary with a key:value of the name:color(hex) to include in legend. This is auto-populated when `autoViz` : True,

                    "queryDict" (dict): A dictionary with a key:value of the queried number:label to include if queried numeric values have corresponding label names. This is auto-populated when `autoViz` : True,

                    "queryParams" (dict, optional): Dictionary of additional parameters for querying visible map layers:

                        {
                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart.,

                            "yLabel" (str, optional): Y axis label for query charts. This is useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired label for the Y axis.
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

                            "chartLabelMaxWidth" (int, default 40): The maximum number of characters, including spaces, allowed in a single line of a chart class label. The class name will be broken at this number of characters, including spaces, to go to the next line,

                            "chartLabelMaxLength" (int, default 100): The maximum number of characters, including spaces, allowed in a chart class label. Any class name with more characters, including spaces, than this number will be cut off at this number of characters,

                            "sankeyTransitionPeriods" (list of lists, default None): The years to use as transition periods for sankey charts (e.g. [[1985,1987],[2000,2002],[2020,2022]]). If not provided, users can enter years in the map user interface under `Area Tools -> Transition Charting Periods`. These will automatically be used for any layers where no sankeyTransitionPeriods were provided. If years are provided, the years in the user interface will not be used for that layer,

                            "sankeyMinPercentage" (float, default 0.5): The minimum percentage a given class has to be to be shown in the sankey chart,

                            "thematic" (bool): Whether input has discrete values or not. If True, it forces the reducer to `ee.Reducer.frequencyHistogram()` even if not specified and even if bandName_class_values, bandName_class_names, bandName_class_palette properties are not available,

                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart,

                            "showGrid" (bool, default True): Whether to show the grid lines on the line or bar graph,

                            "rangeSlider" (bool,default False): Whether to include the x-axis range selector on the bottom of each graph (`https://plotly.com/javascript/range-slider/>`),

                            "barChartMaxClasses" (int, default 20): The maximum number of classes to show for image bar charts. Will automatically only show the top `bartChartMaxClasses` in any image bar chart. Any downloaded csv table will still have all of the class counts,

                            "minZoomSpecifiedScale" (int, default 11): The map zoom level where any lower zoom level, not including this zoom level, will multiply the spatial resolution used for the zonal stats by 2 for each lower zoom level. E.g. if the `minZoomSpecifiedScale` is 9 and the `scale` is 30, any zoom level >= 9 will compute zonal stats at 30m spatial resolution. Then, at zoom level 8, it will be 60m. Zoom level 7 will be 120m, etc,

                            "chartPrecision" (int, default 3): Used to override the default global precision settings for a specific area charting layer. See `setQueryPrecision` for setting the global charting precision. When specified, for this specific area charting layer, will show the larger of `chartPrecision` decimal places or ceiling(`chartDecimalProportion` * total decimal places). E.g. if the number is 1.12345678, 0.25 of 8 decimal places is 2, so 3 will be used and yield 1.123,

                            "chartDecimalProportion" (float, default 0.25): Used to override the default global precision settings for a specific area charting layer. See `setQueryPrecision` for setting the global charting precision. When specified, for this specific area charting layer, will show the larger of `chartPrecision` decimal places or `chartDecimalProportion` * total decimal places. E.g. if the number is 1.1234567891234, ceiling(0.25 of 13) decimal places is 4, so 4 will be used and yield 1.1235,

                            "hovermode" (str, default "closest"): The mode to show hover text in area summary charts. Options include "closest", "x", "y", "x unified", and "y unified",

                            "yAxisLabel" (str, default an appropriate label based on whether data are thematic or continuous): The Y axis label that will be included in charts. Defaults to a unit of % area for thematic and mean for continuous data,

                            "chartType" (str, default "line" for `ee.ImageCollection` and "bar" for `ee.Image` objects): The type of chart to show. Options include "line", "bar", "stacked-line", and "stacked-bar". This is only used for `ee.ImageCollection` objects. For `ee.Image` objects, the chartType is always "bar".
                        }

                }
            name (str): Descriptive name for map layer that will be shown on the map UI
            visible (bool, default True): Whether layer should be visible when map UI loads

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> nlcd = ee.ImageCollection("USGS/NLCD_RELEASES/2021_REL/NLCD").select(['landcover'])
        >>> Map.addLayer(nlcd, {"autoViz": True}, "NLCD Land Cover / Land Use 2021")
        >>> Map.turnOnInspector()
        >>> Map.view()


        """
        if name == None:
            name = f"Layer {self.layerNumber}"
            self.layerNumber += 1
        print("Adding layer: " + name)

        # Make sure not to update viz dictionary elsewhere
        viz = dict(viz)

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
                    viz["areaChartParams"]["reducer"] = viz["areaChartParams"]["reducer"].serialize()
                except Exception as e:
                    try:
                        viz["areaChartParams"]["reducer"] = eval(viz["areaChartParams"]["reducer"]).serialize()
                    except Exception as e:  # Most likely it's already serialized
                        e = e

        # Get the id and populate dictionarye
        idDict = {}

        if "layerType" not in viz.keys():
            imageType = type(image).__name__
            layerType = self.typeLookup[imageType]
            if imageType == "Geometry":
                image = ee.FeatureCollection([ee.Feature(image)])
            elif imageType == "Feature":
                image = ee.FeatureCollection([image])
                print(layerType)
            viz["layerType"] = layerType

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
    def addTimeLapse(self, image: ee.ImageCollection, viz: dict = {}, name: str | None = None, visible: bool = True):
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

                    "includeClassValues" (bool, default True): Whether to include the numeric value of each class in the legend when `"autoViz":True`.

                    "canQuery" (bool, default True): Whether a layer can be queried when visible.,

                    "addToLegend" (bool, default True): Whether geeViz should try to create a legend for this layer. Sometimes setting it to `False` is useful for continuous multi-band inputs.,

                    "classLegendDict" (dict): A dictionary with a key:value of the name:color(hex) to include in legend. This is auto-populated when `autoViz` : True,

                    "queryDict" (dict): A dictionary with a key:value of the queried number:label to include if queried numeric values have corresponding label names. This is auto-populated when `autoViz` : True,

                    "queryParams" (dict, optional): Dictionary of additional parameters for querying visible map layers:

                        {
                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart.,

                            "yLabel" (str, optional): Y axis label for query charts. This is useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired label for the Y axis.
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

                            "chartLabelMaxWidth" (int, default 40): The maximum number of characters, including spaces, allowed in a single line of a chart class label. The class name will be broken at this number of characters, including spaces, to go to the next line,

                            "chartLabelMaxLength" (int, default 100): The maximum number of characters, including spaces, allowed in a chart class label. Any class name with more characters, including spaces, than this number will be cut off at this number of characters,

                            "sankeyTransitionPeriods" (list of lists, default None): The years to use as transition periods for sankey charts (e.g. [[1985,1987],[2000,2002],[2020,2022]]). If not provided, users can enter years in the map user interface under `Area Tools -> Transition Charting Periods`. These will automatically be used for any layers where no sankeyTransitionPeriods were provided. If years are provided, the years in the user interface will not be used for that layer,

                            "sankeyMinPercentage" (float, default 0.5): The minimum percentage a given class has to be to be shown in the sankey chart,

                            "thematic" (bool): Whether input has discrete values or not. If True, it forces the reducer to `ee.Reducer.frequencyHistogram()` even if not specified and even if bandName_class_values, bandName_class_names, bandName_class_palette properties are not available,

                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart,

                            "showGrid" (bool, default True): Whether to show the grid lines on the line or bar graph,

                            "rangeSlider" (bool,default False): Whether to include the x-axis range selector on the bottom of each graph (`https://plotly.com/javascript/range-slider/>`),

                            "barChartMaxClasses" (int, default 20): The maximum number of classes to show for image bar charts. Will automatically only show the top `bartChartMaxClasses` in any image bar chart. Any downloaded csv table will still have all of the class counts,

                            "minZoomSpecifiedScale" (int, default 11): The map zoom level where any lower zoom level, not including this zoom level, will multiply the spatial resolution used for the zonal stats by 2 for each lower zoom level. E.g. if the `minZoomSpecifiedScale` is 9 and the `scale` is 30, any zoom level >= 9 will compute zonal stats at 30m spatial resolution. Then, at zoom level 8, it will be 60m. Zoom level 7 will be 120m, etc,

                            "chartPrecision" (int, default 3): Used to override the default global precision settings for a specific area charting layer. See `setQueryPrecision` for setting the global charting precision. When specified, for this specific area charting layer, will show the larger of `chartPrecision` decimal places or ceiling(`chartDecimalProportion` * total decimal places). E.g. if the number is 1.12345678, 0.25 of 8 decimal places is 2, so 3 will be used and yield 1.123,

                            "chartDecimalProportion" (float, default 0.25): Used to override the default global precision settings for a specific area charting layer. See `setQueryPrecision` for setting the global charting precision. When specified, for this specific area charting layer, will show the larger of `chartPrecision` decimal places or `chartDecimalProportion` * total decimal places. E.g. if the number is 1.1234567891234, ceiling(0.25 of 13) decimal places is 4, so 4 will be used and yield 1.1235,

                            "hovermode" (str, default "closest"): The mode to show hover text in area summary charts. Options include "closest", "x", "y", "x unified", and "y unified",

                            "yAxisLabel" (str, default an appropriate label based on whether data are thematic or continuous): The Y axis label that will be included in charts. Defaults to a unit of % area for thematic and mean for continuous data,

                            "chartType" (str, default "line" for `ee.ImageCollection` and "bar" for `ee.Image` objects): The type of chart to show. Options include "line", "bar", "stacked-line", and "stacked-bar". This is only used for `ee.ImageCollection` objects. For `ee.Image` objects, the chartType is always "bar".
                        }

                }
            name (str): Descriptive name for map layer that will be shown on the map UI
            visible (bool, default True): Whether layer should be visible when map UI loads

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter(ee.Filter.calendarRange(2010, 2023, "year"))
        >>> Map.addTimeLapse(lcms.select(["Land_Cover"]), {"autoViz": True, "mosaic": True}, "LCMS Land Cover Time Lapse")
        >>> Map.addTimeLapse(lcms.select(["Change"]), {"autoViz": True, "mosaic": True}, "LCMS Change Time Lapse")
        >>> Map.addTimeLapse(lcms.select(["Land_Use"]), {"autoViz": True, "mosaic": True}, "LCMS Land Use Time Lapse")
        >>> Map.turnOnInspector()
        >>> Map.view()


        """
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding layer: " + name)

        # Make sure not to update viz dictionary elsewhere
        viz = dict(viz)

        # Handle reducer if ee object is given - delete it
        if "reducer" in viz.keys():
            del viz["reducer"]

        # Handle area charting reducer
        if "areaChartParams" in viz.keys():

            if "reducer" in viz["areaChartParams"].keys():
                try:
                    viz["areaChartParams"]["reducer"] = viz["areaChartParams"]["reducer"].serialize()
                except Exception as e:
                    try:
                        viz["areaChartParams"]["reducer"] = eval(viz["areaChartParams"]["reducer"]).serialize()
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
    def addSelectLayer(self, featureCollection: ee.FeatureCollection, viz: dict = {}, name: str | None = None):
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

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True, "canAreaChart": True, "areaChartParams": {"line": True, "sankey": True}}, "LCMS")
        >>> mtbsBoundaries = ee.FeatureCollection("USFS/GTAC/MTBS/burned_area_boundaries/v1")
        >>> mtbsBoundaries = mtbsBoundaries.map(lambda f: f.set("system:time_start", f.get("Ig_Date")))
        >>> Map.addSelectLayer(mtbsBoundaries, {"strokeColor": "00F", "selectLayerNameProperty": "Incid_Name"}, "MTBS Fire Boundaries")
        >>> Map.turnOnSelectionAreaCharting()
        >>> Map.view()
        """
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1

        # Make sure not to update viz dictionary elsewhere
        viz = dict(viz)

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
    # Function for centering on a GEE object that has a geometry
    def setCenter(self, lng: float, lat: float, zoom: int | None = None):
        """
        Center the map on a specified point and optional zoom on loading

        Args:
            lng (int or float): The longitude to center the map on
            lat (int or float): The latitude to center the map on
            zoom (int, optional): If provided, will force the map to zoom to this level after centering it on the provided coordinates. If not provided, the current zoom level will be used.

        >>> from geeViz.geeView import *
        >>> Map.setCenter(-111,41,10)
        >>> Map.view()
        """

        command = f"Map.setCenter({lng},{lat},{json.dumps(zoom)})"

        self.mapCommandList.append(command)

    ######################################################################
    # Function for setting the map zoom
    def setZoom(self, zoom: int):
        """
        Set the map zoom level

        Args:
            zoom (int): The zoom level to set the map to on loading.

        >>> from geeViz.geeView import *
        >>> Map.setZoom(10)
        >>> Map.view()
        """
        self.mapCommandList.append(f"map.setZoom({zoom})")

    ######################################################################
    # Function for centering on a GEE object that has a geometry
    def centerObject(self, feature: ee.Geometry | ee.Feature | ee.FeatureCollection | ee.Image, zoom: int | None = None):
        """
        Center the map on an object on loading

        Args:
            feature (Feature, FeatureCollection, or Geometry): The object to center the map on
            zoom (int, optional): If provided, will force the map to zoom to this level after centering it on the object. If not provided, the highest zoom level that allows the feature to be viewed fully will be used.

        >>> from geeViz.geeView import *
        >>> pt = ee.Geometry.Point([-111, 41])
        >>> Map.addLayer(pt.buffer(10), {}, "Plot")
        >>> Map.centerObject(pt)
        >>> Map.view()

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
    def view(self, open_browser: bool | None = None, open_iframe: bool | None = None, iframe_height: int = 525):
        """
        Compiles all map objects and commands and starts the map server

        Args:
            open_browser (bool): Whether or not to open the browser. If unspecified, will automatically be selected depending on whether geeViz is being used in a notebook (False) or not (True).

            open_iframe (bool): Whether or not to open an iframe. If unspecified, will automatically be selected depending on whether geeViz is being used in a notebook (True) or not (False).

            iframe_height (int, default 525): The height of the iframe shown if running inside a notebook

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True, "canAreaChart": True, "areaChartParams": {"line": True, "sankey": True}}, "LCMS")
        >>> Map.turnOnInspector()
        >>> Map.view()
        """
        print("Starting webmap")

        # Get access token
        if self.serviceKeyPath == None:
            print("Using default refresh token for geeView")
            self.accessToken = refreshToken()
            self.accessTokenCreationTime = int(datetime.datetime.now().timestamp() * 1000)
        else:
            print("Using service account key for geeView:", self.serviceKeyPath)
            self.accessToken = serviceAccountToken(self.serviceKeyPath)
            if self.accessToken == None:
                print("Trying to authenticate to GEE using persistent refresh token.")
                self.accessToken = refreshToken(self.refreshTokenPath)
                self.accessTokenCreationTime = int(datetime.datetime.now().timestamp() * 1000)
            else:
                self.accessTokenCreationTime = None
        # Set up js code to populate
        lines = "var layerLoadErrorMessages=[];showMessage('Loading',staticTemplates.loadingModal[mode]);function runGeeViz(){"

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
        lines += 'if(layerLoadErrorMessages.length>0){showMessage("Map.addLayer Error List",layerLoadErrorMessages.join("<br>"));};'
        lines += "setTimeout(function(){if(layerLoadErrorMessages.length===0){$('#close-modal-button').click();}}, 2500);"

        # Iterate across each map command
        for mapCommand in self.mapCommandList:
            lines += mapCommand + ";"

        # Set location of query outputs
        lines += 'queryWindowMode = "{}";'.format(self.queryWindowMode)

        # Set whether all layers are turned off when a time lapse is turned on
        lines += "Map.turnOffLayersWhenTimeLapseIsOn = {};".format(str(self.turnOffLayersWhenTimeLapseIsOn).lower())
        lines += "};"

        # Write out js file
        self.ee_run = os.path.join(ee_run_dir, "{}.js".format(self.ee_run_name))
        oo = open(self.ee_run, "w")
        oo.writelines(lines)
        oo.close()

        # Find if port is already active and only start it if it is not
        if not isPortActive(self.port):
            print("Starting local web server at: http://localhost:{}/{}/".format(self.port, geeViewFolder))
            run_local_server(self.port)
            print("Done")

        else:
            print("Local web server at: http://localhost:{}/{}/ already serving.".format(self.port, geeViewFolder))

        # Open viewer in browser or iframe in notebook
        print("cwd", os.getcwd())

        if IS_COLAB:
            proxy_js = "google.colab.kernel.proxyPort({})".format(self.port)
            proxy_url = eval_js(proxy_js)
            geeView_proxy_url = "{}/geeView/?projectID={}&accessToken={}&accessTokenCreationTime={}".format(proxy_url, self.project, self.accessToken, self.accessTokenCreationTime)
            print("Colab Proxy URL:", geeView_proxy_url)
            viewerFrame = IFrame(src=geeView_proxy_url, width="100%", height="{}px".format(iframe_height))
            display(viewerFrame)
        elif IS_WORKBENCH:
            if self.proxy_url == None:
                self.proxy_url = input("Please enter current URL Workbench Notebook is running from (e.g. https://code-dot-region.notebooks.googleusercontent.com/): ")
            self.proxy_url = baseDomain(self.proxy_url)
            geeView_proxy_url = "{}/proxy/{}/geeView/?projectID={}&accessToken={}&accessTokenCreationTime={}".format(self.proxy_url, self.port, self.project, self.accessToken, self.accessTokenCreationTime)
            print("Workbench Proxy URL:", geeView_proxy_url)
            viewerFrame = IFrame(src=geeView_proxy_url, width="100%", height="{}px".format(iframe_height))
            display(viewerFrame)
        else:
            url = "http://localhost:{}/{}/?projectID={}&accessToken={}&accessTokenCreationTime={}".format(self.port, geeViewFolder, self.project, self.accessToken, self.accessTokenCreationTime)
            print("geeView URL:", url)
            if not self.isNotebook or open_browser:
                webbrowser.open(url, new=1)
            elif open_browser == False and open_iframe:
                self.IFrame = IFrame(src=url, width="100%", height="{}px".format(iframe_height))
            else:
                self.IFrame = IFrame(src=url, width="100%", height="{}px".format(iframe_height))
                display(self.IFrame)

    ######################################################################
    def clearMap(self):
        """
        Removes all map layers and commands - useful if running geeViz in a notebook and don't want layers/commands from a prior code block to still be included.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS") # Layer
        >>> Map.turnOnInspector() # Command
        >>> Map.clearMap() # Clear map layer and commands
        >>> Map.view()
        """
        self.layerNumber = 1
        self.idDictList = []
        self.mapCommandList = []

    def clearMapLayers(self):
        """
        Removes all map layers - useful if running geeViz in a notebook and don't want layers from a prior code block to still be included, but want commands to remain.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS") # Layer - this will be removed
        >>> Map.turnOnInspector() # Command - this will remain (even though there will be no layers to query)
        >>> Map.clearMapLayers() # Clear map layer only and leave commands
        >>> Map.view()
        """
        self.layerNumber = 1
        self.idDictList = []

    def clearMapCommands(self):
        """
        Removes all map commands - useful if running geeViz in a notebook and don't want commands from a prior code block to still be included, but want layers to remain.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS") # Layer
        >>> Map.turnOnInspector() # Command - this will be removed
        >>> Map.clearMapCommands() # Clear map comands only and leave layers
        >>> Map.view()
        """
        self.mapCommandList = []

    ######################################################################
    def setMapTitle(self, title):
        """
        Set the title that appears in the left sidebar header and the page title

        Args:
            title (str, default geeViz Data Explorer): The title to appear in the header on the left sidebar as well as the title of the viewer webpage.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS")
        >>> Map.turnOnInspector()
        >>> Map.setMapTitle("<h2>A Custom Title!!!</h2>")  # Set custom map title
        >>> Map.view()
        """
        title_command = f'Map.setTitle("{title}")'
        if title_command not in self.mapCommandList:
            self.mapCommandList.append(title_command)

    ######################################################################
    def setTitle(self, title):
        """
        Redundant function for setMapTitle.
        Set the title that appears in the left sidebar header and the page title

        Args:
            title (str, default geeViz Data Explorer): The title to appear in the header on the left sidebar as well as the title of the viewer webpage.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS")
        >>> Map.turnOnInspector()
        >>> Map.setMapTitle("<h2>A Custom Title!!!</h2>")  # Set custom map title
        >>> Map.view()
        """
        self.setMapTitle(title)

    ######################################################################
    # Functions to set various click query properties
    def setQueryCRS(self, crs: str):
        """
        The coordinate reference system string to query layers with

        Args:
            crs (str, default "EPSG:5070"): Which projection (CRS) to use for querying map layers.

        >>> import geeViz.getImagesLib as gil
        >>> from geeViz.geeView import *
        >>> crs = gil.common_projections["NLCD_AK"]["crs"]
        >>> transform = gil.common_projections["NLCD_AK"]["transform"]
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="SEAK"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS")
        >>> Map.turnOnInspector()
        >>> Map.setQueryCRS(crs)
        >>> Map.setQueryTransform(transform)
        >>> Map.setCenter(-144.36390353, 60.20479529215, 8)
        >>> Map.view()
        """
        print("Setting click query crs to: {}".format(crs))
        cmd = f"Map.setQueryCRS('{crs}')"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryScale(self, scale: int):
        """
        What scale to query map layers with. Will also update the size of the box drawn on the map query layers are queried.

        Args:
            scale (int, default None): The spatial resolution to use for querying map layers in meters. If set, the query transform will be set to None in the map viewer.

        >>> import geeViz.getImagesLib as gil
        >>> from geeViz.geeView import *
        >>> s2s = gil.superSimpleGetS2(ee.Geometry.Point([-107.61, 37.85]), "2024-01-01", "2024-12-31", 190, 250)
        >>> projection = s2s.first().select(["nir"]).projection().getInfo()
        >>> Map.addLayer(s2s.median(), gil.vizParamsFalse10k, "Sentinel-2 Composite")
        >>> Map.turnOnInspector()
        >>> Map.setQueryCRS(projection["crs"])
        >>> Map.setQueryScale(projection["transform"][0])
        >>> Map.centerObject(s2s.first())
        >>> Map.view()

        """
        print("Setting click query scale to: {}".format(scale))
        cmd = f"Map.setQueryScale({scale})"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryTransform(self, transform: list[int]):
        """
        What transform to query map layers with. Will also update the size of the box drawn on the map query layers are queried.

        Args:
            transform (list, default [30, 0, -2361915, 0, -30, 3177735]): The snap to grid to use for querying layers on the map. If set, the query scale will be set to None in the map viewer.

        >>> import geeViz.getImagesLib as gil
        >>> from geeViz.geeView import *
        >>> s2s = gil.superSimpleGetS2(ee.Geometry.Point([-107.61, 37.85]), "2024-01-01", "2024-12-31", 190, 250)
        >>> projection = s2s.first().select(["nir"]).projection().getInfo()
        >>> Map.addLayer(s2s.median(), gil.vizParamsFalse10k, "Sentinel-2 Composite")
        >>> Map.turnOnInspector()
        >>> Map.setQueryCRS(projection["crs"])
        >>> Map.setQueryTransform(projection["transform"])
        >>> Map.centerObject(s2s.first())
        >>> Map.view()

        """
        print("Setting click query transform to: {}".format(transform))
        cmd = f"Map.setQueryTransform({transform})"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryPrecision(self, chartPrecision: int = 3, chartDecimalProportion: float = 0.25):
        """
        What level of precision to show for queried layers. This avoids showing too many digits after the decimal.

        Args:
            chartPrecision (int, default 3): Will show the larger of `chartPrecision` decimal places or ceiling(`chartDecimalProportion` * total decimal places). E.g. if the number is 1.12345678, 0.25 of 8 decimal places is 2, so 3 will be used and yield 1.123.
            chartDecimalProportion (float, default 0.25): Will show the larger of `chartPrecision` decimal places or `chartDecimalProportion` * total decimal places. E.g. if the number is 1.1234567891234, ceiling(0.25 of 13) decimal places is 4, so 4 will be used and yield 1.1235.

        >>> import geeViz.getImagesLib as gil
        >>> from geeViz.geeView import *
        >>> s2s = gil.superSimpleGetS2(ee.Geometry.Point([-107.61, 37.85]), "2024-01-01", "2024-12-31", 190, 250).select(["blue", "green", "red", "nir", "swir1", "swir2"])
        >>> projection = s2s.first().select(["nir"]).projection().getInfo()
        >>> s2s = s2s.map(lambda img: ee.Image(img).divide(10000).set("system:time_start",img.date().millis()))
        >>> Map.addLayer(s2s, gil.vizParamsFalse, "Sentinel-2 Images")
        >>> Map.addLayer(s2s.median(), gil.vizParamsFalse, "Sentinel-2 Composite")
        >>> Map.turnOnInspector()
        >>> Map.setQueryCRS(projection["crs"])
        >>> Map.setQueryTransform(projection["transform"])
        >>> Map.setQueryPrecision(chartPrecision=2, chartDecimalProportion=0.1)
        >>> Map.centerObject(s2s.first())
        >>> Map.view()
        """
        print("Setting click query precision to: {}".format(chartPrecision))
        cmd = f"Map.setQueryPrecision({chartPrecision},{chartDecimalProportion})"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryDateFormat(self, defaultQueryDateFormat: str = "YYYY-MM-dd"):
        """
        Set the date format to be used for any dates when querying.

        Args:
            defaultQueryDateFormat (str, default "YYYY-MM-dd"): The date format string to use for query outputs with dates. To simplify date outputs, "YYYY" is often used instead of the default.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.addLayer(lcms.select([0]), {"autoViz": True}, "LCMS Change")
        >>> Map.turnOnInspector()
        >>> Map.setQueryDateFormat("YYYY")
        >>> Map.view()

        """
        print("Setting default query date format to: {}".format(defaultQueryDateFormat))
        cmd = f'Map.setQueryDateFormat("{defaultQueryDateFormat}")'
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryBoxColor(self, color: str):
        """
        Set the color of the query box to something other than yellow

        Args:
            color (str, default "FFFF00"): Set the default query box color shown on the map by providing a hex color.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.setQueryBoxColor("0FF")
        >>> Map.view()
        """
        print("Setting click query box color to: {}".format(color))
        cmd = f'Map.setQueryBoxColor("{color}")'
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    # Functions to handle location of query outputs
    def setQueryWindowMode(self, mode):
        self.queryWindowMode = mode

    def setQueryToInfoWindow(self):
        """
        Set the location of query outputs to an info window popup over the map

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.setQueryToInfoWindow()
        >>> Map.view()
        """
        self.setQueryWindowMode("infoWindow")

    def setQueryToSidePane(self):
        """
        Set the location of query outputs to the right sidebar above the legend

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.setQueryToSidePane()
        >>> Map.view()
        """
        self.setQueryWindowMode("sidePane")

    ######################################################################
    # Turn on query inspector
    def turnOnInspector(self):
        """
        Turn on the query inspector tool upon map loading. This is used frequently so map layers can be queried as soon as the map viewer loads.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.view()
        """
        query_command = "Map.turnOnInspector()"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    # Turn on area charting
    def turnOnAutoAreaCharting(self):
        """
        Turn on automatic area charting upon map loading. This will automatically update charts by summarizing any visible layers with "canAreaChart" : True any time the map finishes panning or zooming.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True,'canAreaChart':True}, "LCMS Land Cover")
        >>> Map.turnOnAutoAreaCharting()
        >>> Map.view()
        """
        query_command = "Map.turnOnAutoAreaCharting()"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def turnOnUserDefinedAreaCharting(self):
        """
        Turn on area charting by a user defined area upon map loading. This will update charts by summarizing any visible layers with "canAreaChart" : True when the user draws an area to summarize and hits the `Chart Selected Areas` button in the user interface under `Area Tools -> User-Defined Area`.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True,'canAreaChart':True}, "LCMS Land Cover")
        >>> Map.turnOnUserDefinedAreaCharting()
        >>> Map.view()
        """
        query_command = "Map.turnOnUserDefinedAreaCharting()"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def turnOnSelectionAreaCharting(self):
        """
        Turn on area charting by a user selected area upon map loading. This will update charts by summarizing any visible layers with "canAreaChart" : True when the user selects selection areas to summarize and hits the `Chart Selected Areas` button in the user interface under `Area Tools -> Select an Area on Map`.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True,'canAreaChart':True}, "LCMS Land Cover")
        >>> mtbsBoundaries = ee.FeatureCollection("USFS/GTAC/MTBS/burned_area_boundaries/v1")
        >>> mtbsBoundaries = mtbsBoundaries.map(lambda f: f.set("system:time_start", f.get("Ig_Date")))
        >>> Map.addSelectLayer(mtbsBoundaries, {"strokeColor": "00F", "selectLayerNameProperty": "Incid_Name"}, "MTBS Fire Boundaries")
        >>> Map.turnOnSelectionAreaCharting()
        >>> Map.view()
        """
        query_command = "Map.turnOnSelectionAreaCharting()"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def addAreaChartLayer(self, image: ee.Image | ee.ImageCollection, params: dict = {}, name: str | None = None, shouldChart: bool = True):
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

                    "chartLabelMaxWidth" (int, default 40): The maximum number of characters, including spaces, allowed in a single line of a chart class label. The class name will be broken at this number of characters, including spaces, to go to the next line,

                    "chartLabelMaxLength" (int, default 100): The maximum number of characters, including spaces, allowed in a chart class label. Any class name with more characters, including spaces, than this number will be cut off at this number of characters,

                    "sankeyTransitionPeriods" (list of lists, default None): The years to use as transition periods for sankey charts (e.g. [[1985,1987],[2000,2002],[2020,2022]]). If not provided, users can enter years in the map user interface under `Area Tools -> Transition Charting Periods`. These will automatically be used for any layers where no sankeyTransitionPeriods were provided. If years are provided, the years in the user interface will not be used for that layer,

                    "sankeyMinPercentage" (float, default 0.5): The minimum percentage a given class has to be to be shown in the sankey chart,

                    "thematic" (bool): Whether input has discrete values or not. If True, it forces the reducer to `ee.Reducer.frequencyHistogram()` even if not specified and even if bandName_class_values, bandName_class_names, bandName_class_palette properties are not available,

                    "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart,

                    "showGrid" (bool, default True): Whether to show the grid lines on the line or bar graph,

                    "rangeSlider" (bool,default False): Whether to include the x-axis range selector on the bottom of each graph (`https://plotly.com/javascript/range-slider/>`),

                    "barChartMaxClasses" (int, default 20): The maximum number of classes to show for image bar charts. Will automatically only show the top `bartChartMaxClasses` in any image bar chart. Any downloaded csv table will still have all of the class counts,

                    "minZoomSpecifiedScale" (int, default 11): The map zoom level where any lower zoom level, not including this zoom level, will multiply the spatial resolution used for the zonal stats by 2 for each lower zoom level. E.g. if the `minZoomSpecifiedScale` is 9 and the `scale` is 30, any zoom level >= 9 will compute zonal stats at 30m spatial resolution. Then, at zoom level 8, it will be 60m. Zoom level 7 will be 120m, etc,

                    "chartPrecision" (int, default 3): Used to override the default global precision settings for a specific area charting layer. See `setQueryPrecision` for setting the global charting precision. When specified, for this specific area charting layer, will show the larger of `chartPrecision` decimal places or ceiling(`chartDecimalProportion` * total decimal places). E.g. if the number is 1.12345678, 0.25 of 8 decimal places is 2, so 3 will be used and yield 1.123,

                    "chartDecimalProportion" (float, default 0.25): Used to override the default global precision settings for a specific area charting layer. See `setQueryPrecision` for setting the global charting precision. When specified, for this specific area charting layer, will show the larger of `chartPrecision` decimal places or `chartDecimalProportion` * total decimal places. E.g. if the number is 1.1234567891234, ceiling(0.25 of 13) decimal places is 4, so 4 will be used and yield 1.1235,

                    "hovermode" (str, default "closest"): The mode to show hover text in area summary charts. Options include "closest", "x", "y", "x unified", and "y unified",

                    "yAxisLabel" (str, default an appropriate label based on whether data are thematic or continuous): The Y axis label that will be included in charts. Defaults to a unit of % area for thematic and mean for continuous data,

                    "chartType" (str, default "line" for `ee.ImageCollection` and "bar" for `ee.Image` objects): The type of chart to show. Options include "line", "bar", "stacked-line", and "stacked-bar". This is only used for `ee.ImageCollection` objects. For `ee.Image` objects, the chartType is always "bar".

                }
            name (str): Descriptive name for map layer that will be shown on the map UI
            shouldChart (bool, optional): Whether layer should be charted when map UI loads

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select(["Change_Raw_Probability.*"]), {"reducer": ee.Reducer.stdDev(), "min": 0, "max": 10}, "LCMS Change Prob")
        >>> Map.addAreaChartLayer(lcms, {"line": True, "layerType": "ImageCollection"}, "LCMS All Thematic Classes Line", True)
        >>> Map.addAreaChartLayer(lcms, {"sankey": True}, "LCMS All Thematic Classes Sankey", True)
        >>> Map.populateAreaChartLayerSelect()
        >>> Map.turnOnAutoAreaCharting()
        >>> Map.view()

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

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select(["Change_Raw_Probability.*"]), {"reducer": ee.Reducer.stdDev(), "min": 0, "max": 10}, "LCMS Change Prob")
        >>> Map.addAreaChartLayer(lcms, {"line": True, "layerType": "ImageCollection"}, "LCMS All Thematic Classes Line", True)
        >>> Map.addAreaChartLayer(lcms, {"sankey": True}, "LCMS All Thematic Classes Sankey", True)
        >>> Map.populateAreaChartLayerSelect()
        >>> Map.turnOnAutoAreaCharting()
        >>> Map.view()
        """
        query_command = "areaChart.populateChartLayerSelect()"

        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    # Functions to handle setting query output y labels
    def setYLabelMaxLength(self, maxLength: int):
        """
        Set the maximum length a Y axis label can have in charts

        Args:
            maxLength (int, default 30): Maximum number of characters in a Y axis label.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.setYLabelMaxLength(10)  # Double-click on map to inspect area. Change to a larger number and rerun to see how Y labels are impacted
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"yLabelMaxLength = {maxLength}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelBreakLength(self, maxLength: int):
        """
        Set the maximum length per line a Y axis label can have in charts

        Args:
            maxLength (int, default 10): Maximum number of characters in each line of a Y axis label. Will break total characters (setYLabelMaxLength) until maxLines (setYLabelMaxLines) is reached

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.setYLabelBreakLength(5)  # Double-click on map to inspect area. Change to a larger number and rerun to see how Y labels are impacted
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"yLabelBreakLength = {maxLength}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelMaxLines(self, maxLines):
        """
        Set the max number of lines each y-axis label can have.

        Args:
            maxLines (int, default 5): The maximum number of lines each y-axis label can have. Will simply exclude any remaining lines.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.setYLabelMaxLines(3)  # Double-click on map to inspect area. Change to a larger number and rerun to see how Y labels are impacted
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"yLabelMaxLines = {maxLines}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelFontSize(self, fontSize: int):
        """
        Set the size of the font on the y-axis labels. Useful when y-axis labels are too large to fit on the chart.

        Args:
            fontSize (int, default 10): The font size used on the y-axis labels for query charting.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.setYLabelFontSize(8)  # Double-click on map to inspect area. Change to a different number and rerun to see how Y labels are impacted
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"yLabelFontSize = {fontSize}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    # Specify whether layers can be re-ordered by the user
    def setCanReorderLayers(self, canReorderLayers: bool):
        """
        Set whether layers can be reordered by dragging layer user interface objects. By default all non timelapse and non geojson layers can be reordereed by dragging.

        Args:
            canReorderLayers (bool, default True): Set whether layers can be reordered by dragging layer user interface objects. By default all non timelapse and non geojson layers can be reordereed by dragging.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([2]), {"autoViz": True}, "LCMS Land Use")
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.addLayer(lcms.select([0]), {"autoViz": True}, "LCMS Change")
        >>> Map.turnOnInspector()
        >>> Map.setCanReorderLayers(False) # Notice you cannot drag and reorder layers. Change to True and rerun and notice you now can drag layers to reorder
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"Map.canReorderLayers = {str(canReorderLayers).lower()};"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    # Functions to handle batch layer toggling
    def turnOffAllLayers(self):
        """
        Turn off all layers added to the mapper object. Typically used in notebooks or iPython when you want to allow existing layers to remain, but want to turn them all off.

        >>> #%%
        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([2]), {"autoViz": True}, "LCMS Land Use")
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 5)
        >>> Map.view()
        >>> #%%
        >>> Map.turnOffAllLayers()
        >>> Map.addLayer(lcms.select([0]), {"autoViz": True}, "LCMS Change")
        >>> Map.view()
        """
        update = {"visible": "false"}
        self.idDictList = [{**d, **update} for d in self.idDictList]

    def turnOnAllLayers(self):
        """
        Turn on all layers added to the mapper object

        >>> #%%
        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("USFS/GTAC/LCMS/v2023-9").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([2]), {"autoViz": True}, "LCMS Land Use",False)
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover",False)
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 5)
        >>> Map.view()
        >>> #%%
        >>> Map.turnOnAllLayers()
        >>> Map.addLayer(lcms.select([0]), {"autoViz": True}, "LCMS Change")
        >>> Map.view()
        """
        update = {"visible": "true"}
        self.idDictList = [{**d, **update} for d in self.idDictList]


# Instantiate Map object
Map = mapper()
