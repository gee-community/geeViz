//Module imports
var getImageLib = require('users/USFS_GTAC/modules:getImagesLib.js');
///////////////////////////////////////////////////////////////////////////////

///////////////////////////////////////////////
function thresholdChange(changeCollection,changeThresh,changeDir){
  if(changeDir === undefined || changeDir === null){changeDir = 1}
  var bandNames = ee.Image(changeCollection.first()).bandNames();
  bandNames = bandNames.map(function(bn){return ee.String(bn).cat('_change')});
  var change = changeCollection.map(function(img){
    var yr = ee.Date(img.get('system:time_start')).get('year');
    var changeYr = img.multiply(changeDir).gt(changeThresh);
    var yrImage = img.where(img.mask(),yr);
    changeYr = yrImage.updateMask(changeYr).rename(bandNames).int16();
    return img.mask(ee.Image(1)).addBands(changeYr);
  });
  return change;
}

function getExistingChangeData(changeThresh,showLayers){
  if(showLayers === undefined || showLayers === null){
    showLayers = true;
  }
  if(changeThresh === undefined || changeThresh === null){
    changeThresh = 50;
  }
  var startYear = 1985;
  var endYear = 2016;
  
  
  
  // var glriEnsemble = ee.Image('projects/glri-phase3/changeMaps/ensembleOutputs/NBR_NDVI_TCBGAngle_swir1_swir2_median_LT_Ensemble');
  
  
  
  
  
  var conusChange = ee.ImageCollection('projects/glri-phase3/science-team-outputs/conus-lcms-2018')
    .filter(ee.Filter.calendarRange(startYear,endYear,'year'));
  var conusChangeOut = conusChange;
  conusChangeOut = conusChangeOut.map(function(img){
    var m = img.mask();
    var out = img.mask(ee.Image(1));
    out = out.where(m.not(),0);
    return out});

  conusChange = conusChange.map(function(img){
    var yr = ee.Date(img.get('system:time_start')).get('year');
    var change = img.gt(changeThresh);
    var conusChangeYr = ee.Image(yr).updateMask(change).rename(['change']).int16();
    return img.mask(ee.Image(1)).addBands(conusChangeYr);
  });
  if(showLayers){
  Map.addLayer(conusChange.select(['change']).max(),{'min':startYear,'max':endYear,'palette':'FF0,F00'},'CONUS LCMS Most Recent Year of Change',false);
  // Map.addLayer(conusChange.select(['probability']).max(),{'min':0,'max':50,'palette':'888,008'},'LCMSC',false);
  }
  // var glri_lcms = glriEnsemble.updateMask(glriEnsemble.select([0])).select([1]);
  // glri_lcms = glri_lcms.updateMask(glri_lcms.gte(startYear).and(glri_lcms.lte(endYear)));
  if(showLayers){
  // Map.addLayer(glri_lcms,{'min':startYear,'max':endYear,'palette':'FF0,F00'},'GLRI LCMS',false);
  }
  
  
  
  var hansen = ee.Image('UMD/hansen/global_forest_change_2016_v1_4').select(['lossyear']).add(2000).int16();
  hansen = hansen.updateMask(hansen.neq(2000).and(hansen.gte(startYear)).and(hansen.lte(endYear)));
  if(showLayers){
  Map.addLayer(hansen,{'min':startYear,'max':endYear,'palette':'FF0,F00'},'Hansen Change Year',false);
  }
  return conusChangeOut;
}
//########################################################################################################

//########################################################################################################
//##### UNPACKING LT-GEE OUTPUT STRUCTURE FUNCTIONS ##### 
//########################################################################################################

