////////////////////////////////////////////////////////////////////////////////
//Module for getting Landsat, Sentinel 2 and MODIS images/composites
// Define visualization parameters
var vizParamsFalse = {
  'min': 0.1, 
  'max': [0.3,0.4,0.4], 
  'bands': 'swir1,nir,red', 
  'gamma': 1.6
};

var vizParamsTrue = {
  'min': 0, 
  'max': [0.2,0.2,0.2], 
  'bands': 'red,green,blue', 
};



////////////////////////////////////////////////////////////////////////////////
// FUNCTIONS
/////////////////////////////////////////////////////////////////////////////////
//Written by Yang Z.
//------ L8 to L7 HARMONIZATION FUNCTION -----
// slope and intercept citation: Roy, D.P., Kovalskyy, V., Zhang, H.K., Vermote, E.F., Yan, L., Kumar, S.S, Egorov, A., 2016, Characterization of Landsat-7 to Landsat-8 reflective wavelength and normalized difference vegetation index continuity, Remote Sensing of Environment, 185, 57-70.(http://dx.doi.org/10.1016/j.rse.2015.12.024); Table 2 - reduced major axis (RMA) regression coefficients
var harmonizationRoy = function(oli) {
  var slopes = ee.Image.constant([0.9785, 0.9542, 0.9825, 1.0073, 1.0171, 0.9949]);        // create an image of slopes per band for L8 TO L7 regression line - David Roy
  var itcp = ee.Image.constant([-0.0095, -0.0016, -0.0022, -0.0021, -0.0030, 0.0029]);     // create an image of y-intercepts per band for L8 TO L7 regression line - David Roy
  var y = oli.select(['B2','B3','B4','B5','B6','B7'],['B1', 'B2', 'B3', 'B4', 'B5', 'B7']) // select OLI bands 2-7 and rename them to match L7 band names
             .resample('bicubic')                                                          // ...resample the L8 bands using bicubic
             .subtract(itcp.multiply(10000)).divide(slopes)                                // ...multiply the y-intercept bands by 10000 to match the scale of the L7 bands then apply the line equation - subtract the intercept and divide by the slope
             .set('system:time_start', oli.get('system:time_start'));                      // ...set the output system:time_start metadata to the input image time_start otherwise it is null
  return y.toShort();                                                                       // return the image as short to match the type of the other data
};
///////////////////////////////////////////////////////////
//Function to create a multiband image from a collection
function collectionToImage(collection){
  var stack = ee.Image(collection.iterate(function(img, prev) {
    return ee.Image(prev).addBands(img);
  }, ee.Image(1)));

  stack = stack.select(ee.List.sequence(1, stack.bandNames().size().subtract(1)));
  return stack;
} 
//Function to handle empty collections that will cause subsequent processes to fail
//If the collection is empty, will fill it with an empty image
function fillEmptyCollections(inCollection,dummyImage){                       
  var dummyCollection = ee.ImageCollection([dummyImage.mask(ee.Image(0))]);
  var imageCount = inCollection.toList(1).length();
  return ee.ImageCollection(ee.Algorithms.If(imageCount.gt(0),inCollection,dummyCollection));

}
//////////////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////
//Adds the float year with julian proportion to image
function addDateBand(img){
  var d = ee.Date(img.get('system:time_start'));
  var y = d.get('year');
  d = y.add(d.getFraction('year'));
  var db = ee.Image.constant(d).rename(['year']).float();
  db = db.updateMask(img.select([0]).mask())
  return img.addBands(db);
}
////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
var fringeCountThreshold = 279;//Define number of non null observations for pixel to not be classified as a fringe
///////////////////////////////////////////////////
//Kernel used for defringing
var k = ee.Kernel.fixed(41, 41, 
[[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]
);
/////////////////////////////////////////////
//Algorithm to defringe Landsat scenes
function defringeLandsat(img){
  //Find any pixel without sufficient non null pixels (fringes)
  var m = img.mask().reduce(ee.Reducer.min());
  
  //Apply kernel
  var sum = m.reduceNeighborhood(ee.Reducer.sum(), k, 'kernel');
  // Map.addLayer(img,vizParams,'with fringes')
  // Map.addLayer(sum,{'min':20,'max':241},'sum41',false)
  
  //Mask pixels w/o sufficient obs
  sum = sum.gte(fringeCountThreshold);
  img = img.mask(sum);
  // Map.addLayer(img,vizParams,'defringed')
  return img;
}

//////////////////////////////////////////////////////////////////
// Function for acquiring Landsat TOA image collection
function getImageCollection(studyArea,startDate,endDate,startJulian,endJulian,
  toaOrSR,includeSLCOffL7,defringeL5){
  
  if(defringeL5 === null || defringeL5 === undefined){defringeL5 = false}
  
  
  // Set up bands and corresponding band names
  var sensorBandDict = {
    'L8TOA': ee.List([1,2,3,4,5,9,6,'BQA']),
    'L7TOA': ee.List([0,1,2,3,4,5,7,'BQA']),
    'L5TOA': ee.List([0,1,2,3,4,5,6,'BQA']),
    'L4TOA': ee.List([0,1,2,3,4,5,6,'BQA']),
    'L8SR': ee.List([1,2,3,4,5,7,6,'pixel_qa']),
    'L7SR': ee.List([0,1,2,3,4,5,6,'pixel_qa']),
    'L5SR': ee.List([0,1,2,3,4,5,6,'pixel_qa']),
    'L4SR': ee.List([0,1,2,3,4,5,6,'pixel_qa']),
  };
  
  var sensorBandNameDict = {
    'TOA': ee.List(['blue','green','red','nir','swir1','temp','swir2','BQA']),
    'SR': ee.List(['blue','green','red','nir','swir1','temp', 'swir2','pixel_qa'])
  };
  
  // Set up collections
  var collectionDict = {
    'L8TOA': 'LANDSAT/LC08/C01/T1_TOA',
    'L7TOA': 'LANDSAT/LE07/C01/T1_TOA',
    'L5TOA': 'LANDSAT/LT05/C01/T1_TOA',
    'L8SR': 'LANDSAT/LC08/C01/T1_SR',
    'L7SR': 'LANDSAT/LE07/C01/T1_SR',
    'L5SR': 'LANDSAT/LT05/C01/T1_SR'
  };
  
  var multImageDict = {
    'TOA': ee.Image([1,1,1,1,1,1,1,1]),
    'SR': ee.Image([0.0001,0.0001,0.0001,0.0001,0.0001,0.1,0.0001,1])
  };
  
  // Get Landsat data
  var l5s = ee.ImageCollection(collectionDict['L5'+ toaOrSR])
    .filterDate(startDate,endDate)
    .filter(ee.Filter.calendarRange(startJulian,endJulian))
    .filterBounds(studyArea)
    .select(sensorBandDict['L5'+ toaOrSR],sensorBandNameDict[toaOrSR]);
    
  if(defringeL5){
    print('Defringing L5');
    l5s = l5s.map(defringeLandsat);
  }
  var l8s = ee.ImageCollection(collectionDict['L8'+ toaOrSR])
    .filterDate(startDate,endDate)
    .filter(ee.Filter.calendarRange(startJulian,endJulian))
    .filterBounds(studyArea)
    .select(sensorBandDict['L8'+ toaOrSR],sensorBandNameDict[toaOrSR]);
  
  var ls; var l7s;
  if (includeSLCOffL7) {
    print('Including All Landsat 7');
    l7s = ee.ImageCollection(collectionDict['L7'+toaOrSR])
      .filterDate(startDate,endDate)
      .filter(ee.Filter.calendarRange(startJulian,endJulian))
      .filterBounds(studyArea)
      .select(sensorBandDict['L7'+ toaOrSR],sensorBandNameDict[ toaOrSR]);
  } else {
    print('Only including SLC On Landat 7');
    l7s = ee.ImageCollection(collectionDict['L7'+toaOrSR])
      .filterDate(ee.Date.fromYMD(1998,1,1),ee.Date.fromYMD(2003,5,31))
      .filterDate(startDate,endDate)
      .filter(ee.Filter.calendarRange(startJulian,endJulian))
      .filterBounds(studyArea)
      .select(sensorBandDict['L7'+ toaOrSR],sensorBandNameDict[toaOrSR]);
  }
  
  // Merge collections
  ls = ee.ImageCollection(l5s.merge(l7s).merge(l8s));
  
  // Make sure all bands have data
  ls = ls.map(function(img){
    img = img.updateMask(img.mask().reduce(ee.Reducer.min()));
    return img.multiply(multImageDict[toaOrSR])
      .copyProperties(img,['system:time_start']).copyProperties(img);
  });
  
  return ls;
}

////////////////////////////////////////////////////////////////////////////////
// Helper function to apply an expression and linearly rescale the output.
// Used in the landsatCloudScore function below.
function rescale(img, exp, thresholds) {
  return img.expression(exp, {img: img})
    .subtract(thresholds[0]).divide(thresholds[1] - thresholds[0]);
}

////////////////////////////////////////////////////////////////////////////////
// Compute a cloud score and adds a band that represents the cloud mask.  
// This expects the input image to have the common band names: 
// ["red", "blue", etc], so it can work across sensors.
function landsatCloudScore(img) {
  // Compute several indicators of cloudiness and take the minimum of them.
  var score = ee.Image(1.0);
  // Clouds are reasonably bright in the blue band.
  score = score.min(rescale(img, 'img.blue', [0.1, 0.3]));
 
  // Clouds are reasonably bright in all visible bands.
  score = score.min(rescale(img, 'img.red + img.green + img.blue', [0.2, 0.8]));
   
  // Clouds are reasonably bright in all infrared bands.
  score = score.min(
    rescale(img, 'img.nir + img.swir1 + img.swir2', [0.3, 0.8]));

  // Clouds are reasonably cool in temperature.
  score = score.min(rescale(img,'img.temp', [300, 290]));

  // However, clouds are not snow.
  var ndsi = img.normalizedDifference(['green', 'swir1']);
  score = score.min(rescale(ndsi, 'img', [0.8, 0.6]));
  
  // var ss = snowScore(img).select(['snowScore']);
  // score = score.min(rescale(ss, 'img', [0.3, 0]));
  
  score = score.multiply(100).byte();
  score = score.clamp(0,100);
  return score;
}
////////////////////////////////////////////////////////////////////////////////
//Wrapper for applying cloudScore function
function applyCloudScoreAlgorithm(collection,cloudScoreFunction,cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels){
  
  
  // Add cloudScore
  var collection = collection.map(function(img){
    var cs = cloudScoreFunction(img).rename(['cloudScore']);
    return img.addBands(cs);
  });
  
  // Find low cloud score pctl for each pixel to avoid comission errors
  var minCloudScore = collection.select(['cloudScore'])
    .reduce(ee.Reducer.percentile([cloudScorePctl]));
  Map.addLayer(minCloudScore,{'min':0,'max':30},'minCloudScore',false);
  // Apply cloudScore
  var collection = collection.map(function(img){
    var cloudMask = img.select(['cloudScore']).subtract(minCloudScore)
      .lt(cloudScoreThresh)
      .focal_max(contractPixels).focal_min(dilatePixels).rename('cloudMask');
    return img.updateMask(cloudMask);
  });
  return collection;
}
////////////////////////////////////////////////////////////////////////////////
// Functions for applying fmask to SR data
var fmaskBitDict = {'cloud' : 32, 'shadow': 8,'snow':16};

function cFmask(img,fmaskClass){
  var m = img.select('pixel_qa').bitwiseAnd(fmaskBitDict[fmaskClass]).neq(0);
  return img.updateMask(m.not());
}

function cFmaskCloud(img){
  return cFmask(img,'cloud');
}
function cFmaskCloudShadow(img){
  return cFmask(img,'shadow');
}

////////////////////////////////////////////////////////////////////////////////
// Function for finding dark outliers in time series.
// Original concept written by Carson Stam and adapted by Ian Housman.
// Adds a band that is a mask of pixels that are dark, and dark outliers.
function simpleTDOM2(collection,zScoreThresh,shadowSumThresh,contractPixels,
  dilatePixels){
  var shadowSumBands = ['nir','swir1'];
  
  // Get some pixel-wise stats for the time series
  var irStdDev = collection.select(shadowSumBands).reduce(ee.Reducer.stdDev());
  var irMean = collection.select(shadowSumBands).mean();
  
  // Mask out dark dark outliers
  collection = collection.map(function(img){
    var zScore = img.select(shadowSumBands).subtract(irMean).divide(irStdDev);
    var irSum = img.select(shadowSumBands).reduce(ee.Reducer.sum());
    var TDOMMask = zScore.lt(zScoreThresh).reduce(ee.Reducer.sum()).eq(2)
      .and(irSum.lt(shadowSumThresh));
    TDOMMask = TDOMMask.focal_min(contractPixels).focal_max(dilatePixels);
    return img.updateMask(TDOMMask.not());
  });
  
  return collection;
}

////////////////////////////////////////////////////////////////////////////////
// Function to add common (and less common) spectral indices to an image.
// Includes the Normalized Difference Spectral Vector from (Angiuli and Trianni, 2014)
function addIndices(img){
  // Add Normalized Difference Spectral Vector (NDSV)
  img = img.addBands(img.normalizedDifference(['blue','green']).rename('ND_blue_green'));
  img = img.addBands(img.normalizedDifference(['blue','red']).rename('ND_blue_red'));
  img = img.addBands(img.normalizedDifference(['blue','nir']).rename('ND_blue_nir'));
  img = img.addBands(img.normalizedDifference(['blue','swir1']).rename('ND_blue_swir1'));
  img = img.addBands(img.normalizedDifference(['blue','swir2']).rename('ND_blue_swir2'));

  img = img.addBands(img.normalizedDifference(['green','red']).rename('ND_green_red'));
  img = img.addBands(img.normalizedDifference(['green','nir']).rename('ND_green_nir')); //NDWBI
  img = img.addBands(img.normalizedDifference(['green','swir1']).rename('ND_green_swir1')); //NDSI, MNDWI
  img = img.addBands(img.normalizedDifference(['green','swir2']).rename('ND_green_swir2'));

  img = img.addBands(img.normalizedDifference(['red','swir1']).rename('ND_red_swir1'));
  img = img.addBands(img.normalizedDifference(['red','swir2']).rename('ND_red_swir2'));

  img = img.addBands(img.normalizedDifference(['nir','red']).rename('ND_nir_red')); //NDVI
  img = img.addBands(img.normalizedDifference(['nir','swir1']).rename('ND_nir_swir1')); //NDWI, LSWI, -NDBI
  img = img.addBands(img.normalizedDifference(['nir','swir2']).rename('ND_nir_swir2')); //NBR, MNDVI

  img = img.addBands(img.normalizedDifference(['swir1','swir2']).rename('ND_swir1_swir2'));
  
  // Add ratios
  img = img.addBands(img.select('swir1').divide(img.select('nir')).rename('R_swir1_nir')); //ratio 5/4
  img = img.addBands(img.select('red').divide(img.select('swir1')).rename('R_red_swir1')); // ratio 3/5

  // Add Enhanced Vegetation Index (EVI)
  var evi = img.expression(
    '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))', {
      'NIR': img.select('nir'),
      'RED': img.select('red'),
      'BLUE': img.select('blue')
  }).float();
  img = img.addBands(evi.rename('EVI'));
  
  // Add Soil Adjust Vegetation Index (SAVI)
  // using L = 0.5;
  var savi = img.expression(
    '(NIR - RED) * (1 + 0.5)/(NIR + RED + 0.5)', {
      'NIR': img.select('nir'),
      'RED': img.select('red')
  }).float();
  img = img.addBands(savi.rename('SAVI'));
  
  // Add Index-Based Built-Up Index (IBI)
  var ibi_a = img.expression(
    '2*SWIR1/(SWIR1 + NIR)', {
      'SWIR1': img.select('swir1'),
      'NIR': img.select('nir')
    }).rename('IBI_A');
  var ibi_b = img.expression(
    '(NIR/(NIR + RED)) + (GREEN/(GREEN + SWIR1))', {
      'NIR': img.select('nir'),
      'RED': img.select('red'),
      'GREEN': img.select('green'),
      'SWIR1': img.select('swir1')
    }).rename('IBI_B');
  ibi_a = ibi_a.addBands(ibi_b);
  var ibi = ibi_a.normalizedDifference(['IBI_A','IBI_B']);
  img = img.addBands(ibi.rename('IBI'));
  
  return img;
}
/////////////////////////////////////////////////////////////////
//Function for only adding common indices
function simpleAddIndices(in_image){
    in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'red']).select([0],['NDVI']));
    in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'swir2']).select([0],['NBR']));
    in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'swir1']).select([0],['NDMI']));
    in_image = in_image.addBands(in_image.normalizedDifference(['green', 'swir1']).select([0],['NDSI']));
  
    return in_image;
}

