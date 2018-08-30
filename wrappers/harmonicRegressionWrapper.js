/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #d63000 */ee.Geometry.Polygon(
        [[[-78.51688457474665, 37.01424484164281],
          [-78.57902599320369, 37.006020245688354],
          [-78.56529308304744, 36.97777569372612],
          [-78.48838878617244, 36.97558150316421]]]),
    plotPoint = /* color: #98ff00 */ee.Geometry.Point([-78.53164745316462, 36.99093950844145]);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
//Module imports
var getImageLib = require('users/USFS_GTAC/modules:getImagesLib.js');
var dLib = require('users/USFS_GTAC/modules:changeDetectionLib.js');
///////////////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
// Define user parameters:

// 1. Specify study area: Study area
// Can specify a country, provide a fusion table  or asset table (must add 
// .geometry() after it), or draw a polygon and make studyArea = drawnPolygon
var studyArea = geometry;//paramDict[studyAreaName][3];

// 2. Update the startJulian and endJulian variables to indicate your seasonal 
// constraints. This supports wrapping for tropics and southern hemisphere.
// startJulian: Starting Julian date 
// endJulian: Ending Julian date
var startJulian = 1;
var endJulian = 365; 

// 3. Specify start and end years for all analyses
// More than a 3 year span should be provided for time series methods to work 
// well. If using Fmask as the cloud/cloud shadow masking method, this does not 
// matter
var startYear = 1984;
var endYear = 1990;

// 4. Specify an annual buffer to include imagery from the same season 
// timeframe from the prior and following year. timeBuffer = 1 will result 
// in a 3 year moving window
var timebuffer = 3;

// 5. Specify the weights to be used for the moving window created by timeBuffer
//For example- if timeBuffer is 1, that is a 3 year moving window
//If the center year is 2000, then the years are 1999,2000, and 2001
//In order to overweight the center year, you could specify the weights as
//[1,5,1] which would duplicate the center year 5 times and increase its weight for
//the compositing method
var weights = [1,5,1];



// 6. Choose medoid or median compositing method. 
// Median tends to be smoother, while medoid retains 
// single date of observation across all bands
// If not exporting indices with composites to save space, medoid should be used
var compositingMethod = 'medoid';

// 7. Choose Top of Atmospheric (TOA) or Surface Reflectance (SR) 
// Specify TOA or SR
// Current implementation does not support Fmask for TOA
var toaOrSR = 'SR';

// 8. Choose whether to include Landat 7
// Generally only included when data are limited
var includeSLCOffL7 = false;

//9. Whether to defringe L5
//Landsat 5 data has fringes on the edges that can introduce anomalies into 
//the analysis.  This method removes them, but is somewhat computationally expensive
var defringeL5 = false;

// 10. Choose cloud/cloud shadow masking method
// Choices are a series of booleans for cloudScore, TDOM, and elements of Fmask
//Fmask masking options will run fastest since they're precomputed
//CloudScore runs pretty quickly, but does look at the time series to find areas that 
//always have a high cloudScore to reduce comission errors- this takes some time
//and needs a longer time series (>5 years or so)
//TDOM also looks at the time series and will need a longer time series
var applyCloudScore = false;
var applyFmaskCloudMask = true;

var applyTDOM = false;
var applyFmaskCloudShadowMask = true;

var applyFmaskSnowMask = true;

// 11. Cloud and cloud shadow masking parameters.
// If cloudScoreTDOM is chosen
// cloudScoreThresh: If using the cloudScoreTDOMShift method-Threshold for cloud 
//    masking (lower number masks more clouds.  Between 10 and 30 generally 
//    works best)
var cloudScoreThresh = 20;

// Percentile of cloud score to pull from time series to represent a minimum for 
// the cloud score over time for a given pixel. Reduces comission errors over 
// cool bright surfaces. Generally between 5 and 10 works well. 0 generally is a
// bit noisy
var cloudScorePctl = 10; 

// zScoreThresh: Threshold for cloud shadow masking- lower number masks out 
//    less. Between -0.8 and -1.2 generally works well
var zScoreThresh = -1;

