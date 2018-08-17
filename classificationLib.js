///////////////////////////////////////////////////////////////////////////////////////////////
// classification wrapper
///////////////////////////////////////////////////////////////////////////////////////////////
function classificationWrapper(predictors, referenceData, referenceDataType, responseField, classifier, classifierParameters, mode, reducers, crs, transform, scale){
    //create if statement that identifies if reference data is numeric and doesn't apply remap
  var refValType = referenceData.getInfo().columns[responseField];
  print('refValType:', refValType);
  
  if (refValType === 'String'){
    //remap values to numbers
    referenceData = namesToNumbers(referenceData, responseField, responseField+'_number');
  }
  var trainingData;
  // get predictors with reference data
  if(referenceDataType ==='points'){
    trainingData = predictors.sampleRegions({
      collection: referenceData, properties: null, scale: scale, projection: crs, tileScale: 1});
      print('trainingData', trainingData);
  }else{
    trainingData = predictors.reduceRegions({
      collection: referenceData, reducer: reducers, scale: scale, crs: crs, tileScale: 1});
    }
  var applyOutPolygons;
  if(referenceDataType === 'polygons'){
    applyOutPolygons = predictors.reduceRegions({
      collection: applyPolygons.limit(500), reducer: reducers, scale: scale, crs: projection, tileScale: 1});
    }else{}
  
  // get a list of the predictor bands
  var inputProperties = ee.Feature(trainingData.first()).propertyNames();
  var refDataProperties = ee.Feature(referenceData.first()).propertyNames();
  print('inputProperties:', inputProperties);
  print('refDataProperties:', refDataProperties);
  inputProperties = inputProperties.removeAll(refDataProperties);
  print('inputProperties:', inputProperties);
  
  var model = classifier(classifierParameters).setOutputMode(mode).train({
    features: trainingData,
    classProperty: responseField+'_number',
    inputProperties: inputProperties, 
    subsampling: 1,
    subsamplingSeed: 0});
  var ApplyModel;  
  if(referenceDataType === 'points'){ 
    ApplyModel = predictors.classify(model);
    Map.addLayer(ApplyModel, {}, 'Classified Raster');
    return [model, ApplyModel];
    
  }else if(referenceDataType === 'polygons'){
    ApplyModel = applyOutPolygons.classify(model);
    //print('polygonsApplyModel', polygonsApplyModel);
    return [model, ApplyModel];
      
  }
}
///////////////////////////////////////////////////////////////////////////////
// FUNCTIONS
///////////////////////////////////////////////////////////////////////////////
// Function to duplicate a value to a column with a new name (used to simplify
// names)
function renameColumn(feature,oldColumn,newColumn){
  feature = ee.Feature(feature);
  var value = feature.get(oldColumn);
  feature = feature.set(newColumn,value);
  return feature;
}

///////////////////////////////////////////////////////////////////////////////
// Function to remap class names to class numbers (starting at 0)
function namesToNumbers(collection,nameColumn,numberColumn){
  // Get list of names
  var hist = collection.reduceColumns({
    reducer:ee.Reducer.frequencyHistogram(),
    selectors:[nameColumn]
  }).get('histogram');
  var names = ee.Dictionary(hist).keys();
  
  // Get corresponding numbers
  var numbers = ee.List.sequence(0,names.length().subtract(1));
  // Copy name column to number column
  collection = collection.map(function(feature){
    feature = renameColumn(feature,nameColumn,numberColumn);
    return feature;
  });
  // Remap names to numbers in the number column
  collection = collection.remap(names,numbers,numberColumn);
  print('name number list:',names,numbers);
  return collection; 
}

exports.classificationWrapper = classificationWrapper;
exports.renameColumn = renameColumn;
exports.namesToNumbers = namesToNumbers;