var sensorBandDict = {
    'LC08': [1,2,3,4,5,7,6,'pixel_qa'],
    'LE07': [0,1,2,3,4,5,6,'pixel_qa'],
    'LT05': [0,1,2,3,4,5,6,'pixel_qa'],
    'LT04': [0,1,2,3,4,5,6,'pixel_qa'],
  };
var bandNames = ['blue','green','red','nir','swir1','temp', 'swir2','pixel_qa'];
////////////////////////////////////////////////////////////////////////////////
// Functions for applying fmask to SR data
var fmaskBitDict = {'cloud' : 32, 'shadow': 8,'snow':16,'water':4};

function cFmask(img,fmaskClass){
  var m = img.select('pixel_qa').bitwiseAnd(fmaskBitDict[fmaskClass]).neq(0);
  return img.updateMask(m.not());
}

var getLandsat = function(startYear,endYear,startJulian,endJulian,box,sensors,maskWhat){
  if(sensors == undefined || sensors == null){
    sensors = ['LT04','LT05','LE07','LC08']
  };
  if(maskWhat == undefined || maskWhat == null){
    maskWhat = ['cloud','shadow']
  }
  
  var ls =sensors.map(function(sensor){
    var srCollection = ee.ImageCollection('LANDSAT/' + sensor + '/C01/T1_SR')
                      .filterBounds(box)
                      .filter(ee.Filter.calendarRange(startYear, endYear, 'year'))
                      .filter(ee.Filter.calendarRange(startJulian, endJulian))
                      .select(sensorBandDict[sensor],bandNames)
    return srCollection
  })
  ls = ee.ImageCollection(ee.FeatureCollection(ls).flatten());
  
  
  maskWhat.map(function(what){
    print('Using Fmask to mask:',what)
    ls = ls.map(function(img){return cFmask(img,what)})
  })  
  ls = ls.select(['blue','green','red','nir','swir1','temp', 'swir2'])
  return ls
  // Map.addLayer(ls.median(),{'min':1000,'max':3500,'bands':'swir1,nir,red'})
}
////////////////////////////////////////////////////////////////////
// Function for computing the mean squared difference medoid from an image 
// collection
var  medoidMosaicMSD = function(inCollection,medoidIncludeBands) {
  if(medoidIncludeBands == null || medoidIncludeBands == undefined){
    medoidIncludeBands= ['blue','green','red','nir','swir1','swir2'];
  }
  // Find band names in first image
  var f = ee.Image(inCollection.first());
  var bandNames = f.bandNames();
  var bandNumbers = ee.List.sequence(1,bandNames.length());
  
  
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
};


////////////////////////////////////////////////////////////////////////////////
// Create composites for each year within startYear and endYear range
function compositeTimeSeries(ls,startYear,endYear,timebuffer,weights,compositingMethod){

  var ts = ee.List.sequence(startYear+timebuffer,endYear-timebuffer).getInfo()
    .map(function(year){
      
    // Set up dates
    var startYearT = year-timebuffer;
    var endYearT = year+timebuffer;
    // var startDateT = ee.Date.fromYMD(startYearT,1,1).advance(startJulian-1,'day');
    // var endDateT = ee.Date.fromYMD(endYearT,1,1).advance(endJulian-1,'day');
  
    // Filter images for given date range
    // var lsT = ls.filterDate(startDateT,endDateT);
    
    var yearsT = ee.List.sequence(startYearT,endYearT);
    
    var z = yearsT.zip(weights);
    var yearsTT = z.map(function(i){
      i = ee.List(i);
      return ee.List.repeat(i.get(0),i.get(1));
    }).flatten();
    // print(yearsTT)
    var images = yearsTT.map(function(yr){
      
      // Filter images for given date range
      var lsT = ls.filter(ee.Filter.calendarRange(yr,yr,'year'));
                // .filter(ee.Filter.calendarRange(startJulian,endJulian))//.toList(10000,0);
    return lsT;
    });
    var lsT = ee.ImageCollection(ee.FeatureCollection(images).flatten());
   
    // Compute median or medoid
    var composite;
    if (compositingMethod.toLowerCase() === 'median') {
      // print('Computing median');
      composite = lsT.median();
    }
    else {
      // print('Computing medoid');
      composite = medoidMosaicMSD(lsT,['blue','green','red','nir','swir1','swir2']);
    }
    composite = rescaleBands(composite);
    // Map.addLayer(composite,{'min':0.1,'max':0.35,'bands':'swir1,nir,red'},year.toString(),false);
    return composite.set('system:time_start',ee.Date.fromYMD(year,6,1).millis());
  });
  return ee.ImageCollection(ts);
}