// shadowSumThresh: Sum of IR bands to include as shadows within TDOM and the 
//    shadow shift method (lower number masks out less)
var shadowSumThresh = 0.35;

// contractPixels: The radius of the number of pixels to contract (negative 
//    buffer) clouds and cloud shadows by. Intended to eliminate smaller cloud 
//    patches that are likely errors
// (1.5 results in a -1 pixel buffer)(0.5 results in a -0 pixel buffer)
// (1.5 or 2.5 generally is sufficient)
var contractPixels = 1.5; 

// dilatePixels: The radius of the number of pixels to dilate (buffer) clouds 
//    and cloud shadows by. Intended to include edges of clouds/cloud shadows 
//    that are often missed
// (1.5 results in a 1 pixel buffer)(0.5 results in a 0 pixel buffer)
// (2.5 or 3.5 generally is sufficient)
var dilatePixels = 2.5;

// 12. correctIllumination: Choose if you want to correct the illumination using
// Sun-Canopy-Sensor+C correction. Additionally, choose the scale at which the
// correction is calculated in meters.
var correctIllumination = false;
var correctScale = 250;//Choose a scale to reduce on- 250 generally works well

//13. Export params
//Whether to export composites
var exportComposites = false;

//Set up Names for the export
var outputName = 'EWMA';

//Provide location composites will be exported to
//This should be an asset folder, or more ideally, an asset imageCollection
var exportPathRoot = 'users/iwhousman/test/ChangeCollection';

// var exportPathRoot = 'projects/USFS/LCMS-NFS/R4/BT/Base-Learners/Base-Learners-Collection';
//CRS- must be provided.  
//Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
//WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
var crs = 'EPSG:5070';

//Specify transform if scale is null and snapping to known grid is needed
var transform = [30,0,-2361915.0,0,-30,3177735.0];

//Specify scale if transform is null
var scale = null;
////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
var allScenes = getImageLib.getProcessedLandsatScenes(studyArea,startYear,endYear,startJulian,endJulian,
  
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
  applyFmaskCloudShadowMask,applyFmaskSnowMask,
  cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels
  )

////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////
//Function to give year.dd image and harmonics list (e.g. [1,2,3,...])
function getHarmonicList(yearDateImg,transformBandName,harmonicList){
    var t= yearDateImg.select([transformBandName])
    var selectBands = ee.List.sequence(0,harmonicList.length-1);
    
    var sinNames = harmonicList.map(function(h){
      var ht = h*100
      return ee.String('sin_').cat(ht.toString()).cat('_').cat(transformBandName)
    })
    var cosNames = harmonicList.map(function(h){
      var ht =h*100
      return ee.String('cos_').cat(ht.toString()).cat('_').cat(transformBandName)
    })
    
    // var sinCosNames = harmonicList.map(function(h){
    //   var ht =h*100
    //   return ee.String('sin_x_cos_').cat(ht.toString()).cat('_').cat(transformBandName)
    // })
    
    var multipliers = ee.Image(harmonicList).multiply(ee.Number(Math.PI).float()) 
    var sinInd = (t.multiply(ee.Image(multipliers))).sin().select(selectBands,sinNames).float()
    var cosInd = (t.multiply(ee.Image(multipliers))).cos().select(selectBands,cosNames).float()
    // var sinCosInd = sinInd.multiply(cosInd).select(selectBands,sinCosNames);
    
    return yearDateImg.addBands(sinInd.addBands(cosInd))//.addBands(sinCosInd)
  }
