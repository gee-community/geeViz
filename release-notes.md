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