// Function to properly rescale bands of a composite
function rescaleBands(composite){
  var template = composite;
  var compositeBands = composite.bandNames();
 
  var nonDivideBands = ee.List(['temp']);
  var composite10k = composite.select(compositeBands.removeAll(nonDivideBands))
    .divide(10000);
  composite = composite.select(nonDivideBands).addBands(composite10k).select(compositeBands);
 return composite;
}
 ///////////////////////////////////////////////////////////////////////////////
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
function simpleAddIndices(in_image){
    in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'red']).select([0],['NDVI']));
    in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'swir2']).select([0],['NBR']));
    in_image = in_image.addBands(in_image.normalizedDifference(['nir', 'swir1']).select([0],['NDMI']));
    in_image = in_image.addBands(in_image.normalizedDifference(['green', 'swir1']).select([0],['NDSI']));
  
    return in_image;
}
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
function simpleAddTCAngles(image){
  // Select brightness, greenness, and wetness bands
  var brightness = image.select(['brightness']);
  var greenness = image.select(['greenness']);
  var wetness = image.select(['wetness']);
  
  // Calculate Tasseled Cap angles and distances
  var tcAngleBG = brightness.atan2(greenness).divide(Math.PI).rename('tcAngleBG');
  // var tcAngleGW = greenness.atan2(wetness).divide(Math.PI).rename('tcAngleGW');
  // var tcAngleBW = brightness.atan2(wetness).divide(Math.PI).rename('tcAngleBW');
  // var tcDistBG = brightness.hypot(greenness).rename('tcDistBG');
  // var tcDistGW = greenness.hypot(wetness).rename('tcDistGW');
  // var tcDistBW = brightness.hypot(wetness).rename('tcDistBW');
  image = image.addBands(tcAngleBG);
  // .addBands(tcAngleGW)
  //   .addBands(tcAngleBW).addBands(tcDistBG).addBands(tcDistGW)
  //   .addBands(tcDistBW);
  return image;
}
///////////////////////////////////////////////////////////////////////////////
// Function to add 1/3 arcsec NED elevation and derived slope, aspect, eastness, and 
// northness to an image. Elevation is in meters, slope is between 0 and 90 deg,
// aspect is between 0 and 359 deg. Eastness and northness are unitless and are
// between -1 and 1.
function addTopography(img,region){
  // Import SRTM elevation data
  var elevation = ee.Image("USGS/NED");
  // Calculate slope, aspect, and hillshade
  var topo = ee.Algorithms.Terrain(elevation);
  topo = topo.clip(region);
  // From aspect (a), calculate eastness (sin a), northness (cos a)
  var deg2rad = ee.Number(Math.PI).divide(180);
  var aspect = topo.select('aspect');
  var aspect_rad = aspect.multiply(deg2rad);
  var eastness = aspect_rad.sin().rename('eastness').float();
  var northness = aspect_rad.cos().rename('northness').float();
  // Add topography bands to image
  topo = topo.select('elevation','slope','aspect')
    .addBands(eastness).addBands(northness);
  img = img.addBands(topo);
  return img;
}
////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
// Function to export a provided image to an EE asset
function exportToAssetWrapper(imageForExport,assetName,assetPath,
  pyramidingPolicy,roi,scale,crs,transform){
  //Make sure image is clipped to roi in case it's a multi-part polygon
  imageForExport = imageForExport.clip(roi);
  assetName = assetName.replace(/\s+/g,'-');//Get rid of any spaces
  var region = roi.bounds().getInfo().coordinates[0];
  Export.image.toAsset(imageForExport, assetName, assetPath, 
    {'.default': pyramidingPolicy}, null, region, scale, crs, transform, 1e13);
}

