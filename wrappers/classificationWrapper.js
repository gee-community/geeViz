var classificationLib = require()
// get predictor rasters as multi-band image
var predictors = image.addBands(image2);

// get reference data
var referenceData = INPUT_REFERENCE_DATA;

// choose whether to use points or polygons
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
var projection = 'EPSG:26912';

// choose resolution
var scale = 30;

// polygon reducers
var reducers = ee.Reducer.mean().combine({
  reducer2: ee.Reducer.stdDev(),
  sharedInputs: true
});

var out = classificationWrapper(predictors, referenceData, referenceDataType, responseField, classifier, classifierParameters, mode, reducers, projection, null, scale);
print('out', out);
Export.table.toDrive({collection: out[1], description: 'ADD DESCRIPTION',fileFormat: 'KML'});
Map.addLayer(out[1], {}, 'out');
