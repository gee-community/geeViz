/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #d63000 */ee.Geometry.Polygon(
        [[[-110.379638671875, 43.124651636825526],
          [-109.76303100585938, 43.02333341039862],
          [-109.88937377929688, 43.26281560929387],
          [-110.52932739257812, 43.32878344623762],
          [-110.51010131835938, 43.210790549591735]]]);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
//Module imports
var getImageLib = require('users/USFS_GTAC/modules:getImagesLib.js');
var dLib = require('users/USFS_GTAC/modules:changeDetectionLib.js');
///////////////////////////////////////////////////////////////////////////////
// Define user parameters:
dLib.getExistingChangeData();
// 1. Specify study area: Study area
// Can specify a country, provide a fusion table  or asset table (must add 
// .geometry() after it), or draw a polygon and make studyArea = drawnPolygon
var rio = ee.FeatureCollection('users/ianhousman/RIO/Rio_Grande_NF_Boundary_10kBuffer_albers_diss').geometry();
var fnf = ee.FeatureCollection('projects/USFS/LCMS-NFS/R1/FNF/FNF_GNP_Merge_Admin_BND_1k').geometry();
var bt = ee.FeatureCollection('projects/USFS/LCMS-NFS/R4/BT/BT_LCMS_ProjectArea_5km').geometry();
var studyArea = geometry;

// 2. Update the startJulian and endJulian variables to indicate your seasonal 
// constraints. This supports wrapping for tropics and southern hemisphere.
// startJulian: Starting Julian date 
// endJulian: Ending Julian date
var startJulian = 190;
var endJulian = 250; 

// 3. Specify start and end years for all analyses
// More than a 3 year span should be provided for time series methods to work 
// well. If using Fmask as the cloud/cloud shadow masking method, this does not 
// matter
var startYear = 2000;
var endYear = 2017;

// 4. Specify an annual buffer to include imagery from the same season 
// timeframe from the prior and following year. timeBuffer = 1 will result 
// in a 3 year moving window
var timebuffer = 1;

// 5. Specify the weights to be used for the moving window created by timeBuffer
//For example- if timeBuffer is 1, that is a 3 year moving window
//If the center year is 2000, then the years are 1999,2000, and 2001
//In order to overweight the center year, you could specify the weights as
//[1,5,1] which would duplicate the center year 5 times and increase its weight for
//the compositing method
var weights = [1,3,1];



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
var outputName = 'Medoid-Landsat';

//Provide location composites will be exported to
//This should be an asset folder, or more ideally, an asset imageCollection
var exportPathRoot = 'users/ianhousman/test';



//CRS- must be provided.  
//Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
//WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
var crs = 'EPSG:5070';

//Specify transform if scale is null and snapping to known grid is needed
var transform = [30,0,-2361915.0,0,-30,3177735.0];

//Specify scale if transform is null
var scale = null;


////////////////////////////////////////////////////////////
//Landtrendr params
//Param documentation:
// reference: Kennedy, R. E., Yang, Z., & Cohen, W. B. (2010). Detecting trends in forest disturbance and recovery using yearly Landsat time series: 1. LandTrendr—Temporal segmentation algorithms. Remote Sensing of Environment, 114(12), 2897-2910.
//https://github.com/eMapR/LT-GEE
//From: http://www.mdpi.com/2072-4292/10/5/691
// Table 1. LandTrendr parameters used for IDL and GEE runs in all study areas. The NBR spectral metric was used for segmentation. For descriptions of the parameters, see [3]).
// Parameter	IDL	GEE	Comments
// maxSegments	6	6	
// spikeThreshold	0.9	0.9	Renamed from “desawtooth val”
// vertexCountOvershoot	3	3	
// recoveryThreshold	0.25	0.25	
// pvalThreshold	0.05	0.05	
// bestModelProportion	0.75	0.75	
// minObservationsNeeded	6	6	Renamed from “minneeded”
// Background_val	0	NA	GEE uses a mask logic to avoid missing values caused by clouds, shadows, and missing imagery.
// Divisor	−1	NA	Ensures that vegetation loss disturbance results in negative change in value when NBR is used as a spectral metric. In GEE, this must be handled outside of the segmentation algorithm.
// Kernelsize	1	Dropped	Originally used together with skipfactor to save computational burden; no longer necessary.
// Skipfactor	1	Dropped
// Distweightfactor	2	Dropped	Inadvertently hardwired in the IDL code, this parameter was hardwired in the GEE code to the value of 2.
// Fix_doy_effect	1	Dropped	Although correcting day-of-year trends was considered theoretically useful in the original LT implementation, in practice it has been found to distort time series values when change occurs and thus was eliminated.


//Define landtrendr params
var run_params = { 
  maxSegments:            6,
  spikeThreshold:         0.9,
  vertexCountOvershoot:   3,
  preventOneYearRecovery: true,
  recoveryThreshold:      0.25,
  pvalThreshold:          0.05,
  bestModelProportion:    0.75,
  minObservationsNeeded:  6
};

