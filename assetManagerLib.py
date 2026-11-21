"""
Helpful functions for managing GEE assets

geeViz.assetManagerLib includes functions for copying, deleting, uploading, changing permissions, and more.
"""

"""
   Copyright 2026 Leah Campbell, Ian Housman, Nicholas Storey

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
import collections.abc
import numbers
import re
from pathlib import Path

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


def upload_tif(local_tif, gcs_uri, overwrite=False):
    """
    Uploads one TIFF to an explicit GCS object URI using the gcloud CLI (strict).

    Unlike ``uploadTifToGCS`` this requires a full ``gs://bucket/object.tif``
    destination, runs gcloud without a shell, and raises on any failure.

    Args:
        local_tif (str | Path): Path to an existing local file.
        gcs_uri (str): Destination object URI beginning with ``gs://``.
        overwrite (bool, optional): Replace an existing object. Defaults to False (no-clobber).

    Raises:
        FileNotFoundError: The local file or the gcloud executable is missing.
        ValueError: The destination is not an explicit gs:// object URI.
        FileExistsError: The object exists and ``overwrite`` is False.
        RuntimeError: gcloud exited with a non-zero status.

    Example:
        >>> upload_tif('/tmp/image.tif', 'gs://mybucket/folder/image.tif')
    """
    source = Path(local_tif)
    if not source.is_file():
        raise FileNotFoundError(f"Input TIFF does not exist: {source}")
    if not isinstance(gcs_uri, str) or not gcs_uri.startswith("gs://"):
        raise ValueError(f"Expected a gs:// destination URI, received: {gcs_uri!r}")
    if "/" not in gcs_uri[len("gs://"):].strip("/") or gcs_uri.endswith("/"):
        raise ValueError(f"Expected an explicit gs://<bucket>/<object> destination URI, received: {gcs_uri}")
    executable = shutil.which("gcloud") or shutil.which("gcloud.cmd") or shutil.which("gcloud.exe")
    if executable is None:
        raise FileNotFoundError(
            "Could not find the Google Cloud CLI executable on PATH. "
            "Open a shell where 'gcloud --version' works and retry."
        )
    if not overwrite:
        # ``gcloud storage cp -n`` exits 0 and silently skips an existing object,
        # so check first and fail loudly instead of leaving a stale object behind.
        existing = subprocess.run([executable, "storage", "ls", gcs_uri], capture_output=True, text=True)
        if existing.returncode == 0:
            raise FileExistsError(f"Destination already exists (pass overwrite=True to replace it): {gcs_uri}")
    command = [executable, "storage", "cp", str(source), gcs_uri]
    if not overwrite:
        command.append("-n")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to upload TIFF to GCS.\n"
            f"Local file: {source}\nDestination: {gcs_uri}\n"
            f"Exit code: {result.returncode}\nstdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )


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


# Earth Engine reports a missing asset as, e.g.,
#   "Asset 'projects/p/assets/a' does not exist or doesn't allow this operation."
# (it deliberately does not distinguish missing from unreadable). Match only that
# shape so unrelated failures (quota, bad project, transport errors) still raise
# and an asset path that merely contains "404" is not mistaken for a miss.
_NOT_FOUND_PATTERN = re.compile(
    r"^(?:requested )?asset\b(?: '[^']*')? (?:does not exist|not found)\b",
    re.IGNORECASE,
)
_CONTAINER_TYPES = ("folder", "imagecollection")


def _is_not_found_error(exc):
    return bool(_NOT_FOUND_PATTERN.match(str(exc).strip()))


def _require_projects_path(asset_path, min_parts, shape):
    parts = asset_path.split("/") if isinstance(asset_path, str) else []
    if len(parts) < min_parts or parts[0] != "projects" or parts[2] != "assets" or not all(parts):
        raise ValueError(f"Expected an Earth Engine path like '{shape}'; received: {asset_path!r}")
    return parts


def normalize_asset_type(asset_type):
    """Normalizes EE asset type values (e.g. ``IMAGE_COLLECTION`` -> ``imagecollection``)."""
    if not asset_type or not isinstance(asset_type, str):
        return ""
    return asset_type.replace("_", "").lower()


def asset_basename(asset):
    """Returns the last path component of an asset dict's ``id`` or ``name``."""
    asset_id = asset.get("id") or asset.get("name") or ""
    if not isinstance(asset_id, str):
        return ""
    return asset_id.rsplit("/", 1)[-1]


