# geeViz 2025.4.3 Release Notes

## April 18, 2025

### New Features

- **Additional Pydocs** - Added/updated pydocs throughout the package.

---

# geeViz 2025.4.3 Release Notes

## April 17, 2025

### Bug fixes

- `geeViz.geeView.simpleSetProject` bug fix.It would not create the credential directory if it did not already exist. Not it creates it.

---

# geeViz 2025.4.2 Release Notes

## April 17, 2025

### New Features

- **`assetManagerLib.ingestFromGCSImagesAsBands()`** - New function for ingesting multiple images as bands of a single Earth Engine image asset. Takes a list of dictionaries, with each dictionary containing a key/value for the 'gcsURI' of the input image, and optional keys/values for 'pyramidingPolicy', 'noDataValue', and 'bandName'.
- **`assetManagerLib.uploadToGEEAssetImagesAsBands()`** - New wrapper function for uploading multiple images to gcloud and manifesting them as bands of a single Earth Engine image asset. Takes a dictionary in which keys are file paths to each image, and values are dictionaries with keys/values for 'pyramidingPolicy', 'noDataValue', and 'bandName'.
- **`assetManagerLib.uploadTifToGCS()`** - New function for uploading individual tifs to gcloud. Uses `gcloud storage` command instead of `gsutil`.
- **`assetManagerLib.create_image_collection()`** - This function now takes an optional dictionary as a parameter that defines properties to set for the image collection.

- **`examples.LCMS_Levels_Viewer_Notebook` updates** - In preparation for the v2024.10 release of LCMS, the new levels that will be published are now supported and better-documented in the notebook.

---

# geeViz 2025.4.1 Release Notes

## April 16, 2025

### New Features

- **geeView area charting chartType setting** - Can now set the `chartType` (`vizParams["areaChartParams"]["chartType"]`) to "line", "bar", "stacked-line", and "stacked-bar". This is only used for `ee.ImageCollection` objects. For `ee.Image` objects, the chartType is always "bar". See pydoc for `Map.addLayer`, `Map.addTimeLapse`, and `Map.addAreaChartLayer` for details.

### Bug fixes

- `geeViz.geeView.robustInitializer()` bug fix. Method was broken by some updates to the GEE API returning a number for a project ID. This is now fixed. The new `robustIntializer()` is far simpler than the prior versions, so it will not handle as many scenarios as before. The overall stability should be improved though.

---

# geeViz 2025.3.6 Release Notes

## March 31, 2025

### Bug fixes

- `geeViz.geeView` `Map.view()` bug fix for Google Colab. Updated to handle the new Google Colab proxy syntax. The old syntax should work still should they switch back in the future.

---

# geeViz 2025.3.5 Release Notes

## March 31, 2025

### New Features

- **New `examples.LANDTRENDRVizNotebook.ipynb`** - Adapted the `examples.LANDTRENDRViz.py` script to a notebook format. Use this to learn how to take exported LandTrendr outputs and visualize them and use them for change detection.

- **New `examples.Aboveground_Biomass_Viewer_Notebook.ipynb`** - Shows how the visualize and summarize the ESA CCI Global Forest Above Ground Biomass dataset using `geeViz`.

---

# geeViz 2025.3.4 Release Notes

## March 21, 2025

### Bug fixes

- `geeViz.geeView` auto-authentication/initialization create directory bug fix. In the past, this module would always try to create a `.config` directory. Not it only does this if it is using the standard refresh token auth method.

- `examples.LANDTRENDRWrapperNotebook` study area bug fix. The `studyArea` was called on before it was declared in the first example. This was removed.

---

# geeViz 2025.3.3 Release Notes

## March 17, 2025

### New Features

- `getImagesLib.simpeWaterMask` `elevationImagePath` `ee.Image | ee.ImageCollection` support - You can now provide an `ee.Image` or `ee.ImageCollection` type input for the `elevationImagePath` parameter. Previously, this had to be a string. Since some elevation assets are `ee.ImageCollections` supporting additional types was needed.

---

# geeViz 2025.3.2 Release Notes

## March 5, 2025

### New Features

- **`getImagesLib.superSimpleGetS2` `studyArea` Optional** - You no longer have to provide a studyArea for the `getImagesLib.superSimpleGetS2` method. This allows for global, map extent focused applications to use this method. When using this method, only the `.filterDate` method will render an output, so `startJulian` and `endJulian` are ignored. Ideally the `startDate` and `endDate` will suffice.

- **`examples.LANDTRENDRWrapperNotebook.ipynb` Improved Markdown** - Improved the markdown for the `examples.LANDTRENDRWrapperNotebook.ipynb` for easier understanding of what is going on.

- **`examples.timeLapseExample.py` Updates** - Updated the assets and visualization methods in `examples.timeLapseExample.py`

---

# geeViz 2025.3.1 Release Notes

## March 3, 2025