/////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
// Function to compute the Tasseled Cap transformation and return an image
// with the following bands added: ['brightness', 'greenness', 'wetness', 
// 'fourth', 'fifth', 'sixth']
function getTasseledCap(image) {
 
  var bands = ee.List(['blue','green','red','nir','swir1','swir2']);
  // // Kauth-Thomas coefficients for Thematic Mapper data
  // var coefficients = ee.Array([
  //   [0.3037, 0.2793, 0.4743, 0.5585, 0.5082, 0.1863],
  //   [-0.2848, -0.2435, -0.5436, 0.7243, 0.0840, -0.1800],
  //   [0.1509, 0.1973, 0.3279, 0.3406, -0.7112, -0.4572],
  //   [-0.8242, 0.0849, 0.4392, -0.0580, 0.2012, -0.2768],
  //   [-0.3280, 0.0549, 0.1075, 0.1855, -0.4357, 0.8085],
  //   [0.1084, -0.9022, 0.4120, 0.0573, -0.0251, 0.0238]
  // ]);
  
  //Crist 1985 coeffs - TOA refl (http://www.gis.usu.edu/~doug/RS5750/assign/OLD/RSE(17)-301.pdf)
  var coefficients = ee.Array([[0.2043, 0.4158, 0.5524, 0.5741, 0.3124, 0.2303],
                    [-0.1603, -0.2819, -0.4934, 0.7940, -0.0002, -0.1446],
                    [0.0315, 0.2021, 0.3102, 0.1594, -0.6806, -0.6109],
                    [-0.2117, -0.0284, 0.1302, -0.1007, 0.6529, -0.7078],
                    [-0.8669, -0.1835, 0.3856, 0.0408, -0.1132, 0.2272],
                   [0.3677, -0.8200, 0.4354, 0.0518, -0.0066, -0.0104]]);
  // Make an Array Image, with a 1-D Array per pixel.
  var arrayImage1D = image.select(bands).toArray();
  
  // Make an Array Image with a 2-D Array per pixel, 6x1.
  var arrayImage2D = arrayImage1D.toArray(1);
  
  var componentsImage = ee.Image(coefficients)
    .matrixMultiply(arrayImage2D)
    // Get rid of the extra dimensions.
    .arrayProject([0])
    // Get a multi-band image with TC-named bands.
    .arrayFlatten(
      [['brightness', 'greenness', 'wetness', 'fourth', 'fifth', 'sixth']])
    .float();
  
  return image.addBands(componentsImage);
}

