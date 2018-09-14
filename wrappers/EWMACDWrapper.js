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
var startYear = 2000;
var endYear = 2018;

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


//List of bands or indices to iterate across
//Typically a list of spectral bands or computed indices
//Can include: 'blue','green','red','nir','swir1','swir2'
//'NBR','NDVI','wetness','greenness','brightness','tcAngleBG'
// var indexList = ee.List(['nir','swir1']);
var indexList = ['NBR','NDVI'];//['nir','swir1','swir2','NDMI',NBR','NDVI','wetness','greenness','brightness','tcAngleBG'];


///////////////////////////////////////////////////////////////////////
//EWMACD Parameters


//Expected frequency of phenological cycles. 
//harmonicCount is n pi so 1 cycle/yr is 2 
var harmonicCount = 1;

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
var indexNames = ['NBR'];//['blue','green','red','nir','swir1','swir2','NDMI','NDVI','NBR','tcAngleBG']

var processedScenes = getImageLib.getProcessedLandsatScenes(studyArea,startYear,endYear,startJulian,endJulian,
  
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
  applyFmaskCloudShadowMask,applyFmaskSnowMask,
  cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels
  )
  
function addPrefixToImage(i,prefix){
  var bandNames = i.bandNames();
	var outBandNames = bandNames.map(function(i){return ee.String(prefix).cat(i)});
	return i.select(bandNames,outBandNames);
}


var trainingStartYear = 2000;
var trainingEndYear = 2004;


indexNames.map(function(indexName){
  var lsIndex = processedScenes.select(indexName);
 
 
 
//Apply EWMACD
var ewmaOutputs = dLib.runEWMACD(lsIndex,indexName,startYear,endYear,trainingStartYear,trainingEndYear,harmonicCount,annualReducer,!includeSLCOffL7);
// var annualEWMA = ewmaOutputs[1]//.map(function(img){return dLib.multBands(img,1,0.01)});
var ewmaRaw = ewmaOutputs[0]
  Map.addLayer(ewmaRaw,{},indexName + ' ewma',false);
//   if(outputCollection === undefined){
//     outputCollection = annualEWMA
//   }else{
//     outputCollection = getImageLib.joinCollections(outputCollection,annualEWMA,false);
//   }
  
  
// });
})


// var years = ee.List.sequence(startYear,endYear).getInfo();

//   years.map(function(year){
//     var ewmaYr = ee.Image(outputCollection.filter(ee.Filter.calendarRange(year,year,'year')).first())
//     .int16();
    


//   var exportName = outputName+'_' + year.toString();
//     var exportPath = exportPathRoot + '/'+exportName
    
//     getImageLib.exportToAssetWrapper(ewmaYr,exportName,exportPath,'mean',
//       studyArea,null,crs,transform);
//   });
