/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #d63000 */ee.Geometry.Polygon(
        [[[-111.92909653962062, 40.56004934701077],
          [-111.47865708649562, 40.59759845053245],
          [-111.52809556305812, 40.84738694424386],
          [-111.91811021149562, 40.85985175572704]]]);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
var getImageLib = require('users/USFS_GTAC/modules:getImagesLib.js');

//Get images
var images = getImageLib.getImageCollection(geometry,ee.Date.fromYMD(2015,1,1),ee.Date.fromYMD(2018,12,31),190,250,
  'SR',false,false,false);
   

//Apply Fmask 
images = images.map(function(img){return getImageLib.cFmask(img,'cloud')});
images = images.map(function(img){return getImageLib.cFmask(img,'shadow')}).select(['blue','green','red','nir','swir1','swir2']);

//Create composite
var composite = getImageLib.medoidMosaicMSD(images,['blue','green','red','nir','swir1','swir2']);
Map.addLayer(composite,getImageLib.vizParamsFalse,'Composite');

//Get dates in composite
//If there is more than one of the same value in the collection for the chosen
//composite pixel value, it will only return a single value
//Using the mode helps reduce this confusion
var dates = getImageLib.compositeDates(images,composite,['blue','green','red','nir','swir1','swir2']);
Map.addLayer(dates.reduce(ee.Reducer.mode()),{min:2015.5,max:2018.5},'Dates Mode');