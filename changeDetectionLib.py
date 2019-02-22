#! /usr/bin/env python
#--------------------------------------------------------------------------
#           CHANGEDETECTIONLIB.PY
#--------------------------------------------------------------------------
# Adapted from changeDetectionLib.js
# I have only been converting functions as I use them. Unconverted functions are included at the bottom of this file.

import sys, ee
sys.path.append('C:\Users\leahcampbell\home\scripts\gee-modules')#'\\166.2.126.25\GTAC_Apps\GEE\modules')
import getImagesLib as getImageLib
import math
ee.Initialize()

#-------------------------------------------------------------------------
#             Image and array manipulation
#------------------------------------------------------------------------
#Helper to multiply image
def multBands(img,distDir,by):
  out = img.multiply(ee.Image(distDir).multiply(by))
  out  = ee.Image(out.copyProperties(img,['system:time_start']).copyProperties(img))
  return out

def addToImage(img,howMuch):
  out = img.add(ee.Image(howMuch))
  out  = ee.Image(out.copyProperties(img,['system:time_start']).copyProperties(img))
  return out

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
    longTermThreshold = finalDistImg.select(['mag']).gte(params.tree_loss20).And(longTermDisturbance)
    threshold = finalDistImg.select(['mag']).gte(params.tree_loss1)

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
    print('Applying mmu:'+mmu+' to LANDTRENDR heuristic outputs')
    
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
  
#--------------------------------------------------------------------------
#                 VERDET
#--------------------------------------------------------------------------
#Wrapper for applying VERDET slightly more simply
#Returns annual collection of verdet slope
def verdetAnnualSlope(tsIndex,indexName,startYear,endYear):
  #Apply VERDET
  verdet =   ee.Algorithms.TemporalSegmentation.Verdet({'timeSeries': tsIndex,
                                        'tolerance': 0.0001,
                                        'alpha': 1/3.0}).arraySlice(0,1,null)
  print('indexName: '+indexName)
  #Map.addLayer(verdet,{},'verdet '+indexName)
  tsYear = tsIndex.map(getImageLib.addYearBand).select([1]).toArray().arraySlice(0,1,null).arrayProject([0])
  
  #Find possible years to convert back to collection with
  possibleYears = ee.List.sequence(startYear+1,endYear)
  verdetC = arrayToTimeSeries(verdet,tsYear,possibleYears,'VERDET_fitted_'+indexName+'_slope')
  
  return verdetC

