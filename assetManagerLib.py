"""
   Copyright 2019 Leah Campbell

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Pieces of code were taken from: https://github.com/tracek/gee_asset_manager

"""

#--------------------------------------------------------------------------
#           ASSETMANAGERLIB.PY
#--------------------------------------------------------------------------

import sys, ee, os, shutil, subprocess, datetime, calendar, json
import time, logging, pdb
ee.Initialize()

taskLimit = 10

#############################################################################################
#               Functions to update ACL
#############################################################################################

#Function for updating ACL for a given GEE asset path
def updateACL(assetName,writers = [],all_users_can_read = True,readers = []):
    ee.data.setAssetAcl(assetName, json.dumps({u'writers': writers, u'all_users_can_read': all_users_can_read, u'readers': readers}))

#--------------------------------------------------------------------------------------------

#Function for updating all assets under a given folder level in GEE
def batchUpdateAcl(folder,writers = [],all_users_can_read = True,readers = []):
    allImages = walkFolders(folder)

    for image in allImages:
        print( 'Updating acl for:',image)
        try:
            updateACL(image,writers ,all_users_can_read ,readers)
        except:
            print( 'Could not update',image)

#############################################################################################
# Functions for copying, deleting, etc. assets
#############################################################################################
# outTypes = 'imageCollection' or 'tables'
def batchCopy(fromFolder,toFolder,outType = 'imageCollection'):

    if outType == 'imageCollection':
        create_image_collection(toFolder)
    elif outType == 'tables':
        verify_path(toFolder)

    if toFolder[-1] == '/':
        toFolder = toFolder[:-1]

    if outType == 'imageCollection':
        images = walkFolders(fromFolder)
    elif outType == 'tables':
        images = walkFoldersTables(fromFolder)
    #print( images)

    for image in images:
        out = toFolder +'/'+ base(image)
        print( out)
        try:
            ee.data.copyAsset(image,out)
        except:
            print( out,'Error: May already exist')

#---------------------------------------------------------------------------------------------

def moveImages(images,toFolder):
    create_image_collection(toFolder)
    for image in images:
        print ('Copying',base(image))
        out = toFolder + '/' + base(image)
        try:
            ee.data.copyAsset(image,out)
            #ee.data.deleteAsset(image)
        except:
            print (out,'already exists')

#---------------------------------------------------------------------------------------------
# types = 'imageCollection' or 'tables'
def batchDelete(Collection, type = 'imageCollection'):

    if type == 'imageCollection':
        images = walkFolders(Collection)
    elif type == 'tables':
        images = walkFoldersTables(Collection) 

    for image in images:
        print('Deleting: '+ Collection +'/'+ base(image))
        ee.data.deleteAsset(image)

#############################################################################################
#       Asset Info Queries
#############################################################################################

# Adapted from Samapriya Roy's assetsize.py (https://github.com/samapriya/Planet-GEE-Pipeline-CLI)
suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
def humansize(nbytes):
    i = 0
    while nbytes >= 1024 and i < len(suffixes)-1:
        nbytes /= 1024.
        i += 1
    f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])
l=[]
def assetsize(asset):
    header=ee.data.getInfo(asset)['type']
    if header=="ImageCollection":
        collc=ee.ImageCollection(asset)
        size=collc.aggregate_array('system:asset_size')
        print('')
        print(str(asset)+" ===> "+str(humansize(sum(size.getInfo()))))
        print('Total number of items in collection: '+str(collc.size().getInfo()))
    elif header=="Image":
        collc=ee.Image(asset)
        print('')
        print(str(asset)+" ===> "+str(humansize(collc.get('system:asset_size').getInfo())))
    elif header=="Table":
        collc=ee.FeatureCollection(asset)
        print('')
        print(str(asset)+" ===> "+str(humansize(collc.get('system:asset_size').getInfo())))
    elif header =="Folder":
        b=subprocess.check_output("earthengine du "+asset+" -s",shell=True)
        num=subprocess.check_output("earthengine ls "+asset,shell=True)
        size=humansize(float(b.strip().split(' ')[0]))
        print('')
        print(str(asset)+" ===> "+str(size))
        print('Total number of items in folder: '+str(len(num.split('\n'))-1))
if __name__ == '__main__':
    assetsize(None)