def get_asset(asset_path):
    """Returns asset metadata; raises RuntimeError (chained to the EE error) on any failure."""
    try:
        asset = ee.data.getAsset(asset_path)
    except ee.EEException as exc:
        raise RuntimeError(f"Failed to get Earth Engine asset: {asset_path}") from exc
    if not isinstance(asset, dict):
        raise RuntimeError(f"Unexpected Earth Engine asset response for: {asset_path}")
    return asset


def get_asset_if_exists(asset_path):
    """Returns asset metadata, or None only for a genuine not-found response.

    Authorization, quota, network and other errors raise RuntimeError.
    """
    try:
        asset = ee.data.getAsset(asset_path)
    except ee.EEException as exc:
        if _is_not_found_error(exc):
            return None
        raise RuntimeError(f"Failed to get Earth Engine asset: {asset_path}") from exc
    if not isinstance(asset, dict):
        raise RuntimeError(f"Unexpected Earth Engine asset response for: {asset_path}")
    return asset


def ensure_asset_folder(folder_path):
    """Creates an EE folder if absent; raises if the path exists as a non-container asset."""
    asset = get_asset_if_exists(folder_path)
    if asset is None:
        try:
            ee.data.createAsset({"type": "FOLDER"}, folder_path)
        except ee.EEException as exc:
            raise RuntimeError(f"Failed to create Earth Engine folder: {folder_path}") from exc
        return
    if normalize_asset_type(asset.get("type")) not in _CONTAINER_TYPES:
        raise RuntimeError(f"Existing asset is not a folder or collection: {folder_path} (type={asset.get('type')})")


def ensure_asset_path(asset_path):
    """Ensures every folder in a ``projects/<project>/assets/<folder>/...`` path exists."""
    parts = _require_projects_path(asset_path, 4, "projects/<project>/assets/<folder>")
    current = "/".join(parts[:3])
    for folder in parts[3:]:
        current = f"{current}/{folder}"
        ensure_asset_folder(current)


def ensure_parent_asset_path(asset_path):
    """Ensures the parent folder path of ``projects/<project>/assets/<folder>/<asset>`` exists."""
    parts = _require_projects_path(asset_path, 5, "projects/<project>/assets/<folder>/<asset>")
    ensure_asset_path("/".join(parts[:-1]))


def list_child_asset_basenames(parent_path):
    """Returns the set of direct-child basenames under a parent (follows pagination)."""
    basenames = set()
    params = {"parent": parent_path}
    while True:
        try:
            response = ee.data.listAssets(dict(params))
        except ee.EEException as exc:
            raise RuntimeError(f"Failed to list child assets under Earth Engine path: {parent_path}") from exc
        if not isinstance(response, dict):
            raise RuntimeError(f"Unexpected Earth Engine listAssets response for: {parent_path}")
        assets = response.get("assets") or []
        if not isinstance(assets, list):
            raise RuntimeError(f"Unexpected Earth Engine listAssets 'assets' value for: {parent_path}")
        for asset in assets:
            if isinstance(asset, dict) and asset_basename(asset):
                basenames.add(asset_basename(asset))
        token = response.get("nextPageToken")
        if not token:
            return basenames
        params["pageToken"] = token


def find_missing_collection_children(source_collection_path, destination_collection_path):
    """Returns sorted basenames present in the source collection but absent from the destination."""
    return sorted(list_child_asset_basenames(source_collection_path) - list_child_asset_basenames(destination_collection_path))


