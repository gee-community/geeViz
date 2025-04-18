import ee, os, json, re

ee.Initialize()
###################################################################################################
"""
 This script recursively migrates Google Earth Engine assets from one repository to a new one, sets permissions, and deletes old assets if needed.
 **Important** for this to work you need the following:
       - The credential you're using must have editor permissions in both the source and destination repositories
                               OR
       - The credential you're using must have editor permissions in the destination repository, and you are willing to
           change the permissions of all the original assets to "Anyone Can Read" (to do this, set changePermissions = True below)
       - The geeViz package installed in your python instance. (https://github.com/gee-community/geeViz)

"""

# Written by:
# Ian Housman ian.housman@usda.gov ian.housman@gmail.com
# Leah Campbell leah.campbell@usda.gov leahs.campbell@gmail.com
# RedCastle Resources Inc.
# MIT License
###################################################################################################
# Repository you are moving from:
sourceRoot = "users/iwhousman/test"
# sourceRoot = 'projects/USFS/LCMS-NFS/R1/FNF'
# sourceRoot = 'projects/lcms-292214/assets/AK-Ancillary-Data'

# Repository you are moving to:
# It is assumed this folder already exists and user account has write access to it
# destinationRoot = 'projects/lcms-292214/assets/migrationTest/FNF'
# destinationRoot = 'users/usfs-ihousman/migrationTest'
# If the credential you're using does not have editor permissions in the source repository
# Must include 'user:' prefix if it is a individual's Email or 'group:' if it is a Google Group
changeSourcePermissions = True
sourceReaders = []
sourceWriters = ["user:ian.housman@usda.gov"]
source_all_users_can_read = False

changeDestinationPermissions = True
destinationReaders = []
destinationWriters = []
destination_all_users_can_read = False


###################################################################################################
# Function to get all folders, imageCollections, images, and tables under a given folder or imageCollection level
def getTree(fromRoot, toRoot, treeList=[]):
    """
    Recursively gets all folders, imageCollections, images, and tables under a given folder or imageCollection level.

    Args:
        fromRoot (str): The source root asset path.
        toRoot (str): The destination root asset path.
        treeList (list, optional): List to accumulate results.

    Returns:
        list: List of [type, fromID, toID] for all assets found.

    Example:
        >>> getTree('users/source/folder', 'users/dest/folder')
    """
    pathPrefix = "projects/earthengine-legacy/assets/"

    # Clean up the given paths
    if fromRoot[-1] != "/":
        fromRoot += "/"
    if toRoot[-1] != "/":
        toRoot += "/"

    # Handle inconsistencies with the earthengine-legacy prefix
    if re.match("^projects/[^/]+/assets/.*$", fromRoot) == None:
        fromRoot = pathPrefix + fromRoot
    if re.match("^projects/[^/]+/assets/.*$", toRoot) == None:
        toRoot = pathPrefix + toRoot
    # print(fromRoot,toRoot)
    # List assets
    try:
        assets = ee.data.listAssets({"parent": fromRoot})["assets"]
    except Exception as e1:
        print(e1)
        # try:
        #     assets = ee.data.listAssets({'parent':fromRoot})['assets']
        # except Exception as e2:
        #     print(e2)

    # Reursively walk down the tree
    nextLevels = []
    for asset in assets:
        fromID = asset["name"]
        fromType = asset["type"]
        # fromID = fromID.replace('projects/earthengine-legacy/assets/','')
        toID = fromID.replace(fromRoot, toRoot)

        if fromType in ["FOLDER", "IMAGE_COLLECTION"]:
            nextLevels.append([fromID, toID])
        treeList.append([fromType, fromID, toID])

    for i1, i2 in nextLevels:
        getTree(i1, i2, treeList)
    return treeList