// ----- FUNCTION TO EXTRACT VERTICES FROM LT RESULTS AND STACK BANDS -----
var getLTvertStack = function(LTresult,run_params) {
  var emptyArray = [];                              // make empty array to hold another array whose length will vary depending on maxSegments parameter    
  var vertLabels = [];                              // make empty array to hold band names whose length will vary depending on maxSegments parameter 
  var iString;                                      // initialize variable to hold vertex number
  for(var i=1;i<=run_params.maxSegments+1;i++){     // loop through the maximum number of vertices in segmentation and fill empty arrays
    iString = i.toString();                         // define vertex number as string 
    vertLabels.push("vert_"+iString);               // make a band name for given vertex
    emptyArray.push(0);                             // fill in emptyArray
  }
  
  var zeros = ee.Image(ee.Array([emptyArray,        // make an image to fill holes in result 'LandTrendr' array where vertices found is not equal to maxSegments parameter plus 1
                                 emptyArray,
                                 emptyArray]));
  
  var lbls = [['yrs_','src_','fit_'], vertLabels,]; // labels for 2 dimensions of the array that will be cast to each other in the final step of creating the vertice output 

  var vmask = LTresult.arraySlice(0,3,4);           // slices out the 4th row of a 4 row x N col (N = number of years in annual stack) matrix, which identifies vertices - contains only 0s and 1s, where 1 is a vertex (referring to spectral-temporal segmentation) year and 0 is not
  
  var ltVertStack = LTresult.arrayMask(vmask)       // uses the sliced out isVert row as a mask to only include vertice in this data - after this a pixel will only contain as many "bands" are there are vertices for that pixel - min of 2 to max of 7. 
                      .arraySlice(0, 0, 3)          // ...from the vertOnly data subset slice out the vert year row, raw spectral row, and fitted spectral row
                      .addBands(zeros)              // ...adds the 3 row x 7 col 'zeros' matrix as a band to the vertOnly array - this is an intermediate step to the goal of filling in the vertOnly data so that there are 7 vertice slots represented in the data - right now there is a mix of lengths from 2 to 7
                      .toArray(1)                   // ...concatenates the 3 row x 7 col 'zeros' matrix band to the vertOnly data so that there are at least 7 vertice slots represented - in most cases there are now > 7 slots filled but those will be truncated in the next step
                      .arraySlice(1, 0, run_params.maxSegments+1) // ...before this line runs the array has 3 rows and between 9 and 14 cols depending on how many vertices were found during segmentation for a given pixel. this step truncates the cols at 7 (the max verts allowed) so we are left with a 3 row X 7 col array
                      .arrayFlatten(lbls, '');      // ...this takes the 2-d array and makes it 1-d by stacking the unique sets of rows and cols into bands. there will be 7 bands (vertices) for vertYear, followed by 7 bands (vertices) for rawVert, followed by 7 bands (vertices) for fittedVert, according to the 'lbls' list

  return ltVertStack;                               // return the stack
};





//########################################################################################################
//##### GREATEST DISTURBANCE EXTRACTION FUNCTIONS #####
//########################################################################################################