///////////////////////////////////////////////////////////////////////////////
// Function to add Tasseled Cap angles and distances to an image.
// Assumes image has bands: 'brightness', 'greenness', and 'wetness'.
function addTCAngles(image){
  // Select brightness, greenness, and wetness bands
  var brightness = image.select(['brightness']);
  var greenness = image.select(['greenness']);
  var wetness = image.select(['wetness']);
  
  // Calculate Tasseled Cap angles and distances
  var tcAngleBG = brightness.atan2(greenness).divide(Math.PI).rename('tcAngleBG');
  var tcAngleGW = greenness.atan2(wetness).divide(Math.PI).rename('tcAngleGW');
  var tcAngleBW = brightness.atan2(wetness).divide(Math.PI).rename('tcAngleBW');
  var tcDistBG = brightness.hypot(greenness).rename('tcDistBG');
  var tcDistGW = greenness.hypot(wetness).rename('tcDistGW');
  var tcDistBW = brightness.hypot(wetness).rename('tcDistBW');
  image = image.addBands(tcAngleBG).addBands(tcAngleGW)
    .addBands(tcAngleBW).addBands(tcDistBG).addBands(tcDistGW)
    .addBands(tcDistBW);
  return image;
}
////////////////////////////////////////////////////
//Only adds tc bg angle as in Powell et al 2009
//https://www.sciencedirect.com/science/article/pii/S0034425709003745?via%3Dihub
function simpleAddTCAngles(image){
  // Select brightness, greenness, and wetness bands
  var brightness = image.select(['brightness']);
  var greenness = image.select(['greenness']);
  var wetness = image.select(['wetness']);
  
  // Calculate Tasseled Cap angles and distances
  var tcAngleBG = brightness.atan2(greenness).divide(Math.PI).rename('tcAngleBG');
  
  return image.addBands(tcAngleBG);
}
///////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
// Function to add solar zenith and azimuth in radians as bands to image
function addZenithAzimuth(img,toaOrSR){
  
  // Define zenith and azimuth metadata
  var zenithDict = {
    'TOA': 'SUN_ELEVATION',
    'SR': 'SOLAR_ZENITH_ANGLE'
  };
  var azimuthDict = {
    'TOA': 'SUN_AZIMUTH',
    'SR': 'SOLAR_AZIMUTH_ANGLE'
  };
  
  var zenith = ee.Image.constant(img.get(zenithDict[toaOrSR]))
    .multiply(Math.PI).divide(180).float().rename('zenith');
  
  var azimuth = ee.Image.constant(img.get(azimuthDict[toaOrSR]))
    .multiply(Math.PI).divide(180).float().rename('azimuth');
    
  return img.addBands(zenith).addBands(azimuth);
}

