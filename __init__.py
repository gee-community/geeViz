# ********************Initializes system paths for module imports******************************
# Function to find paths for modules:
# This uses a .txt file that MUST be kept at C:\Users\your_local_username\lcms_code_locations.txt
# that lists the paths to append.
# e.g. module_list = ['gee_modules','lcms']
def findPaths(module_list):
    module_dict = {}
    username = os.getcwd().split('\\')[2]
    with open('C:\\Users\\'+username+'\\lcms_code_locations.txt') as f:
        for line in f:
            for mod in module_list:
               if line.split('=')[0].strip(' ') == mod:
                   module_dict[mod] = line.split('=')[1].strip(' ').strip('\n')
    return module_dict

import ee, sys, os
ee.Initialize()
module_list = ['gee_py_modules','lcms_scripts']
module_dict = findPaths(module_list)
sys.path.append(module_dict['gee_py_modules'])
sys.path.append(module_dict['lcms_scripts'])