### Bug fixes

- `geeViz layer indexing` simplification. Layer IDs are always the name with an index only appended if a layer with the same name was already added.

---

# geeViz 2025.1.6 Release Notes

## January 23, 2025

### Bug fixes

- `phEEnoViz` module bug fix with colormap causing method to fail. See `examples.phEEnoVizWrapper.py` for a working example of how to use this powerful tool.

- `Map.turnOnAutoAreaCharting` bug fix. Occasionally the tool would not activate when this method was called. This method has now been moved to a setTimeout callback, so it should activate more consistently.

---

# geeViz 2025.1.5 Release Notes

## January 23, 2025

### New Features

- **geeviz.org logo integration** - Updated geeViz branding logo

---

# geeViz 2025.1.4 Release Notes

## January 15, 2025

### New Features

- **geeviz.org migration** - Migrated documentation from https://gee-community.github.io/geeViz/build/html/index.html to the geeviz.org domain

---

# geeViz 2025.1.3 Release Notes

## January 9, 2025

### Bug fixes

- `examples.LCMS_Levels_Viewer_Notebook` import of the `lcmsLevelLookup` script path didn't work in Colab. Not it's imported as part of the geeViz module.

---

# geeViz 2025.1.2 Release Notes

## January 9, 2025

### New Features

- **getImagesLib.getClimateWrapper Exporting** - You can now specify whether you'd like to export to Google Cloud Storage or an Earth Engine asset with the `getImagesLib.getClimateWrapper` function.

---

# geeViz 2025.1.1 Release Notes

## January 9, 2025

### New Features

- **LCMS Classification Levels Notebook** - A new example notebook showing how to crosswalk (remap) LCMS classes to various levels of thematic detail is now provided in `examples.LCMS_Levels_Viewer_Notebook`. This is intended to serve as a companion to a forthcoming LCMS manuscript.

---

# geeViz 2024.11.4 Release Notes

## November 26, 2024

### Bug fixes

- Follow-on bug fix - Area Charting Tools UI is not only visible if an area charting layer has been added to the map. Previously, the UI would show an older area charting UI if no area charting layers had been added the map.

---

# geeViz 2024.11.3 Release Notes

## November 25, 2024

### New Features

- **geeViz.geeView Enanced Image Area Charting** - geeViz.geeView aera charting for thematic images now tries to optimize the orientation of the bar chart based on the length of the class labels. Any chart with long class label lengths will be a horizontal bar chart. Short class labels will remain a vertical bar chart as it has always been. Also, the Plotly `autoMargin` functionality is now used for these charts.

### Bug fixes

- Area Charting Tools UI is not only visible if an area charting layer has been added to the map. Previously, the UI would show an older area charting UI if no area charting layers had been added the map.

---

# geeViz 2024.11.2 Release Notes

## November 11, 2024

### New Features

- **geeViz.geeView Enanced Error Handling** - geeViz.geeView no longer falls back on default credentials if loading fails. The error messaging has been improved to help users navigate likely causes of loading failures so they can continue to use the same credentials on the Python and javaScript side (using a temporary access token) of geeViz.geeView.

### Bug fixes

- `examples.CCDCVizNotebook` endYear bug fix. The endYear was set to 2024, but needed set to 2022 for the first few code blocks.

---

# geeViz 2024.11.1 Release Notes

## November 8, 2024

### New Features

- **CCDC Feathering Documentation** - The ability to combine two CCDC raw array `ee.Image` outputs for prediction and change detection has been streamlined and included in examples `examples.CCDCVizNotebook` and `examples.CCDCViz`, along with improved Pydocs.

- **Annual NLCD Example Notebook** - New notebook for Annual NLCD has been included in `examples.Annual_NLCD_Viewer_Notebook`. This notebook walks through how to visualize, summarize, and explore Annua NLCD products.

---

# geeViz 2024.10.1 Release Notes

## October 25, 2024

### New Features

- **geeView UI Layout Enhancements** - UI has had minor enhancements to improve use of space and alignment.

- **upload_to_gcs overwrite setting** - `assetManagerLib.upload_to_gcs` `overwite` parameter. By default, it is now set to `False`. This can be a breaking change since before it was unset, leaving it to essentially be `overwrite = True`.

- **cloudStorageManager new functions** - `cloudStorageManager.list_files`, `cloudStorageManager.bucket_exists`, and `cloudStorageManager.create_bucket` functions to facilitate various cloud storage tasks.

- **geeView query yLabel setting** - Can now set the `yLabel` (`vizParams["queryParams"]["yLabel"]`) to label the y axis of a query chart. See pydoc for `Map.addLayer` and `Map.addTimeLapse` for details.

- **geeView minZoomSpecifiedScale** - Can now set min zoom level to start changing zonal stats reduction scale changes (`vizParams["areaChartParams"]["minZoomSpecifiedScale"]`). This is useful to avoid memory errors, but ideally, can be set to a lower zoom level if possible. See pydoc for `Map.addLayer` and `Map.addTimeLapse` for details.