////////////////////////////////////////////////////////////////////////////////
// Function for computing the mean squared difference medoid from an image 
// collection
function medoidMosaicMSD(inCollection,medoidIncludeBands) {
  // Find band names in first image
  var f = ee.Image(inCollection.first());
  var bandNames = f.bandNames();
  var bandNumbers = ee.List.sequence(1,bandNames.length());
  
  if (medoidIncludeBands === undefined || medoidIncludeBands === null) {
    medoidIncludeBands = bandNames;
  }
  // Find the median
  var median = inCollection.select(medoidIncludeBands).median();
  
  // Find the squared difference from the median for each image
  var medoid = inCollection.map(function(img){
    var diff = ee.Image(img).select(medoidIncludeBands).subtract(median)
      .pow(ee.Image.constant(2));
    return diff.reduce('sum').addBands(img);
  });
  
  // Minimize the distance across all bands
  medoid = ee.ImageCollection(medoid)
    .reduce(ee.Reducer.min(bandNames.length().add(1)))
    .select(bandNumbers,bandNames);

  return medoid;
}

////////////////////////////////////////////////////////////////////////////////
// Function to export a provided image to an EE asset
function exportToAssetWrapper(imageForExport,assetName,assetPath,
  pyramidingPolicy,roi,scale,crs,transform){
  //Make sure image is clipped to roi in case it's a multi-part polygon
  imageForExport = imageForExport.clip(roi);
  assetName = assetName.replace(/\s+/g,'-');//Get rid of any spaces
  
  Export.image.toAsset(imageForExport, assetName, assetPath, 
    {'.default': pyramidingPolicy}, null, roi, scale, crs, transform, 1e13);
}

////////////////////////////////////////////////////////////////////////////////
// Create composites for each year within startYear and endYear range
function compositeTimeSeries(ls,startYear,endYear,startJulian,endJulian,timebuffer,weights,compositingMethod){
  var dummyImage = ee.Image(ls.first());
  var ts = ee.List.sequence(startYear+timebuffer,endYear-timebuffer).getInfo()
    .map(function(year){
    // Set up dates
    var startYearT = year-timebuffer;
    var endYearT = year+timebuffer;
    var startDateT = ee.Date.fromYMD(startYearT,1,1).advance(startJulian-1,'day');
    var endDateT = ee.Date.fromYMD(endYearT,1,1).advance(endJulian-1,'day');
  
    // Filter images for given date range
    var lsT = ls.filterDate(startDateT,endDateT);
    
    //Fill empty collections
    lsT = fillEmptyCollections(lsT,dummyImage);
    
    var yearsT = ee.List.sequence(startYearT,endYearT);
    
    var z = yearsT.zip(weights);
    var yearsTT = z.map(function(i){
      i = ee.List(i);
      return ee.List.repeat(i.get(0),i.get(1));
    }).flatten();
    // print('Weighted composite years for year:',year,yearsTT);
    var images = yearsTT.map(function(yr){
      
      // Filter images for given date range
      var lsT = ls.filter(ee.Filter.calendarRange(yr,yr,'year'))
                .filter(ee.Filter.calendarRange(startJulian,endJulian));//.toList(10000,0);
      lsT = fillEmptyCollections(lsT,dummyImage);
      return lsT;
    });
    lsT = ee.ImageCollection(ee.FeatureCollection(images).flatten());
   
    // Compute median or medoid
    var composite;
    if (compositingMethod.toLowerCase() === 'median') {
      composite = lsT.median();
    }
    else {
      
      composite = medoidMosaicMSD(lsT,['blue','green','red','nir','swir1','swir2']);
    }
    
    return composite.set('system:time_start',ee.Date.fromYMD(year,6,1).millis());
  });
  return ee.ImageCollection(ts);
}

////////////////////////////////////////////////////////////////////////////////
// Function to calculate illumination condition (IC). Function by Patrick Burns 
// (pb463@nau.edu) and Matt Macander 
// (mmacander@abrinc.com)
function illuminationCondition(img){
  // Extract solar zenith and azimuth bands
  var SZ_rad = img.select('zenith');
  var SA_rad = img.select('azimuth');
  
  // Creat terrain layers
  // var dem = ee.Image('CGIAR/SRTM90_V4');
  var dem = ee.Image('USGS/NED');
  var slp = ee.Terrain.slope(dem);
  var slp_rad = ee.Terrain.slope(dem).multiply(Math.PI).divide(180);
  var asp_rad = ee.Terrain.aspect(dem).multiply(Math.PI).divide(180);
  
  // Calculate the Illumination Condition (IC)
  // slope part of the illumination condition
  var cosZ = SZ_rad.cos();
  var cosS = slp_rad.cos();
  var slope_illumination = cosS.expression("cosZ * cosS", 
                                          {'cosZ': cosZ,
                                           'cosS': cosS.select('slope')});
  // aspect part of the illumination condition
  var sinZ = SZ_rad.sin(); 
  var sinS = slp_rad.sin();
  var cosAziDiff = (SA_rad.subtract(asp_rad)).cos();
  var aspect_illumination = sinZ.expression("sinZ * sinS * cosAziDiff", 
                                           {'sinZ': sinZ,
                                            'sinS': sinS,
                                            'cosAziDiff': cosAziDiff});
  // full illumination condition (IC)
  var ic = slope_illumination.add(aspect_illumination);

  // Add IC to original image
  return img.addBands(ic.rename('IC'))
    .addBands(cosZ.rename('cosZ'))
    .addBands(cosS.rename('cosS'))
    .addBands(slp.rename('slope'));
}

