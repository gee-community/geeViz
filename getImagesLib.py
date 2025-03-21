"""
Get images and organize them so they are easier to work with

geeViz.getImagesLib is the core module for setting up various imageCollections from GEE. Notably, it facilitates Landsat, Sentinel-2, and MODIS data organization. This module helps avoid many common mistakes in GEE. Most functions ease matching band names, ensuring resampling methods are properly set, date wrapping, and helping with cloud and cloud shadow masking.

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
# %%
# Script to help with data prep, analysis, and delivery from GEE
# Intended to work within the geeViz package
######################################################################
from geeViz.geeView import *
import geeViz.cloudStorageManagerLib as cml
import geeViz.assetManagerLib as aml
import geeViz.taskManagerLib as tml
import math, ee, json, pdb, datetime
from threading import Thread

# %%
######################################################################
# Module for getting Landsat, Sentinel 2 and MODIS images/composites
# Define visualization parameters
vizParamsFalse = {
    "min": 0.05,
    "max": [0.5, 0.6, 0.6],
    "bands": "swir1,nir,red",
    "gamma": 1.6,
}
vizParamsFalse10k = {
    "min": 0.05 * 10000,
    "max": [0.5 * 10000, 0.6 * 10000, 0.6 * 10000],
    "bands": "swir1,nir,red",
    "gamma": 1.6,
}
vizParamsTrue = {"min": 0, "max": [0.2, 0.2, 0.2], "bands": "red,green,blue"}
vizParamsTrue10k = {
    "min": 0,
    "max": [0.2 * 10000, 0.2 * 10000, 0.2 * 10000],
    "bands": "red,green,blue",
}

common_projections = {}
common_projections["NLCD_CONUS"] = {
    "crs": 'PROJCS["Albers_Conical_Equal_Area",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],TOWGS84[0,0,0,0,0,0,0],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]],PROJECTION["Albers_Conic_Equal_Area"],PARAMETER["latitude_of_center",23],PARAMETER["longitude_of_center",-96],PARAMETER["standard_parallel_1",29.5],PARAMETER["standard_parallel_2",45.5],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["meters",1],AXIS["Easting",EAST],AXIS["Northing",NORTH]]',
    "transform": [30, 0, -2361915.0, 0, -30, 3177735.0],
}
common_projections["NLCD_AK"] = {
    "crs": 'PROJCS["Albers_Conical_Equal_Area",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],TOWGS84[0,0,0,0,0,0,0],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9108"]],AUTHORITY["EPSG","4326"]],PROJECTION["Albers_Conic_Equal_Area"],PARAMETER["standard_parallel_1",55],PARAMETER["standard_parallel_2",65],PARAMETER["latitude_of_center",50],PARAMETER["longitude_of_center",-154],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["meters",1]]',
    "transform": [30, 0, -48915.0, 0, -30, 1319415.0],
}
common_projections["NLCD_HI"] = {
    "crs": 'PROJCS["Albers_Conical_Equal_Area",GEOGCS["WGS 84",DATUM["WGS_1984", SPHEROID["WGS 84", 6378137.0, 298.257223563, AUTHORITY["EPSG","7030"]], AUTHORITY["EPSG","6326"]], PRIMEM["Greenwich", 0.0], UNIT["degree", 0.017453292519943295], AXIS["Longitude", EAST], AXIS["Latitude", NORTH], AUTHORITY["EPSG","4326"]], PROJECTION["Albers_Conic_Equal_Area"], PARAMETER["central_meridian", -157.0],PARAMETER["latitude_of_origin", 3.0],PARAMETER["standard_parallel_1", 8.0],PARAMETER["false_easting", 0.0],PARAMETER["false_northing", 0.0],PARAMETER["standard_parallel_2", 18.0],UNIT["m", 1.0],AXIS["x", EAST],AXIS["y", NORTH]]',
    "transform": [30, 0, -342585, 0, -30, 2127135],
}

# Direction of  a decrease in photosynthetic vegetation- add any that are missing
changeDirDict = {
    "blue": 1,
    "green": 1,
    "red": 1,
    "nir": -1,
    "swir1": 1,
    "swir2": 1,
    "temp": 1,
    "NDVI": -1,
    "NBR": -1,
    "NDMI": -1,
    "NDSI": 1,
    "brightness": 1,
    "greenness": -1,
    "wetness": -1,
    "fourth": -1,
    "fifth": 1,
    "sixth": -1,
    "ND_blue_green": -1,
    "ND_blue_red": -1,
    "ND_blue_nir": 1,
    "ND_blue_swir1": -1,
    "ND_blue_swir2": -1,
    "ND_green_red": -1,
    "ND_green_nir": 1,
    "ND_green_swir1": -1,
    "ND_green_swir2": -1,
    "ND_red_swir1": -1,
    "ND_red_swir2": -1,
    "ND_nir_red": -1,
    "ND_nir_swir1": -1,
    "ND_nir_swir2": -1,
    "ND_swir1_swir2": -1,
    "R_swir1_nir": 1,
    "R_red_swir1": -1,
    "EVI": -1,
    "SAVI": -1,
    "IBI": 1,
    "tcAngleBG": -1,
    "tcAngleGW": -1,
    "tcAngleBW": -1,
    "tcDistBG": 1,
    "tcDistGW": 1,
    "tcDistBW": 1,
    "NIRv": -1,
    "NDCI": -1,
    "NDGI": -1,
}


# Precomputed cloudscore offsets and TDOM stats
# These have been pre-computed for all CONUS for Landsat and Setinel 2 (separately)
# and are appropriate to use for any time period within the growing season
# The cloudScore offset is generally some lower percentile of cloudScores on a pixel-wise basis
# The TDOM stats are the mean and standard deviations of the two bands used in TDOM
# By default, TDOM uses the nir and swir1 bands
preComputedCloudScoreOffset = ee.ImageCollection("projects/lcms-tcc-shared/assets/CS-TDOM-Stats/cloudScore").mosaic()
preComputedTDOMStats = ee.ImageCollection("projects/lcms-tcc-shared/assets/CS-TDOM-Stats/TDOM").filter(ee.Filter.eq("endYear", 2019)).mosaic().divide(10000)


def getPrecomputedCloudScoreOffsets(cloudScorePctl=10):
    return {
        "landsat": preComputedCloudScoreOffset.select(["Landsat_CloudScore_p{}".format(cloudScorePctl)]),
        "sentinel2": preComputedCloudScoreOffset.select(["Sentinel2_CloudScore_p{}".format(cloudScorePctl)]),
    }


def getPrecomputedTDOMStats():
    return {
        "landsat": {
            "mean": preComputedTDOMStats.select(["Landsat_nir_mean", "Landsat_swir1_mean"]),
            "stdDev": preComputedTDOMStats.select(["Landsat_nir_stdDev", "Landsat_swir1_stdDev"]),
        },
        "sentinel2": {
            "mean": preComputedTDOMStats.select(["Sentinel2_nir_mean", "Sentinel2_swir1_mean"]),
            "stdDev": preComputedTDOMStats.select(["Sentinel2_nir_stdDev", "Sentinel2_swir1_stdDev"]),
        },
    }


######################################################################
# FUNCTIONS
######################################################################
######################################################################
# Function to asynchronously print ee objects
def printEE(eeObject, message=""):
    def printIt(eeObject):
        print(message, eeObject.getInfo())
        print()

    t = Thread(target=printIt, args=(eeObject,))
    t.start()


######################################################################
######################################################################
# Function to set null value for export or conversion to arrays
def setNoData(image: ee.Image, noDataValue: float) -> ee.Image:
    """Sets null values for an image.

    Args:
        image: The input Earth Engine image.
        noDataValue: The value to assign to null pixels.

    Returns:
        An Earth Engine image with null pixels set to the specified noDataValue.
    """
    image = image.unmask(noDataValue, False)  # .set('noDataValue', noDataValue)
    return image  # .set(args)


######################################################################
######################################################################
# Formats arguments as strings so can be easily set as properties
def formatArgs(args: dict) -> dict:
    """Formats arguments as strings for setting as image properties.

    Args:
        args: A dictionary of arguments.

    Returns:
        A dictionary of formatted arguments.
    """
    formattedArgs = {}
    for key in args.keys():
        if type(args[key]) in [bool, list, dict, type(None)]:
            formattedArgs[key] = str(args[key])
        elif type(args[key]) in [str, int]:
            formattedArgs[key] = args[key]
    return formattedArgs


######################################################################
######################################################################
# Functions to perform basic clump and elim
def sieve(image: ee.Image, mmu: float) -> ee.Image:
    """Performs clumping and elimination on an image.

    Args:
        image: The input Earth Engine image.
        mmu: The minimum mapping unit.

    Returns:
        An Earth Engine image with clumping and elimination applied.
    """
    args = formatArgs(locals())
    connected = image.connectedPixelCount(mmu + 20)
    # Map.addLayer(connected,{'min':1,'max':mmu},'connected')
    elim = connected.gt(mmu)
    mode = image.focal_mode(mmu / 2, "circle")
    mode = mode.mask(image.mask())
    filled = image.where(elim.Not(), mode)
    return filled.set("mmu", mmu).set(args)


# Written by Yang Z.
# ------ L8 to L7 HARMONIZATION FUNCTION -----
# slope and intercept citation: Roy, D.P., Kovalskyy, V., Zhang, H.K., Vermote, E.F., Yan, L., Kumar, S.S, Egorov, A., 2016, Characterization of Landsat-7 to Landsat-8 reflective wavelength and normalized difference vegetation index continuity, Remote Sensing of Environment, 185, 57-70.(http://dx.doi.org/10.1016/j.rse.2015.12.024); Table 2 - reduced major axis (RMA) regression coefficients
def harmonizationRoy(oli: ee.Image) -> ee.Image:
    """Harmonizes Landsat 8 OLI to Landsat 7 ETM+ using Roy et al. (2016) coefficients.

    Args:
        oli: A Landsat 8 OLI image.

    Returns:
        A harmonized Landsat 8 OLI image.
    """
    slopes = ee.Image.constant([0.9785, 0.9542, 0.9825, 1.0073, 1.0171, 0.9949])  # create an image of slopes per band for L8 TO L7 regression line - David Roy
    itcp = ee.Image.constant([-0.0095, -0.0016, -0.0022, -0.0021, -0.0030, 0.0029])  # create an image of y-intercepts per band for L8 TO L7 regression line - David Roy
    bns = oli.bandNames()
    includeBns = ["blue", "green", "red", "nir", "swir1", "swir2"]
    otherBns = bns.removeAll(includeBns)

    # create an image of y-intercepts per band for L8 TO L7 regression line - David Roy
    y = oli.select(includeBns).float().subtract(itcp).divide(slopes).set("system:time_start", oli.get("system:time_start"))
    y = y.addBands(oli.select(otherBns)).select(bns)
    return y.float()


####################################################################
# Code to implement OLI/ETM/MSI regression
# Chastain et al 2018 coefficients
# Empirical cross sensor comparison of Sentinel-2A and 2B MSI, Landsat-8 OLI, and Landsat-7 ETM+ top of atmosphere spectral characteristics over the conterminous United States
# https://www.sciencedirect.com/science/article/pii/S0034425718305212#t0020
# Left out 8a coefficients since all sensors need to be cross- corrected with bands common to all sensors
# Dependent and Independent variables can be switched since Major Axis (Model 2) linear regression was used
chastainBandNames = ["blue", "green", "red", "nir", "swir1", "swir2"]

# From Table 4
# msi = oli*slope+intercept
# oli = (msi-intercept)/slope
msiOLISlopes = [1.0946, 1.0043, 1.0524, 0.8954, 1.0049, 1.0002]
msiOLIIntercepts = [-0.0107, 0.0026, -0.0015, 0.0033, 0.0065, 0.0046]

# From Table 5
# msi = etm*slope+intercept
# etm = (msi-intercept)/slope
msiETMSlopes = [1.10601, 0.99091, 1.05681, 1.0045, 1.03611, 1.04011]
msiETMIntercepts = [-0.0139, 0.00411, -0.0024, -0.0076, 0.00411, 0.00861]

# From Table 6
# oli = etm*slope+intercept
# etm = (oli-intercept)/slope
oliETMSlopes = [1.03501, 1.00921, 1.01991, 1.14061, 1.04351, 1.05271]
oliETMIntercepts = [-0.0055, -0.0008, -0.0021, -0.0163, -0.0045, 0.00261]

# Construct dictionary to handle all pairwise combos
chastainCoeffDict = {
    "MSI_OLI": [msiOLISlopes, msiOLIIntercepts, 1],
    "MSI_ETM": [msiETMSlopes, msiETMIntercepts, 1],
    "OLI_ETM": [oliETMSlopes, oliETMIntercepts, 1],
    "OLI_MSI": [msiOLISlopes, msiOLIIntercepts, 0],
    "ETM_MSI": [msiETMSlopes, msiETMIntercepts, 0],
    "ETM_OLI": [oliETMSlopes, oliETMIntercepts, 0],
}


# Function to apply model in one direction
def dir0Regression(img, slopes, intercepts):
    bns = img.bandNames()
    nonCorrectBands = bns.removeAll(chastainBandNames)
    nonCorrectedBands = img.select(nonCorrectBands)
    corrected = img.select(chastainBandNames).multiply(slopes).add(intercepts)
    out = corrected.addBands(nonCorrectedBands).select(bns)
    return out


# Applying the model in the opposite direction
def dir1Regression(img, slopes, intercepts):
    bns = img.bandNames()
    nonCorrectBands = bns.removeAll(chastainBandNames)
    nonCorrectedBands = img.select(nonCorrectBands)
    corrected = img.select(chastainBandNames).subtract(intercepts).divide(slopes)
    out = corrected.addBands(nonCorrectedBands).select(bns)
    return out


# Function to correct one sensor to another
def harmonizationChastain(img: ee.Image, fromSensor: str, toSensor: str) -> ee.Image:
    """Harmonizes Landsat images using Chastain et al. (2018) coefficients.

    Args:
        img: The input Landsat image.
        fromSensor: The sensor of the input image (e.g., 'OLI', 'ETM+').
        toSensor: The target sensor for harmonization (e.g., 'OLI', 'ETM+').

    Returns:
        A harmonized Landsat image.
    """
    args = formatArgs(locals())

    # Get the model for the given from and to sensor
    comboKey = fromSensor.upper() + "_" + toSensor.upper()
    coeffList = chastainCoeffDict[comboKey]
    slopes = coeffList[0]
    intercepts = coeffList[1]
    direction = ee.Number(coeffList[2])

    # Apply the model in the respective direction
    out = ee.Algorithms.If(
        direction.eq(0),
        dir0Regression(img, slopes, intercepts),
        dir1Regression(img, slopes, intercepts),
    )
    out = ee.Image(out).copyProperties(img).copyProperties(img, ["system:time_start"])
    out = out.set({"fromSensor": fromSensor, "toSensor": toSensor}).set(args)
    return ee.Image(out)


####################################################################
# Function to create a multiband image from a collection
def collectionToImage(collection: ee.ImageCollection) -> ee.Image:
    """Deprecated - use `.toBands()`. Converts an image collection to a multiband image.

    Args:
        collection: The input Earth Engine image collection.

    Returns:
        A multiband Earth Engine image.
    """

    def cIterator(img, prev):
        return ee.Image(prev).addBands(img)

    stack = ee.Image(collection.iterate(cIterator, ee.Image(1)))
    stack = stack.select(ee.List.sequence(1, stack.bandNames().size().subtract(1)))
    return stack


####################################################################
####################################################################
# Function to find the date for a given composite computed from a given set of images
# Will work on composites computed with methods that include different dates across different bands
# such as the median.  For something like a medoid, only a single bands needs passed through
# A known bug is that if the same value occurs twice, it will choose only a single date
def compositeDates(images: ee.ImageCollection, composite: ee.Image, bandNames: list = None) -> ee.Image:
    """Finds the dates corresponding to bands in a composite image.

    Args:
        images: The original image collection.
        composite: The composite image.
        bandNames: Optional list of band names to consider.

    Returns:
        An Earth Engine image with date information for each band.
    """
    if bandNames == None:
        bandNames = ee.Image(images.first()).bandNames()
    else:
        images = images.select(bandNames)
        composite = composite.select(bandNames)

    def bnCat(bn):
        return ee.String(bn).cat("_diff")

    bns = ee.Image(images.first()).bandNames().map(bnCat)

    # Function to get the abs diff from a given composite *-1
    def getDiff(img):
        out = img.subtract(composite).abs().multiply(-1).rename(bns)
        return img.addBands(out)

    # Find the diff and add a date band
    images = images.map(getDiff)
    images = images.map(addDateBand)

    # Iterate across each band and find the corresponding date to the composite
    def bnCat2(bn):
        bn = ee.String(bn)
        t = images.select([bn, bn.cat("_diff"), "year"]).qualityMosaic(bn.cat("_diff"))
        return t.select(["year"]).rename(["YYYYDD"])

    out = bandNames.map(bnCat2)

    # Convert to an image and rename
    out = collectionToImage(ee.ImageCollection(out))
    # var outBns = bandNames.map(function(bn){return ee.String(bn).cat('YYYYDD')});
    # out = out.rename(outBns);

    return out


############################################################################
# Function to handle empty collections that will cause subsequent processes to fail
# If the collection is empty, will fill it with an empty image
def fillEmptyCollections(inCollection: ee.ImageCollection, dummyImage: ee.Image) -> ee.ImageCollection:
    """Fills empty image collections with a dummy image. This handles empty collections that will cause subsequent processes to fail.

    Args:
        inCollection: The input Earth Engine image collection.
        dummyImage: A dummy Earth Engine image.

    Returns:
        The input image collection or a collection containing the dummy image if empty.
    """
    dummyCollection = ee.ImageCollection([dummyImage.mask(ee.Image(0))])
    imageCount = inCollection.toList(1).length()
    return ee.ImageCollection(ee.Algorithms.If(imageCount.gt(0), inCollection, dummyCollection))


############################################################################
# Add band tracking which satellite the pixel came from
def addSensorBand(img: ee.Image, whichProgram: str, toaOrSR: str) -> ee.Image:
    """Adds a sensor band to an image.

    Args:
        img: The input Earth Engine image.
        whichProgram: The program (e.g., 'C1_landsat', "C2_landsat", 'sentinel2').
        toaOrSR: Whether the image is TOA or SR.

    Returns:
        The input image with an added sensor band.
    """
    sensorDict = ee.Dictionary(
        {
            "LANDSAT_4": 4,
            "LANDSAT_5": 5,
            "LANDSAT_7": 7,
            "LANDSAT_8": 8,
            "LANDSAT_9": 9,
            "Sentinel-2A": 21,
            "Sentinel-2B": 22,
            "Sentinel-2C": 23,
        }
    )
    sensorPropDict = ee.Dictionary(
        {
            "C1_landsat": {"TOA": "SPACECRAFT_ID", "SR": "SATELLITE"},
            "C2_landsat": {"TOA": "SPACECRAFT_ID", "SR": "SPACECRAFT_ID"},
            "sentinel2": {"TOA": "SPACECRAFT_NAME", "SR": "SPACECRAFT_NAME"},
        }
    )
    toaOrSR = toaOrSR.upper()
    sensorProp = ee.Dictionary(sensorPropDict.get(whichProgram)).get(toaOrSR)
    sensorName = img.get(sensorProp)
    img = img.addBands(ee.Image.constant(sensorDict.get(sensorName)).rename(["sensor"]).byte()).set("sensor", sensorName)
    return img


############################################################################
############################################################################
# Adds the float year with julian proportion to image
def addDateBand(img: ee.Image, maskTime: bool = False) -> ee.Image:
    """Adds a date band to an image.

    Args:
        img: The input Earth Engine image.
        maskTime: Whether to mask the date band based on the image mask.

    Returns:
        The input image with an added date band.
    """
    d = ee.Date(img.get("system:time_start"))
    y = d.get("year")
    d = y.add(d.getFraction("year"))
    # d=d.getFraction('year')
    db = ee.Image.constant(d).rename(["year"]).float()
    if maskTime:
        db = db.updateMask(img.select([0]).mask())
    return img.addBands(db)


def addYearFractionBand(img: ee.Image) -> ee.Image:
    """Adds a year fraction band to an image.

    Args:
        img: The input Earth Engine image.

    Returns:
        The input image with an added year fraction band.
    """
    d = ee.Date(img.get("system:time_start"))
    y = d.get("year")
    # d = y.add(d.getFraction('year'));
    d = d.getFraction("year")
    db = ee.Image.constant(d).rename(["year"]).float()
    db = db  # .updateMask(img.select([0]).mask())
    return img.addBands(db)


def addYearYearFractionBand(img: ee.Image) -> ee.Image:
    """Adds a year and year fraction band to an image.

    Args:
        img: The input Earth Engine image.

    Returns:
        The input image with an added year and year fraction band.
    """
    d = ee.Date(img.get("system:time_start"))
    y = d.get("year")
    # d = y.add(d.getFraction('year'));
    d = d.getFraction("year")
    db = ee.Image.constant(y).add(ee.Image.constant(d)).rename(["year"]).float()
    db = db  # .updateMask(img.select([0]).mask())
    return img.addBands(db)


def addYearBand(img: ee.Image) -> ee.Image:
    """Adds a year band to an image.

    Args:
        img: The input Earth Engine image.

    Returns:
        The input image with an added year band.
    """
    d = ee.Date(img.get("system:time_start"))
    y = d.get("year")

    db = ee.Image.constant(y).rename(["year"]).float()
    db = db  # .updateMask(img.select([0]).mask())
    return img.addBands(db)


def addJulianDayBand(img: ee.Image) -> ee.Image:
    """Adds a Julian day band to an image.

    Args:
        img: The input Earth Engine image.

    Returns:
        The input image with an added Julian day band.
    """
    d = ee.Date(img.get("system:time_start"))
    julian = ee.Image(ee.Number.parse(d.format("DD"))).rename(["julianDay"])

    return img.addBands(julian).float()


def addYearJulianDayBand(img: ee.Image) -> ee.Image:
    """Adds a year and Julian day band to an image.

    Args:
        img: The input Earth Engine image.

    Returns:
        The input image with an added year and Julian day band.
    """
    d = ee.Date(img.get("system:time_start"))
    yj = ee.Image(ee.Number.parse(d.format("YYDD"))).rename(["yearJulian"])
    return img.addBands(yj).float()


def addFullYearJulianDayBand(img: ee.Image) -> ee.Image:
    """Adds a full year Julian day band to an image.

    Args:
        img: The input Earth Engine image.

    Returns:
        The input image with an added full year Julian day band.
    """
    d = ee.Date(img.get("system:time_start"))
    yj = ee.Image(ee.Number.parse(d.format("YYYYDD"))).rename(["yearJulian"]).int64()

    return img.addBands(yj).float()


def offsetImageDate(img: ee.Image, n: int, unit: str) -> ee.Image:
    """Offsets the date of an image.

    Args:
        img: The input Earth Engine image.
        n: The number of units to offset.
        unit: The unit of the offset (e.g., 'year', 'month', 'day').

    Returns:
        The image with an offset date.
    """
    date = ee.Date(img.get("system:time_start"))
    date = date.advance(n, unit)
    # date = ee.Date.fromYMD(100,date.get('month'),date.get('day'))
    return img.set("system:time_start", date.millis())


################################################################
################################################################
fringeCountThreshold = 279  # Define number of non null observations for pixel to not be classified as a fringe
################################################################
# Kernel used for defringing
k = ee.Kernel.fixed(
    41,
    41,
    [
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
    ],
)


################################################################
# Algorithm to defringe Landsat scenes
def defringeLandsat(img: ee.Image) -> ee.Image:
    """Defringes a Landsat 7 image.

    Args:
        img: The input Landsat 7 image.

    Returns:
        The defringed Landsat 7 image.
    """
    # Find any pixel without sufficient non null pixels (fringes)
    m = img.mask().reduce(ee.Reducer.min())

    # Apply kernel
    kernelSum = m.reduceNeighborhood(ee.Reducer.sum(), k, "kernel")
    # Map.addLayer(img,vizParams,'with fringes')
    # Map.addLayer(sum,{'min':20,'max':241},'sum41',false)

    # Mask pixels w/o sufficient obs
    kernelSum = kernelSum.gte(fringeCountThreshold)
    img = img.mask(kernelSum)
    # Map.addLayer(img,vizParams,'defringed')
    return img


################################################################
# Function to find unique values of a field in a collection
def uniqueValues(collection: ee.ImageCollection, field: str) -> ee.List:
    """Finds unique values of a field in an image collection.

    Args:
        collection: The input Earth Engine image collection.
        field: The field to extract unique values from.

    Returns:
        A list of unique values.
    """
    values = ee.Dictionary(collection.reduceColumns(ee.Reducer.frequencyHistogram(), [field]).get("histogram")).keys()
    return values


###############################################################
# Function to simplify data into daily mosaics
# This procedure must be used for proper processing of S2 imagery
def dailyMosaics(imgs: ee.ImageCollection) -> ee.ImageCollection:
    """Creates daily mosaics from an image collection.

    Args:
        imgs: The input Earth Engine image collection.

    Returns:
        An Earth Engine image collection containing daily mosaics.
    """

    # Simplify date to exclude time of day
    def propWrapper(img):
        d = img.date().format("YYYY-MM-dd")
        orbit = ee.Number(img.get("SENSING_ORBIT_NUMBER")).format()
        return img.set({"date-orbit": d.cat(ee.String("_")).cat(orbit), "date": d})

    imgs = imgs.map(propWrapper)

    # Find the unique day orbits
    dayOrbits = ee.Dictionary(imgs.aggregate_histogram("date-orbit")).keys()

    def dayWrapper(d):
        date = ee.Date(ee.String(d).split("_").get(0))
        orbit = ee.Number.parse(ee.String(d).split("_").get(1))
        t = imgs.filterDate(date, date.advance(1, "day")).filter(ee.Filter.eq("SENSING_ORBIT_NUMBER", orbit))
        f = ee.Image(t.first())
        t = t.mosaic()
        t = t.set("system:time_start", date.millis())
        t = t.copyProperties(f)
        return t

    imgs = dayOrbits.map(dayWrapper)
    imgs = ee.ImageCollection.fromImages(imgs)

    return imgs


################################################################
# Sentinel 1 processing
# Adapted from: https://code.earthengine.google.com/39a3ad5ac59cd8af14e3dbd78436d2b5
# Author: Warren Scott

# --------------------------------------- DEFINE SPECKLEFUNCTION---------------------------------------------------*/


# Sigma Lee filter
def toNatural(img: ee.Image) -> ee.Image:
    """Converts a Sentinel-1 image from dB to natural units.

    Args:
        img: The input Sentinel-1 image in dB.

    Returns:
        The converted image in natural units.
    """
    return ee.Image(10.0).pow(img.select(0).divide(10.0))


def toDB(img: ee.Image) -> ee.Image:
    """Converts a Sentinel-1 image from natural units to dB.

    Args:
        img: The input Sentinel-1 image in natural units.

    Returns:
        The converted image in dB.
    """
    return ee.Image(img).log10().multiply(10.0)


# The RL speckle filter from https://code.earthengine.google.com/2ef38463ebaf5ae133a478f173fd0ab5 by Guido Lemoine
# As coded in the SNAP 3.0 S1TBX:
def RefinedLee(img: ee.Image) -> ee.Image:
    """Applies the Refined Lee speckle filter to a Sentinel-1 image.

    Args:
        img: The input Sentinel-1 image in natural units.

    Returns:
        The speckle filtered image.
    """
    # img must be in natural units, i.e. not in dB!
    # Set up 3x3 kernels
    weights3 = ee.List.repeat(ee.List.repeat(1, 3), 3)
    kernel3 = ee.Kernel.fixed(3, 3, weights3, 1, 1, False)

    mean3 = img.reduceNeighborhood(ee.Reducer.mean(), kernel3)
    variance3 = img.reduceNeighborhood(ee.Reducer.variance(), kernel3)

    # Use a sample of the 3x3 windows inside a 7x7 windows to determine gradients and directions
    sample_weights = ee.List(
        [
            [0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 1, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 1, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 1, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 0],
        ]
    )

    sample_kernel = ee.Kernel.fixed(7, 7, sample_weights, 3, 3, False)

    # Calculate mean and variance for the sampled windows and store as 9 bands
    sample_mean = mean3.neighborhoodToBands(sample_kernel)
    sample_var = variance3.neighborhoodToBands(sample_kernel)

    # Determine the 4 gradients for the sampled windows
    gradients = sample_mean.select(1).subtract(sample_mean.select(7)).abs()
    gradients = gradients.addBands(sample_mean.select(6).subtract(sample_mean.select(2)).abs())
    gradients = gradients.addBands(sample_mean.select(3).subtract(sample_mean.select(5)).abs())
    gradients = gradients.addBands(sample_mean.select(0).subtract(sample_mean.select(8)).abs())

    # And find the maximum gradient amongst gradient bands
    max_gradient = gradients.reduce(ee.Reducer.max())

    # Create a mask for band pixels that are the maximum gradient
    gradmask = gradients.eq(max_gradient)

    # duplicate gradmask bands: each gradient represents 2 directions
    gradmask = gradmask.addBands(gradmask)

    # Determine the 8 directions
    directions = sample_mean.select(1).subtract(sample_mean.select(4)).gt(sample_mean.select(4).subtract(sample_mean.select(7))).multiply(1)
    directions = directions.addBands(sample_mean.select(6).subtract(sample_mean.select(4)).gt(sample_mean.select(4).subtract(sample_mean.select(2))).multiply(2))
    directions = directions.addBands(sample_mean.select(3).subtract(sample_mean.select(4)).gt(sample_mean.select(4).subtract(sample_mean.select(5))).multiply(3))
    directions = directions.addBands(sample_mean.select(0).subtract(sample_mean.select(4)).gt(sample_mean.select(4).subtract(sample_mean.select(8))).multiply(4))

    # The next 4 are the not() of the previous 4
    directions = directions.addBands(directions.select(0).Not().multiply(5))
    directions = directions.addBands(directions.select(1).Not().multiply(6))
    directions = directions.addBands(directions.select(2).Not().multiply(7))
    directions = directions.addBands(directions.select(3).Not().multiply(8))

    # Mask all values that are not 1-8
    directions = directions.updateMask(gradmask)

    # "collapse" the stack into a singe band image (due to masking, each pixel has just one value (1-8) in it's directional band, and is otherwise masked)
    directions = directions.reduce(ee.Reducer.sum())

    # var pal = ['ffffff','ff0000','ffff00', '00ff00', '00ffff', '0000ff', 'ff00ff', '000000'];
    # Map.addLayer(directions.reduce(ee.Reducer.sum()), {min:1, max:8, palette: pal}, 'Directions', false);

    sample_stats = sample_var.divide(sample_mean.multiply(sample_mean))

    # Calculate localNoiseVariance
    sigmaV = sample_stats.toArray().arraySort().arraySlice(0, 0, 5).arrayReduce(ee.Reducer.mean(), [0])

    # Set up the 7*7 kernels for directional statistics
    rect_weights = ee.List.repeat(ee.List.repeat(0, 7), 3).cat(ee.List.repeat(ee.List.repeat(1, 7), 4))

    diag_weights = ee.List(
        [
            [1, 0, 0, 0, 0, 0, 0],
            [1, 1, 0, 0, 0, 0, 0],
            [1, 1, 1, 0, 0, 0, 0],
            [1, 1, 1, 1, 0, 0, 0],
            [1, 1, 1, 1, 1, 0, 0],
            [1, 1, 1, 1, 1, 1, 0],
            [1, 1, 1, 1, 1, 1, 1],
        ]
    )

    rect_kernel = ee.Kernel.fixed(7, 7, rect_weights, 3, 3, False)
    diag_kernel = ee.Kernel.fixed(7, 7, diag_weights, 3, 3, False)

    # Create stacks for mean and variance using the original kernels. Mask with relevant direction.
    dir_mean = img.reduceNeighborhood(ee.Reducer.mean(), rect_kernel).updateMask(directions.eq(1))
    dir_var = img.reduceNeighborhood(ee.Reducer.variance(), rect_kernel).updateMask(directions.eq(1))

    dir_mean = dir_mean.addBands(img.reduceNeighborhood(ee.Reducer.mean(), diag_kernel).updateMask(directions.eq(2)))
    dir_var = dir_var.addBands(img.reduceNeighborhood(ee.Reducer.variance(), diag_kernel).updateMask(directions.eq(2)))

    # and add the bands for rotated kernels
    for i in range(1, 4):
        dir_mean = dir_mean.addBands(img.reduceNeighborhood(ee.Reducer.mean(), rect_kernel.rotate(i)).updateMask(directions.eq(2 * i + 1)))
        dir_var = dir_var.addBands(img.reduceNeighborhood(ee.Reducer.variance(), rect_kernel.rotate(i)).updateMask(directions.eq(2 * i + 1)))
        dir_mean = dir_mean.addBands(img.reduceNeighborhood(ee.Reducer.mean(), diag_kernel.rotate(i)).updateMask(directions.eq(2 * i + 2)))
        dir_var = dir_var.addBands(img.reduceNeighborhood(ee.Reducer.variance(), diag_kernel.rotate(i)).updateMask(directions.eq(2 * i + 2)))

    # "collapse" the stack into a single band image (due to masking, each pixel has just one value in it's directional band, and is otherwise masked)
    dir_mean = dir_mean.reduce(ee.Reducer.sum())
    dir_var = dir_var.reduce(ee.Reducer.sum())

    # A finally generate the filtered value
    varX = dir_var.subtract(dir_mean.multiply(dir_mean).multiply(sigmaV)).divide(sigmaV.add(1.0))

    b = varX.divide(dir_var)

    result = dir_mean.add(b.multiply(img.subtract(dir_mean)))
    return result.arrayFlatten([["sum"]])


################################################################


# Load and filter Sentinel-1 GRD data by predefined parameters
def getS1(
    studyArea: ee.Geometry | ee.Feature | ee.FeatureCollection,
    startYear: int,
    endYear: int,
    startJulian: int,
    endJulian: int,
    polarization: str = "VV",
    pass_direction: str = "ASCENDING",
) -> ee.ImageCollection:
    """Loads Sentinel-1 GRD data for a given area and time period.

    Args:
        studyArea: The geographic area of interest.
        startYear: The start year of the desired data.
        endYear: The end year of the desired data.
        startJulian: The start Julian day of the desired data.
        endJulian: The end Julian day of the desired data.
        polarization: The desired polarization (default: "VV").
        pass_direction: The desired pass direction (default: "ASCENDING").

    Returns:
        An Earth Engine ImageCollection containing the loaded Sentinel-1 data.
    """
    collection = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filter(ee.Filter.calendarRange(startYear, endYear, "year"))
        .filter(ee.Filter.calendarRange(startJulian, endJulian))
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", polarization))
        .filter(ee.Filter.eq("orbitProperties_pass", pass_direction))
        .filter(ee.Filter.eq("resolution_meters", 10))
        .filterBounds(studyArea)
        .select([polarization])
    )

    return collection


################################################################
# Sentinel-2 collections and bands to use
# 3/22 - Changed to using the _HARMONIZED collections following the introduction of a 1000 value offset from Jan 25 2022 onward
# These collections account for these differences
s2CollectionDict = {
    "TOA": "COPERNICUS/S2_HARMONIZED",
    "SR": "COPERNICUS/S2_SR_HARMONIZED",
}

sensorBandDict = {
    "SR": [
        "B1",
        "B2",
        "B3",
        "B4",
        "B5",
        "B6",
        "B7",
        "B8",
        "B8A",
        "B9",
        "B11",
        "B12",
    ],
    "TOA": [
        "B1",
        "B2",
        "B3",
        "B4",
        "B5",
        "B6",
        "B7",
        "B8",
        "B8A",
        "B9",
        "B10",
        "B11",
        "B12",
    ],
}

sensorBandNameDict = {
    "SR": [
        "cb",
        "blue",
        "green",
        "red",
        "re1",
        "re2",
        "re3",
        "nir",
        "nir2",
        "waterVapor",
        "swir1",
        "swir2",
    ],
    "TOA": [
        "cb",
        "blue",
        "green",
        "red",
        "re1",
        "re2",
        "re3",
        "nir",
        "nir2",
        "waterVapor",
        "cirrus",
        "swir1",
        "swir2",
    ],
}


# Function to get Sentinel 2 A and B data into a single collection with meaningful band names for a specified area and date range
# Will also join the S2 cloudless cloud probability collection if specified
def getS2(
    studyArea: ee.Geometry | ee.Feature | ee.FeatureCollection,
    startDate: ee.Date | datetime.datetime | str,
    endDate: ee.Date | datetime.datetime | str,
    startJulian: int = 1,
    endJulian: int = 365,
    resampleMethod: str = "nearest",
    toaOrSR: str = "TOA",
    convertToDailyMosaics: bool = True,
    addCloudProbability: bool = False,
    addCloudScorePlus: bool = True,
    cloudScorePlusScore: str = "cs",
) -> ee.ImageCollection:
    """Loads Sentinel-2 data for a given area and time period and joins cloud score information. Partially deprecated in favor of the simpler superSimpleGetS2.

    Args:
        studyArea: The geographic area of interest.
        startDate: The start date of the desired data. Can be an ee.Date object, datetime object, or date string.
        endDate: The end date of the desired data. Can be an ee.Date object, datetime object, or date string.
        startJulian: The start Julian day of the desired data.
        endJulian: The end Julian day of the desired data.
        resampleMethod: The resampling method (default: "nearest").
        toaOrSR: Whether to load TOA or SR data (default: "TOA").
        convertToDailyMosaics: Whether to convert the data to daily mosaics (default: True).
        addCloudProbability: Whether to add cloud probability data (default: False).
        addCloudScorePlus: Whether to add cloud score plus data (default: True).
        cloudScorePlusScore: The band name for cloud score plus (default: "cs").

    Returns:
        ee.ImageCollection: A collection of Sentinel-2 satellite images filtered by the specified criteria.


    >>> import geeViz.getImagesLib as gil
    >>> Map = gil.Map
    >>> ee = gil.ee
    >>> studyArea = gil.testAreas["CA"]
    >>> composite = gil.getS2(studyArea, "2024-01-01", "2024-12-31", 190, 250).median()
    >>> Map.addLayer(composite, gil.vizParamsFalse, "Sentinel-2 Composite")
    >>> Map.addLayer(studyArea, {"canQuery": False}, "Study Area")
    >>> Map.centerObject(studyArea)
    >>> Map.turnOnInspector()
    >>> Map.view()

    """
    args = formatArgs(locals())

    toaOrSR = toaOrSR.upper()
    startDate = ee.Date(startDate)
    endDate = ee.Date(endDate)

    # Specify S2 continuous bands if resampling is set to something other than near
    s2_continuous_bands = sensorBandNameDict[toaOrSR]

    def multS2(img):
        t = img.select(sensorBandDict[toaOrSR]).divide(10000)
        # t = t.addBands(img.select(['QA60']))
        # out = t.copyProperties(img).copyProperties(img,['system:time_start'])
        return img.addBands(t, None, True)

    # Get some s2 data
    print("Using S2 Collection:", s2CollectionDict[toaOrSR])
    s2s = (
        ee.ImageCollection(s2CollectionDict[toaOrSR])
        .filterDate(startDate, endDate.advance(1, "day"))
        .filter(ee.Filter.calendarRange(startJulian, endJulian))
        .filterBounds(studyArea)
        .map(multS2)
        .select(["QA60"] + sensorBandDict[toaOrSR], ["QA60"] + sensorBandNameDict[toaOrSR])
    )

    if addCloudProbability:
        print("Joining pre-computed cloud probabilities from: COPERNICUS/S2_CLOUD_PROBABILITY")
        cloudProbabilities = (
            ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY")
            # .filterDate(startDate, endDate.advance(1, "day"))
            # .filter(ee.Filter.calendarRange(startJulian, endJulian))
            # .filterBounds(studyArea)
            .select(["probability"], ["cloud_probability"])
        )

        cloudProbabilitiesIds = ee.List(ee.Dictionary(cloudProbabilities.aggregate_histogram("system:index")).keys())
        s2sIds = ee.List(ee.Dictionary(s2s.aggregate_histogram("system:index")).keys())
        missing = s2sIds.removeAll(cloudProbabilitiesIds)
        # print('Missing cloud probability ids:', missing.getInfo())
        # print('N s2 images before joining with cloud prob:', s2s.size().getInfo())
        # s2s = joinCollections(s2s, cloudProbabilities, False, "system:index")
        s2s = s2s.linkCollection(cloudProbabilities, ["cloud_probability"])
        # print('N s2 images after joining with cloud prob:', s2s.size().getInfo())

    if addCloudScorePlus:
        print("Joining pre-computed cloudScore+ from: GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
        cloudScorePlus = (
            ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
            # .filterDate(startDate, endDate.advance(1, "day"))
            # .filter(ee.Filter.calendarRange(startJulian, endJulian))
            # .filterBounds(studyArea)
            .select([cloudScorePlusScore], ["cloudScorePlus"])
        )

        cloudScorePlusIds = ee.List(ee.Dictionary(cloudScorePlus.aggregate_histogram("system:index")).keys())

        s2sIds = ee.List(ee.Dictionary(s2s.aggregate_histogram("system:index")).keys())
        missing = s2sIds.removeAll(cloudScorePlus)
        # print('Missing cloud probability ids:', missing.getInfo())
        # print('N s2 images before joining with cloudScore+:', s2s.size().getInfo())
        # s2s = joinCollections(s2s, cloudScorePlus, False, "system:index")
        s2s = s2s.linkCollection(cloudScorePlus, ["cloudScorePlus"])
        # print('N s2 images after joining with cloud prob:', s2s.size().getInfo())

    # Set resampling method - only sets to non nearest-neighbor for continuous bands
    if resampleMethod == "bilinear" or resampleMethod == "bicubic":
        print("Setting resample method to ", resampleMethod)
        s2s = s2s.map(lambda img: img.addBands(img.select(s2_continuous_bands).resample(resampleMethod), None, True))
    elif resampleMethod == "aggregate":
        print("Setting to aggregate instead of resample ")
        s2s = s2s.map(
            lambda img: img.addBands(
                img.select(s2_continuous_bands).reduceResolution(ee.Reducer.mean(), True, 64),
                None,
                True,
            )
        )

    # Convert to daily mosaics to avoid redundant observations in MGRS overlap areas and edge artifacts for shadow masking
    if convertToDailyMosaics:
        print("Converting S2 data to daily mosaics")
        s2s = dailyMosaics(s2s)

    # This needs to occur AFTER the mosaicking to remove remaining edge artifacts.
    # Update on 15 May 2024 to only include spectral bands since qa bands are null after ~Feb 2024
    s2s = s2s.map(lambda img: img.updateMask(img.select(sensorBandNameDict[toaOrSR]).mask().reduce(ee.Reducer.min())))

    return s2s.set(args)


getSentinel2 = getS2
##################################################################
# Set up dictionaries to manage various Landsat collections, rescale factors, band names, etc
landsat_C2_L2_rescale_dict = {
    "C1": {"refl_mult": 0.0001, "refl_add": 0, "temp_mult": 0.1, "temp_add": 0},
    "C2": {
        "refl_mult": 0.0000275,
        "refl_add": -0.2,
        "temp_mult": 0.00341802,
        "temp_add": 149.0,
    },
}
# Specify Landsat continuous bands if resampling is set to something other than near
landsat_continuous_bands = ["blue", "green", "red", "nir", "swir1", "temp", "swir2"]
# Set up bands and corresponding band names
landsatSensorBandDict = {
    "C1_L4_TOA": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "BQA"],
    "C2_L4_TOA": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "QA_PIXEL"],
    "C1_L5_TOA": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "BQA"],
    "C2_L5_TOA": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "QA_PIXEL"],
    "C1_L7_TOA": ["B1", "B2", "B3", "B4", "B5", "B6_VCID_1", "B7", "BQA"],
    "C2_L7_TOA": ["B1", "B2", "B3", "B4", "B5", "B6_VCID_1", "B7", "QA_PIXEL"],
    "C1_L8_TOA": ["B2", "B3", "B4", "B5", "B6", "B10", "B7", "BQA"],
    "C2_L8_TOA": ["B2", "B3", "B4", "B5", "B6", "B10", "B7", "QA_PIXEL"],
    "C2_L9_TOA": ["B2", "B3", "B4", "B5", "B6", "B10", "B7", "QA_PIXEL"],
    "C1_L4_SR": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "pixel_qa"],
    "C2_L4_SR": [
        "SR_B1",
        "SR_B2",
        "SR_B3",
        "SR_B4",
        "SR_B5",
        "ST_B6",
        "SR_B7",
        "QA_PIXEL",
    ],
    "C1_L5_SR": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "pixel_qa"],
    "C2_L5_SR": [
        "SR_B1",
        "SR_B2",
        "SR_B3",
        "SR_B4",
        "SR_B5",
        "ST_B6",
        "SR_B7",
        "QA_PIXEL",
    ],
    "C1_L7_SR": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "pixel_qa"],
    "C2_L7_SR": [
        "SR_B1",
        "SR_B2",
        "SR_B3",
        "SR_B4",
        "SR_B5",
        "ST_B6",
        "SR_B7",
        "QA_PIXEL",
    ],
    "C1_L8_SR": ["B2", "B3", "B4", "B5", "B6", "B10", "B7", "pixel_qa"],
    "C2_L8_SR": [
        "SR_B2",
        "SR_B3",
        "SR_B4",
        "SR_B5",
        "SR_B6",
        "ST_B10",
        "SR_B7",
        "QA_PIXEL",
    ],
    "C2_L9_SR": [
        "SR_B2",
        "SR_B3",
        "SR_B4",
        "SR_B5",
        "SR_B6",
        "ST_B10",
        "SR_B7",
        "QA_PIXEL",
    ],
}

# Provide common band names
landsatSensorBandNameDict = {
    "C1_TOA": ["blue", "green", "red", "nir", "swir1", "temp", "swir2", "BQA"],
    "C1_SR": ["blue", "green", "red", "nir", "swir1", "temp", "swir2", "pixel_qa"],
    "C1_SRFMASK": ["pixel_qa"],
    "C2_TOA": ["blue", "green", "red", "nir", "swir1", "temp", "swir2", "QA_PIXEL"],
    "C2_SR": ["blue", "green", "red", "nir", "swir1", "temp", "swir2", "QA_PIXEL"],
}

# Set up collections
landsatCollectionDict = {
    "C1_L8_TOA": "LANDSAT/LC08/C01/T1",
    "C1_L7_TOA": "LANDSAT/LE07/C01/T1",
    "C1_L5_TOA": "LANDSAT/LT05/C01/T1",
    "C1_L4_TOA": "LANDSAT/LT04/C01/T1",
    "C1_L8_SR": "LANDSAT/LC08/C01/T1_SR",
    "C1_L7_SR": "LANDSAT/LE07/C01/T1_SR",
    "C1_L5_SR": "LANDSAT/LT05/C01/T1_SR",
    "C1_L4_SR": "LANDSAT/LT04/C01/T1_SR",
    "C2_L9_TOA": "LANDSAT/LC09/C02/T1",
    "C2_L8_TOA": "LANDSAT/LC08/C02/T1",
    "C2_L7_TOA": "LANDSAT/LE07/C02/T1",
    "C2_L5_TOA": "LANDSAT/LT05/C02/T1",
    "C2_L4_TOA": "LANDSAT/LT04/C02/T1",
    "C2_L9_SR": "LANDSAT/LC09/C02/T1_L2",
    "C2_L8_SR": "LANDSAT/LC08/C02/T1_L2",
    "C2_L7_SR": "LANDSAT/LE07/C02/T1_L2",
    "C2_L5_SR": "LANDSAT/LT05/C02/T1_L2",
    "C2_L4_SR": "LANDSAT/LT04/C02/T1_L2",
}

# Name of cFmask qa bits band for Collections 1 and 2
landsatFmaskBandNameDict = {"C1": "pixel_qa", "C2": "QA_PIXEL"}


##################################################################
# Method for rescaling reflectance and surface temperature data to 0-1 and Kelvin respectively
# This was adapted from the method provided by Google for rescaling Collection 2:
# https://code.earthengine.google.com/?scriptPath=Examples%3ADatasets%2FLANDSAT_LC08_C02_T1_L2
def applyScaleFactors(image, landsatCollectionVersion):
    factor_dict = landsat_C2_L2_rescale_dict[landsatCollectionVersion]
    opticalBands = image.select("blue", "green", "red", "nir", "swir1", "swir2").multiply(factor_dict["refl_mult"]).add(factor_dict["refl_add"]).float()
    thermalBands = image.select("temp").multiply(factor_dict["temp_mult"]).add(factor_dict["temp_add"]).float()
    return image.addBands(opticalBands, None, True).addBands(thermalBands, None, True)


##################################################################
# Function for acquiring Landsat image collections
def getLandsat(
    studyArea: ee.Geometry | ee.Feature | ee.FeatureCollection,
    startDate: ee.Date | datetime.datetime | str,
    endDate: ee.Date | datetime.datetime | str,
    startJulian: int = 1,
    endJulian: int = 365,
    toaOrSR: str = "SR",
    includeSLCOffL7: bool = False,
    defringeL5: bool = False,
    addPixelQA: bool = False,
    resampleMethod: str = "near",
    landsatCollectionVersion: str = "C2",
):
    """Retrieves Landsat imagery for a specified study area and date range.

    Args:
        studyArea (ee.Geometry, ee.Feature, or ee.FeatureCollection): The geographic area of interest.
        startDate (ee.Date, datetime.datetime, or str): The start date of the desired image range.
        endDate (ee.Date, datetime.datetime, or str): The end date of the desired image range.
        startJulian (int, optional): The start Julian day of the desired image range. Defaults to 1.
        endJulian (int, optional): The end Julian day of the desired image range. Defaults to 365.
        toaOrSR (str, optional): Whether to retrieve TOA or SR data. Defaults to "SR".
        includeSLCOffL7 (bool, optional): Whether to include SLC-off L7 data. Defaults to False.
        defringeL5 (bool, optional): Whether to defringe L5 data. Defaults to False.
        addPixelQA (bool, optional): Whether to add pixel QA band. Defaults to False.
        resampleMethod (str, optional): Resampling method. Options are "near", "bilinear", or "bicubic". Defaults to "near".
        landsatCollectionVersion (str, optional): Landsat collection version. Options are "C1" or "C2". Defaults to "C2".

    Returns:
        ee.ImageCollection: A collection of Landsat images meeting the specified criteria.


    >>> import geeViz.getImagesLib as gil
    >>> Map = gil.Map
    >>> ee = gil.ee
    >>> studyArea = gil.testAreas["CA"]
    >>> composite = gil.getLandsat(studyArea, "2024-01-01", "2024-12-31", 190, 250).median()
    >>> Map.addLayer(composite, gil.vizParamsFalse, "Landsat Composite")
    >>> Map.addLayer(studyArea, {"canQuery": False}, "Study Area")
    >>> Map.centerObject(studyArea)
    >>> Map.turnOnInspector()
    >>> Map.view()

    """
    args = formatArgs(locals())

    toaOrSR = toaOrSR.upper()
    startDate = ee.Date(startDate)
    endDate = ee.Date(endDate)

    def getLandsatCollection(landsatCollectionVersion, whichC, toaOrSR):
        c = (
            ee.ImageCollection(landsatCollectionDict[landsatCollectionVersion + "_" + whichC + "_" + toaOrSR])
            .filterDate(startDate, endDate.advance(1, "day"))
            .filter(ee.Filter.calendarRange(startJulian, endJulian))
            .filterBounds(studyArea)
            .filter(ee.Filter.lte("WRS_ROW", 120))
        )
        if toaOrSR.lower() == "toa":
            c = c.map(ee.Algorithms.Landsat.TOA)

        c = c.select(
            landsatSensorBandDict[landsatCollectionVersion + "_" + whichC + "_" + toaOrSR],
            landsatSensorBandNameDict[landsatCollectionVersion + "_" + toaOrSR],
        )

        if toaOrSR.lower() == "sr":
            print("Applying scale factors for {} {} data".format(landsatCollectionVersion, whichC))
            c = c.map(lambda image: applyScaleFactors(image, landsatCollectionVersion))

        return c

    def getLandsatCollections(toaOrSR, landsatCollectionVersion):
        # Get Landsat data
        l4s = getLandsatCollection(landsatCollectionVersion, "L4", toaOrSR)
        l5s = getLandsatCollection(landsatCollectionVersion, "L5", toaOrSR)

        if defringeL5:
            print("Defringing L4 and L5")
            l4s = l4s.map(defringeLandsat)
            l5s = l5s.map(defringeLandsat)

        l8s = getLandsatCollection(landsatCollectionVersion, "L8", toaOrSR)

        #   var ls; var l7s;
        if includeSLCOffL7:
            print("Including All Landsat 7")
            l7s = getLandsatCollection(landsatCollectionVersion, "L7", toaOrSR)
        else:
            print("Only including SLC On Landsat 7")
            l7s = getLandsatCollection(landsatCollectionVersion, "L7", toaOrSR).filterDate(
                ee.Date.fromYMD(1998, 1, 1),
                ee.Date.fromYMD(2003, 5, 31).advance(1, "day"),
            )
        # Merge collections
        ls = ee.ImageCollection(l4s.merge(l5s).merge(l7s).merge(l8s))

        # Bring in Landsat 9 if using Collection 2
        if landsatCollectionVersion.lower() == "c2":
            l9s = getLandsatCollection(landsatCollectionVersion, "L9", toaOrSR)
            ls = ee.ImageCollection(ls.merge(l9s))

        return ls

    ls = getLandsatCollections(toaOrSR, landsatCollectionVersion)
    # If TOA and Fmask need to merge Fmask qa bits with toa- this gets the qa band from the sr collections
    if toaOrSR.lower() == "toa" and addPixelQA and landsatCollectionVersion.lower() == "c1":
        print("Acquiring SR qa bands for applying Fmask to TOA data")
        l4sTOAFMASK = (
            ee.ImageCollection(landsatCollectionDict["C1_L4_SR"])
            .filterDate(startDate, endDate.advance(1, "day"))
            .filter(ee.Filter.calendarRange(startJulian, endJulian))
            .filterBounds(studyArea)
            .filter(ee.Filter.lte("WRS_ROW", 120))
            .select(landsatSensorBandNameDict["C1_SRFMASK"])
        )

        l5sTOAFMASK = (
            ee.ImageCollection(landsatCollectionDict["C1_L5_SR"])
            .filterDate(startDate, endDate.advance(1, "day"))
            .filter(ee.Filter.calendarRange(startJulian, endJulian))
            .filterBounds(studyArea)
            .filter(ee.Filter.lte("WRS_ROW", 120))
            .select(landsatSensorBandNameDict["C1_SRFMASK"])
        )

        l8sTOAFMASK = (
            ee.ImageCollection(landsatCollectionDict["C1_L8_SR"])
            .filterDate(startDate, endDate.advance(1, "day"))
            .filter(ee.Filter.calendarRange(startJulian, endJulian))
            .filterBounds(studyArea)
            .filter(ee.Filter.lte("WRS_ROW", 120))
            .select(landsatSensorBandNameDict["C1_SRFMASK"])
        )

        if includeSLCOffL7:
            print("Including All Landsat 7 for TOA QA")
            l7sTOAFMASK = (
                ee.ImageCollection(landsatCollectionDict["C1_L7_SR"])
                .filterDate(startDate, endDate.advance(1, "day"))
                .filter(ee.Filter.calendarRange(startJulian, endJulian))
                .filterBounds(studyArea)
                .filter(ee.Filter.lte("WRS_ROW", 120))
                .select(landsatSensorBandNameDict["C1_SRFMASK"])
            )
        else:
            print("Only including SLC On Landsat 7 for TOA QA")
            l7sTOAFMASK = (
                ee.ImageCollection(landsatCollectionDict["C1_L7_SR"])
                .filterDate(
                    ee.Date.fromYMD(1998, 1, 1),
                    ee.Date.fromYMD(2003, 5, 31).advance(1, "day"),
                )
                .filterDate(startDate, endDate.advance(1, "day"))
                .filter(ee.Filter.calendarRange(startJulian, endJulian))
                .filterBounds(studyArea)
                .filter(ee.Filter.lte("WRS_ROW", 120))
                .select(landsatSensorBandNameDict["C1_SRFMASK"])
            )

        lsTOAFMASK = ee.ImageCollection(l4sTOAFMASK.merge(l5sTOAFMASK).merge(l7sTOAFMASK).merge(l8sTOAFMASK))

        # Join the TOA with SR QA bands
        print("Joining TOA with SR QA bands")
        # print(ls.size(), lsTOAFMASK.size())
        ls = joinCollections(ls.select([0, 1, 2, 3, 4, 5, 6]), lsTOAFMASK, False, "system:index")
        # lsTOAFMASK = getLandsat('SR').select(['pixel_qa'])
        # #Join the TOA with SR QA bands
        # print('Joining TOA with SR QA bands')
        # ls = joinCollections(ls.select([0,1,2,3,4,5,6]),lsTOAFMASK)

    def dataInAllBands(img):
        return img.updateMask(img.select(["blue", "green", "red", "nir", "swir1", "swir2"]).mask().reduce(ee.Reducer.min()))
        # return img.multiply(multImageDict[toaOrSR]).copyProperties(img,['system:time_start']).copyProperties(img)

    # Make sure all bands have data
    ls = ls.map(dataInAllBands)

    # Set resampling method - only sets to non nearest-neighbor for continuous bands
    def setResample(img):
        return img.resample(resampleMethod)

    if resampleMethod in ["bilinear", "bicubic"]:
        print("Setting resample method to ", resampleMethod)
        ls = ls.map(
            lambda img: img.addBands(
                img.select(landsat_continuous_bands).resample(resampleMethod),
                None,
                True,
            )
        )
    elif resampleMethod == "aggregate":
        print("Setting to aggregate instead of resample ")
        ls = ls.map(
            lambda img: img.addBands(
                img.select(landsat_continuous_bands).reduceResolution(ee.Reducer.mean(), True, 64),
                None,
                True,
            )
        )

    return ls.set(args)


getImageCollection = getLandsat


###########################################################################
# Helper function to apply an expression and linearly rescale the output.
# Used in the landsatCloudScore function below.
def rescale(img: ee.Image, thresholds: tuple) -> ee.Image:
    """Rescales pixel values in an image using a min-max normalization.

    Args:
        img: The input Earth Engine image.
        thresholds: A tuple containing the minimum and maximum values for rescaling.

    Returns:
        A rescaled Earth Engine image.
    """
    return img.subtract(thresholds[0]).divide(thresholds[1] - thresholds[0])


###########################################################################
# /***
#  * Implementation of Basic cloud shadow shift
#  *
#  * Author: Gennadii Donchyts
#  * License: Apache 2.0
#  */
# Cloud heights added by Ian Housman
# yMult bug fix adapted from code written by Noel Gorelick by Ian Housman
def projectShadows(
    cloudMask,
    image,
    irSumThresh,
    contractPixels,
    dilatePixels,
    cloudHeights,
    yMult=None,
):
    if yMult == None:
        yMult = ee.Algorithms.If(
            ee.Algorithms.IsEqual(image.select([3]).projection(), ee.Projection("EPSG:4326")),
            1,
            -1,
        )

    meanAzimuth = image.get("MEAN_SOLAR_AZIMUTH_ANGLE")
    meanZenith = image.get("MEAN_SOLAR_ZENITH_ANGLE")
    ##################################################
    # print('a',meanAzimuth)
    # print('z',meanZenith)

    # Find dark pixels
    darkPixels = image.select(["nir", "swir1", "swir2"]).reduce(ee.Reducer.sum()).lt(irSumThresh).focal_min(contractPixels).focal_max(dilatePixels)
    # .gte(1)

    # Get scale of image
    nominalScale = cloudMask.projection().nominalScale()
    # Find where cloud shadows should be based on solar geometry
    # Convert to radians
    azR = ee.Number(meanAzimuth).add(180).multiply(Math.PI).divide(180.0)
    zenR = ee.Number(meanZenith).multiply(Math.PI).divide(180.0)

    def castShadows(cloudHeight):
        cloudHeight = ee.Number(cloudHeight)
        shadowCastedDistance = zenR.tan().multiply(cloudHeight)  # Distance shadow is cast
        x = azR.sin().multiply(shadowCastedDistance).divide(nominalScale)  # X distance of shadow
        y = azR.cos().multiply(shadowCastedDistance).divide(nominalScale).multiply(yMult)
        # Y distance of shadow
        return cloudMask.changeProj(cloudMask.projection(), cloudMask.projection().translate(x, y))

    # Find the shadows
    shadows = cloudHeights.map(castShadows)

    shadowMask = ee.ImageCollection.fromImages(shadows).max()

    # Create shadow mask
    shadowMask = shadowMask.And(cloudMask.Not())
    shadowMask = shadowMask.And(darkPixels).focal_min(contractPixels).focal_max(dilatePixels)
    # Map.addLayer(cloudMask.updateMask(cloudMask),{'min':1,'max':1,'palette':'88F'},'Cloud mask')
    # Map.addLayer(shadowMask.updateMask(shadowMask),{'min':1,'max':1,'palette':'880'},'Shadow mask')

    cloudShadowMask = shadowMask.Or(cloudMask)

    image = image.updateMask(cloudShadowMask.Not()).addBands(shadowMask.rename(["cloudShadowMask"]))
    return image


def projectShadowsWrapper(
    img,
    cloudThresh=20,
    irSumThresh=0.35,
    contractPixels=1.5,
    dilatePixels=3.5,
    cloudHeights=ee.List.sequence(500, 10000, 500),
):

    args = formatArgs(locals())

    cloudMask = sentinel2CloudScore(img).gt(cloudThresh).focal_min(contractPixels).focal_max(dilatePixels)

    img = projectShadows(cloudMask, img, irSumThresh, contractPixels, dilatePixels, cloudHeights)

    return img.set(args)


#########################################################################
#########################################################################
# Function to mask clouds using the Sentinel-2 QA band.
def maskS2clouds(image: ee.Image) -> ee.Image:
    """Masks clouds in a Sentinel-2 image using the QA60 band.

    Args:
        image: The input Sentinel-2 image.

    Returns:
        The cloud-masked image.
    """
    qa = image.select("QA60").int16()

    # Bits 10 and 11 are clouds and cirrus, respectively.
    cloudBitMask = 1 << 10
    cirrusBitMask = 1 << 11

    # Both flags should be set to zero, indicating clear conditions.
    mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))

    # Return the masked and scaled data.
    return image.updateMask(mask)


#########################################################################
#########################################################################
# Compute a cloud score and adds a band that represents the cloud mask.
# This expects the input image to have the common band names:
# ["red", "blue", etc], so it can work across sensors.
def landsatCloudScore(img: ee.Image) -> ee.Image:
    """Computes a cloud score for a Landsat image and adds a band that represents the cloud mask. This expects the input image to have the common band names: ["red", "blue", etc], so it can work across sensors.

    Args:
        img: The input Landsat image.

    Returns:
        An image with a cloud score band.
    """
    # Compute several indicators of cloudiness and take the minimum of them.
    score = ee.Image(1.0)
    # Clouds are reasonably bright in the blue band.
    score = score.min(rescale(img.select(["blue"]), [0.1, 0.3]))

    # Clouds are reasonably bright in all visible bands.
    score = score.min(rescale(img.select(["red", "green", "blue"]).reduce(ee.Reducer.sum()), [0.2, 0.8]))

    # Clouds are reasonably bright in all infrared bands.
    score = score.min(rescale(img.select(["swir1", "swir2", "nir"]).reduce(ee.Reducer.sum()), [0.3, 0.8]))

    # Clouds are reasonably cool in temperature.
    # Unmask temperature to a cold cold temp so it doesn't exclude the pixels entirely
    # This is an issue largely with SR data where a suspected cloud temperature value is masked out
    tempUnmasked = img.select(["temp"]).unmask(270)
    score = score.min(rescale(tempUnmasked, [300, 290]))

    # However, clouds are not snow.
    ndsi = img.normalizedDifference(["green", "swir1"])
    score = score.min(rescale(ndsi, [0.8, 0.6]))

    # ss = snowScore(img).select(['snowScore'])
    # score = score.min(rescale(ss, 'img', [0.3, 0]))

    score = score.multiply(100).byte()
    score = score.clamp(0, 100)
    return score.rename(["cloudScore"])


#########################################################################
#########################################################################
# Wrapper for applying cloudScore function
def applyCloudScoreAlgorithm(
    collection: ee.ImageCollection,
    cloudScoreFunction: "function",
    cloudScoreThresh: float = 20,
    cloudScorePctl: float = 10,
    contractPixels: float = 1.5,
    dilatePixels: float = 3.5,
    performCloudScoreOffset: bool = True,
    preComputedCloudScoreOffset: ee.Image = None,
) -> ee.ImageCollection:
    """Applies a cloud score algorithm to an image collection.

    Args:
        collection: The input Earth Engine image collection.
        cloudScoreFunction: A function to calculate the cloud score for an image.
        cloudScoreThresh: The cloud score threshold for masking (default: 20).
        cloudScorePctl: The percentile for computing the cloud score offset (default: 10).
        contractPixels: The contraction kernel size (default: 1.5).
        dilatePixels: The dilation kernel size (default: 3.5).
        performCloudScoreOffset: Whether to perform cloud score offsetting (default: True).
        preComputedCloudScoreOffset: A pre-computed cloud score offset image (optional).

    Returns:
        The image collection with cloud masks applied.
    """

    # Add cloudScore
    def cloudScoreWrapper(img):
        img = ee.Image(img)
        cs = cloudScoreFunction(img).rename(["cloudScore"])
        return img.addBands(cs)

    collection = collection.map(cloudScoreWrapper)

    if performCloudScoreOffset:
        if preComputedCloudScoreOffset == None:
            # Find low cloud score pctl for each pixel to avoid commission errors
            print("Computing cloudScore offset")
            minCloudScore = collection.select(["cloudScore"]).reduce(ee.Reducer.percentile([cloudScorePctl]))
        else:
            print("Using pre-computed cloudScore offset")
            minCloudScore = preComputedCloudScoreOffset.rename(["cloudScore"])
    else:
        print("Not computing cloudScore offset")
        minCloudScore = ee.Image(0).rename(["cloudScore"])

    # Apply cloudScore
    def cloudScoreBusterWrapper(img):
        cloudMask = img.select(["cloudScore"]).subtract(minCloudScore).lt(cloudScoreThresh).focal_max(contractPixels).focal_min(dilatePixels).rename(["cloudMask"])
        return img.updateMask(cloudMask)

    collection = collection.map(cloudScoreBusterWrapper)
    return collection


#########################################################################
#########################################################################
# Functions for applying fmask to SR data
fmaskBitDict = {
    "C1": {"cloud": 5, "shadow": 3, "snow": 4},
    "C2": {"cloud": 3, "shadow": 4, "snow": 5},
}


# LSC updated 4/16/19 to add medium and high confidence cloud masks
# Supported fmaskClass options: 'cloud', 'shadow', 'snow', 'high_confidence_cloud', 'med_confidence_cloud'
def cFmask(img: ee.Image, fmaskClass: str, bitMaskBandName: str = "QA_PIXEL") -> ee.Image:
    """Applies the CFMask algorithm to a Landsat image.

    Args:
        img: The input Landsat image.
        fmaskClass: The CFMask class to apply (e.g., 'cloud', 'shadow', 'snow').
        bitMaskBandName: The name of the QA band (default: "QA_PIXEL").

    Returns:
        The cloud-masked image.
    """
    qa = img.select(bitMaskBandName).uint16()
    if fmaskClass == "high_confidence_cloud":
        m = qa.bitwiseAnd(1 << 6).neq(0).And(qa.bitwiseAnd(1 << 7).neq(0))
    elif fmaskClass == "med_confidence_cloud":
        m = qa.bitwiseAnd(1 << 7).neq(0)
    else:
        m = qa.bitwiseAnd(fmaskBitDict[fmaskClass]).neq(0)

    return img.updateMask(m.Not())


# Method for applying a single bit bit mask
def applyBitMask(img: ee.Image, bit: int, bitMaskBandName: str = "QA_PIXEL") -> ee.Image:
    """Applies a bitmask to an image.

    Args:
        img: The input image.
        bit: The bit position to mask.
        bitMaskBandName: The name of the QA band (default: "QA_PIXEL").

    Returns:
        The masked image.
    """
    m = img.select([bitMaskBandName]).uint16()
    m = m.bitwiseAnd(1 << bit).neq(0)
    return img.updateMask(m.Not())


def cFmaskCloud(img: ee.Image, landsatCollectionVersion: str, bitMaskBandName: str = "QA_PIXEL") -> ee.Image:
    """Applies the CFMask cloud mask to a Landsat image.

    Args:
        img: The input Landsat image.
        landsatCollectionVersion: The Landsat collection version (e.g., 'C1', 'C2').
        bitMaskBandName: The name of the QA band (default: "QA_PIXEL").

    Returns:
        The cloud-masked image.
    """
    return applyBitMask(img, fmaskBitDict[landsatCollectionVersion]["cloud"], bitMaskBandName)


def cFmaskCloudShadow(img: ee.Image, landsatCollectionVersion: str, bitMaskBandName: str = "QA_PIXEL") -> ee.Image:
    """Applies the CFMask cloud shadow mask to a Landsat image.

    Args:
        img: The input Landsat image.
        landsatCollectionVersion: The Landsat collection version (e.g., 'C1', 'C2').
        bitMaskBandName: The name of the QA band (default: "QA_PIXEL").

    Returns:
        The cloud shadow masked image.
    """
    return applyBitMask(img, fmaskBitDict[landsatCollectionVersion]["shadow"], bitMaskBandName)


#########################################################################
#########################################################################
# Function for finding dark outliers in time series.
# Original concept written by Carson Stam and adapted by Ian Housman.
# Adds a band that is a mask of pixels that are dark, and dark outliers.
def simpleTDOM2(
    collection: ee.ImageCollection,
    zScoreThresh: float = -1,
    shadowSumThresh: float = 0.35,
    contractPixels: float = 1.5,
    dilatePixels: float = 3.5,
    shadowSumBands: list = ["nir", "swir1"],
    preComputedTDOMIRMean: ee.Image | None = None,
    preComputedTDOMIRStdDev: ee.Image | None = None,
) -> ee.ImageCollection:
    """Applies a simple temporal dark object differencing (TDOM) algorithm to an image collection. Adds a band that is a mask of pixels that are dark, and dark outliers.

    Args:
        collection: The input Earth Engine image collection.
        zScoreThresh: The z-score threshold for dark outliers (default: -1).
        shadowSumThresh: The shadow sum threshold (default: 0.35).
        contractPixels: The contraction kernel size (default: 1.5).
        dilatePixels: The dilation kernel size (default: 3.5).
        shadowSumBands: The bands used for shadow sum calculation (default: ["nir", "swir1"]).
        preComputedTDOMIRMean: Precomputed mean of the shadow sum bands (optional).
        preComputedTDOMIRStdDev: Precomputed standard deviation of the shadow sum bands (optional).

    Returns:
        The image collection with dark outliers masked.
    """
    args = formatArgs(locals())

    # Get some pixel-wise stats for the time series
    if preComputedTDOMIRMean == None:
        print("Computing irMean for TDOM")
        irMean = collection.select(shadowSumBands).mean()
    else:
        print("Using pre-computed irMean for TDOM")
        irMean = preComputedTDOMIRMean

    if preComputedTDOMIRStdDev == None:
        print("Computing irStdDev for TDOM")
        irStdDev = collection.select(shadowSumBands).reduce(ee.Reducer.stdDev())
    else:
        print("Using pre-computed irStdDev for TDOM")
        irStdDev = preComputedTDOMIRStdDev

    def zThresholder(img):
        zScore = img.select(shadowSumBands).subtract(irMean).divide(irStdDev)
        irSum = img.select(shadowSumBands).reduce(ee.Reducer.sum())
        TDOMMask = zScore.lt(zScoreThresh).reduce(ee.Reducer.sum()).eq(len(shadowSumBands)).And(irSum.lt(shadowSumThresh))
        TDOMMask = TDOMMask.focal_min(contractPixels).focal_max(dilatePixels)
        return img.updateMask(TDOMMask.Not())

    # Mask out dark dark outliers
    collection = collection.map(zThresholder)
    return collection.set(args)


#########################################################################
#########################################################################
# Function to add common (and less common) spectral indices to an image.
# Includes the Normalized Difference Spectral Vector from (Angiuli and Trianni, 2014)
def addIndices(img: ee.Image) -> ee.Image:
    """Adds various spectral indices to an image.

    Args:
        img: The input Earth Engine image.

    Returns:
        The image with added spectral indices.
    """
    # Add Normalized Difference Spectral Vector (NDSV)
    img = img.addBands(img.normalizedDifference(["blue", "green"]).rename(["ND_blue_green"]))
    img = img.addBands(img.normalizedDifference(["blue", "red"]).rename(["ND_blue_red"]))
    img = img.addBands(img.normalizedDifference(["blue", "nir"]).rename(["ND_blue_nir"]))
    img = img.addBands(img.normalizedDifference(["blue", "swir1"]).rename(["ND_blue_swir1"]))
    img = img.addBands(img.normalizedDifference(["blue", "swir2"]).rename(["ND_blue_swir2"]))

    img = img.addBands(img.normalizedDifference(["green", "red"]).rename(["ND_green_red"]))
    img = img.addBands(img.normalizedDifference(["green", "nir"]).rename(["ND_green_nir"]))  # NDWBI
    img = img.addBands(img.normalizedDifference(["green", "swir1"]).rename(["ND_green_swir1"]))  # NDSI, MNDWI
    img = img.addBands(img.normalizedDifference(["green", "swir2"]).rename(["ND_green_swir2"]))

    img = img.addBands(img.normalizedDifference(["red", "swir1"]).rename(["ND_red_swir1"]))
    img = img.addBands(img.normalizedDifference(["red", "swir2"]).rename(["ND_red_swir2"]))

    img = img.addBands(img.normalizedDifference(["nir", "red"]).rename(["ND_nir_red"]))  # NDVI
    img = img.addBands(img.normalizedDifference(["nir", "swir1"]).rename(["ND_nir_swir1"]))  # NDWI, LSWI, -NDBI
    img = img.addBands(img.normalizedDifference(["nir", "swir2"]).rename(["ND_nir_swir2"]))  # NBR, MNDVI

    img = img.addBands(img.normalizedDifference(["swir1", "swir2"]).rename(["ND_swir1_swir2"]))

    # Add ratios
    img = img.addBands(img.select("swir1").divide(img.select("nir")).rename(["R_swir1_nir"]))  # ratio 5/4
    img = img.addBands(img.select("red").divide(img.select("swir1")).rename(["R_red_swir1"]))  # ratio 3/5

    # Add Enhanced Vegetation Index (EVI)
    evi = img.expression(
        "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
        {
            "NIR": img.select("nir"),
            "RED": img.select("red"),
            "BLUE": img.select("blue"),
        },
    ).float()
    img = img.addBands(evi.rename("EVI"))

    # Add Soil Adjust Vegetation Index (SAVI)
    # using L = 0.5;
    savi = img.expression(
        "(NIR - RED) * (1 + 0.5)/(NIR + RED + 0.5)",
        {"NIR": img.select("nir"), "RED": img.select("red")},
    ).float()
    img = img.addBands(savi.rename(["SAVI"]))

    # Add Index-Based Built-Up Index (IBI)
    ibi_a = img.expression(
        "2*SWIR1/(SWIR1 + NIR)",
        {"SWIR1": img.select("swir1"), "NIR": img.select("nir")},
    ).rename(["IBI_A"])

    ibi_b = img.expression(
        "(NIR/(NIR + RED)) + (GREEN/(GREEN + SWIR1))",
        {
            "NIR": img.select("nir"),
            "RED": img.select("red"),
            "GREEN": img.select("green"),
            "SWIR1": img.select("swir1"),
        },
    ).rename(["IBI_B"])

    ibi_a = ibi_a.addBands(ibi_b)
    ibi = ibi_a.normalizedDifference(["IBI_A", "IBI_B"])
    img = img.addBands(ibi.rename(["IBI"]))

    return img


#########################################################################
#########################################################################
# Function to  add SAVI and EVI
def addSAVIandEVI(img: ee.Image) -> ee.Image:
    """Adds SAVI and EVI indices to an image.

    Args:
        img: The input Earth Engine image.

    Returns:
        The image with added SAVI and EVI indices.
    """
    # Add Enhanced Vegetation Index (EVI)
    evi = img.expression(
        "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
        {
            "NIR": img.select("nir"),
            "RED": img.select("red"),
            "BLUE": img.select("blue"),
        },
    ).float()
    img = img.addBands(evi.rename(["EVI"]))

    # Add Soil Adjust Vegetation Index (SAVI)
    # using L = 0.5
    savi = img.expression(
        "(NIR - RED) * (1 + 0.5)/(NIR + RED + 0.5)",
        {"NIR": img.select("nir"), "RED": img.select("red")},
    ).float()

    #########################################################################
    # NIRv: Badgley, G., Field, C. B., & Berry, J. A. (2017). Canopy near-infrared reflectance and terrestrial photosynthesis. Science Advances, 3, e1602244.
    # https://www.researchgate.net/publication/315534107_Canopy_near-infrared_reflectance_and_terrestrial_photosynthesis
    # NIRv function: 'image' is a 2 band stack of NDVI and NIR
    #########################################################################
    NIRv = img.select(["NDVI"]).subtract(0.08).multiply(img.select(["nir"]))  # .multiply(0.0001))

    img = img.addBands(savi.rename(["SAVI"])).addBands(NIRv.rename(["NIRv"]))
    return img


#########################################################################
###############################################################
# Apply bloom detection algorithm
def HoCalcAlgorithm2(image: ee.Image) -> ee.Image:
    """
    Applies an algal detection algorithm based on:
    Matthews, M. (2011) A current review of empirical procedures
    of remote sensing in inland and near-coastal transitional
    waters, International Journal of Remote Sensing, 32:21,
    6855-6899, DOI: 10.1080/01431161.2010.512947.

    Args:
        image: The input Earth Engine image.

    Returns:
        The image with added bloom2 and NDGI bands.
    """
    # Algorithm 2 based on:
    # Matthews, M. (2011) A current review of empirical procedures
    #  of remote sensing in inland and near-coastal transitional
    #  waters, International Journal of Remote Sensing, 32:21,
    #  6855-6899, DOI: 10.1080/01431161.2010.512947

    # Apply algorithm 2: B2/B1
    bloom2 = image.select("green").divide(image.select("blue")).rename(["bloom2"])
    ndgi = image.normalizedDifference(["green", "blue"]).rename(["NDGI"])
    return image.addBands(bloom2).addBands(ndgi)


#########################################################################
# Function for only adding common indices
def simpleAddIndices(in_image: ee.Image) -> ee.Image:
    """Adds common spectral indices to an image.

    Args:
        in_image: The input Earth Engine image.

    Returns:
        The image with added NDVI, NBR, NDMI, and NDSI indices.
    """
    in_image = in_image.addBands(in_image.normalizedDifference(["nir", "red"]).select([0], ["NDVI"]))
    in_image = in_image.addBands(in_image.normalizedDifference(["nir", "swir2"]).select([0], ["NBR"]))
    in_image = in_image.addBands(in_image.normalizedDifference(["nir", "swir1"]).select([0], ["NDMI"]))
    in_image = in_image.addBands(in_image.normalizedDifference(["green", "swir1"]).select([0], ["NDSI"]))

    return in_image


#########################################################################
#########################################################################
# Function for adding common indices
#########################################################################
def addSoilIndices(img: ee.Image) -> ee.Image:
    """Adds soil-related indices to an image.

    Args:
        img: The input Earth Engine image.

    Returns:
        The image with added soil indices.
    """
    img = img.addBands(img.normalizedDifference(["red", "green"]).rename(["NDCI"]))
    img = img.addBands(img.normalizedDifference(["red", "swir2"]).rename(["NDII"]))
    img = img.addBands(img.normalizedDifference(["swir1", "nir"]).rename(["NDFI"]))

    bsi = img.expression(
        "((SWIR1 + RED) - (NIR + BLUE)) / ((SWIR1 + RED) + (NIR + BLUE))",
        {
            "BLUE": img.select("blue"),
            "RED": img.select("red"),
            "NIR": img.select("nir"),
            "SWIR1": img.select("swir1"),
        },
    ).float()

    img = img.addBands(bsi.rename(["BSI"]))

    hi = img.expression("SWIR1 / SWIR2", {"SWIR1": img.select("swir1"), "SWIR2": img.select("swir2")}).float()
    img = img.addBands(hi.rename(["HI"])).float()
    return img


#########################################################################
#########################################################################
# Function to compute the Tasseled Cap transformation and return an image
# with the following bands added: ['brightness', 'greenness', 'wetness',
#'fourth', 'fifth', 'sixth']
def getTasseledCap(image: ee.Image) -> ee.Image:
    """Computes the Tasseled Cap transformation for an image using the Crist 1985 coefficients.

    Args:
        image: The input Earth Engine image.

    Returns:
        The image with added Tasseled Cap components.
    """

    bands = ee.List(["blue", "green", "red", "nir", "swir1", "swir2"])
    #   // // Kauth-Thomas coefficients for Thematic Mapper data
    #   // var coefficients = ee.Array([
    #   //   [0.3037, 0.2793, 0.4743, 0.5585, 0.5082, 0.1863],
    #   //   [-0.2848, -0.2435, -0.5436, 0.7243, 0.0840, -0.1800],
    #   //   [0.1509, 0.1973, 0.3279, 0.3406, -0.7112, -0.4572],
    #   //   [-0.8242, 0.0849, 0.4392, -0.0580, 0.2012, -0.2768],
    #   //   [-0.3280, 0.0549, 0.1075, 0.1855, -0.4357, 0.8085],
    #   //   [0.1084, -0.9022, 0.4120, 0.0573, -0.0251, 0.0238]
    #   // ]);

    # Crist 1985 coeffs - TOA refl (http://www.gis.usu.edu/~doug/RS5750/assign/OLD/RSE(17)-301.pdf)
    coefficients = ee.Array(
        [
            [0.2043, 0.4158, 0.5524, 0.5741, 0.3124, 0.2303],
            [-0.1603, -0.2819, -0.4934, 0.7940, -0.0002, -0.1446],
            [0.0315, 0.2021, 0.3102, 0.1594, -0.6806, -0.6109],
            [-0.2117, -0.0284, 0.1302, -0.1007, 0.6529, -0.7078],
            [-0.8669, -0.1835, 0.3856, 0.0408, -0.1132, 0.2272],
            [0.3677, -0.8200, 0.4354, 0.0518, -0.0066, -0.0104],
        ]
    )
    # Make an Array Image, with a 1-D Array per pixel.
    arrayImage1D = image.select(bands).toArray()

    # Make an Array Image with a 2-D Array per pixel, 6x1.
    arrayImage2D = arrayImage1D.toArray(1)

    componentsImage = ee.Image(coefficients).matrixMultiply(arrayImage2D).arrayProject([0]).arrayFlatten([["brightness", "greenness", "wetness", "fourth", "fifth", "sixth"]]).float()

    return image.addBands(componentsImage)


#########################################################################
#########################################################################
def simpleGetTasseledCap(image: ee.Image) -> ee.Image:
    """Computes the Tasseled Cap transformation for an image, including only brightness, greenness, and wetness using the Crist 1985 coefficients.

    Args:
        image: The input Earth Engine image.

    Returns:
        The image with added brightness, greenness, and wetness bands.
    """
    bands = ee.List(["blue", "green", "red", "nir", "swir1", "swir2"])
    #   // // Kauth-Thomas coefficients for Thematic Mapper data
    #   // var coefficients = ee.Array([
    #   //   [0.3037, 0.2793, 0.4743, 0.5585, 0.5082, 0.1863],
    #   //   [-0.2848, -0.2435, -0.5436, 0.7243, 0.0840, -0.1800],
    #   //   [0.1509, 0.1973, 0.3279, 0.3406, -0.7112, -0.4572],
    #   //   [-0.8242, 0.0849, 0.4392, -0.0580, 0.2012, -0.2768],
    #   //   [-0.3280, 0.0549, 0.1075, 0.1855, -0.4357, 0.8085],
    #   //   [0.1084, -0.9022, 0.4120, 0.0573, -0.0251, 0.0238]
    #   // ]);

    # Crist 1985 coeffs - TOA refl (http://www.gis.usu.edu/~doug/RS5750/assign/OLD/RSE(17)-301.pdf)
    coefficients = ee.Array(
        [
            [0.2043, 0.4158, 0.5524, 0.5741, 0.3124, 0.2303],
            [-0.1603, -0.2819, -0.4934, 0.7940, -0.0002, -0.1446],
            [0.0315, 0.2021, 0.3102, 0.1594, -0.6806, -0.6109],
        ]
    )
    # Make an Array Image, with a 1-D Array per pixel.
    arrayImage1D = image.select(bands).toArray()

    # Make an Array Image with a 2-D Array per pixel, 6x1.
    arrayImage2D = arrayImage1D.toArray(1)

    componentsImage = ee.Image(coefficients).matrixMultiply(arrayImage2D).arrayProject([0]).arrayFlatten([["brightness", "greenness", "wetness"]]).float()

    return image.addBands(componentsImage)


#########################################################################
#########################################################################
# Function to add Tasseled Cap angles and distances to an image.
# Assumes image has bands: 'brightness', 'greenness', and 'wetness'.
def addTCAngles(image: ee.Image) -> ee.Image:
    """
    Adds Tasseled Cap angles and distances to an image.
    Assumes image has bands: 'brightness', 'greenness', and 'wetness'.

    Args:
        image: The input Earth Engine image with brightness, greenness, and wetness bands.

    Returns:
        The image with added Tasseled Cap angles and distances.
    """
    # Select brightness, greenness, and wetness bands
    brightness = image.select(["brightness"])
    greenness = image.select(["greenness"])
    wetness = image.select(["wetness"])

    # Calculate Tasseled Cap angles and distances
    tcAngleBG = brightness.atan2(greenness).divide(math.pi).rename(["tcAngleBG"])
    tcAngleGW = greenness.atan2(wetness).divide(math.pi).rename(["tcAngleGW"])
    tcAngleBW = brightness.atan2(wetness).divide(math.pi).rename(["tcAngleBW"])
    tcDistBG = brightness.hypot(greenness).rename(["tcDistBG"])
    tcDistGW = greenness.hypot(wetness).rename(["tcDistGW"])
    tcDistBW = brightness.hypot(wetness).rename(["tcDistBW"])
    image = image.addBands(tcAngleBG).addBands(tcAngleGW).addBands(tcAngleBW).addBands(tcDistBG).addBands(tcDistGW).addBands(tcDistBW)
    return image


#########################################################################
#########################################################################
# Only adds tc bg angle as in Powell et al 2009
# https://www.sciencedirect.com/science/article/pii/S0034425709003745?via%3Dihub
def simpleAddTCAngles(image: ee.Image) -> ee.Image:
    """
    Adds the Tasseled Cap brightness-greenness angle to an image as in Powell et al 2009.
    Assumes image has bands: 'brightness', 'greenness', and 'wetness'.

    Args:
        image: The input Earth Engine image with brightness and greenness bands.

    Returns:
        The image with added brightness-greenness angle.
    """
    # Select brightness, greenness, and wetness bands
    brightness = image.select(["brightness"])
    greenness = image.select(["greenness"])
    wetness = image.select(["wetness"])

    # Calculate Tasseled Cap angles and distances
    tcAngleBG = brightness.atan2(greenness).divide(math.pi).rename(["tcAngleBG"])

    return image.addBands(tcAngleBG)


#########################################################################
#########################################################################
# Function to add solar zenith and azimuth in radians as bands to image
def addZenithAzimuth(
    img: ee.Image,
    toaOrSR: str,
    zenithDict: dict = {"TOA": "SUN_ELEVATION", "SR": "SOLAR_ZENITH_ANGLE"},
    azimuthDict: dict = {"TOA": "SUN_AZIMUTH", "SR": "SOLAR_AZIMUTH_ANGLE"},
):
    """
    Adds solar zenith and azimuth angles in radians to an image.

    Args:
        img: The input Earth Engine image.
        toaOrSR: Whether the image is TOA or SR.
        zenithDict: A dictionary mapping toaOrSR to the zenith band name.
        azimuthDict: A dictionary mapping toaOrSR to the azimuth band name.

    Returns:
        The image with added zenith and azimuth bands.
    """
    zenith = ee.Image.constant(img.get(zenithDict[toaOrSR])).multiply(math.pi).divide(180).float().rename(["zenith"])

    azimuth = ee.Image.constant(img.get(azimuthDict[toaOrSR])).multiply(math.pi).divide(180).float().rename(["azimuth"])

    return img.addBands(zenith).addBands(azimuth)


#########################################################################
#########################################################################
# Function for computing the mean squared difference medoid from an image collection
# As the data are not normalized in this method, ensuring the medoidIncludeBands have roughly comparable ranges of values
# helps the function work properly. For example, if temperature is included, it will account for most of the variance
# thus resulting in a medoid mosaic that will more or less choose values closest to the median temperature only, rather than
# all the bands
def medoidMosaicMSD(inCollection: ee.ImageCollection, medoidIncludeBands: ee.List | None = None) -> ee.Image:
    """Creates a medoid mosaic using the Mean Squared Difference (MSD) (euclidean distance) method.

    This function calculates the medoid image from an image collection based on minimizing the sum of squared differences between pixel values.

    Args:
        inCollection: The input Earth Engine ImageCollection to create the mosaic from.
        medoidIncludeBands: A list of band names to include in the MSD calculation. If None, all bands are used.

    Returns:
        An Earth Engine Image representing the medoid mosaic.

    Note:
        * As the data are not normalized in this method, ensuring the medoidIncludeBands have roughly comparable ranges of values helps the function work properly. For example, if temperature is included, it will account for most of the variance thus resulting in a medoid mosaic that will more or less choose values closest to the median temperature only, rather than all the bands

        * The function assumes that the image collection has consistent band names and data types.


    >>> import geeViz.getImagesLib as gil
    >>> Map = gil.Map
    >>> ee = gil.ee
    >>> studyArea = gil.testAreas["CO"]
    >>> s2s = gil.superSimpleGetS2(studyArea, "2024-01-01", "2024-12-31", 190, 250)
    >>> median_composite = s2s.median()
    >>> medoid_composite = gil.medoidMosaicMSD(s2s, ["green", "red", "nir", "swir1", "swir2"])
    >>> Map.addLayer(median_composite, gil.vizParamsFalse10k, "Sentinel-2 Median Composite")
    >>> Map.addLayer(medoid_composite, gil.vizParamsFalse10k, "Sentinel-2 Medoid Composite")
    >>> Map.addLayer(studyArea, {"canQuery": False}, "Study Area")
    >>> Map.centerObject(studyArea)
    >>> Map.turnOnInspector()
    >>> Map.view()

    """

    if medoidIncludeBands == None:
        medoidIncludeBands = ee.Image(inCollection.first()).bandNames()

    # Find the median
    median = inCollection.select(medoidIncludeBands).median()

    # Find the squared difference from the median for each image
    # Multiply by -1 so quality mosaic function can be used
    def msdGetter(img):
        diff = ee.Image(img).select(medoidIncludeBands).subtract(median).pow(2)
        img = addYearBand(img)
        img = addJulianDayBand(img)
        return diff.reduce("sum").multiply(-1).addBands(img)

    medoid = inCollection.map(msdGetter)

    # Minimize the distance across all bands by finding the pixels that correspond to the minimum distance (multiplied by -1 above)
    medoid = medoid.qualityMosaic("sum")
    medoid = medoid.select(medoid.bandNames().remove("sum"))

    return medoid


#########################################################################
#########################################################################
# Function to export a provided image to an EE asset
# For earthengine-api version 0.1.226
# There was an issue with the region with this new version.
# From earthengine-api batch.Export.toAsset documentation: "region: The lon,lat coordinates for a LinearRing or Polygon specifying the region to export.
#     Can be specified as a nested lists of numbers or a serialized string. Defaults to the image's region."
def exportToAssetWrapper(
    imageForExport: ee.Image, assetName: str, assetPath: str, pyramidingPolicyObject: dict | None = None, roi: ee.Geometry | None = None, scale: float | None = None, crs: str | None = None, transform: list | None = None, overwrite: bool = False
):
    """Exports an image to an Earth Engine asset.

    This function provides a wrapper for exporting images to Earth Engine assets with additional features like handling existing assets and setting the pyramiding policy.

    Args:
        imageForExport: The Earth Engine Image to export.
        assetName: The desired name for the asset.
        assetPath: The full path for the asset in the Earth Engine asset tree.
        pyramidingPolicyObject: An optional dictionary specifying the pyramiding policy for the exported asset.
        roi: An optional Earth Engine Geometry defining the region of interest for export.
        scale: The desired export scale in meters.
        crs: The desired coordinate reference system for the export.
        transform: The desired transform for the export.
        overwrite: A boolean indicating whether to overwrite an existing asset.

    Returns:
        None. The function starts the export task.
    """
    # Get rid of any spaces
    assetName = assetName.replace("/\s+/g", "-")
    assetPath = assetPath.replace("/\s+/g", "-")

    # Pull geometry if feature or featureCollection
    if roi != None:
        try:
            roi = roi.geometry()
        except Exception as e:
            x = e
        imageForExport = imageForExport.clip(roi)
        outRegion = roi.bounds(100, crs)
    else:
        outRegion = None

    if transform != None and (str(type(transform)) == "<type 'list'>" or str(type(transform)) == "<class 'list'>"):
        transform = str(transform)

    if pyramidingPolicyObject == None:
        pyramidingPolicyObject = {".default": "mean"}
    elif type(pyramidingPolicyObject) == str:
        pyramidingPolicyObject = {".default": pyramidingPolicyObject}
    # pyramidingPolicyObject = json.dumps(pyramidingPolicyObject)
    # print('pyramiding object:',pyramidingPolicyObject)

    # Handle different instances of an asset either already existing or currently being exported and whether it should be overwritten
    currently_exporting = assetName in tml.getTasks()["running"] or assetName in tml.getTasks()["ready"]
    currently_exists = aml.ee_asset_exists(assetPath)

    if overwrite and currently_exists:
        ee.data.deleteAsset(assetPath)
    if overwrite and currently_exporting:
        tml.cancelByName(assetName)
    if overwrite or (not currently_exists and not currently_exporting):

        # LSC 1/6/20 was getting error: "ee.ee_exception.EEException: JSON provided for reductionPolicy must be an object." Getting rid of json.dumps() seemed to fix the problem
        t = ee.batch.Export.image.toAsset(
            imageForExport,
            description=assetName,
            assetId=assetPath,
            pyramidingPolicy=pyramidingPolicyObject,
            dimensions=None,
            region=None,
            scale=scale,
            crs=crs,
            crsTransform=transform,
            maxPixels=1e13,
        )
        print("Exporting:", assetName)
        # print(t)
        t.start()
    else:
        print(f"{assetName} currently exists or is being exported and overwrite = False. Set overwite = True if you would like to overwite any existing asset or asset exporting task")
    # Map.addLayer(imageForExport,vizParamsFalse,assetName)


#########################################################################
def exportToDriveWrapper(imageForExport: ee.Image, outputName: str, driveFolderName: str, roi: ee.Geometry, scale: float | None = None, crs: str | None = None, transform: list | None = None, outputNoData: int = -32768):
    """Exports an image to Google Drive.

    This function exports an Earth Engine Image to a specified Google Drive folder.

    Args:
        imageForExport: The Earth Engine Image to export.
        outputName: The desired name for the exported file.
        driveFolderName: The name of the Google Drive folder to export to.
        roi: The Earth Engine Geometry defining the region of interest.
        scale: The desired export scale in meters.
        crs: The desired coordinate reference system for the export.
        transform: The desired transform for the export.
        outputNoData: The no data value to use for the export.

    Returns:
        None. The function starts the export task.
    """
    outputName = outputName.replace("/\s+/g", "-")  # Get rid of any spaces

    # Pull geometry if feature or featureCollection
    try:
        roi = roi.geometry()
    except Exception as e:
        x = e

    # Make sure image is clipped to roi in case it's a multi-part polygon
    imageForExport = imageForExport.clip(roi).unmask(outputNoData, False)

    if transform != None and (str(type(transform)) == "<type 'list'>" or str(type(transform)) == "<class 'list'>"):
        transform = str(transform)

    # Ensure bounds are in export projection
    outRegion = roi.bounds(100, crs)

    # Map.addLayer(imageForExport,{},outputName,False)
    t = ee.batch.Export.image.toDrive(
        imageForExport,
        outputName,
        driveFolderName,
        outputName,
        None,
        outRegion,
        scale,
        crs,
        transform,
        1e13,
    )
    print("Exporting:", outputName)
    t.start()


#########################################################################
def exportToCloudStorageWrapper(
    imageForExport: ee.Image,
    outputName: str,
    bucketName: str,
    roi: ee.Geometry,
    scale: float | None = None,
    crs: str | None = None,
    transform: list | None = None,
    outputNoData: int = -32768,
    fileFormat: str = "GeoTIFF",
    formatOptions: dict = {"cloudOptimized": True},
    overwrite: bool = False,
):
    """Exports an image to Google Cloud Storage.

    This function exports an Earth Engine Image to a specified Google Cloud Storage bucket.

    Args:
        imageForExport: The Earth Engine Image to export.
        outputName: The desired name for the exported file.
        bucketName: The name of the Google Cloud Storage bucket.
        roi: The Earth Engine Geometry defining the region of interest.
        scale: The desired export scale in meters.
        crs: The desired coordinate reference system for the export.
        transform: The desired transform for the export.
        outputNoData: The no data value to use for the export.
        fileFormat: The desired output file format (e.g., "GeoTIFF", "TFRecord").
        formatOptions: Additional format options for the export.
        overwrite: A boolean indicating whether to overwrite an existing file.

    Returns:
        None. The function starts the export task.
    """
    outputName = outputName.replace("/\s+/g", "-")  # Get rid of any spaces

    extension_dict = {"GeoTIFF": [".tif"], "TFRecord": [".tfrecord", ".json"]}
    extensions = extension_dict[fileFormat]
    # Pull geometry if feature or featureCollection
    try:
        roi = roi.geometry()
    except Exception as e:
        x = e

    # Make sure image is clipped to roi in case it's a multi-part polygon
    imageForExport = imageForExport.clip(roi).unmask(outputNoData, False)

    if transform != None and (str(type(transform)) == "<type 'list'>" or str(type(transform)) == "<class 'list'>"):
        transform = str(transform)

    # Ensure bounds are in export projection
    outRegion = roi.bounds(100, crs)

    # Handle different instances of an blob either already existing or currently being exported and whether it should be overwritten
    currently_exporting = outputName in tml.getTasks()["running"] or outputName in tml.getTasks()["ready"]
    currently_exists = cml.gcs_exists(bucketName, outputName + extensions[0])

    if overwrite and currently_exists:
        for extension in extensions:
            cml.delete_blob(bucketName, outputName + extension)
    if overwrite and currently_exporting:
        tml.cancelByName(outputName)
    if overwrite or (not currently_exists and not currently_exporting):
        t = ee.batch.Export.image.toCloudStorage(
            imageForExport,
            outputName,
            bucketName,
            outputName,
            None,
            outRegion,
            scale,
            crs,
            transform,
            1e13,
            fileFormat=fileFormat,
            formatOptions=formatOptions,
        )
        print("Exporting:", outputName)
        print(t)
        t.start()


#########################################################################
#########################################################################
# Function for wrapping dates when the startJulian < endJulian
# Checks for year with majority of the days and the wrapOffset
def wrapDates(startJulian: int, endJulian: int) -> list:
    """Wraps dates when the startJulian is greater than the endJulian.

    This function handles cases where the start Julian day is later in the year than the end Julian day.

    Args:
        startJulian: The start Julian day.
        endJulian: The end Julian day.

    Returns:
        A list containing the wrap offset and the year with the majority of days.
    """
    # Set up date wrapping
    wrapOffset = 0
    yearWithMajority = 0
    if startJulian > endJulian:
        wrapOffset = 365
        y1NDays = 365 - startJulian
        y2NDays = endJulian
        if y2NDays > y1NDays:
            yearWithMajority = 1

    return [wrapOffset, yearWithMajority]


#########################################################################
#########################################################################
# Create composites for each year within startYear and endYear range
def compositeTimeSeries(
    ls: ee.ImageCollection, startYear: int, endYear: int, startJulian: int, endJulian: int, timebuffer: int = 0, weights: list = [1], compositingMethod: str | None = None, compositingReducer: ee.Reducer | None = None
) -> ee.ImageCollection:
    """Creates composites for each year within a specified date range.

    This function generates annual composites from an image collection, allowing for time buffering and weighted averaging.


    Args:
        ls: The input Earth Engine image collection.
        startYear: The start year of the composite period.
        endYear: The end year of the composite period.
        startJulian: The start Julian day of the composite period.
        endJulian: The end Julian day of the composite period.
        timebuffer: The number of years to include in the composite (default: 0).
        weights: The weights for the composite (default: [1]).
        compositingMethod: The compositing method (e.g., 'median', 'medoid') (optional).
        compositingReducer: A custom compositing reducer (optional).

    Returns:
        An Earth Engine image collection containing the composites.
    """

    args = formatArgs(locals())
    if "args" in args.keys():
        del args["args"]

    dummyImage = ee.Image(ls.first())

    dateWrapping = wrapDates(startJulian, endJulian)
    wrapOffset = dateWrapping[0]
    yearWithMajority = dateWrapping[1]

    def yearCompositeGetter(year):

        # Set up dates
        startYearT = year - timebuffer
        endYearT = year + timebuffer
        startDateT = ee.Date.fromYMD(startYearT, 1, 1).advance(startJulian - 1, "day")
        endDateT = ee.Date.fromYMD(endYearT, 1, 1).advance(endJulian - 1 + wrapOffset, "day")

        # print(year,startDateT,endDateT)

        # Set up weighted moving widow
        yearsT = ee.List.sequence(startYearT, endYearT)

        def zipper(i):
            i = ee.List(i)
            return ee.List.repeat(i.get(0), i.get(1))

        z = yearsT.zip(weights)

        yearsTT = z.map(zipper).flatten()

        # print('Weighted composite years for year:',year,yearsTT.getInfo())

        # Iterate across each year in list
        def yrGetter(yr):
            # Set up dates
            startDateT = ee.Date.fromYMD(yr, 1, 1).advance(startJulian - 1, "day")
            endDateT = ee.Date.fromYMD(yr, 1, 1).advance(endJulian - 1 + wrapOffset, "day")

            # Filter images for given date range
            lsT = ls.filterDate(startDateT, endDateT.advance(1, "day"))
            lsT = fillEmptyCollections(lsT, dummyImage)
            return lsT

        images = yearsTT.map(yrGetter)
        lsT = ee.ImageCollection(ee.FeatureCollection(images).flatten())

        count = lsT.select([0]).reduce(ee.Reducer.count()).rename(["compositeObsCount"])
        # Compute median or medoid or apply reducer
        if compositingReducer != None:
            composite = lsT.reduce(compositingReducer)
        elif compositingMethod.lower() == "median":
            composite = lsT.median()
        else:
            composite = medoidMosaicMSD(lsT, ["green", "red", "nir", "swir1", "swir2"])
        composite = composite.addBands(count).float()

        return composite.set(
            {
                "system:time_start": ee.Date.fromYMD(year + yearWithMajority, 6, 1).millis(),
                "startDate": startDateT.millis(),
                "endDate": endDateT.millis(),
                "startJulian": startJulian,
                "endJulian": endJulian,
                "yearBuffer": timebuffer,
                "yearWeights": str(weights),
                "yrOriginal": year,
                "yrUsed": year + yearWithMajority,
            }
        )

    # Iterate across each year
    ts = [yearCompositeGetter(yr) for yr in ee.List.sequence(startYear + timebuffer, endYear - timebuffer).getInfo()]
    ts = ee.ImageCollection(ts).set(args)

    return ts


# ////////////////////////////////////////////////////////////////////////////////
# Function to calculate illumination condition (IC). Function by Patrick Burns
# (pb463@nau.edu) and Matt Macander
# (mmacander@abrinc.com)
def illuminationCorrection(img: ee.Image, scale: float, studyArea: ee.Geometry, bandList: list = ["blue", "green", "red", "nir", "swir1", "swir2", "temp"]) -> ee.Image:
    """Applies the Sun-Canopy-Sensor + C (SCSc) correction method to an image.

    This function corrects for topographic effects on image reflectance.

    Args:
        img: The input Earth Engine Image.
        scale: The scale for the reduction region.
        studyArea: The study area.
        bandList: A list of bands to correct.

    Returns:
        The corrected Earth Engine Image.
    """
    # Extract solar zenith and azimuth bands
    SZ_rad = img.select("zenith")
    SA_rad = img.select("azimuth")

    # Creat terrain layers
    # dem = ee.Image('CGIAR/SRTM90_V4')
    dem = ee.Image("USGS/NED")
    slp = ee.Terrain.slope(dem)
    slp_rad = ee.Terrain.slope(dem).multiply(math.pi).divide(180)
    asp_rad = ee.Terrain.aspect(dem).multiply(math.pi).divide(180)

    # Calculate the Illumination Condition (IC)
    # slope part of the illumination condition
    cosZ = SZ_rad.cos()
    cosS = slp_rad.cos()
    slope_illumination = cosS.expression("cosZ * cosS", {"cosZ": cosZ, "cosS": cosS.select("slope")})
    # aspect part of the illumination condition
    sinZ = SZ_rad.sin()
    sinS = slp_rad.sin()
    cosAziDiff = (SA_rad.subtract(asp_rad)).cos()
    aspect_illumination = sinZ.expression(
        "sinZ * sinS * cosAziDiff",
        {"sinZ": sinZ, "sinS": sinS, "cosAziDiff": cosAziDiff},
    )
    # full illumination condition (IC)
    ic = slope_illumination.add(aspect_illumination)

    # Add IC to original image
    return img.addBands(ic.rename("IC")).addBands(cosZ.rename("cosZ")).addBands(cosS.rename("cosS")).addBands(slp.rename("slope"))


########################################
# Function to apply the Sun-Canopy-Sensor + C (SCSc) correction method to each
# image. Function by Patrick Burns (pb463@nau.edu) and Matt Macander
# (mmacander@s.com)
def illuminationCorrection(
    img,
    scale,
    studyArea,
    bandList=["blue", "green", "red", "nir", "swir1", "swir2", "temp"],
):

    props = img.toDictionary()
    st = img.get("system:time_start")
    img_plus_ic = img
    mask2 = img_plus_ic.select("slope").gte(5).And(img_plus_ic.select("IC").gte(0)).And(img_plus_ic.select("nir").gt(-0.1))
    img_plus_ic_mask2 = ee.Image(img_plus_ic.updateMask(mask2))

    # Specify Bands to topographically correct
    compositeBands = img.bandNames()
    nonCorrectBands = img.select(compositeBands.removeAll(bandList))

    def apply_SCSccorr(bandList):
        method = "SCSc"
        out = img_plus_ic_mask2.select("IC", bandList).reduceRegion(
            **{
                "reducer": ee.Reducer.linearFit(),
                "geometry": studyArea,
                "scale": scale,
                "maxPixels": 1e13,
            }
        )

        out_a = ee.Number(out.get("scale"))
        out_b = ee.Number(out.get("offset"))
        out_c = out_b.divide(out_a)
        # Apply the SCSc correction
        SCSc_output = img_plus_ic_mask2.expression(
            "((image * (cosB * cosZ + cvalue)) / (ic + cvalue))",
            {
                "image": img_plus_ic_mask2.select(bandList),
                "ic": img_plus_ic_mask2.select("IC"),
                "cosB": img_plus_ic_mask2.select("cosS"),
                "cosZ": img_plus_ic_mask2.select("cosZ"),
                "cvalue": out_c,
            },
        )

        return SCSc_output

    img_SCSccorr = ee.Image(bandList.map(apply_SCSccorr)).addBands(img_plus_ic.select("IC"))
    bandList_IC = ee.List([bandList, "IC"]).flatten()
    img_SCSccorr = img_SCSccorr.unmask(img_plus_ic.select(bandList_IC)).select(bandList)

    return img_SCSccorr.addBands(nonCorrectBands).setMulti(props).set("system:time_start", st)


#########################################################################
#########################################################################
# A function to mask out pixels that did not have observations for MODIS.
def maskEmptyPixels(image: ee.Image) -> ee.Image:
    """Masks pixels without observations in an image.

    This function masks pixels where the number of observations is zero.

    Args:
        image: The input Earth Engine Image with a "num_observations_1km" band.

    Returns:
        The masked Earth Engine Image.
    """
    # Find pixels that had observations.
    withObs = image.select("num_observations_1km").gt(0)
    return image.mask(image.mask().And(withObs))


#########################################################################
#########################################################################
# A function that returns an image containing just the specified QA bits.
#
# Args:
#   image - The QA Image to get bits from.
#   start - The first bit position, 0-based.
#   end   - The last bit position, inclusive.
#   name  - A name for the output image.


def getQABits(image: ee.Image, start: int, end: int, name: str) -> ee.Image:
    """Extracts specific bits from a QA band.

    This function extracts a range of bits from a QA band and creates a new band.

    Args:
        image: The input Earth Engine Image with a QA band.
        start: The starting bit position (0-based).
        end: The ending bit position.
        name: The name for the output band.

    Returns:
        The Earth Engine Image with the extracted bits.
    """
    # Compute the bits we need to extract.
    pattern = 0
    for i in range(start, end + 1):
        pattern += math.pow(2, i)

    # Return a single band image of the extracted QA bits, giving the band a new name.
    return image.select([0], [newName]).bitwiseAnd(pattern).rightShift(start)


#########################################################################
#########################################################################
# A function to mask out cloudy pixels.
def maskCloudsWQA(image):
    # Select the QA band.
    QA = image.select("state_1km")
    # Get the internal_cloud_algorithm_flag bit.
    internalCloud = getQABits(QA, 10, 10, "internal_cloud_algorithm_flag")
    # Return an image masking out cloudy areas.
    return image.mask(image.mask().And(internalCloud.eq(0)))


#########################################################################
#########################################################################
# Source: code.earthengine.google.com
# Compute a cloud score.  This expects the input image to have the common
# band names: ["red", "blue", etc], so it can work across sensors.
def modisCloudScore(img):

    useTempInCloudMask = True
    # Compute several indicators of cloudyness and take the minimum of them.
    score = ee.Image(1.0)

    # Clouds are reasonably bright in the blue band.
    # score = score.min(rescale(img, 'img.blue', [0.1, 0.3]))
    # Clouds are reasonably bright in all visible bands.
    vizSum = rescale(img.select(["red", "green", "blue"]).reduce(ee.Reducer.sum()), [0.2, 0.8])
    score = score.min(vizSum)

    # Clouds are reasonably bright in all infrared bands.
    # irSum =rescale(img, 'img.nir + img.swir2', [0.3, 0.7])
    irSum = rescale(img.select(["nir", "swir1", "swir2"]).reduce(ee.Reducer.sum()), [0.3, 0.8])
    score = score.min(irSum)

    # However, clouds are not snow.
    ndsi = img.normalizedDifference(["green", "swir2"])
    snowScore = rescale(ndsi, [0.8, 0.6])
    score = score.min(snowScore)

    # For MODIS, provide the option of not using thermal since it introduces
    # a precomputed mask that may or may not be wanted
    if useTempInCloudMask:
        # Clouds are reasonably cool in temperature.
        # tempScore = rescale(img, 'img.temp', [305, 300])
        # Map.addLayer(tempScore,{},'tempscore')
        # score = score.min(tempScore)
        score = score.where(img.select(["temp"]).mask().Not(), 1)

    score = score.multiply(100)
    score = score.clamp(0, 100).byte()

    return score.rename(["cloudScore"])


#########################################################################
#########################################################################
# Cloud masking algorithm for Sentinel2
# Built on ideas from Landsat cloudScore algorithm
# Currently in beta and may need tweaking for individual study areas
def sentinel2CloudScore(img):
    # Compute several indicators of cloudyness and take the minimum of them.
    score = ee.Image(1)
    blueCirrusScore = ee.Image(0)

    # Clouds are reasonably bright in the blue or cirrus bands.
    # Use .max as a pseudo OR conditional
    blueCirrusScore = blueCirrusScore.max(rescale(img.select(["blue"]), [0.1, 0.5]))
    blueCirrusScore = blueCirrusScore.max(rescale(img.select(["cb"]), [0.1, 0.5]))
    # blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.cirrus', [0.1, 0.3]))

    # reSum = rescale(img,'(img.re1+img.re2+img.re3)/3',[0.5, 0.7])

    score = score.min(blueCirrusScore)

    # Clouds are reasonably bright in all visible bands.
    score = score.min(rescale(img.select(["red", "green", "blue"]).reduce(ee.Reducer.sum()), [0.2, 0.8]))

    # Clouds are reasonably bright in all infrared bands.
    score = score.min(rescale(img.select(["nir", "swir1", "swir2"]).reduce(ee.Reducer.sum()), [0.3, 0.8]))

    # However, clouds are not snow.
    ndsi = img.normalizedDifference(["green", "swir1"])
    score = score.min(rescale(ndsi, [0.8, 0.6]))

    score = score.multiply(100).byte().clamp(0, 100).rename(["cloudScore"])
    return score


#########################################################################
# Adapted from: https://earth.esa.int/documents/10174/3166008/ESA_Training_Vilnius_07072017_SAR_Optical_Snow_Ice_Exercises.pdf
def sentinel2SnowMask(img, dilatePixels=3.5):
    ndsi = img.normalizedDifference(["green", "swir1"])

    # IF NDSI > 0.40 AND ρ(NIR) > 0.11 THEN snow in open land
    # IF 0.1 < NDSI < 0.4 THEN snow in forest
    snowOpenLand = ndsi.gt(0.4).And(img.select(["nir"]).gt(0.11))
    snowForest = ndsi.gt(0.1).And(ndsi.lt(0.4))

    # Map.addLayer(snowOpenLand.selfMask(),{'min':1,'max':1,'palette':'88F'},'Snow Open Land')
    # Map.addLayer(snowForest.selfMask(),{'min':1,'max':1,'palette':'00F'},'Snow Forest')
    # Fractional snow cover (FSC, 0 % - 100% snow) can be detected by the approach of Salomonson
    # and Appel (2004, 2006), which was originally developed for MODIS data:
    # FSC = –0.01 + 1.45 * NDSI
    fsc = ndsi.multiply(1.45).subtract(0.01)
    # Map.addLayer(fsc,{'min':0,'max':1,'palette':'080,008'},'Fractional Snow Cover')
    snowMask = ((snowOpenLand.Or(snowForest)).Not()).focal_min(dilatePixels)
    return img.updateMask(snowMask)


#########################################################################
#########################################################################
# MODIS processing
#########################################################################
#########################################################################
# Some globals to deal with multi-spectral MODIS
# wTempSelectOrder = [2,3,0,1,4,6,5]#Band order to select to be Landsat 5-like if thermal is included
# wTempStdNames = ['blue', 'green', 'red', 'nir', 'swir1','temp','swir2']

# woTempSelectOrder = [2,3,0,1,4,5]#Band order to select to be Landsat 5-like if thermal is excluded
# woTempStdNames = ['blue', 'green', 'red', 'nir', 'swir1','swir2']
modis250SelectBands = ["sur_refl_b01", "sur_refl_b02"]
modis250BandNames = ["red", "nir"]

modis500SelectBands = ["sur_refl_b03", "sur_refl_b04", "sur_refl_b06", "sur_refl_b07"]
modis500BandNames = ["blue", "green", "swir1", "swir2"]

combinedModisBandNames = ["red", "nir", "blue", "green", "swir1", "swir2"]

dailyViewAngleBandNames = [
    "SensorZenith",
    "SensorAzimuth",
    "SolarZenith",
    "SolarAzimuth",
]
compositeViewAngleBandNames = ["SolarZenith", "ViewZenith", "RelativeAzimuth"]
# Dictionary of MODIS collections
modisCDict = {
    "eightDayNDVIA": "MODIS/061/MYD13Q1",
    "eightDayNDVIT": "MODIS/061/MOD13Q1",
    "eightDaySR250A": "MODIS/061/MYD09Q1",
    "eightDaySR250T": "MODIS/061/MOD09Q1",
    "eightDaySR500A": "MODIS/061/MYD09A1",
    "eightDaySR500T": "MODIS/061/MOD09A1",
    "eightDayLST1000A": "MODIS/061/MYD11A2",
    "eightDayLST1000T": "MODIS/061/MOD11A2",
    "dailySR250A": "MODIS/061/MYD09GQ",
    "dailySR250T": "MODIS/061/MOD09GQ",
    "dailySR500A": "MODIS/061/MYD09GA",
    "dailySR500T": "MODIS/061/MOD09GA",
    "dailyLST1000A": "MODIS/061/MYD11A1",
    "dailyLST1000T": "MODIS/061/MOD11A1",
}
multModisDict = {
    "tempNoAngleDaily": [
        ee.Image([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.02, 1, 1]),
        ["blue", "green", "red", "nir", "swir1", "temp", "swir2", "Emis_31", "Emis_32"],
    ],
    "tempNoAngleComposite": [
        ee.Image([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.02, 1, 1]),
        ["blue", "green", "red", "nir", "swir1", "temp", "swir2", "Emis_31", "Emis_32"],
    ],
    "tempAngleDaily": [
        ee.Image([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 1, 1, 1, 1, 0.02, 1, 1]),
        [
            "blue",
            "green",
            "red",
            "nir",
            "swir1",
            "temp",
            "swir2",
            "SensorZenith",
            "SensorAzimuth",
            "SolarZenith",
            "SolarAzimuth",
            "Emis_31",
            "Emis_32",
        ],
    ],
    "tempAngleComposite": [
        ee.Image([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 1, 1, 1, 0.02, 1, 1]),
        [
            "blue",
            "green",
            "red",
            "nir",
            "swir1",
            "temp",
            "swir2",
            "SolarZenith",
            "ViewZenith",
            "RelativeAzimuth",
            "Emis_31",
            "Emis_32",
        ],
    ],
    "noTempNoAngleDaily": [
        ee.Image([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001]),
        ["blue", "green", "red", "nir", "swir1", "swir2"],
    ],
    "noTempNoAngleComposite": [
        ee.Image([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001]),
        ["blue", "green", "red", "nir", "swir1", "swir2"],
    ],
    "noTempAngleDaily": [
        ee.Image([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 1, 1, 1, 1]),
        [
            "blue",
            "green",
            "red",
            "nir",
            "swir1",
            "swir2",
            "SensorZenith",
            "SensorAzimuth",
            "SolarZenith",
            "SolarAzimuth",
        ],
    ],
    "noTempAngleComposite": [
        ee.Image([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 1, 1, 1]),
        [
            "blue",
            "green",
            "red",
            "nir",
            "swir1",
            "swir2",
            "SolarZenith",
            "ViewZenith",
            "RelativeAzimuth",
        ],
    ],
}


#########################################################################
#########################################################################
# Helper function to join two collections- Source: code.earthengine.google.com
def joinCollections(
    c1,
    c2,
    maskAnyNullValues=True,
    joinProperty="system:time_start",
    joinPropertySecondary=None,
):

    if joinPropertySecondary == None:
        joinPropertySecondary = joinProperty

    def MergeBands(element):
        # A function to merge the bands together.
        # After a join, results are in 'primary' and 'secondary' properties.
        return ee.Image.cat(element.get("primary"), element.get("secondary"))

    join = ee.Join.inner()
    joinFilter = ee.Filter.equals(joinProperty, None, joinPropertySecondary)
    joined = ee.ImageCollection(join.apply(c1, c2, joinFilter))

    joined = ee.ImageCollection(joined.map(MergeBands))
    if maskAnyNullValues:

        def nuller(img):
            return img.mask(img.mask().And(img.reduce(ee.Reducer.min()).neq(0)))

        joined = joined.map(nuller)

    return joined


def smartJoin(primary, secondary, hourDiff):
    millis = hourDiff * 60 * 60 * 1000

    # Create a time filter to define a match as overlapping timestamps.
    maxDiffFilter = ee.Filter.maxDifference(
        {
            "difference": millis,
            "leftField": "system:time_start",
            "rightField": "system:time_start",
        }
    )
    # Define the join.
    saveBestJoin = ee.Join.saveBest({"matchKey": "bestImage", "measureKey": "timeDiff"})

    def MergeBands(element):
        # A function to merge the bands together.
        # After a join, results are in 'primary' and 'secondary' properties.
        return ee.Image.cat(element, element.get("bestImage"))

    # Apply the join.
    joined = saveBestJoin.apply(primary, secondary, maxDiffFilter)
    joined = joined.map(MergeBands)
    return joined


#########################################################################
# Join collections by space (intersection) and time (specified by user)
def spatioTemporalJoin(primary, secondary, hourDiff=24, outKey="secondary"):
    time = hourDiff * 60 * 60 * 1000

    outBns = ee.Image(secondary.first()).bandNames().map(lambda bn: ee.String(bn).cat("_").cat(outKey))
    # Define a spatial filter as geometries that intersect.
    spatioTemporalFilter = ee.Filter.And(
        ee.Filter.maxDifference(
            {
                "difference": time,
                "leftField": "system:time_start",
                "rightField": "system:time_start",
            }
        ),
        ee.Filter.intersects({"leftField": ".geo", "rightField": ".geo", "maxError": 10}),
    )
    # Define a save all join.
    saveBestJoin = ee.Join.saveBest({"matchKey": outKey, "measureKey": "timeDiff"})

    # Apply the join.
    joined = saveBestJoin.apply(primary, secondary, spatioTemporalFilter)

    def MergeBands(element):
        # A function to merge the bands together.
        # After a join, results are in 'primary' and 'secondary' properties.
        return ee.Image.cat(element, ee.Image(element.get(outKey)).rename(outBns))

    joined = joined.map(MergeBands)
    return joined


# Simple inner join function for featureCollections
# Matches features based on an exact match of the fieldName parameter
# An optional different field name can be provided for the second featureCollection
# Retains the geometry of the primary, but copies the properties of the secondary collection
def joinFeatureCollections(primary, secondary, fieldName, fieldNameSecondary=None):
    if fieldNameSecondary == None:
        fieldNameSecondary = fieldName
    # Use an equals filter to specify how the collections match.
    f = ee.Filter.equals(fieldName, None, fieldNameSecondary)

    # Define the join.
    innerJoin = ee.Join.inner("primary", "secondary")

    # Apply the join.
    joined = innerJoin.apply(primary, secondary, f)
    joined = joined.map(lambda f: ee.Feature(f.get("primary")).copyProperties(ee.Feature(f.get("secondary"))))

    return joined


#########################################################################
#########################################################################
# Method for removing spikes in time series
def despikeCollection(c, absoluteSpike, bandNo):
    c = c.toList(10000, 0)

    # Get book ends for adding back at the end
    first = c.slice(0, 1)
    last = c.slice(-1, None)

    # Slice the left, center, and right for the moving window
    left = c.slice(0, -2)
    center = c.slice(1, -1)
    right = c.slice(2, None)

    # Find how many images there are to compare
    seq = ee.List.sequence(0, left.length().subtract(1))

    # Compare the center to the left and right images
    def compare(i):
        lt = ee.Image(left.get(i))
        rt = ee.Image(right.get(i))

        ct = ee.Image(center.get(i))
        time_start = ct.get("system:time_start")
        time_end = ct.get("system:time_end")
        si = ct.get("system:index")

        diff1 = ct.select([bandNo]).add(1).subtract(lt.select([bandNo]).add(1))
        diff2 = ct.select([bandNo]).add(1).subtract(rt.select([bandNo]).add(1))

        highSpike = diff1.gt(absoluteSpike).And(diff2.gt(absoluteSpike))
        lowSpike = diff1.lt(-absoluteSpike).And(diff2.lt(-absoluteSpike))
        BinarySpike = highSpike.Or(lowSpike)

        originalMask = ct.mask()
        ct = ct.mask(BinarySpike.eq(0))

        doNotMask = lt.mask().Not().Or(rt.mask().Not())
        lrMean = lt.add(rt)
        lrMean = lrMean.divide(2)
        # out = ct.mask(doNotMask.Not().And(ct.mask()))
        out = ct.where(BinarySpike.eq(1).And(doNotMask.Not()), lrMean)
        return out.set("system:index", si).set("system:time_start", time_start).set("system:time_end", time_end)

    outCollection = seq.map(compare)

    # Add the bookends back on
    outCollection = ee.List([first, outCollection, last]).flatten()
    return ee.ImageCollection.fromImages(outCollection)


#########################################################################
#########################################################################
# Function to get MODIS data from various collections
# Will pull from daily or 8-day composite collections based on the boolean variable "daily"
def getModisData(
    startYear: int,
    endYear: int,
    startJulian: int,
    endJulian: int,
    daily: bool = False,
    maskWQA: bool = False,
    zenithThresh: int = 90,
    useTempInCloudMask: bool = True,
    addLookAngleBands: bool = False,
    resampleMethod: str = "near",
):
    """
    Retrieves MODIS imagery from Earth Engine for a specified period. Handles joining all MODIS collections for Terra and Aqua and aligning band names

    Args:
        startYear (int): The starting year for the data collection.
        endYear (int): The ending year for the data collection.
        startJulian (int): The starting Julian day of year for the data collection (1-366).
        endJulian (int): The ending Julian day of year for the data collection (1-366).
        daily (bool, optional): Determines whether to retrieve daily or 8-day composite data. Defaults to False (8-day composite).
        maskWQA (bool, optional): Controls whether to mask pixels based on the Quality Assurance (QA) band. Only applicable for daily data (daily=True). Defaults to False.
        zenithThresh (float, optional): Sets the threshold for solar zenith angle in degrees. Pixels with zenith angle exceeding this threshold will be masked out. Defaults to 90.
        useTempInCloudMask (bool, optional): Determines whether to use the thermal band for cloud masking. Defaults to True.
        addLookAngleBands (bool, optional): Controls whether to include view angle bands in the output. Defaults to False.
        resampleMethod (str, optional): Specifies the resampling method to apply to the imagery. Valid options include "near", "bilinear", and "bicubic". Defaults to "near" (nearest neighbor).

    Returns:
        ee.ImageCollection: A collection of MODIS imagery for the specified criteria.

    >>> import geeViz.getImagesLib as gil
    >>> Map = gil.Map
    >>> ee = gil.ee
    >>> crs = gil.common_projections["NLCD_CONUS"]["crs"]
    >>> transform = gil.common_projections["NLCD_CONUS"]["transform"]
    >>> scale = 240
    >>> transform[0] = scale
    >>> transform[4] = -scale
    >>> composite = gil.getModisData(2024, 2024, 190, 250, resampleMethod="bicubic").median().reproject(crs, transform)
    >>> Map.addLayer(composite, gil.vizParamsFalse, "MODIS Composite")
    >>> Map.setCenter(-111, 41, 7)
    >>> Map.turnOnInspector()
    >>> Map.view()
    """
    # Find which collections to pull from based on daily or 8-day
    if daily == False:
        a250C = modisCDict["eightDaySR250A"]
        t250C = modisCDict["eightDaySR250T"]
        a500C = modisCDict["eightDaySR500A"]
        t500C = modisCDict["eightDaySR500T"]
        a1000C = modisCDict["eightDayLST1000A"]
        t1000C = modisCDict["eightDayLST1000T"]
        viewAngleBandNames = compositeViewAngleBandNames
    else:
        a250C = modisCDict["dailySR250A"]
        t250C = modisCDict["dailySR250T"]
        a500C = modisCDict["dailySR500A"]
        t500C = modisCDict["dailySR500T"]
        a1000C = modisCDict["dailyLST1000A"]
        t1000C = modisCDict["dailyLST1000T"]
        viewAngleBandNames = dailyViewAngleBandNames

    # Pull images from each of the collections
    a250 = ee.ImageCollection(a250C).filter(ee.Filter.calendarRange(startYear, endYear, "year")).filter(ee.Filter.calendarRange(startJulian, endJulian)).select(modis250SelectBands, modis250BandNames)

    t250 = ee.ImageCollection(t250C).filter(ee.Filter.calendarRange(startYear, endYear, "year")).filter(ee.Filter.calendarRange(startJulian, endJulian)).select(modis250SelectBands, modis250BandNames)
    if addLookAngleBands:
        modis500SelectBandsT = modis500SelectBands + viewAngleBandNames
        modis500BandNamesT = modis500BandNames + viewAngleBandNames
    else:
        modis500SelectBandsT = modis500SelectBands
        modis500BandNamesT = modis500BandNames

    def get500(c):
        images = ee.ImageCollection(c).filter(ee.Filter.calendarRange(startYear, endYear, "year")).filter(ee.Filter.calendarRange(startJulian, endJulian))

        def applyZenith(img):
            img = img.mask(img.mask().And(img.select(["SensorZenith"]).lt(zenithThresh * 100)))
            if maskWQA:
                img = maskCloudsWQA(img)
            return img

        # Mask pixels above a certain zenith
        if daily:
            if maskWQA:
                print("Masking with QA band:", c)
            images = images.map(applyZenith)

        #     images = images.select(modis500SelectBands, modis500BandNames)
        # else:
        images = images.select(modis500SelectBandsT, modis500BandNamesT)

        return images

    a500 = get500(a500C)
    t500 = get500(t500C)

    # If thermal collection is wanted, pull it as well
    tempbandNames = ["temp", "Emis_31", "Emis_32"]
    if useTempInCloudMask:
        t1000 = ee.ImageCollection(t1000C).filter(ee.Filter.calendarRange(startYear, endYear, "year")).filter(ee.Filter.calendarRange(startJulian, endJulian)).select([0, 8, 9], tempbandNames)

        a1000 = ee.ImageCollection(a1000C).filter(ee.Filter.calendarRange(startYear, endYear, "year")).filter(ee.Filter.calendarRange(startJulian, endJulian)).select([0, 8, 9], tempbandNames)

    # Now all collections are pulled, start joining them
    # First join the 250 and 500 m Aqua
    # a = joinCollections(a250, a500, False)
    a = a250.linkCollection(a500, modis500BandNamesT)

    # Then Terra
    # t = joinCollections(t250, t500, False)
    t = t250.linkCollection(t500, modis500BandNamesT)
    # If temp was pulled, join that in as well
    # Also select the bands in an L5-like order and give descriptive names
    if useTempInCloudMask:
        # a = joinCollections(a, a1000, False)
        # t = joinCollections(t, t1000, False)
        a = a.linkCollection(a1000, tempbandNames)
        t = t.linkCollection(t1000, tempbandNames)
    #   tSelectOrder = wTempSelectOrder
    #   tStdNames = wTempStdNames

    # #If no thermal was pulled, leave that out
    # else:
    #   tSelectOrder = woTempSelectOrder
    #   tStdNames = woTempStdNames

    a = a.map(lambda img: img.set({"platform": "aqua"}))
    t = t.map(lambda img: img.set({"platform": "terra"}))

    if daily:
        dailyPiece = "Daily"
    else:
        dailyPiece = "Composite"

    if useTempInCloudMask:
        tempPiece = "temp"
    else:
        tempPiece = "noTemp"
    if addLookAngleBands:
        anglePiece = "Angle"
    else:
        anglePiece = "NoAngle"
    multKey = tempPiece + anglePiece + dailyPiece

    mult = multModisDict[multKey]
    multImage = mult[0]
    multNames = mult[1]

    # Join Terra and Aqua
    joined = ee.ImageCollection(a.merge(t))  # .select(tSelectOrder,tStdNames)

    def multiplyImg(img):
        return img.multiply(multImage).float().select(multNames).copyProperties(img, ["system:time_start", "system:time_end", "system:index"]).copyProperties(img)

    def setResample(img):
        return img.resample(resampleMethod)

    joined = joined.map(multiplyImg)

    if resampleMethod in ["bilinear", "bicubic"]:
        print("Setting resample method to ", resampleMethod)
        joined = joined.map(setResample)
    return joined


#########################################################################
#########################################################################
# Function to get cloud, cloud shadow busted modis images
# Takes care of matching different modis collections as well
def getProcessedModis(
    startYear: int,
    endYear: int,
    startJulian: int,
    endJulian: int,
    zenithThresh: float = 90,
    addLookAngleBands: bool = True,
    applyCloudScore: bool = True,
    applyTDOM: bool = True,
    useTempInCloudMask: bool = True,
    cloudScoreThresh: int = 20,
    performCloudScoreOffset: bool = True,
    cloudScorePctl: int = 10,
    zScoreThresh: float = -1,
    shadowSumThresh: float = 0.35,
    contractPixels: int = 0,
    dilatePixels: float = 2.5,
    shadowSumBands: list[str] = ["nir", "swir2"],
    resampleMethod: str = "bicubic",
    preComputedCloudScoreOffset: ee.Image | None = None,
    preComputedTDOMIRMean: ee.Image | None = None,
    preComputedTDOMIRStdDev: ee.Image | None = None,
    addToMap: bool = False,
    crs: str = "EPSG:4326",
    scale: int | None = 250,
    transform: list[int] | None = None,
):
    """
    Retrieves, processes, and filters MODIS imagery for a specified period.

    This function retrieves daily MODIS imagery from Earth Engine, applies various cloud and
    cloud shadow masking techniques, and returns a collection of processed images.

    Args:
        startYear (int): The starting year for the data collection.
        endYear (int): The ending year for the data collection.
        startJulian (int): The starting Julian day of year for the data collection (1-366).
        endJulian (int): The ending Julian day of year for the data collection (1-366).
        zenithThresh (float, optional): Sets the threshold for solar zenith angle in degrees. Pixels with zenith angle exceeding this threshold will be masked out. Defaults to 90.
        addLookAngleBands (bool, optional): Controls whether to include view angle bands in the output. Defaults to True.
        applyCloudScore (bool, optional): Determines whether to apply cloud masking based on the CloudScore simple algorithm adapted to MODIS. Defaults to True.
        applyTDOM (bool, optional): Determines whether to apply the TDOM (Temporal Dark Outlier Mask)
        technique for cloud shadow masking. Defaults to True.
        useTempInCloudMask (bool, optional): Determines whether to use the thermal band for cloud masking during MODIS data retrieval. Defaults to True.
        cloudScoreThresh (int, optional): Threshold for the CloudScore simple algorithm to classify a pixel as cloudy. Lower number masks out more. Defaults to 20.
        performCloudScoreOffset (bool, optional): Controls whether to perform an offset correction on the Cloud Score data over bright surfaces. Only use this if bright areas are being masked as clouds. Do not use this in persistently cloud areas. Defaults to True.
        cloudScorePctl (int, optional): Percentile of the Cloud Score product to use for the offset correction. Defaults to 10.
        zScoreThresh (float, optional): Threshold for the z-score used in TDOM cloud shadow masking. Pixels with z-scores below this threshold are masked. Defaults to -1.
        shadowSumThresh (float, optional): Threshold for the sum of reflectance in shadow bands used in TDOM cloud shadow masking. Pixels below this threshold and the zScoreThresh are masked as dark outliers (likely cloud shadows). Defaults to 0.35.
        contractPixels (int, optional): Number of pixels to contract cloud and shadow masks by. Defaults to 0.
        dilatePixels (float, optional): Number of pixels to dilate cloud and shadow masks by. Defaults to 2.5.
        shadowSumBands (list[str], optional): List of band names to use for calculating the sum of reflectance in TDOM cloud shadow masking. Defaults to ["nir", "swir2"].
        resampleMethod (str, optional): Specifies the resampling method to apply to the imagery. Valid options include "near", "bilinear", and "bicubic". Defaults to "bicubic".
        preComputedCloudScoreOffset (float | None, optional): Pre-computed Cloud Score offset value to avoid redundant calculations. Defaults to None (automatic calculation).
        preComputedTDOMIRMean (float | None, optional): Pre-computed mean of the IR band used in TDOM cloud shadow masking to avoid redundant calculations. Defaults to None (automatic calculation).
        preComputedTDOMIRStdDev (float | None, optional): Pre-computed standard deviation of the IR band used in TDOM cloud shadow masking to avoid redundant calculations. Defaults to None (automatic calculation).
        addToMap (bool, optional): Controls whether to add intermediate processing steps (masked medians) to the Earth Engine map for visualization purposes. Defaults to False.
        crs (str, optional): Only used if addToMap is True. Coordinate Reference System (CRS) for the output imagery. Defaults to "EPSG:4326".
        scale (int | None, optional): Only used if addToMap is True. Scale (resolution) of the output imagery in meters. Defaults to 250.
        transform (list | None, optional): Only used if addToMap is True. Optional transformation matrix to apply to the output imagery. Defaults to None.

    >>> import geeViz.getImagesLib as gil
    >>> Map = gil.Map
    >>> ee = gil.ee
    >>> crs = gil.common_projections["NLCD_CONUS"]["crs"]
    >>> transform = gil.common_projections["NLCD_CONUS"]["transform"]
    >>> scale = 240
    >>> transform[0] = scale
    >>> transform[4] = -scale
    >>> composite = gil.getProcessedModis(2024, 2024, 190, 250).median().reproject(crs, transform)
    >>> Map.addLayer(composite, gil.vizParamsFalse, "MODIS Composite")
    >>> Map.setCenter(-111, 41, 7)
    >>> Map.turnOnInspector()
    >>> Map.view()
    """

    args = formatArgs(locals())
    if "args" in args.keys():
        del args["args"]

    # Get joined modis collection
    modisImages = getModisData(
        startYear,
        endYear,
        startJulian,
        endJulian,
        daily=True,
        maskWQA=False,
        zenithThresh=zenithThresh,
        useTempInCloudMask=useTempInCloudMask,
        addLookAngleBands=addLookAngleBands,
        resampleMethod=resampleMethod,
    )

    if addToMap:
        Map.addLayer(
            modisImages.median().reproject(crs, transform, scale),
            vizParamsFalse,
            "Raw Median",
        )

    if applyCloudScore:
        print("Applying cloudScore")
        modisImages = applyCloudScoreAlgorithm(
            modisImages,
            modisCloudScore,
            cloudScoreThresh,
            cloudScorePctl,
            contractPixels,
            dilatePixels,
            performCloudScoreOffset,
            preComputedCloudScoreOffset,
        )

        if addToMap:
            Map.addLayer(
                modisImages.median().reproject(crs, transform, scale),
                vizParamsFalse,
                "Cloud Masked Median",
                False,
            )
            Map.addLayer(
                modisImages.min().reproject(crs, transform, scale),
                vizParamsFalse,
                "Cloud Masked Min",
                False,
            )

    if applyTDOM:
        print("Applying TDOM")
        # Find and mask out dark outliers
        modisImages = simpleTDOM2(
            modisImages,
            zScoreThresh,
            shadowSumThresh,
            contractPixels,
            dilatePixels,
            shadowSumBands,
            preComputedTDOMIRMean,
            preComputedTDOMIRStdDev,
        )

        if addToMap:
            Map.addLayer(
                modisImages.median().reproject(crs, transform, scale),
                vizParamsFalse,
                "Cloud/Cloud Shadow Masked Median",
                False,
            )
            Map.addLayer(
                modisImages.min().reproject(crs, transform, scale),
                vizParamsFalse,
                "Cloud/Cloud Shadow Masked Min",
                False,
            )

    modisImages = modisImages.map(simpleAddIndices)
    modisImages = modisImages.map(lambda img: img.float())
    return modisImages.set(args)


#########################################################################
# Function to take images and create a median composite every n days
def nDayComposites(images, startYear, endYear, startJulian, endJulian, compositePeriod):

    # create dummy image for with no values
    dummyImage = ee.Image(images.first())

    # convert to composites as defined above
    def getYrImages(yr):
        # take the year of the image
        yr = ee.Number(yr).int16()
        # filter out images for the year
        yrImages = images.filter(ee.Filter.calendarRange(yr, yr, "year"))

        # use dummy image to fill in gaps for GEE processing
        yrImages = fillEmptyCollections(yrImages, dummyImage)
        return yrImages

    # Get images for a specified start day
    def getJdImages(yr, yrImages, start):
        yr = ee.Number(yr).int16()
        start = ee.Number(start).int16()
        date = ee.Date.fromYMD(yr, 1, 1).advance(start.subtract(1), "day")
        index = date.format("yyyy-MM-dd")
        end = start.add(compositePeriod - 1).int16()
        jdImages = yrImages.filter(ee.Filter.calendarRange(start, end))
        jdImages = fillEmptyCollections(jdImages, dummyImage)
        composite = jdImages.median()
        return composite.set({"system:index": index, "system:time_start": date.millis()})

    # Set up wrappers
    def jdWrapper(yr, yrImages):
        return ee.FeatureCollection(ee.List.sequence(startJulian, endJulian, compositePeriod).map(lambda start: getJdImages(yr, yrImages, start)))

    def yrWrapper(yr):
        yrImages = getYrImages(yr)
        return jdWrapper(yr, yrImages)

    composites = ee.FeatureCollection(ee.List.sequence(startYear, endYear).map(lambda yr: yrWrapper(yr)))
    # return the composites as an image collection
    composites = ee.ImageCollection(composites.flatten())

    return composites


###############################################################
#########################################################################
def exportCollection(
    exportPathRoot, outputName, studyArea, crs, transform, scale, collection, startYear, endYear, startJulian, endJulian, compositingReducer, timebuffer, exportBands, overwrite=False, exportToAssets=False, exportToCloud=False, bucket=None
):

    # Take care of date wrapping
    dateWrapping = wrapDates(startJulian, endJulian)
    wrapOffset = dateWrapping[0]
    yearWithMajority = dateWrapping[1]

    # Clean up output name
    outputName = outputName.replace("/\s+/g", "-")
    outputName = outputName.replace("/\//g", "-")

    # Select bands for export
    collection = collection.select(exportBands)

    # Iterate across each year and export image
    for year in ee.List.sequence(startYear + timebuffer, endYear - timebuffer).getInfo():
        print("Exporting:", year)
        # Set up dates
        startYearT = year - timebuffer
        endYearT = year + timebuffer + yearWithMajority

        # Get yearly composite
        composite = collection.filter(ee.Filter.calendarRange(year + yearWithMajority, year + yearWithMajority, "year"))
        composite = ee.Image(composite.first()).clip(studyArea)

        # Add metadata, cast to integer, and export composite
        composite = composite.set(
            {
                "system:time_start": ee.Date.fromYMD(year + yearWithMajority, 6, 1).millis(),
                "yearBuffer": timebuffer,
            }
        )

        # Export the composite
        # Set up export name and path
        exportName = outputName + "_" + str(int(startYearT)) + "_" + str(int(endYearT)) + "_" + str(int(startJulian)) + "_" + str(int(endJulian))

        exportPath = exportPathRoot + "/" + exportName

        if exportToAssets:
            exportToAssetWrapper(
                composite,
                exportName,
                exportPath,
                "mean",
                studyArea,
                scale,
                crs,
                transform,
                overwrite,
            )

        if exportToCloud:
            exportToCloudStorageWrapper(
                composite,
                exportName,
                bucket,
                studyArea,
                scale,
                crs,
                transform,
                overwrite,
            )


#########################################################################
#########################################################################
# Function to export composite collection
def exportCompositeCollection(
    collection,
    exportPathRoot,
    outputName,
    origin,
    studyArea,
    crs,
    transform,
    scale,
    startYear,
    endYear,
    startJulian,
    endJulian,
    compositingMethod,
    timebuffer,
    toaOrSR,
    nonDivideBands,
    exportBands,
    additionalPropertyDict=None,
    overwrite=False,
):

    args = formatArgs(locals())

    pyramidingPolicy = "mean"
    dateWrapping = wrapDates(startJulian, endJulian)
    wrapOffset = dateWrapping[0]
    yearWithMajority = dateWrapping[1]

    # Clean up output name
    outputName = outputName.replace("/\s+/g", "-")
    outputName = outputName.replace("/\//g", "-")

    collection = collection.select(exportBands)
    for year in ee.List.sequence(startYear + timebuffer, endYear - timebuffer).getInfo():
        # Set up dates
        startYearT = year - timebuffer
        endYearT = year + timebuffer + yearWithMajority

        # Get yearly composite
        composite = collection.filter(ee.Filter.calendarRange(year + yearWithMajority, year + yearWithMajority, "year"))
        composite = ee.Image(composite.first())

        # Reformat data for export
        compositeBands = composite.bandNames()
        if nonDivideBands != None:
            composite10k = composite.select(compositeBands.removeAll(nonDivideBands)).multiply(10000)
            composite = composite10k.addBands(composite.select(nonDivideBands)).select(compositeBands).int16()

        else:
            composite = composite.multiply(10000).int16()

        startYearComposite = startYearT
        endYearComposite = endYearT
        systemTimeStartYear = year + yearWithMajority
        yearOriginal = year
        yearUsed = systemTimeStartYear
        # args['system:time_start'] = ee.Date.fromYMD(systemTimeStartYear, 6, 1).millis()

        composite = composite.set(formatArgs(args))

        composite = composite.set("system:time_start", ee.Date.fromYMD(systemTimeStartYear, 6, 1).millis())

        if additionalPropertyDict != None:
            if "args" in additionalPropertyDict.keys():
                del additionalPropertyDict["args"]
            composite = composite.set(formatArgs(additionalPropertyDict))

        # Export the composite
        # Set up export name and path
        exportName = outputName + "_" + toaOrSR + "_" + compositingMethod + "_" + str(int(startYearT)) + "_" + str(int(endYearT)) + "_" + str(int(startJulian)) + "_" + str(int(endJulian))
        exportPath = exportPathRoot + "/" + exportName

        exportToAssetWrapper(
            imageForExport=composite,
            assetName=exportName,
            assetPath=exportPath,
            pyramidingPolicyObject=pyramidingPolicy,
            roi=studyArea,
            scale=scale,
            crs=crs,
            transform=transform,
            overwrite=overwrite,
        )


#########################################################################
#########################################################################
# Wrapper function for getting Landsat imagery
def getLandsatWrapper(
    studyArea,
    startYear,
    endYear,
    startJulian,
    endJulian,
    timebuffer=0,
    weights=[1],
    compositingMethod="medoid",
    toaOrSR="SR",
    includeSLCOffL7=False,
    defringeL5=False,
    applyCloudScore=False,
    applyFmaskCloudMask=True,
    applyTDOM=False,
    applyFmaskCloudShadowMask=True,
    applyFmaskSnowMask=False,
    cloudScoreThresh=10,
    performCloudScoreOffset=True,
    cloudScorePctl=10,
    zScoreThresh=-1,
    shadowSumThresh=0.35,
    contractPixels=1.5,
    dilatePixels=3.5,
    correctIllumination=False,
    correctScale=250,
    exportComposites=False,
    outputName="Landsat-Composite",
    exportPathRoot="users/username/test",
    crs="EPSG:5070",
    transform=[30, 0, -2361915.0, 0, -30, 3177735.0],
    scale=None,
    resampleMethod="near",
    preComputedCloudScoreOffset=None,
    preComputedTDOMIRMean=None,
    preComputedTDOMIRStdDev=None,
    compositingReducer=None,
    harmonizeOLI=False,
    landsatCollectionVersion="C2",
    overwrite=False,
    verbose=False,
):

    toaOrSR = toaOrSR.upper()
    origin = "Landsat"
    args = formatArgs(locals())
    if "args" in args.keys():
        del args["args"]

    # Prepare dates
    wrapOffset = 0
    if startJulian > endJulian:
        wrapOffset = 365
    startDate = ee.Date.fromYMD(startYear, 1, 1).advance(startJulian - 1, "day")
    endDate = ee.Date.fromYMD(endYear, 1, 1).advance(endJulian - 1 + wrapOffset, "day")

    # Get Landsat image collection and apply cloud masking
    ls = getProcessedLandsatScenes(
        studyArea=studyArea,
        startYear=startYear,
        endYear=endYear,
        startJulian=startJulian,
        endJulian=endJulian,
        toaOrSR=toaOrSR,
        includeSLCOffL7=includeSLCOffL7,
        defringeL5=defringeL5,
        applyCloudScore=applyCloudScore,
        applyFmaskCloudMask=applyFmaskCloudMask,
        applyTDOM=applyTDOM,
        applyFmaskCloudShadowMask=applyFmaskCloudShadowMask,
        applyFmaskSnowMask=applyFmaskSnowMask,
        cloudScoreThresh=cloudScoreThresh,
        performCloudScoreOffset=performCloudScoreOffset,
        cloudScorePctl=cloudScorePctl,
        zScoreThresh=zScoreThresh,
        shadowSumThresh=shadowSumThresh,
        contractPixels=contractPixels,
        dilatePixels=dilatePixels,
        resampleMethod=resampleMethod,
        harmonizeOLI=harmonizeOLI,
        preComputedCloudScoreOffset=preComputedCloudScoreOffset,
        preComputedTDOMIRMean=preComputedTDOMIRMean,
        preComputedTDOMIRStdDev=preComputedTDOMIRStdDev,
        landsatCollectionVersion=landsatCollectionVersion,
        verbose=verbose,
    )

    # Add zenith and azimuth
    if correctIllumination:
        print("Adding zenith and azimuth for terrain correction")
        ls = ls.map(lambda img: addZenithAzimuth(img, toaOrSR))

    # Create composite time series
    ts = compositeTimeSeries(
        ls=ls,
        startYear=startYear,
        endYear=endYear,
        startJulian=startJulian,
        endJulian=endJulian,
        timebuffer=timebuffer,
        weights=weights,
        compositingMethod=compositingMethod,
        compositingReducer=compositingReducer,
    )

    # Correct illumination
    if correctIllumination:
        print("Correcting illumination")
        ts = ts.map(illuminationCondition).map(lambda img: illuminationCorrection(img, correctScale, studyArea))

    # Export composites
    if exportComposites:
        if compositingMethod == "medoid":
            exportBands = [
                "blue",
                "green",
                "red",
                "nir",
                "swir1",
                "swir2",
                "temp",
                "compositeObsCount",
                "sensor",
                "year",
                "julianDay",
            ]
            nonDivideBands = [
                "temp",
                "compositeObsCount",
                "sensor",
                "year",
                "julianDay",
            ]
        else:
            exportBands = [
                "blue",
                "green",
                "red",
                "nir",
                "swir1",
                "swir2",
                "temp",
                "compositeObsCount",
            ]
            nonDivideBands = ["temp", "compositeObsCount"]

        exportCompositeCollection(
            collection=ts,
            exportPathRoot=exportPathRoot,
            outputName=outputName,
            origin=origin,
            studyArea=studyArea,
            crs=crs,
            transform=transform,
            scale=scale,
            startYear=startYear,
            endYear=endYear,
            startJulian=startJulian,
            endJulian=endJulian,
            compositingMethod=compositingMethod,
            timebuffer=timebuffer,
            toaOrSR=toaOrSR,
            nonDivideBands=nonDivideBands,
            exportBands=exportBands,
            # weights = weights,
            # defringeL5 = False,
            # includeSLCOffL7 = includeSLCOffL7,
            # convertToDailyMosaics = 'NA',
            # applyQABand = False,
            # applyCloudScore = applyCloudScore,
            # applyFmaskCloudMask = applyFmaskCloudMask,
            # applyCloudProbability = 'NA',
            # applyTDOM = applyTDOM,
            # applyFmaskCloudShadowMask = applyFmaskCloudShadowMask,
            # applyFmaskSnowMask = applyFmaskSnowMask,
            # applyShadowShift = 'NA',
            # cloudHeights = cloudHeights,
            # cloudScoreThresh = cloudScoreThresh,
            # performCloudScoreOffset = performCloudScoreOffset,
            # cloudScorePctl = cloudScorePctl,
            # zScoreThresh = zScoreThresh,
            # shadowSumThresh = shadowSumThresh,
            # contractPixels = contractPixels,
            # dilatePixels = dilatePixels,
            # correctIllumination = correctIllumination,
            # correctScale = correctScale,
            # nonDivideBands = nonDivideBands,
            # exportBands = exportBands,
            # resampleMethod = resampleMethod,
            # runChastainHarmonization = 'NA',
            additionalPropertyDict=args,
            overwrite=overwrite,
        )

    args["processedScenes"] = ls
    args["processedComposites"] = ts

    return args


#########################################################################
#########################################################################
# Wrapper function for getting Landsat imagery
def getProcessedLandsatScenes(
    studyArea: ee.Geometry | ee.Feature | ee.FeatureCollection,
    startYear: int,
    endYear: int,
    startJulian: int,
    endJulian: int,
    toaOrSR: str = "SR",
    includeSLCOffL7: bool = False,
    defringeL5: bool = False,
    applyCloudScore: bool = False,
    applyFmaskCloudMask: bool = True,
    applyTDOM: bool = False,
    applyFmaskCloudShadowMask: bool = True,
    applyFmaskSnowMask: bool = False,
    cloudScoreThresh: int = 10,
    performCloudScoreOffset: bool = True,
    cloudScorePctl: int = 10,
    zScoreThresh: float = -1,
    shadowSumThresh: float = 0.35,
    contractPixels: float = 1.5,
    dilatePixels: float = 3.5,
    shadowSumBands: list[str] = ["nir", "swir1"],
    resampleMethod: str = "near",
    harmonizeOLI: bool = False,
    preComputedCloudScoreOffset: ee.Image | None = None,
    preComputedTDOMIRMean: ee.Image | None = None,
    preComputedTDOMIRStdDev: ee.Image | None = None,
    landsatCollectionVersion: str = "C2",
    verbose: bool = False,
) -> ee.ImageCollection:
    """
    Retrieves, processes, and filters Landsat scenes for a specified area and time period.

    This function retrieves Landsat scenes from Earth Engine, applies various cloud,
    cloud shadow, and snow masking techniques, calculates common indices, and returns
    a collection of processed images.

    Args:
        studyArea (ee.Geometry): The geographic area of interest (study area) as an Earth Engine geometry, Feature, or FeatureCollection object.
        startYear (int): The starting year for the data collection.
        endYear (int): The ending year for the data collection.
        startJulian (int): The starting Julian day of year for the data collection (1-365).
        endJulian (int): The ending Julian day of year for the data collection (1-365).
        toaOrSR (str, optional): Flag indicating desired reflectance type: "TOA" (Top Of Atmosphere) or "SR" (Surface Reflectance). Defaults to "SR".
        includeSLCOffL7 (bool, optional): Determines whether to include Landsat 7 SLC-off scenes. Defaults to False.
        defringeL5 (bool, optional): Determines whether to defringe Landsat 5 scenes. Defaults to False.
        applyCloudScore (bool, optional): Determines whether to apply cloud masking based on the CloudScore simple algorithm. Defaults to False.
        applyFmaskCloudMask (bool, optional): Determines whether to apply the Fmask cloud mask. Defaults to True.
        applyTDOM (bool, optional): Determines whether to apply the TDOM (Temporal Dark Outlier Mask) technique for cloud shadow masking. Defaults to False.
        applyFmaskCloudShadowMask (bool, optional): Determines whether to apply the Fmask cloud shadow mask. Defaults to True.
        applyFmaskSnowMask (bool, optional): Determines whether to apply the Fmask snow mask. Defaults to False.
        cloudScoreThresh (int, optional): Threshold for the CloudScore simple algorithm to classify a pixel as cloudy. Lower number masks out more. Defaults to 10.
        performCloudScoreOffset (bool, optional): Controls whether to perform an offset correction on the Cloud Score data over bright surfaces. Only use this if bright areas are being masked as clouds. Do not use this in persistently cloud areas. Defaults to True.
        cloudScorePctl (int, optional): Percentile of the Cloud Score product to use for the offset correction. Defaults to 10.
        zScoreThresh (float, optional): Threshold for the z-score used in TDOM cloud shadow masking. Pixels with z-scores below this threshold are masked. Defaults to -1.
        shadowSumThresh (float, optional): Threshold for the sum of reflectance in shadow bands used in TDOM cloud shadow masking. Pixels below this threshold and the zScoreThresh are masked as dark outliers (likely cloud shadows). Defaults to 0.35.
        contractPixels (float, optional): Number of pixels to contract cloud and shadow masks by. Defaults to 1.5.
        dilatePixels (float, optional): Number of pixels to dilate cloud and shadow masks by. Defaults to 3.5.
        shadowSumBands (list[str], optional): List of band names to use for calculating the sum of reflectance in TDOM cloud shadow masking. Defaults to ["nir", "swir1"].
        resampleMethod (str, optional): Specifies the resampling method to apply to the imagery. Valid options include "near", "bilinear", and "bicubic". Defaults to "near".
        harmonizeOLI (bool, optional): Determines whether to harmonize OLI data to match TM/ETM+ spectral response. Defaults to False.
        preComputedCloudScoreOffset (float | None, optional): Pre-computed Cloud Score offset value to avoid redundant calculations. Defaults to None (automatic calculation).
        preComputedTDOMIRMean (float | None, optional): Pre-computed mean of the IR band used in TDOM cloud shadow masking to avoid redundant calculations. Defaults to None (automatic calculation).
        preComputedTDOMIRStdDev (float | None, optional): Pre-computed standard deviation of the IR band used in TDOM cloud shadow masking to avoid redundant calculations. Defaults to None (automatic calculation).
        landsatCollectionVersion (str, optional): Specifies the Landsat collection version to use (e.g., "C1", "C2"). Defaults to "C2".
        verbose (bool, optional): Controls whether to print additional information during processing. Defaults to False.

    Returns:
        ee.ImageCollection: A collection of analysis ready, cloud and cloud shadow asked Landsat scenes with common band names.

    >>> import geeViz.getImagesLib as gil
    >>> Map = gil.Map
    >>> ee = gil.ee
    >>> studyArea = gil.testAreas["CO"]
    >>> composite = gil.getProcessedLandsatScenes(studyArea, 2023, 2023, 190, 250).median()
    >>> Map.addLayer(composite, gil.vizParamsFalse, "Landsat Composite")
    >>> Map.addLayer(studyArea, {"canQuery": False}, "Study Area")
    >>> Map.centerObject(studyArea)
    >>> Map.turnOnInspector()
    >>> Map.view()

    """
    origin = "Landsat"
    toaOrSR = toaOrSR.upper()
    if toaOrSR.lower() == "toa" and landsatCollectionVersion.lower() == "c1" and (applyFmaskCloudMask or applyFmaskCloudShadowMask or applyFmaskSnowMask):
        addPixelQA = True
    else:
        addPixelQA = False

    # Prepare dates
    # Wrap the dates if needed
    wrapOffset = 0
    if startJulian > endJulian:
        wrapOffset = 365
    startDate = ee.Date.fromYMD(startYear, 1, 1).advance(startJulian - 1, "day")
    endDate = ee.Date.fromYMD(endYear, 1, 1).advance(endJulian - 1 + wrapOffset, "day")

    args = formatArgs(locals())
    if "args" in args.keys():
        del args["args"]

    print("Get Processed Landsat: ")
    print(
        "Start date:",
        startDate.format("MMM dd yyyy").getInfo(),
        ", End date:",
        endDate.format("MMM dd yyyy").getInfo(),
    )
    if verbose:
        for arg in args.keys():
            print(arg, ": ", args[arg])

    # Get Landsat image collection
    ls = getLandsat(
        studyArea=studyArea,
        startDate=startDate,
        endDate=endDate,
        startJulian=startJulian,
        endJulian=endJulian,
        toaOrSR=toaOrSR,
        includeSLCOffL7=includeSLCOffL7,
        defringeL5=defringeL5,
        addPixelQA=addPixelQA,
        resampleMethod=resampleMethod,
        landsatCollectionVersion=landsatCollectionVersion,
    )

    # Apply relevant cloud masking methods
    if applyCloudScore:
        print("Applying Cloud Score")
        ls = applyCloudScoreAlgorithm(
            collection=ls,
            cloudScoreFunction=landsatCloudScore,
            cloudScoreThresh=cloudScoreThresh,
            cloudScorePctl=cloudScorePctl,
            contractPixels=contractPixels,
            dilatePixels=dilatePixels,
            performCloudScoreOffset=performCloudScoreOffset,
            preComputedCloudScoreOffset=preComputedCloudScoreOffset,
        )

    if applyFmaskCloudMask:
        print("Applying Fmask Cloud Mask")
        ls = ls.map(
            lambda img: applyBitMask(
                img,
                fmaskBitDict[landsatCollectionVersion]["cloud"],
                landsatFmaskBandNameDict[landsatCollectionVersion],
            )
        )

    if applyTDOM:
        print("Applying TDOM Shadow Mask")
        ls = simpleTDOM2(
            collection=ls,
            zScoreThresh=zScoreThresh,
            shadowSumThresh=shadowSumThresh,
            contractPixels=contractPixels,
            dilatePixels=dilatePixels,
            shadowSumBands=["nir", "swir1"],
            preComputedTDOMIRMean=preComputedTDOMIRMean,
            preComputedTDOMIRStdDev=preComputedTDOMIRStdDev,
        )

    if applyFmaskCloudShadowMask:
        print("Applying Fmask Shadow Mask")
        ls = ls.map(
            lambda img: applyBitMask(
                img,
                fmaskBitDict[landsatCollectionVersion]["shadow"],
                landsatFmaskBandNameDict[landsatCollectionVersion],
            )
        )

    if applyFmaskSnowMask:
        print("Applying Fmask snow mask")
        ls = ls.map(
            lambda img: applyBitMask(
                img,
                fmaskBitDict[landsatCollectionVersion]["snow"],
                landsatFmaskBandNameDict[landsatCollectionVersion],
            )
        )

    # Add common indices
    ls = ls.map(simpleAddIndices).map(getTasseledCap).map(simpleAddTCAngles)

    # Add Sensor Band
    ls = ls.map(lambda img: addSensorBand(img, landsatCollectionVersion + "_landsat", toaOrSR))

    return ls.set(args)


#########################################################################
#########################################################################
# Wrapper function for getting Sentinel2 imagery
def getProcessedSentinel2Scenes(
    studyArea,
    startYear,
    endYear,
    startJulian,
    endJulian,
    applyQABand=False,
    applyCloudScore=False,
    applyShadowShift=False,
    applyTDOM=False,
    cloudScoreThresh=20,
    performCloudScoreOffset=True,
    cloudScorePctl=10,
    cloudHeights=ee.List.sequence(500, 10000, 500),
    zScoreThresh=-1,
    shadowSumThresh=0.35,
    contractPixels=1.5,
    dilatePixels=3.5,
    shadowSumBands=["nir", "swir1"],
    resampleMethod="aggregate",
    toaOrSR="TOA",
    convertToDailyMosaics=True,
    applyCloudProbability=False,
    preComputedCloudScoreOffset=None,
    preComputedTDOMIRMean=None,
    preComputedTDOMIRStdDev=None,
    cloudProbThresh=40,
    verbose=False,
    applyCloudScorePlus=True,
    cloudScorePlusThresh=0.6,
    cloudScorePlusScore="cs",
):

    origin = "Sentinel2"
    toaOrSR = toaOrSR.upper()

    # Prepare dates
    # Wrap the dates if needed
    wrapOffset = 0
    if startJulian > endJulian:
        wrapOffset = 365
    startDate = ee.Date.fromYMD(startYear, 1, 1).advance(startJulian - 1, "day")
    endDate = ee.Date.fromYMD(endYear, 1, 1).advance(endJulian - 1 + wrapOffset, "day")

    args = formatArgs(locals())
    if "args" in args.keys():
        del args["args"]

    print("Get Processed Sentinel2: ")
    print(
        "Start date:",
        startDate.format("MMM dd yyyy").getInfo(),
        ", End date:",
        endDate.format("MMM dd yyyy").getInfo(),
    )
    if verbose:
        for arg in args.keys():
            print(arg, ": ", args[arg])

    # Get Sentinel2 image collection
    s2s = getS2(
        studyArea=studyArea,
        startDate=startDate,
        endDate=endDate,
        startJulian=startJulian,
        endJulian=endJulian,
        resampleMethod=resampleMethod,
        toaOrSR=toaOrSR,
        convertToDailyMosaics=convertToDailyMosaics,
        addCloudProbability=applyCloudProbability,
        addCloudScorePlus=applyCloudScorePlus,
        cloudScorePlusScore=cloudScorePlusScore,
    )

    if applyQABand:
        print("Applying QA Band Cloud Mask")
        s2s = s2s.map(maskS2clouds)

    if applyCloudScore:
        print("Applying Cloud Score")
        s2s = applyCloudScoreAlgorithm(
            collection=s2s,
            cloudScoreFunction=sentinel2CloudScore,
            cloudScoreThresh=cloudScoreThresh,
            cloudScorePctl=cloudScorePctl,
            contractPixels=contractPixels,
            dilatePixels=dilatePixels,
            performCloudScoreOffset=performCloudScoreOffset,
            preComputedCloudScoreOffset=preComputedCloudScoreOffset,
        )

    if applyCloudProbability:
        print("Applying Cloud Probability")
        s2s = s2s.map(lambda img: img.updateMask(img.select(["cloud_probability"]).lte(cloudProbThresh)))

    if applyCloudScorePlus:
        print("Applying cloudScore+")
        s2s = s2s.map(lambda img: img.updateMask(img.select(["cloudScorePlus"]).gte(cloudScorePlusThresh)))

    if applyShadowShift:
        print("Applying Shadow Shift")
        s2s = s2s.map(
            lambda img: projectShadowsWrapper(
                img=img,
                cloudThresh=cloudScoreThresh,
                irSumThresh=shadowSumThresh,
                contractPixels=contractPixels,
                dilatePixels=dilatePixels,
                cloudHeights=cloudHeights,
            )
        )

    if applyTDOM:
        print("Applying TDOM")
        s2s = simpleTDOM2(
            collection=s2s,
            zScoreThresh=zScoreThresh,
            shadowSumThresh=shadowSumThresh,
            contractPixels=contractPixels,
            dilatePixels=dilatePixels,
            shadowSumBands=["nir", "swir1"],
            preComputedTDOMIRMean=preComputedTDOMIRMean,
            preComputedTDOMIRStdDev=preComputedTDOMIRStdDev,
        )

    # Add common indices
    s2s = s2s.map(simpleAddIndices).map(getTasseledCap).map(simpleAddTCAngles).map(lambda img: img.addBands(img.normalizedDifference(["re1", "red"]).select([0], ["NDCI"])))
    # Add Sensor Band
    s2s = s2s.map(lambda img: addSensorBand(img, "sentinel2", toaOrSR))

    return s2s.set(args)


#########################################################################
#########################################################################
def superSimpleGetS2(
    studyArea: ee.Geometry | ee.Feature | ee.FeatureCollection | None,
    startDate: ee.Date | datetime.datetime | str,
    endDate: ee.Date | datetime.datetime | str,
    startJulian: int = 1,
    endJulian: int = 365,
    toaOrSR: str = "TOA",
    applyCloudScorePlus: bool = True,
    cloudScorePlusThresh: float = 0.6,
    cloudScorePlusScore: str = "cs",
) -> ee.ImageCollection:
    """
    This function retrieves Sentinel-2 satellite imagery from Earth Engine for a specified study area and date range.
    It applies the cloudScore+ algorithm unless told otherwise.

    Args:
        studyArea (ee.Geometry, ee.Feature, ee.FeatureCollection, or None, optional): An Earth Engine geometry object representing the area of interest. If set to None, startJulian and endJulian cannot be used. Doing so will cause the image to never render.
        startDate (ee.Date, datetime.datetime, or str): The start date for the image collection in YYYY-MM-DD format.
        endDate (ee.Date, datetime.datetime, or str): The end date for the image collection in YYYY-MM-DD format.
        startJulian (int, optional): The start Julian day of the desired data. Defaults to 1.
        endJulian (int, optional): The end Julian day of the desired data. Defaults to 365.
        toaOrSR (str, optional): Specifies whether to retrieve data in Top-Of-Atmosphere (TOA) reflectance or Surface Reflectance (SR). Defaults to "TOA".
        applyCloudScorePlus (bool, optional): Determines whether to apply cloud filtering based on the Cloud Score Plus product. Defaults to True.
        cloudScorePlusThresh (float, optional): Sets the threshold for cloud cover percentage based on Cloud Score Plus. Images with cloud cover exceeding this threshold will be masked out if `applyCloudScorePlus` is True. A higher value will mask out more pixels (call them cloud/cloud-shadow). Defaults to 0.6.
        cloudScorePlusScore (str, optional): One of "cs" - Tends to mask out more. Commits ephemeral water, but doesn't omit cloud shadows as much or "cs_cdf" - Tends to mask out less, notably fewer water bodies and shadows. This can result in omitting cloud shadows, but not committing ephemeral water as a cloud shadow. Specifies the band name within the Cloud Score Plus product containing the cloud cover information. Defaults to "cs".

    Returns:
        ee.ImageCollection: A collection of cloud and cloud-shadow-free Sentinel-2 satellite images filtered by the specified criteria.


    >>> import geeViz.getImagesLib as gil
    >>> Map = gil.Map
    >>> ee = gil.ee
    >>> studyArea = gil.testAreas["CA"]
    >>> composite = gil.superSimpleGetS2(studyArea, "2024-01-01", "2024-12-31", 190, 250).median()
    >>> Map.addLayer(composite, gil.vizParamsFalse10k, "Sentinel-2 Composite")
    >>> Map.addLayer(studyArea, {"canQuery": False}, "Study Area")
    >>> Map.centerObject(studyArea)
    >>> Map.turnOnInspector()
    >>> Map.view()

    """

    toaOrSR = toaOrSR.upper()
    startDate = ee.Date(startDate)
    endDate = ee.Date(endDate)

    s2s = ee.ImageCollection(s2CollectionDict[toaOrSR]).filterDate(startDate, endDate.advance(1, "day"))

    if studyArea != None:
        s2s = s2s.filterBounds(studyArea)

        if startJulian != 1 or endJulian != 365:
            s2s = s2s.filter(ee.Filter.calendarRange(startJulian, endJulian))

    s2s = s2s.select(sensorBandDict[toaOrSR], sensorBandNameDict[toaOrSR])

    cloudScorePlus = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED").select([cloudScorePlusScore], ["cloudScorePlus"])

    s2s = s2s.linkCollection(cloudScorePlus, ["cloudScorePlus"])

    if applyCloudScorePlus:
        s2s = s2s.map(lambda img: img.updateMask(img.select(["cloudScorePlus"]).gte(cloudScorePlusThresh)))
    return s2s


#########################################################################
#########################################################################
# Wrapper function for getting Sentinel 2 imagery
def getSentinel2Wrapper(
    studyArea,
    startYear,
    endYear,
    startJulian,
    endJulian,
    timebuffer=0,
    weights=[1],
    compositingMethod="medoid",
    applyQABand=False,
    applyCloudScore=False,
    applyShadowShift=False,
    applyTDOM=False,
    cloudScoreThresh=20,
    performCloudScoreOffset=True,
    cloudScorePctl=10,
    cloudHeights=ee.List.sequence(500, 10000, 500),
    zScoreThresh=-1,
    shadowSumThresh=0.35,
    contractPixels=1.5,
    dilatePixels=3.5,
    shadowSumBands=["nir", "swir1"],
    correctIllumination=False,
    correctScale=250,
    exportComposites=False,
    outputName="Sentinel2-Composite",
    exportPathRoot="users/username/test",
    crs="EPSG:5070",
    transform=[10, 0, -2361915.0, 0, -10, 3177735.0],
    scale=None,
    resampleMethod="aggregate",
    toaOrSR="TOA",
    convertToDailyMosaics=True,
    applyCloudProbability=False,
    preComputedCloudScoreOffset=None,
    preComputedTDOMIRMean=None,
    preComputedTDOMIRStdDev=None,
    cloudProbThresh=40,
    overwrite=False,
    verbose=False,
    applyCloudScorePlus=True,
    cloudScorePlusThresh=0.6,
    cloudScorePlusScore="cs",
):

    origin = "Sentinel2"
    toaOrSR = toaOrSR.upper()

    args = formatArgs(locals())
    if "args" in args.keys():
        del args["args"]

    s2s = getProcessedSentinel2Scenes(
        studyArea=studyArea,
        startYear=startYear,
        endYear=endYear,
        startJulian=startJulian,
        endJulian=endJulian,
        applyQABand=applyQABand,
        applyCloudScore=applyCloudScore,
        applyShadowShift=applyShadowShift,
        applyTDOM=applyTDOM,
        cloudScoreThresh=cloudScoreThresh,
        performCloudScoreOffset=performCloudScoreOffset,
        cloudScorePctl=cloudScorePctl,
        cloudHeights=cloudHeights,
        zScoreThresh=zScoreThresh,
        shadowSumThresh=shadowSumThresh,
        contractPixels=contractPixels,
        dilatePixels=dilatePixels,
        shadowSumBands=shadowSumBands,
        resampleMethod=resampleMethod,
        toaOrSR=toaOrSR,
        convertToDailyMosaics=convertToDailyMosaics,
        applyCloudProbability=applyCloudProbability,
        preComputedCloudScoreOffset=preComputedCloudScoreOffset,
        preComputedTDOMIRMean=preComputedTDOMIRMean,
        preComputedTDOMIRStdDev=preComputedTDOMIRStdDev,
        cloudProbThresh=cloudProbThresh,
        verbose=verbose,
        applyCloudScorePlus=applyCloudScorePlus,
        cloudScorePlusThresh=cloudScorePlusThresh,
        cloudScorePlusScore=cloudScorePlusScore,
    )

    # Add zenith and azimuth
    # if correctIllumination:
    #  s2s = s2s.map(function(img){
    #    return addZenithAzimuth(img,'TOA',{'TOA':'MEAN_SOLAR_ZENITH_ANGLE'},{'TOA':'MEAN_SOLAR_AZIMUTH_ANGLE'});
    #  });
    # }

    # Create composite time series
    ts = compositeTimeSeries(
        ls=s2s,
        startYear=startYear,
        endYear=endYear,
        startJulian=startJulian,
        endJulian=endJulian,
        timebuffer=timebuffer,
        weights=weights,
        compositingMethod=compositingMethod,
    )

    # Correct illumination
    # if (correctIllumination){
    #   f = ee.Image(ts.first());
    #   Map.addLayer(f,vizParamsFalse,'First-non-illuminated',false);

    #   print('Correcting illumination');
    #   ts = ts.map(illuminationCondition)
    #     .map(function(img){
    #       return illuminationCorrection(img, correctScale,studyArea,[ 'blue', 'green', 'red','nir','swir1', 'swir2']);
    #     });
    #   f = ee.Image(ts.first());
    #   Map.addLayer(f,vizParamsFalse,'First-illuminated',false);

    # Export composites
    if exportComposites:
        exportBandDict = {
            "SR_medoid": [
                "cb",
                "blue",
                "green",
                "red",
                "re1",
                "re2",
                "re3",
                "nir",
                "nir2",
                "waterVapor",
                "swir1",
                "swir2",
                "compositeObsCount",
                "sensor",
                "year",
                "julianDay",
            ],
            "SR_median": [
                "cb",
                "blue",
                "green",
                "red",
                "re1",
                "re2",
                "re3",
                "nir",
                "nir2",
                "waterVapor",
                "swir1",
                "swir2",
                "compositeObsCount",
            ],
            "TOA_medoid": [
                "cb",
                "blue",
                "green",
                "red",
                "re1",
                "re2",
                "re3",
                "nir",
                "nir2",
                "waterVapor",
                "cirrus",
                "swir1",
                "swir2",
                "compositeObsCount",
                "sensor",
                "year",
                "julianDay",
            ],
            "TOA_median": [
                "cb",
                "blue",
                "green",
                "red",
                "re1",
                "re2",
                "re3",
                "nir",
                "nir2",
                "waterVapor",
                "cirrus",
                "swir1",
                "swir2",
                "compositeObsCount",
            ],
        }
        nonDivideBandDict = {
            "medoid": ["compositeObsCount", "sensor", "year", "julianDay"],
            "median": ["compositeObsCount"],
        }
        exportBands = exportBandDict[toaOrSR + "_" + compositingMethod]
        nonDivideBands = nonDivideBandDict[compositingMethod]

        exportCompositeCollection(
            collection=ts,
            exportPathRoot=exportPathRoot,
            outputName=outputName,
            origin=origin,
            studyArea=studyArea,
            crs=crs,
            transform=transform,
            scale=scale,
            startYear=startYear,
            endYear=endYear,
            startJulian=startJulian,
            endJulian=endJulian,
            compositingMethod=compositingMethod,
            timebuffer=timebuffer,
            toaOrSR=toaOrSR,
            nonDivideBands=nonDivideBands,
            exportBands=exportBands,
            additionalPropertyDict=args,
            overwrite=overwrite,
        )

    args["processedScenes"] = s2s
    args["processedComposites"] = ts

    return args


# Hybrid get Landsat and Sentinel 2 processed scenes
# Handles getting processed scenes  with Landsat and Sentinel 2
def getProcessedLandsatAndSentinel2Scenes(
    studyArea,
    startYear,
    endYear,
    startJulian,
    endJulian,
    toaOrSR="TOA",
    includeSLCOffL7=False,
    defringeL5=False,
    applyQABand=False,
    applyCloudProbability=False,
    applyShadowShift=False,
    applyCloudScoreLandsat=False,
    applyCloudScoreSentinel2=False,
    applyTDOMLandsat=True,
    applyTDOMSentinel2=False,
    applyFmaskCloudMask=True,
    applyFmaskCloudShadowMask=True,
    applyFmaskSnowMask=False,
    cloudHeights=ee.List.sequence(500, 10000, 500),
    cloudScoreThresh=20,
    performCloudScoreOffset=True,
    cloudScorePctl=10,
    zScoreThresh=-1,
    shadowSumThresh=0.35,
    contractPixels=1.5,
    dilatePixels=3.5,
    shadowSumBands=["nir", "swir1"],
    landsatResampleMethod="near",
    sentinel2ResampleMethod="aggregate",
    convertToDailyMosaics=True,
    runChastainHarmonization=True,
    correctIllumination=False,
    correctScale=250,
    preComputedLandsatCloudScoreOffset=None,
    preComputedLandsatTDOMIRMean=None,
    preComputedLandsatTDOMIRStdDev=None,
    preComputedSentinel2CloudScoreOffset=None,
    preComputedSentinel2TDOMIRMean=None,
    preComputedSentinel2TDOMIRStdDev=None,
    cloudProbThresh=40,
    landsatCollectionVersion="C2",
    verbose=False,
    applyCloudScorePlus=True,
    cloudScorePlusThresh=0.6,
    cloudScorePlusScore="cs",
):

    if toaOrSR == "SR":
        runChastainHarmonization = False

    origin = "Landsat-Sentinel2-Hybrid"
    toaOrSR = toaOrSR.upper()

    # Prepare dates
    # Wrap the dates if needed
    wrapOffset = 0
    if startJulian > endJulian:
        wrapOffset = 365
    startDate = ee.Date.fromYMD(startYear, 1, 1).advance(startJulian - 1, "day")
    endDate = ee.Date.fromYMD(endYear, 1, 1).advance(endJulian - 1 + wrapOffset, "day")

    args = formatArgs(locals())
    if "args" in args.keys():
        del args["args"]

    print("Get Processed Landsat and Sentinel2 Scenes: ")
    print(
        "Start date:",
        startDate.format("MMM dd yyyy").getInfo(),
        ", End date:",
        endDate.format("MMM dd yyyy").getInfo(),
    )
    if verbose:
        for arg in args.keys():
            print(arg, ": ", args[arg])

    # Get Landsat
    ls = getProcessedLandsatScenes(
        studyArea=studyArea,
        startYear=startYear,
        endYear=endYear,
        startJulian=startJulian,
        endJulian=endJulian,
        toaOrSR=toaOrSR,
        includeSLCOffL7=includeSLCOffL7,
        defringeL5=defringeL5,
        applyCloudScore=applyCloudScoreLandsat,
        applyFmaskCloudMask=applyFmaskCloudMask,
        applyTDOM=applyTDOMLandsat,
        applyFmaskCloudShadowMask=applyFmaskCloudShadowMask,
        applyFmaskSnowMask=applyFmaskSnowMask,
        cloudScoreThresh=cloudScoreThresh,
        performCloudScoreOffset=performCloudScoreOffset,
        cloudScorePctl=cloudScorePctl,
        zScoreThresh=zScoreThresh,
        shadowSumThresh=shadowSumThresh,
        contractPixels=contractPixels,
        dilatePixels=dilatePixels,
        shadowSumBands=shadowSumBands,
        resampleMethod=landsatResampleMethod,
        # harmonizeOLI = harmonizeOLI,
        preComputedCloudScoreOffset=preComputedLandsatCloudScoreOffset,
        preComputedTDOMIRMean=preComputedLandsatTDOMIRMean,
        preComputedTDOMIRStdDev=preComputedSentinel2TDOMIRStdDev,
        landsatCollectionVersion=landsatCollectionVersion,
        verbose=False,
    )

    # Get Sentinel 2
    s2s = getProcessedSentinel2Scenes(
        studyArea=studyArea,
        startYear=startYear,
        endYear=endYear,
        startJulian=startJulian,
        endJulian=endJulian,
        applyQABand=applyQABand,
        applyCloudScore=applyCloudScoreSentinel2,
        applyShadowShift=applyShadowShift,
        applyTDOM=applyTDOMSentinel2,
        cloudScoreThresh=cloudScoreThresh,
        performCloudScoreOffset=performCloudScoreOffset,
        cloudScorePctl=cloudScorePctl,
        cloudHeights=cloudHeights,
        zScoreThresh=zScoreThresh,
        shadowSumThresh=shadowSumThresh,
        contractPixels=contractPixels,
        dilatePixels=dilatePixels,
        shadowSumBands=shadowSumBands,
        resampleMethod=sentinel2ResampleMethod,
        toaOrSR=toaOrSR,
        convertToDailyMosaics=convertToDailyMosaics,
        applyCloudProbability=applyCloudProbability,
        preComputedCloudScoreOffset=preComputedSentinel2CloudScoreOffset,
        preComputedTDOMIRMean=preComputedSentinel2TDOMIRMean,
        preComputedTDOMIRStdDev=preComputedSentinel2TDOMIRStdDev,
        cloudProbThresh=cloudProbThresh,
        verbose=False,
        applyCloudScorePlus=applyCloudScorePlus,
        cloudScorePlusThresh=cloudScorePlusThresh,
        cloudScorePlusScore=cloudScorePlusScore,
    )

    # Select off common bands between Landsat and Sentinel 2
    commonBands = ["blue", "green", "red", "nir", "swir1", "swir2", "sensor"]
    ls = ls.select(commonBands)
    s2s = s2s.select(commonBands)
    # Fill in any empty collections
    # If they're both empty, this will not work
    dummyImage = ee.Image(ee.ImageCollection(ee.Algorithms.If(ls.toList(1).length().gt(0), ls, s2s)).first())
    ls = fillEmptyCollections(ls, dummyImage)
    s2s = fillEmptyCollections(s2s, dummyImage)

    if runChastainHarmonization and toaOrSR == "TOA":

        # Separate each sensor

        tm = ls.filter(ee.Filter.inList("SENSOR_ID", ["TM", "ETM"]))
        oli = ls.filter(ee.Filter.eq("SENSOR_ID", "OLI_TIRS"))
        # else:
        #   tm = ls.filter(ee.Filter.inList('sensor',['LANDSAT_4','LANDSAT_5','LANDSAT_7']))
        #   oli = ls.filter(ee.Filter.eq('sensor','LANDSAT_8'))
        msi = s2s

        # Fill if no images exist for particular Landsat sensor
        # Allow it to fail of no images exist for Sentinel 2 since the point
        # of this method is to include S2
        tm = fillEmptyCollections(tm, ee.Image(ls.first()))
        oli = fillEmptyCollections(oli, ee.Image(ls.first()))

        print("Running Chastain et al 2019 harmonization")

        # Apply correction
        # Currently coded to go to ETM+

        # No need to correct ETM to ETM
        # tm = tm.map(function(img){return getImagesLib.harmonizationChastain(img, 'ETM','ETM')})
        # etm = etm.map(function(img){return getImagesLib.harmonizationChastain(img, 'ETM','ETM')})

        # Harmonize the other two
        oli = oli.map(lambda img: harmonizationChastain(img, "OLI", "ETM"))
        msi = msi.map(lambda img: harmonizationChastain(img, "MSI", "ETM"))

        s2s = msi

        # Merge Landsat back together
        ls = ee.ImageCollection(tm.merge(oli))

    # Merge Landsat and S2
    merged = ee.ImageCollection(ls.merge(s2s))
    merged = merged.map(simpleAddIndices).map(getTasseledCap).map(simpleAddTCAngles)

    merged = merged.set(args)

    return merged


#################################################################################
# Function to register an imageCollection to images within it
# Always uses the first image as the reference image
def coRegisterCollection(images, referenceBands=["nir"]):
    referenceImageIndex = 0
    referenceImage = ee.Image(images.toList(referenceImageIndex + 1).get(referenceImageIndex)).select(referenceBands)

    def registerImage(image):
        # Determine the displacement by matching only the referenceBand bands.
        displacement_params = {
            "referenceImage": referenceImage,
            "maxOffset": 20.0,
            "projection": None,
            "patchWidth": 20.0,
            "stiffness": 5,
        }
        displacement = image.select(referenceBands).displacement(**displacement_params)
        return image.displace(displacement)

    out = ee.ImageCollection(ee.ImageCollection(images.toList(10000, 1)).map(registerImage))  # (ee.Image(images.toList(10000,0).get(1)),referenceImage)
    out = ee.ImageCollection(images.limit(1).merge(out))

    return out


#################################################################################
# Function to find a subset of a collection
# For each group (e.g. tile or orbit or path), all images within that group will be registered
# As single collection is returned
def coRegisterGroups(imgs, fieldName="SENSING_ORBIT_NUMBER", fieldIsNumeric=True):
    groups = ee.Dictionary(imgs.aggregate_histogram(fieldName)).keys()
    if fieldIsNumeric:
        groups = groups.map(lambda n: ee.Number.parse(n))

    out = ee.ImageCollection(ee.FeatureCollection(groups.map(lambda group: coRegisterCollection(imgs.filter(ee.Filter.eq(fieldName, group))))).flatten())

    return out


#################################################################################
def getLandsatAndSentinel2HybridWrapper(
    studyArea,
    startYear,
    endYear,
    startJulian,
    endJulian,
    timebuffer=0,
    weights=[1],
    compositingMethod="medoid",
    toaOrSR="TOA",
    includeSLCOffL7=False,
    defringeL5=False,
    applyQABand=False,
    applyCloudProbability=False,
    applyShadowShift=False,
    applyCloudScoreLandsat=False,
    applyCloudScoreSentinel2=False,
    applyTDOMLandsat=True,
    applyTDOMSentinel2=False,
    applyFmaskCloudMask=True,
    applyFmaskCloudShadowMask=True,
    applyFmaskSnowMask=False,
    cloudHeights=ee.List.sequence(500, 10000, 500),
    cloudScoreThresh=20,
    performCloudScoreOffset=True,
    cloudScorePctl=10,
    zScoreThresh=-1,
    shadowSumThresh=0.35,
    contractPixels=1.5,
    dilatePixels=3.5,
    shadowSumBands=["nir", "swir1"],
    landsatResampleMethod="near",
    sentinel2ResampleMethod="aggregate",
    convertToDailyMosaics=True,
    runChastainHarmonization=True,
    correctIllumination=False,
    correctScale=250,
    exportComposites=False,
    outputName="Landsat-Sentinel2-Hybrid",
    exportPathRoot=None,
    crs="EPSG:5070",
    transform=[30, 0, -2361915.0, 0, -30, 3177735.0],
    scale=None,
    preComputedLandsatCloudScoreOffset=None,
    preComputedLandsatTDOMIRMean=None,
    preComputedLandsatTDOMIRStdDev=None,
    preComputedSentinel2CloudScoreOffset=None,
    preComputedSentinel2TDOMIRMean=None,
    preComputedSentinel2TDOMIRStdDev=None,
    cloudProbThresh=40,
    landsatCollectionVersion="C2",
    overwrite=False,
    verbose=False,
    applyCloudScorePlusSentinel2=True,
    cloudScorePlusThresh=0.6,
    cloudScorePlusScore="cs",
):

    origin = "Landsat-Sentinel2-Hybrid"
    toaOrSR = toaOrSR.upper()

    args = formatArgs(locals())
    if "args" in args.keys():
        del args["args"]

    merged = getProcessedLandsatAndSentinel2Scenes(
        studyArea=studyArea,
        startYear=startYear,
        endYear=endYear,
        startJulian=startJulian,
        endJulian=endJulian,
        toaOrSR=toaOrSR,
        includeSLCOffL7=includeSLCOffL7,
        defringeL5=defringeL5,
        applyQABand=applyQABand,
        applyCloudProbability=applyCloudProbability,
        applyShadowShift=applyShadowShift,
        applyCloudScoreLandsat=applyCloudScoreLandsat,
        applyCloudScoreSentinel2=applyCloudScoreSentinel2,
        applyTDOMLandsat=applyTDOMLandsat,
        applyTDOMSentinel2=applyTDOMSentinel2,
        applyFmaskCloudMask=applyFmaskCloudMask,
        applyFmaskCloudShadowMask=applyFmaskCloudShadowMask,
        applyFmaskSnowMask=applyFmaskSnowMask,
        cloudHeights=cloudHeights,
        cloudScoreThresh=cloudScoreThresh,
        performCloudScoreOffset=performCloudScoreOffset,
        cloudScorePctl=cloudScorePctl,
        zScoreThresh=zScoreThresh,
        shadowSumThresh=shadowSumThresh,
        contractPixels=contractPixels,
        dilatePixels=dilatePixels,
        shadowSumBands=shadowSumBands,
        landsatResampleMethod=landsatResampleMethod,
        sentinel2ResampleMethod=sentinel2ResampleMethod,
        convertToDailyMosaics=convertToDailyMosaics,
        runChastainHarmonization=runChastainHarmonization,
        correctIllumination=correctIllumination,
        correctScale=correctScale,
        preComputedLandsatCloudScoreOffset=preComputedLandsatCloudScoreOffset,
        preComputedLandsatTDOMIRMean=preComputedLandsatTDOMIRMean,
        preComputedLandsatTDOMIRStdDev=preComputedLandsatTDOMIRStdDev,
        preComputedSentinel2CloudScoreOffset=preComputedSentinel2CloudScoreOffset,
        preComputedSentinel2TDOMIRMean=preComputedSentinel2TDOMIRMean,
        preComputedSentinel2TDOMIRStdDev=preComputedSentinel2TDOMIRStdDev,
        cloudProbThresh=cloudProbThresh,
        landsatCollectionVersion=landsatCollectionVersion,
        verbose=verbose,
        applyCloudScorePlus=applyCloudScorePlusSentinel2,
        cloudScorePlusThresh=cloudScorePlusThresh,
        cloudScorePlusScore=cloudScorePlusScore,
    )

    # Create hybrid composites
    composites = compositeTimeSeries(
        ls=merged,
        startYear=startYear,
        endYear=endYear,
        startJulian=startJulian,
        endJulian=endJulian,
        timebuffer=timebuffer,
        weights=weights,
        compositingMethod=compositingMethod,
    )

    # Export composite collection
    if exportComposites:

        exportBandDict = {
            "medoid": [
                "blue",
                "green",
                "red",
                "nir",
                "swir1",
                "swir2",
                "compositeObsCount",
                "sensor",
                "year",
                "julianDay",
            ],
            "median": [
                "blue",
                "green",
                "red",
                "nir",
                "swir1",
                "swir2",
                "compositeObsCount",
            ],
        }
        nonDivideBandDict = {
            "medoid": ["compositeObsCount", "sensor", "year", "julianDay"],
            "median": ["compositeObsCount"],
        }
        exportBands = exportBandDict[compositingMethod]
        nonDivideBands = nonDivideBandDict[compositingMethod]

        exportCompositeCollection(
            collection=composites,
            exportPathRoot=exportPathRoot,
            outputName=outputName,
            origin=origin,
            studyArea=studyArea,
            crs=crs,
            transform=transform,
            scale=scale,
            startYear=startYear,
            endYear=endYear,
            startJulian=startJulian,
            endJulian=endJulian,
            compositingMethod=compositingMethod,
            timebuffer=timebuffer,
            toaOrSR=toaOrSR,
            nonDivideBands=nonDivideBands,
            exportBands=exportBands,
            additionalPropertyDict=args,
            overwrite=overwrite,
        )

    args["processedScenes"] = merged
    args["processedComposites"] = composites

    return args


#########################################################################
#########################################################################
# Harmonic regression
#########################################################################
#########################################################################
# Function to give year.dd image and harmonics list (e.g. [1,2,3,...])
def getHarmonicList(yearDateImg, transformBandName, harmonicList):
    t = yearDateImg.select([transformBandName])
    selectBands = ee.List.sequence(0, len(harmonicList) - 1)

    def sinCat(h):
        ht = h * 100
        return ee.String("sin_").cat(str(ht)).cat("_").cat(transformBandName)

    sinNames = list(map(lambda i: sinCat(i), harmonicList))

    def cosCat(h):
        ht = h * 100
        return ee.String("cos_").cat(str(ht)).cat("_").cat(transformBandName)

    cosNames = list(map(lambda i: cosCat(i), harmonicList))

    multipliers = ee.Image(harmonicList).multiply(ee.Number(math.pi).float())
    sinInd = (t.multiply(ee.Image(multipliers))).sin().select(selectBands, sinNames).float()
    cosInd = (t.multiply(ee.Image(multipliers))).cos().select(selectBands, cosNames).float()

    return yearDateImg.addBands(sinInd.addBands(cosInd))


#########################################################################
#########################################################################
# Takes a dependent and independent variable and returns the dependent,
# sin of ind, and cos of ind
# Intended for harmonic regression
def getHarmonics2(collection, transformBandName, harmonicList, detrend=False):

    depBandNames = ee.Image(collection.first()).bandNames().remove(transformBandName)
    depBandNumbers = depBandNames.map(lambda dbn: depBandNames.indexOf(dbn))

    def harmWrap(img):
        outT = getHarmonicList(img, transformBandName, harmonicList).copyProperties(img, ["system:time_start", "system:time_end"])
        return outT

    out = collection.map(harmWrap)

    if not detrend:
        outBandNames = ee.Image(out.first()).bandNames().removeAll(["year"])
        out = out.select(outBandNames)

    indBandNames = ee.Image(out.first()).bandNames().removeAll(depBandNames)
    indBandNumbers = indBandNames.map(lambda ind: ee.Image(out.first()).bandNames().indexOf(ind))

    out = out.set(
        {
            "indBandNames": indBandNames,
            "depBandNames": depBandNames,
            "indBandNumbers": indBandNumbers,
            "depBandNumbers": depBandNumbers,
        }
    )

    return out


#########################################################################
#########################################################################
# Simplifies the use of the robust linear regression reducer
# Assumes the dependent is the first band and all subsequent bands are independents
def newRobustMultipleLinear2(dependentsIndependents):
    # Set up the band names

    dependentBands = ee.List(dependentsIndependents.get("depBandNumbers"))
    independentBands = ee.List(dependentsIndependents.get("indBandNumbers"))
    bns = ee.Image(dependentsIndependents.first()).bandNames()
    dependents = ee.List(dependentsIndependents.get("depBandNames"))
    independents = ee.List(dependentsIndependents.get("indBandNames"))

    # dependent = bns.slice(0,1)
    # independents = bns.slice(1,null)
    noIndependents = independents.length().add(1)
    noDependents = dependents.length()

    outNames = ee.List(["intercept"]).cat(independents)

    # Add constant band for intercept and reorder for
    # syntax: constant, ind1,ind2,ind3,indn,dependent
    def forFitFun(img):
        out = img.addBands(ee.Image(1).select([0], ["constant"]))
        out = out.select(ee.List(["constant", independents]).flatten())
        return out.addBands(img.select(dependents))

    forFit = dependentsIndependents.map(forFitFun)

    # Apply reducer, and convert back to image with respective bandNames
    reducerOut = forFit.reduce(ee.Reducer.linearRegression(noIndependents, noDependents))
    # // test = forFit.reduce(ee.Reducer.robustLinearRegression(noIndependents,noDependents,0.2))
    # // resids = test
    # // .select([1],['residuals']).arrayFlatten([dependents]);
    # // Map.addLayer(resids,{},'residsImage');
    # // Map.addLayer(reducerOut.select([0]),{},'coefficients');
    # // Map.addLayer(test.select([1]),{},'tresiduals');
    # // Map.addLayer(reducerOut.select([1]),{},'roresiduals');
    reducerOut = reducerOut.select([0], ["coefficients"]).arrayTranspose().arrayFlatten([dependents, outNames])
    reducerOut = reducerOut.set(
        {
            "noDependents": ee.Number(noDependents),
            "modelLength": ee.Number(noIndependents),
        }
    )

    return reducerOut


#########################################################################
#########################################################################
# Code for finding the date of peak of green
# Also converts it to Julian day, month, and day of month
monthRemap = [
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    2,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    3,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    4,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    5,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    6,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    7,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    8,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    9,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    10,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    11,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
    12,
]
monthDayRemap = [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
]
julianDay = [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    32,
    33,
    34,
    35,
    36,
    37,
    38,
    39,
    40,
    41,
    42,
    43,
    44,
    45,
    46,
    47,
    48,
    49,
    50,
    51,
    52,
    53,
    54,
    55,
    56,
    57,
    58,
    59,
    60,
    61,
    62,
    63,
    64,
    65,
    66,
    67,
    68,
    69,
    70,
    71,
    72,
    73,
    74,
    75,
    76,
    77,
    78,
    79,
    80,
    81,
    82,
    83,
    84,
    85,
    86,
    87,
    88,
    89,
    90,
    91,
    92,
    93,
    94,
    95,
    96,
    97,
    98,
    99,
    100,
    101,
    102,
    103,
    104,
    105,
    106,
    107,
    108,
    109,
    110,
    111,
    112,
    113,
    114,
    115,
    116,
    117,
    118,
    119,
    120,
    121,
    122,
    123,
    124,
    125,
    126,
    127,
    128,
    129,
    130,
    131,
    132,
    133,
    134,
    135,
    136,
    137,
    138,
    139,
    140,
    141,
    142,
    143,
    144,
    145,
    146,
    147,
    148,
    149,
    150,
    151,
    152,
    153,
    154,
    155,
    156,
    157,
    158,
    159,
    160,
    161,
    162,
    163,
    164,
    165,
    166,
    167,
    168,
    169,
    170,
    171,
    172,
    173,
    174,
    175,
    176,
    177,
    178,
    179,
    180,
    181,
    182,
    183,
    184,
    185,
    186,
    187,
    188,
    189,
    190,
    191,
    192,
    193,
    194,
    195,
    196,
    197,
    198,
    199,
    200,
    201,
    202,
    203,
    204,
    205,
    206,
    207,
    208,
    209,
    210,
    211,
    212,
    213,
    214,
    215,
    216,
    217,
    218,
    219,
    220,
    221,
    222,
    223,
    224,
    225,
    226,
    227,
    228,
    229,
    230,
    231,
    232,
    233,
    234,
    235,
    236,
    237,
    238,
    239,
    240,
    241,
    242,
    243,
    244,
    245,
    246,
    247,
    248,
    249,
    250,
    251,
    252,
    253,
    254,
    255,
    256,
    257,
    258,
    259,
    260,
    261,
    262,
    263,
    264,
    265,
    266,
    267,
    268,
    269,
    270,
    271,
    272,
    273,
    274,
    275,
    276,
    277,
    278,
    279,
    280,
    281,
    282,
    283,
    284,
    285,
    286,
    287,
    288,
    289,
    290,
    291,
    292,
    293,
    294,
    295,
    296,
    297,
    298,
    299,
    300,
    301,
    302,
    303,
    304,
    305,
    306,
    307,
    308,
    309,
    310,
    311,
    312,
    313,
    314,
    315,
    316,
    317,
    318,
    319,
    320,
    321,
    322,
    323,
    324,
    325,
    326,
    327,
    328,
    329,
    330,
    331,
    332,
    333,
    334,
    335,
    336,
    337,
    338,
    339,
    340,
    341,
    342,
    343,
    344,
    345,
    346,
    347,
    348,
    349,
    350,
    351,
    352,
    353,
    354,
    355,
    356,
    357,
    358,
    359,
    360,
    361,
    362,
    363,
    364,
    365,
]


#########################################################################
#########################################################################
# Function for getting the date of the peak of veg vigor- can handle bands negatively correlated to veg in
# changeDirDict dictionary above
def getPeakDate(coeffs, peakDirection=1):

    sin = coeffs.select([0])
    cos = coeffs.select([1])

    # Find where in cycle slope is zero
    greenDate = ((sin.divide(cos)).atan()).divide(2 * math.pi).rename(["peakDate"])
    greenDateLater = greenDate.add(0.5)
    # Check which d1 slope = 0 is the max by predicting out the value
    predicted1 = coeffs.select([0]).add(sin.multiply(greenDate.multiply(2 * math.pi).sin())).add(cos.multiply(greenDate.multiply(2 * math.pi).cos())).rename(["predicted"]).multiply(ee.Image.constant(peakDirection)).addBands(greenDate)
    predicted2 = coeffs.select([0]).add(sin.multiply(greenDateLater.multiply(2 * math.pi).sin())).add(cos.multiply(greenDateLater.multiply(2 * math.pi).cos())).rename(["predicted"]).multiply(ee.Image.constant(peakDirection)).addBands(greenDateLater)
    finalGreenDate = ee.ImageCollection([predicted1, predicted2]).qualityMosaic("predicted").select(["peakDate"]).rename(["peakJulianDay"])

    finalGreenDate = finalGreenDate.where(finalGreenDate.lt(0), greenDate.add(1)).multiply(365).int16()

    # Convert to month and day of month
    greenMonth = finalGreenDate.remap(julianDay, monthRemap).rename(["peakMonth"])
    greenMonthDay = finalGreenDate.remap(julianDay, monthDayRemap).rename(["peakDayOfMonth"])
    greenStack = finalGreenDate.addBands(greenMonth).addBands(greenMonthDay)
    return greenStack
    # Map.addLayer(greenStack,{'min':1,'max':12},'greenMonth',False)


#########################################################################
#########################################################################
# Function for getting left sum under the curve for a single growing season
# Takes care of normalization by forcing the min value along the curve 0
# by taking the amplitude as the intercept
# Assumes the sin and cos coeffs are the harmCoeffs
# t0 is the start time (defaults to 0)(min value should be but doesn't have to be 0)
# t1 is the end time (defaults to 1)(max value should be but doesn't have to be 1)


# Example of what this code is doing can be found here:
#  http://www.wolframalpha.com/input/?i=integrate+0.15949074923992157+%2B+-0.08287599*sin(2+PI+T)+%2B+-0.11252010613*cos(2+PI+T)++from+0+to+1
def getAreaUnderCurve(harmCoeffs, t0=0, t1=1):

    # Pull apart the model
    amplitude = harmCoeffs.select([1]).hypot(harmCoeffs.select([0]))
    intereceptNormalized = amplitude  # When making the min 0, the intercept becomes the amplitude (the hypotenuse)
    sin = harmCoeffs.select([0])
    cos = harmCoeffs.select([1])

    # Find the sum from - infinity to 0
    sum0 = intereceptNormalized.multiply(t0).subtract(sin.divide(2 * math.pi).multiply(math.sin(2 * math.pi * t0))).add(cos.divide(2 * math.pi).multiply(math.cos(2 * math.pi * t0)))
    # Find the sum from - infinity to 1
    sum1 = intereceptNormalized.multiply(t1).subtract(sin.divide(2 * math.pi).multiply(math.sin(2 * math.pi * t1))).add(cos.divide(2 * math.pi).multiply(math.cos(2 * math.pi * t1)))
    # Find the difference
    leftSum = sum1.subtract(sum0).rename(["AUC"])
    return leftSum


#########################################################################
#########################################################################
def getPhaseAmplitudePeak(coeffs, t0=0, t1=1):
    # Parse the model
    bandNames = coeffs.bandNames()
    bandNumber = bandNames.length()
    noDependents = ee.Number(coeffs.get("noDependents"))
    modelLength = ee.Number(coeffs.get("modelLength"))
    interceptBands = ee.List.sequence(0, bandNumber.subtract(1), modelLength)

    models = ee.List.sequence(0, noDependents.subtract(1))

    def modelGetter(mn):
        mn = ee.Number(mn)
        return bandNames.slice(mn.multiply(modelLength), mn.multiply(modelLength).add(modelLength))

    parsedModel = models.map(modelGetter)

    # print('Parsed harmonic regression model',parsedModel)

    # Iterate across models to convert to phase, amplitude, and peak
    def papGetter(pm):
        pm = ee.List(pm)
        modelCoeffs = coeffs.select(pm)

        intercept = modelCoeffs.select(".*_intercept")
        harmCoeffs = modelCoeffs.select(".*_200_year")
        outName = ee.String(ee.String(pm.get(1)).split("_").get(0))
        sign = ee.Number(ee.Dictionary(changeDirDict).get(outName)).multiply(-1)

        amplitude = harmCoeffs.select([1]).hypot(harmCoeffs.select([0])).multiply(2).rename([outName.cat("_amplitude")])
        phase = harmCoeffs.select([0]).atan2(harmCoeffs.select([1])).unitScale(-math.pi, math.pi).rename([outName.cat("_phase")])

        # Get peak date info
        peakDate = getPeakDate(harmCoeffs, sign)
        peakDateBandNames = peakDate.bandNames()
        peakDateBandNames = peakDateBandNames.map(lambda bn: outName.cat(ee.String("_").cat(ee.String(bn))))

        # Get the left sum
        leftSum = getAreaUnderCurve(harmCoeffs, t0, t1)
        leftSumBandNames = leftSum.bandNames()
        leftSumBandNames = leftSumBandNames.map(lambda bn: outName.cat(ee.String("_").cat(ee.String(bn))))

        return amplitude.addBands(phase).addBands(peakDate.rename(peakDateBandNames)).addBands(leftSum.rename(leftSumBandNames))

    # Convert to an image
    phaseAmplitude = parsedModel.map(papGetter)

    phaseAmplitude = ee.ImageCollection.fromImages(phaseAmplitude)

    phaseAmplitude = ee.Image(collectionToImage(phaseAmplitude)).float().copyProperties(coeffs, ["system:time_start"])
    # print('pa',phaseAmplitude);
    return phaseAmplitude


#########################################################################
#########################################################################
# Function for applying harmonic regression model to set of predictor sets
def newPredict(coeffs, harmonics):
    # Parse the model
    bandNames = coeffs.bandNames()
    bandNumber = bandNames.length()
    noDependents = ee.Number(coeffs.get("noDependents"))
    modelLength = ee.Number(coeffs.get("modelLength"))
    interceptBands = ee.List.sequence(0, bandNumber.subtract(1), modelLength)
    timeBand = ee.List(harmonics.get("indBandNames")).get(0)
    actualBands = harmonics.get("depBandNumbers")
    indBands = harmonics.get("indBandNumbers")
    indBandNames = ee.List(harmonics.get("indBandNames"))
    depBandNames = ee.List(harmonics.get("depBandNames"))
    predictedBandNames = depBandNames.map(lambda depbnms: ee.String(depbnms).cat("_predicted"))
    predictedBandNumbers = ee.List.sequence(0, predictedBandNames.length().subtract(1))

    models = ee.List.sequence(0, noDependents.subtract(1))

    def mnGetter(mn):
        mn = ee.Number(mn)
        return bandNames.slice(mn.multiply(modelLength), mn.multiply(modelLength).add(modelLength))

    parsedModel = models.map(mnGetter)

    # print('Parsed harmonic regression model',parsedModel,predictedBandNames)

    # Apply parsed model
    def predGetter(img):
        time = img.select(timeBand)
        actual = img.select(actualBands).float()
        predictorBands = img.select(indBandNames)

        # Iterate across each model for each dependent variable
        def pmGetter(pm):
            pm = ee.List(pm)
            modelCoeffs = coeffs.select(pm)
            outName = ee.String(pm.get(1)).cat("_predicted")
            intercept = modelCoeffs.select(modelCoeffs.bandNames().slice(0, 1))
            others = modelCoeffs.select(modelCoeffs.bandNames().slice(1, None))

            predicted = predictorBands.multiply(others).reduce(ee.Reducer.sum()).add(intercept).float()
            return predicted.float()

        predictedList = parsedModel.map(pmGetter)

        # Convert to an image
        predictedList = ee.ImageCollection.fromImages(predictedList)
        predictedImage = collectionToImage(predictedList).select(predictedBandNumbers, predictedBandNames)

        # Set some metadata
        out = actual.addBands(predictedImage.float()).copyProperties(img, ["system:time_start", "system:time_end"])
        return out

    predicted = harmonics.map(predGetter)

    predicted = ee.ImageCollection(predicted)

    # Map.addLayer(predicted,{},'predicted',False)

    return predicted


#########################################################################
#########################################################################
# Function to get a dummy image stack for synthetic time series
def getDateStack(startYear, endYear, startJulian, endJulian, frequency):
    years = ee.List.sequence(startYear, endYear)
    dates = ee.List.sequence(startJulian, endJulian, frequency)

    def yrGetter(yr):
        def dGetter(d):
            return ee.Date.fromYMD(yr, 1, 1).advance(d, "day")

        ds = dates.map(dGetter)
        return ds

    dateSets = years.map(yrGetter)

    l = range(1, len(indexNames) + 1)
    l = [i % i for i in l]
    c = ee.Image(l).rename(indexNames)
    c = c.divide(c)

    dateSets = dateSets.flatten()

    def dtGetter(dt):
        dt = ee.Date(dt)
        y = dt.get("year")
        d = dt.getFraction("year")
        i = ee.Image(y.add(d)).float().select([0], ["year"])

        i = c.addBands(i).float().set("system:time_start", dt.millis()).set("system:time_end", dt.advance(frequency, "day").millis())
        return i

    stack = dateSets.map(dtGetter)
    stack = ee.ImageCollection.fromImages(stack)
    return stack


#########################################################################
#########################################################################
def getHarmonicCoefficientsAndFit(allImages, indexNames, whichHarmonics=[2], detrend=False):

    # Select desired bands
    allIndices = allImages.select(indexNames)

    # Add date band
    if detrend:
        allIndices = allIndices.map(addDateBand)
    else:
        allIndices = allIndices.map(addYearFractionBand)

    # Add independent predictors (harmonics)
    withHarmonics = getHarmonics2(allIndices, "year", whichHarmonics, detrend)
    withHarmonicsBns = ee.Image(withHarmonics.first()).bandNames().slice(len(indexNames) + 1, None)

    # Optionally chart the collection with harmonics

    # Fit a linear regression model
    coeffs = newRobustMultipleLinear2(withHarmonics)

    # Can visualize the phase and amplitude if only the first ([2]) harmonic is chosen
    # if whichHarmonics == 2{
    #    pa = getPhaseAmplitude(coeffs);
    #  // Turn the HSV data into an RGB image and add it to the map.
    #  seasonality = pa.select([1,0]).addBands(allIndices.select([indexNames[0]]).mean()).hsvToRgb();
    #  // Map.addLayer(seasonality, {}, 'Seasonality');
    #  }

    # Map.addLayer(coeffs,{},'Harmonic Regression Coefficients',False)
    predicted = newPredict(coeffs, withHarmonics)
    return [coeffs, predicted]


#########################################################################
#########################################################################
# Simple predict function for harmonic coefficients
# Expects coeffs from getHarmonicCoefficientsAndFit function
# Date image is expected to be yyyy.dd where dd is the day of year / 365 (proportion of year)
# ex. synthImage(coeffs,ee.Image([2019.6]),['blue','green','red','nir','swir1','swir2','NBR','NDVI'],[2,4],true)
def synthImage(coeffs, dateImage, indexNames, harmonics, detrend):
    # Set up constant image to multiply coeffs by
    constImage = ee.Image(1)
    if detrend:
        constImage = constImage.addBands(dateImage)
    for harm in harmonics:
        constImage = constImage.addBands(ee.Image([dateImage.multiply(harm * math.pi).sin()]).rename(["{}_sin".format(harm * 100)]))
    for harm in harmonics:
        constImage = constImage.addBands(ee.Image([dateImage.multiply(harm * math.pi).cos()]).rename(["{}_cos".format(harm * 100)]))

    # coeffssBn = coeffs.select(ee.String(indexNames[0]).cat('_.*'))
    # print(constImage.bandNames().getInfo(),coeffssBn.bandNames().getInfo())
    # Predict values for each band
    out = ee.Image(1)

    def predictWrapper(bn, out):
        bn = ee.String(bn)
        # Select coeffs for that band
        coeffssBn = coeffs.select(ee.String(bn).cat("_.*"))
        predicted = constImage.multiply(coeffssBn).reduce("sum").rename(bn)
        return ee.Image(out).addBands(predicted)

    out = ee.Image(ee.List(indexNames).iterate(predictWrapper, out))

    out = out.select(ee.List.sequence(1, out.bandNames().size().subtract(1)))

    return out


#####################################################################
# Wrapper function to get climate data
# Supports:
# NASA/ORNL/DAYMET_V3
# NASA/ORNL/DAYMET_V4
# UCSB-CHG/CHIRPS/DAILY (precipitation only)
# and possibly others
def getClimateWrapper(
    collectionName: str,
    studyArea: ee.Geometry | ee.Feature | ee.FeatureCollection,
    startYear: int,
    endYear: int,
    startJulian: int,
    endJulian: int,
    timebuffer: int = 0,
    weights: ee.List | list | None = None,
    compositingReducer: ee.Reducer | None = None,
    exportComposites: bool = False,
    exportPathRoot: str | None = None,
    crs: str | None = None,
    transform: list[int] | None = None,
    scale: int | None = None,
    exportBands: ee.List | list | None = None,
    exportNamePrefix: str = "",
    exportToAssets: bool = False,
    exportToCloud: bool = False,
    bucket: str = "",
) -> ee.ImageCollection:
    """
    Wrapper function to retrieve and process climate data from various Earth Engine collections.

    This function supports retrieving climate data from collections like NASA/ORNL/DAYMET_V3,
    NASA/ORNL/DAYMET_V4, UCSB-CHG/CHIRPS/DAILY (precipitation only), and potentially others. It allows
    filtering by date, study area, and Julian day, specifying a compositing reducer, and optionally
    exporting the resulting time series.

    Args:
        collectionName (str): Name of the Earth Engine collection containing climate data.
        studyArea (ee.Geometry | ee.Feature | ee.FeatureCollection): The geographic area of interest (study area) as an Earth Engine geometry object.
        startYear (int): The starting year for the data collection.
        endYear (int): The ending year for the data collection.
        startJulian (int): The starting Julian day of year for the data collection (1-365).
        endJulian (int): The ending Julian day of year for the data collection (1-365).
        timebuffer (int, optional): Number of years to buffer around each year. Defaults to 0.
        weights (ee.List | list| None, optional): List of weights for weighted compositing (if applicable
            to the chosen collection). Defaults to None (equal weights).
        compositingReducer (ee.Reducer | None, optional): Earth Engine reducer used for compositing
            daily data into the desired temporal resolution. Defaults to None (may require a reducer
            depending on the collection).
        exportComposites (bool, optional): Flag indicating whether to export the resulting time series.
            Defaults to False.
        exportPathRoot (str | None, optional): Root path for exporting the composites (if exportComposites
            is True). Defaults to None (no export).
        crs (str | None, optional): Earth Engine projection object for the exported composites
            (if exportComposites is True). Defaults to None (uses the source collection's projection).
        transform (list[int] | None, optional): Earth Engine transform object for the exported
            composites (if exportComposites is True). Defaults to None (uses the source collection's transform).
        scale (int | None, optional): Scale in meters for the exported composites (if exportComposites
            is True). Defaults to None (uses the source collection's scale).
        exportBands (ee.List | list | None, optional): List of band names to export from the composites (if
            exportComposites is True). Defaults to None (all bands from the first image in the collection).
        exportNamePrefix (str, optional): Name to place before default name of exported image. Defaults to ''.
        exportToAssets (bool, optional): Set to True to export images to earth engine assets. Defaults to False.
        exportToCloud (bool, optional): Set to True to export images to Google Cloud Storage. Defaults to False.
        bucket (str, optional): If exportToCloud is True, images are exported to this Google Cloud storage bucket. Defaults to '', but will need to be provided if `exportToCloud` is `True`.

    Returns:
        ee.ImageCollection: The time series collection of processed climate data.

    >>> import geeViz.getImagesLib as gil
    >>> Map = gil.Map
    >>> ee = gil.ee
    >>> studyArea = gil.testAreas["CO"]
    >>> startJulian = 274
    >>> endJulian = 273
    >>> startYear = 2016
    >>> endYear = 2023
    >>> timebuffer = 0
    >>> weights = [1]
    >>> compositingReducer = ee.Reducer.mean()
    >>> collectionName = "NASA/ORNL/DAYMET_V4"
    >>> exportComposites = False
    >>> exportPathRoot = "users/username/someCollection"
    >>> exportBands = ["prcp.*", "tmax.*", "tmin.*"]
    >>> exportNamePrefix = 'Colorado_Test_Area_'
    >>> crs = "EPSG:5070"
    >>> transform = [1000, 0, -2361915.0, 0, -1000, 3177735.0]
    >>> scale = None
    >>> climateComposites = gil.getClimateWrapper(collectionName, studyArea, startYear, endYear, startJulian, endJulian, timebuffer, weights, compositingReducer, exportComposites, exportPathRoot, crs, transform, scale, exportBands, exportNamePrefix,exportToAssets,exportToCloud,bucket)
    >>> Map.addTimeLapse(climateComposites.select(exportBands), {}, "Climate Composite Time Lapse")
    >>> Map.addLayer(studyArea, {"strokeColor": "0000FF", "canQuery": False}, "Study Area", True)
    >>> Map.centerObject(studyArea)
    >>> Map.turnOnInspector()
    >>> Map.view()
    """
    args = formatArgs(locals())
    if "args" in args.keys():
        del args["args"]
    print(args)

    # Prepare dates
    # Wrap the dates if needed
    wrapOffset = 0
    if startJulian > endJulian:
        wrapOffset = 365

    startDate = ee.Date.fromYMD(startYear, 1, 1).advance(startJulian - 1, "day")
    endDate = ee.Date.fromYMD(endYear, 1, 1).advance(endJulian - 1 + wrapOffset, "day")
    print(
        "Start and end dates:",
        startDate.format("YYYY-MM-dd").getInfo(),
        endDate.format("YYYY-MM-dd").getInfo(),
    )
    print("Julian days are:", startJulian, endJulian)

    # Get climate data
    c = ee.ImageCollection(collectionName).filterBounds(studyArea).filterDate(startDate, endDate.advance(1, "day")).filter(ee.Filter.calendarRange(startJulian, endJulian))

    # Set to appropriate resampling method
    c = c.map(lambda img: img.resample("bicubic"))
    Map.addLayer(c, {}, "Raw Climate", False)

    # Create composite time series
    ts = compositeTimeSeries(
        c,
        startYear,
        endYear,
        startJulian,
        endJulian,
        timebuffer,
        weights,
        None,
        compositingReducer,
    )
    ts = ee.ImageCollection(ts.map(lambda i: i.float()))

    # Export composite collection
    if exportComposites:
        # Set up export bands if not specified
        if exportBands == None:
            exportBands = ee.List(ee.Image(ts.first()).bandNames())

        exportCollection(
            exportPathRoot, f'{exportNamePrefix}{collectionName.split("/")[-1]}', studyArea, crs, transform, scale, ts, startYear, endYear, startJulian, endJulian, compositingReducer, timebuffer, exportBands, exportToAssets, exportToCloud, bucket
        )

    return ts


#####################################################################
# Adds absolute difference from a specified band summarized by a provided percentile
# Intended for custom sorting across collections
def addAbsDiff(inCollection, qualityBand, percentile, sign):
    bestQuality = inCollection.select([qualityBand]).reduce(ee.Reducer.percentile([percentile]))

    def w(image):
        delta = image.select([qualityBand]).subtract(bestQuality).abs().multiply(sign)
        return image.addBands(delta.select([0], ["delta"]))

    out = inCollection.map(w)
    return out


#####################################################################
# Method for applying the qualityMosaic function using a specified percentile
# Useful when the max of the quality band is not what is wanted
def customQualityMosaic(inCollection, qualityBand, percentile):
    # Add an absolute difference from the specified percentile
    # This is inverted for the qualityMosaic function to properly prioritize
    inCollectionDelta = addAbsDiff(inCollection, qualityBand, percentile, -1)

    # Apply the qualityMosaic function
    return inCollectionDelta.qualityMosaic("delta")


#####################################################################
def simpleWaterMask(
    img: ee.Image,
    contractPixels: int = 0,
    slope_thresh: float = 10,
    elevationImagePath: str | ee.Image | ee.ImageCollection = "USGS/3DEP/10m",
    elevationFocalMeanRadius: float = 5.5,
) -> ee.Image:
    """
    Performs a basic on-the-fly water masking for TOA reflectance imagery.

    This function creates a water mask based on thresholds applied to Tasseled Cap angles, brightness, and slope.
    It's designed for time-sensitive analysis and works well when wet snow is absent. However, wet snow in flat areas
    can lead to false positives. SR data might cause false negatives (omissions).

    Args:
        img (ee.Image): The input Earth Engine image (TOA reflectance data recommended) with Tasseled Cap transformation bands added. You may need to run `getTasseledCap` to add these bands.
        contractPixels (int, optional): Number of pixels to contract the water mask by for morphological closing. Defaults to 0 (no contraction).
        slope_thresh (float, optional): Threshold for slope (degrees) to identify flat areas suitable for water masking. Defaults to 10.
        elevationImagePath (str or ee.Image or ee.ImageCollection, optional): Path to the Earth Engine image or Earth Engine image or imageCollection object containing elevation data. Defaults to "USGS/3DEP/10m" (10m DEM from USGS 3D Elevation Program).
        elevationFocalMeanRadius (float, optional): Radius (in pixels) for the focal mean filter applied to the elevation data before calculating slope. Defaults to 5.5.

    Returns:
        ee.Image: The water mask image with a single band named "waterMask".

    >>> import geeViz.getImagesLib as gil
    >>> Map = gil.Map
    >>> ee = gil.ee
    >>> studyArea = gil.testAreas["CO"]
    >>> s2s = gil.superSimpleGetS2(studyArea, "2024-01-01", "2024-12-31", 190, 250).map(lambda img: gil.getTasseledCap(img.resample("bicubic").divide(10000)))
    >>> median_composite = s2s.median()
    >>> water = gil.simpleWaterMask(median_composite).rename("Water")
    >>> water = water.selfMask().set({"Water_class_values": [1], "Water_class_names": ["Water"], "Water_class_palette": ["0000DD"]})
    >>> Map.addLayer(median_composite.reproject("EPSG:32613", None, 10), gil.vizParamsFalse, "Sentinel-2 Median Composite")
    >>> Map.addLayer(water.reproject("EPSG:32613", None, 10), {"autoViz": True}, "Water Mask")
    >>> Map.addLayer(studyArea, {"canQuery": False}, "Study Area")
    >>> Map.centerObject(studyArea, 12)
    >>> Map.turnOnInspector()
    >>> Map.view()
    """

    # Add Tasseled Cap angles to the image
    img = addTCAngles(img)

    # Load and resample elevation data
    # Handle different data types
    edType = type(elevationImagePath).__name__
    ed = ee.Image(elevationImagePath) if edType == "str" else (ee.ImageCollection(elevationImagePath).mosaic() if edType == "ImageCollection" else elevationImagePath)

    ed = ee.Image(ed).resample("bicubic")

    # Calculate slope using focal mean filtered elevation
    slope = ee.Terrain.slope(ed.focal_mean(elevationFocalMeanRadius))

    # Identify flat areas based on slope threshold
    flat = slope.lte(slope_thresh)  # Less than or equal to threshold

    # Define water mask conditions based on Tasseled Cap angles, brightness, and slope
    waterMask = img.select(["tcAngleBW"]).gte(-0.05).And(img.select(["tcAngleBG"]).lte(0.05)).And(img.select(["brightness"]).lt(0.3)).And(flat)

    # Apply morphological closing with focal minimum filter
    waterMask = waterMask.focal_min(contractPixels)

    # Rename the water mask band
    return waterMask.rename(["waterMask"])


####################
# Jeff Ho Method for algal bloom detection
# https://www.nature.com/articles/s41586-019-1648-7

# Simplified Script for Landsat Water Quality
# Produces a map of an algal bloom in Lake Erie on 2011/9/3
# Created on 12/7/2015 by Jeff Ho


# Specifies a threshold for hue to estimate "green" pixels
# this is used as an additional filter to refine the algorithm above
def HoCalcGreenness(img):
    # map r, g, and b for more readable algebra below
    r = img.select(["red"])
    g = img.select(["green"])
    b = img.select(["blue"])

    # calculate intensity, hue
    I = r.add(g).add(b).rename(["I"])
    mins = r.min(g).min(b).rename(["mins"])
    H = mins.where(mins.eq(r), (b.subtract(r)).divide(I.subtract(r.multiply(3))).add(1))
    H = H.where(mins.eq(g), (r.subtract(g)).divide(I.subtract(g.multiply(3))).add(2))
    H = H.where(mins.eq(b), (g.subtract(b)).divide(I.subtract(b.multiply(3))))

    # pixels with hue below 1.6 more likely to be bloom and not suspended sediment
    Hthresh = H.lte(1.6)

    return H.rename("H")


# Apply bloom detection algorithm
def HoCalcAlgorithm1(image):
    truecolor = 1  # show true color image as well
    testThresh = False  # add a binary image classifying into "bloom"and "non-bloom
    bloomThreshold = 0.02346  # threshold for classification fit based on other data
    greenessThreshold = 1.6

    # Algorithm 1 based on:
    # Wang, M., & Shi, W. (2007). The NIR-SWIR combined atmospheric
    #  correction approach for MODIS ocean color data processing.
    #  Optics Express, 15(24), 15722–15733.

    # Add secondary filter using greenness function below
    image = image.addBands(HoCalcGreenness(image))

    # Apply algorithm 1: B4 - 1.03*B5
    # bloom1 = image.select('nir').subtract(image.select('swir1').multiply(1.03)).rename('bloom1')

    # Get binary image by applying the threshold
    bloom1_mask = image.select("H").lte(greenessThreshold).rename(["bloom1_mask"])

    return image.addBands(bloom1).addBands(bloom1_mask)


# //////////////////////////////////////////////////////////////////////////
# // END FUNCTIONS
# ////////////////////////////////////////////////////////////////////////////////


testAreas = {}
testAreas["CO"] = ee.Geometry.Polygon(
    [
        [
            [-108.28630509064759, 38.085343638120925],
            [-108.28630509064759, 37.18051220092945],
            [-106.74821915314759, 37.18051220092945],
            [-106.74821915314759, 38.085343638120925],
        ]
    ],
    None,
    False,
)
testAreas["CO_North"] = ee.Geometry.Polygon(
    [
        [
            [-106.41977869339524, 40.97947702393234],
            [-106.41977869339524, 39.96406321814001],
            [-105.20578943558274, 39.96406321814001],
            [-105.20578943558274, 40.97947702393234],
        ]
    ],
    None,
    False,
)
testAreas["CA"] = ee.Geometry.Polygon(
    [
        [
            [-119.96383760287506, 37.138150574108714],
            [-119.96383760287506, 36.40774412106424],
            [-117.95333955600006, 36.40774412106424],
            [-117.95333955600006, 37.138150574108714],
        ]
    ],
    None,
    False,
)

testAreas["CA_Small"] = ee.Geometry.Polygon(
    [
        [
            [-123.22566968374625, 39.677209599269155],
            [-123.22566968374625, 38.993179504697586],
            [-122.60494214468375, 38.993179504697586],
            [-122.60494214468375, 39.677209599269155],
        ]
    ],
    None,
    False,
)

testAreas["HI"] = ee.Geometry.Polygon(
    [
        [
            [-160.50824874450544, 22.659814513909474],
            [-160.50824874450544, 18.54750309959827],
            [-154.35590499450544, 18.54750309959827],
            [-154.35590499450544, 22.659814513909474],
        ]
    ],
    None,
    False,
)
