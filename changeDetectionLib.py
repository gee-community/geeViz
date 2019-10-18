"""
   Copyright 2019 Ian Housman

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http:#www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
#Script to help with basic change detection
#Intended to work within the geeViz package
######################################################################
# Adapted from changeDetectionLib.js
# I have only been converting functions as I use them. Unconverted functions are included at the bottom of this file.

from geeViz.getImagesLib import *
import sys, math, ee
from datetime import datetime

#-------------------------------------------------------------------------
#             Image and array manipulation
#------------------------------------------------------------------------
#Helper to multiply image
def multBands(img,distDir,by):
  out = img.multiply(ee.Image(distDir).multiply(by))
  out  = ee.Image(out.copyProperties(img,['system:time_start']).copyProperties(img))
  return out

# Helper to multiply new baselearner format values (LandTrendr & Verdet) by the appropriate amount when importing
# Duration is the only band that does not get multiplied by 0.0001 upon import.
def LT_VT_multBands(img):
    fitted = img.select('.*_fitted').multiply(0.0001)
    slope = img.select('.*_slope').multiply(0.0001)
    diff = img.select('.*_diff').multiply(0.0001)
    mag = img.select('.*_mag').multiply(0.0001)
    dur = img.select('.*_dur')
    out = dur.addBands(fitted).addBands(slope).addBands(diff).addBands(mag)
    out  = out.copyProperties(img,['system:time_start'])\
              .copyProperties(img)
    return out


def addToImage(img,howMuch):
  out = img.add(ee.Image(howMuch))
  out  = ee.Image(out.copyProperties(img,['system:time_start']).copyProperties(img))
  return out

# Used when masking out pixels that don't have sufficient data for Landtrendr and Verdet
def nullFinder(img, countMask):
    m = img.mask()
    #Allow areas with insufficient data to be included, but then set to a dummy value for later masking
    m = m.Or(countMask.Not())
    img = img.mask(m)
    img = img.where(countMask.Not(), -32768)
    return img

#Function to convert an image array object to collection
def arrayToTimeSeries(tsArray,yearsArray,possibleYears,bandName):
  #Set up dummy image for handling null values
  noDateValue = -32768
  dummyImage = ee.Image(noDateValue).toArray()

  #Iterate across years
  def applyMasks(yr):    
    yr = ee.Number(yr)
  
    #Pull out given year
    yrMask = yearsArray.eq(yr)

    #Mask array for that given year
    masked = tsArray.arrayMask(yrMask)      
  
    #Find null pixels
    l = masked.arrayLength(0)
  
    #Fill null values and convert to regular image
    masked = masked.where(l.eq(0),dummyImage).arrayGet([-1])
  
    #Remask nulls
    masked = masked.updateMask(masked.neq(noDateValue)).rename([bandName])\
    .set('system:time_start',ee.Date.fromYMD(yr,6,1).millis())

    return masked
  tsC = possibleYears.map(lambda yr: applyMasks(yr))

  return ee.ImageCollection(tsC)

#########################################################################################################
###### GREATEST DISTURBANCE EXTRACTION FUNCTIONS #####
#########################################################################################################

# ----- function to extract greatest disturbance based on spectral delta between vertices 
def extractDisturbance(lt, distDir, params, mmu):
  # select only the vertices that represents a change
  vertexMask = lt.arraySlice(0, 3, 4) # get the vertex - yes(1)/no(0) dimension
  vertices = lt.arrayMask(vertexMask) # convert the 0's to masked
 

  # numberOfVertices = vertexMask.arrayReduce(ee.Reducer.sum(),[1]).arrayProject([1]).arrayFlatten([['vertexCount']])
  # secondMask = numberOfVertices.gte(3)
  # thirdMask = numberOfVertices.gte(4)
  # Map.addLayer(numberOfVertices,{min:2,max:4},'number of vertices',false)
  # construct segment start and end point years and index values
  left = vertices.arraySlice(1, 0, -1)    # slice out the vertices as the start of segments
  right = vertices.arraySlice(1, 1, None) # slice out the vertices as the end of segments
  startYear = left.arraySlice(0, 0, 1)    # get year dimension of LT data from the segment start vertices
  startVal = left.arraySlice(0, 2, 3)     # get spectral index dimension of LT data from the segment start vertices
  endYear = right.arraySlice(0, 0, 1)     # get year dimension of LT data from the segment end vertices 
  endVal = right.arraySlice(0, 2, 3)      # get spectral index dimension of LT data from the segment end vertices
  
  dur = endYear.subtract(startYear)       # subtract the segment start year from the segment end year to calculate the duration of segments 
  mag = endVal.subtract(startVal)         # substract the segment start index value from the segment end index value to calculate the delta of segments 

  
  # concatenate segment start year, delta, duration, and starting spectral index value to an array 
  distImg = ee.Image.cat([startYear.add(1), mag, dur, startVal.multiply(-1)]).toArray(0) # make an image of segment attributes - multiply by the distDir parameter to re-orient the spectral index if it was flipped for segmentation - do it here so that the subtraction to calculate segment delta in the above line is consistent - add 1 to the detection year, because the vertex year is not the first year that change is detected, it is the following year
 
  # sort the segments in the disturbance attribute image delta by spectral index change delta  
  distImgSorted = distImg.arraySort(mag.multiply(-1))    
  
  # slice out the first (greatest) delta
  tempDistImg1 = distImgSorted.arraySlice(1, 0, 1).unmask(ee.Image(ee.Array([[0],[0],[0],[0]])))
  tempDistImg2 = distImgSorted.arraySlice(1, 1, 2).unmask(ee.Image(ee.Array([[0],[0],[0],[0]])))
  tempDistImg3 = distImgSorted.arraySlice(1, 2, 3).unmask(ee.Image(ee.Array([[0],[0],[0],[0]])))
  
 
  # make an image from the array of attributes for the greatest disturbance
  finalDistImg1 = tempDistImg1.arrayProject([0]).arrayFlatten([['yod','mag','dur','preval']])
  finalDistImg2 = tempDistImg2.arrayProject([0]).arrayFlatten([['yod','mag','dur','preval']])
  finalDistImg3 = tempDistImg3.arrayProject([0]).arrayFlatten([['yod','mag','dur','preval']])
  
  
  # filter out disturbances based on user settings
  def filterDisturbances(finalDistImg):
    # threshold = ee.Image(finalDistImg.select(['dur']))                        # get the disturbance band out to apply duration dynamic disturbance magnitude threshold 
    #       .multiply((params.tree_loss20 - params.tree_loss1) / 19.0)  # ...
    #       .add(params.tree_loss1)                                     #    ...interpolate the magnitude threshold over years between a 1-year mag thresh and a 20-year mag thresh
    #       .lte(finalDistImg.select(['mag']))                          # ...is disturbance less then equal to the interpolated, duration dynamic disturbance magnitude threshold 
    #       .and(finalDistImg.select(['mag']).gt(0))                    # and is greater than 0  
    #       .and(finalDistImg.select(['preval']).gt(params.pre_val))
    longTermDisturbance = finalDistImg.select(['dur']).gte(15)
    longTermThreshold = finalDistImg.select(['mag']).gte(params['tree_loss20']).And(longTermDisturbance)
    threshold = finalDistImg.select(['mag']).gte(params['tree_loss1'])

    return finalDistImg.updateMask(threshold.Or(longTermThreshold)) 

  finalDistImg1 = filterDisturbances(finalDistImg1)
  finalDistImg2 = filterDisturbances(finalDistImg2)
  finalDistImg3 = filterDisturbances(finalDistImg3)

  
  def applyMMU(finalDistImg):
      # patchify based on disturbances having the same year of detection
      # count the number of pixel in a candidate patch
      mmuPatches = finalDistImg.select(['yod.*']).int16()\
          .connectedPixelCount(mmu, True)\
          .gte(mmu)                      # are the the number of pixels per candidate patch greater than user-defined minimum mapping unit?
      return finalDistImg.updateMask(mmuPatches)     # mask the pixels/patches that are less than minimum mapping unit

  # patchify the remaining disturbance pixels using a minimum mapping unit
  if (mmu > 1):
    print('Applying mmu:'+str(mmu)+' to LANDTRENDR heuristic outputs')
    
    finalDistImg1 = applyMMU(finalDistImg1)
    finalDistImg2 = applyMMU(finalDistImg2)
    finalDistImg3 = applyMMU(finalDistImg3)
  
  return finalDistImg1.addBands(finalDistImg2).addBands(finalDistImg3) # return the filtered greatest disturbance attribute image

#-------------------------------------------------------------------------
#             LandTrendr Code
#------------------------------------------------------------------------
#Landtrendr code taken from users/emaprlab/public
###### UNPACKING LT-GEE OUTPUT STRUCTURE FUNCTIONS ##### 

# ----- FUNCTION TO EXTRACT VERTICES FROM LT RESULTS AND STACK BANDS -----
def getLTvertStack(LTresult,run_params):
  emptyArray = []                              # make empty array to hold another array whose length will vary depending on maxSegments parameter    
  vertLabels = []                              # make empty array to hold band names whose length will vary depending on maxSegments parameter 
  #iString                                      # initialize variable to hold vertex number
  # loop through the maximum number of vertices in segmentation and fill empty arrays:
  for i in range(1, run_params['maxSegments']+2):   
    vertLabels.append("vert_"+str(i))               # define vertex number as string, make a band name for given vertex
    emptyArray.append(0)                             # fill in emptyArray
  
  zeros = ee.Image(ee.Array([emptyArray,        # make an image to fill holes in result 'LandTrendr' array where vertices found is not equal to maxSegments parameter plus 1
                                 emptyArray,
                                 emptyArray]))
  
  lbls = [['yrs_','src_','fit_'], vertLabels] # labels for 2 dimensions of the array that will be cast to each other in the final step of creating the vertice output 

  vmask = LTresult.arraySlice(0,3,4)           # slices out the 4th row of a 4 row x N col (N = number of years in annual stack) matrix, which identifies vertices - contains only 0s and 1s, where 1 is a vertex (referring to spectral-temporal segmentation) year and 0 is not
  
  # Line by line comments taken from call below
  # .arrayMask uses the sliced out isVert row as a mask to only include vertice in this data - after this a pixel will only contain as many "bands" are there are vertices for that pixel - min of 2 to max of 7. 
  # .arraySlice()...from the vertOnly data subset slice out the vert year row, raw spectral row, and fitted spectral row
  # .addBands() # ...adds the 3 row x 7 col 'zeros' matrix as a band to the vertOnly array - this is an intermediate step to the goal of filling in the vertOnly data so that there are 7 vertice slots represented in the data - right now there is a mix of lengths from 2 to 7
  # .toArray() # ...concatenates the 3 row x 7 col 'zeros' matrix band to the vertOnly data so that there are at least 7 vertice slots represented - in most cases there are now > 7 slots filled but those will be truncated in the next step
  # .arraySlice()...before this line runs the array has 3 rows and between 9 and 14 cols depending on how many vertices were found during segmentation for a given pixel. this step truncates the cols at 7 (the max verts allowed) so we are left with a 3 row X 7 col array
  # .arrayFlatten()...this takes the 2-d array and makes it 1-d by stacking the unique sets of rows and cols into bands. there will be 7 bands (vertices) for vertYear, followed by 7 bands (vertices) for rawVert, followed by 7 bands (vertices) for fittedVert, according to the 'lbls' list
  ltVertStack = LTresult.arrayMask(vmask)\
    .arraySlice(0, 0, 3)\
    .addBands(zeros)\
    .toArray(1)\
    .arraySlice(1, 0, run_params['maxSegments']+1)\
    .arrayFlatten(lbls, '')    
    
  return ltVertStack                               # return the stack


#Adapted version for converting sorted array to image
def getLTStack(LTresult, maxVertices, bandNames):
  
  nBands = len(bandNames)
  emptyArray = []                              # make empty array to hold another array whose length will vary depending on maxSegments parameter    
  vertLabels = []                              # make empty array to hold band names whose length will vary depending on maxSegments parameter 
  for i in range(1, maxVertices+1):              # loop through the maximum number of vertices in segmentation and fill empty arrays
    vertLabels.append(str(i))            # make a band name for given vertex
    emptyArray.append(-32768)                  # fill in emptyArray

  #Set up empty array list
  emptyArrayList = []
  for i in range(1, nBands+1):
    emptyArrayList.append(emptyArray)

  zeros = ee.Image(ee.Array(emptyArrayList))        # make an image to fill holes in result 'LandTrendr' array where vertices found is not equal to maxSegments parameter plus 1
                               
  
  lbls = [bandNames, vertLabels] # labels for 2 dimensions of the array that will be cast to each other in the final step of creating the vertice output 
  
          # slices out the 4th row of a 4 row x N col (N = number of years in annual stack) matrix, which identifies vertices - contains only 0s and 1s, where 1 is a vertex (referring to spectral-temporal segmentation) year and 0 is not
  
  ltVertStack = LTresult.addBands(zeros)\
                        .toArray(1)\
                        .arraySlice(1, 0, maxVertices)\
                        .arrayFlatten(lbls, '')      
  # Line by line comments taken from call above
  # LTresult:                       # uses the sliced out isVert row as a mask to only include vertice in this data - after this a pixel will only contain as many "bands" are there are vertices for that pixel - min of 2 to max of 7. 
  # .addBands(zeros):               # ...adds the 3 row x 7 col 'zeros' matrix as a band to the vertOnly array - this is an intermediate step to the goal of filling in the vertOnly data so that there are 7 vertice slots represented in the data - right now there is a mix of lengths from 2 to 7
  # .toArray(1):                    # ...concatenates the 3 row x 7 col 'zeros' matrix band to the vertOnly data so that there are at least 7 vertice slots represented - in most cases there are now > 7 slots filled but those will be truncated in the next step
  # .arraySlice(1, 0, maxVertices): # ...before this line runs the array has 3 rows and between 9 and 14 cols depending on how many vertices were found during segmentation for a given pixel. this step truncates the cols at 7 (the max verts allowed) so we are left with a 3 row X 7 col array
  # .arrayFlatten(lbls, ''):        # ...this takes the 2-d array and makes it 1-d by stacking the unique sets of rows and cols into bands. there will be 7 bands (vertices) for vertYear, followed by 7 bands (vertices) for rawVert, followed by 7 bands (vertices) for fittedVert, according to the 'lbls' list
  return ltVertStack.updateMask(ltVertStack.neq(-32768))

#Function to wrap landtrendr processing
def landtrendrWrapper(processedComposites,startYear,endYear,indexName,distDir,run_params,distParams,mmu):
  # startYear = 1984#ee.Date(ee.Image(processedComposites.first()).get('system:time_start')).get('year').getInfo()
  # endYear = 2017#ee.Date(ee.Image(processedComposites.sort('system:time_start',false).first()).get('system:time_start')).get('year').getInfo()
  noDataValue = 32768
  if (distDir == 1):
    noDataValue = -1.*noDataValue

  #----- RUN LANDTRENDR -----
  ltCollection = processedComposites.select(indexName).map(lambda img:
     ee.Image(multBands(img,distDir,1)))#.unmask(noDataValue)

  # Map.addLayer(ltCollection,{},'ltCollection',false)
  run_params['timeSeries'] = ltCollection               # add LT collection to the segmentation run parameter object
  lt = ee.Algorithms.TemporalSegmentation.LandTrendr(**run_params) # run LandTrendr spectral temporal segmentation algorithm
  
  #########################################################################################################
  ###### RUN THE GREATEST DISTURBANCE EXTRACT FUNCTION #####
  #########################################################################################################
  
  # run the dist extract function
  distImg = extractDisturbance(lt.select('LandTrendr'), distDir, distParams,mmu)
  distImgBandNames = distImg.bandNames()
  distImgBandNames = distImgBandNames.map(lambda bn: ee.String(indexName).cat('_').cat(bn))
  distImg = distImg.rename(distImgBandNames)
  
  #Convert to collection
  rawLT = lt.select([0])
  ltYear = rawLT.arraySlice(0,0,1).arrayProject([1])
  ltFitted = rawLT.arraySlice(0,2,3).arrayProject([1])
  if (distDir == -1):
    ltFitted = ltFitted.multiply(-1)

  
  fittedCollection = arrayToTimeSeries(ltFitted,ltYear,ee.List.sequence(startYear,endYear),'LT_Fitted_'+indexName)
  

  #Convert to single image
  vertStack = getLTvertStack(rawLT,run_params)
  return [lt,distImg,fittedCollection,vertStack]

# Function to prep data following our workflows. Will have to run Landtrendr and convert to stack after.
def prepTimeSeriesForLandTrendr(ts,indexName, run_params):
  maxSegments = ee.Number(run_params['maxSegments'])
  startYear = ee.Date(ts.first().get('system:time_start')).get('year')
  endYear = ee.Date(ts.sort('system:time_start',False).first().get('system:time_start')).get('year')

  # Get single band time series and set its direction so that a loss in veg is going up
  ts = ts.select([indexName])
  distDir = changeDirDict[indexName]
  tsT = ts.map(lambda img: multBands(img, 1, distDir))
  
  # Find areas with insufficient data to run LANDTRENDR
  countMask = tsT.count().unmask().gte(maxSegments.add(1))

  # Mask areas identified by countMask
  tsT = tsT.map(lambda img: nullFinder(img, countMask))

  run_params['timeSeries'] = tsT
  countMask = countMask.rename('insufficientDataMask')
  prepDict = {\
    'run_params': run_params,\
    'countMask':    countMask\
  }

  return prepDict 

# This function outputs Landtrendr as a vertical stack and adds properties about the run.
def LANDTRENDRVertStack(composites, indexName, run_params, startYear, endYear):
  creationDate = datetime.strftime(datetime.now(),'%Y%m%d')

  # Prep Time Series and put into run parameters
  prepDict = prepTimeSeriesForLandTrendr(composites, indexName, run_params)
  run_params = prepDict['run_params']
  countMask = prepDict['countMask']

  # Run LANDTRENDR
  rawLt = ee.Algorithms.TemporalSegmentation.LandTrendr(**run_params)
  
  # Convert to image stack
  lt = rawLt.select([0])
  ltStack = ee.Image(getLTvertStack(lt, run_params)).updateMask(countMask)
  ltStack = ltStack.select('yrs.*').addBands(ltStack.select('fit.*'))
  rmse = rawLt.select([1]).rename('rmse')    
  ltStack = ltStack.addBands(rmse) 

  # Undo distdir change done in prepTimeSeriesForLandtrendr()
  ltStack = applyDistDir_vertStack(ltStack, changeDirDict[indexName], 'landtrendr')

  # Set Properties
  ltStack = ltStack.set({\
    'startYear': startYear,\
    'endYear': endYear,\
    'band': indexName,\
    'creationDate': creationDate,\
    'maxSegments': run_params['maxSegments'],\
    'spikeThreshold': run_params['spikeThreshold'],\
    'vertexCountOvershoot': run_params['vertexCountOvershoot'],\
    'recoveryThreshold': run_params['recoveryThreshold'],\
    'pvalThreshold': run_params['pvalThreshold'],\
    'bestModelProportion': run_params['bestModelProportion'],\
    'minObservationsNeeded': run_params['minObservationsNeeded']\
  })

  return ee.Image(ltStack)

#############################################/
#Function for running LANDTRENDR and converting output to annual image collection
#with the fitted value, duration, magnitude, slope, and diff for the segment for each given year
def LANDTRENDRFitMagSlopeDiffCollection(ts, indexName, run_params):

  startYear = ee.Date(ts.first().get('system:time_start')).get('year')
  endYear = ee.Date(ts.sort('system:time_start',False).first().get('system:time_start')).get('year')
  
  # Run LandTrendr and convert to VertStack format
  ltStack = ee.Image(LANDTRENDRVertStack(ts, indexName, run_params, startYear, endYear))
  ltStack = ee.Image(LT_VT_vertStack_multBands(ltStack, 'landtrendr', 10000))
  
  # Convert to durFitMagSlope format
  durFitMagSlope = convertStack_To_DurFitMagSlope(ltStack, 'LT')
  
  return durFitMagSlope

#----------------------------------------------------------------------------------------------------
#        Functions for both Verdet and Landtrendr
#----------------------------------------------------------------------------------------------------
# Helper to multiply new baselearner format values (LandTrendr & Verdet) by the appropriate amount when importing
# Duration is the only band that does not get multiplied by 0.0001 upon import.
# img = landtrendr or verdet image in fitMagDurSlope format
# multBy = 10000 (to prep for export) or 0.0001 (after import)
def LT_VT_multBands(img, multBy):
    fitted = img.select('.*_fitted').multiply(multBy)
    slope = img.select('.*_slope').multiply(multBy)
    diff = img.select('.*_diff').multiply(multBy)
    mag = img.select('.*_mag').multiply(multBy)
    dur = img.select('.*_dur')
    out = dur.addBands(fitted).addBands(slope).addBands(diff).addBands(mag)
    out  = out.copyProperties(img,['system:time_start'])\
              .copyProperties(img)
    return out

# Function to apply the Direction of  a decrease in photosynthetic vegetation to Landtrendr or Verdet vertStack format
# img = vertStack image for one band, e.g. "NBR"
# verdet_or_landtrendr = 'verdet' or 'landtrendr'
# distDir = from getImagesLib.changeDirDict
def applyDistDir_vertStack(stack, distDir, verdet_or_landtrendr):
  years = stack.select('yrs.*')
  fitted = stack.select('fit.*').multiply(distDir)
  out = years.addBands(fitted)
  if verdet_or_landtrendr == 'landtrendr':
    rmse = stack.select('rmse')
    out = out.addBands(rmse) 
  out  = out.copyProperties(stack,['system:time_start'])\
            .copyProperties(stack)
  return out

# Helper to multiply vertStack bands by the appropriate amount before exporting (multBy = 10000)
# or after importing (multBy = 0.0001)
# img = vertStack image for one band, e.g. "NBR"
# verdet_or_landtrendr = 'verdet' or 'landtrendr'
# multBy = 10000 or 0.0001
def LT_VT_vertStack_multBands(img, verdet_or_landtrendr, multBy):
    years = img.select('yrs.*')
    fitted = img.select('fit.*').multiply(multBy)
    out = years.addBands(fitted)
    if verdet_or_landtrendr == 'landtrendr':
      rmse = img.select('rmse').multiply(multBy)
      out = out.addBands(rmse) 
    out  = out.copyProperties(img,['system:time_start'])\
              .copyProperties(img)
    return out

# Function to parse stack from LANDTRENDR or VERDET into image collection
# July 2019 LSC: multiply(distDir) and multiply(10000) now take place outside of this function,
# but must be done BEFORE stack is passed to this function
def fitStackToCollection(stack, maxSegments, startYear, endYear):
  # Parse into annual fitted, duration, magnitude, and slope images
  # Iterate across each possible segment and find its fitted end value, duration, magnitude, and slope
  def segmentLooper(i):
    i = ee.Number(i)
    
    #Set up slector for left and right side of segments
    stringSelectLeft = ee.String('.*_').cat(i.byte().format())
    stringSelectRight = ee.String('.*_').cat((i.add(1)).byte().format())
    
    #Get the left and right bands into separate images
    stackLeft = stack.select([stringSelectLeft])
    stackRight = stack.select([stringSelectRight])
    
    #Select off the year bands
    segYearsLeft = stackLeft.select(['yrs_.*']).rename(['year_left'])
    segYearsRight = stackRight.select(['yrs_.*']).rename(['year_right'])
    
    #Select off the fitted bands and flip them if they were flipped for use in LT
    segFitLeft = stackLeft.select(['fit_.*']).rename(['fitted'])
    segFitRight = stackRight.select(['fit_.*']).rename(['fitted'])
    
    #Comput duration, magnitude, and then slope
    segDur = segYearsRight.subtract( segYearsLeft).rename(['dur'])
    segMag = segFitRight.subtract( segFitLeft).rename(['mag'])
    segSlope = segMag.divide(segDur).rename(['slope'])
    
    #Iterate across each year to see if the year is within a given segment
    #All annualizing is done from the right vertex backward
    #The first year of the time series is inserted manually with an if statement
    #Ex: If the first segment goes from 1984-1990 and the second from 1990-1997, the duration, magnitude,and slope
    #values from the first segment will be given to 1984-1990, while the second segment (and any subsequent segment)
    #the duration, magnitude, and slope values will be given from 1991-1997    
    def annualizer(yr):
      yr = ee.Number(yr)
      yrImage = ee.Image(yr)
      
      #Find if the year is the first and include the left year if it is
      #Otherwise, do not include the left year
      yrImage = ee.Algorithms.If(yr.eq(startYear),
                  yrImage.updateMask(segYearsLeft.lte(yr).And(segYearsRight.gte(yr))),
                  yrImage.updateMask(segYearsLeft.lt(yr).And(segYearsRight.gte(yr))))
    
      yrImage = ee.Image(yrImage).rename(['yr']).int16()
      
      #Mask out the duration, magnitude, slope, and fit raster for the given year mask
      yrDur = segDur.updateMask(yrImage)
      yrMag = segMag.updateMask(yrImage)
      yrSlope = segSlope.updateMask(yrImage)
      yrFit = segFitRight.subtract(yrSlope.multiply(segYearsRight.subtract(yr))).updateMask(yrImage)
      
      #Get the difference from the 
      diffFromLeft =yrFit.subtract(segFitLeft).updateMask(yrImage).rename(['diff'])
      # relativeDiffFromLeft = diffFromLeft.divide(segMag.abs()).updateMask(yrImage).rename(['rel_yr_diff_left']).multiply(10000)
      
      # diffFromRight =yrFit.subtract(segFitRight).updateMask(yrImage).rename(['yr_diff_right'])
      # relativeDiffFromRight = diffFromRight.divide(segMag.abs()).updateMask(yrImage).rename(['rel_yr_diff_right']).multiply(10000)
      #Stack it up
      out = yrDur.addBands(yrFit).addBands(yrMag).addBands(yrSlope)\
                .addBands(diffFromLeft)

      out = out.set('system:time_start',ee.Date.fromYMD(yr,6,1).millis())
      return out

    annualCollection = ee.FeatureCollection(ee.List.sequence(startYear,endYear).map(lambda yr: annualizer(yr)))
    return annualCollection  

  yrDurMagSlope = ee.FeatureCollection(ee.List.sequence(1,maxSegments).map(lambda i: segmentLooper(i)))

  #Convert to an image collection
  yrDurMagSlope = ee.ImageCollection(yrDurMagSlope.flatten())
  
  #Collapse each given year to the single segment with data  
  def cleaner(yrDurMagSlope, yr):
    yrDurMagSlopeT = yrDurMagSlope.filter(ee.Filter.calendarRange(yr,yr,'year')).mosaic()
    yrDurMagSlopeT = yrDurMagSlopeT.set('system:time_start',ee.Date.fromYMD(yr,6,1).millis())
    return yrDurMagSlopeT
  yrDurMagSlopeCleaned = ee.ImageCollection.fromImages(ee.List.sequence(startYear,endYear).map(lambda yr: cleaner(yrDurMagSlope, yr)))

  return yrDurMagSlopeCleaned

# Convert image collection created using LANDTRENDRVertStack() to the same format as that created by
# LANDTRENDRFitMagSlopeDiffCollection(). Also works for Verdet Stack.
# VTorLT is the string that is put in the band names, 'LT' or 'VT'
def convertStack_To_DurFitMagSlope(stackCollection, VTorLT):
  stackList = stackCollection.first().bandNames()
  if 'rmse' in stackList.getInfo():
    stackList.remove('rmse')
    stackCollection = stackCollection.select(stackList)

  # Prep parameters for fitStackToCollection
  maxSegments = stackCollection.first().get('maxSegments')
  startYear = stackCollection.first().get('startYear')
  endYear = stackCollection.first().get('endYear')
  indexList = ee.Dictionary(stackCollection.aggregate_histogram('band')).keys().getInfo()
  
  #Set up output collection to populate
  outputCollection = []
  #Iterate across indices
  for indexName in indexList: 
    stack = stackCollection.filter(ee.Filter.eq('band',indexName)).first()
  
    #Convert to image collection
    yrDurMagSlopeCleaned = fitStackToCollection(stack, \
      maxSegments, \
      startYear, \
      endYear\
    ) 
    
    # Rename
    bns = ee.Image(yrDurMagSlopeCleaned.first()).bandNames()
    outBns = bns.map(lambda bn: ee.String(indexName).cat('_'+VTorLT+'_').cat(bn))  
    yrDurMagSlopeCleaned = yrDurMagSlopeCleaned.select(bns,outBns)
  
    if outputCollection == []:
      outputCollection = yrDurMagSlopeCleaned
    else:
      outputCollection = joinCollections(outputCollection, yrDurMagSlopeCleaned, False)

  return outputCollection

#############################################/


#--------------------------------------------------------------------------
#                 Linear Interpolation functions
#--------------------------------------------------------------------------
#Adapted from: https:#code.earthengine.google.com/?accept_repo=users/kongdd/public
#To work with multi-band images
def replace_mask(img, newimg, nodata = 0):
    # con = img.mask()
    # res = img., NODATA
    mask = img.mask()
    
    '''** 
     * This solution lead to interpolation fails | 2018-07-12
     * Good vlaues can become NA.
     *'''
    # img = img.expression("img*mask + newimg*(!mask)", {
    #     img    : img.unmask(),  # default unmask value is zero
    #     newimg : newimg, 
    #     mask   : mask
    # })

    #** The only nsolution is unmask & updatemask */
    img = img.unmask(nodata)
    img = img.where(mask.Not(), newimg)
    # 
    # error 2018-07-13 : mask already in newimg, so it's unnecessary to updateMask again
    # either test or image is masked, values will not be changed. So, newimg 
    # mask can transfer to img. 
    # 
    img = img.updateMask(img.neq(nodata))
    return img

#** Interpolation not considering weights */
def addMillisecondsTimeBand(img):
    #** make sure mask is consistent */
    mask = img.mask().reduce(ee.Reducer.min())
    time = img.metadata('system:time_start').rename("time").mask(mask)
    return img.addBands(time)

def linearInterp(imgcol, frame = 32, nodata = 0):
    bns = ee.Image(imgcol.first()).bandNames()
    # frame = 32
    time   = 'system:time_start'
    imgcol = imgcol.map(addMillisecondsTimeBand)
   
    # We'll look for all images up to 32 days away from the current image.
    maxDiff = ee.Filter.maxDifference(frame * (1000*60*60*24), time, None, time)
    cond    = {'leftField':time, 'rightField':time}
    
    # Images after, sorted in descending order (so closest is last).
    #f1 = maxDiff.and(ee.Filter.lessThanOrEquals(time, null, time))
    f1 = ee.Filter.And(maxDiff, ee.Filter.lessThanOrEquals(**cond))
    c1 = ee.Join.saveAll(**{'matchesKey':'after', 'ordering':time, 'ascending':False})\
        .apply(imgcol, imgcol, f1)
    
    # Images before, sorted in ascending order (so closest is last).
    #f2 = maxDiff.and(ee.Filter.greaterThanOrEquals(time, null, time))
    f2 = ee.Filter.And(maxDiff, ee.Filter.greaterThanOrEquals(**cond))
    c2 = ee.Join.saveAll(**{'matchesKey':'before', 'ordering':time, 'ascending':True})\
        .apply(c1, imgcol, f2)
  
    # print(c2, 'c2')
    # img = ee.Image(c2.toList(1, 15).get(0))
    # mask   = img.select([0]).mask()
    # Map.addLayer(img , {}, 'img')
    # Map.addLayer(mask, {}, 'mask')
    def interpolator(img):
        img = ee.Image(img)
      
        before = ee.ImageCollection.fromImages(ee.List(img.get('before'))).mosaic()
        after  = ee.ImageCollection.fromImages(ee.List(img.get('after'))).mosaic()
        
        img = img.set('before', None).set('after', None)
        # constrain after or before no NA values, confirm linear Interp having result
        before = replace_mask(before, after, nodata)
        after  = replace_mask(after , before, nodata)
        
        # Compute the ratio between the image times.
        x1 = before.select('time').double()
        x2 = after.select('time').double()
        now = ee.Image.constant(img.date().millis()).double()
        ratio = now.subtract(x1).divide(x2.subtract(x1))  # this is zero anywhere x1 = x2
        # Compute the interpolated image.
        before = before.select(bns) #remove time band now
        after  = after.select(bns)
        img    = img.select(bns) 
        
        interp = after.subtract(before).multiply(ratio).add(before)
        # mask   = img.select([0]).mask()
        
        qc = img.mask().Not()#.rename('qc')
        interp = replace_mask(img, interp, nodata)
        # Map.addLayer(interp, {}, 'interp')
        return interp.copyProperties(img, img.propertyNames())
    interpolated = ee.ImageCollection(c2.map(lambda img: interpolator(img)))

    return interpolated

# Function to apply linear interpolation for Verdet
def applyLinearInterp(composites, nYearsInterpolate):      
    
    # Start with just the basic bands
    composites = composites.select(['red','green','blue','nir','swir1','swir2'])
    
    # Find pixels/years with no data
    masks = composites.map(lambda img: img.mask().reduce(ee.Reducer.min()).byte().copyProperties(img, img.propertyNames())).select([0])
    masks = masks.map(lambda img: img.rename([ee.Date(img.get('system:time_start')).format('YYYY')]))
    masks = masks.toBands()

    # rename bands to better names
    origNames = masks.bandNames()
    print('mask bandNames', origNames.getInfo())
    newNames = origNames.map(lambda bandName: ee.String(bandName).replace('null','mask'))
    masks = masks.select(origNames, newNames).set('creationDate',datetime.strftime(datetime.now(),'%Y%m%d')).set('mask',True)
    
    # Perform linear interpolation        
    composites = linearInterp(composites, 365*nYearsInterpolate, -32768)\
            .map(simpleAddIndices)\
            .map(getTasseledCap)\
            .map(simpleAddTCAngles)
            
    outDict = {'composites': composites,\
                   'masks':      masks\
    }
    return outDict

#--------------------------------------------------------------------------
#                 VERDET
#--------------------------------------------------------------------------
# Functions to apply our scaling work arounds for Verdet
# Multiply by a predetermined factor beforehand and divide after
# Add 1 before and subtract 1 after
def applyVerdetScaling(ts, indexName, correctionFactor):
  distDir = changeDirDict[indexName]
  #tsT = ts.map(lambda img: multBands(img, 1, -distDir)) # Apply change in direction first
  tsT = ts.map(lambda img: addToImage(img, 1))            # Then add 1 to image to get rid of any negatives
  tsT = tsT.map(lambda img: multBands(img, 1, correctionFactor))  # Finally we can apply scaling.
  return tsT

def undoVerdetScaling(fitted, indexName, correctionFactor):
  distDir = changeDirDict[indexName]
  fitted = ee.Image(multBands(fitted, 1, 1.0/correctionFactor)) # Undo scaling first
  fitted = addToImage(fitted, -1) # Undo getting rid of negatives
  #fitted = multBands(fitted, 1, -distDir) #Finally, undo change in direction # LSC 10/19, this is not working as intended. Decided to just comment it out as I believe it is an unnecessary step.
  return fitted

# Function to prep data for Verdet. Will have to run Verdet and convert to stack after.
# This step applies the Verdet Scaling. The scaling is undone in VERDETVertStack().
def prepTimeSeriesForVerdet(ts, indexName, run_params, correctionFactor):
  # Get the start and end years
  startYear = ee.Date(ts.first().get('system:time_start')).get('year')
  endYear = ee.Date(ts.sort('system:time_start',False).first().get('system:time_start')).get('year')

  # Get single band time series and set its direction so that a loss in veg is going up
  ts = ts.select([indexName])
  tsT = applyVerdetScaling(ts, indexName, correctionFactor)
  
  # Find areas with insufficient data to run VERDET
  # VERDET currently requires all pixels have a value
  countMask = tsT.count().unmask().gte(endYear.subtract(startYear).add(1))
  
  # Mask areas identified by countMask
  tsT = tsT.map(lambda img: nullFinder(img, countMask))

  run_params['timeSeries'] = tsT
  
  countMask = countMask.rename('insufficientDataMask')
  prepDict = {\
    'run_params': run_params,\
    'countMask':  countMask,\
    'startYear':  startYear,\
    'endYear':    endYear\
  }
  
  return prepDict  

# Function to run Verdet and reformat as vertex stack in the same format as landtrendr
def VERDETVertStack(ts,indexName,run_params = {'tolerance': 0.0001, 'alpha': 0.1}, maxSegments = 10, correctionFactor = 1, doLinearInterp = 'false'):
  # linearInterp is applied outside this function. This parameter is just to set the properties (true/false)
  
  # Get today's date for properties
  creationDate = datetime.strftime(datetime.now(),'%Y%m%d')
  
  # Extract composite time series and apply relevant masking & scaling
  prepDict = prepTimeSeriesForVerdet(ts, indexName, run_params, correctionFactor)
  run_params = prepDict['run_params']
  countMask = prepDict['countMask']
  startYear = prepDict['startYear']
  endYear = prepDict['endYear']
  
  # Run VERDET
  verdet =   ee.Algorithms.TemporalSegmentation.Verdet(**run_params).arraySlice(0,1,None)
  
  #Get all possible years
  tsYearRight = ee.Image(ee.Array.cat([ee.Array([startYear]),ee.Array(ee.List.sequence(startYear.add(2),endYear))]))
  #Slice off right and left slopes
  vLeft = verdet.arraySlice(0,1,-1)
  vRight = verdet.arraySlice(0,2,None)
  
  #Find whether its a vertex (abs of curvature !== 0)
  vCurvature = vLeft.subtract(vRight)
  vVertices = vCurvature.abs().gte(0.00001)
  
  #Append vertices to the start and end of the time series al la LANDTRENDR
  vVertices = ee.Image(ee.Array([1])).arrayCat(vVertices,0).arrayCat(ee.Image(ee.Array([1])),0)
  #Mask out vertex years
  tsYearRight = tsYearRight.arrayMask(vVertices)
  #Find the duration of each segment
  dur = tsYearRight.arraySlice(0,1,None).subtract(tsYearRight.arraySlice(0,0,-1))
  dur = ee.Image(ee.Array([0])).arrayCat(dur,0)
  #Mask out vertex slopes
  verdet = verdet.arrayMask(vVertices)
  
  #Get the magnitude of change for each segment
  mag = verdet.multiply(dur)
  
  #Get the fitted values
  fitted = ee.Image(run_params['timeSeries'].limit(3).mean()).toArray().arrayCat(mag,0)
  fitted = fitted.arrayAccum(0, ee.Reducer.sum()).arraySlice(0,1,None)
  # Undo scaling of fitted values
  fitted = undoVerdetScaling(fitted, indexName, correctionFactor)
  
  #Get the bands needed to convert to image stack
  forStack = tsYearRight.addBands(fitted).toArray(1)  

  #Convert to stack and mask out any pixels that didn't have an observation in every image
  stack = getLTStack(forStack.arrayTranspose(),maxSegments+1,['yrs_','fit_']).updateMask(countMask)

  # Set Properties
  stack = stack.set({\
    'startYear': startYear,\
    'endYear': endYear,\
    'band': indexName,\
    'creationDate': creationDate,\
    'maxSegments': maxSegments,\
    'correctionFactor': correctionFactor,\
    'tolerance': run_params['tolerance'],\
    'alpha': run_params['alpha'],\
    'linearInterpApplied': doLinearInterp\
  })

  return ee.Image(stack)

# Update Mask from LinearInterp step
def updateVerdetMasks(img, linearInterpMasks):
  thisYear = ee.Date(img.get('system:time_start')).format('YYYY')
  #thisYear_maskName = ee.String('mask_').cat(thisYear)
  thisYear_maskName = ee.String('.*_').cat(thisYear)
  thisMask = linearInterpMasks.select(thisYear_maskName)
  img = img.updateMask(thisMask)
  return img

# Function for running VERDET and converting output to annual image collection
# with the fitted value, duration, magnitude, slope, and diff for the segment for each given year
# Linear Interpolation has to be done beforehand, and the masks collection passed in to this function
def VERDETFitMagSlopeDiffCollection(composites, indexName, run_params = {'tolerance':0.0001, 'alpha': 0.1}, maxSegments = 10, correctionFactor = 1, doLinearInterp = 'false', masks = None):
  
  # Run Verdet and convert to vertStack format
  vtStack = VERDETVertStack(composites, indexName, run_params, maxSegments, correctionFactor, doLinearInterp)
  vtStack = ee.Image(LT_VT_vertStack_multBands(vtStack, 'verdet', 10000)) # This needs to happen before the fitStackToCollection() step
  
  # Convert to durFitMagSlope format
  durFitMagSlope = convertStack_To_DurFitMagSlope(vtStack, 'VT')

  # Prep data types for export
  durFitMagSlope = durFitMagSlope.map(lambda img: img.int16())

  if doLinearInterp:
    durFitMagSlope = durFitMagSlope.map(lambda img: updateVerdetMasks(img))

  return durFitMagSlope

#Wrapper for applying VERDET slightly more simply
#Returns annual collection of verdet slope
def verdetAnnualSlope(tsIndex, indexName, startYear, endYear, alpha): #tolerance = 0.0001,alpha = 1/3.0):
  #Apply VERDET
  run_params = {'timeSeries': tsIndex,
                'tolerance': 0.0001, # default = 0.0001
                'alpha': alpha} # default = 1/3.0
  verdet =   ee.Algorithms.TemporalSegmentation.Verdet(**run_params).arraySlice(0,1,None)
  print('indexName: '+indexName)
  #Map.addLayer(verdet,{},'verdet '+indexName)
  tsYear = tsIndex.map(getImageLib.addYearBand).select([1]).toArray().arraySlice(0,1,None).arrayProject([0])
  
  #Find possible years to convert back to collection with
  #possibleYears = ee.List.sequence(startYear+1,endYear)
  possibleYears = ee.List.sequence(startYear, endYear)
  verdetC = arrayToTimeSeries(verdet, tsYear, possibleYears, 'VERDET_fitted_'+indexName+'_slope')
  
  return verdetC

#--------------------------------------------------------------------------
#          UNCONVERTED JAVASCRIPT FUNCTIONS BELOW HERE
#--------------------------------------------------------------------------

#######################/
def thresholdChange(changeCollection,changeThresh,changeDir = None):
  if changeDir == None:changeDir = 1
  bandNames = ee.Image(changeCollection.first()).bandNames()
  bandNames = bandNames.map(lambda bn: ee.String(bn).cat('_change'))
  def thresholder(img):
    yr = ee.Date(img.get('system:time_start')).get('year')
    changeYr = img.multiply(changeDir).gt(changeThresh)
    yrImage = img.where(img.mask(),yr)
    changeYr = yrImage.updateMask(changeYr).rename(bandNames).int16()
    return img.mask(ee.Image(1)).addBands(changeYr)

  change = changeCollection.map(thresholder)

  return change

# function thresholdSubtleChange(changeCollection,changeThreshLow,changeThreshHigh,changeDir){
#   if(changeDir === undefined || changeDir === null){changeDir = 1}
#   bandNames = ee.Image(changeCollection.first()).bandNames()
#   bandNames = bandNames.map(function(bn){return ee.String(bn).cat('_change')})
#   change = changeCollection.map(function(img){
#     yr = ee.Date(img.get('system:time_start')).get('year')
#     changeYr = img.multiply(changeDir).gt(changeThreshLow).and(img.multiply(changeDir).lt(changeThreshHigh))
#     yrImage = img.where(img.mask(),yr)
#     changeYr = yrImage.updateMask(changeYr).rename(bandNames).int16()
#     return img.mask(ee.Image(1)).addBands(changeYr)
#   })
#   return change
# }

# function getExistingChangeData(changeThresh,showLayers){
#   if(showLayers === undefined || showLayers === null){
#     showLayers = true
#   }
#   if(changeThresh === undefined || changeThresh === null){
#     changeThresh = 50
#   }
#   startYear = 1985
#   endYear = 2016
  
  
  
#   # glriEnsemble = ee.Image('projects/glri-phase3/changeMaps/ensembleOutputs/NBR_NDVI_TCBGAngle_swir1_swir2_median_LT_Ensemble')
  
  
  
  
  
 
#   # if(showLayers){
#   # Map.addLayer(conusChange.select(['change']).max(),{'min':startYear,'max':endYear,'palette':'FF0,F00'},'CONUS LCMS Most Recent Year of Change',false)
#   # Map.addLayer(conusChange.select(['probability']).max(),{'min':0,'max':50,'palette':'888,008'},'LCMSC',false)
#   # }
#   # glri_lcms = glriEnsemble.updateMask(glriEnsemble.select([0])).select([1])
#   # glri_lcms = glri_lcms.updateMask(glri_lcms.gte(startYear).and(glri_lcms.lte(endYear)))
#   # if(showLayers){
#   # Map.addLayer(glri_lcms,{'min':startYear,'max':endYear,'palette':'FF0,F00'},'GLRI LCMS',false)
#   # }
  
  
  
#   hansen = ee.Image('UMD/hansen/global_forest_change_2016_v1_4').select(['lossyear']).add(2000).int16()
#   hansen = hansen.updateMask(hansen.neq(2000).and(hansen.gte(startYear)).and(hansen.lte(endYear)))
#   if(showLayers){
#   Map.addLayer(hansen,{'min':startYear,'max':endYear,'palette':'FF0,F00'},'Hansen Change Year',false)
#   }
#   # return conusChangeOut
# }



# #####################################
# #Wrapper for applying EWMACD slightly more simply
# function getEWMA(lsIndex,trainingStartYear,trainingEndYear, harmonicCount){
#   if(harmonicCount === null || harmonicCount === undefined){harmonicCount = 1}
  
  
#   #Run EWMACD 
#   ewmacd = ee.Algorithms.TemporalSegmentation.Ewmacd({
#     timeSeries: lsIndex, 
#     vegetationThreshold: -1, 
#     trainingStartYear: trainingStartYear, 
#     trainingEndYear: trainingEndYear, 
#     harmonicCount: harmonicCount
#   })
  
#   #Extract the ewmac values
#   ewma = ewmacd.select(['ewma'])
#   return ewma
# }

# #Function for converting EWMA values to annual collection
# function annualizeEWMA(ewma,indexName,lsYear,startYear,endYear,annualReducer,remove2012){
#   #Fill null parameters
#   if(annualReducer === null || annualReducer === undefined){annualReducer = ee.Reducer.min()}
#   if(remove2012 === null || remove2012 === undefined){remove2012 = true}
  
#    #Find the years to annualize with
#   years = ee.List.sequence(startYear,endYear)
  
#   #Find if 2012 needs replaced
#   replace2012 = ee.Number(ee.List([years.indexOf(2011),years.indexOf(2012),years.indexOf(2013)]).reduce(ee.Reducer.min())).neq(-1).getInfo()
#   print('2012 needs replaced:',replace2012)
  
  
#   #Remove 2012 if in list and set to true
#   if(remove2012){years = years.removeAll([2012])}
  
  
  
  
#   #Annualize
#   #Set up dummy image for handling null values
#   noDateValue = -32768;
#   dummyImage = ee.Image(noDateValue).toArray();
    
  
#   annualEWMA = years.map(function(yr){
#     yr = ee.Number(yr);
#     yrMask = lsYear.int16().eq(yr);
#     ewmacdYr = ewma.arrayMask(yrMask);
#     ewmacdYearYr = lsYear.arrayMask(yrMask);
#     ewmacdYrSorted = ewmacdYr.arraySort(ewmacdYr);
#     ewmacdYearYrSorted= ewmacdYearYr.arraySort(ewmacdYr);
    
#     yrData = ewmacdYrSorted.arrayCat(ewmacdYearYrSorted,1);
#     yrReduced = ewmacdYrSorted.arrayReduce(annualReducer,[0]);
   
    
#     #Find null pixels
#     l = yrReduced.arrayLength(0);
    
#     #Fill null values and convert to regular image
#     yrReduced = yrReduced.where(l.eq(0),dummyImage).arrayGet([-1]);
    
#     #Remask nulls
#     yrReduced = yrReduced.updateMask(yrReduced.neq(noDateValue)).rename(['EWMA_'+indexName])      
#       .set('system:time_start',ee.Date.fromYMD(yr,6,1).millis()).int16();
      
   
#     return yrReduced;
#   });
#   annualEWMA = ee.ImageCollection.fromImages(annualEWMA);
#   # print(remove2012,replace2012 ==1)
#   if(remove2012 && replace2012 ==1){
#     print('Replacing EWMA 2012 with mean of 2011 and 2013');
#     value2011 = ee.Image(annualEWMA.filter(ee.Filter.calendarRange(2011,2011,'year')).first());
#     value2013 = ee.Image(annualEWMA.filter(ee.Filter.calendarRange(2013,2013,'year')).first());
#     value2012 = value2013.add(value2011);
#     value2012 = value2012.divide(2).rename(['EWMA_'+indexName])
#     .set('system:time_start',ee.Date.fromYMD(2012,6,1).millis()).int16();
    
#     annualEWMA = ee.ImageCollection(ee.FeatureCollection([annualEWMA,ee.ImageCollection([value2012])]).flatten()).sort('system:time_start');
#   }
#   return annualEWMA;
# }
# #
# function runEWMACD(lsIndex,indexName,startYear,endYear,trainingStartYear,trainingEndYear, harmonicCount,annualReducer,remove2012){
#   # bandName = ee.String(ee.Image(lsIndex.first()).bandNames().get(0));
 
#   ewma = getEWMA(lsIndex,trainingStartYear,trainingEndYear, harmonicCount);
  
#   #Get dates for later reference
#   lsYear = lsIndex.map(function(img){return getImageLib.addDateBand(img,true)}).select(['year']).toArray().arrayProject([0]);

  
#   annualEWMA = annualizeEWMA(ewma,indexName,lsYear,startYear,endYear,annualReducer,remove2012);
  
#   return [ewma.arrayCat(lsYear,1),annualEWMA];
# }
# #####################################
# #Function to find the pairwise difference of a time series
# #Assumes one image per year
# function pairwiseSlope(c){
#     c = c.sort('system:time_start');
    
#     bandNames = ee.Image(c.first()).bandNames();
#     # bandNames = bandNames.map(function(bn){return ee.String(bn).cat('_slope')});
    
#     years = c.toList(10000).map(function(i){i = ee.Image(i);return ee.Date(i.get('system:time_start')).get('year')});
    
#     yearsLeft = years.slice(0,-1);
#     yearsRight = years.slice(1,null);
#     yearPairs = yearsLeft.zip(yearsRight);
    
#     slopeCollection = yearPairs.map(function(yp){
#       yp = ee.List(yp);
#       yl = ee.Number(yp.get(0));
#       yr = ee.Number(yp.get(1));
#       yd = yr.subtract(yl);
#       l = ee.Image(c.filter(ee.Filter.calendarRange(yl,yl,'year')).first()).add(0.000001);
#       r = ee.Image(c.filter(ee.Filter.calendarRange(yr,yr,'year')).first());
      
#       slope = (r.subtract(l)).rename(bandNames);
#       slope = slope.set('system:time_start',ee.Date.fromYMD(yr,6,1).millis());
#       return slope;
#     });
#     return ee.ImageCollection.fromImages(slopeCollection);
#   }

############################################Function for converting collection into annual median collection
#Does not support date wrapping across the new year (e.g. Nov- April window is a no go)
def toAnnualMedian(images,startYear,endYear):
  dummyImmage = ee.Image(images.first())
  def getMedian(yr):
    imagesT = images.filter(ee.Filter.calendarRange(yr,yr,'year'))
    imagesT = getImageLib.fillEmptyCollections(imagesT,dummyImmage)
    return imagesT.median().set('system:time_start',ee.Date.fromYMD(yr,6,1))
  out = ee.List.sequence(startYear,endYear).map(getMedian)
  return ee.ImageCollection.fromImages(out)

############################################Function for applying linear fit model
#Assumes the model has a intercept and slope band prefix to the bands in the model
#Assumes that the c (collection) has the raw bands in it
def predictModel(c,model,bandNames = None):
  
  #Parse model
  intercepts = model.select('intercept_.*')
  slopes = model.select('slope_.*')
  
  #Find band names for raw data if not provided
  if bandNames == None:
    bandNames = slopes.bandNames().map(lambda bn: ee.String(bn).split('_').get(1))

  
  #Set up output band names
  predictedBandNames = bandNames.map(lambda bn :ee.String(bn).cat('_trend'))
  
  #Predict model
  def pModel(img):
    cActual = img.select(bandNames);
    out = img.select(['year']).multiply(slopes).add(img.select(['constant']).multiply(intercepts)).rename(predictedBandNames)
    return cActual.addBands(out).copyProperties(img,['system:time_start'])
  predicted = c.map(pModel)
  
  return predicted
###########################################
#Function for getting a linear fit of a time series and applying it
def getLinearFit(c,bandNames = None):
  #Find band names for raw data if not provided
  if bandNames == None:
    bandNames = ee.Image(c.first()).bandNames()
  else:
    bandNames = ee.List(bandNames)
    c = c.select(bandNames)
  
  
  #Add date and constant independents
  c = c.map(lambda img: img.addBands(ee.Image(1)))
  c = c.map(getImageLib.addDateBand)
  selectOrder = ee.List([['constant','year'],bandNames]).flatten()
  
  #Fit model
  model = c.select(selectOrder).reduce(ee.Reducer.linearRegression(2,bandNames.length())).select([0])
  
  #Convert model to image
  model = model.arrayTranspose().arrayFlatten([bandNames,['intercept','slope']])
  
  #Apply model
  predicted = predictModel(c,model,bandNames)
  
  #Return both the model and predicted
  return [model,predicted]

####################################/
# #Iterate across each time window and do a z-score and trend analysis
# #This method does not currently support date wrapping
def zAndTrendChangeDetection(allScenes,indexNames,nDays,startYear,endYear,startJulian,endJulian,\
          baselineLength = 5,baselineGap = 1,epochLength = 5,zReducer = ee.Reducer.mean(),useAnnualMedianForTrend = True,\
          exportImages = False,exportPathRoot = 'users/iwhousman/test/ChangeCollection',studyArea = None,scale = 30,crs = None,transform = None,\
          minBaselineObservationsNeeded = 10):

  #House-keeping
  allScenes = allScenes.select(indexNames)
  print(allScenes.size().getInfo())
  dummyScene = ee.Image(allScenes.first());

  outNames = map(lambda bn: bn +'_Z',indexNames)
 
  analysisStartYear = max(startYear+baselineLength+baselineGap,startYear+epochLength-1)
  
  years = ee.List.sequence(analysisStartYear,endYear,1).getInfo()
  julians = ee.List.sequence(startJulian,endJulian-nDays,nDays).getInfo()
  
  #Iterate across each year and perform analysis
  
  def processYrJd(yjd):
    yjd = ee.List(yjd)
    yr = ee.Number(yjd.get(0))
    jd = ee.Number(yjd.get(1))
    #Set up the baseline years
    blStartYear = yr.subtract(baselineLength).subtract(baselineGap)
    blEndYear = yr.subtract(1).subtract(baselineGap)

    
    #Set up the trend years
    trendStartYear = yr.subtract(epochLength).add(1)


    
      
    #Set up the julian date range
    jdStart = jd
    jdEnd = jd.add(nDays)
   
    #Get the baseline images
    blImages = allScenes.filter(ee.Filter.calendarRange(blStartYear,blEndYear,'year'))\
                            .filter(ee.Filter.calendarRange(jdStart,jdEnd))
    blImages = getImageLib.fillEmptyCollections(blImages,dummyScene);

    #Mask out where not enough observations
    blCounts = blImages.count();
    blImages = blImages.map(lambda img: img.updateMask(blCounts.gte(minBaselineObservationsNeeded)))

    
    #Get the z analysis images
    analysisImages = allScenes.filter(ee.Filter.calendarRange(yr,yr,'year'))\
                            .filter(ee.Filter.calendarRange(jdStart,jdEnd))
    analysisImages = getImageLib.fillEmptyCollections(analysisImages,dummyScene)
    
    #Get the images for the trend analysis
    trendImages = allScenes.filter(ee.Filter.calendarRange(trendStartYear,yr,'year'))\
                            .filter(ee.Filter.calendarRange(jdStart,jdEnd))
    trendImages = getImageLib.fillEmptyCollections(trendImages,dummyScene)
    
    
    #Convert to annual stack if selected
    if useAnnualMedianForTrend:
      trendImages = toAnnualMedian(trendImages,trendStartYear,yr)
   
    
    #Perform the linear trend analysis
    linearTrend = getLinearFit(trendImages,indexNames);
    linearTrendModel = ee.Image(linearTrend[0]).select(['.*_slope']).multiply(10000)
  
    #Perform the z analysis
    blMean = blImages.mean()
    blStd = blImages.reduce(ee.Reducer.stdDev())
  
    analysisImagesZ = analysisImages.map(lambda img:img.subtract(blMean).divide(blStd))\
              .reduce(zReducer).rename(outNames).multiply(10)
    
    # Set up the output
    outName = ee.String('Z_and_Trend_b').cat(ee.Number(blStartYear).int16().format('%04d')).cat(ee.String('_'))\
                                .cat(ee.Number(blEndYear).int16().format('%04d'))\
                                .cat(ee.String('_epoch')).cat(ee.Number(epochLength).format('%02d'))\
                                .cat(ee.String('_y')).cat(yr.int16().format('%04d')).cat(ee.String('_jd'))\
                                .cat(jdStart.int16().format('%03d')).cat(ee.String('_')).cat(jdEnd.int16().format('%03d'))
    

    imageStartDate =ee.Date.fromYMD(yr,1,1).advance(jdStart,'day').millis()
    
    
    out = analysisImagesZ.addBands(linearTrendModel).int16()\
          .set({'system:time_start':imageStartDate,\
                'system:time_end':ee.Date.fromYMD(yr,1,1).advance(jdEnd,'day').millis(),\
                'baselineYrs': baselineLength,\
                'baselineStartYear':blStartYear,\
                'baselineEndYear':blEndYear,\
                'epochLength':epochLength,\
                'trendStartYear':trendStartYear,\
                'year':yr,\
                'startJulian':jdStart,\
                'endJulian':jdEnd,\
                'system:index':outName\
          })
    
    # if exportImages:
    #   outName = outName.getInfo()
    #   outPath = exportPathRoot + '/' + outName
    #   getImageLib.exportToAssetWrapper(out.clip(studyArea),outName,outPath,\
    #     'mean',studyArea.bounds(),scale,crs,transform)
    # zAndTrendCollection.append(out)
    return out


  yjdList = []
  for yr in years:
    #Iterate across the julian dates
    for jd in julians:
      yjdList.append(ee.List([yr,jd]))

  

  zAndTrendCollection = ee.ImageCollection.fromImages(ee.List(yjdList).map(processYrJd))

  return zAndTrendCollection



def thresholdZAndTrend(zAndTrendCollection,zThresh,slopeThresh,startYear,endYear,negativeOrPositiveChange = None):
  if negativeOrPositiveChange == None:
    negativeOrPositiveChange = 'negative'

  if negativeOrPositiveChange == 'negative':dir = -1
  else:dir = 1

  zCollection = zAndTrendCollection.select('.*_Z')
  trendCollection = zAndTrendCollection.select('.*_slope')
  
  zChange = thresholdChange(zCollection,-zThresh,dir).select('.*_change')
  trendChange = thresholdChange(trendCollection,-slopeThresh,dir).select('.*_change')
  
  return [zChange,trendChange]
  
 


# function thresholdZAndTrendSubtle(zAndTrendCollection,zThreshLow,zThreshHigh,slopeThreshLow,slopeThreshHigh,startYear,endYear,negativeOrPositiveChange){
#   if(negativeOrPositiveChange === null || negativeOrPositiveChange === undefined){negativeOrPositiveChange = 'negative'}
#   dir;colorRamp;
#   if(negativeOrPositiveChange === 'negative'){dir = -1;colorRamp = 'FF0,F00';}
#   else{dir = 1; colorRamp = 'BBB,080';}
#   zCollection = zAndTrendCollection.select('.*_Z');
#   trendCollection = zAndTrendCollection.select('.*_slope');
  
#   zChange = thresholdSubtleChange(zCollection,-zThreshLow,-zThreshHigh,dir).select('.*_change');
#   trendChange = thresholdSubtleChange(trendCollection,-slopeThreshLow,-slopeThreshHigh,dir).select('.*_change');
  
  
  
#   Map.addLayer(zChange.max().select([0]),{'min':startYear,'max':endYear,'palette':colorRamp},'Z Most Recent Change Year '+negativeOrPositiveChange,false);
#   Map.addLayer(trendChange.max().select([0]),{'min':startYear,'max':endYear,'palette':colorRamp},'Trend Most Recent Change Year '+negativeOrPositiveChange,false);
  
# }


# function exportZAndTrend(zAndTrendCollection,dates,exportPathRoot,studyArea,scale,crs,transform){
 
# print('Exporting z and trend collection');
# i = 0;
# dates.map(function(d){
#   image = ee.Image(zAndTrendCollection.filterDate(d,d).first());
   
#   outPath = exportPathRoot + '/' + i;
#   getImageLib.exportToAssetWrapper(image,i.toString(),outPath,
#         'mean',studyArea,scale,crs,transform)
#     i++;
#   # image.id().evaluate(function(id){
#   #     outPath = exportPathRoot + '/' + id;
#   #     getImageLib.exportToAssetWrapper(image,id,outPath,
#   #       'mean',studyArea,scale,crs,transform);
#   #   });
# })
# # zAndTrendCollectionL = zAndTrendCollection.toList(100);
# #   zAndTrendCollection.size().evaluate(function(count){
# #   ee.List.sequence(0,count-1).getInfo().map(function(i){
   
# #     image = ee.Image(zAndTrendCollectionL.get(i));
    
# #     image.id().evaluate(function(id){
# #       outPath = exportPathRoot + '/' + id;
# #       getImageLib.exportToAssetWrapper(image,id,outPath,
# #         'mean',studyArea,scale,crs,transform);
# #     });
# #   });
# # }); 
# }
#####################################