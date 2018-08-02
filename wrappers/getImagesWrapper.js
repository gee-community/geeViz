/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #d63000 */ee.Geometry.Polygon(
        [[[-109.8193359375, 43.205175817237304],
          [-109.775390625, 43.03677585761058],
          [-109.566650390625, 43.000629854450004],
          [-109.4677734375, 43.23319741022135]]]);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
///////////////////////////////////////////////////////////////////////////////
// Define user parameters:

// 1. Specify study area: Study area
// Can specify a country, provide a fusion table  or asset table (must add 
// .geometry() after it), or draw a polygon and make studyArea = drawnPolygon
var rio = ee.FeatureCollection('users/ianhousman/RIO/Rio_Grande_NF_Boundary_10kBuffer_albers_diss');
var fnf = ee.FeatureCollection('projects/USFS/LCMS-NFS/R1/FNF/FNF_GNP_Merge_Admin_BND_1k');
var bt = ee.FeatureCollection('projects/USFS/LCMS-NFS/R4/BT/BT_LCMS_ProjectArea_5km');
var studyArea = geometry;//bt.geometry();//fnf.geometry();

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
var startYear = 2015;
var endYear = 2018;

// 4. Specify an annual buffer to include imagery from the same season 
// timeframe from the prior and following year. timeBuffer = 1 will result 
// in a 3 year moving window
var timebuffer = 1;
var weights = [1,5,1];
// 5. Set up Names for the export
var outputName = 'Medoid';//'Medoid_Corrected';//

// 6. Provide location composites will be exported to
// var exportPathRoot = 'projects/USFS/LCMS-NFS/RIO-Test/'+ outputName;

// var exportPathRoot = 'projects/USFS/LCMS-NFS/R1/FNF/FNF-Collection';
// var exportPathRoot = 'projects/USFS/LCMS-NFS/R1/FNF/Composites/FNF-Composite-Collection';
var exportPathRoot = 'projects/USFS/LCMS-NFS/R4/BT/Composites/BT-Composite-Collection';
// 7. Choose medoid or median compositing method. 
// Median tends to be smoother, while medoid retains 
// single date of observation across all bands
// Specify compositing method (median or medoid)
var compositingMethod = 'medoid';

// 8. Choose Top of Atmospheric (TOA) or Surface Reflectance (SR) 
// Specify TOA or SR
var toaOrSR = 'SR';

// 9. Choose whether to include Landat 7
// Generally only included when data are limited
var includeSLCOffL7 = false;

// 10. Choose cloud/cloud shadow masking method
// Choices are a series of booleans for cloudScore, TDOM, and elements of Fmask
//Fmask masking options will run fastest since they're precomputed
//CloudScore runs pretty quickly, but does look at the time series to find areas that 
//always have a high cloudScore to reduce comission errors- this takes some time
//and needs a longer time series (>5 years or so)
//TDOM also looks at the time series and will need a longer time series
var applyCloudScore = true;
var applyFmaskCloudMask = true;

var applyTDOM = true;
var applyFmaskCloudShadowMask = true;
var applyFmaskSnowMask = false;

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
var cloudScorePctl = 100; 

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
var correctScale = 250;

//13. Export params
var crs = 'EPSG:5070';
var transform = [30,0,-2361915.0,0,-30,3177735.0];
///////////////////////////////////////////////////////////////////////
// End user parameters

// Prep client-side region for exporting
// var studyAreaBounds = studyArea.bounds();
// var region = studyArea.bounds(1000).getInfo().coordinates[0];

// Prepare dates
if (startJulian > endJulian) {
  endJulian = endJulian + 365;
}
var startDate = ee.Date.fromYMD(startYear,1,1).advance(startJulian-1,'day');
var endDate = ee.Date.fromYMD(endYear,1,1).advance(endJulian-1,'day');
print('Start and end dates:', startDate, endDate);

toaOrSR = toaOrSR.toUpperCase();
////////////////////////////////////////////////////////////////////////////////
var getImageLib = require('users/USFS_GTAC/modules:getImagesLib.js');
// Get Landsat image collection
var ls = getImageLib.getImageCollection(studyArea,startDate,endDate,startJulian,endJulian,
  toaOrSR,includeSLCOffL7);

// Apply relevant cloud masking methods
if(applyCloudScore){
  print('Running cloudScore');
  ls = getImageLib.applyCloudScoreAlgorithm(ls,getImageLib.landsatCloudScore,cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels); 
  
}
if(applyFmaskCloudMask){
  print('Applying Fmask cloudmask');
  ls = ls.map(function(img){return getImageLib.cFmask(img,'cloud')});
}

if(applyTDOM){
  print('Applying TDOM');
  //Find and mask out dark outliers
  ls = getImageLib.simpleTDOM2(ls,zScoreThresh,shadowSumThresh,contractPixels,dilatePixels);
}
if(applyFmaskCloudShadowMask){}
// if(applyFmaskSnowMask){}


// if ((cloudcloudShadowMaskingMethod.toLowerCase() === 'fmask' || 
//   cloudcloudShadowMaskingMethod.toLowerCase() === 'hybrid') && 
//   toaOrSR.toLowerCase() != 'toa') {
//   print('Extracting cFmask cloud masks');
//   ls = ls.map(cFmaskCloud);
// }

// if ( applyFmaskSnowMask == true){
//   print('Applying Fmask snowmask');
//   ls = ls.map(function(img){return cFmask(img,'snow')});
// }

// if (cloudcloudShadowMaskingMethod.toLowerCase() === 'cloudscoretdom' || 
//   cloudcloudShadowMaskingMethod.toLowerCase() === 'hybrid' || 
//   toaOrSR.toLowerCase() === 'toa') {
//   print('Running TDOM');
//   // Find and mask out dark outliers
//   ls = simpleTDOM2(ls,zScoreThresh,shadowSumThresh,contractPixels,dilatePixels);
// }

// if ((cloudcloudShadowMaskingMethod.toLowerCase() === 'fmask' || 
//   cloudcloudShadowMaskingMethod.toLowerCase() === 'hybrid') && 
//   toaOrSR.toLowerCase() != 'toa') {
//   print('Extracting cFmask cloud shadow masks');
//   ls = ls.map(cFmaskCloudShadow);
// }

// // Add common indices
// // ls = ls.map(addIndices);

// // Add zenith and azimuth
// if (correctIllumination){
//   ls = ls.map(function(img){
//     return addZenithAzimuth(img,toaOrSR);
//   });
// }

// // Create composite time series
// var ts = compositeTimeSeries(startYear,endYear,timebuffer,weights);

// // Correct illumination
// if (correctIllumination){
//   ts = ts.map(illuminationCondition)
//     .map(function(img){
//       return illuminationCorrection(img, correctScale);
//     });
// }

// // Export composite collection
// var exportBands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'temp'];
// exportCollection(ts,startYear,endYear,timebuffer,exportBands);
// // print(ee.Image(ts.first()));

// ////////////////////////////////////////////////////////////////////////////////
// // Load the study region, with a blue outline.
// // Create an empty image into which to paint the features, cast to byte.
// // Paint all the polygon edges with the same number and width, display.
// var empty = ee.Image().byte();
// var outline = empty.paint({
//   featureCollection: studyArea,
//   color: 1,
//   width: 3
// });
// Map.addLayer(outline, {palette: '0000FF'}, "Study Area", false);
// // Map.centerObject(studyArea, 6);
  