import ee
import sys,os,webbrowser,json,socket,subprocess
from threading import Thread
if sys.version_info[0] < 3:
    import SimpleHTTPServer, SocketServer
else:
    import http.server, socketserver 


ee.Initialize()

#Set up template web viewer
#Do not change
cwd = os.getcwd()

template = cwd+'/gee-py-viz/index.html'
ee_run = cwd +'/gee-py-viz/ee/run2.js'
local_server_port = 8004



#Function for running local web server
def run_local_server(port = 8001):
    # socketserver.TCPServer.allow_reuse_address = True # required for fast reuse ! 
    # """
    # Check out :
    # https://stackoverflow.com/questions/15260558/python-tcpserver-address-already-in-use-but-i-close-the-server-and-i-use-allow
    # """
    # Handler = httpserver.SimpleHTTPRequestHandler
    # httpd = socketserver.TCPServer(("", port), Handler)
    # print("Creating server at port", port)
    # httpd.serve_forever()
    if sys.version[0] == '2':
        subprocess.Popen('python -m SimpleHTTPServer '+str(local_server_port),shell = True)
    else:
        
        subprocess.Popen('python -m http.server '+str(local_server_port),shell = True)
def isPortActive(port = 8001):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)                                      #2 Second Timeout
    result = sock.connect_ex(('localhost',port))
    if result == 0:
        return True
    else:
        return False
class mapper:
    def __init__(self):
        self.layerNumber = 1
        self.idDictList = []
    #Function for adding a layer to the map
    def addLayer(self,image,viz = {},name= None,visible= True):
        
        

        # if viz != None:
        #     image = image.visualize(**viz)
        # else:

            # viz = {};
        if name == None:
            name = 'Layer '+str(self.layerNumber)
            self.layerNumber+=1
        print('Adding layer: ' +name)
        #Get the id and populate dictionary
        idDict = {}#image.getMapId()
        idDict['item'] = image.serialize()
        idDict['name'] = name
        idDict['visible'] = str(visible).lower()
        idDict['viz'] = json.dumps(viz)
        self.idDictList.append(idDict)


    #Function for launching the web map after all adding to the map has been completed
    def launchGEEVisualization(self):
        print('Starting webmap')

        #Set up js code to populate
        lines = "function run(){\n"


        #Iterate across each map layer to add js code to
        for idDict in self.idDictList:
            t ="addSerializedRasterToMap('"+idDict['item']+"',"+idDict['viz']+",'"+idDict['name']+"',"+str(idDict['visible']).lower()+");\n"
            lines += t
        lines += "}"

        #Write out js file
        oo = open(ee_run,'w')
        oo.writelines(lines)
        oo.close()
        # print 'Open web browser to http://localhost:'+str(local_server_port) + '/template/'
        if not isPortActive(local_server_port):
            print('Starting local web server at: http://localhost:'+str(local_server_port)+ '/gee-py-viz/')
            # run_local_server(local_server_port)
            # subprocess.Popen('python -m SimpleHTTPServer '+str(local_server_port),shell = True)
            t = Thread(target = run_local_server,args = (local_server_port,))
            t.start()

        else:
            print('Local web server at: http://localhost:'+str(local_server_port)+'/gee-py-viz/ already serving.')
            print('Refresh browser instance')
        webbrowser.open('http://localhost:'+str(local_server_port)+'/gee-py-viz/',new = 1)
        
    def clearMap(self):
        self.idDictList = []
    


Map = mapper()
