# geeViz 2023.8.7 Release Notes
## August 24, 2023

### New Features
* **extractPointValuesToDataFrame** - `gee2Pandas.extractPointValuesToDataFrame` function extract values as a Pandas data frame. Will handle images or imageCollections automatically. 

### Bug fixes
* Minor bug fixes

____
# geeViz 2023.8.6 Release Notes
## August 23, 2023

### New Features
* **imageArrayPixelToDataFrame** - `gee2Pandas.imageArrayPixelToDataFrame` function to easily visualize image array values as a Pandas data frame.
* **new_interp_date** - `changeDetectionLib.new_interp_date` experimental function to interpolate dates. This method is likely no faster than the previous method (`changeDetectionLib.linearInterp`), but does extrapolate in a more expected manner.


### Bug fixes
* Minor bug fixes

____
# geeViz 2023.8.5 Release Notes
## August 17, 2023

### New Features
* **setZoom** - `setZoom` function to set the zoom level of the map within `geeView.Mapper` . This functionality is also avail 
able in the `centerObject` function where the zoom level can optionally be set.

* **Date Interpolation now optional for annualizing CCDC** - `annualizeCCDC` and `getTimeImageCollectionFromComposites` functions now can have the linear interpolation turned off. Turning interpolation off will speed up creating outputs, but will result in null values where any date image data are missing.

### Bug fixes
* Minor bug fixes

____
# geeViz 2023.8.4 Release Notes
## August 10, 2023

### Bug fixes
* Minor bug fixes

____
# geeViz 2023.8.3 Release Notes
## August 9, 2023

### Bug fixes
* Minor bug fixes
____
# geeViz 2023.8.2 Release Notes
## August 7, 2023

### New Features
* **robust_featureCollection_to_df** - `robust_featureCollection_to_df` in the `gee2Pandas` module will handle large featureCollection conversion to a Pandas dataframe. 

### Bug fixes
* `create_asset` will now handle nested folder creation with `recursive = True`.
____
# geeViz 2023.8.1 Release Notes
## August 3, 2023

### New Features
* **verbose parameter** - `getImagesLib` Landsat and Sentinel 2 functions now can be less verbose when run. This helps clean up the console. By defult, `verbose = False`. 

### Bug fixes
* `assetManagerLib` has improved error handling when various operations cannot be performed - likely due to permissions errors.
____
# geeViz 2023.7.5 Release Notes
## July 28, 2023

### New Features
* **geeView Vertex AI Workbench lab Support** - `geeView` can now be used in Vertex AI notebooks. This support may present authentication bugs depending on how you are authenticating to GEE. You must provide the URL from which the lab is being run as the variable `proxy_url`. This can be set as `MapObject.proxy_url = https://code-dot-region.notebooks.googleusercontent.com/`. If it is not provided before a `.view()` call is made, the user will be prompted to enter it. This attribute will stick with the Map object for the duration of its existence. 
____
# geeViz 2023.7.4 Release Notes
## July 24, 2023

### New Features
* **exportToAssetWrapper overwrite support in wrappers** - `getLandsatWrapper`, `getSentinel2Wrapper`, and  `getLandsatAndSentinel2HybridWrapper` can now be run with `overwrite` set to `True` or `False`. It will check to see if the asset either exists or is currently being exported. If set to `True` it will stop the export or delete the existing asset and restart it. If set to `False`, it will not start the export.
____
# geeViz 2023.7.3 Release Notes
## July 24, 2023

### New Features
* **exportToAssetWrapper overwrite support** - `exportToAssetWrapper` can now be run with `overwrite` set to `True` or `False`. It will check to see if the asset either exists or is currently being exported. If set to `True` it will stop the export or delete the existing asset and restart it. If set to `False`, it will not start the export.
____
# geeViz 2023.7.2 Release Notes
## July 19, 2023

### New Features
* **geeView Colab Support** - `geeView` can now be used in Google Colab notebooks. This support may present authentication bugs depending on how you are authenticating to GEE. 
____
# geeViz 2023.7.1 Release Notes
## July 14, 2023

