#--------------------------------------------------------
#           migrateGEEAssets.py
#-------------------------------------------------------
# Leah Campbell, 11/19/2020
# This script recursively migrates Google Earth Engine assets from one repository to a new one.
# **Important** for this to work you need the following:
#       - The credential you're using must have editor permissions in both the source and destination repositories
#                               OR
#       - The credential you're using must have editor permissions in the destination repository, and you are willing to
#           change the permissions of all the original assets to "Anyone Can Read" (to do this, set changePermissions = True below)
#       - The geeViz package installed in your python instance. (https://github.com/gee-community/geeViz)

import ee
ee.Initialize()
import os, pdb, sys
from geeViz import assetManagerLib as assetLib

# Repository you are moving from:
sourceRoot = 'projects/earthengine-legacy/assets/projects/USFS/LCMS-NFS/Processing_Tiles_Alaska' # Make sure you keep 'projects/earthengine-legacy/assets' in front here.
# Repository you are moving to:
destinationRoot = 'projects/lcms-tcc-shared/assets/Processing_Tiles/Alaska'

# If there are any assets you DON'T want to move, enter the full path here.
# Assets = images, imageCollections, featureCollections, etc., NOT folders.
assetsToSkip = []

# If the credential you're using does not have editor permissions in the source repository
changePermissions = True

#-------------------------------------------------------------------
#                   Functions
#--------------------------------------------------------------------

def sortFolderAssets(assets):
    imagesAndTables = [a for a in assets if a['type'] == 'IMAGE' or a['type'] == 'TABLE']
    imageCollections = [a for a in assets if a['type'] == 'IMAGE_COLLECTION']
    folders = [a for a in assets if a['type'] == 'FOLDER']
    return imagesAndTables, imageCollections, folders

def createFolders(oldFolders, existingNewFolders, newDirName):
    existingFolderIDs = [object['name'] for object in existingNewFolders]
    for oldFolder in oldFolders:
        newFolder = os.path.join(newDirName, os.path.basename(oldFolder['name'])).replace('\\','/')
        if newFolder in existingFolderIDs:
            print('Skipping '+newFolder+': Already Exists')
        else:
            print('Creating '+newFolder)
            ee.data.createAsset({'type': 'FOLDER', 'name': newFolder})

def copyImages(oldDirName, oldImages, newDirName, existingNewImages):
    if len(oldImages) > 0:
        failedCopies = []
        existingImageIDs = [object['name'] for object in existingNewImages]
        for oldImage in oldImages:
            if oldImage['id'] not in assetsToSkip:
                newImage = os.path.join(newDirName, os.path.basename(oldImage['name'])).replace('\\','/')
                if newImage in existingImageIDs:
                    print(newImage+' Already Exists: Skipping Copy')
                else:
                    print('Copying '+oldImage['name']+' to '+newImage)
                    try:
                        ee.data.copyAsset(oldImage['id'], newImage)
                    except Exception as e:
                        print('Error: ',oldImage['id'])
                        failedCopies.append([oldImage['id'], e])
                        
        if len(failedCopies) > 0:
            print('')
            print('FAILED IMAGE/TABLE COPIES: ')
            for c in failedCopies:
                print(c[0])
                print(c[1])
            print('EXITING BECAUSE OF FAILED COPIES LISTED ABOVE')
            sys.exit(0)
        else:
            print('SUCCESS COPYING IMAGES AND TABLES FROM '+oldDirName)
    else:
        print('NO IMAGES OR TABLES TO COPY')

def copyImageCollections(oldDirName, oldImageCollections, newDirName, existingNewImageCollections):
    if len(oldImageCollections) > 0:
        failedCopies = []
        existingImageCollectionIDs = [object['name'] for object in existingNewImageCollections]
        for oldImageCollection in oldImageCollections:
            if oldImageCollection['id'] not in assetsToSkip:
                newImageCollection = os.path.join(newDirName, os.path.basename(oldImageCollection['name'])).replace('\\','/')
                if newImageCollection in existingImageCollectionIDs:
                    print(newImageCollection+' Already Exists')
                    imageCollectionExists = True
                else:
                    print('Creating '+newImageCollection)
                    imageCollectionExists = False
                    try:
                        ee.data.createAsset({'type': 'IMAGE_COLLECTION', 'name': newImageCollection})
                    except:
                        print('Error creating '+newImageCollection)
                        failedCopies.append([oldImageCollection['id'], e])
                        return

                sizeOld = ee.ImageCollection(oldImageCollection['id']).size().getInfo()
                sizeNew = ee.ImageCollection(newImageCollection).size().getInfo()
                print('Copying '+oldImageCollection['name']+' to '+newImageCollection)
                if (imageCollectionExists and sizeOld != sizeNew) or (imageCollectionExists == False):
                    try:
                        oldImages = ee.data.listAssets({'parent': oldImageCollection['name']})['assets']
                        existingImageIDs = [object['name'] for object in ee.data.listAssets({'parent': newImageCollection})['assets']]
                        for oldImage in oldImages:
                            newImage = os.path.join(newImageCollection, os.path.basename(oldImage['name'])).replace('\\','/')
                            if newImage in existingImageIDs:
                                print(newImage+' Already Exists: Skipping Copy')
                            else:
                                print('Copying '+oldImage['name']+' to '+newImage)
                                try:
                                    ee.data.copyAsset(oldImage['id'], newImage)
                                except Exception as e:
                                    print('Error: ',oldImage['id'])
                                    failedCopies.append([oldImage['id'], e])
                                    
                    except Exception as e:
                        print('Error Copying Images: ',oldImageCollection['id'])
                        failedCopies.append([oldImageCollection['id'], e])
        if len(failedCopies) > 0:
            print('')
            print('FAILED IMAGE COLLECTION COPIES: ')
            for c in failedCopies:
                print(c[0])
                print(c[1])
            print('EXITING BECAUSE OF FAILED COPIES LISTED ABOVE')
            sys.exit(0)
        else:
            print('SUCCESS COPYING IMAGE COLLECTIONS FROM '+oldDirName)
    else:
        print('NO IMAGE COLLECTIONS TO COPY')

