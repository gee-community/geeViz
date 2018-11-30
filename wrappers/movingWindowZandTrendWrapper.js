/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #d63000 */ee.Geometry.Polygon(
        [[[-114.64614410458967, 46.78379503331787],
          [-114.71206207333967, 45.605104594235314],
          [-111.82265777646467, 45.55127657199464],
          [-111.98745269833967, 46.72357800019127]]]);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
//Wrapper for running z-score and linear trend across a moving window of years

//Module imports
var getImageLib = require('users/USFS_GTAC/modules:getImagesLib.js');
var dLib = require('users/USFS_GTAC/modules:changeDetectionLib.js');
///////////////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
dLib.getExistingChangeData();
// Define user parameters:

// 1. Specify study area: Study area
// Can specify a country, provide a fusion table  or asset table (must add 
// .geometry() after it), or draw a polygon and make studyArea = drawnPolygon
var studyArea =geometry;

// 2. Update the startJulian and endJulian variables to indicate your seasonal 
// constraints. This supports wrapping for tropics and southern hemisphere.
// startJulian: Starting Julian date 
// endJulian: Ending Julian date
var startJulian = 190;
var endJulian = 270

// 3. Specify start and end years for all analyses
// More than a 3 year span should be provided for time series methods to work 
// well. If using Fmask as the cloud/cloud shadow masking method, this does not 
// matter
var startYear = 1984;
var endYear = 2018;



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
// var outputName = 'Test_Z_';

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


////////////////////////////////////////////////
//Moving window parameters

//Parameters used for both z and trend analyses

//Number of julian days for each analysis
//Generally want it to be >= 32 or the output will be noisy
//Should almost never be less than 16
var nDays = 80;

//Which bands/indices to run the analysis with
//Can be any of ['blue','green','red','nir','swir1','swir2','NDMI','NDVI','NBR','NDSI','tcAngleBG']
var indexNames = ['NBR','NDVI'];//['nir','swir1','swir2','NDMI','NDVI','NBR','tcAngleBG'];//['blue','green','red','nir','swir1','swir2','NDMI','NDVI','NBR','tcAngleBG'];

//Whether each output should be exported to asset
var exportImages = false;

////////////////////////////////////
//Moving window z parameters

//Number of years in baseline
//Generally 5 years works best in the Western CONUS and 3 in the Eastern CONUS
var baselineLength = 5;

//Number of years between the analysis year and the last year of the baseline
//This helps ensure the z-test is being performed data that are less likely to be 
//temporally auto-correlated
//E.g. if the analysis year is 1990, the last year of the baseline would be 1987
//Set to 0 if the last year of the baseline needs to be the year just before the analysis year
var baselineGap = 5;

//Number of cloud/cloud shadow free observations necessary to have in the baseline for a 
//pixel to run the analysis for a given year
//Generally 5-30 works well.  If false positives are prevalant, use something toward 30
//If there are too many holes in the outputs where data are sparse, this method may not work, but try 
//using a lower minBaselineObservationsNeeded
var minBaselineObservationsNeeded = 10;

//Since there could be multiple z values for a given pixel on a given analysis period, how to summarize
//Generally use ee.Reducer.mean() or ee.Reducer.median()
var zReducer = ee.Reducer.mean();

//Whether to reduce the collection to an annual median stack
//Since linear regression can be leveraged by outliers, this generally
//improves the trend analysis, but does get rid of a lot of potentially
//good data
var useAnnualMedianForTrend = true;
////////////////////////////////////
//Moving window trend parameters

//Number of years in a given trend analysis inclusive of the analysis year
//E.g. if the analysis year was 1990 and the epochLength was 5, 
//the years included in the trend analysis would be 1986,1987,1988,1989, and 1990
var epochLength =10;


////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
//Function Calls
//Get all images
var allScenes = getImageLib.getProcessedLandsatScenes(studyArea,startYear,endYear,startJulian,endJulian,
  
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
  applyFmaskCloudShadowMask,applyFmaskSnowMask,
  cloudScoreThresh,cloudScorePctl,
  zScoreThresh,shadowSumThresh,
  contractPixels,dilatePixels
  ).select(indexNames);


////////////////////////////////////////////////////////////


var zAndTrendCollection = 
dLib.zAndTrendChangeDetection(allScenes,indexNames,nDays,startYear,endYear,startJulian,endJulian,
          baselineLength,baselineGap,epochLength,zReducer,useAnnualMedianForTrend,
          exportImages,exportPathRoot,studyArea,scale,crs,transform,minBaselineObservationsNeeded);
          
dLib.thresholdZAndTrend(zAndTrendCollection,-5*10,-0.05*10000,startYear,endYear);
dLib.thresholdZAndTrend(zAndTrendCollection,-3*10,-0.03*10000,startYear,endYear,'positive');

var allotments = ee.FeatureCollection('projects/USFS/LCMS-NFS/R1/FNF/Ancillary/R1_Allotments_w_RPMS_Monitoring_data_1984_to_2018')
                  .reduceToImage(['Corr'], ee.Reducer.first())
Map.addLayer(allotments,{min:0,max:1,palette:'FF0,0F0'},'Allotments',false);