////////////////////////////////////////////////////////////////////////////////
// Function to apply the Sun-Canopy-Sensor + C (SCSc) correction method to each 
// image. Function by Patrick Burns (pb463@nau.edu) and Matt Macander 
// (mmacander@abrinc.com)
function illuminationCorrection(img, scale,studyArea){
  var props = img.toDictionary();
  var st = img.get('system:time_start');
  var img_plus_ic = img;
  var mask2 = img_plus_ic.select('slope').gte(5)
    .and(img_plus_ic.select('IC').gte(0))
    .and(img_plus_ic.select('nir').gt(-0.1));
  var img_plus_ic_mask2 = ee.Image(img_plus_ic.updateMask(mask2));
  
  // Specify Bands to topographically correct  
  var bandList = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'temp']; 
  var compositeBands = img.bandNames();
  var nonCorrectBands = img.select(compositeBands.removeAll(bandList));
  
  function apply_SCSccorr(bandList){
    var method = 'SCSc';
    var out = img_plus_ic_mask2.select('IC', bandList).reduceRegion({
      reducer: ee.Reducer.linearFit(),
      geometry: studyArea,
      scale: scale,
      maxPixels: 1e13
    }); 
    var out_a = ee.Number(out.get('scale'));
    var out_b = ee.Number(out.get('offset'));
    var out_c = out_b.divide(out_a);
    // Apply the SCSc correction
    var SCSc_output = img_plus_ic_mask2.expression(
      "((image * (cosB * cosZ + cvalue)) / (ic + cvalue))", {
      'image': img_plus_ic_mask2.select(bandList),
      'ic': img_plus_ic_mask2.select('IC'),
      'cosB': img_plus_ic_mask2.select('cosS'),
      'cosZ': img_plus_ic_mask2.select('cosZ'),
      'cvalue': out_c
    });
    
    return SCSc_output;
  }
  
  var img_SCSccorr = ee.Image(bandList.map(apply_SCSccorr))
    .addBands(img_plus_ic.select('IC'));
  var bandList_IC = ee.List([bandList, 'IC']).flatten();
  img_SCSccorr = img_SCSccorr.unmask(img_plus_ic.select(bandList_IC)).select(bandList);
  
  return img_SCSccorr.addBands(nonCorrectBands)
    .setMulti(props)
    .set('system:time_start',st);
}
function listToString(list,space){
  if(space === undefined){space = ' '}
  var out = '';
  list.map(function(s){out = out + space+s.toString()});
  return out;
}
////////////////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////
// A function to mask out pixels that did not have observations for MODIS.
var maskEmptyPixels = function(image) {
  // Find pixels that had observations.
  var withObs = image.select('num_observations_1km').gt(0);
  return image.mask(image.mask().and(withObs));
};
//////////////////////////////////////////////////////////////////////////
/*
 * A function that returns an image containing just the specified QA bits.
 *
 * Args:
 *   image - The QA Image to get bits from.
 *   start - The first bit position, 0-based.
 *   end   - The last bit position, inclusive.
 *   name  - A name for the output image.
 */
var getQABits = function(image, start, end, newName) {
    // Compute the bits we need to extract.
    var pattern = 0;
    for (var i = start; i <= end; i++) {
       pattern += Math.pow(2, i);
    }
    // Return a single band image of the extracted QA bits, giving the band
    // a new name.
    return image.select([0], [newName])
                  .bitwiseAnd(pattern)
                  .rightShift(start);
};
/////////////////////////////////////////////////////////////////
// A function to mask out cloudy pixels.
var maskCloudsWQA = function(image) {
  // Select the QA band.
  var QA = image.select('state_1km');
  // Get the internal_cloud_algorithm_flag bit.
  var internalCloud = getQABits(QA, 10, 10, 'internal_cloud_algorithm_flag');
  // Return an image masking out cloudy areas.
  return image.mask(image.mask().and(internalCloud.eq(0)));
};
/////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////////
//Source: code.earthengine.google.com
// Compute a cloud score.  This expects the input image to have the common
// band names: ["red", "blue", etc], so it can work across sensors.
function modisCloudScore(img) {
  var useTempInCloudMask = true;
  // A helper to apply an expression and linearly rescale the output.
  var rescale = function(img, exp, thresholds) {
    return img.expression(exp, {img: img})
        .subtract(thresholds[0]).divide(thresholds[1] - thresholds[0]);
  };

  // Compute several indicators of cloudyness and take the minimum of them.
  var score = ee.Image(1.0);
  
  // Clouds are reasonably bright in the blue band.
  score = score.min(rescale(img, 'img.blue', [0.1, 0.3]));
  
  // Clouds are reasonably bright in all visible bands.
  var vizSum = rescale(img, 'img.red + img.green + img.blue', [0.2, 0.8]);
  score = score.min(vizSum);
  
  // Clouds are reasonably bright in all infrared bands.
  var irSum =rescale(img, 'img.nir + img.swir1 + img.swir2', [0.3, 0.8]);
  score = score.min(
      irSum);
  
  
  
  // However, clouds are not snow.
  var ndsi = img.normalizedDifference(['green', 'swir1']);
  var snowScore = rescale(ndsi, 'img', [0.8, 0.6]);
  score =score.min(snowScore);
  
  //For MODIS, provide the option of not using thermal since it introduces
  //a precomputed mask that may or may not be wanted
  if(useTempInCloudMask === true){
    // Clouds are reasonably cool in temperature.
    var tempScore = rescale(img, 'img.temp', [305, 300]);
    score = score.min(tempScore);
  }
  
  score = score.multiply(100);
  score = score.clamp(0,100);
  return score;
}
////////////////////////////////////////
// Cloud masking algorithm for Sentinel2
//Built on ideas from Landsat cloudScore algorithm
//Currently in beta and may need tweaking for individual study areas
function sentinelCloudScore(img) {
  

  // Compute several indicators of cloudyness and take the minimum of them.
  var score = ee.Image(1);
  var blueCirrusScore = ee.Image(0);
  
  // Clouds are reasonably bright in the blue or cirrus bands.
  //Use .max as a pseudo OR conditional
  blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.blue', [0.1, 0.5]));
  blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.cb', [0.1, 0.5]));
  blueCirrusScore = blueCirrusScore.max(rescale(img, 'img.cirrus', [0.1, 0.3]));
  
  // var reSum = rescale(img,'(img.re1+img.re2+img.re3)/3',[0.5, 0.7])
  // Map.addLayer(blueCirrusScore,{'min':0,'max':1})
  score = score.min(blueCirrusScore);


  // Clouds are reasonably bright in all visible bands.
  score = score.min(rescale(img, 'img.red + img.green + img.blue', [0.2, 0.8]));
  
  // Clouds are reasonably bright in all infrared bands.
  score = score.min(
      rescale(img, 'img.nir + img.swir1 + img.swir2', [0.3, 0.8]));
  
  
  // However, clouds are not snow.
  var ndsi =  img.normalizedDifference(['green', 'swir1']);
 
  
  score=score.min(rescale(ndsi, 'img', [0.8, 0.6]));
  
  score = score.multiply(100).byte();
  score = score.clamp(0,100).rename(['cloudScore']);
 
  return score;
}
///////////////////////////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////////
//MODIS processing
//////////////////////////////////////////////////
//Some globals to deal with multi-spectral MODIS
var wTempSelectOrder = [2,3,0,1,4,6,5];//Band order to select to be Landsat 5-like if thermal is included
var wTempStdNames = ['blue', 'green', 'red', 'nir', 'swir1','temp','swir2'];

