/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #d63000 */ee.Geometry.Polygon(
        [[[-115.19522231507318, 48.704101580291294],
          [-115.12930434632318, 48.39866293818322],
          [-114.10757583069818, 48.62065285721024],
          [-114.40969985413568, 48.87781053836135]]]);
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
var startJulian =190;
var endJulian = 250; 

// 3. Specify start and end years for all analyses
// More than a 3 year span should be provided for time series methods to work 
// well. If using Fmask as the cloud/cloud shadow masking method, this does not 
// matter
var startYear = 2016;
var endYear = 2018;

// 4. Specify an annual buffer to include imagery from the same season 
// timeframe from the prior and following year. timeBuffer = 1 will result 
// in a 3 year moving window
// var timebuffer = 1;

// 5. Specify the weights to be used for the moving window created by timeBuffer
//For example- if timeBuffer is 1, that is a 3 year moving window
//If the center year is 2000, then the years are 1999,2000, and 2001
//In order to overweight the center year, you could specify the weights as
//[1,5,1] which would duplicate the center year 5 times and increase its weight for
//the compositing method
// var weights = [1,5,1];



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
// var applyCloudScore = true;
// var applyFmaskCloudMask = false;

// var applyTDOM = true;
// var applyFmaskCloudShadowMask = false;

// var applyFmaskSnowMask = false;

// 11. Cloud and cloud shadow masking parameters.
// If cloudScoreTDOM is chosen
// cloudScoreThresh: If using the cloudScoreTDOMShift method-Threshold for cloud 
//    masking (lower number masks more clouds.  Between 10 and 30 generally 
//    works best)
var cloudScoreThresh = 10;

//Whether to find if an area typically has a high cloudScore
//If an area is always cloudy, this will result in cloud masking omission
//For bright areas that may always have a high cloudScore
//but not actually be cloudy, this will result in a reduction of commission errors
//This procedure needs at least 5 years of data to work well
var performCloudScoreOffset = false;

// If performCloudScoreOffset = true:
//Percentile of cloud score to pull from time series to represent a minimum for 
// the cloud score over time for a given pixel. Reduces comission errors over 
// cool bright surfaces. Generally between 5 and 10 works well. 0 generally is a
// bit noisy but may be necessary in persistently cloudy areas
var cloudScorePctl = 10;

//Sentinel 2 only!
//Height of clouds to use to project cloud shadows
var cloudHeights = ee.List.sequence(500,10000,500);

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
var dilatePixels = 3.5;

// // 12. correctIllumination: Choose if you want to correct the illumination using
// // Sun-Canopy-Sensor+C correction. Additionally, choose the scale at which the
// // correction is calculated in meters.
// var correctIllumination = false;
// var correctScale = 250;//Choose a scale to reduce on- 250 generally works well

// //13. Export params
// //Whether to export composites
// var exportComposites = true;

//Set up Names for the export
var outputName = 'Landsat';

//Provide location composites will be exported to
//This should be an asset folder, or more ideally, an asset imageCollection
var exportPathRoot = 'users/ianhousman/test/changeCollection';



//CRS- must be provided.  
//Common crs codes: Web mercator is EPSG:4326, USGS Albers is EPSG:5070, 
//WGS84 UTM N hemisphere is EPSG:326+ zone number (zone 12 N would be EPSG:32612) and S hemisphere is EPSG:327+ zone number
var crs = 'EPSG:32717'//'EPSG:5070';

//Specify transform if scale is null and snapping to known grid is needed
var transform = null;//[30,0,-2361915.0,0,-30,3177735.0];

//Specify scale if transform is null
var scale = 20;


///////////////////////////////////////////////////////////////////////
// End user parameters
///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////
//Start function calls

// Prepare dates
//Wrap the dates if needed
var wrapOffset = 0;
// if (startJulian > endJulian) {
//   wrapOffset = 365;
// }
var startDate = ee.Date.fromYMD(startYear,1,1).advance(startJulian-1,'day');
var endDate = ee.Date.fromYMD(endYear,1,1).advance(endJulian-1+wrapOffset,'day');
print('Start and end dates:', startDate, endDate);