---

# geeViz 2024.9.3 Release Notes

## September 20, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website. Numerous function-wise examples added to the code.

- **GEE Palettes Integration** - Converted Gena's EE Palettes json to a Python script/module. Use the module as `import geeViz.geePalettes as palettes`

### Bug fixes

- `Map.addLayer` and `Map.addTimeLapse` functions now create a copy of the `viz` param dictionary. If you passed a dictionary, and then reused that in another layer call, the `layerType` key was then populated and wouldn't be updated, this resulting in an object type error. By creating a copy, the dictionary isn't changed outside the function.

---

# geeViz 2024.9.2 Release Notes

## September 18, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website.

- **Simple Sentinel-2** - `getImagesLib.superSimpleGetS2` is a super lightweight function to get analysis-ready Sentinel-2 data integrating the cloudScore+ algorithm. This may be a better option than existing functions that support out-dated legacy methods that are no longer needed since cloudScore+ works so well.

---

# geeViz 2024.9.1 Release Notes

## September 6, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website.

- **MapBiomas Example Rework** - The MapBiomas example script and notebook now integrate a full mosaic of all study areas and the ability to collapse to lower levels of the classification hiearchy.

---

# geeViz 2024.8.3 Release Notes

## August 28, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website - logo bug fix..

---

# geeViz 2024.8.2 Release Notes

## August 28, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website.

- **New and Updated Example Notebooks** - Global Landcover notebook added and updates to MapBiomas example notebook and script.

---

# geeViz 2024.8.1 Release Notes

## August 23, 2024

### New Features

- **Doc updates** - Continued work improving Documentation website. Notably integrating notebook examples into doc website.

### Bug fixes

- Function parameter reordering bug fix for `getImagesLib.getS2`

---

# geeViz 2024.7.1 Release Notes

## July 1, 2024

### New Features

- **CloudScore+ cs_cdf band support** - You can now utilize the `"cs_cdf"` band from the cloudScore+ algorithm in any of the Sentinel-2 image prep functions in the `getImagesLib` (`getS2`, `getProcessedSentinel2Scenes`, `getProcessedLandsatAndSentinel2Scenes`, `getSentinel2Wrapper`, `getLandsatAndSentinel2HybridWrapper`) by specifying `cloudScorePlusScore = "cs_cdf"`.

- **LayerType optimizing** - The specification of the `layerType` insize the visualization pareters in a `Map.addLayer` function is now largely unnecessary since an efficient object type method has been added.

### Bug fixes

- Area charting add layer bug fix for adding area chart layers without delcared object type.

---

# geeViz 2024.5.3 Release Notes

## May 15, 2024

### New Features

- **Larger Area Charts for Downloading** - Area charts no automatically scale by 2x for downloading

- **Sankey Charts Filtering** - Any class less than a specified percentage (`sankeyMinPercentage` - default : `0.5%`) won't be shown in the sankey chart. This helps clean up largely meaningless transitions from being shown.

- **Composite uploading support** - `assetManagerLib.uploadToGEEImageAsset` now supports composite uploading using the `"GSUtil:parallel_composite_upload_threshold` setting.

### Bug fixes

- Sentinel-2 QA bands being set to null instead of 0 since ~Feb 2024 bug fixed. QA bands are no longer required to have values for a pixel to be valid.

---

# geeViz 2024.5.2 Release Notes

## May 1, 2024

### Bug fixes

- Google Colab bug fix - earthengine-api changed `ee.oauth._in_colab_shell()` to `ee.oauth.in_colab_shell()`. Backward compatability supported for older function name.

---

# geeViz 2024.5.1 Release Notes

## May 1, 2024

### Bug fixes

- Area charting bug fixes and time lapse uneven dates slider bug fix.

---

# geeViz 2024.4.1 Release Notes

## April 4, 2024

### New Features

- **Area Charting Example Notebook** - There is now an area chart example notebook that walks through many examples of the available methods for charting zonal stats of ee images and imageCollections.

### Bug fixes

- Area charting bug fixes for various data types including thematic images.

---

# geeViz 2024.3.1 Release Notes

## March 22, 2024

### Bug fixes

- You can now use `Map.addLayer` or `Map.addTimeLapse` with an image collection where `"canAreaChart" : True` and `"reducer : ee.Reducer.frequencyHistogram()` but no `bandName_class_values`, `bandName_class_names`, `bandName_class_palette` are provided. Previously, this would not work.

- Fixed bug where `areaChartParams` `reducer` was not being handled properly for `Map.addTimeLapse` calls.

---

# geeViz 2024.3.1 Release Notes

## March 21, 2024

### New Features

- **Documentation for geeViz** - We are working on including docstrings and corresponding documentation. The site is located here: <https://gee-community.github.io/geeViz/build/html/index.html>