var woTempSelectOrder = [2,3,0,1,4,5];//Band order to select to be Landsat 5-like if thermal is excluded
var woTempStdNames = ['blue', 'green', 'red', 'nir', 'swir1','swir2'];

//Band names from different MODIS resolutions
//Try to take the highest spatial res for a given band
var modis250SelectBands = ['sur_refl_b01','sur_refl_b02'];
var modis250BandNames = ['red','nir'];

var modis500SelectBands = ['sur_refl_b03','sur_refl_b04','sur_refl_b06','sur_refl_b07'];
var modis500BandNames = ['blue','green','swir1','swir2'];

var combinedModisBandNames = ['red','nir','blue','green','swir1','swir2'];


//Dictionary of MODIS collections
var modisCDict = {
  'eightDayNDVIA' : 'MODIS/006/MYD13Q1',
  'eightDayNDVIT' : 'MODIS/006/MOD13Q1',
  
  
  'eightDaySR250A' : 'MODIS/006/MYD09Q1',
  'eightDaySR250T' : 'MODIS/006/MOD09Q1',
  
  'eightDaySR500A' : 'MODIS/006/MYD09A1',
  'eightDaySR500T' : 'MODIS/006/MOD09A1',
  
  'eightDayLST1000A' : 'MODIS/006/MYD11A2',
  'eightDayLST1000T' : 'MODIS/006/MOD11A2',
  
  // 'dailyNDVIA' : 'MODIS/MYD09GA_NDVI',
  // 'dailyNDVIT' : 'MODIS/MOD09GA_NDVI',
  
  
  'dailySR250A' : 'MODIS/006/MYD09GQ',
  'dailySR250T' : 'MODIS/006/MOD09GQ',
  
  'dailySR500A' : 'MODIS/006/MYD09GA',
  'dailySR500T' : 'MODIS/006/MOD09GA',
  
  'dailyLST1000A' : 'MODIS/006/MYD11A1',
  'dailyLST1000T' : 'MODIS/006/MOD11A1'
};
/////////////////////////////////////////////////
//Helper function to join two collections- Source: code.earthengine.google.com
    function joinCollections(c1,c2, maskAnyNullValues){
      if(maskAnyNullValues === undefined || maskAnyNullValues === null){maskAnyNullValues = true}
      var MergeBands = function(element) {
        // A function to merge the bands together.
        // After a join, results are in 'primary' and 'secondary' properties.
        return ee.Image.cat(element.get('primary'), element.get('secondary'));
      };

      var join = ee.Join.inner();
      var filter = ee.Filter.equals('system:time_start', null, 'system:time_start');
      var joined = ee.ImageCollection(join.apply(c1, c2, filter));
     
      joined = ee.ImageCollection(joined.map(MergeBands));
      if(maskAnyNullValues){
        joined = joined.map(function(img){return img.mask(img.mask().and(img.reduce(ee.Reducer.min()).neq(0)))});
      }
      return joined;
    }
//////////////////////////////////////////////////////
//////////////////////////////////////////////////////
//Method for removing spikes in time series
function despikeCollection(c,absoluteSpike,bandNo){
  c = c.toList(10000,0);
  
  //Get book ends for adding back at the end
  var first = c.slice(0,1);
  var last = c.slice(-1,null);
  
  //Slice the left, center, and right for the moving window
  var left = c.slice(0,-2);
  var center = c.slice(1,-1);
  var right = c.slice(2,null);
  
  //Find how many images there are to compare
  var seq = ee.List.sequence(0,left.length().subtract(1));
  
  //Compare the center to the left and right images
  var outCollection = seq.map(function(i){
    var lt = ee.Image(left.get(i));
    var rt = ee.Image(right.get(i));
    
    var ct = ee.Image(center.get(i));
    var time_start = ct.get('system:time_start');
    var time_end = ct.get('system:time_end');
    var si = ct.get('system:index');
   
    
    
    var diff1 = ct.select([bandNo]).add(1).subtract(lt.select([bandNo]).add(1));
    var diff2 = ct.select([bandNo]).add(1).subtract(rt.select([bandNo]).add(1));
    
    var highSpike = diff1.gt(absoluteSpike).and(diff2.gt(absoluteSpike));
    var lowSpike = diff1.lt(- absoluteSpike).and(diff2.lt(- absoluteSpike));
    var BinarySpike = highSpike.or(lowSpike);
    
    //var originalMask = ct.mask();
    // ct = ct.mask(BinarySpike.eq(0));
    
    var doNotMask = lt.mask().not().or(rt.mask().not());
    var lrMean = lt.add(rt)
    lrMean = lrMean.divide(2)
    // var out = ct.mask(doNotMask.not().and(ct.mask()))
    var out = ct.where(BinarySpike.eq(1).and(doNotMask.not()),lrMean)
    return out.set('system:index',si).set('system:time_start', time_start).set('system:time_end', time_end);
    
    
  });
  //Add the bookends back on
  outCollection =  ee.List([first,outCollection,last]).flatten();
   
  return ee.ImageCollection.fromImages(outCollection);
  
}


