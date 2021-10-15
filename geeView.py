"""
   Copyright 2020 Ian Housman

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
#Script to allow GEE objects to be viewed in a web viewer
#Intended to work within the geeViz package
######################################################################
#Import modules
import ee,sys,os,webbrowser,json,socket,subprocess,site,time
from threading import Thread
from IPython.display import IFrame
if sys.version_info[0] < 3:
    import SimpleHTTPServer, SocketServer
else:
    import http.server, socketserver 
######################################################################
#Set up GEE and paths
try:
    z = ee.Number(1).getInfo()
except:
    print('Initializing GEE')
    ee.Initialize()

geeVizFolder = 'geeViz'
geeViewFolder = 'geeView'
#Set up template web viewer
#Do not change
cwd = os.getcwd()

paths = sys.path

gee_py_modules_dir = site.getsitepackages()[-1]

py_viz_dir = os.path.join(gee_py_modules_dir,geeVizFolder)
# os.chdir(py_viz_dir)
print('geeViz package folder:', py_viz_dir)

#Specify location of files to run
template = os.path.join(py_viz_dir,geeViewFolder,'index.html')
ee_run_dir =  os.path.join(py_viz_dir, geeViewFolder,'js')
if os.path.exists(ee_run_dir) == False:os.makedirs(ee_run_dir)
ee_run = os.path.join(ee_run_dir, 'runGeeViz.js')

#Specify port to run on
local_server_port = 8005    
######################################################################
######################################################################
#Functions
#Function for running local web server
def run_local_server(port = 8001):
    if sys.version[0] == '2':
        server_name = 'SimpleHTTPServer'
    else:
        server_name = 'http.server'
    # c = '"{}" -m {} -d "{}" {}'.format(sys.executable, server_name,py_viz_dir,str(local_server_port))
    cwd = os.getcwd()
    os.chdir(py_viz_dir)
    # print('cwd',os.getcwd())
    c = '"{}" -m {}  {}'.format(sys.executable, server_name,local_server_port)
    print('HTTP server command:',c)
    # call = 
    subprocess.Popen(c,shell = True)
    os.chdir(cwd)
    # print('cwd',os.getcwd())
    # call.wait()


#Function to see if port is active
def isPortActive(port = 8001):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)                                      #2 Second Timeout
    result = sock.connect_ex(('localhost',port))
    if result == 0:
        return True
    else:
        return False

#Set up map object
class mapper:
    def __init__(self):
        self.layerNumber = 1
        self.idDictList = []
        self.mapCommandList  = []

    #Function for adding a layer to the map
    def addLayer(self,image,viz = {},name= None,visible= True):
        if name == None:
            name = 'Layer '+str(self.layerNumber)
            self.layerNumber+=1
        print('Adding layer: ' +name)
        #Get the id and populate dictionary
        idDict = {}#image.getMapId()
        idDict['item'] = image.serialize()
        idDict['name'] = name 
        idDict['visible'] = str(visible).lower()
        idDict['viz'] = json.dumps(viz, sort_keys=False)
        idDict['function'] = 'addSerializedLayer'
        self.idDictList.append(idDict)

    #Function for adding a layer to the map
    def addTimeLapse(self,image,viz = {},name= None,visible= True):
        if name == None:
            name = 'Layer '+str(self.layerNumber)
            self.layerNumber+=1
        print('Adding layer: ' +name)
        #Get the id and populate dictionary
        idDict = {}#image.getMapId()
        idDict['item'] = image.serialize()
        idDict['name'] = name 
        idDict['visible'] = str(visible).lower()
        idDict['viz'] = json.dumps(viz, sort_keys=False)
        idDict['function'] = 'addSerializedTimeLapse'
        self.idDictList.append(idDict)

    #Function for centering on a GEE object that has a geometry
    def centerObject(self,feature):
        try:
            bounds = json.dumps(feature.geometry().bounds().getInfo())
        except Exception as e:
            bounds = json.dumps(feature.bounds().getInfo())
        command = 'synchronousCenterObject('+bounds+')'
        
        self.mapCommandList.append(command)
    #Function for launching the web map after all adding to the map has been completed
    def view(self,open_browser = True, open_iframe = False,iframe_height = 525):
        print('Starting webmap')

        #Set up js code to populate
        lines = "showMessage('Loading',staticTemplates.loadingModal);\nfunction runGeeViz(){\n"


        #Iterate across each map layer to add js code to
        for idDict in self.idDictList:
            t ="Map2.{}({},{},'{}',{});\n".format(idDict['function'],idDict['item'],idDict['viz'],idDict['name'],str(idDict['visible']).lower())
            lines += t
        
        lines += "setTimeout(function(){$('#close-modal-button').click();}, 2500);\n"

        #Iterate across each map command
        for mapCommand in self.mapCommandList:
            lines += mapCommand + '\n'

        lines+= "}"
        
        #Write out js file
        oo = open(ee_run,'w')
        oo.writelines(lines)
        oo.close()
        if not isPortActive(local_server_port):
            print('Starting local web server at: http://localhost:{}/{}/'.format(local_server_port,geeViewFolder))
            run_local_server(local_server_port)
            print('Done')
            # t = Thread(target = run_local_server,args = (local_server_port,))
            # t.start()

        else:
            print('Local web server at: http://localhost:{}/{}/ already serving.'.format(local_server_port,geeViewFolder))
            # print('Refresh browser instance')
        print('cwd',os.getcwd())
        if open_browser:
            webbrowser.open('http://localhost:{}/{}/'.format(local_server_port,geeViewFolder),new = 1)
        if open_iframe:
            self.IFrame = IFrame(src='http://localhost:{}/{}/'.format(local_server_port,geeViewFolder), width='100%', height='{}px'.format(iframe_height))
    def clearMap(self):
        self.layerNumber = 1
        self.idDictList = []
        self.mapCommandList  = []
    
    def turnOnInspector(self):
        # self.mapCommandList.append("$('#tools-collapse-div').addClass('show')")
        query_command = "$('#query-label').click();"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append("$('#query-label').click();")
        
    def turnOffAllLayers(self):
        update = {'visible':'false'}
        self.idDictList = [{**d,**update} for d in self.idDictList]
    def turnOnAllLayers(self):
        update = {'visible':'true'}
        self.idDictList = [{**d,**update} for d in self.idDictList]
#Instantiate Map object
Map = mapper()