//////////////////////////////////////////////////////
//Takes a dependent and independent variable and returns the dependent, 
// sin of ind, and cos of ind
//Intended for harmonic regression
function getHarmonics2(collection,transformBandName,harmonicList){
  var depBandNames = ee.Image(collection.first()).bandNames().remove(transformBandName)
  var depBandNumbers = depBandNames.map(function(dbn){
    return depBandNames.indexOf(dbn)
  })
  
  var out = collection.map(function(img){
    var outT = getHarmonicList(img,transformBandName,harmonicList)
    .copyProperties(img,['system:time_start','system:time_end'])
    return outT
  })
 

  var indBandNames = ee.Image(out.first()).bandNames().removeAll(depBandNames);
  var indBandNumbers = indBandNames.map(function(ind){
    return ee.Image(out.first()).bandNames().indexOf(ind)
  })
  
  out = out.set({'indBandNames':indBandNames,'depBandNames':depBandNames,
                'indBandNumbers':indBandNumbers,'depBandNumbers':depBandNumbers
  })
  
  return out
}
////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////
//Simplifies the use of the robust linear regression reducer
//Assumes the dependent is the first band and all subsequent bands are independents
function newRobustMultipleLinear2(dependentsIndependents){//,dependentBands,independentBands){
  //Set up the band names

  var dependentBands = ee.List(dependentsIndependents.get('depBandNumbers'));
  var independentBands = ee.List(dependentsIndependents.get('indBandNumbers'));
  var bns = ee.Image(dependentsIndependents.first()).bandNames();
  var dependents = ee.List(dependentsIndependents.get('depBandNames'));
  var independents = ee.List(dependentsIndependents.get('indBandNames'));
  
  // var dependent = bns.slice(0,1);
  // var independents = bns.slice(1,null)
  var noIndependents = independents.length().add(1);
  var noDependents = dependents.length();
  
  var outNames = ee.List(['intercept']).cat(independents)
 
  //Add constant band for intercept and reorder for 
  //syntax: constant, ind1,ind2,ind3,indn,dependent
  var forFit = dependentsIndependents.map(function(img){
    var out = img.addBands(ee.Image(1).select([0],['constant']))
    out = out.select(ee.List(['constant',independents]).flatten())
    return out.addBands(img.select(dependents))
  })
  
  //Apply reducer, and convert back to image with respective bandNames
  var reducerOut = forFit.reduce(ee.Reducer.linearRegression(noIndependents,noDependents))
  // var test = forFit.reduce(ee.Reducer.robustLinearRegression(noIndependents,noDependents,0.2))
  // var resids = test
  // .select([1],['residuals']).arrayFlatten([dependents]);
  // Map.addLayer(resids,{},'residsImage');
  // Map.addLayer(reducerOut.select([0]),{},'coefficients');
  // Map.addLayer(test.select([1]),{},'tresiduals');
  // Map.addLayer(reducerOut.select([1]),{},'roresiduals');
  reducerOut = reducerOut
  .select([0],['coefficients']).arrayTranspose().arrayFlatten([dependents,outNames])
  reducerOut = reducerOut
  .set({'noDependents':ee.Number(noDependents),
  'modelLength':ee.Number(noIndependents)
    
  })
  
  return reducerOut
}
//////////////////////////////////////////////////
//Function to set null value for export or conversion to arrays
function setNoData(image,noDataValue){
  var m = image.mask();
  image = image.mask(ee.Image(1));
  image = image.where(m.not(),noDataValue);
  return image;
}
/////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////
//Function to convert collection to a multi-band image
//Assumes a single-band image in the collection
//Derives its own band names
function collectionToImage(collection){
  collection = ee.ImageCollection(collection);
  var i = collection.toArray();
  var bns2 = ee.Image(collection.first()).bandNames();
  var il = ee.List(collection.toList(100000));
  var bns1 = ee.List.sequence(1,il.length())
  .map(function(bn){return ee.String(ee.Number(bn).int16())});
  
  var o = i
  // .arrayProject([0])
  .arrayFlatten([bns1,bns2]);
  return o
}