///////////////////////////////////////////////////////////
//Function to get MODIS data from various collections
//Will pull from daily or 8-day composite collections based on the boolean variable "daily"
function getModisData(startYear,endYear,startJulian,endJulian,daily,maskWQA,zenithThresh,useTempInCloudMask){
    var a250C;var t250C;var a500C;var t500C;var a1000C;var t1000C;
    var a250CV6;var t250CV6;var a500CV6;var t500CV6;var a1000CV6;var t1000CV6;
    
      //Find which collections to pull from based on daily or 8-day
      if(daily === false){
        a250C = modisCDict.eightDaySR250A;
        t250C = modisCDict.eightDaySR250T;
        a500C = modisCDict.eightDaySR500A;
        t500C = modisCDict.eightDaySR500T;
        a1000C = modisCDict.eightDayLST1000A;
        t1000C = modisCDict.eightDayLST1000T;
        
      
      }
     else{
        a250C = modisCDict.dailySR250A;
        t250C = modisCDict.dailySR250T;
        a500C = modisCDict.dailySR500A;
        t500C = modisCDict.dailySR500T;
        a1000C = modisCDict.dailyLST1000A;
        t1000C = modisCDict.dailyLST1000T;
        
        
      }
      
    //Pull images from each of the collections  
    var a250 = ee.ImageCollection(a250C)
              .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
              .filter(ee.Filter.calendarRange(startJulian,endJulian))
              .select(modis250SelectBands,modis250BandNames);
    
            
    var t250 = ee.ImageCollection(t250C)
              .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
              .filter(ee.Filter.calendarRange(startJulian,endJulian))
              .select(modis250SelectBands,modis250BandNames);
    
    
    function get500(c){
       var images = ee.ImageCollection(c)
              .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
              .filter(ee.Filter.calendarRange(startJulian,endJulian));
              
              //Mask pixels above a certain zenith
              if(daily === true){
                if(maskWQA === true){print('Masking with QA band:',c)}
                images = images
              .map(function(img){
                img = img.mask(img.mask().and(img.select(['SensorZenith']).lt(zenithThresh*100)));
                if(maskWQA === true){
                  
                  img = maskCloudsWQA (img);
                }
                return img;
              });
              }
              images = images
              .select(modis500SelectBands,modis500BandNames);
              return images;
    }         
    var a500 = get500(a500C);
    var t500 = get500(t500C);
    
    
    //If thermal collection is wanted, pull it as well
    if(useTempInCloudMask === true){
       var t1000 = ee.ImageCollection(t1000C)
              .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
              .filter(ee.Filter.calendarRange(startJulian,endJulian))
              .select([0]);
            
      var a1000 = ee.ImageCollection(a1000C)
              .filter(ee.Filter.calendarRange(startYear,endYear,'year'))
              .filter(ee.Filter.calendarRange(startJulian,endJulian))
              .select([0]);        
    }
    
    //Now all collections are pulled, start joining them
    //First join the 250 and 500 m Aqua
      var a;var t;var tSelectOrder;var tStdNames;
      a = joinCollections(a250,a500);
      
      //Then Terra
      t = joinCollections(t250,t500);
      
      //If temp was pulled, join that in as well
      //Also select the bands in an L5-like order and give descriptive names
      if(useTempInCloudMask === true){
        a = joinCollections(a,a1000);
        t = joinCollections(t,t1000);
        tSelectOrder = wTempSelectOrder;
        tStdNames = wTempStdNames;
      }
      //If no thermal was pulled, leave that out
      else{
        tSelectOrder = woTempSelectOrder;
        tStdNames = woTempStdNames;
      }
      
      //Join Terra and Aqua 
      var joined = ee.ImageCollection(a.merge(t)).select(tSelectOrder,tStdNames);
     
      //Divide by 10000 to make it work with cloud masking algorithm out of the box
      joined = joined.map(function(img){return img.divide(10000).float()
        .copyProperties(img,['system:time_start','system:time_end']);
        
      });
      // print('Collection',joined);
      //Since MODIS thermal is divided by 0.02, multiply it by that and 10000 if it was included
      if(useTempInCloudMask === true){
      joined = joined.map(function(img){
        var t = img.select(['temp']).multiply(0.02*10000);
        return img.select(['blue','green','red','nir','swir1','swir2'])
        .addBands(t).select([0,1,2,3,4,6,5]);
      
      });
      }
    
  //   //Get some descriptive names for displaying layers
  //   var name = 'surRefl';
  //   if(daily === true){
  //     name = name + '_daily';
  //   }
  //   else{name = name + '8DayComposite'}
  //   if(maskWQA === true){
  //     name = name + '_WQAMask';
  //   }
    
  // //Add first image as well as median for visualization
  //   // Map.addLayer(ee.Image(joined.first()),vizParams,name+'_singleFirstImageBeforeMasking',false);
  //   // Map.addLayer(ee.Image(joined.median()),vizParams,name+'_CompositeBeforeMasking',false);
    
  //   if(applyCloudScore === true){
  // //Compute cloud score and mask cloudy pixels
  //     print('Applying Google cloudScore algorithm');
  //     // var joined = joined.map(function(img,useTempInCloudMask){
  //     //   var cs = modisCloudScore(img);
  //     //   return img.mask(img.mask().and(cs.lt(cloudThresh)))//.addBands(cs.select([0],['cloudScore']))
        
  //     // });
  //   //Add first image as well as median for visualization
  //   // Map.addLayer(ee.Image(joined.first()),vizParams,name+'_singleFirstImageAfterMasking',false);
  //   // Map.addLayer(ee.Image(joined.median()),vizParams,name+'_CompositeAfterMasking',false);
  //   joined = joined.map(function(img){return getCloudMask(img,modisCloudScore,cloudThresh,useTempInCloudMask,contractPixels,dilatePixels)});
      
  //   }
    
  // //   //If cloud shadow masking is chosen, run it
  // //   if(runTDOM === true){
  // //     print('Running TDOM');
  // //     joined = simpleTDOM(joined,zShadowThresh,zCloudThresh,maskAllDarkPixels)
    
  // //   //Add first image as well as median for visualization after TDOM
  // // // Map.addLayer(ee.Image(joined.first()),vizParams,name+'_singleFirstImageAfterMaskingWTDOM',false);
  // // // Map.addLayer(ee.Image(joined.median()),vizParams,name+'_CompositeAfterMaskingWTDOM',false);
  
      
  // //   };
  
  
  // // //Add indices and select them
  // // joined = joined.map(addIndices);
  // joined = joined.map(addIndices);
  // var indicesAdded = true;
  // if(despikeMODIS){
  //   print('Despiking MODIS');
  //   joined = despikeCollection(joined,modisSpikeThresh,indexName);
  // }
  
  return ee.ImageCollection(joined);
    
  }
  
////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////
function exportCollection(exportPathRoot,outputName,studyArea, crs,transform,scale,
collection){
  
}

