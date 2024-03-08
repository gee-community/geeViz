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

IS_COLAB = ee.oauth._in_colab_shell()  # "google.colab" in sys.modules
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
# Function to check if being run inside a notebook
# Taken from: https://stackoverflow.com/questions/15411967/how-can-i-check-if-code-is-executed-in-the-ipython-notebook
def is_notebook():
    return ee.oauth._in_jupyter_shell()
    # try:
    #     shell = get_ipython().__class__.__name__
    #     if shell == 'ZMQInteractiveShell':
    #         return True   # Jupyter notebook or qtconsole
    #     elif shell == 'TerminalInteractiveShell':
    #         return False  # Terminal running IPython
    #     else:
    #         return False  # Other type (?)
    # except NameError:
    #     return False      # Probably standard Python interpreter


######################################################################
# Function for cleaning trailing .... in accessToken
def cleanAccessToken(accessToken):
    while accessToken[-1] == ".":
        accessToken = accessToken[:-1]
    return accessToken


# Function to get domain base without any folders
def baseDomain(url):
    url_parts = urlparse(url)
    return f"{url_parts.scheme}://{url_parts.netloc}"


# Function for using default GEE refresh token to get an access token for geeView
# Updated 12/23 to reflect updated auth methods for GEE
def refreshToken():
    credentials = ee.data.get_persistent_credentials()
    credentials.refresh(gReq.Request())
    accessToken = credentials.token
    # print(credentials.to_json())
    accessToken = cleanAccessToken(accessToken)
    return accessToken


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


# Function to see if port is active
def isPortActive(port=8001):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)  # 2 Second Timeout
    result = sock.connect_ex(("localhost", port))
    if result == 0:
        return True
    else:
        return False


