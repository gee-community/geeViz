# geeViz 2021.8.1 Release Notes
## August 26, 2021

## New Features
* **Smarter GEE initialization** - All modules that call upon ee.Initialize will now check to ensure GEE hasn't already been initialized. If it hasn't, it will initialize.

## Bug fixes 
* GEE occasionally wouldn't recognize an imageCollection as such when adding a TimeLapse. An explicit cast to imageCollection was now made.



# geeViz 2021.7.2 Release Notes
## July 28, 2021

## New Features
* **Back and foward view buttons** - Users can go backward and forward views within the geeView viewer.

## Bug fixes 
* Fixed export wrappers exporting empty areas with GEE update to export methods


# geeViz 2021.7.1 and prior Release Notes

## New Features
* **Notebook examples** - Several examples are now available in an interactive notebook format under the examples module.
* **CCDC updates** - Updates to CCDC annualizing functionality.
* **MODIS Processing** - Similar pre-processing (cloud and cloud shadow masking) functionality that has been available for Landsat and Sentinel 2 now available for MODIS data.



