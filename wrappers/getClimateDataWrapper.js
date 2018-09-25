/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #98ff00 */ee.Geometry.Polygon(
        [[[-107.88010335430403, 37.74944967250176],
          [-104.41965417436563, 37.91850622749146],
          [-105.360767292844, 39.25236887854654],
          [-107.57914696634225, 39.18649132261251]]]);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
//Module imports
var getImageLib = require('users/USFS_GTAC/modules:getImagesLib.js');
///////////////////////////////////////////////////////////////////////////////
// Define user parameters:

// 1. Specify study area: Study area
// Can specify a country, provide a fusion table  or asset table (must add 
// .geometry() after it), or draw a polygon and make studyArea = drawnPolygon
var studyArea = geometry;

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
var startYear = 2010;
var endYear = 2012;

// 4. Specify an annual buffer to include imagery from the same season 
// timeframe from the prior and following year. timeBuffer = 1 will result 
// in a 3 year moving window
var timebuffer = 0;

// 5. Specify the weights to be used for the moving window created by timeBuffer
//For example- if timeBuffer is 1, that is a 3 year moving window
//If the center year is 2000, then the years are 1999,2000, and 2001
//In order to overweight the center year, you could specify the weights as
//[1,5,1] which would duplicate the center year 5 times and increase its weight for
//the compositing method
var weights = [1];



// 6. Choose medoid or median compositing method. 
// Median tends to be smoother, while medoid retains 
// single date of observation across all bands
// If not exporting indices with composites to save space, medoid should be used
var compositingMethod = 'median';

// 7. Choose collection to use
// Specify TOA or SR
// Supports:
// NASA/ORNL/DAYMET_V3
// UCSB-CHG/CHIRPS/DAILY (precipitation)
var collectionName = 'NASA/ORNL/DAYMET_V3';





//13. Export params
//Whether to export composites
var exportComposites = true;

//Set up Names for the export
var outputName = 'Median-Climate';

//Provide location composites will be exported to
//This should be an asset folder, or more ideally, an asset imageCollection
var exportPathRoot = 'users/ianhousman/test';



//CRS- must be provided.  
//Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
//WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
var crs = 'EPSG:5070';

//Specify transform if scale is null and snapping to known grid is needed
var transform = [1000,0,-2361915.0,0,-1000,3177735.0];

//Specify scale if transform is null
var scale = null;
///////////////////////////////////////////////////////////////////////
// End user parameters
///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
//Start function calls
function getClimateWrapper(collectionName,studyArea,startYear,endYear,startJulian,endJulian,
  timebuffer,weights,compositingMethod,
  exportComposites,outputName,exportPathRoot,crs,transform,scale){
    
    // Prepare dates
  //Wrap the dates if needed
  if (startJulian > endJulian) {
    endJulian = endJulian + 365;
  }
  var startDate = ee.Date.fromYMD(startYear,1,1).advance(startJulian-1,'day');
  var endDate = ee.Date.fromYMD(endYear,1,1).advance(endJulian-1,'day');
  print('Start and end dates:', startDate, endDate);
  var c = ee.ImageCollection(collectionName)
          .filterBounds(studyArea.bounds())
          .filterDate(startDate,endDate)
          .filter(ee.Filter.calendarRange(startJulian,endJulian))
  // Create composite time series
  var ts = getImageLib.compositeTimeSeries(c,startYear,endYear,startJulian,endJulian,timebuffer,weights,compositingMethod);
  Map.addLayer(ts.select(['prcp']))
  print(ts.size())
  }
////////////////////////////////////////////////////////////////////////////////
//Call on master wrapper function to get Landat scenes and composites
var climateSummaries = getClimateWrapper(collectionName,studyArea,startYear,endYear,startJulian,endJulian,
  timebuffer,weights,compositingMethod,
  exportComposites,outputName,exportPathRoot,crs,transform,scale);


////////////////////////////////////////////////////////////////////////////////
// Load the study region, with a blue outline.
// Create an empty image into which to paint the features, cast to byte.
// Paint all the polygon edges with the same number and width, display.
var empty = ee.Image().byte();
var outline = empty.paint({
  featureCollection: studyArea,
  color: 1,
  width: 3
});
Map.addLayer(outline, {palette: '0000FF'}, "Study Area", false);
// Map.centerObject(studyArea, 6);
////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////