////////////////////////////////////////////////////////////////////////////////
//Get Landsat and Sentinel 2 raw images
var ls = getImageLib.getImageCollection(studyArea,startDate,endDate,startJulian,endJulian,
    toaOrSR,includeSLCOffL7,defringeL5);
var s2s = getImageLib.getS2(studyArea,startDate,endDate,startJulian,endJulian);
Map.addLayer(ls.first(),getImageLib.vizParamsFalse,'Landsat No Masking',false)

//Apply respective cloudScore functions
ls = getImageLib.applyCloudScoreAlgorithm(ls,getImageLib.landsatCloudScore,cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels,performCloudScoreOffset);
s2s = getImageLib.applyCloudScoreAlgorithm(s2s,getImageLib.sentinel2CloudScore,cloudScoreThresh,cloudScorePctl,contractPixels,dilatePixels,performCloudScoreOffset);
Map.addLayer(ls.first(),getImageLib.vizParamsFalse,'Landsat Cloud Masking',false)
//Set a property for splitting apart later
ls = ls.map(function(img){return img.float().set('whichProgram','Landsat')});
s2s = s2s.map(function(img){return img.float().set('whichProgram','Sentinel2')});

//Merge collections
var merged = ls.merge(s2s);

//Perform TDOM
merged = getImageLib.simpleTDOM2(merged,zScoreThresh,shadowSumThresh,contractPixels,dilatePixels);

//Seperate back out
ls = merged.filter(ee.Filter.eq('whichProgram','Landsat'));
s2s = merged.filter(ee.Filter.eq('whichProgram','Sentinel2'));
Map.addLayer(ls.first(),getImageLib.vizParamsFalse,'Landsat Cloud/Shadow Masking',false)
// // Create composite time series function
// function createAndExportComposites(c,startYear,endYear,startJulian,endJulian,timebuffer,weights,everyHowManyDays,exportPathRoot,exportName,exportBands,nonDivideBands,scale,crs,transform){

// //Iterate across each year
// ee.List.sequence(startYear+timebuffer,endYear-timebuffer).getInfo().map(function(year){
//     var dummyImage = ee.Image(c.first());
//     // Set up dates
//     var startYearT = year-timebuffer;
//     var endYearT = year+timebuffer;
//   //Set up weighted moving widow
//     var yearsT = ee.List.sequence(startYearT,endYearT);
    
//     var z = yearsT.zip(weights);
//     var yearsTT = z.map(function(i){
//       i = ee.List(i);
//       return ee.List.repeat(i.get(0),i.get(1));
//     }).flatten();
    
//   ee.List.sequence(startJulian,endJulian,everyHowManyDays).getInfo().map(function(startJulianT){
//     var endJulianT = startJulianT+everyHowManyDays-1;

//     if(endJulianT <= endJulian){
//       // print(startYearT,endYearT,year,startJulianT,endJulianT);
//       //Iterate across each year in list
//       var images = yearsTT.map(function(yrT){
       
        
//         // Filter images for given date range
//         var cT = c.filter(ee.Filter.calendarRange(yrT,yrT,'year'))
//                     .filter(ee.Filter.calendarRange(startJulianT,endJulianT));
//         cT = getImageLib.fillEmptyCollections(cT,dummyImage);
//         return cT;
//       });
//       var cT = ee.ImageCollection(ee.FeatureCollection(images).flatten());
//       var count = cT.select([0]).count().rename(['count'])
//       // Compute median or medoid or apply reducer
//     var composite;
//     if (compositingMethod.toLowerCase() === 'median') {
//       composite = cT.median();
//     }
//     else {
      
//       composite = getImageLib.medoidMosaicMSD(cT,['blue','green','red','nir','swir1','swir2']);
//     }
//     composite = composite.addBands(count).select(exportBands);
    
    
    