////////////////////////////////////////////////////////////////////////////////
// var startYear = 1985;
// var endYear = 1992;
// var startJulian = 190;
// var endJulian = 250;
// var studyArea = fnf;
// var timeBuffer = 0;
// var weights =[1];// [1,5,1];
// var compositingMethod = 'medoid';
// var ls = getLandsat(startYear,endYear,startJulian,endJulian,studyArea);

// var ts = compositeTimeSeries(ls,startYear,endYear,timeBuffer,weights,compositingMethod)
// 

// ts = ts
//   .map(rescaleBands)
//   .map(addIndices)
//   .map(function(img){
//     img = getTasseledCap(img);
//     img = addTCAngles(img);
//     img = addTopography(img,studyArea);
//     return img;
//   });
// var nd = ts.select(['ND_nir_swir2'])
// // .map(function(img){
// //   var out = img.multiply(-1)
// //   return out.copyProperties(img,['system:time_start'])});
// Map.addLayer(nd,{},'ts',false)


function getExistingChangeData(changeThresh,showLayers){
  if(showLayers === undefined || showLayers === null){
    showLayers = true;
  }
  if(changeThresh === undefined || changeThresh === null){
    changeThresh = 50;
  }
  var startYear = 1985;
  var endYear = 2016;
  
  
  
  var glriEnsemble = ee.Image('projects/glri-phase3/changeMaps/ensembleOutputs/NBR_NDVI_TCBGAngle_swir1_swir2_median_LT_Ensemble');
  
  
  
  
  
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
  Map.addLayer(conusChange.select(['change']).max(),{'min':startYear,'max':endYear,'palette':'FF0,F00'},'CONUS LCMS',true);
  Map.addLayer(conusChange.select(['probability']).max(),{'min':0,'max':50,'palette':'888,008'},'LCMSC',false);
  }
  var glri_lcms = glriEnsemble.updateMask(glriEnsemble.select([0])).select([1]);
  glri_lcms = glri_lcms.updateMask(glri_lcms.gte(startYear).and(glri_lcms.lte(endYear)));
  if(showLayers){
  // Map.addLayer(glri_lcms,{'min':startYear,'max':endYear,'palette':'FF0,F00'},'GLRI LCMS',false);
  }
  
  
  
  var hansen = ee.Image('UMD/hansen/global_forest_change_2016_v1_4').select(['lossyear']).add(2000).int16();
  hansen = hansen.updateMask(hansen.neq(2000).and(hansen.gte(startYear)).and(hansen.lte(endYear)));
  if(showLayers){
  Map.addLayer(hansen,{'min':startYear,'max':endYear,'palette':'FF0,F00'},'Hansen',false);
  }
  return conusChangeOut;
}
////////////////////////////////////////////////////////
exports.getExistingChangeData =  getExistingChangeData;


exports.bt = bt;exports.fnf = fnf
exports.getLandsat = getLandsat;
exports.compositeTimeSeries = compositeTimeSeries;
exports.rescaleBands = rescaleBands;
exports.addIndices = addIndices;
exports.addDateBand = addDateBand
exports.simpleAddIndices = simpleAddIndices;
exports.simpleAddTCAngles = simpleAddTCAngles;
exports.getTasseledCap = getTasseledCap;
exports.addTCAngles = addTCAngles;
exports.addTopography = addTopography;
exports.crs = 'EPSG:5070';
exports.transform = [30,0,-2361915.0,0,-30,3177735.0];
exports.exportToAssetWrapper = exportToAssetWrapper;