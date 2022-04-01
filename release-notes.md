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