###################################################################################################
# Function for setting permissions for all files under a specified root level
# Either a list of assets a root to start from can be provided
def batchChangePermissions(
    assetList=None, root=None, readers=[], writers=[], all_users_can_read=False
):
    """
    Sets permissions for all files under a specified root level or for a provided list of assets.

    Args:
        assetList (list, optional): List of asset IDs to change permissions for.
        root (str, optional): Root asset path to start from if assetList not provided.
        readers (list, optional): List of readers.
        writers (list, optional): List of writers.
        all_users_can_read (bool, optional): If True, anyone can read.

    Returns:
        None

    Example:
        >>> batchChangePermissions(root='users/youruser/folder', writers=['user:someone@gmail.com'])
    """
    if assetList == None:
        assetList = [i[1] for i in getTree(root, root)]

    for assetID in assetList:
        print("Changing permissions for: {}".format(assetID))
        try:
            ee.data.setAssetAcl(
                assetID,
                json.dumps(
                    {
                        "writers": writers,
                        "all_users_can_read": all_users_can_read,
                        "readers": readers,
                    }
                ),
            )
        except Exception as e:
            print(e)


###################################################################################################
# Function to copy all folders, imageCollections, images, and tables under a given folder or imageCollection level
# Permissions can also be set here
def copyAssetTree(
    fromRoot,
    toRoot,
    changePermissions=False,
    readers=[],
    writers=[],
    all_users_can_read=False,
):
    """
    Copies all folders, imageCollections, images, and tables under a given folder or imageCollection level.

    Args:
        fromRoot (str): Source root asset path.
        toRoot (str): Destination root asset path.
        changePermissions (bool, optional): Whether to change permissions after copy.
        readers (list, optional): List of readers for permissions.
        writers (list, optional): List of writers for permissions.
        all_users_can_read (bool, optional): If True, anyone can read.

    Returns:
        None

    Example:
        >>> copyAssetTree('users/source/folder', 'users/dest/folder', changePermissions=True)
    """
    treeList = getTree(fromRoot, toRoot)

    # Iterate across all assets and copy and create when appropriate
    for fromType, fromID, toID in treeList:
        if fromType in ["FOLDER", "IMAGE_COLLECTION"]:
            try:
                print("Creating {}: {}".format(fromType, toID))
                ee.data.createAsset({"type": "Image_Collection", "name": toID})
            except Exception as e:
                print(e)
        else:
            try:
                print("Copying {}: {}".format(fromType, toID))
                ee.data.copyAsset(fromID, toID, False)

            except Exception as e:
                print(e)
        print()
        print()

    if changePermissions:
        batchChangePermissions(
            assetList=[i[2] for i in treeList],
            root=None,
            readers=[],
            writers=[],
            all_users_can_read=False,
        )


###################################################################################################
# Function to delete all folders, imageCollections, images, and tables under a given folder or imageCollection level
def deleteAssetTree(root):
    """
    Deletes all folders, imageCollections, images, and tables under a given folder or imageCollection level.

    Args:
        root (str): Root asset path to delete from.

    Returns:
        None

    Example:
        >>> deleteAssetTree('users/youruser/folder')
    """
    answer = input(
        "Are you sure you want to delete all assets under {}? (y = yes, n = no) ".format(
            root
        )
    )
    print(answer)
    if answer.lower() == "y":
        answer = input(
            "You answered yes. Just double checking. Are you sure you want to delete all assets under {}? (y = yes, n = no) ".format(
                root
            )
        )
        if answer.lower() == "y":
            treeList = getTree(root, root)
            treeList.reverse()
            for fromType, ID1, ID2 in treeList:
                print("Deleting {}".format(ID1))
                try:
                    ee.data.deleteAsset(ID1)
                except Exception as e:
                    print(e)


###################################################################################################
# Step 1: Make sure source has account added as reader (may need to use different credentials for this)
batchChangePermissions(
    None, sourceRoot, sourceReaders, sourceWriters, source_all_users_can_read
)
###################################################################################################
# Step 2: Use this function to copy assets
# copyAssetTree(sourceRoot,destinationRoot,changeDestinationPermissions,destinationReaders,destinationWriters,destination_all_users_can_read)
###################################################################################################
#!!!!!!! DANGER !!!!!!!!!
#!!!!!!! DANGER !!!!!!!!!
#!!!!!!! DANGER !!!!!!!!!
#!!!!!!! DANGER !!!!!!!!!
# Optional Step 3: Once all assets are copied and inspected, you can use this method to delete all files under the root level
# This method is final and there is no way to undo this
# deleteAssetTree(destinationRoot)