#--------------------------------------------------------------------------
#          UNCONVERTED JAVASCRIPT FUNCTIONS BELOW HERE
#--------------------------------------------------------------------------
'''
#######################/
function thresholdChange(changeCollection,changeThresh,changeDir){
  if(changeDir === undefined || changeDir === null){changeDir = 1}
  bandNames = ee.Image(changeCollection.first()).bandNames()
  bandNames = bandNames.map(function(bn){return ee.String(bn).cat('_change')})
  change = changeCollection.map(function(img){
    yr = ee.Date(img.get('system:time_start')).get('year')
    changeYr = img.multiply(changeDir).gt(changeThresh)
    yrImage = img.where(img.mask(),yr)
    changeYr = yrImage.updateMask(changeYr).rename(bandNames).int16()
    return img.mask(ee.Image(1)).addBands(changeYr)
  })
  return change
}
function thresholdSubtleChange(changeCollection,changeThreshLow,changeThreshHigh,changeDir){
  if(changeDir === undefined || changeDir === null){changeDir = 1}
  bandNames = ee.Image(changeCollection.first()).bandNames()
  bandNames = bandNames.map(function(bn){return ee.String(bn).cat('_change')})
  change = changeCollection.map(function(img){
    yr = ee.Date(img.get('system:time_start')).get('year')
    changeYr = img.multiply(changeDir).gt(changeThreshLow).and(img.multiply(changeDir).lt(changeThreshHigh))
    yrImage = img.where(img.mask(),yr)
    changeYr = yrImage.updateMask(changeYr).rename(bandNames).int16()
    return img.mask(ee.Image(1)).addBands(changeYr)
  })
  return change
}

function getExistingChangeData(changeThresh,showLayers){
  if(showLayers === undefined || showLayers === null){
    showLayers = true
  }
  if(changeThresh === undefined || changeThresh === null){
    changeThresh = 50
  }
  startYear = 1985
  endYear = 2016
  
  
  
  # glriEnsemble = ee.Image('projects/glri-phase3/changeMaps/ensembleOutputs/NBR_NDVI_TCBGAngle_swir1_swir2_median_LT_Ensemble')
  
  
  
  
  
 
  # if(showLayers){
  # Map.addLayer(conusChange.select(['change']).max(),{'min':startYear,'max':endYear,'palette':'FF0,F00'},'CONUS LCMS Most Recent Year of Change',false)
  # Map.addLayer(conusChange.select(['probability']).max(),{'min':0,'max':50,'palette':'888,008'},'LCMSC',false)
  # }
  # glri_lcms = glriEnsemble.updateMask(glriEnsemble.select([0])).select([1])
  # glri_lcms = glri_lcms.updateMask(glri_lcms.gte(startYear).and(glri_lcms.lte(endYear)))
  # if(showLayers){
  # Map.addLayer(glri_lcms,{'min':startYear,'max':endYear,'palette':'FF0,F00'},'GLRI LCMS',false)
  # }
  
  
  
  hansen = ee.Image('UMD/hansen/global_forest_change_2016_v1_4').select(['lossyear']).add(2000).int16()
  hansen = hansen.updateMask(hansen.neq(2000).and(hansen.gte(startYear)).and(hansen.lte(endYear)))
  if(showLayers){
  Map.addLayer(hansen,{'min':startYear,'max':endYear,'palette':'FF0,F00'},'Hansen Change Year',false)
  }
  # return conusChangeOut
}



#####################################
#Wrapper for applying EWMACD slightly more simply
function getEWMA(lsIndex,trainingStartYear,trainingEndYear, harmonicCount){
  if(harmonicCount === null || harmonicCount === undefined){harmonicCount = 1}
  
  
  #Run EWMACD 
  ewmacd = ee.Algorithms.TemporalSegmentation.Ewmacd({
    timeSeries: lsIndex, 
    vegetationThreshold: -1, 
    trainingStartYear: trainingStartYear, 
    trainingEndYear: trainingEndYear, 
    harmonicCount: harmonicCount
  })
  
  #Extract the ewmac values
  ewma = ewmacd.select(['ewma'])
  return ewma
}

#Function for converting EWMA values to annual collection
function annualizeEWMA(ewma,indexName,lsYear,startYear,endYear,annualReducer,remove2012){
  #Fill null parameters
  if(annualReducer === null || annualReducer === undefined){annualReducer = ee.Reducer.min()}
  if(remove2012 === null || remove2012 === undefined){remove2012 = true}
  
   #Find the years to annualize with
  years = ee.List.sequence(startYear,endYear)
  
  #Find if 2012 needs replaced
  replace2012 = ee.Number(ee.List([years.indexOf(2011),years.indexOf(2012),years.indexOf(2013)]).reduce(ee.Reducer.min())).neq(-1).getInfo()
  print('2012 needs replaced:',replace2012)
  
  
  #Remove 2012 if in list and set to true
  if(remove2012){years = years.removeAll([2012])}
  
  
  
  
  #Annualize
  #Set up dummy image for handling null values
  noDateValue = -32768;
  dummyImage = ee.Image(noDateValue).toArray();
    
  
  annualEWMA = years.map(function(yr){
    yr = ee.Number(yr);
    yrMask = lsYear.int16().eq(yr);
    ewmacdYr = ewma.arrayMask(yrMask);
    ewmacdYearYr = lsYear.arrayMask(yrMask);
    ewmacdYrSorted = ewmacdYr.arraySort(ewmacdYr);
    ewmacdYearYrSorted= ewmacdYearYr.arraySort(ewmacdYr);
    
    yrData = ewmacdYrSorted.arrayCat(ewmacdYearYrSorted,1);
    yrReduced = ewmacdYrSorted.arrayReduce(annualReducer,[0]);
   
    
    #Find null pixels
    l = yrReduced.arrayLength(0);
    
    #Fill null values and convert to regular image
    yrReduced = yrReduced.where(l.eq(0),dummyImage).arrayGet([-1]);
    
    #Remask nulls
    yrReduced = yrReduced.updateMask(yrReduced.neq(noDateValue)).rename(['EWMA_'+indexName])      
      .set('system:time_start',ee.Date.fromYMD(yr,6,1).millis()).int16();
      
   
    return yrReduced;
  });
  annualEWMA = ee.ImageCollection.fromImages(annualEWMA);
  # print(remove2012,replace2012 ==1)
  if(remove2012 && replace2012 ==1){
    print('Replacing EWMA 2012 with mean of 2011 and 2013');
    value2011 = ee.Image(annualEWMA.filter(ee.Filter.calendarRange(2011,2011,'year')).first());
    value2013 = ee.Image(annualEWMA.filter(ee.Filter.calendarRange(2013,2013,'year')).first());
    value2012 = value2013.add(value2011);
    value2012 = value2012.divide(2).rename(['EWMA_'+indexName])
    .set('system:time_start',ee.Date.fromYMD(2012,6,1).millis()).int16();
    
    annualEWMA = ee.ImageCollection(ee.FeatureCollection([annualEWMA,ee.ImageCollection([value2012])]).flatten()).sort('system:time_start');
  }
  return annualEWMA;
}
#
function runEWMACD(lsIndex,indexName,startYear,endYear,trainingStartYear,trainingEndYear, harmonicCount,annualReducer,remove2012){
  # bandName = ee.String(ee.Image(lsIndex.first()).bandNames().get(0));
 
  ewma = getEWMA(lsIndex,trainingStartYear,trainingEndYear, harmonicCount);
  
  #Get dates for later reference
  lsYear = lsIndex.map(function(img){return getImageLib.addDateBand(img,true)}).select(['year']).toArray().arrayProject([0]);

  
  annualEWMA = annualizeEWMA(ewma,indexName,lsYear,startYear,endYear,annualReducer,remove2012);
  
  return [ewma.arrayCat(lsYear,1),annualEWMA];
}
#####################################
#Function to find the pairwise difference of a time series
#Assumes one image per year
function pairwiseSlope(c){
    c = c.sort('system:time_start');
    
    bandNames = ee.Image(c.first()).bandNames();
    # bandNames = bandNames.map(function(bn){return ee.String(bn).cat('_slope')});
    
    years = c.toList(10000).map(function(i){i = ee.Image(i);return ee.Date(i.get('system:time_start')).get('year')});
    
    yearsLeft = years.slice(0,-1);
    yearsRight = years.slice(1,null);
    yearPairs = yearsLeft.zip(yearsRight);
    
    slopeCollection = yearPairs.map(function(yp){
      yp = ee.List(yp);
      yl = ee.Number(yp.get(0));
      yr = ee.Number(yp.get(1));
      yd = yr.subtract(yl);
      l = ee.Image(c.filter(ee.Filter.calendarRange(yl,yl,'year')).first()).add(0.000001);
      r = ee.Image(c.filter(ee.Filter.calendarRange(yr,yr,'year')).first());
      
      slope = (r.subtract(l)).rename(bandNames);
      slope = slope.set('system:time_start',ee.Date.fromYMD(yr,6,1).millis());
      return slope;
    });
    return ee.ImageCollection.fromImages(slopeCollection);
  }

##########################/
#Function for converting collection into annual median collection
#Does not support date wrapping across the new year (e.g. Nov- April window is a no go)
function toAnnualMedian(images,startYear,endYear){
      dummyImmage = ee.Image(images.first());
      out = ee.List.sequence(startYear,endYear).map(function(yr){
        imagesT = images.filter(ee.Filter.calendarRange(yr,yr,'year'));
        imagesT = getImageLib.fillEmptyCollections(imagesT,dummyImmage);
        return imagesT.median().set('system:time_start',ee.Date.fromYMD(yr,6,1));
      });
      return ee.ImageCollection.fromImages(out);
    }
##########################
#Function for applying linear fit model
#Assumes the model has a intercept and slope band prefix to the bands in the model
#Assumes that the c (collection) has the raw bands in it
function predictModel(c,model,bandNames){
  
  #Parse model
  intercepts = model.select('intercept_.*');
  slopes = model.select('slope_.*');
  
  #Find band names for raw data if not provided
  if(bandNames === null || bandNames === undefined){
    bandNames = slopes.bandNames().map(function(bn){return ee.String(bn).split('_').get(1)});
  }
  
  #Set up output band names
  predictedBandNames = bandNames.map(function(bn){return ee.String(bn).cat('_trend')});
  
  #Predict model
  predicted = c.map(function(img){
    cActual = img.select(bandNames);
    out = img.select(['year']).multiply(slopes).add(img.select(['constant']).multiply(intercepts)).rename(predictedBandNames);
    return cActual.addBands(out).copyProperties(img,['system:time_start']);
  });
  
  return predicted;
}
###########
#Function for getting a linear fit of a time series and applying it
function getLinearFit(c,bandNames){
  #Find band names for raw data if not provided
  if(bandNames === null || bandNames === undefined){
    bandNames = ee.Image(c.first()).bandNames();
  }
  else{
    bandNames = ee.List(bandNames);
    c = c.select(bandNames);
  }
  
  #Add date and constant independents
  c = c.map(function(img){return img.addBands(ee.Image(1))});
  c = c.map(getImageLib.addDateBand);
  selectOrder = ee.List([['constant','year'],bandNames]).flatten();
  
  #Fit model
  model = c.select(selectOrder).reduce(ee.Reducer.linearRegression(2,bandNames.length())).select([0]);
  
  #Convert model to image
  model = model.arrayTranspose().arrayFlatten([bandNames,['intercept','slope']]);
  
  #Apply model
  predicted = predictModel(c,model,bandNames);
  
  #Return both the model and predicted
  return [model,predicted];
}
####################################/
#Iterate across each time window and do a z-score and trend analysis
#This method does not currently support date wrapping
function zAndTrendChangeDetection(allScenes,indexNames,nDays,startYear,endYear,startJulian,endJulian,
          baselineLength,baselineGap,epochLength,zReducer,useAnnualMedianForTrend,
          exportImages,exportPathRoot,studyArea,scale,crs,transform,
          minBaselineObservationsNeeded){
  if(minBaselineObservationsNeeded === null || minBaselineObservationsNeeded === undefined){
    minBaselineObservationsNeeded = 30;
  }
  #House-keeping
  allScenes = allScenes.select(indexNames);
  dummyScene = ee.Image(allScenes.first());
  outNames = indexNames.map(function(bn){return ee.String(bn).cat('_Z')});
  analysisStartYear = Math.max(startYear+baselineLength+baselineGap,startYear+epochLength-1);
  
  years = ee.List.sequence(analysisStartYear,endYear,1).getInfo();
  julians = ee.List.sequence(startJulian,endJulian-nDays,nDays).getInfo();
  
  #Iterate across each year and perform analysis
  zAndTrendCollection = years.map(function(yr){
    yr = ee.Number(yr);
    
    #Set up the baseline years
    blStartYear = yr.subtract(baselineLength).subtract(baselineGap);
    blEndYear = yr.subtract(1).subtract(baselineGap);
    
    #Set up the trend years
    trendStartYear = yr.subtract(epochLength).add(1);
    
    #Iterate across the julian dates
    return ee.FeatureCollection(julians.map(function(jd){
      
      jd = ee.Number(jd);
      
      #Set up the julian date range
      jdStart = jd;
      jdEnd = jd.add(nDays);
     
      #Get the baseline images
      blImages = allScenes.filter(ee.Filter.calendarRange(blStartYear,blEndYear,'year'))
                              .filter(ee.Filter.calendarRange(jdStart,jdEnd));
      blImages = getImageLib.fillEmptyCollections(blImages,dummyScene);
      
      #Mask out where not enough observations
      blCounts = blImages.count();
      blImages = blImages.map(function(img){return img.updateMask(blCounts.gte(minBaselineObservationsNeeded))});
      
      #Get the z analysis images
      analysisImages = allScenes.filter(ee.Filter.calendarRange(yr,yr,'year'))
                              .filter(ee.Filter.calendarRange(jdStart,jdEnd)); 
      analysisImages = getImageLib.fillEmptyCollections(analysisImages,dummyScene);
      
      #Get the images for the trend analysis
      trendImages = allScenes.filter(ee.Filter.calendarRange(trendStartYear,yr,'year'))
                              .filter(ee.Filter.calendarRange(jdStart,jdEnd));
      trendImages = getImageLib.fillEmptyCollections(trendImages,dummyScene);
      
      
      #Convert to annual stack if selected
      if(useAnnualMedianForTrend){
        trendImages = toAnnualMedian(trendImages,trendStartYear,yr);
      }
      
      #Perform the linear trend analysis
      linearTrend = getLinearFit(trendImages,indexNames);
      linearTrendModel = ee.Image(linearTrend[0]).select(['.*_slope']).multiply(10000);
      
      #Perform the z analysis
      blMean = blImages.mean();
      blStd = blImages.reduce(ee.Reducer.stdDev());
    
      analysisImagesZ = analysisImages.map(function(img){
        return (img.subtract(blMean)).divide(blStd);
      }).reduce(zReducer).rename(outNames).multiply(10);
      
      # Set up the output
      outName = ee.String('Z_and_Trend_b').cat(ee.String(blStartYear.int16())).cat(ee.String('_'))
                                  .cat(ee.String(blEndYear.int16())).cat(ee.String('_epoch')).cat(ee.String(ee.Number(epochLength)))
                                  .cat(ee.String('_y')).cat(ee.String(yr.int16())).cat(ee.String('_jd'))
                                  .cat(ee.String(jdStart.int16())).cat(ee.String('_')).cat(ee.String(jdEnd.int16()));
      imageStartDate =ee.Date.fromYMD(yr,1,1).advance(jdStart,'day').millis();
      
      
      out = analysisImagesZ.addBands(linearTrendModel).int16()
            .set({'system:time_start':imageStartDate,
                  'system:time_end':ee.Date.fromYMD(yr,1,1).advance(jdEnd,'day').millis(),
                  'baselineYrs': baselineLength,
                  'baselineStartYear':blStartYear,
                  'baselineEndYear':blEndYear,
                  'epochLength':epochLength,
                  'trendStartYear':trendStartYear,
                  'year':yr,
                  'startJulian':jdStart,
                  'endJulian':jdEnd,
                  'system:index':outName
            });
        
      if(exportImages){
        outName = outName.getInfo();
        outPath = exportPathRoot + '/' + outName;
          getImageLib.exportToAssetWrapper(out.clip(studyArea),outName,outPath,
          'mean',studyArea.bounds(),scale,crs,transform);
      }
      return out;
      }));
    });
    zAndTrendCollection = ee.ImageCollection(ee.FeatureCollection(zAndTrendCollection).flatten());
    
    return zAndTrendCollection;
}


function thresholdZAndTrend(zAndTrendCollection,zThresh,slopeThresh,startYear,endYear,negativeOrPositiveChange){
  if(negativeOrPositiveChange === null || negativeOrPositiveChange === undefined){negativeOrPositiveChange = 'negative'}
  dir;
  if(negativeOrPositiveChange === 'negative'){dir = -1}
  else{dir = 1};
  zCollection = zAndTrendCollection.select('.*_Z');
  trendCollection = zAndTrendCollection.select('.*_slope');
  
  zChange = thresholdChange(zCollection,-zThresh,dir).select('.*_change');
  trendChange = thresholdChange(trendCollection,-slopeThresh,dir).select('.*_change');
  
  
  Map.addLayer(zChange.max().select([0]),{'min':startYear,'max':endYear,'palette':'FF0,F00'},'Z Most Recent Change Year '+negativeOrPositiveChange,false);
  Map.addLayer(trendChange.max().select([0]),{'min':startYear,'max':endYear,'palette':'FF0,F00'},'Trend Most Recent Change Year '+negativeOrPositiveChange,false);
  
}

function thresholdZAndTrendSubtle(zAndTrendCollection,zThreshLow,zThreshHigh,slopeThreshLow,slopeThreshHigh,startYear,endYear,negativeOrPositiveChange){
  if(negativeOrPositiveChange === null || negativeOrPositiveChange === undefined){negativeOrPositiveChange = 'negative'}
  dir;colorRamp;
  if(negativeOrPositiveChange === 'negative'){dir = -1;colorRamp = 'FF0,F00';}
  else{dir = 1; colorRamp = 'BBB,080';}
  zCollection = zAndTrendCollection.select('.*_Z');
  trendCollection = zAndTrendCollection.select('.*_slope');
  
  zChange = thresholdSubtleChange(zCollection,-zThreshLow,-zThreshHigh,dir).select('.*_change');
  trendChange = thresholdSubtleChange(trendCollection,-slopeThreshLow,-slopeThreshHigh,dir).select('.*_change');
  
  
  
  Map.addLayer(zChange.max().select([0]),{'min':startYear,'max':endYear,'palette':colorRamp},'Z Most Recent Change Year '+negativeOrPositiveChange,false);
  Map.addLayer(trendChange.max().select([0]),{'min':startYear,'max':endYear,'palette':colorRamp},'Trend Most Recent Change Year '+negativeOrPositiveChange,false);
  
}
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
exports.extractDisturbance = extractDisturbance;
exports.landtrendrWrapper = landtrendrWrapper;
exports.multBands = multBands;
exports.addToImage = addToImage;
exports.getExistingChangeData = getExistingChangeData;

exports.verdetAnnualSlope  = verdetAnnualSlope;
exports.annualizeEWMA = annualizeEWMA;
exports.getEWMA = getEWMA;
exports.runEWMACD = runEWMACD;

exports.pairwiseSlope = pairwiseSlope;
exports.thresholdChange = thresholdChange;

exports.predictModel = predictModel;
exports.getLinearFit = getLinearFit;
exports.toAnnualMedian = toAnnualMedian;

exports.zAndTrendChangeDetection = zAndTrendChangeDetection;
exports.thresholdZAndTrend = thresholdZAndTrend;
exports.thresholdZAndTrendSubtle = thresholdZAndTrendSubtle;
exports.thresholdSubtleChange = thresholdSubtleChange;
'''