# Set up map object
class mapper:
    def __init__(self, port=8001):
        self.port = port
        self.layerNumber = 1
        self.idDictList = []
        self.mapCommandList = []
        self.ee_run_name = "runGeeViz"

        self.isNotebook = ee.oauth._in_jupyter_shell()
        self.isColab = ee.oauth._in_colab_shell()  # "google.colab" in sys.modules

        self.proxy_url = None

        self.refreshTokenPath = ee.oauth.get_credentials_path()
        self.serviceKeyPath = None
        self.queryWindowMode = "sidePane"
        self.project = project_id

    # Function for adding a layer to the map
    def addLayer(self, image, viz={}, name=None, visible=True):
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding layer: " + name)

        # Handle reducer if ee object is given
        if "reducer" in viz.keys():
            # if str(type(viz['reducer']))=="<class 'ee.Reducer'>":
            #     viz['reducer'] = eval(viz['reducer'])

            try:
                viz["reducer"] = viz["reducer"].serialize()
            except Exception as e:
                try:
                    viz["reducer"] = eval(viz["reducer"]).serialize()
                except Exception as e:  # Most likely it's already serialized
                    e = e
        # Get the id and populate dictionary
        idDict = {}
        if not isinstance(image, dict):
            image = image.serialize()
            idDict["item"] = image
            idDict["function"] = "addSerializedLayer"
        # Handle passing in geojson vector layers
        else:
            idDict["item"] = image
            viz["layerType"] = "geoJSONVector"
            idDict["function"] = "addLayer"

        idDict["name"] = name
        idDict["visible"] = str(visible).lower()
        idDict["viz"] = json.dumps(viz, sort_keys=False)

        self.idDictList.append(idDict)

    # Function for adding a layer to the map
    def addTimeLapse(self, image, viz={}, name=None, visible=True):
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding layer: " + name)

        # Handle reducer if ee object is given - delete it
        if "reducer" in viz.keys():
            del viz["reducer"]
        # Get the id and populate dictionary
        idDict = {}  # image.getMapId()
        idDict["item"] = image.serialize()
        idDict["name"] = name
        idDict["visible"] = str(visible).lower()
        idDict["viz"] = json.dumps(viz, sort_keys=False)
        idDict["function"] = "addSerializedTimeLapse"
        self.idDictList.append(idDict)

    # Function for setting the map zoom
    def setZoom(self, zoom):
        self.mapCommandList.append(f"map.setZoom({zoom})")

    # Function for centering on a GEE object that has a geometry
    def centerObject(self, feature, zoom=None):
        try:
            bounds = json.dumps(feature.geometry().bounds(100, "EPSG:4326").getInfo())
        except Exception as e:
            bounds = json.dumps(feature.bounds(100, "EPSG:4326").getInfo())
        command = "synchronousCenterObject(" + bounds + ")"

        self.mapCommandList.append(command)

        if zoom != None:
            self.setZoom(zoom)

    # Function for launching the web map after all adding to the map has been completed
    def view(self, open_browser=None, open_iframe=None, iframe_height=525):
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
            t = "Map.{}({},{},'{}',{});".format(
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

    def clearMap(self):
        self.layerNumber = 1
        self.idDictList = []
        self.mapCommandList = []

    def setMapTitle(self, title):
        title_command = f'Map.setTitle("{title}")'
        if title_command not in self.mapCommandList:
            self.mapCommandList.append(title_command)

    def setTitle(self, title):
        self.setMapTitle(title)

    # Functions to set various click query properties
    def setQueryCRS(self, crs):
        print("Setting click query crs to: {}".format(crs))
        cmd = f'Map.setQueryCRS("{crs}");'
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    def setQueryScale(self, scale):
        print("Setting click query scale to: {}".format(scale))
        cmd = f"Map.setQueryScale({scale});"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    def setQueryTransform(self, transform):
        print("Setting click query transform to: {}".format(transform))
        cmd = f"Map.setQueryTransform({transform});"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    def setQueryPrecision(self, chartPrecision=3, chartDecimalProportion=0.25):
        print("Setting click query precision to: {}".format(chartPrecision))
        cmd = f"Map.setQueryPrecision({chartPrecision},{chartDecimalProportion});"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    def setQueryDateFormat(self, defaultQueryDateFormat="YYYY-MM-dd"):
        print("Setting default query date format to: {}".format(defaultQueryDateFormat))
        cmd = f'Map.setQueryDateFormat("{defaultQueryDateFormat}");'
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    def setQueryBoxColor(self, color):
        print("Setting click query box color to: {}".format(color))
        cmd = f'Map.setQueryBoxColor("{color}");'
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    # Functions to handle location of query outputs
    def setQueryWindowMode(self, mode):
        self.queryWindowMode = mode

    def setQueryToInfoWindow(self):
        self.setQueryWindowMode("infoWindow")

    def setQueryToSidePane(self):
        self.setQueryWindowMode("sidePane")

    # Turn on query inspector
    def turnOnInspector(self):
        query_command = "Map.turnOnInspector();"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    # Turn on area charting
    def turnOnAutoAreaCharting(self):
        query_command = "Map.turnOnAutoAreaCharting();"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def turnOnUserDefinedAreaCharting(self):
        query_command = "Map.turnOnUserDefinedAreaCharting();"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def turnOnSelectionAreaCharting(self):
        query_command = "Map.turnOnSelectionAreaCharting();"
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
        command = f"yLabelMaxLines = {maxLines}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelFontSize(self, fontSize):
        command = f"yLabelFontSize = {fontSize}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    # Specify whether layers can be re-ordered by the user
    def setCanReorderLayers(self, canReorderLayers):
        command = f"Map.canReorderLayers = {str(canReorderLayers).lower()};"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    # Functions to handle batch layer toggling
    def turnOffAllLayers(self):
        update = {"visible": "false"}
        self.idDictList = [{**d, **update} for d in self.idDictList]

    def turnOnAllLayers(self):
        update = {"visible": "true"}
        self.idDictList = [{**d, **update} for d in self.idDictList]


# Instantiate Map object
Map = mapper()


# print(ee.data._initialized  )
# ee.Authenticate(auth_mode='localhost')
# ee.Authenticate(force=True)

# ee.Authenticate()
# ee.Initialize()#project='lcms-292214')
# ee.data.setCloudApiUserProject('rcr-gee')

# # ee.Initialize()
# print(ee.data._cloud_api_user_project  )
# print(refreshToken())
# f = ee.FeatureCollection('projects/rcr-gee-2/assets/test/DAMAGE_AREAS_FLAT_AllYears_CONUS_Rgn9')
# print(ee.Image().getInfo())
# Map.addLayer(f,{'palette':'F00'})
# Map.turnOnInspector()