// ----- function to extract greatest disturbance based on spectral delta between vertices 
var extractDisturbance = function(lt, distDir, params, mmu) {
  // select only the vertices that represents a change
  var vertexMask = lt.arraySlice(0, 3, 4); // get the vertex - yes(1)/no(0) dimension
  var vertices = lt.arrayMask(vertexMask); // convert the 0's to masked
  
  // construct segment start and end point years and index values
  var left = vertices.arraySlice(1, 0, -1);    // slice out the vertices as the start of segments
  var right = vertices.arraySlice(1, 1, null); // slice out the vertices as the end of segments
  var startYear = left.arraySlice(0, 0, 1);    // get year dimension of LT data from the segment start vertices
  var startVal = left.arraySlice(0, 2, 3);     // get spectral index dimension of LT data from the segment start vertices
  var endYear = right.arraySlice(0, 0, 1);     // get year dimension of LT data from the segment end vertices 
  var endVal = right.arraySlice(0, 2, 3);      // get spectral index dimension of LT data from the segment end vertices
  
  var dur = endYear.subtract(startYear);       // subtract the segment start year from the segment end year to calculate the duration of segments 
  var mag = endVal.subtract(startVal);         // substract the segment start index value from the segment end index value to calculate the delta of segments 

  // concatenate segment start year, delta, duration, and starting spectral index value to an array 
  var distImg = ee.Image.cat([startYear.add(1), mag, dur, startVal.multiply(distDir)]).toArray(0); // make an image of segment attributes - multiply by the distDir parameter to re-orient the spectral index if it was flipped for segmentation - do it here so that the subtraction to calculate segment delta in the above line is consistent - add 1 to the detection year, because the vertex year is not the first year that change is detected, it is the following year
 
  // sort the segments in the disturbance attribute image delta by spectral index change delta  
  var distImgSorted = distImg.arraySort(mag.multiply(-1));                                  // flip the delta around so that the greatest delta segment is first in order

  // slice out the first (greatest) delta
  var tempDistImg = distImgSorted.arraySlice(1, 0, 1).unmask(ee.Image(ee.Array([[0],[0],[0],[0]])));                                      // get the first segment in the sorted array

  // make an image from the array of attributes for the greatest disturbance
  var finalDistImg = ee.Image.cat(tempDistImg.arraySlice(0,0,1).arrayProject([1]).arrayFlatten([['yod']]),     // slice out year of disturbance detection and re-arrange to an image band 
                                  tempDistImg.arraySlice(0,1,2).arrayProject([1]).arrayFlatten([['mag']]),     // slice out the disturbance magnitude and re-arrange to an image band 
                                  tempDistImg.arraySlice(0,2,3).arrayProject([1]).arrayFlatten([['dur']]),     // slice out the disturbance duration and re-arrange to an image band
                                  tempDistImg.arraySlice(0,3,4).arrayProject([1]).arrayFlatten([['preval']])); // slice out the pre-disturbance spectral value and re-arrange to an image band
  
  // filter out disturbances based on user settings
  var threshold = ee.Image(finalDistImg.select(['dur']))                        // get the disturbance band out to apply duration dynamic disturbance magnitude threshold 
                    .multiply((params.tree_loss20 - params.tree_loss1) / 19.0)  // ...
                    .add(params.tree_loss1)                                     //    ...interpolate the magnitude threshold over years between a 1-year mag thresh and a 20-year mag thresh
                    .lte(finalDistImg.select(['mag']))                          // ...is disturbance less then equal to the interpolated, duration dynamic disturbance magnitude threshold 
                    .and(finalDistImg.select(['mag']).gt(0))                    // and is greater than 0  
                    .and(finalDistImg.select(['preval']).gt(params.pre_val));   // and is greater than pre-disturbance spectral index value threshold
  
  // apply the filter mask
  finalDistImg = finalDistImg.mask(threshold).int16(); 
  
   // patchify the remaining disturbance pixels using a minimum mapping unit
  if(mmu > 1){
    var mmuPatches = finalDistImg.select(['yod'])           // patchify based on disturbances having the same year of detection
                            .connectedPixelCount(mmu, true) // count the number of pixel in a candidate patch
                            .gte(mmu);                      // are the the number of pixels per candidate patch greater than user-defined minimum mapping unit?
    finalDistImg = finalDistImg.updateMask(mmuPatches);     // mask the pixels/patches that are less than minimum mapping unit
  } 
  
  return finalDistImg; // return the filtered greatest disturbance attribute image
};
//////////////////////////////////////////////////////////////////////////
//Helper to multiply image
function multBands(img,distDir,by){
    var out = img.multiply(ee.Image(distDir).multiply(by));
    out  = out.copyProperties(img,['system:time_start']);
    return out;
  }
///////////////////////////////////////////////////////////////
//Function to convert an image array object to collection
function arrayToTimeSeries(tsArray,yearsArray,possibleYears,bandName){
    //Set up dummy image for handling null values
    var noDateValue = -32768;
    var dummyImage = ee.Image(noDateValue).toArray();
    
    //Ierate across years
    var tsC = possibleYears.map(function(yr){
    yr = ee.Number(yr);
    
    //Pull out given year
    var yrMask = yearsArray.eq(yr);
  
    //Mask array for that given year
    var masked = tsArray.arrayMask(yrMask);
    
    
    //Find null pixels
    var l = masked.arrayLength(0);
    
    //Fill null values and convert to regular image
    masked = masked.where(l.eq(0),dummyImage).arrayGet([-1]);
    
    //Remask nulls
    masked = masked.updateMask(masked.neq(noDateValue)).rename([bandName])      
      .set('system:time_start',ee.Date.fromYMD(yr,6,1).millis());
      
    return masked;
    
    
  });
  return ee.ImageCollection(tsC);
  }