### New Features
* **More robust authentication and initialization** - There are many inconsistencies being introduced for authenticating and initializing to GEE. A new function (`geeViz.geeView.robustInitializer`) attempts to handle some of these scenarios. It is not solid though and if you know your particular environment setup, it is best to authenticate and initialize before importing geeViz. There is also difficulty with authenticating on the javaScript client for geeView for some GEE accounts. If the javaScript instance fails to initialize, it will fall back on an existing auth proxy. Since this uses an account different from your own, it may result in errors in accessing assets for viewing in geeView. This can be solved by sharing assets publically. 

### Bug fixes
* `changeDetectionLib.getTimeImageCollectionFromComposites` has been updated to fill in a blank image for any missing years and allow a year range to be specified to allow for interpolation and extrapolation. The unused parameters of `startJulian` and `endJulian` are no longer used.
____
# geeViz 2023.6.1 Release Notes
## June 13, 2023

### New Features
* **Folium based simple GEE object viewer** - A Folium-based GEE object viewer is now available (`foliumView.py`). The syntax is very similar to geeView. It tends to load faster, but be quite buggy with layer ordering, and lacks the ability to query values of layers. Examples are provided to help use it (`examples\foliumViewer.ipynb`,`examples\geeViewVSFoliumViewerExampleNotebook.ipynb`)

* **GEE2Pandas data science helper module** - A new module geared toward going between traditional data formats (csv, Excel, dbf, json, etc) and GEE (`gee2Pandas.py`). Functions are provided to go from a Pandas dataframe to GEE featureCollection and back. An example is provided (`examples\gee2PandasExample.ipynb`)

### Bug fixes
* geeView layer names with odd characters are now accepted (`e.g. / \ `)
____
# geeViz 2023.4.1 Release Notes
## April 11, 2023

### New Features
* **Default Query Output Location Change** - Query outputs are not placed in the side pane where the legend is located. 
    * To back to using the default on-map infoWindow use: `Map.setQueryToInfoWindow()`

* **Improved Upload To Asset Capabilities** - Can now upload tifs to gee assets more easily and handle setting a number of paramters (`assetManagerLib.uploadToGEEImageAsset`) and (`assetManagerLib.ingestImageFromGCS`)

### Bug fixes
* All MODIS collections have been updated to newer 061 collections
* Query box size now reflects the chosen scale
____
# geeViz 2023.3.1 Release Notes
## March 22, 2023

### New Features
* **Query (inspector) parameters setting** - Can now set the click query projection (crs, scale and/or transform), and query box color parameters. 
    * To set the query box color: `Map.setQueryBoxColor(hexColor)`
    * To set the query crs: `Map.setQueryCRS(crs)`
    * To set the query transform: `Map.setQueryTransform(transform)` (note: this will set the scale to null)
    * To set the query scale: `Map.setQueryScale(scale)` (note: this will set the transform to null)