def copyAndCreate(oldDirName, newDirName):
    # List assets you want to move over and the existing assets in the new location.
    oldAssets = ee.data.listAssets({'parent': oldDirName})['assets']
    existingNewAssets = ee.data.listAssets({'parent': newDirName})['assets']

    # Sort assets to move and existing assets
    oldImagesAndTables, oldImageCollections, oldFolders = sortFolderAssets(oldAssets)
    existingNewImagesAndTables, existingNewImageCollections, existingNewFolders = sortFolderAssets(existingNewAssets)

    # Copy over Images and Tables
    copyImages(oldDirName, oldImagesAndTables, newDirName, existingNewImagesAndTables)
    copyImageCollections(oldDirName, oldImageCollections, newDirName, existingNewImageCollections) 

    # Create any folders that don't exist already
    createFolders(oldFolders, existingNewFolders, newDirName)

    return oldFolders

#--------------------------------------------------------------------------------------------
#            Work Through Hierarchy and Make Sure All Assets Have Proper Permissions
#--------------------------------------------------------------------------------------------
if changePermissions:
    assets = ee.data.listAssets({'parent': sourceRoot})['assets']
    for assetName in assets:
        print('Updating ACL For', assetName['id'])
        assetLib.updateACL(assetName['id'], writers = [], all_users_can_read = True, readers = [])
    folders = [a['name'] for a in assets if a['type'] == 'FOLDER']
    for folder in folders:
        subAssets = ee.data.listAssets({'parent': folder})['assets']
        for assetName in subAssets:
            print('Updating ACL For', assetName['id'])
            assetLib.updateACL(assetName['id'], writers = [], all_users_can_read = True, readers = [])
        subFolders = [a['name'] for a in subAssets if a['type'] == 'FOLDER']
        for subFolder in subFolders:
            subAssets2 = ee.data.listAssets({'parent': subFolder})['assets']
            for assetName in subAssets2:
                print('Updating ACL For', assetName['id'])
                assetLib.updateACL(assetName['id'], writers = [], all_users_can_read = True, readers = [])
            subFolders2 = [a['name'] for a in subAssets if a['type'] == 'FOLDER']
            for subFolder2 in subFolders2:
                subAssets3 = ee.data.listAssets({'parent': subFolder2})['assets']
                for assetName in subAssets3:
                    print('Updating ACL For', assetName['id'])
                    assetLib.updateACL(assetName['name'], writers = [], all_users_can_read = True, readers = [])

#--------------------------------------------------------------------------------------------
#            Work Through Hierarchy and Copy Over Assets
#--------------------------------------------------------------------------------------------
# First create the folders in the new repository
oldFolders = copyAndCreate(sourceRoot, destinationRoot)

# Then go folder by folder and copy everything over.
for oldFolder in oldFolders:
    print(oldFolder)
    
    sourceSubRoot = oldFolder['name']
    destinationSubRoot = os.path.join(destinationRoot, sourceSubRoot.split(sourceRoot)[1].split('/')[1]).replace('\\','/') 

    oldSubFolders = copyAndCreate(sourceSubRoot, destinationSubRoot)
    for oldSubFolder in oldSubFolders:
        print(oldSubFolder)
        
        sourceSubRoot2 = oldSubFolder['name']
        destinationSubRoot2 = os.path.join(destinationSubRoot, sourceSubRoot2.split(sourceSubRoot)[1].split('/')[1]).replace('\\','/') 

        oldSubFolders2 = copyAndCreate(sourceSubRoot2, destinationSubRoot2)
        for oldSubFolder2 in oldSubFolders2:
            print(oldSubFolder2)
        
            sourceSubRoot3 = oldSubFolder2['name']
            destinationSubRoot3 = os.path.join(destinationSubRoot2, sourceSubRoot3.split(sourceSubRoot2)[1].split('/')[1]).replace('\\','/') 

            oldSubFolders2 = copyAndCreate(sourceSubRoot3, destinationSubRoot3)