//Function to wrap landtrendr processing
function landtrendrWrapper(processedComposites,startYear,endYear,indexName,distDir,run_params,distParams,mmu){
  // var startYear = 1984;//ee.Date(ee.Image(processedComposites.first()).get('system:time_start')).get('year').getInfo();
  // var endYear = 2017;//ee.Date(ee.Image(processedComposites.sort('system:time_start',false).first()).get('system:time_start')).get('year').getInfo();
  
  //----- RUN LANDTRENDR -----
  var ltCollection = processedComposites.select([indexName]).map(function(img){
     return multBands(img,distDir,1);
  });
  // Map.addLayer(ltCollection,{},'ltCollection',false);
  run_params.timeSeries = ltCollection;               // add LT collection to the segmentation run parameter object
  var lt = ee.Algorithms.TemporalSegmentation.LandTrendr(run_params); // run LandTrendr spectral temporal segmentation algorithm
  
  //########################################################################################################
  //##### RUN THE GREATEST DISTURBANCE EXTRACT FUCTION #####
  //########################################################################################################
  
  //assemble the disturbance extraction parameters
  
  
  // run the dist extract function
  var distImg = extractDisturbance(lt.select('LandTrendr'), distDir, distParams,mmu);
  var distImgBandNames = distImg.bandNames();
  distImgBandNames = distImgBandNames.map(function(bn){return ee.String(indexName).cat('_').cat(bn)})
  distImg = distImg.rename(distImgBandNames)
  
  
  
  //########################################################################################################
  //##### DISTURBANCE MAP DISPLAY #####
  //########################################################################################################
  
  // ----- set visualization dictionaries -----
  
  // var yodVizParms = {
  //   min: startYear+1,
  //   max: endYear,
  //   palette: ['#9400D3', '#4B0082', '#0000FF', '#00FF00', '#FFFF00', '#FF7F00', '#FF0000']
  // };
  
  // var magVizParms = {
  //   min: distParams.tree_loss1,
  //   max: 1000,
  //   palette: ['#0000FF', '#00FF00', '#FFFF00', '#FF7F00', '#FF0000']
  // };
  
  // var durVizParms = {
  //   min: 1,
  //   max: endYear-startYear,
  //   palette: ['#FF0000', '#FF7F00', '#FFFF00', '#00FF00', '#0000FF']
  // };
  
  // var preValVizParms = {
  //   min: distParams.pre_val,
  //   max: 800,
  //   palette: ['#FF0000', '#FF7F00', '#FFFF00', '#00FF00', '#0000FF']
  // };
  
  
  // ----- display the disturbance attribute maps ----- 
                                                  // clip the data to the geometry
  // Map.addLayer(distImg.select(['preval']), preValVizParms, 'LT-Pre-dist Value',false); // add pre-disturbacne spectral index value to map
  // Map.addLayer(distImg.select(['dur']), durVizParms, 'LT-Duration',false);             // add disturbance duration to map
  // Map.addLayer(distImg.select(['mag']), magVizParms, 'LT-Magnitude',false);            // add magnitude to map
  // Map.addLayer(distImg.select(['yod']), yodVizParms, 'LT-Year of Detection',false);    // add disturbance year of detection to map
  
  //Convert to collection
  var rawLT = lt.select([0]);
  var ltYear = rawLT.arraySlice(0,0,1).arrayProject([1]);
  var ltFitted = rawLT.arraySlice(0,2,3).arrayProject([1]);
  if(distDir === -1){
    ltFitted = ltFitted.multiply(-1);
  }
  
  var ca = arrayToTimeSeries(ltFitted,ltYear,ee.List.sequence(startYear,endYear),'LT_Fitted_'+indexName);
 

  //Convert to single image
  var vertStack = getLTvertStack(rawLT,run_params);
  return [lt,distImg,ca,vertStack];
  
}

//////////////////////////////////////////////////////////////////////////
//Wrapper for applying VERDET slightly more simply
//Returns annual collection of verdet slope
function verdetAnnualSlope(tsIndex,indexName,startYear,endYear){
  //Apply VERDET
  var verdet =   ee.Algorithms.TemporalSegmentation.Verdet({timeSeries: tsIndex,
                                        tolerance: 0.0001,
                                        alpha: 1/3.0}).arraySlice(0,1,null);
                                        
  var tsYear = tsIndex.map(getImageLib.addYearBand).select([1]).toArray().arraySlice(0,1,null).arrayProject([0]);
  
  
  //Find possible years to convert back to collection with
  var possibleYears = ee.List.sequence(startYear+1,endYear);
  var verdetC = arrayToTimeSeries(verdet,tsYear,possibleYears,'VERDET_fitted_'+indexName+'_slope');
 
  
  return verdetC;
}
//////////////////////////////////////////////////////////////////////////
//Wrapper for applying EWMACD slightly more simply
function getEWMA(lsIndex,trainingStartYear,trainingEndYear, harmonicCount){
  if(harmonicCount === null || harmonicCount === undefined){harmonicCount = 2}
  
  
  //Run EWMACD 
  var ewmacd = ee.Algorithms.TemporalSegmentation.Ewmacd({
    timeSeries: lsIndex, 
    vegetationThreshold: -1, 
    trainingStartYear: trainingStartYear, 
    trainingEndYear: trainingEndYear, 
    harmonicCount: 2
  });
  
  //Extract the ewmac values
  var ewma = ewmacd.select(['ewma']);
  return ewma;
}