- **Map Layer area charting option** - Can now include any map layer for area summarizing using the `"canAreaChart" : True` inside the `viz` parameters dictionary. The `lcmsViewerExample.py` and new `mapBiomasViewerExample.py` include the area charting functionality.

- **Map Biomas Example** - There is an example of how to visualize and explore the Map Biomas land use / land cover datasets provided in `mapBiomasViewerExample.py`.

- **Linearly Interpolated Color Ramp** - A function to linearly interpolate a set of hex colors given a starting set of colors, and min and max values (`geeview.get_poly_gradient_ct`). This is useful for charting values.

### Bug fixes

- When querying layers, if `"autoViz" :True` or a `queryDict` is provided, but there is a queried value that is returned not found in that dictionary, the value will be shown instead. Previously, this would result in an error.

---

# geeViz 2024.2.3 Release Notes

## February 8, 2024

### New Features

- **Map Layer Drag Reordering Deactivation Option** - Can now deactivate layer reordering using `Map.setCanReorderLayers(False)`.

### Bug fixes

- Layer reordering with > 10 layers bug fixed. Sorting > 10 would sort 1,10,11,2,3,....etc. `geeVector` layerType is now frozen and cannot be reordered. This is because Google Maps API doesn't treat vector layers the same as raster overlays.Support for reordering vectors on the map is not supported.

---

# geeViz 2024.2.2 Release Notes

## February 7, 2024

### New Features

- **Map Layer Drag Reordering** - Can now reorder non-timelapse map layers by clicking and dragging the layer up or down. This feature still can be buggy depending on the underlying layer type.

- **CCDC output smart join method** - The `batchFeatherCCDCImgs` will take two time series of CCDC coefficients (typically created using `predictCCDC`), and linearly weight which coefficients are being used across a user-specified transition period (`featherStartYr`,`featherEndYr`). This allows for a smooth way of splicing together two sets of CCDC outputs with a generous overlapping time period. An example script of how to use this will be provided in a future release once this function solidifies a bit.

---

# geeViz 2024.2.1 Release Notes

## February 7, 2024

### Bug fixes

- The reducer in `batchSimpleLTFit` was hard-coded to `.max` for reducing any multi-image inputs for a given band/index. This resulted in nulls or errors in overlapping areas if LandTrendr arrays were being mosaicked. There is now a parameter `mosaicReducer` that can be set to handle overlapping values as you see fit. For array formatted outputs, it has to be `ee.Reducer.firstNonNull()` or `ee.Reducer.lastNonNull()` (default) since GEE doesn't handle array reductions well for imageCollection reductions.

---

# geeViz 2024.1.1 Release Notes

## January 19, 2024

### New Features

- **Improved cloudStorage Support** - Can now manage cloudStorage assets with the `cloudStorageManagerLib.py` module.

- **Improved `exportToCloudStorageWrapper`** - The `exportToCloudStorageWrapper` now can overwrite running tasks or existing cloudStorage blobs if `overwrite = True` is specified. Additionally, support for TFrecords is not handled.

- **geemap integration** - We are starting to use the `geemap` package when possible. There is a new example script `geeViz_and_geemap.py` that we will be building on to illustrate using geemap with geeViz. The first example illustrates how you would take a shapefile, use `geemap` to convert it to an ee object, and the use that in a `geeViz` workflow.

### Bug fixes

- If `ee.Initialize(project='someProjectID')` is called on prior to importing geeViz, that project will automatically be used

---

# geeViz 2023.12.6 Release Notes

## December 21, 2023

### New Features

- **Easier Colab Availability** - Colab links are now provided in each notebook in the examples folder.

### Bug fixes

- 'addLayer' Viz params `reducer` bug fix. When a reducer within a `viz` dictionary is passed to the map with a `addLayer` call more than once, geeViz would try to serialize it again resulting in an error. It now accepts it and assumes it's already been serialized.

---

# geeViz 2023.12.5 Release Notes

## December 21, 2023

### Bug fixes

- Fixed bug when `ee.oauth.get_credentials_path()` folder didn't exist already and geeViz tried to store the selected project within it. The folder is now created if it does not exist. This is needed when `ee.Authenticate` does not automatically make the folder.

---

# geeViz 2023.12.4 Release Notes

## December 21, 2023

### Bug fixes

- Fixed bug where project was not read in if ee was initialized outside of geeViz. `setProject` is run when geeView is imported which sets the `project_id` to the project provided in `ee.Initialize` if it was provided.

---

# geeViz 2023.12.3 Release Notes

## December 21, 2023

### New Features

- **Enhanced project support** - More robust handling of projects for authentication, as well as geeViz viewer authentication. The same project you are using in Python is now used in `geeView`.

### Bug fixes

- `geeView` query of collections with over 5000 image\*bands values would not query. Reverted to older getRegion-based query method.

---