function addDateBand(img){
  var d = ee.Date(img.get('system:time_start'));
  var y = d.get('year');
  d = y.add(d.getFraction('year'));
  var db = ee.Image.constant(d).rename(['year']).float();
  db = db.updateMask(img.select([0]).mask())
  return img.addBands(db);
}
/////////////////////////////////////////////////////
//Function for applying harmonic regression model to set of predictor sets
function newPredict(coeffs,harmonics){
  //Parse the model
  var bandNames = coeffs.bandNames();
  var bandNumber = bandNames.length();
  var noDependents = ee.Number(coeffs.get('noDependents'));
  var modelLength = ee.Number(coeffs.get('modelLength'));
  var interceptBands = ee.List.sequence(0,bandNumber.subtract(1),modelLength);
  var timeBand = ee.List(harmonics.get('indBandNames')).get(0);
  var actualBands = harmonics.get('depBandNumbers');
  var indBands = harmonics.get('indBandNumbers');
  var indBandNames = ee.List(harmonics.get('indBandNames'));
  var depBandNames = ee.List(harmonics.get('depBandNames'));
  var predictedBandNames = depBandNames.map(function(depbnms){return ee.String(depbnms).cat('_predicted')})
  var predictedBandNumbers = ee.List.sequence(0,predictedBandNames.length().subtract(1));

  var models = ee.List.sequence(0,noDependents.subtract(1));
  var parsedModel =models.map(function(mn){
    mn = ee.Number(mn);
    return bandNames.slice(mn.multiply(modelLength),mn.multiply(modelLength).add(modelLength))
  });
  print('Parsed harmonic regression model',parsedModel,predictedBandNames);

  //Apply parsed model
  var predicted =harmonics.map(function(img){
    var time = img.select(timeBand);
    var actual = img.select(actualBands).float();
    var predictorBands = img.select(indBandNames);
   
    //Iterate across each model for each dependent variable
    var predictedList =parsedModel.map(function(pm){
      pm = ee.List(pm);
      var modelCoeffs = coeffs.select(pm);
      var outName = ee.String(pm.get(1)).cat('_predicted')
      var intercept = modelCoeffs.select(modelCoeffs.bandNames().slice(0,1));
      var others = modelCoeffs.select(modelCoeffs.bandNames().slice(1,null));
      
      var regCoeffs = modelCoeffs.select(modelCoeffs.bandNames().slice(2,null));
      var amplitude = regCoeffs.pow(2).reduce(ee.Reducer.sum()).sqrt().rename(['amplitude']);
      // var amplitude2 = regCoeffs.select([1]).hypot(regCoeffs.select([0])).rename(['amplitude2']);
      var phase = regCoeffs.select([0]).atan2(regCoeffs.select([1])).rename(['phase']);
      predicted = predictorBands.multiply(others).reduce(ee.Reducer.sum()).add(intercept).float();
      return predicted.float().addBands(amplitude).addBands(phase)
    
    })
    //Convert to an image
    predictedList = ee.ImageCollection.fromImages(predictedList);
    var predictedImage = collectionToImage(predictedList);//.select(predictedBandNumbers,predictedBandNames);
    
    //Set some metadata
    var out = actual.addBands(predictedImage.float())
    // var out = predictedImage.float()
    .copyProperties(img,['system:time_start','system:time_end'])
    return out
    
  })
predicted = ee.ImageCollection(predicted)
print(predicted.first())
var g = Chart.image.series(predicted,plotPoint,ee.Reducer.mean(),90);
print(g);
// var g = Chart.image.series(predicted.select([0]),plotPoint,ee.Reducer.mean(),90);
// print(g);
// var g = Chart.image.series(predicted.select([1]),plotPoint,ee.Reducer.mean(),90);
// print(g);
Map.addLayer(predicted,{},'predicted',false)

return predicted
}
//////////////////////////////////////////////////////
//Function to get a dummy image stack for synthetic time series
function getDateStack(startYear,endYear,startJulian,endJulian,frequency){
  var years = ee.List.sequence(startYear,endYear);
  var dates = ee.List.sequence(startJulian,endJulian,frequency);
  //print(startYear,endYear,startJulian,endJulian)
  var dateSets = years.map(function(yr){
    var ds = dates.map(function(d){
      return ee.Date.fromYMD(yr,1,1).advance(d,'day')
    })
    return ds
  })
  var l = range(1,indexNames.length+1)
  l = l.map(function(i){return i%i})
  var c = ee.Image(l).rename(indexNames);
  var c = c.divide(c)
 
  dateSets = dateSets.flatten();
  var stack = dateSets.map(function(dt){
    dt = ee.Date(dt)
    var y = dt.get('year');
    var d = dt.getFraction('year');
    var i = ee.Image(y.add(d)).float().select([0],['year'])
    
    i = c.addBands(i).float()
    .set('system:time_start',dt.millis())
    .set('system:time_end',dt.advance(frequency,'day').millis())
    return i
    
  })
  stack = ee.ImageCollection.fromImages(stack);
  return stack
}



