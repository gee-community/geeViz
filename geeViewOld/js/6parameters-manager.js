var includeLegend = true; //Whether to include a legend
var useShapes = false; //Whether to provie the ability of the user to draw polygons
var exportCapability = false; //Whether to include the ability to export EE data added with the addExport command (useShapes must = true)
var downloadCapability = true; //Whether to allow for pre-exported downloads
var includeTools = true; //Whether to include the distance, area, and charting tools
var userCharting = true; //Whether to provide the ability to chart values of keyword chartCollection
var displayParameters = true; //Whether to provide the ability to change EE parameters
var plotNavigation = false; //Whether to provide the capability to show a list of plot IDS with corresponding jump-to locations
var helpBox = true; //Whether to provide the capability to show a help box with a message about the webpage

// var initialCenter = [48.16,-113.08];//Provide initial map center (lat,lng)for first time user loads page
var initialCenter = [43.2, -110.1];
var initialZoomLevel = 8; //Provide initial map zoom level (1-20) for first time user loads page

var chartTypeOptions = true;