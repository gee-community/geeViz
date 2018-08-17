//  get the classification library
var classificationLib = require('users/USFS_GTAC/modules:classificationLib.js')

// define a study area
sa = DEFINE

// get predictor rasters as multi-band image
var predictors = X;

// get reference data
var referenceData = INPUT_REFERENCE_DATA;

// choose whether to use 'points' or 'polygons'.
//If the referece data are points than the classification will result in a raster output.
// If the referece data are points than the classification reqires the polygons to be split into training and
//apply datasets. The result will be classified polygons. Computations will time out with too many polygons. 
var referenceDataType = 'points';

// get column name of reference field as a string
var responseField = 'INPUT_REFERENCE_COLUMN';

// choose the polygons to apply classifier to if the reference data type is polygons otherwise choose null
var applyPolygons = null;

// choose classifier 
var classifier = ee.Classifier.randomForest;

// choose classifier parameters
var classifierParameters = {};

// choose classifier output mode: CLASSIFICATION, REGRESSION, PROBABILITY
var mode = 'CLASSIFICATION'

// choose projection
var crs = 'EPSG:26912';

// choose resolution
var scale = 30;

// choose export name
var exportName = 'NAME'

// polygon reducers
var reducers = ee.Reducer.mean().combine({
  reducer2: ee.Reducer.stdDev(),
  sharedInputs: true
});

var out = classificationLib.classificationWrapper(predictors, referenceData, referenceDataType, responseField, classifier, classifierParameters, mode, reducers, crs, null, scale);
print('out', out);
//Export.table.toDrive({collection: out[1], description: 'ADD DESCRIPTION',fileFormat: 'KML'});
Export.image.toDrive({image: out[1], description: exportName, region: sa, scale: scale, crs: crs, maxPixels: 1e13})
Map.addLayer(out[1], {}, 'out');