//Function for converting EWMA values to annual collection
function annualizeEWMA(ewma,indexName,lsYear,startYear,endYear,annualReducer,remove2012){
  //Fill null parameters
  if(annualReducer === null || annualReducer === undefined){annualReducer = ee.Reducer.min()}
  if(remove2012 === null || remove2012 === undefined){remove2012 = true}
  
   //Find the years to annualize with
  var years = ee.List.sequence(startYear,endYear);
  
  //Find if 2012 needs replaced
  var replace2012 = ee.Number(ee.List([years.indexOf(2011),years.indexOf(2012),years.indexOf(2013)]).reduce(ee.Reducer.min())).neq(-1).getInfo();
  print('2012 needs replaced:',replace2012);
  
  
  //Remove 2012 if in list and set to true
  if(remove2012){years = years.removeAll([2012])}
  
  
  
  
  //Annualize
  //Set up dummy image for handling null values
  var noDateValue = -32768;
  var dummyImage = ee.Image(noDateValue).toArray();
    
  
  var annualEWMA = years.map(function(yr){
    yr = ee.Number(yr);
    var yrMask = lsYear.int16().eq(yr);
    var ewmacdYr = ewma.arrayMask(yrMask);
    var ewmacdYearYr = lsYear.arrayMask(yrMask);
    var ewmacdYrSorted = ewmacdYr.arraySort(ewmacdYr);
    var ewmacdYearYrSorted= ewmacdYearYr.arraySort(ewmacdYr);
    
    var yrData = ewmacdYrSorted.arrayCat(ewmacdYearYrSorted,1);
    var yrReduced = ewmacdYrSorted.arrayReduce(annualReducer,[0]);
   
    
    //Find null pixels
    var l = yrReduced.arrayLength(0);
    
    //Fill null values and convert to regular image
    yrReduced = yrReduced.where(l.eq(0),dummyImage).arrayGet([-1]);
    
    //Remask nulls
    yrReduced = yrReduced.updateMask(yrReduced.neq(noDateValue)).rename(['EWMA_'+indexName])      
      .set('system:time_start',ee.Date.fromYMD(yr,6,1).millis()).int16();
      
   
    return yrReduced;
  });
  annualEWMA = ee.ImageCollection.fromImages(annualEWMA);
  // print(remove2012,replace2012 ==1)
  if(remove2012 && replace2012 ==1){
    print('Replacing EWMA 2012 with mean of 2011 and 2013');
    var value2011 = ee.Image(annualEWMA.filter(ee.Filter.calendarRange(2011,2011,'year')).first());
    var value2013 = ee.Image(annualEWMA.filter(ee.Filter.calendarRange(2013,2013,'year')).first());
    var value2012 = value2013.add(value2011);
    value2012 = value2012.divide(2).rename(['EWMA_'+indexName])
    .set('system:time_start',ee.Date.fromYMD(2012,6,1).millis()).int16();
    
    annualEWMA = ee.ImageCollection(ee.FeatureCollection([annualEWMA,ee.ImageCollection([value2012])]).flatten()).sort('system:time_start');
  }
  return annualEWMA;
}
//
function runEWMACD(lsIndex,indexName,startYear,endYear,trainingStartYear,trainingEndYear, harmonicCount,annualReducer,remove2012){
  // var bandName = ee.String(ee.Image(lsIndex.first()).bandNames().get(0));
 
  var ewma = getEWMA(lsIndex,trainingStartYear,trainingEndYear, harmonicCount);
  
  //Get dates for later reference
  var lsYear = lsIndex.map(getImageLib.addDateBand).select(['year']).toArray().arrayProject([0]);

  
  var annualEWMA = annualizeEWMA(ewma,indexName,lsYear,startYear,endYear,annualReducer,remove2012);
  
  return [ewma.arrayCat(lsYear,1),annualEWMA];
}
//////////////////////////////////////////////////////////////////////////
//Function to find the pairwise difference of a time series
//Assumes one image per year
function pairwiseSlope(c){
    c = c.sort('system:time_start');
    
    var bandNames = ee.Image(c.first()).bandNames();
    // bandNames = bandNames.map(function(bn){return ee.String(bn).cat('_slope')});
    
    var years = c.toList(10000).map(function(i){i = ee.Image(i);return ee.Date(i.get('system:time_start')).get('year')});
    
    var yearsLeft = years.slice(0,-1);
    var yearsRight = years.slice(1,null);
    var yearPairs = yearsLeft.zip(yearsRight);
    
    var slopeCollection = yearPairs.map(function(yp){
      yp = ee.List(yp);
      var yl = ee.Number(yp.get(0));
      var yr = ee.Number(yp.get(1));
      var yd = yr.subtract(yl);
      var l = ee.Image(c.filter(ee.Filter.calendarRange(yl,yl,'year')).first()).add(0.000001);
      var r = ee.Image(c.filter(ee.Filter.calendarRange(yr,yr,'year')).first());
      
      var slope = (r.subtract(l)).rename(bandNames);
      slope = slope.set('system:time_start',ee.Date.fromYMD(yr,6,1).millis());
      return slope;
    });
    return ee.ImageCollection.fromImages(slopeCollection);
  }
  