# geeViz 2023.12.2 Release Notes

## December 8, 2023

### New Features

- **Color name support** - Colors for `vizParams` `palette` and `classLegendDict` can now be provided as standard w3 color name strings.

- **simpleLTFit batchSimpleLTFit multBy support** - Better support for ingesting landTrendr array vertex outputs that are multiplied by 10000 using the `multBy` parameter in the `simpleLTFit` `batchSimpleLTFit` functions. E.g. if the fitted vertex values were multiplied by 10000, set `multBy = 0.0001`.

---

# geeViz 2023.12.1 Release Notes

## December 4, 2023

### New Features

- **Simplified simpleLANDTRENDR** - the `simpleLANDTRENDR` function has been reworked to be more streamlined, but still provide the same functionality. Steps it uses are now available as stand-alone functions. These include the following new functions: `runLANDTRENDR, multLT, LTLossGainExportPrep, and addLossGainToMap` and the following previously existing functions: `simpleLTFit and convertToLossGain`. The `LANDTRENDRViz.py`, `LANDTRENDRWrapper.py`, and `LANDTRENDRWrapperNotebook.ipynb` examples have all been updated to utilize these reworked functions.

- **setQueryPrecision for Charting** - The precision of query outputs is now handled better. It can be changed by using the `Map.setQueryPrecision` function. Any floating point number will be constrained by the maximum of `chartPrecision` or `chartDecimalProportion*len(someFloatingPointNumber)`. The default is `3` and `0.25` respectively. E.g. if the number is `0.12345`, `max[3,ceiling(len(0.12345)*0.25)] = 3`, so the final number would be `0.123`.

- **setQueryDateFormat for Charting** - The date format can be changed by using the `Map.setQueryDateFormat` function or `queryDateFormat` property within the viz params for a `Map.addLayer` or `Map.addTimeLapse` call. E.g. if you want to only show the year in a chart, you'd put `Map.setQueryDateFormat('YYYY')` or if you need hours and minutes, `Map.setQueryDateFormat('YYYY-MM-dd HH:mm')`

### Bug fixes

- ImageCollection query bug when some pixels were null, but there was a `queryDict` provided is now fixed

---

# geeViz 2023.10.1 Release Notes

## October 31, 2023

### New Features

- **cloudScore+ For Sentinel-2** - cloudScore+ is now available for cloud and cloud shadow masking for Sentinel-2. It is available for all Sentinel-2 functions/wrappers/examples.

- **mosiac time lapses** - if an input imageCollection for an `addTimeLapse` call has multiple images per date, you can now have them mosaicked on-the-fly by using `{'mosaic':True}` in the viz parameters.

- **Reducers for imageCollections in addLayer** - When adding an imageCollection with `Map.addLayer`, you can now specify the reducer that is used to reduce the imageCollection to a single image to show on the map. Use `{'reducer':ee.SomeReducer()}` in the viz params.

### Bug fixes

- Improved Y axis label overcrowding image query charting robustness

---

# geeViz 2023.9.1 Release Notes

## September 20, 2023

### New Features

- **queryDict Chart Y Tick Labels** - Charting any imageCollection from a `Map.addLayer` or `Map.addTimeLapse` call will automatically use the `queryDict` `viz` parameter (e.g. `Map.addLayer(someLayer,{"queryDict":{1:"Trees",2:"Grass",3:"Water"}},"SomeLayerName")`) to label the Y axis ticks with class names. If class names are too long, they will be shortened. The max character length and the max characters per line in a Y axis tick label can be changed using `Map.setYLabelMaxLength` and `Map.setYLabelBreakLength` respectively.

### Bug fixes

- Improved array and mixed array and traditional image query charting robustness

---

# geeViz 2023.8.7 Release Notes

## August 24, 2023

### New Features

- **extractPointValuesToDataFrame** - `gee2Pandas.extractPointValuesToDataFrame` function extract values as a Pandas data frame. Will handle images or imageCollections automatically.

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.6 Release Notes

## August 23, 2023

### New Features

- **imageArrayPixelToDataFrame** - `gee2Pandas.imageArrayPixelToDataFrame` function to easily visualize image array values as a Pandas data frame.
- **new_interp_date** - `changeDetectionLib.new_interp_date` experimental function to interpolate dates. This method is likely no faster than the previous method (`changeDetectionLib.linearInterp`), but does extrapolate in a more expected manner.

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.5 Release Notes

## August 17, 2023

### New Features

- **setZoom** - `setZoom` function to set the zoom level of the map within `geeView.Mapper` . This functionality is also avail
  able in the `centerObject` function where the zoom level can optionally be set.

- **Date Interpolation now optional for annualizing CCDC** - `annualizeCCDC` and `getTimeImageCollectionFromComposites` functions now can have the linear interpolation turned off. Turning interpolation off will speed up creating outputs, but will result in null values where any date image data are missing.

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.4 Release Notes

