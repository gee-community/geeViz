"""
Helpful functions for managing GEE assets

geeViz.assetManagerLib includes functions for copying, deleting, uploading, changing permissions, and more.
"""

"""
   Copyright 2025 Leah Campbell, Ian Housman, Nicholas Storey

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

# --------------------------------------------------------------------------
#           ASSETMANAGERLIB.PY
# --------------------------------------------------------------------------
# %%
import geeViz.geeView
import sys, ee, os, shutil, subprocess, datetime, calendar, json, glob
import time, logging, pdb

taskLimit = 10
# %%
#############################################################################################
#               Functions to update ACL
#############################################################################################


def updateACL(assetName, writers=[], all_users_can_read=True, readers=[]):
    """
    Updates the Access Control List (ACL) for a given GEE asset.

    Args:
        assetName (str): The name of the GEE asset.
        writers (list, optional): List of users with write access. Defaults to an empty list.
        all_users_can_read (bool, optional): Whether all users can read the asset. Defaults to True.
        readers (list, optional): List of users with read access. Defaults to an empty list.

    Returns:
        None

    Example:
        >>> updateACL('users/youruser/yourasset', writers=['user1'], all_users_can_read=False, readers=['user2'])
    """
    print("Updating permissions for: ", assetName)
    try:
        ee.data.setAssetAcl(
            assetName,
            json.dumps(
                {
                    "writers": writers,
                    "all_users_can_read": all_users_can_read,
                    "readers": readers,
                }
            ),
        )
    except Exception as E:
        print("Could not update permissions for: ", assetName)
        print(E)


def listAssets(folder: str) -> list[str]:
    """
    Lists assets within a given asset folder or image collection.

    Args:
        folder (str): The path to the asset folder or image collection.

    Returns:
        list[str]: A list of asset IDs within the specified folder.

    Example:
        >>> listAssets('users/youruser/yourfolder')
    """
    return [i["id"] for i in ee.data.listAssets({"parent": folder})["assets"]]


def batchUpdateAcl(folder, writers=[], all_users_can_read=True, readers=[]):
    """
    Updates the ACL for all assets under a given folder in GEE.

    Args:
        folder (str): The path to the folder in GEE.
        writers (list, optional): List of users with write access. Defaults to an empty list.
        all_users_can_read (bool, optional): Whether all users can read the assets. Defaults to True.
        readers (list, optional): List of users with read access. Defaults to an empty list.

    Returns:
        None

    Example:
        >>> batchUpdateAcl('users/youruser/yourfolder', writers=['user1'], all_users_can_read=False)
    """
    assets = ee.data.listAssets({"parent": folder})["assets"]
    folders = [a for a in assets if a["type"] == "FOLDER"]
    for subFolder in folders:
        print("Updating acl for:", subFolder)
        try:
            updateACL(subFolder["id"], writers, all_users_can_read, readers)
        except:
            print("Could not update", subFolder)

    allImages = walkFolders(folder)
    for image in allImages:
        print("Updating acl for:", image)
        try:
            updateACL(image, writers, all_users_can_read, readers)
        except:
            print("Could not update", image)


#############################################################################################
# Functions for copying, deleting, etc. assets
#############################################################################################


def batchCopy(fromFolder, toFolder, outType="imageCollection"):
    """
    Copies all assets from one folder to another in GEE.

    Args:
        fromFolder (str): The source folder path.
        toFolder (str): The destination folder path.
        outType (str, optional): The type of assets to copy ('imageCollection' or 'tables'). Defaults to 'imageCollection'.

    Returns:
        None

    Example:
        >>> batchCopy('users/youruser/source', 'users/youruser/dest')
    """
    if outType == "imageCollection":
        create_image_collection(toFolder)
    elif outType == "tables":
        verify_path(toFolder)

    if toFolder[-1] == "/":
        toFolder = toFolder[:-1]

    if outType == "imageCollection":
        images = walkFolders(fromFolder)
    elif outType == "tables":
        images = walkFoldersTables(fromFolder)

    for image in images:
        out = toFolder + "/" + base(image)
        if not ee_asset_exists(out):
            print("Copying: ", image)
            try:
                ee.data.copyAsset(image, out)
            except Exception as E:
                print("Could not copy: ", image)
                print(E)
        else:
            print(out, " already exists")


def copyByName(fromFolder, toFolder, nameIdentifier, outType="imageCollection"):
    """
    Copies assets from one folder to another based on a name identifier.

    Args:
        fromFolder (str): The source folder path.
        toFolder (str): The destination folder path.
        nameIdentifier (str): A substring to identify assets to copy.
        outType (str, optional): The type of assets to copy ('imageCollection' or 'tables'). Defaults to 'imageCollection'.

    Returns:
        None

    Example:
        >>> copyByName('users/youruser/source', 'users/youruser/dest', '2020')
    """
    if outType == "imageCollection":
        create_image_collection(toFolder)
    elif outType == "tables":
        verify_path(toFolder)

    if toFolder[-1] == "/":
        toFolder = toFolder[:-1]

    if outType == "imageCollection":
        images = walkFolders(fromFolder)
    elif outType == "tables":
        images = walkFoldersTables(fromFolder)

    for image in images:
        if nameIdentifier in image:
            out = toFolder + "/" + base(image)
            print(out)
            try:
                ee.data.copyAsset(image, out)
            except:
                print(out, "Error: May already exist")


def moveImages(images, toFolder, delete_original=False):
    """
    Moves images to a new folder, optionally deleting the originals.

    Args:
        images (list): List of image paths to move.
        toFolder (str): The destination folder path.
        delete_original (bool, optional): Whether to delete the original images. Defaults to False.

    Returns:
        None

    Example:
        >>> moveImages(['users/youruser/img1', 'users/youruser/img2'], 'users/youruser/dest', delete_original=True)
    """
    create_image_collection(toFolder)
    for image in images:
        print("Copying", base(image))
        out = toFolder + "/" + base(image)
        if not ee_asset_exists(out):
            try:
                ee.data.copyAsset(image, out)
                if delete_original:
                    ee.data.deleteAsset(image)
            except Exception as E:
                print("Error copying:", image)
                print(E)


def batchDelete(Collection, type="imageCollection"):
    """
    Deletes all assets in a collection.

    Args:
        Collection (str): The path to the collection.
        type (str, optional): The type of assets to delete ('imageCollection' or 'tables'). Defaults to 'imageCollection'.

    Returns:
        None

    Example:
        >>> batchDelete('users/youruser/collection')
    """
    if type == "imageCollection":
        images = walkFolders(Collection)
    elif type == "tables":
        images = walkFoldersTables(Collection)

    for image in images:
        print("Deleting: " + Collection + "/" + base(image))
        try:
            ee.data.deleteAsset(image)
        except Exception as E:
            print("Could not delete: ", image)
            print(E)


def deleteByName(Collection, nameIdentifier, type="imageCollection"):
    """
    Deletes assets in a collection based on a name identifier.

    Args:
        Collection (str): The path to the collection.
        nameIdentifier (str): A substring to identify assets to delete.
        type (str, optional): The type of assets to delete ('imageCollection' or 'tables'). Defaults to 'imageCollection'.

    Returns:
        None

    Example:
        >>> deleteByName('users/youruser/collection', '2020')
    """
    if type == "imageCollection":
        images = walkFolders(Collection)
    elif type == "tables":
        images = walkFoldersTables(Collection)

    for image in images:
        if nameIdentifier in image:
            print("Deleting: " + Collection + "/" + base(image))
            try:
                ee.data.deleteAsset(image)
            except Exception as E:
                print("Could not delete: ", image)
                print(E)


#############################################################################################
#       Asset Info Queries
#############################################################################################

suffixes = ["B", "KB", "MB", "GB", "TB", "PB"]


def humansize(nbytes):
    """
    Converts a file size in bytes to a human-readable format.

    Args:
        nbytes (int): The size in bytes.

    Returns:
        str: The human-readable file size.

    Example:
        >>> humansize(1048576)
        '1 MB'
    """
    i = 0
    while nbytes >= 1024 and i < len(suffixes) - 1:
        nbytes /= 1024.0
        i += 1
    f = ("%.2f" % nbytes).rstrip("0").rstrip(".")
    return "%s %s" % (f, suffixes[i])


def assetsize(asset):
    """
    Prints the size of a GEE asset.

    Args:
        asset (str): The path to the GEE asset.

    Returns:
        None

    Example:
        >>> assetsize('users/youruser/yourasset')
    """
    header = ee.data.getInfo(asset)["type"]
    if header == "IMAGE_COLLECTION":
        collc = ee.ImageCollection(asset)
        size = collc.aggregate_array("system:asset_size")
        print("")
        print(str(asset) + " ===> " + str(humansize(sum(size.getInfo()))))
        print("Total number of items in collection: " + str(collc.size().getInfo()))
    elif header == "IMAGE":
        collc = ee.Image(asset)
        print("")
        print(str(asset) + " ===> " + str(humansize(collc.get("system:asset_size").getInfo())))
    elif header == "TABLE":
        collc = ee.FeatureCollection(asset)
        print("")
        print(str(asset) + " ===> " + str(humansize(collc.get("system:asset_size").getInfo())))
    elif header == "FOLDER":
        b = subprocess.check_output("earthengine du " + asset + " -s", shell=True)
        num = subprocess.check_output("earthengine ls " + asset, shell=True)
        size = humansize(float(b.strip().split(" ")[0]))
        print("")
        print(str(asset) + " ===> " + str(size))
        print("Total number of items in folder: " + str(len(num.split("\n")) - 1))


#############################################################################################
#       Functions to Upload to Google Cloud Storage and Google Earth Engine Repository
#############################################################################################


def upload_to_gcs(image_dir, gs_bucket, image_extension=".tif", copy_or_sync="copy", overwrite=False):
    """
    Uploads files to Google Cloud Storage.

    Args:
        image_dir (str): The directory containing the images to upload.
        gs_bucket (str): The GCS bucket to upload to.
        image_extension (str, optional): The file extension of the images. Defaults to '.tif'.
        copy_or_sync (str, optional): Whether to copy or sync files ('copy' or 'sync'). Defaults to 'copy'.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to False.

    Returns:
        None

    Example:
        >>> upload_to_gcs('/tmp/images/', 'gs://mybucket')
    """
    if gs_bucket.find("gs://") == -1:
        gs_bucket = f"gs://{gs_bucket}"
    overwrite_str = "-n "
    if overwrite:
        overwrite_str = ""
    if copy_or_sync == "copy":
        call_str = f'gsutil.cmd -m cp {overwrite_str}"{image_dir}*{image_extension}" {gs_bucket}'
    else:
        call_str = f'gsutil.cmd -m rsync {overwrite_str}"{image_dir}" {gs_bucket}'
    print(call_str)
    call = subprocess.Popen(call_str)
    call.wait()


def uploadTifToGCS(tif, gcsBucket, overwrite=False):
    """
    Uploads a single TIFF file to Google Cloud Storage.

    Args:
        tif (str): The path to the TIFF file.
        gcsBucket (str): The GCS bucket to upload to.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to False.

    Returns:
        None

    Example:
        >>> uploadTifToGCS('/tmp/image.tif', 'gs://mybucket')
    """
    if gcsBucket[-1] == '/':
        gcsBucket = gcsBucket[:-1]
    if gcsBucket.find("gs://") == -1:
        gcsBucket = f"gs://{gcsBucket}"

    overwrite_str = "-n"
    if overwrite:
        overwrite_str = ""

    uploadCommand = f'gcloud storage cp {tif} {gcsBucket} {overwrite_str}'
    call = subprocess.Popen(uploadCommand, shell=True)
    call.wait()


def upload_to_gee(
    image_dir,
    gs_bucket,
    asset_dir,
    image_extension=".tif",
    resample_method="MEAN",
    band_names=[],
    property_list=[],
):
    """
    Uploads images to Google Earth Engine.

    Args:
        image_dir (str): The directory containing the images to upload.
        gs_bucket (str): The GCS bucket to upload to.
        asset_dir (str): The GEE asset directory.
        image_extension (str, optional): The file extension of the images. Defaults to '.tif'.
        resample_method (str, optional): The resampling method. Defaults to 'MEAN'.
        band_names (list, optional): List of band names. Defaults to an empty list.
        property_list (list, optional): List of properties for the images. Defaults to an empty list.

    Returns:
        None

    Example:
        >>> upload_to_gee('/tmp/images/', 'gs://mybucket', 'users/youruser/yourcollection')
    """
    create_image_collection(asset_dir)
    tifs = glob.glob(os.path.join(image_dir, image_extension))
    asset_dir = check_end(asset_dir)
    gs_files = map(lambda i: gs_bucket + os.path.basename(i), tifs)
    band_names = map(lambda i: {"id": i}, band_names)

    i = 0
    for gs_file in gs_files:
        limitTasks(taskLimit)
        asset_name = asset_dir + base(gs_file)
        if not ee_asset_exists(asset_name):
            print("Importing asset:", asset_name)
            properties = property_list[i]
            sl = {"primaryPath": gs_file, "additionalPaths": []}
            request = {
                "id": asset_name,
                "tilesets": [{"sources": [sl]}],
                "bands": band_names,
                "properties": properties,
                "pyramidingPolicy": resample_method,
            }
            print(request)
            taskid = ee.data.newTaskId(1)[0]
            print(taskid)
            message = ee.data.startIngestion(taskid, request)
            print("Task message:", message)
        else:
            print(asset_name, "already exists")
        i += 1

    task_count = countTasks(False)
    while task_count >= 1:
        running, ready = countTasks(True)
        print(running, "tasks running at:", now())
        print(ready, "tasks ready at:", now())
        task_count = running + ready
        time.sleep(5)


#############################################################################################
#               Helper Functions
##############################################################################################


def check_end(in_path, add="/"):
    """
    Ensures a trailing character is in the path.

    Args:
        in_path (str): The input path.
        add (str, optional): The character to add. Defaults to '/'.

    Returns:
        str: The modified path.

    Example:
        >>> check_end('users/youruser/collection')
        'users/youruser/collection/'
    """
    if in_path[-len(add) :] != add:
        out = in_path + add
    else:
        out = in_path
    return out


def base(in_path):
    """
    Gets the filename without extension.

    Args:
        in_path (str): The input path.

    Returns:
        str: The filename without extension.

    Example:
        >>> base('/tmp/image.tif')
        'image'
    """
    return os.path.basename(os.path.splitext(in_path)[0])


def walkFolders(folder, images=[]):
    """
    Walks down folders and gets all images.

    Args:
        folder (str): The folder path.
        images (list, optional): List of images. Defaults to an empty list.

    Returns:
        list: List of image paths.

    Example:
        >>> walkFolders('users/youruser/collection')
    """
    assets = ee.data.getList({"id": folder})
    folders = [str(i["id"]) for i in assets if i["type"] == "Folder"]
    imagesT = [str(i["id"]) for i in assets if i["type"] == "Image"]
    print(imagesT)
    for i in imagesT:
        if i not in images:
            images.append(i)
    iteration = 2
    while len(folders) > 0:
        print("Starting iteration", iteration)
        for folder in folders:
            print(folder)
            assets = ee.data.getList({"id": folder})
            folders = [str(i["id"]) for i in assets if i["type"] == "Folder"]
            imagesT = [str(i["id"]) for i in assets if i["type"] == "Image"]
            for i in imagesT:
                if i not in images:
                    images.append(i)

        iteration += 1

    return images


def walkFoldersTables(folder, tables=[]):
    """
    Walks down folders and gets all tables.

    Args:
        folder (str): The folder path.
        tables (list, optional): List of tables. Defaults to an empty list.

    Returns:
        list: List of table paths.

    Example:
        >>> walkFoldersTables('users/youruser/collection')
    """
    assets = ee.data.getList({"id": folder})
    folders = [str(i["id"]) for i in assets if i["type"] == "Folder"]
    tablesT = [str(i["id"]) for i in assets if i["type"] == "Table"]
    print(tablesT)
    for i in tablesT:
        if i not in tables:
            tables.append(i)
    iteration = 2
    while len(folders) > 0:
        print("Starting iteration", iteration)
        for folder in folders:
            print(folder)
            assets = ee.data.getList({"id": folder})
            folders = [str(i["id"]) for i in assets if i["type"] == "Folder"]
            tablesT = [str(i["id"]) for i in assets if i["type"] == "Table"]
            for i in tablesT:
                if i not in tables:
                    tables.append(i)

        iteration += 1

    return tables


def check_dir(in_path):
    """
    Ensures the directory exists.

    Args:
        in_path (str): The directory path.

    Returns:
        None

    Example:
        >>> check_dir('/tmp/mydir')
    """
    if os.path.exists(in_path) == False:
        print("Making dir:", in_path)
        os.makedirs(in_path)


def year_month_day_to_seconds(year_month_day):
    """
    Converts a date to seconds since epoch.

    Args:
        year_month_day (list): List containing year, month, and day.

    Returns:
        int: Seconds since epoch.

    Example:
        >>> year_month_day_to_seconds([2020, 1, 1])
    """
    ymd = year_month_day
    return calendar.timegm(datetime.datetime(ymd[0], ymd[1], ymd[2]).timetuple())


def limitTasks(taskLimit):
    """
    Limits the number of tasks running.

    Args:
        taskLimit (int): The maximum number of tasks.

    Returns:
        None

    Example:
        >>> limitTasks(10)
    """
    taskCount = countTasks()
    while taskCount > taskLimit:
        running, ready = countTasks(True)
        print(running, "tasks running at:", now())
        print(ready, "tasks ready at:", now())
        taskCount = running + ready
        time.sleep(10)


def countTasks(break_running_ready=False):
    """
    Counts the number of tasks.

    Args:
        break_running_ready (bool, optional): Whether to break running and ready tasks. Defaults to False.

    Returns:
        int or tuple: Total tasks or tuple of running and ready tasks.

    Example:
        >>> countTasks()
        >>> countTasks(True)
    """
    tasks = ee.data.getTaskList()
    running_tasks = len(filter(lambda i: i["state"] == "RUNNING", tasks))
    ready_tasks = len(filter(lambda i: i["state"] == "READY", tasks))
    if not break_running_ready:
        return running_tasks + ready_tasks
    else:
        return running_tasks, ready_tasks


def ee_asset_exists(path):
    """
    Checks if a GEE asset exists.

    Args:
        path (str): The asset path.

    Returns:
        bool: True if the asset exists, False otherwise.

    Example:
        >>> ee_asset_exists('users/youruser/yourasset')
    """
    return True if ee.data.getInfo(path) else False


def create_image_collection(full_path_to_collection, properties=None):
    """
    Creates an image collection in GEE.

    Args:
        full_path_to_collection (str): The full path to the collection.
        properties (dict, optional): Properties for the collection. Defaults to None.

    Returns:
        None

    Example:
        >>> create_image_collection('users/youruser/newcollection')
    """
    if ee_asset_exists(full_path_to_collection):
        print("Collection " + full_path_to_collection + " already exists")
    else:
        try:
            ee.data.createAsset({"type": ee.data.ASSET_TYPE_IMAGE_COLL}, full_path_to_collection, properties=properties)
            print("New collection " + full_path_to_collection + " created")
        except Exception as E:
            print("Could not create: ", full_path_to_collection)
            print(E)


def create_asset(asset_path, asset_type=ee.data.ASSET_TYPE_FOLDER, recursive=True):
    """
    Creates an asset in GEE.

    Args:
        asset_path (str): The asset path.
        asset_type (str, optional): The type of asset. Defaults to ee.data.ASSET_TYPE_FOLDER.
        recursive (bool, optional): Whether to create nested folders. Defaults to True.

    Returns:
        None

    Example:
        >>> create_asset('users/youruser/newfolder')
    """
    project_root = f'{asset_path.split("assets")[0]}assets'
    sub_directories = f'{asset_path.split("assets/")[1]}'.split("/")

    if len(sub_directories) > 1 and recursive:
        print("Found the following sub directories: ", sub_directories)
        print("Will attempt to create them if they do not exist")
        path_temp = project_root
        for sub_directory in sub_directories[:-1]:
            path_temp = f"{path_temp}/{sub_directory}"
            create_asset(path_temp, asset_type=ee.data.ASSET_TYPE_FOLDER, recursive=False)

    if ee_asset_exists(asset_path):
        print("Asset " + asset_path + " already exists")
    else:
        try:
            print(asset_path)
            ee.data.createAsset({"type": asset_type}, asset_path)
            print("New asset " + asset_path + " created")
        except Exception as E:
            print("Could not create: ", asset_path)
            print(E)


def verify_path(path):
    """
    Verifies the validity of a path.

    Args:
        path (str): The path to verify.

    Returns:
        None

    Example:
        >>> verify_path('users/youruser/collection')
    """
    response = ee.data.getInfo(path)
    if not response:
        logging.error(
            "%s is not a valid destination. Make sure full path is provided e.g. users/user/nameofcollection " "or projects/myproject/myfolder/newcollection and that you have write access there.",
            path,
        )
        sys.exit(1)


def is_leap_year(year):
    """
    Determines if a year is a leap year.

    Args:
        year (int): The year.

    Returns:
        bool: True if the year is a leap year, False otherwise.

    Example:
        >>> is_leap_year(2020)
        True
    """
    year = int(year)
    if year % 4 == 0:
        if year % 100 == 0 and year % 400 != 0:
            return False
        else:
            return True
    else:
        return False


def now(Format="%b %d %Y %H:%M:%S %a"):
    """
    Gets the current readable date/time.

    Args:
        Format (str, optional): The format of the date/time. Defaults to '%b %d %Y %H:%M:%S %a'.

    Returns:
        str: The current date/time.

    Example:
        >>> now()
    """
    today = datetime.datetime.today()
    s = today.strftime(Format)
    d = datetime.datetime.strptime(s, Format)
    return d.strftime(Format)


def julian_to_calendar(julian_date, year):
    """
    Converts a Julian date to a calendar date.

    Args:
        julian_date (int): The Julian date.
        year (int): The year.

    Returns:
        list: List containing year, month, and day.

    Example:
        >>> julian_to_calendar(32, 2020)
        [2020, 2, 1]
    """
    julian_date, year = int(julian_date), int(year)
    is_leap = is_leap_year(year)
    if is_leap:
        leap, length = True, [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    else:
        leap, length = False, [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
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
        lmn = "0" + str(mn)
    else:
        lmn = str(mn)
    if len(str(dn)) == 1:
        ldn = "0" + str(dn)
    else:
        ldn = str(dn)
    return [year, mn, dn]


def getDate(year, month, day):
    """
    Gets a date in ISO format.

    Args:
        year (int): The year.
        month (int): The month.
        day (int): The day.

    Returns:
        str: The date in ISO format.

    Example:
        >>> getDate(2020, 1, 1)
        '2020-01-01T00:00:00Z'
    """
    return datetime.datetime(year, month, day).isoformat() + "Z"


def setDate(assetPath, year, month, day):
    """
    Sets the date for an asset.

    Args:
        assetPath (str): The asset path.
        year (int): The year.
        month (int): The month.
        day (int): The day.

    Returns:
        None

    Example:
        >>> setDate('users/youruser/yourasset', 2020, 1, 1)
    """
    ee.data.updateAsset(assetPath, {"start_time": getDate(year, month, day)}, ["start_time"])


def ingestImageFromGCS(
    gcsURIs,
    assetPath,
    overwrite=False,
    bandNames=None,
    properties=None,
    pyramidingPolicy=None,
    noDataValues=None,
):
    """
    Ingests an image from Google Cloud Storage to GEE.

    Args:
        gcsURIs (list): List of GCS URIs.
        assetPath (str): The asset path in GEE.
        overwrite (bool, optional): Whether to overwrite existing assets. Defaults to False.
        bandNames (list, optional): List of band names. Defaults to None.
        properties (dict, optional): Properties for the asset. Defaults to None.
        pyramidingPolicy (list, optional): Pyramiding policy for the bands. Defaults to None.
        noDataValues (list, optional): No data values for the bands. Defaults to None.

    Returns:
        None

    Example:
        >>> ingestImageFromGCS(['gs://mybucket/image.tif'], 'users/youruser/yourasset')
    """
    if overwrite or not ee_asset_exists(assetPath):
        taskID = ee.data.newTaskId(1)[0]
        create_image_collection(os.path.dirname(assetPath))
        if str(type(gcsURIs)).find("'str'") > -1:
            gcsURIs = [gcsURIs]
        if bandNames != None and pyramidingPolicy != None and str(type(pyramidingPolicy)).find("'str'") > -1:
            pyramidingPolicy = [pyramidingPolicy] * len(bandNames)
        if bandNames != None and noDataValues != None and str(type(noDataValues)).find("'list'") == -1:
            noDataValues = [noDataValues] * len(bandNames)
        params = {"name": assetPath, "tilesets": [{"sources": [{"uris": gcsURIs}]}]}
        if bandNames != None:
            bnDict = []
            for i, bn in enumerate(bandNames):
                bnDictT = {"id": bn, "tileset_band_index": i}
                if pyramidingPolicy != None:
                    bnDictT["pyramiding_policy"] = pyramidingPolicy[i]
                if noDataValues != None:
                    bnDictT["missing_data"] = {"values": [noDataValues[i]]}
                bnDict.append(bnDictT)
            params["bands"] = bnDict

        def fixDate(propIn, propOut):
            if propIn in properties.keys():
                d = properties[propIn]
                if str(type(d)).find("ee.ee_date.Date") > -1:
                    d = d.format("YYYY-MM-dd").cat("T").cat(d.format("HH:mm:SS")).cat("Z").getInfo()
                params[propOut] = d
                properties.pop(propIn)

        if properties != None:
            fixDate("system:time_start", "start_time")
            fixDate("system:time_end", "end_time")
            params["properties"] = properties
        print("Ingestion manifest:", params)
        ee.data.startIngestion(taskID, params, overwrite)
        print("Starting ingestion task:", assetPath)
    else:
        print(assetPath, "already exists")


def ingestFromGCSImagesAsBands(
    gcsURIs,
    assetPath,
    overwrite=False,
    properties=None,
):
    """
    Ingests multiple images from Google Cloud Storage as bands of a single GEE image.

    Args:
        gcsURIs (list): List of GCS URIs or dictionaries with band information.
        assetPath (str): The asset path in GEE.
        overwrite (bool, optional): Whether to overwrite existing assets. Defaults to False.
        properties (dict, optional): Properties for the asset. Defaults to None.

    Returns:
        None

    Example:
        >>> ingestFromGCSImagesAsBands([{'gcsURI': 'gs://mybucket/band1.tif', 'bandName': 'B1'}], 'users/youruser/yourasset')
    """
    if overwrite or not ee_asset_exists(assetPath):
        taskID = ee.data.newTaskId(1)[0]
        create_image_collection(os.path.dirname(assetPath))
        if str(type(gcsURIs)).find("'str'") > -1:
            gcsURIs = [{"gcsURI": gcsURIs}]
        elif isinstance(gcsURIs, list):
            for i, item in enumerate(gcsURIs):
                if not isinstance(item, dict):
                    gcsURIs[i] = {'gcsURI': item}
        params = {"name": assetPath, "tilesets": [], "bands": []}
        for i, item in enumerate(gcsURIs):
            if "gcsURI" not in item:
                raise ValueError(f"ERROR: The 'gcsURIs' parameter must be a string, list, or list of dictionaries with a key for 'gcsURI'")
            tileset_entry = {"id": f"tileset_for_band{i+1}", "sources": [{"uris":[item["gcsURI"]]}]}
            band_entry = {"tileset_id": f"tileset_for_band{i+1}"}
            if "bandName" in item:
                band_entry["id"] = str(item["bandName"])
            else:
                band_entry["id"] = f"Band{i+1}"
            if "pyramidingPolicy" in item:
                band_entry["pyramidingPolicy"] = item["pyramidingPolicy"]
            if "noDataValue" in item:
                band_entry["missing_data"] = {"values": [item["noDataValue"]]}
            params["tilesets"].append(tileset_entry)
            params["bands"].append(band_entry)

        def fixDate(propIn, propOut):
            if propIn in properties.keys():
                d = properties[propIn]
                if str(type(d)).find("ee.ee_date.Date") > -1:
                    d = d.format("YYYY-MM-dd").cat("T").cat(d.format("HH:mm:SS")).cat("Z").getInfo()
                params[propOut] = d
                properties.pop(propIn)

        if properties != None:
            fixDate("system:time_start", "start_time")
            fixDate("system:time_end", "end_time")
            params["properties"] = properties
        print("Ingestion manifest:", params)
        ee.data.startIngestion(taskID, params, overwrite)
        print("Starting ingestion task:", assetPath)
    else:
        print(assetPath, "already exists")


def uploadToGEEImageAsset(
    localTif,
    gcsBucket,
    assetPath,
    overwrite=False,
    bandNames=None,
    properties=None,
    pyramidingPolicy=None,
    noDataValues=None,
    parallel_threshold="150M",
    gsutil_path="C:/Program Files (x86)/Google/Cloud SDK/google-cloud-sdk/bin/gsutil.cmd",
):
    """
    Uploads an image to GEE as an asset.

    Args:
        localTif (str): Path to the local TIFF file.
        gcsBucket (str): The GCS bucket to upload to.
        assetPath (str): The asset path in GEE.
        overwrite (bool, optional): Whether to overwrite existing assets. Defaults to False.
        bandNames (list, optional): List of band names. Defaults to None.
        properties (dict, optional): Properties for the asset. Defaults to None.
        pyramidingPolicy (list, optional): Pyramiding policy for the bands. Defaults to None.
        noDataValues (list, optional): No data values for the bands. Defaults to None.
        parallel_threshold (str, optional): Threshold for parallel uploads. Defaults to '150M'.
        gsutil_path (str, optional): Path to the gsutil command. Defaults to a default path.

    Returns:
        None

    Example:
        >>> uploadToGEEImageAsset('/tmp/image.tif', 'gs://mybucket', 'users/youruser/yourasset')
    """
    localTifs = glob.glob(localTif)
    gcsURIs = [gcsBucket + "/" + os.path.basename(tif) for tif in localTifs]
    uploadCommand = '"{}" -o "GSUtil:parallel_composite_upload_threshold="{}" " -m cp -n -r {} {}'.format(gsutil_path, parallel_threshold, localTif, gcsBucket)
    call = subprocess.Popen(uploadCommand)
    call.wait()
    ingestImageFromGCS(
        gcsURIs,
        assetPath,
        overwrite=overwrite,
        bandNames=bandNames,
        properties=properties,
        pyramidingPolicy=pyramidingPolicy,
        noDataValues=noDataValues,
    )


def uploadToGEEAssetImagesAsBands(
    tif_dict,
    gcsBucket,
    assetPath,
    overwrite=False,
    properties=None,
):
    """
    Uploads images to GCS and manifests them as bands of a single GEE image.

    Args:
        tif_dict (dict): Dictionary of TIFF files and their properties.
        gcsBucket (str): The GCS bucket to upload to.
        assetPath (str): The asset path in GEE.
        overwrite (bool, optional): Whether to overwrite existing assets. Defaults to False.
        properties (dict, optional): Properties for the asset. Defaults to None.

    Returns:
        None

    Example:
        >>> tif_dict = {'/tmp/band1.tif': {'bandName': 'B1'}, '/tmp/band2.tif': {'bandName': 'B2'}}
        >>> uploadToGEEAssetImagesAsBands(tif_dict, 'gs://mybucket', 'users/youruser/yourasset')
    """
    if not isinstance(tif_dict, dict):
        raise ValueError("ERROR: tif_dict must be a dictionary.")
    for tif in tif_dict.keys():
        print(f"Uploading {tif} to GCS...")
        uploadTifToGCS(tif, gcsBucket)
        tif_dict[tif]["gcsURI"] = gcsBucket + "/" + os.path.basename(tif)
    print(f"Ingesting GCS images as bands...")
    ingestFromGCSImagesAsBands(
        tif_dict.values(),
        assetPath,
        overwrite=overwrite,
        properties=properties,
    )