//Define disturbance mapping filter parameters 
var treeLoss1  = 1;      //150 delta filter for 1 year duration disturbance, <= will not be included as disturbance - units are in units of segIndex defined in the following function definition
var treeLoss20 = 200;      //200 delta filter for 20 year duration disturbance, <= will not be included as disturbance - units are in units of segIndex defined in the following function definition
var preVal     = 1;      //200 pre-disturbance value threshold - values below the provided threshold will exclude disturbance for those pixels - units are in units of segIndex defined in the following function definition
var mmu        = 15;       //15 minimum mapping unit for disturbance patches - units of pixels

var distParams = {
    tree_loss1: treeLoss1,
    tree_loss20: treeLoss20,  
    pre_val: preVal           
  };



var distDir = -1; // define the sign of spectral delta for vegetation loss for the segmentation index - 
                  // NBR delta is negetive for vegetation loss, so -1 for NBR, 1 for band 5, -1 for NDVI, etc

var indexName = 'NBR';



///////////////////////////////////////////////////////////////////////
//EWMACD Parameters

//Number of years to include at the beginning of the time series to train
//the harmonic regression model.
//Generally 3-5 works well
var ewmacdTrainingYears = 5;

//Expected frequency of phenological cycles. 
//harmonicCount is n pi so 1 cycle/yr is 2 
var harmonicCount = 2;

//When simplifying from all EWMA values to annual values
//this is the reducer that is applied.  Generally will want to pull from the 
//bottom quadrant
var annualReducer = ee.Reducer.percentile([10])

///////////////////////////////////////////////////////////////////////
// End user parameters
///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
//Start function calls

////////////////////////////////////////////////////////////////////////////////
//Call on master wrapper function to get Landat scenes and composites
var lsAndTs = getImageLib.getLandsatWrapper(studyArea,startYear,endYear,startJulian,endJulian,
  timebuffer,weights,compositingMethod,
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
  applyFmaskCloudShadowMask,applyFmaskSnowMask,
  cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels,
  correctIllumination,correctScale,
  exportComposites,outputName,exportPathRoot,crs,transform,scale);

//Separate into scenes and composites for subsequent analysis
var processedScenes = lsAndTs[0];
var processedComposites = lsAndTs[1];

//Get all images from the entire year for EWMACD 
var lsAndTsAll = getImageLib.getLandsatWrapper(studyArea,startYear+timebuffer,endYear-timebuffer,1,365,
  timebuffer,weights,compositingMethod,
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
  applyFmaskCloudShadowMask,true,
  cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels,
  correctIllumination,correctScale,
  false,outputName,exportPathRoot,crs,transform,scale);

//Separate into scenes and composites for subsequent analysis
var allScenes = lsAndTsAll[0];


var indexList = ee.List(['nir','swir1']);//ee.List(['nir','swir1','swir2','NBR','NDVI','wetness','greenness','brightness','tcAngleBG']);
var ltDirection = ee.List([-1,    1]);//ee.List([-1,    1,      1,    -1,    -1,   -1,           -1,        1,          -1]);
var indexDirList = indexList.zip(ltDirection).getInfo();

indexDirList.map(function(indexDir){
  print(indexDir);
  var indexName = indexDir[0];
  var distDir = indexDir[1];
  
  var tsIndex = processedComposites.select(indexName);
  var lsIndex = allScenes.select(indexName);
 
 
  //Apply LANDTRENDR
  var ltOutputs = dLib.landtrendrWrapper(processedComposites,indexName,distDir,run_params,distParams,mmu);
  var rawLT = ltOutputs[0].select([0]);
  var ltAnnualSlope = dLib.landtrendrToAnnualSlope(rawLT,startYear,endYear,timebuffer);
  
  //Apply VERDET
  var verdetOutputs = dLib.verdetAnnualSlope(tsIndex,startYear,endYear,timebuffer);
  
  function pairwiseSlope(c){
    c = c.sort('system:time_start');
    
    var bandNames = ee.Image(c.first()).bandNames();
    bandNames = bandNames.map(function(bn){return ee.String(bn).cat('_slope')})
    var years = c.toList(10000).map(function(i){i = ee.Image(i);return ee.Date(i.get('system:time_start')).get('year')});
    
    var yearsLeft = years.slice(0,-1);
    var yearsRight = years.slice(1,null);
    var yearPairs = yearsLeft.zip(yearsRight);
    
    var slopeCollection = yearPairs.map(function(yp){
      yp = ee.List(yp);
      var yl = ee.Number(yp.get(0));
      var yr = ee.Number(yp.get(1));
      var yd = yr.subtract(yl);
      var l = ee.Image(c.filter(ee.Filter.calendarRange(yl,yl,'year')).first()).add(0.00001);
      var r = ee.Image(c.filter(ee.Filter.calendarRange(yr,yr,'year')).first());
      
      var slope = (r.subtract(l)).rename(bandNames);
      slope = slope.set('system:time_start',ee.Date.fromYMD(yr,6,1).millis());
      return slope;
    });
    return ee.ImageCollection.fromImages(slopeCollection);
  }
  //Apply EWMACD
  var ewmaOutputs = dLib.runEWMACD(lsIndex,startYear+timebuffer,endYear-timebuffer,ewmacdTrainingYears,harmonicCount,annualReducer,!includeSLCOffL7);
  var annualEWMA = ewmaOutputs[1].map(function(img){return dLib.multBands(img,1,0.01)});
  
  var changeOutputs = getImageLib.joinCollections(ltAnnualSlope,verdetOutputs);
  // var changeOutputs = getImageLib.joinCollections(changeOutputs,annualEWMA);
  
  var tsIndexSlope = pairwiseSlope(tsIndex);
  var annualEWMASlope = pairwiseSlope(annualEWMA);
  
  // changeOutputs = getImageLib.joinCollections(changeOutputs,tsIndex);
  changeOutputs = getImageLib.joinCollections(changeOutputs,tsIndexSlope);
  changeOutputs = getImageLib.joinCollections(changeOutputs,annualEWMASlope);
  
  Map.addLayer(changeOutputs,{},'changeOutputs',false);
  Map.addLayer(annualEWMA,{},'annualEWMA',false);
  Map.addLayer(annualEWMASlope,{},'annualEWMASlope',false);
  Map.addLayer(tsIndexSlope,{},'tsIndexSlope',false);
  
  Map.addLayer(ltAnnualSlope,{},'ltAnnualSlope',false);
  Map.addLayer(verdetOutputs,{},'verdetOutputs',false);
  
  
});
// ////////////////////////////////////////////////////////////////////////////////////////////////////
// ////////////////////////////////////////////////////////////////////////////////////////////////////
// ////////////////////////////////////////////////////////////////////////////////////////////////////
// ////////////////////////////////////////////////////////////////////////////////////////////////////

