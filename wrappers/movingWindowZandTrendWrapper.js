/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #d63000 */ee.Geometry.Polygon(
        [[[-114.47916369631713, 48.7444187437357],
          [-114.42697863772338, 48.39000318609775],
          [-113.31735949709838, 48.51205685707847],
          [-113.28989367678588, 48.84935559144764]]]);
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
var endJulian = 250

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
var nDays = 60;

//Which bands/indices to run the analysis with
//Can be any of ['blue','green','red','nir','swir1','swir2','NDMI','NDVI','NBR','NDSI','tcAngleBG']
var indexNames = ['NBR','NDVI'];//['nir','swir1','swir2','NDMI','NDVI','NBR','tcAngleBG'];//['blue','green','red','nir','swir1','swir2','NDMI','NDVI','NBR','tcAngleBG'];


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
var baselineGap = 2;

//Since there could be multiple z values for a given pixel on a given analysis period, how to summarize
//Generally use ee.Reducer.mean() or ee.Reducer.median()
var zReducer = ee.Reducer.mean();

////////////////////////////////////
//Moving window trend parameters

//Number of years in a given trend analysis inclusive of the analysis year
//E.g. if the analysis year was 1990 and the epochLength was 5, 
//the years included in the trend analysis would be 1986,1987,1988,1989, and 1990
var epochLength = 5;


////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
//Function Calls
//Get all images
var allScenes = getImageLib.getProcessedLandsatScenes(studyArea,startYear,endYear,startJulian,endJulian,
  
  toaOrSR,includeSLCOffL7,defringeL5,applyCloudScore,applyFmaskCloudMask,applyTDOM,
  applyFmaskCloudShadowMask,applyFmaskSnowMask,
  cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels
  ).select(indexNames);


////////////////////////////////////////////////////////////
//Iterate across each time window and do a z-score and trend analysis

//House-keeping
var dummyScene = ee.Image(allScenes.first());
var outNames = indexNames.map(function(bn){return ee.String(bn).cat('_Z')});
var analysisStartYear = Math.max(startYear+baselineLength+baselineGap,startYear+epochLength-1);

//Iterate across each year and perform analysis
var zAndTrendCollection = ee.List.sequence(analysisStartYear,endYear,1).map(function(yr){
  yr = ee.Number(yr);
  
  //Set up the baseline years
  var blStartYear = yr.subtract(baselineLength).subtract(baselineGap);
  var blEndYear = yr.subtract(1).subtract(baselineGap);
  
  //Set up the trend years
  var trendStartYear = yr.subtract(epochLength).add(1);
  
  //Iterate across the julian dates
  return ee.FeatureCollection(ee.List.sequence(startJulian,endJulian-nDays,nDays).map(function(jd){
    
    jd = ee.Number(jd);
    
    //Set up the julian date range
    var jdStart = jd;
    var jdEnd = jd.add(nDays);
    
    //Get the baseline images
    var blImages = allScenes.filter(ee.Filter.calendarRange(blStartYear,blEndYear,'year'))
                            .filter(ee.Filter.calendarRange(jdStart,jdEnd));
    blImages = getImageLib.fillEmptyCollections(blImages,dummyScene);
    
    
    //Get the z analysis images
    var analysisImages = allScenes.filter(ee.Filter.calendarRange(yr,yr,'year'))
                            .filter(ee.Filter.calendarRange(jdStart,jdEnd)); 
    analysisImages = getImageLib.fillEmptyCollections(analysisImages,dummyScene);
    
    //Get the images for the trend analysis
    var trendImages = allScenes.filter(ee.Filter.calendarRange(trendStartYear,yr,'year'))
                            .filter(ee.Filter.calendarRange(jdStart,jdEnd));
    trendImages = getImageLib.fillEmptyCollections(trendImages,dummyScene);
    
    //Perform the linear trend analysis
    var linearTrend = dLib.getLinearFit(trendImages,indexNames);
    var linearTrendModel = ee.Image(linearTrend[0]).select(['.*_slope']);
    
    //Perform the z analysis
    var blMean = blImages.mean();
    var blStd = blImages.reduce(ee.Reducer.stdDev());
    
    var analysisImagesZ = analysisImages.map(function(img){
      return (img.subtract(blMean)).divide(blStd);
    }).reduce(zReducer).rename(outNames);
    
    //Set up the output
    var outName = ee.String('Z_and_Trend_b').cat(ee.String(blStartYear.int16())).cat(ee.String('_'))
                                .cat(ee.String(blEndYear.int16())).cat(ee.String('_epoch')).cat(ee.String(epochLength)).cat(ee.String('_y')).cat(ee.String(yr.int16())).cat(ee.String('_'))
                                .cat(ee.String(jdStart.int16())).cat(ee.String('_')).cat(ee.String(jdEnd.int16()))
    
    var out = analysisImages.reduce(zReducer).rename(indexNames).addBands(analysisImagesZ).addBands(linearTrendModel)
          .set({'system:time_start':ee.Date.fromYMD(yr,1,1).advance(jdStart,'day').millis(),
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
    
    return out;
  }));
});

function thresholdZAndTrend(zAndTrendCollection,zThresh,slopeThresh){
  var zCollection = zAndTrendCollection.select('.*_Z');
  var trendCollection = zAndTrendCollection.select('.*_slope');
  var zChange = dLib.thresholdChange(zCollection,-zThresh,-1).select('.*_change');
  var trendChange = dLib.thresholdChange(trendCollection,-slopeThresh,-1).select('.*_change');
  
  Map.addLayer(zAndTrendCollection,{},'zAndTrendCollection',false);
  Map.addLayer(zChange.max().select([0]),{'min':startYear,'max':endYear,'palette':'FF0,F00'},'zChangeMax',false);
  Map.addLayer(trendChange.max().select([0]),{'min':startYear,'max':endYear,'palette':'FF0,F00'},'trendChangeMax',false);

}


zAndTrendCollection = ee.ImageCollection(ee.FeatureCollection(zAndTrendCollection).flatten());
thresholdZAndTrend(zAndTrendCollection,-5,-0.05)
var zAndTrendCollectionL = zAndTrendCollection.toList(100);
print(zAndTrendCollection)
// zAndTrendCollection.size().evaluate(function(count){
//   ee.List.sequence(0,count-1).getInfo().map(function(i){
//     var image = ee.Image(zAndTrendCollectionL.get(i));
//     var blStartYear = image.get('baselineStartYear').getInfo();
//     var blEndYear = image.get('baselineEndYear').getInfo();
//     var yr = image.get('year').getInfo();
//     var jdStart = image.get('startJulian').getInfo();
//     var jdEnd = image.get('endJulian').getInfo();
//     print(image)
//     // Export image
//     var outName = outputName + '_b'+ blStartYear.toString() + '_' + blEndYear.toString() + '_'+yr.toString() + '_'+jdStart.toString() + '_'+ jdEnd.toString();
//     print(outName)
//     // var outPath = exportPathRoot + '/' + outName;
//     // getImageLib.exportToAssetWrapper(out,outName,outPath,
//       // 'mean',studyArea,scale,crs,transform);
//   })
// });