//Function for applying linear fit model
//Assumes the model has a intercept and slope band prefix to the bands in the model
//Assumes that the c (collection) has the raw bands in it
function predictModel(c,model,bandNames){
  
  //Parse model
  var intercepts = model.select('intercept_.*');
  var slopes = model.select('slope_.*');
  
  //Find band names for raw data if not provided
  if(bandNames === null || bandNames === undefined){
    bandNames = slopes.bandNames().map(function(bn){return ee.String(bn).split('_').get(1)});
  }
  
  //Set up output band names
  var predictedBandNames = bandNames.map(function(bn){return ee.String(bn).cat('_trend')});
  
  //Predict model
  var predicted = c.map(function(img){
    var cActual = img.select(bandNames);
    var out = img.select(['year']).multiply(slopes).add(img.select(['constant']).multiply(intercepts)).rename(predictedBandNames);
    return cActual.addBands(out).copyProperties(img,['system:time_start']);
  });
  
  return predicted;
}
//////////////////////
//Function for getting a linear fit of a time series and applying it
function getLinearFit(c,bandNames){
  //Find band names for raw data if not provided
  if(bandNames === null || bandNames === undefined){
    bandNames = ee.Image(c.first()).bandNames();
  }
  else{
    bandNames = ee.List(bandNames);
    c = c.select(bandNames);
  }
  
  //Add date and constant independents
  c = c.map(function(img){return img.addBands(ee.Image(1))});
  c = c.map(getImageLib.addDateBand);
  var selectOrder = ee.List([['constant','year'],bandNames]).flatten();
  
  //Fit model
  var model = c.select(selectOrder).reduce(ee.Reducer.linearRegression(2,bandNames.length())).select([0]);
  
  //Convert model to image
  model = model.arrayTranspose().arrayFlatten([bandNames,['intercept','slope']]);
  
  //Apply model
  var predicted = predictModel(c,model,bandNames);
  
  //Return both the model and predicted
  return [model,predicted];
}
//////////////////////////////////////////////////////////////////////////
exports.extractDisturbance = extractDisturbance;
exports.landtrendrWrapper = landtrendrWrapper;
exports.multBands = multBands;

exports.getExistingChangeData = getExistingChangeData;

exports.verdetAnnualSlope  = verdetAnnualSlope;
exports.annualizeEWMA = annualizeEWMA;
exports.getEWMA = getEWMA;
exports.runEWMACD = runEWMACD;

exports.pairwiseSlope = pairwiseSlope;
exports.thresholdChange = thresholdChange;

exports.predictModel = predictModel;
exports.getLinearFit = getLinearFit;