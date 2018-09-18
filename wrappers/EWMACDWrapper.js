/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #d63000 */ee.Geometry.Polygon(
        [[[-122.91349669443616, 40.98973589629366],
          [-123.02335997568616, 40.4652228774622],
          [-122.01261778818616, 40.481937594544576],
          [-122.00163146006116, 40.931660898201365]]]);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
//Module imports
var getImageLib = require('users/USFS_GTAC/modules:getImagesLib.js');
var dLib = require('users/USFS_GTAC/modules:changeDetectionLib.js');
///////////////////////////////////////////////////////////////////////////////
dLib.getExistingChangeData();
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
var endYear = 2000;





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
var exportPathRoot = 'users/ianhousman/test/changeCollection';

// var exportPathRoot = 'projects/USFS/LCMS-NFS/R4/BT/Base-Learners/Base-Learners-Collection';
//CRS- must be provided.  
//Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
//WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
var crs = 'EPSG:5070';

//Specify transform if scale is null and snapping to known grid is needed
var transform = [30,0,-2361915.0,0,-30,3177735.0];

//Specify scale if transform is null
var scale = null;


////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
//EWMACD Parameters


//Expected frequency of phenological cycles. 
//harmonicCount is n pi so 1 cycle/yr is 2 
var harmonicCount = 2;

//When simplifying from all EWMA values to annual values
//this is the reducer that is applied.  Generally will want to pull from the 
//bottom quadrant
var annualReducer = ee.Reducer.percentile([10]);

//List of bands or indices to iterate across
//Typically a list of spectral bands or computed indices
//Can include: 'blue','green','red','nir','swir1','swir2'
//'NBR','NDVI','wetness','greenness','brightness','tcAngleBG'
// var indexList = ee.List(['nir','swir1']);
var indexNames = ['NBR','SAVI','EVI'];//['NBR','blue','green','red','nir','swir1','swir2','NDMI','NDVI','wetness','greenness','brightness','tcAngleBG'];

//Year range to train harmonic regression model with
var trainingStartYear = 1984;
var trainingEndYear = 1989;

///////////////////////////////////////////////////////////////////////
// End user parameters
///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
//Start function calls

////////////////////////////////////////////////////////////////////////////////
//Call on master wrapper function to get Landat scenes and composites
var processedScenes = getImageLib.getProcessedLandsatScenes(studyArea,startYear,endYear,startJulian,endJulian,
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
  applyFmaskCloudShadowMask,applyFmaskSnowMask,
  cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels
  ).map(getImageLib.addSAVIandEVI);
  

//Get EWMACD values for each index/band
var outputCollection;
indexNames.map(function(indexName){
  var lsIndex = processedScenes.select(indexName);
 
  //Apply EWMACD
  var ewmaOutputs = dLib.runEWMACD(lsIndex,indexName,startYear,endYear,trainingStartYear,trainingEndYear,harmonicCount,annualReducer,!includeSLCOffL7);
  var annualEWMA = ewmaOutputs[1];
  
  var ewmaChange = dLib.thresholdChange(annualEWMA,3,-1).select('.*_change');
  Map.addLayer(annualEWMA,{},indexName + ' ewma',false);
  Map.addLayer(ewmaChange.min().select([0]),{'min':startYear,'max':endYear,'palette':'FF0,F00'},indexName + ' EWMA First Change Year',false);
    
    if(outputCollection === undefined){
      outputCollection = annualEWMA;
    }else{
      outputCollection = getImageLib.joinCollections(outputCollection,annualEWMA,false);
    }

});

//Export each years EWMACD output
// var years = ee.List.sequence(startYear,endYear).getInfo();

//   years.map(function(year){
//     var ewmaYr = ee.Image(outputCollection.filter(ee.Filter.calendarRange(year,year,'year')).first())
//     .int16();
    
//   var exportName = outputName+'_' + year.toString();
//     var exportPath = exportPathRoot + '/'+exportName;
    
//     getImageLib.exportToAssetWrapper(ewmaYr,exportName,exportPath,'mean',
//       studyArea,null,crs,transform);
//   });
var ewmaOut = ee.ImageCollection('users/ianhousman/test/changeCollection');
Map.addLayer(ewmaOut)
ewmaOut = dLib.thresholdChange(ewmaOut,5,-1)
Map.addLayer(ewmaOut.select([5]).min(),{'min':1984,'max':2018,'palette':'FF0,F00'})