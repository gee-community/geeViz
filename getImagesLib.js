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
////////////////////////////////////////////////////////////////////////////////
// Function for acquiring Landsat TOA image collection
function getImageCollection(studyArea,startDate,endDate,startJulian,endJulian,
  toaOrSR,includeSLCOffL7){
  
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
//Function for only adding common indices
function simpleAddIndices(in_image){
    in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'red']).select([0],['NDVI']));
    in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'swir2']).select([0],['NBR']));
    in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'swir1']).select([0],['NDMI']));
    in_image = in_image.addBands(in_image.normalizedDifference(['green', 'swir1']).select([0],['NDSI']));
  
    return in_image;
}
/////////////////////////////////////////////////////////////////
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
  pyramidingPolicy,roi,region,scale,crs,transform){
  //Make sure image is clipped to roi in case it's a multi-part polygon
  imageForExport = imageForExport.clip(roi);
  assetName = assetName.replace(/\s+/g,'-');//Get rid of any spaces
  
  Export.image.toAsset(imageForExport, assetName, assetPath, 
    {'.default': pyramidingPolicy}, null, region, scale, crs, transform, 1e13);
}

////////////////////////////////////////////////////////////////////////////////
// Create composites for each year within startYear and endYear range
function compositeTimeSeries(ls,startYear,endYear,startJulian,endJulian,timebuffer,weights,compositingMethod){
  var ts = ee.List.sequence(startYear+timebuffer,endYear-timebuffer).getInfo()
    .map(function(year){
    // Set up dates
    var startYearT = year-timebuffer;
    var endYearT = year+timebuffer;
    var startDateT = ee.Date.fromYMD(startYearT,1,1).advance(startJulian-1,'day');
    var endDateT = ee.Date.fromYMD(endYearT,1,1).advance(endJulian-1,'day');
  
    // Filter images for given date range
    var lsT = ls.filterDate(startDateT,endDateT);
    
    var yearsT = ee.List.sequence(startYearT,endYearT);
    
    var z = yearsT.zip(weights);
    var yearsTT = z.map(function(i){
      i = ee.List(i);
      return ee.List.repeat(i.get(0),i.get(1));
    }).flatten();
    print('Weighted composite years for year:',year,yearsTT);
    var images = yearsTT.map(function(yr){
      
      // Filter images for given date range
      var lsT = ls.filter(ee.Filter.calendarRange(yr,yr,'year'))
                .filter(ee.Filter.calendarRange(startJulian,endJulian));//.toList(10000,0);
    return lsT;
    });
    var lsT = ee.ImageCollection(ee.FeatureCollection(images).flatten())
   
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
// Function to export composite collection
function exportCollection(collection,startYear,endYear,startJulian,endJulian,compositingMethod,timebuffer,exportBands,toaOrSR,weights,
applyCloudScore, applyFmaskCloudMask,applyTDOM,applyFmaskCloudShadowMask,applyFmaskSnowMask){
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
      'date': ee.Date.fromYMD(year,6,1),
      'source': toaOrSR,
      'yearBuffer':timebuffer,
      'yearWeights': listToString(weights),
      'startJulian': startJulian,
      'endJulian': endJulian,
      'applyCloudScore':applyCloudScore,
      'applyFmaskCloudMask' :applyFmaskCloudMask,
      'applyTDOM' :applyTDOM,
      'applyFmaskCloudShadowMask' :applyFmaskCloudShadowMask,
      'applyFmaskSnowMask': applyFmaskSnowMask,
      'compositingMethod': compositingMethod,
      'includeSLCOffL7': includeSLCOffL7.toString()
    });
  
    // Export the composite 
    // Set up export name and path
    var exportName = outputName  + toaOrSR + '_' + compositingMethod + 
      '_' + cloudcloudShadowMaskingMethod+'_' + startYearT + '_' + endYearT+'_' + 
      startJulian + '_' + endJulian ;
   
    
    var exportPath = exportPathRoot + '/' + exportName;
    // print('Write down the Asset ID:', exportPath);
  
    exportToAssetWrapper(composite,exportName,exportPath,'mean',
      studyArea,region,null,crs,transform);
    });
}

////////////////////////////////////////////////////////////////////////////////
// END FUNCTIONS
////////////////////////////////////////////////////////////////////////////////
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
exports.exportCollection = exportCollection;