## August 10, 2023

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.3 Release Notes

## August 9, 2023

### Bug fixes

- Minor bug fixes

---

# geeViz 2023.8.2 Release Notes

## August 7, 2023

### New Features

- **robust_featureCollection_to_df** - `robust_featureCollection_to_df` in the `gee2Pandas` module will handle large featureCollection conversion to a Pandas dataframe.

### Bug fixes

- `create_asset` will now handle nested folder creation with `recursive = True`.

---

# geeViz 2023.8.1 Release Notes

## August 3, 2023

### New Features

- **verbose parameter** - `getImagesLib` Landsat and Sentinel 2 functions now can be less verbose when run. This helps clean up the console. By defult, `verbose = False`.

### Bug fixes

- `assetManagerLib` has improved error handling when various operations cannot be performed - likely due to permissions errors.

---

# geeViz 2023.7.5 Release Notes

## July 28, 2023

### New Features

- **geeView Vertex AI Workbench lab Support** - `geeView` can now be used in Vertex AI notebooks. This support may present authentication bugs depending on how you are authenticating to GEE. You must provide the URL from which the lab is being run as the variable `proxy_url`. This can be set as `MapObject.proxy_url = https://code-dot-region.notebooks.googleusercontent.com/`. If it is not provided before a `.view()` call is made, the user will be prompted to enter it. This attribute will stick with the Map object for the duration of its existence.

---

# geeViz 2023.7.4 Release Notes

## July 24, 2023

### New Features

- **exportToAssetWrapper overwrite support in wrappers** - `getLandsatWrapper`, `getSentinel2Wrapper`, and `getLandsatAndSentinel2HybridWrapper` can now be run with `overwrite` set to `True` or `False`. It will check to see if the asset either exists or is currently being exported. If set to `True` it will stop the export or delete the existing asset and restart it. If set to `False`, it will not start the export.

---

# geeViz 2023.7.3 Release Notes

## July 24, 2023

### New Features

- **exportToAssetWrapper overwrite support** - `exportToAssetWrapper` can now be run with `overwrite` set to `True` or `False`. It will check to see if the asset either exists or is currently being exported. If set to `True` it will stop the export or delete the existing asset and restart it. If set to `False`, it will not start the export.

---

# geeViz 2023.7.2 Release Notes

## July 19, 2023

### New Features

- **geeView Colab Support** - `geeView` can now be used in Google Colab notebooks. This support may present authentication bugs depending on how you are authenticating to GEE.

---

# geeViz 2023.7.1 Release Notes

## July 14, 2023

### New Features

- **More robust authentication and initialization** - There are many inconsistencies being introduced for authenticating and initializing to GEE. A new function (`geeViz.geeView.robustInitializer`) attempts to handle some of these scenarios. It is not solid though and if you know your particular environment setup, it is best to authenticate and initialize before importing geeViz. There is also difficulty with authenticating on the javaScript client for geeView for some GEE accounts. If the javaScript instance fails to initialize, it will fall back on an existing auth proxy. Since this uses an account different from your own, it may result in errors in accessing assets for viewing in geeView. This can be solved by sharing assets publically.

### Bug fixes

- `changeDetectionLib.getTimeImageCollectionFromComposites` has been updated to fill in a blank image for any missing years and allow a year range to be specified to allow for interpolation and extrapolation. The unused parameters of `startJulian` and `endJulian` are no longer used.

---

# geeViz 2023.6.1 Release Notes

## June 13, 2023

### New Features

- **Folium based simple GEE object viewer** - A Folium-based GEE object viewer is now available (`foliumView.py`). The syntax is very similar to geeView. It tends to load faster, but be quite buggy with layer ordering, and lacks the ability to query values of layers. Examples are provided to help use it (`examples\foliumViewer.ipynb`,`examples\geeViewVSFoliumViewerExampleNotebook.ipynb`)

- **GEE2Pandas data science helper module** - A new module geared toward going between traditional data formats (csv, Excel, dbf, json, etc) and GEE (`gee2Pandas.py`). Functions are provided to go from a Pandas dataframe to GEE featureCollection and back. An example is provided (`examples\gee2PandasExample.ipynb`)

### Bug fixes

- geeView layer names with odd characters are now accepted (`e.g. / \ `)

---

# geeViz 2023.4.1 Release Notes

## April 11, 2023

### New Features

- **Default Query Output Location Change** - Query outputs are not placed in the side pane where the legend is located.

  - To back to using the default on-map infoWindow use: `Map.setQueryToInfoWindow()`

- **Improved Upload To Asset Capabilities** - Can now upload tifs to gee assets more easily and handle setting a number of paramters (`assetManagerLib.uploadToGEEImageAsset`) and (`assetManagerLib.ingestImageFromGCS`)

### Bug fixes

- All MODIS collections have been updated to newer 061 collections
- Query box size now reflects the chosen scale

