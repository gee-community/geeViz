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
var outputName = 'Test_Z_';

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
//Moving window z parameters

var nDays = 60;
var baselineLength = 5;
var baselineGap = 2;

var zReducer = ee.Reducer.mean();


var epochLength = 5;
//Which bands/indices to run z score on
var indexNames = ['NBR','NDVI'];//['nir','swir1','swir2','NDMI','NDVI','NBR','tcAngleBG'];//['blue','green','red','nir','swir1','swir2','NDMI','NDVI','NBR','tcAngleBG'];

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
//Iterate across each time window and fit harmonic regression model
var dummyScene = ee.Image(allScenes.first());
var outNames = indexNames.map(function(bn){return ee.String(bn).cat('_Z')});
var zAndTrendCollection = ee.List.sequence(startYear+baselineLength+baselineGap,endYear,1).map(function(yr){
  yr = ee.Number(yr);
  var blStartYear = yr.subtract(baselineLength).subtract(baselineGap);
  var blEndYear = yr.subtract(1).subtract(baselineGap);
  
  var trendStartYear = yr.subtract(epochLength).add(1);
  
  // print(yr,blStartYear,blEndYear);
  return ee.FeatureCollection(ee.List.sequence(startJulian,endJulian-nDays,nDays).map(function(jd){
    // print(jd);
    jd = ee.Number(jd);
    var jdStart = jd;
    var jdEnd = jd.add(nDays);
    
    var blImages = allScenes.filter(ee.Filter.calendarRange(blStartYear,blEndYear,'year'))
                            .filter(ee.Filter.calendarRange(jdStart,jdEnd));
    blImages = getImageLib.fillEmptyCollections(blImages,dummyScene);
    
    var analysisImages = allScenes.filter(ee.Filter.calendarRange(yr,yr,'year'))
                            .filter(ee.Filter.calendarRange(jdStart,jdEnd)); 
    analysisImages = getImageLib.fillEmptyCollections(analysisImages,dummyScene);
    
    var trendImages = allScenes.filter(ee.Filter.calendarRange(trendStartYear,yr,'year'))
                            .filter(ee.Filter.calendarRange(jdStart,jdEnd));
    trendImages = getImageLib.fillEmptyCollections(trendImages,dummyScene);
    
    var linearTrend = dLib.getLinearFit(trendImages,indexNames);
    var linearTrendModel = ee.Image(linearTrend[0]).select(['.*_slope']).multiply(epochLength);
    
    var blMean = blImages.mean();
    var blStd = blImages.reduce(ee.Reducer.stdDev());
    
    var analysisImagesZ = analysisImages.map(function(img){
      return img.subtract(blMean).divide(blStd);
    }).reduce(zReducer).rename(outNames);
    // Map.addLayer(analysisImagesZ,{'min':-20,'max':20,'palette':'F00,888,0F0'},'z '+outName,false);
    var out = analysisImages.reduce(zReducer).rename(indexNames).addBands(analysisImagesZ).addBands(linearTrendModel)
          .set({'system:time_start':ee.Date.fromYMD(yr,1,1).advance(jdStart,'day').millis(),
                'system:time_end':ee.Date.fromYMD(yr,1,1).advance(jdEnd,'day').millis(),
                'baselineYrs': baselineLength,
                'baselineStartYear':blStartYear,
                'baselineEndYear':blEndYear,
                'epochLength':epochLength,
                'trendStartYear':trendStartYear,
                'year':yr,
                
          });
    // Export image
    // var outName = outputName + blStartYear.toString() + '_' + blEndYear.toString() + '_'+yr.toString() + '_'+jdStart.toString() + '_'+ jdEnd.toString();
    // var outPath = exportPathRoot + '/' + outName;
    // getImageLib.exportToAssetWrapper(out,outName,outPath,
      // 'mean',studyArea,scale,crs,transform);
    return out//.float()
    // zCollection.push(out);
    
  }));
  
  //Set up dates
  // var startYearT = yr-timebuffer;
  // var endYearT = yr+timebuffer;
  
  // //Get scenes for those dates
  // var allScenesT = allScenes.filter(ee.Filter.calendarRange(startYearT,endYearT,'year'));
  
  // //Fit harmonic model
  // var coeffsPredicted =getImageLib.getHarmonicCoefficientsAndFit(allScenesT,indexNames,whichHarmonics);
  
  // //Set some properties
  // var coeffs = coeffsPredicted[0]
  //           .set({'system:time_start':ee.Date.fromYMD(yr,6,1).millis(),
  //           'timebuffer':timebuffer,
  //           'startYearT':startYearT,
  //           'endYearT':endYearT,
  //           }).float();
            
  // var predicted = coeffsPredicted[1];
  
  // //Export image
  // var outName = outputName + startYearT.toString() + '_'+ endYearT.toString();
  // var outPath = exportPathRoot + '/' + outName;
  // getImageLib.exportToAssetWrapper(coeffs,outName,outPath,
  // 'mean',studyArea,scale,crs,transform);
  // // Map.addLayer(allScenesT.median(),{'min':0.1,'max':0.3,'bands':'swir1,nir,red'},yr.toString(),false);
  // return coeffs;
  
});
zAndTrendCollection = ee.ImageCollection(ee.FeatureCollection(zAndTrendCollection).flatten());
var zCollection = zAndTrendCollection.select('.*_Z');
var trendCollection = zAndTrendCollection.select('.*_slope');

var zChange = dLib.thresholdChange(zCollection,-5,-1);
print(zChange)
print(zAndTrendCollection)
Map.addLayer(zAndTrendCollection,{},'zAndTrendCollection',false);
// Map.addLayer(zChange.max(),{},'zAndTrendCollection',false);