//     // Reformat data for export
//     var compositeBands = composite.bandNames();
//     if(nonDivideBands != null){
//       var composite10k = composite.select(compositeBands.removeAll(nonDivideBands))
//       .multiply(10000);
//       composite = composite10k.addBands(composite.select(nonDivideBands))
//       .select(compositeBands).int16();
//     }
//     else{
//       composite = composite.multiply(10000).int16();
//     }
    
    
//     var startDate = ee.Date.fromYMD(year,1,1).advance(startJulianT,'day').millis();
//     var endDate = ee.Date.fromYMD(year,1,1).advance(endJulianT,'day').millis();
    
//     composite = composite.set({
//                         'system:time_start':startDate,
//                         'system:time_end':endDate,
//                         'startJulian':startJulian,
//                         'endJulian':endJulian,
//                         'yearBuffer':timebuffer,
//                         'yearWeights': getImageLib.listToString(weights),
//                         'yrCenter':year,
//                         'dilatePixels':dilatePixels,
//                         'contractPixels':contractPixels,
//                         'cloudScoreThresh':cloudScoreThresh,
//                         'useCloudScore':true,
//                         'crs':crs,
//                         'startDOY':startJulianT,
//                         'endDOY':endJulianT,
//                         'useSRmask':false,
//                         'shadowSumThresh':shadowSumThresh,
//                         'zScoreThresh':zScoreThresh,
//                         'terrain':false.toString(),
//                         'useCloudProject':performCloudScoreOffset.toString(),
//                         'useTDOM':true.toString(),
//                         'useLandsatS2HybridTDOM':true.toString(),
//                         'whichProgram':exportName,
//                         'compositingMethod':compositingMethod.toLowerCase()
                     
//     });
    


//     var outName = exportName+'_y'+startYearT.toString() + '_'+ endYearT.toString() + '_j'+startJulianT.toString() + '_' + endJulianT.toString();
//     // Map.addLayer(composite,{min:500,max:5000,bands:'swir1,nir,red'},outName,false);
    
    
//     var exportPath = exportPathRoot + '/' + outName;
//     // print('Write down the Asset ID:', exportPath);
  
//     getImageLib.exportToAssetWrapper(composite,outName,exportPath,'mean',
//       studyArea,scale,crs,transform);
    
//     }
// });
// });
// }

// //Export bands for each program
// var lExportBands = [ 'blue', 'green', 'red','nir','swir1', 'swir2','temp','count'];
// var S2ExportBands = ['cb', 'blue', 'green', 'red', 're1','re2','re3','nir', 'nir2', 'waterVapor', 'cirrus','swir1', 'swir2','count'];

// //Export bi-weekly
// createAndExportComposites(ls,2000,2018,1,365,0,[1],14,'projects/Sacha/L8/L8_Biweekly_Updated','Landsat',lExportBands,['temp','count'],scale,crs,null);
// createAndExportComposites(s2s,2015,2018,1,365,0,[1],14,'projects/Sacha/S2/S2_Biweekly_Updated','Sentinel2',S2ExportBands,['count'],scale,crs,null);

//Export annuals
// createAndExportComposites(ls,1999,2019,1,365,1,[1,3,1],365,'projects/Sacha/L8/L8_Annual_Updated','Landsat',lExportBands,['temp','count'],scale,crs,null);
// createAndExportComposites(s2s,2014,2019,1,365,1,[1,3,1],365,'projects/Sacha/S2/S2_Annual_Updated','Sentinel2',S2ExportBands,['count'],scale,crs,null);

/////////////////////////////////////////////////////
//Code for starting all tasks once this script has ran
//Press f12, then paste functions into console
//Then paste function calls into console
// function runTaskList() {


//     //1. task local type-EXPORT_FEATURES awaiting-user-config

//     //2. task local type-EXPORT_IMAGE awaiting-user-config

//     var tasklist = document.getElementsByClassName('awaiting-user-config');

//     for (var i = 0; i < tasklist.length; i++)

//         tasklist[i].children[2].click();

// }

// // confirmAll();

// function confirmAll() {

//     var ok = document.getElementsByClassName('goog-buttonset-default goog-buttonset-action');

//     for (var i = 0; i < ok.length; i++)

//         ok[i].click();

// }