#############################################################################################
#       Functions to Upload to Google Cloud Storage and Google Earth Engine Repository
#############################################################################################
#Wrapper function to upload to google cloudStorage
#Bucket must already exist
def upload_to_gcs(image_dir,gs_bucket,image_extension = '.tif',copy_or_sync = 'copy'):
    if copy_or_sync == 'copy':
        call_str = 'gsutil.cmd -m cp "' + image_dir + '*'+image_extension+'" '+gs_bucket
    else:
        call_str = 'gsutil.cmd -m  rsync "' +   image_dir  + '" ' + gs_bucket
    print(call_str)
    call = subprocess.Popen(call_str)
    call.wait()
    
#---------------------------------------------------------------------------------------------
#Wrapper function for uploading GEE assets
def upload_to_gee(image_dir, gs_bucket,asset_dir,image_extension = '.tif', resample_method = 'MEAN',band_names = [],property_list = []):
    #First upload to GCS
    #upload_to_gcs(image_dir,gs_bucket,image_extension,'copy')

    #Make sure collection exists
    create_image_collection(asset_dir)

    #Get the names that need to be transferred form GCS to EE
    tifs = glob(image_dir,image_extension)

    #Set up the asset dir, files, and band names object
    asset_dir = check_end(asset_dir)
    gs_files = map(lambda i: gs_bucket+os.path.basename(i),tifs)
    band_names = map(lambda i:{'id':i},band_names)

    #Iterate through each file to upload
    i = 0
    for gs_file in gs_files:

        #Check to ensure the task limit (set globally) is not exceeded
        #Exporting can slow down if too many tasks are submitted
        limitTasks(taskLimit)

        #Export asset if it does not exist
        asset_name = asset_dir + base(gs_file)
        if not ee_asset_exists(asset_name):

            print('Importing asset:',asset_name)
            properties = property_list[i]

            #Set up sources
            sl ={"primaryPath": gs_file,
                                   "additionalPaths": []}
            #Set up request
            request = {"id": asset_name,
                          "tilesets": [
                              {"sources": [sl]}
                          ],

                          "bands": band_names,
                          'properties':properties,
                          "pyramidingPolicy": resample_method
                          }
            print(request)
            #Get a task id
            taskid = ee.data.newTaskId(1)[0]
            print(taskid)
            #Submit task
            message =ee.data.startIngestion(taskid, request)
            print('Task message:',message)
        else:
            print(asset_name,'already exists')
        i+=1

    #Keep track of tasks once they are all submitted
    task_count = countTasks(False)
    while task_count >= 1:
        running,ready = countTasks(True)
        print(running, 'tasks running at:',now())
        print(ready, 'tasks ready at:',now())
        task_count = running+ready
        time.sleep(5)

#############################################################################################
#               Helper Functions
##############################################################################################
#Function to ensure trailing / is in path
def check_end(in_path, add = '/'):
    if in_path[-len(add):] != add:
        out = in_path + add
    else:
        out = in_path
    return out
##############################################################################################
#Returns all files containing an extension or any of a list of extensions
#Can give a single extension or a list of extensions
def glob(Dir, extension):
    Dir = check_end(Dir)
    if type(extension) != list:
        if extension.find('*') == -1:
            return map(lambda i : Dir + i, filter(lambda i: os.path.splitext(i)[1] == extension, os.listdir(Dir)))
        else:
            return map(lambda i : Dir + i, os.listdir(Dir))
    else:
        out_list = []
        for ext in extension:
            tl = map(lambda i : Dir + i, filter(lambda i: os.path.splitext(i)[1] == ext, os.listdir(Dir)))
            for l in tl:
                out_list.append(l)
        return out_list
##############################################################################################
#Function to get filename without extension
def base(in_path):
    return os.path.basename(os.path.splitext(in_path)[0])
##############################################################################################

#################################################################
#Function to walk down folders and get all images
def walkFolders(folder,images = []):
    assets = ee.data.getList({'id':folder})
    folders = [str(i['id']) for i in assets if i['type'] == 'Folder']
    imagesT = [str(i['id']) for i in assets if i['type'] == 'Image']
    print(imagesT)
    for i in imagesT:
        if i not in images:
            images.append(i)
    iteration = 2
    while len(folders)>0:
        print('Starting iteration',iteration)
        for folder in folders:
            print(folder)
            assets = ee.data.getList({'id':folder})
            folders = [str(i['id']) for i in assets if i['type'] == 'Folder']
            imagesT = [str(i['id']) for i in assets if i['type'] == 'Image']
            for i in imagesT:
                if i not in images:
                    images.append(i)

        iteration+=1

    return images