def copy_asset(source_path, destination_path, overwrite=False):
    """Copies an image or table asset (not a collection; see ``copy_collection``)."""
    try:
        ee.data.copyAsset(source_path, destination_path, overwrite)
    except ee.EEException as exc:
        raise RuntimeError(f"Failed to copy Earth Engine asset from {source_path} to {destination_path}") from exc


def copy_collection(source_collection_path, destination_collection_path, overwrite=False):
    """Copies every child of an ImageCollection into a destination ImageCollection.

    The destination is created if absent and must be an ImageCollection if it
    exists. Existing children cause an error unless ``overwrite`` is True.
    All child failures are collected and raised as one RuntimeError.
    """
    destination = get_asset_if_exists(destination_collection_path)
    if destination is None:
        try:
            ee.data.createAsset({"type": "IMAGE_COLLECTION"}, destination_collection_path)
        except ee.EEException as exc:
            raise RuntimeError(f"Failed to create Earth Engine collection: {destination_collection_path}") from exc
    elif normalize_asset_type(destination.get("type")) != "imagecollection":
        raise RuntimeError(
            f"Destination asset exists but is not an ImageCollection: {destination_collection_path} (type={destination.get('type')})"
        )
    children = sorted(list_child_asset_basenames(source_collection_path))
    failures = []
    for name in children:
        try:
            ee.data.copyAsset(f"{source_collection_path}/{name}", f"{destination_collection_path}/{name}", overwrite)
        except ee.EEException as exc:
            failures.append((name, str(exc)))
    if failures:
        details = "; ".join(f"{name}: {message}" for name, message in failures)
        raise RuntimeError(
            f"Failed to copy {len(failures)} of {len(children)} assets from {source_collection_path} "
            f"to {destination_collection_path}: {details}"
        )


def promote_assets_to_catalog(input_dataset_path, final_dataset_path, overwrite=False):
    """Promotes an image, table or ImageCollection to its final catalog path, creating parent folders."""
    asset = get_asset(input_dataset_path)
    asset_type = normalize_asset_type(asset.get("type"))
    if asset_type == "imagecollection":
        ensure_parent_asset_path(final_dataset_path)
        copy_collection(input_dataset_path, final_dataset_path, overwrite)
    elif asset_type in ("image", "table", "featurecollection"):
        ensure_parent_asset_path(final_dataset_path)
        copy_asset(input_dataset_path, final_dataset_path, overwrite)
    else:
        raise RuntimeError(f"Unsupported Earth Engine asset type for promotion: {asset.get('type')} at {input_dataset_path}")


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


_PYRAMIDING_POLICIES = ("MEAN", "MODE", "MIN", "MAX", "SAMPLE")


def _normalize_band_entries(gcsURIs):
    """Validate ingestion input and return a new list of fresh entry dicts.

    Never mutates the caller's list or dictionaries.
    """
    if isinstance(gcsURIs, (str, dict)):
        gcsURIs = [gcsURIs]
    elif isinstance(gcsURIs, collections.abc.Iterable) and not isinstance(gcsURIs, bytes):
        # Accept any iterable (e.g. dict.values(), as uploadToGEEAssetImagesAsBands passes).
        gcsURIs = list(gcsURIs)
    if not isinstance(gcsURIs, list) or len(gcsURIs) == 0:
        raise ValueError("The 'gcsURIs' parameter must be a gs:// string, or a non-empty list of strings or dictionaries with a key for 'gcsURI'")
    entries = []
    for i, item in enumerate(gcsURIs):
        entry = dict(item) if isinstance(item, dict) else {"gcsURI": item}
        if "gcsURI" not in entry:
            raise ValueError(f"The 'gcsURIs' parameter must be a string, list, or list of dictionaries with a key for 'gcsURI' (entry {i})")
        uri = entry["gcsURI"]
        if not isinstance(uri, str) or not uri.startswith("gs://") or len(uri) <= len("gs://"):
            raise ValueError(f"Entry {i}: 'gcsURI' must be a non-empty gs:// URI, received: {uri!r}")
        if "bandName" in entry and not str(entry["bandName"]).strip():
            raise ValueError(f"Entry {i}: 'bandName' must not be empty")
        if "pyramidingPolicy" in entry and str(entry["pyramidingPolicy"]).upper() not in _PYRAMIDING_POLICIES:
            raise ValueError(f"Entry {i}: 'pyramidingPolicy' must be one of {_PYRAMIDING_POLICIES}, received: {entry['pyramidingPolicy']!r}")
        if "noDataValue" in entry and entry["noDataValue"] is None:
            del entry["noDataValue"]  # None means "no nodata value"
        if "noDataValue" in entry:
            nd = entry["noDataValue"]
            if isinstance(nd, bool) or not isinstance(nd, numbers.Real):
                raise ValueError(f"Entry {i}: 'noDataValue' must be numeric, received: {nd!r}")
            if hasattr(nd, "item"):
                entry["noDataValue"] = nd.item()  # numpy scalar -> JSON-serializable Python number
        entries.append(entry)
    return entries