////////////////////////////////////////////////////////////////////
function harmonicRegression(allImages,indexNames,whichHarmonics){
  //Set up metadata table
  // var metaData = ee.Feature(ee.Image(allImages.first()).geometry());
  // metaData = metaData.set('Training_Image_Count',allImages.size());
  // // metaData = metaData.set('Start_Date',startDate);
  // // metaData = metaData.set('End_Date',endDate);
  // metaData = metaData.set('Start_Julian',startJulian);
  // metaData = metaData.set('End_Julian',endJulian);
  // // metaData = metaData.set('Run_TDOM',runTDOM);
  // metaData = metaData.set('Run_Defringe',runDefringe);
  // metaData = metaData.set('Which_Harmonics',whichHarmonics);
  // metaData = metaData.set('Which_Bands',indexNames);
  // metaData = metaData.set('Include L7',includeL7);
  //Select desired bands
  var allIndices = allImages.select(indexNames);
  allIndices = allIndices.map(addDateBand);
  
  //Add independent predictors (harmonics)
  var withHarmonics = getHarmonics2(allIndices,'year',whichHarmonics)
  var withHarmonicsBns = ee.Image(withHarmonics.first()).bandNames().slice(2,null);
  
  // Map.addLayer(withHarmonics.select(withHarmonicsBns),{},'Fit Apply Image Set',false)
  var g = Chart.image.series(withHarmonics.select(withHarmonicsBns),plotPoint,ee.Reducer.mean(),30);
  print(g);
  //Fit a linear regression model
  var coeffs = newRobustMultipleLinear2(withHarmonics)
  
  var bns = coeffs.bandNames();
  print(bns)
  
  Map.addLayer(coeffs,{},'Harmonic Regression Coefficients',false);
  Map.addLayer(coeffs,{},'Coeffs')
  
newPredict(coeffs,withHarmonics)
  
//   var dateStack = getDateStack(startDate.get('year'),endDate.get('year'),startDate.getFraction('year').multiply(365),endDate.getFraction('year').multiply(365),syntheticFrequency);
//   var synthHarmonics = getHarmonics2(dateStack,'year',whichHarmonics)
//   var predictedBandNames = indexNames.map(function(nm){
//     return ee.String(nm).cat('_predicted')
//   })
//   var syntheticStack = ee.ImageCollection(newPredict(coeffs,synthHarmonics)).select(predictedBandNames,indexNames)
 
//   //Filter out and visualize synthetic test image
//   Map.addLayer(syntheticStack.median(),vizParams,'Synthetic All Images Composite',false);
//   var test1ImageSynth = syntheticStack.filterDate(test1Start,test1End);
//   Map.addLayer(test1ImageSynth,vizParams,'Synthetic Test 1 Composite',false);
//   var test2ImageSynth = syntheticStack.filterDate(test2Start,test2End);
//   Map.addLayer(test2ImageSynth,vizParams,'Synthetic Test 2 Composite',false);
  
  
//   //Export image for download
//   var forExport = setNoData(coeffs.clip(sa),outNoData);
//   Map.addLayer(forExport,vizParamsCoeffs,'For Export',false);
//   Export.image(forExport,exportName,{'crs':crs,'region':regionJSON,'scale':exportRes,'maxPixels':1e13})
  
//   Export.table(ee.FeatureCollection([metaData]),exportName + '_metadata');
//   return syntheticStack
}
///////////////////////////////////////////////////////
//Function Calls

ee.List.sequence(startYear+timebuffer,endYear-timebuffer,1).slice(0,1).getInfo().map(function(yr){
  var startYearT = yr-timebuffer;
  var endYearT = yr+timebuffer;
  var allScenesT = allScenes.filter(ee.Filter.calendarRange(startYearT,endYearT,'year'));
  var syntheticStack =harmonicRegression(allScenesT,['NDVI'],[2])

  Map.addLayer(allScenesT.median(),{'min':0.1,'max':0.3,'bands':'swir1,nir,red'})
})