/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #98ff00 */ee.Geometry.Polygon(
        [[[-118.63531656897908, 36.74257058586009],
          [-117.82232828772908, 37.408727967272085],
          [-118.17467006767367, 38.18264304528551],
          [-119.39337320960408, 38.293547223630156],
          [-119.54718180335408, 37.47850889576281]]]);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
//Module imports
var getImageLib = require('users/USFS_GTAC/modules:getImagesLib.js');
///////////////////////////////////////////////////////////////////////////////
// Define user parameters:

// 1. Specify study area: Study area
// Can specify a country, provide a fusion table  or asset table (must add 
// .geometry() after it), or draw a polygon and make studyArea = drawnPolygon
var states = ee.FeatureCollection('TIGER/2016/States');
states = states.filter(ee.Filter.inList('NAME',['California'])).union(1000).geometry().buffer(10000);

var studyArea = states;

// 2. Update the startJulian and endJulian variables to indicate your seasonal 
// constraints. This supports wrapping for tropics and southern hemisphere.
// startJulian: Starting Julian date 
// endJulian: Ending Julian date
var startJulian = 274;
var endJulian = 273; 

// 3. Specify start and end years for all analyses
// More than a 3 year span should be provided for time series methods to work 
// well. If using Fmask as the cloud/cloud shadow masking method, this does not 
// matter
var startYear = 1980;
var endYear = 2018;

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



// 6. Choose reducer to use for summarizing
var compositingReducer = ee.Reducer.mean();

// 7. Choose collection to use
// Specify TOA or SR
// Supports:
// NASA/ORNL/DAYMET_V3
// UCSB-CHG/CHIRPS/DAILY (precipitation only)
var collectionName = 'NASA/ORNL/DAYMET_V3';



//8. Export params
//Whether to export composites
var exportComposites = true;


//Provide location composites will be exported to
//This should be an asset folder, or more ideally, an asset imageCollection
var exportPathRoot = 'users/ianhousman/test/changeCollection';

//Specify which bands to export
//If not sure or want all bands, just set to null
var exportBands = ['prcp.*','tmax.*','tmin.*'];

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
////////////////////////////////////////////////////////////////////////////////
//Call on master wrapper function to get Landat scenes and composites
var climateSummaries = getImageLib.getClimateWrapper(collectionName,studyArea,startYear,endYear,startJulian,endJulian,
  timebuffer,weights,compositingReducer,
  exportComposites,exportPathRoot,crs,transform,scale,exportBands);
print(climateSummaries)
// Map.addLayer(climateSummaries.select(['prcp.*']))
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