// /////////////////////////////////////////////////////////////


// ////////////////////////////////////////////////////////////////////////////////////////////////////
// ////////////////////////////////////////////////////////////////////////////////////////////////////
// ////////////////////////////////////////////////////////////////////////////////////////////////////
// ////////////////////////////////////////////////////////////////////////////////////////////////////
// //Verdet
// // var verdetTsIndex = processedComposites.select([indexName])
// // var verdetTs = verdetTsIndex.map(getImageLib.addDateBand);
// // var verdet =   ee.Algorithms.TemporalSegmentation.Verdet({timeSeries: verdetTsIndex,
// // //                                         tolerance: 0.0001,
// // //                                         alpha: 1/3.0})
// // verdet = verdet.arraySlice(0,1,null)
// // // var tsYear = verdetTs.select([1]).toArray().arraySlice(0,0,-1).arrayProject([0])

// // Map.addLayer(verdet.arrayCat(tsYear,1))
// // var verdetLeft = verdet.arraySlice(0,0,-1)
// // var verdetRight = verdet.arraySlice(0,1,null);
// // var verdetDiff = verdetRight.subtract(verdetLeft)
// // var yearsLeft = tsYear.arraySlice(0,0,-1)
// // var yearsRight = tsYear.arraySlice(0,1,null)
// // var isVertex = verdetDiff.gt(0.00000001).or(verdetDiff.lt(-0.00000001))
// // var isEndVertex = verdetDiff.gt(0.00000001)
// // verdetLeft = verdetLeft.arrayMask(isVertex);
// // verdetRight = verdetRight.arrayMask(isVertex);
// // verdetDiff = verdetDiff.arrayMask(isEndVertex);
// // yearsLeft = yearsLeft.arrayMask(isEndVertex)
// // yearsRight = yearsRight.arrayMask(isEndVertex)
// // verdet = verdetRight.arrayCat(yearsRight,1)

// // var changeYear = yearsRight;
// // var changeMag = verdetDiff
// // // verdet = verdetDiff.arrayCat(isVertex,1)//.arrayCat(verdetDiff,1)
// // // var verdetValues = verdet.reduceRegion(ee.Reducer.first(),geometry, 30, 'EPSG:5070', null,true, 1,1).get('score')

// // // // var verdetGraph = ui.Chart.array.values(verdetValues, 0);
// // // // verdetGraph = verdetGraph.setChartType('ScatterChart')
// // // // print(verdetGraph)
// // // // Map.addLayer(tsIndex,{},'tsIndex',false);
// // // Map.addLayer(verdet)

// // // Map.addLayer(verdetTsIndex,{},'VERDET-ts'+indexName,false);
// // // Map.addLayer(verdet,{},'VERDET-'+indexName,false);
// // Map.addLayer(changeYear);
// // Map.addLayer(changeMag,{'min':0,'max':0.2})

// // // tsYear = tsYear.arraySlice(0,1,null)
// ///////////////////////////////////////////////////////////////////////////////

// var lsIndex = allScenes.select([indexName]);
// Map.addLayer(lsIndex,{},'ls'+indexName,false);




// var ewmaOutputs = dLib.runEWMACD(lsIndex,startYear,endYear,ewmacdTrainingYears,harmonicCount,annualReducer,!includeSLCOffL7);
// var annualEWMA = ewmaOutputs[1].map(function(img){return dLib.multBands(img,1,0.01)});
// var joinedEWMA = getImageLib.joinCollections(processedComposites.select(['NBR']),annualEWMA)
// Map.addLayer(joinedEWMA,{},'annualewma',false);
  