def ingestFromGCSImagesAsBands(
    gcsURIs,
    assetPath,
    overwrite=False,
    properties=None,
):
    """
    Ingests multiple images from Google Cloud Storage as bands of a single GEE image.

    Inputs are validated and copied; neither ``gcsURIs`` nor ``properties`` is modified.
    Entry dictionaries accept ``gcsURI`` (required), ``bandName``, ``pyramidingPolicy``
    and ``noDataValue``; the manifest uses ``tileset_id``, ``pyramiding_policy`` and
    ``missing_data``.

    Args:
        gcsURIs (str | list): A GCS URI, or list of GCS URIs or dictionaries with band information.
        assetPath (str): The asset path in GEE.
        overwrite (bool, optional): Whether to overwrite existing assets. Defaults to False.
        properties (dict, optional): Properties for the asset. Defaults to None.

    Returns:
        The result of ``ee.data.startIngestion`` (includes the task ``id``), or None
        if the asset already exists and ``overwrite`` is False.

    Example:
        >>> ingestFromGCSImagesAsBands([{'gcsURI': 'gs://mybucket/band1.tif', 'bandName': 'B1'}], 'users/youruser/yourasset')
    """
    entries = _normalize_band_entries(gcsURIs)
    properties = dict(properties) if properties is not None else None
    if not (overwrite or not ee_asset_exists(assetPath)):
        print(assetPath, "already exists")
        return None
    taskID = ee.data.newTaskId(1)[0]
    create_image_collection(os.path.dirname(assetPath))
    params = {"name": assetPath, "tilesets": [], "bands": []}
    for i, item in enumerate(entries):
        tileset_id = f"tileset_for_band{i+1}"
        band_entry = {"tileset_id": tileset_id, "id": str(item["bandName"]) if "bandName" in item else f"Band{i+1}"}
        if "pyramidingPolicy" in item:
            band_entry["pyramiding_policy"] = str(item["pyramidingPolicy"]).upper()
        if "noDataValue" in item:
            band_entry["missing_data"] = {"values": [item["noDataValue"]]}
        params["tilesets"].append({"id": tileset_id, "sources": [{"uris": [item["gcsURI"]]}]})
        params["bands"].append(band_entry)

    def fixDate(propIn, propOut):
        if propIn in properties:
            d = properties.pop(propIn)
            if str(type(d)).find("ee.ee_date.Date") > -1:
                d = d.format("YYYY-MM-dd").cat("T").cat(d.format("HH:mm:SS")).cat("Z").getInfo()
            params[propOut] = d

    if properties is not None:
        fixDate("system:time_start", "start_time")
        fixDate("system:time_end", "end_time")
        params["properties"] = properties
    print("Ingestion manifest:", params)
    result = ee.data.startIngestion(taskID, params, overwrite)
    print("Starting ingestion task:", assetPath)
    return result


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