#################################################################
#Function to walk down folders and get all tables
def walkFoldersTables(folder, tables = []):
    assets = ee.data.getList({'id':folder})
    folders = [str(i['id']) for i in assets if i['type'] == 'Folder']
    tablesT = [str(i['id']) for i in assets if i['type'] == 'Table']
    print(tablesT)
    for i in tablesT:
        if i not in tables:
            tables.append(i)
    iteration = 2
    while len(folders)>0:
        print('Starting iteration',iteration)
        for folder in folders:
            print(folder)
            assets = ee.data.getList({'id':folder})
            folders = [str(i['id']) for i in assets if i['type'] == 'Folder']
            tablesT = [str(i['id']) for i in assets if i['type'] == 'Table']
            for i in tablesT:
                if i not in tables:
                    tables.append(i)

        iteration+=1

    return tables
#################################################################
##############################################################################################
#Make sure the directory exists
def check_dir(in_path):
    if os.path.exists(in_path) == False:
        print('Making dir:', in_path)
        os.makedirs(in_path)
##############################################################################################
def year_month_day_to_seconds(year_month_day):

    ymd = year_month_day
    return calendar.timegm(datetime.datetime(ymd[0], ymd[1], ymd[2]).timetuple())
#######################################################################################
def limitTasks(taskLimit):
    taskCount = countTasks()
    while taskCount > taskLimit:
        running,ready = countTasks(True)
        print(running, 'tasks running at:',now())
        print(ready, 'tasks ready at:',now())
        taskCount = running+ready
        time.sleep(10)
#######################################################################################

def countTasks(break_running_ready = False):
    tasks = ee.data.getTaskList()
    running_tasks = len(filter(lambda i: i['state'] == 'RUNNING',tasks))
    ready_tasks = len(filter(lambda i: i['state'] == 'READY',tasks))
    if not break_running_ready:
        return running_tasks+ready_tasks
    else:
        return running_tasks,ready_tasks
#######################################################################################
#Adapted from: https://github.com/tracek/gee_asset_manager/blob/master/geebam/helper_functions.py
#Author: Lukasz Tracewski
def ee_asset_exists(path):
    return True if ee.data.getInfo(path) else False

#Adapted from: https://github.com/tracek/gee_asset_manager/blob/master/geebam/helper_functions.py
#Author: Lukasz Tracewski
def create_image_collection(full_path_to_collection):
    if ee_asset_exists(full_path_to_collection):
        print("Collection "+full_path_to_collection+" already exists")
    else:
        ee.data.createAsset({'type': ee.data.ASSET_TYPE_IMAGE_COLL}, full_path_to_collection)
        print('New collection '+full_path_to_collection+' created')

def verify_path(path):
    response = ee.data.getInfo(path)
    if not response:
        logging.error('%s is not a valid destination. Make sure full path is provided e.g. users/user/nameofcollection '
                      'or projects/myproject/myfolder/newcollection and that you have write access there.', path)
        sys.exit(1)
##############################################################################################
#Find whether image is a leap year
def is_leap_year(year):
    year = int(year)
    if year % 4 == 0:
        if year%100 == 0 and year % 400 != 0:
            return False
        else:
            return True
    else:
        return False
##############################################################################################
#Function to find current readable date/time
def now(Format = "%b %d %Y %H:%M:%S %a"):
##    import datetime
    today = datetime.datetime.today()
    s = today.strftime(Format)
    d = datetime.datetime.strptime(s, Format)
    return d.strftime(Format)
##############################################################################################
#Convert julian to calendar
def julian_to_calendar(julian_date, year):
    julian_date, year = int(julian_date), int(year)
    is_leap = is_leap_year(year)
    if is_leap:
        leap, length = True, [31,29,31,30,31,30,31,31,30,31,30,31]
    else:
        leap, length = False, [31,28,31,30,31,30,31,31,30,31,30,31]
    ranges = []
    start = 1
    for month in length:
        stop = start + month
        ranges.append(range(start, stop))
        start = start + month

    month_no = 1
    for Range in ranges:
        if julian_date in Range:
            mn = month_no
            day_no = 1
            for day in Range:
                if day == julian_date:
                    dn = day_no
                day_no += 1
        month_no += 1
    if len(str(mn)) == 1:
        lmn = '0' + str(mn)
    else:
        lmn = str(mn)
    if len(str(dn)) == 1:
        ldn = '0' + str(dn)
    else:
        ldn = str(dn)
    return [year,mn,dn]
##############################################################################################