// Function to export composite collection
function exportCompositeCollection(exportPathRoot,outputName,studyArea, crs,transform,scale,
collection,startYear,endYear,startJulian,endJulian,compositingMethod,timebuffer,exportBands,toaOrSR,weights,
applyCloudScore, applyFmaskCloudMask,applyTDOM,applyFmaskCloudShadowMask,applyFmaskSnowMask,includeSLCOffL7,correctIllumination){
  collection = collection.select(exportBands);
  var years = ee.List.sequence(startYear+timebuffer,endYear-timebuffer).getInfo()
    .map(function(year){
    // Set up dates
    var startYearT = year-timebuffer;
    var endYearT = year+timebuffer;
    
    // Get yearly composite
    var composite = collection.filter(ee.Filter.calendarRange(year,year,'year'));
    composite = ee.Image(composite.first());
    
    // Display the Landsat composite
    Map.addLayer(composite, vizParamsTrue, year.toString() + ' True Color ' + 
      toaOrSR, false);
    Map.addLayer(composite, vizParamsFalse, year.toString() + ' False Color ' + 
      toaOrSR, false);
  
    // Reformat data for export
    var compositeBands = composite.bandNames();
    var nonDivideBands = ee.List(['temp']);
    var composite10k = composite.select(compositeBands.removeAll(nonDivideBands))
      .multiply(10000);
    composite = composite10k.addBands(composite.select(nonDivideBands))
      .select(compositeBands).int16();

    // Add metadata, cast to integer, and export composite
    composite = composite.set({
      'system:time_start': ee.Date.fromYMD(year,6,1).millis(),
      'source': toaOrSR,
      'yearBuffer':timebuffer,
      'yearWeights': listToString(weights),
      'startJulian': startJulian,
      'endJulian': endJulian,
      'applyCloudScore':applyCloudScore.toString(),
      'applyFmaskCloudMask' :applyFmaskCloudMask.toString(),
      'applyTDOM' :applyTDOM.toString(),
      'applyFmaskCloudShadowMask' :applyFmaskCloudShadowMask.toString(),
      'applyFmaskSnowMask': applyFmaskSnowMask.toString(),
      'compositingMethod': compositingMethod,
      'includeSLCOffL7': includeSLCOffL7.toString(),
      'correctIllumination':correctIllumination.toString()
    });
  
    // Export the composite 
    // Set up export name and path
    var exportName = outputName  + toaOrSR + '_' + compositingMethod + 
      '_'  + startYearT + '_' + endYearT+'_' + 
      startJulian + '_' + endJulian ;
   
    
    var exportPath = exportPathRoot + '/' + exportName;
    // print('Write down the Asset ID:', exportPath);
  
    exportToAssetWrapper(composite,exportName,exportPath,'mean',
      studyArea,null,crs,transform);
    });
}
/////////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////
//Wrapper function for getting Landsat imagery
function getLandsatWrapper(studyArea,startYear,endYear,startJulian,endJulian,
  timebuffer,weights,compositingMethod,
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
  applyFmaskCloudShadowMask,applyFmaskSnowMask,
  cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels,
  correctIllumination,correctScale,
  exportComposites,outputName,exportPathRoot,crs,transform,scale){
  
  // Prepare dates
  //Wrap the dates if needed
  if (startJulian > endJulian) {
    endJulian = endJulian + 365;
  }
  var startDate = ee.Date.fromYMD(startYear,1,1).advance(startJulian-1,'day');
  var endDate = ee.Date.fromYMD(endYear,1,1).advance(endJulian-1,'day');
  print('Start and end dates:', startDate, endDate);

  //Do some error checking
  toaOrSR = toaOrSR.toUpperCase();
  if(toaOrSR === 'TOA'){
      applyFmaskCloudMask = false;
  
      applyFmaskCloudShadowMask = false;
  
      applyFmaskSnowMask = false;
    }
  // Get Landsat image collection
  var ls = getImageCollection(studyArea,startDate,endDate,startJulian,endJulian,
    toaOrSR,includeSLCOffL7,defringeL5);
  
  // Apply relevant cloud masking methods
  if(applyCloudScore){
    print('Applying cloudScore');
    ls = applyCloudScoreAlgorithm(ls,landsatCloudScore,cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels); 
    
  }
  
  if(applyFmaskCloudMask){
    print('Applying Fmask cloud mask');
    ls = ls.map(function(img){return cFmask(img,'cloud')});
  }
  
  if(applyTDOM){
    print('Applying TDOM');
    //Find and mask out dark outliers
    ls = simpleTDOM2(ls,zScoreThresh,shadowSumThresh,contractPixels,dilatePixels);
  }
  if(applyFmaskCloudShadowMask){
    print('Applying Fmask shadow mask');
    ls = ls.map(function(img){return cFmask(img,'shadow')});
  }
  if(applyFmaskSnowMask){
    print('Applying Fmask snow mask');
    ls = ls.map(function(img){return cFmask(img,'snow')});
  }
  
  
  // Add zenith and azimuth
  if (correctIllumination){
    ls = ls.map(function(img){
      return addZenithAzimuth(img,toaOrSR);
    });
  }
  
  // Add common indices- can use addIndices for comprehensive indices 
  //or simpleAddIndices for only common indices
  ls = ls.map(simpleAddIndices)
          .map(getTasseledCap)
          .map(simpleAddTCAngles);
  
  // Create composite time series
  var ts = compositeTimeSeries(ls,startYear,endYear,startJulian,endJulian,timebuffer,weights,compositingMethod);
  
  
  // Correct illumination
  if (correctIllumination){
    var f = ee.Image(ts.first());
    Map.addLayer(f,vizParamsFalse,'First-non-illuminated',false);
  
    print('Correcting illumination');
    ts = ts.map(illuminationCondition)
      .map(function(img){
        return illuminationCorrection(img, correctScale,studyArea);
      });
    var f = ee.Image(ts.first());
    Map.addLayer(f,vizParamsFalse,'First-illuminated',false);
  }
  
  //Export composites
  if(exportComposites){// Export composite collection
    var exportBands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'temp'];
    exportCompositeCollection(exportPathRoot,outputName,studyArea,crs,transform,scale,
    ts,startYear,endYear,startJulian,endJulian,compositingMethod,timebuffer,exportBands,toaOrSR,weights,
                  applyCloudScore, applyFmaskCloudMask,applyTDOM,applyFmaskCloudShadowMask,applyFmaskSnowMask,includeSLCOffL7,correctIllumination);
  }
  
  return [ls,ts];
}

////////////////////////////////////////////////////////////////////////////////
// END FUNCTIONS
////////////////////////////////////////////////////////////////////////////////
exports.addDateBand = addDateBand;
exports.collectionToImage = collectionToImage;
exports.getImageCollection = getImageCollection;
exports.vizParamsFalse = vizParamsFalse;
exports.vizParamsTrue = vizParamsTrue;
exports.landsatCloudScore = landsatCloudScore;
exports.applyCloudScoreAlgorithm = applyCloudScoreAlgorithm;
exports.cFmask = cFmask;
exports.simpleTDOM2 = simpleTDOM2;
exports.addIndices = addIndices;
exports.simpleAddIndices = simpleAddIndices;
exports.compositeTimeSeries = compositeTimeSeries;
exports.addZenithAzimuth = addZenithAzimuth;
exports.illuminationCorrection = illuminationCorrection;
exports.illuminationCondition = illuminationCondition;
exports.addTCAngles = addTCAngles;
exports.simpleAddTCAngles = simpleAddTCAngles;
exports.exportCompositeCollection = exportCompositeCollection;
exports.getLandsatWrapper = getLandsatWrapper;

exports.getModisData = getModisData;
exports.modisCloudScore = modisCloudScore;
exports.despikeCollection = despikeCollection;
exports.exportToAssetWrapper = exportToAssetWrapper;
exports.joinCollections = joinCollections;
exports.listToString = listToString;
exports.harmonizationRoy = harmonizationRoy
exports.fillEmptyCollections = fillEmptyCollections;