* **LandTrendr Array Image Support** - Can now export the raw LandTrendr array image output for vertex values only as well as RMSE (`changeDetectionLib.rawLTToVertices`). Functions to annualize vertex-only array images are now available too (`changeDetectionLib.simpleLTFit` with `arrayMode = True`. See the LANDTRENDRWrapper example script for a detailed example.
* **Improved `Map.addLayer` error handling** - Any ee object added using a `Map.addLayer` call that fails to load will show an error and not load onto the map rather than stopping the entire map from loading.

### Bug fixes
* Landsat and Sentinel 2 resampling was set for all bands, including the qa bits. This resulted in speckling around the edges of cloud, cloud shadow, and snow masks. Now, the resampling method remains nearest neighbor for any qa bit band for both Landsat and Sentinel 2. This bug does not exist for MODIS since all masking is performed on continuous bands or the underlying mask of the thermal data.
____
# geeViz 2023.1.3 Release Notes
## January 26, 2023

### New Features
* **Join Collections Using Different Field Names** - The `joinFeatureCollections` and `joinCollections` functions now optionally support different field names between the two collections. e.g. `joinFeatureCollections(primaryFC,secondaryFC,'primaryFieldName','secondaryFieldName')`
____
# geeViz 2023.1.2 Release Notes
## January 18, 2023

### New Features
* **Sentinel 1 Basic Processing** - Integration of Guido Lemoine's shared GEE adaptation of the Refined Lee speckle filter from [this script](https://code.earthengine.google.com/2ef38463ebaf5ae133a478f173fd0ab5) as coded in the SNAP 3.0 S1 Toolbox. This can be found in the `getS1` function in the `getImagesLib`.
____
# geeViz 2023.1.1 Release Notes
## January 17, 2023

### Bug fixes
* When loading very large/complicated outputs into geeView, it would often not load the first time. This bug has been fixed to the page properly loads even with very large/complicated EE objects. It can take a while to load the page however.
____
# geeViz 2022.7.2 Release Notes
## July 8, 2022

### New Features
* **geeView Service Account Options** - geeView can now utilize a service account key for authentication to GEE. For general guidance for setting up a service account, [see this](https://developers.google.com/earth-engine/guides/service_account). This service account must be white-listed using [this tool](https://signup.earthengine.google.com/#!/service_accounts). Be sure to download the json key to a local, unshared location. To have geeView use a service account key, specify the path to the json key file as the `serviceKeyPath` attribute of the Map object (e.g. `Map.serviceKeyPath = r"c:\someFolder\keyFile.json"`). This will cause geeView to use that file to gain access to GEE instead of using the default persistent refresh token. If it fails, geeView will then try to use the persistent credential method.  
____
# geeViz 2022.7.1 Release Notes
## July 6, 2022

### New Features
* **geeView Token Options** - geeView now tries to utilize the default location GEE refresh token instead of a proxy. It cannot use private keys from service accounts. You can however specify a different location of the refresh token from the default (e.g. `Map.accessToken = r'C:\someOtherFolder\someOtherPersistentCredentials`). 
If geeView fails to find a refresh token, it will fall back to utilizing the default proxy location. If that fails, a message will appear. It is best to simply ensure there is a working refresh token available (most easily created using `earthengine authenticate` or `ee.Authenticate()`).
____
# geeViz 2022.6.1 Release Notes
## June 17, 2022

### New Features
* **Landsat 9 Integration** - Landsat 9 is now included for all Collection 2 Landsat functions.
* **Specify geeView port** - You can now specify which port to run geeView through by specifying it (e.g. `Map.port = 8000`).
____
# geeViz 2022.4.2 Release Notes
## April 15, 2022

### New Features
* **GFS Time Lapse Example** - A new example script illustrating how to visualize the GFS forecast model outputs.


### Bug fixes
* When running geeViz from inside certain IDEs (such as IDLE), the use of sys.executable to identify how to run the local web server would hit on the pythonw instead of python executable. If it finds a pythonw under the sys.executable variable, it now forces it to use the python (without a w).
____
# geeViz 2022.4.1 Release Notes
## April 1, 2022

### New Features
* **Improved LandTrendr decompression method.** - A new function called batchSimpleLTFit has been added to the changeDetectionLib to help provide a faster method for decompressing the LandTrendr stacked output format into a usable time series image collection with all relevant metrics from LandTrendr.

* **LANDTRENDRViz example script.** - A new example script that demonstrates how to visualize and post-process LandTrendr outputs.

* **Common projection info dictionary** - In order to help organize common projections, a common_projections dictionary is now provided in the getImagesLib module. 

### Bug fixes
* Landsat Collection 2 Level 2 data often have null values in the thermal band. Past versions of geeViz forced all bands to have data (some earlier scenes would have missing data in some but not all bands). This would result in null values in all bands over any area the new Collection 2 surface temperature algorithm could not compute an output. In order to handle this, for Landsat data, all optical bands found in TM, ETM+, and OLI sensors (blue, green, red, nir, swir1, swir2) must have data now, thus allowing a null thermal value to carry through. 
* Related to the bug fix above - The medoidMosaicMSD function would still result in a null output if any band had null values. In order to fix this, the min reducer was swapped with the qualityMosaic function and the sum of the squared differences is multiplied by -1 so the qualityMosaic function can function properly. This results in almost the identical result. As the sum of the squared differences approaches 0 for more than a single observation for a given pixel, this method can result in a slightly different pixel choice, but should not make any substantive differences in the final composite.
* Removed the layerType key from the vizParams found within the getImagesLib. If imageCollections were added to the map using addLayer or addTimeLapse, they would not render if using any of the vizParams (vizParamsFalse and vizParamsTrue) since the layer type was explicitly specified as geeImage. You can add the relevant property back into those dictionaries in order to speed up map rendering. Example scripts that make use of these vizParams dictionaries have been updated. e.g. getImagesLib.vizParamsFalse['layerType']= 'geeImage' or getImagesLib.vizParamsFalse['layerType']= 'geeImageCollection' 
____
# geeViz 2022.2.1 Release Notes
## February 14, 2022

### New Features
* **LCMAP_and_LCMS_Viewer Script and Notebook.** - A new example viewer that displays two US-wide change mapping products - Land Change Monitoring, Assessment, and Projection (LCMAP) produced by USGS and the Landscape Change Monitoring System (LCMS) produced by USFS. Land cover, land use, and change outputs from each product suite are displayed for easy comparison. The notebook facilitates the comparison by bringing in each set of data from the data suites into separate viewers.

* **Task Tracking in Example Scripts** - While the taskManagerLib is not new, the task tracking functionality available within that module was added to the example scripts that export data. 

### Bug fixes
* Fixed bug in pulling CCDC most recent loss and gain year out. It now behaves in a similar manner as the most recent loss and gain outputs.

____
# geeViz 2021.12.1 Release Notes
## December 27, 2021

### New Features
* **Time Lapse Charting** - Any time lapse that is visible will be charted if double-clicked using "Query Visible Map Layers" tool.
* **Landsat Collection 2 Support** - Landsat Collection 2 is now used by default for all getLandsat methods. Collection 1 is still available by specifying landsatCollectionVersion = 'C1'. Specify 'C2' (which is the default) if you would like to use Collection 2. 

____
# geeViz 2021.11.1 Release Notes
## November 19, 2021

### New Features
* None

### Bug fixes 
* Fixed endDate for all filterDate calls. Previously, it had been assumed this was inclusive of the day of the endDate, when the GEE filterDate method is exclusive of the day of the endDate. Since the assumption is that all dates specified are inclusive, the current fix involves advancing all endDates provided to any filterDate function by 1 day.
____
# geeViz 2021.10.1 Release Notes
## October 15, 2021

### New Features
* **LANDTRENDRWrapper Notebook** - A new example of how to use LandTrendr in a Jupyter Notebook format. This is very similar to the script, but provides a little more detail of the resources available to run LandTrendr.

### Bug fixes 
* geeView would not work in ArcPro Miniconda Python builds (and perhaps others). The new fix addresses this issue and allows it to run from Miniconda Python builds based from ArcPro
____
# geeViz 2021.8.1 Release Notes
## August 26, 2021

### New Features
* **Smarter GEE initialization** - All modules that call upon ee.Initialize will now check to ensure GEE hasn't already been initialized. If it hasn't, it will initialize.

### Bug fixes 
* GEE occasionally wouldn't recognize an imageCollection as such when adding a TimeLapse. An explicit cast to imageCollection was now made.
____
# geeViz 2021.7.2 Release Notes
## July 28, 2021

### New Features
* **Back and foward view buttons** - Users can go backward and forward views within the geeView viewer.

### Bug fixes 
* Fixed export wrappers exporting empty areas with GEE update to export methods
____
# geeViz 2021.7.1 and prior Release Notes

### New Features
* **Notebook examples** - Several examples are now available in an interactive notebook format under the examples module.
* **CCDC updates** - Updates to CCDC annualizing functionality.
* **MODIS Processing** - Similar pre-processing (cloud and cloud shadow masking) functionality that has been available for Landsat and Sentinel 2 now available for MODIS data.