---

# geeViz 2023.3.1 Release Notes

## March 22, 2023

### New Features

- **Query (inspector) parameters setting** - Can now set the click query projection (crs, scale and/or transform), and query box color parameters.
  - To set the query box color: `Map.setQueryBoxColor(hexColor)`
  - To set the query crs: `Map.setQueryCRS(crs)`
  - To set the query transform: `Map.setQueryTransform(transform)` (note: this will set the scale to null)
  - To set the query scale: `Map.setQueryScale(scale)` (note: this will set the transform to null)
- **LandTrendr Array Image Support** - Can now export the raw LandTrendr array image output for vertex values only as well as RMSE (`changeDetectionLib.rawLTToVertices`). Functions to annualize vertex-only array images are now available too (`changeDetectionLib.simpleLTFit` with `arrayMode = True`. See the LANDTRENDRWrapper example script for a detailed example.
- **Improved `Map.addLayer` error handling** - Any ee object added using a `Map.addLayer` call that fails to load will show an error and not load onto the map rather than stopping the entire map from loading.

### Bug fixes

- Landsat and Sentinel 2 resampling was set for all bands, including the qa bits. This resulted in speckling around the edges of cloud, cloud shadow, and snow masks. Now, the resampling method remains nearest neighbor for any qa bit band for both Landsat and Sentinel 2. This bug does not exist for MODIS since all masking is performed on continuous bands or the underlying mask of the thermal data.

---

# geeViz 2023.1.3 Release Notes

## January 26, 2023

### New Features

- **Join Collections Using Different Field Names** - The `joinFeatureCollections` and `joinCollections` functions now optionally support different field names between the two collections. e.g. `joinFeatureCollections(primaryFC,secondaryFC,'primaryFieldName','secondaryFieldName')`

---

# geeViz 2023.1.2 Release Notes

## January 18, 2023

### New Features

- **Sentinel 1 Basic Processing** - Integration of Guido Lemoine's shared GEE adaptation of the Refined Lee speckle filter from [this script](https://code.earthengine.google.com/2ef38463ebaf5ae133a478f173fd0ab5) as coded in the SNAP 3.0 S1 Toolbox. This can be found in the `getS1` function in the `getImagesLib`.

---

# geeViz 2023.1.1 Release Notes

## January 17, 2023

### Bug fixes

- When loading very large/complicated outputs into geeView, it would often not load the first time. This bug has been fixed to the page properly loads even with very large/complicated EE objects. It can take a while to load the page however.

---

# geeViz 2022.7.2 Release Notes

## July 8, 2022

### New Features

- **geeView Service Account Options** - geeView can now utilize a service account key for authentication to GEE. For general guidance for setting up a service account, [see this](https://developers.google.com/earth-engine/guides/service_account). This service account must be white-listed using [this tool](https://signup.earthengine.google.com/#!/service_accounts). Be sure to download the json key to a local, unshared location. To have geeView use a service account key, specify the path to the json key file as the `serviceKeyPath` attribute of the Map object (e.g. `Map.serviceKeyPath = r"c:\someFolder\keyFile.json"`). This will cause geeView to use that file to gain access to GEE instead of using the default persistent refresh token. If it fails, geeView will then try to use the persistent credential method.

---

# geeViz 2022.7.1 Release Notes

## July 6, 2022

### New Features

- **geeView Token Options** - geeView now tries to utilize the default location GEE refresh token instead of a proxy. It cannot use private keys from service accounts. You can however specify a different location of the refresh token from the default (e.g. `Map.accessToken = r'C:\someOtherFolder\someOtherPersistentCredentials`).
  If geeView fails to find a refresh token, it will fall back to utilizing the default proxy location. If that fails, a message will appear. It is best to simply ensure there is a working refresh token available (most easily created using `earthengine authenticate` or `ee.Authenticate()`).

---

# geeViz 2022.6.1 Release Notes

## June 17, 2022

### New Features

- **Landsat 9 Integration** - Landsat 9 is now included for all Collection 2 Landsat functions.
- **Specify geeView port** - You can now specify which port to run geeView through by specifying it (e.g. `Map.port = 8000`).

---

# geeViz 2022.4.2 Release Notes

## April 15, 2022

### New Features

- **GFS Time Lapse Example** - A new example script illustrating how to visualize the GFS forecast model outputs.

### Bug fixes

- When running geeViz from inside certain IDEs (such as IDLE), the use of sys.executable to identify how to run the local web server would hit on the pythonw instead of python executable. If it finds a pythonw under the sys.executable variable, it now forces it to use the python (without a w).

---

# geeViz 2022.4.1 Release Notes

## April 1, 2022

### New Features

- **Improved LandTrendr decompression method.** - A new function called batchSimpleLTFit has been added to the changeDetectionLib to help provide a faster method for decompressing the LandTrendr stacked output format into a usable time series image collection with all relevant metrics from LandTrendr.

- **LANDTRENDRViz example script.** - A new example script that demonstrates how to visualize and post-process LandTrendr outputs.

- **Common projection info dictionary** - In order to help organize common projections, a common_projections dictionary is now provided in the getImagesLib module.

### Bug fixes

- Landsat Collection 2 Level 2 data often have null values in the thermal band. Past versions of geeViz forced all bands to have data (some earlier scenes would have missing data in some but not all bands). This would result in null values in all bands over any area the new Collection 2 surface temperature algorithm could not compute an output. In order to handle this, for Landsat data, all optical bands found in TM, ETM+, and OLI sensors (blue, green, red, nir, swir1, swir2) must have data now, thus allowing a null thermal value to carry through.
- Related to the bug fix above - The medoidMosaicMSD function would still result in a null output if any band had null values. In order to fix this, the min reducer was swapped with the qualityMosaic function and the sum of the squared differences is multiplied by -1 so the qualityMosaic function can function properly. This results in almost the identical result. As the sum of the squared differences approaches 0 for more than a single observation for a given pixel, this method can result in a slightly different pixel choice, but should not make any substantive differences in the final composite.
- Removed the layerType key from the vizParams found within the getImagesLib. If imageCollections were added to the map using addLayer or addTimeLapse, they would not render if using any of the vizParams (vizParamsFalse and vizParamsTrue) since the layer type was explicitly specified as geeImage. You can add the relevant property back into those dictionaries in order to speed up map rendering. Example scripts that make use of these vizParams dictionaries have been updated. e.g. getImagesLib.vizParamsFalse['layerType']= 'geeImage' or getImagesLib.vizParamsFalse['layerType']= 'geeImageCollection'

---

# geeViz 2022.2.1 Release Notes

## February 14, 2022

### New Features

- **LCMAP_and_LCMS_Viewer Script and Notebook.** - A new example viewer that displays two US-wide change mapping products - Land Change Monitoring, Assessment, and Projection (LCMAP) produced by USGS and the Landscape Change Monitoring System (LCMS) produced by USFS. Land cover, land use, and change outputs from each product suite are displayed for easy comparison. The notebook facilitates the comparison by bringing in each set of data from the data suites into separate viewers.

- **Task Tracking in Example Scripts** - While the taskManagerLib is not new, the task tracking functionality available within that module was added to the example scripts that export data.

### Bug fixes

- Fixed bug in pulling CCDC most recent loss and gain year out. It now behaves in a similar manner as the most recent loss and gain outputs.

---

# geeViz 2021.12.1 Release Notes

## December 27, 2021

### New Features

- **Time Lapse Charting** - Any time lapse that is visible will be charted if double-clicked using "Query Visible Map Layers" tool.
- **Landsat Collection 2 Support** - Landsat Collection 2 is now used by default for all getLandsat methods. Collection 1 is still available by specifying landsatCollectionVersion = 'C1'. Specify 'C2' (which is the default) if you would like to use Collection 2.

---

# geeViz 2021.11.1 Release Notes

## November 19, 2021

### New Features

- None

### Bug fixes

- Fixed endDate for all filterDate calls. Previously, it had been assumed this was inclusive of the day of the endDate, when the GEE filterDate method is exclusive of the day of the endDate. Since the assumption is that all dates specified are inclusive, the current fix involves advancing all endDates provided to any filterDate function by 1 day.

---

# geeViz 2021.10.1 Release Notes

## October 15, 2021

### New Features

- **LANDTRENDRWrapper Notebook** - A new example of how to use LandTrendr in a Jupyter Notebook format. This is very similar to the script, but provides a little more detail of the resources available to run LandTrendr.

### Bug fixes

- geeView would not work in ArcPro Miniconda Python builds (and perhaps others). The new fix addresses this issue and allows it to run from Miniconda Python builds based from ArcPro

---

# geeViz 2021.8.1 Release Notes

## August 26, 2021

### New Features

- **Smarter GEE initialization** - All modules that call upon ee.Initialize will now check to ensure GEE hasn't already been initialized. If it hasn't, it will initialize.

### Bug fixes

- GEE occasionally wouldn't recognize an imageCollection as such when adding a TimeLapse. An explicit cast to imageCollection was now made.

---

# geeViz 2021.7.2 Release Notes

## July 28, 2021

### New Features

- **Back and foward view buttons** - Users can go backward and forward views within the geeView viewer.

### Bug fixes

- Fixed export wrappers exporting empty areas with GEE update to export methods

---

# geeViz 2021.7.1 and prior Release Notes

### New Features

- **Notebook examples** - Several examples are now available in an interactive notebook format under the examples module.
- **CCDC updates** - Updates to CCDC annualizing functionality.
- **MODIS Processing** - Similar pre-processing (cloud and cloud shadow masking) functionality that has been available for Landsat and Sentinel 2 now available for MODIS data.
