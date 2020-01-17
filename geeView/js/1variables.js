//Load global variables
var lowerThresholdDecline = 0.3;
var upperThresholdDecline = 1.0;
var lowerThresholdRecovery = 0.3;
var upperThresholdRecovery = 1.0;
var studyAreaName = 'BTNF';
var startYear = 1984;
var endYear = 2019;
var startJulian = 153;//190;
var endJulian = 274;//250;
var layerObj = null;
var queryObj = {};
var initialCenter = [37.5334105816903,-105.6787109375];
var initialZoomLevel = 5;
var cachedStudyAreaName = null;
var studyAreaDict = {
                  'Flathead National Forest':{
                                                name:'FNF',
                                                center:[48.16,-115.08,8],
                                                crs:'EPSG:26911',
                                                lossThresh:0.4,
                                                lossFastThresh:0.4,
                                                lossSlowThresh:0.35,
                                                gainThresh:0.45,
                                                startYear:1985,
                                                endYear:2019,
                                            	popOver:"Flathead National Forest buffered along with Glacier National Park buffered by 1km"},
                  'Bridger-Teton National Forest':{
                                                  name:'BTNF',
                                                  center:[43.4,-111.1,8],
                                                  crs:'EPSG:26912',
                                                  lossThresh:0.4,
                                                  lossFastThresh:0.25,
                                                  lossSlowThresh:0.4,
                                                  gainThresh:0.45,
                                                  startYear : 1985,
                                                  endYear : 2019,
                                              	  popOver:"Bridger-Teton National Forest boundary buffered by 5km plus Star Valley"},
                  'Manti-La Sal National Forest':{
                                                  name:'MLSNF',
                                                  center:[38.8,-111,8],
                                                  crs:'EPSG:26912',
                                                  lossThresh:0.3,
                                                  lossFastThresh:0.4,
                                                  lossSlowThresh:0.3,
                                                  gainThresh:0.3,
                                                  startYear: 1985,
                                                  endYear: 2019,
                                              	  popOver:"Manti-La Sal National Forest"},
                  'Chugach National Forest - Kenai Peninsula':{
                                                name:'CNFKP',
                                                center:[60.4,-150.1, 9],
                                                crs:'EPSG:3338',
                                                lossThresh:0.35,
                                                gainThresh:0.45,
                                                startYear:1985,
                                                endYear:2019,
                                            	popOver:"Chugach National Forest - Kenai Peninsula"},
                  'Science Team CONUS':{
                                                name:'CONUS',
                                                center:[37.5334105816903,-105.6787109375,5],
                                                crs:'EPSG:5070',
                                                lossThresh:0.30,
                                                gainThresh:0.30,
                                                startYear:1985,
                                                endYear:2019,
                                            	popOver:"2019 LCMS Science Team CONUS-wide loss"}
                };

var clientBoundsDict = {'All':{"geodesic": false,"type": "Polygon","coordinates": [[[-169.215141654273, 71.75307977193499],
        [-169.215141654273, 15.643479915898974],
        [-63.043266654273, 15.643479915898974],
        [-63.043266654273, 71.75307977193499]]]},
                    'CONUS':{"geodesic": false,"type": "Polygon","coordinates": [[[-148.04139715349993,30.214881196707502],[-63.66639715349993,30.214881196707502],[-63.66639715349993,47.18482008797388],[-148.04139715349993,47.18482008797388],[-148.04139715349993,30.214881196707502]]]},
                    'Alaska':{"geodesic": false,"type": "Polygon","coordinates": [[[-168.91542059099993, 71.62680009186087],
        [-168.91542059099993, 52.67867842404269],
        [-129.54042059099993, 52.67867842404269],
        [-129.54042059099993, 71.62680009186087]]]},
                    'Hawaii':{"geodesic": false,"type": "Polygon","coordinates": [[[-162.7925163471209,18.935659110261664],[-152.2511345111834,18.935659110261664],[-152.2511345111834,22.134763696750557],[-162.7925163471209,22.134763696750557],[-162.7925163471209,18.935659110261664]]]},
                    'Puerto-Rico':{"geodesic": false,"type": "Polygon","coordinates": [[[-67.98169635150003,17.751237971831113],[-65.34635089251566,17.751237971831113],[-65.34635089251566,18.532938160084615],[-67.98169635150003,18.532938160084615],[-67.98169635150003,17.751237971831113]]]}
         }
// var applyTreeMask = true;
// var summaryMethod = 'recent';
var whichIndex = 'NBR';
// var viewBeta = false;
// var fc;//Feature collection container for drawing on map and submitting tasks with user-defined vectors
var toExport;
var exportArea;
var taskCount = 0;//Keeping track of the number of export tasks each session submitted
var canAddToMap = true;//Set whether addToMap function can add to the map
var canExport = false;//Set whether exports are allowed
var colorRampIndex = 1;
var NEXT_LAYER_ID = 1;var layerChildID = 0;
var layerCount = 0;var refreshNumber = 0;
var uri;var uriName;var csvName;var dataTable;var chartOptions;var infowindow;var queryGeoJSON;var marker;var mtbsSummaryMethod;

// var selectedFeatures;
var selectedFeaturesJSON = {};
var selectionUNID = 1;
// var selectedFeaturesNames;

var outputURL;
var tableConverter = null;
var groundOverlayOn = false;

var chartIncludeDate = true;var chartCollection;var areaChartCollections = {};var whichAreaChartCollection;var queryClassDict = {};var exportImage;var exportVizParams;var eeBoundsPoly;var shapesMap;
var mouseLat;var mouseLng; var area = 0;var distance = 0;var areaPolygon; var markerList = [];var distancePolylineT;var clickCoords;var distanceUpdater;
var updateArea;var updateDistance;var areaPolygonObj = {};var udpPolygonObj = {};var udpPolygonNumber = 1;var mapHammer;var chartMTBS;var chartMTBSByNLCD;var chartMTBSByAspect;

var distancePolyline;
var distancePolylineOptions = {
              strokeColor: '#FF0',
              icons: [{
                icon:  {
              path: 'M 0,-1 0,1',
              strokeOpacity: 1,
              scale: 4
            },
                offset: '0',
                repeat: '20px'
              }],
              strokeOpacity: 0,
              strokeWeight: 3,
              draggable: true,
              editable: true,
              geodesic:true
            };

var polyNumber = 1;
var polyOn = false;


var areaPolygonOptions = {
              strokeColor:'#FF0',
                fillOpacity:0.2,
              strokeOpacity: 1,
              strokeWeight: 3,
              draggable: true,
              editable: true,
              geodesic:true,
              polyNumber: polyNumber
            
            };

var userDefinedI = 1;

var udpOptions = {
          strokeColor:'#FF0',
            fillOpacity:0.2,
          strokeOpacity: 1,
          strokeWeight: 3,
          draggable: true,
          editable: true,
          geodesic:true,
          polyNumber: 1
        };
var exportAreaPolylineOptions = {
          strokeColor:'#FF0',
            fillOpacity:0.2,
          strokeOpacity: 1,
          strokeWeight: 3,
          draggable: true,
          editable: true,
          geodesic:true,
          polyNumber: 1
        };
var exportAreaPolygonOptions = {
          strokeColor:'#FF0',
            fillOpacity:0.2,
          strokeOpacity: 1,
          strokeWeight: 3,
          draggable: false,
          editable: false,
          geodesic:true,
          polyNumber: 1
        };
var exportImageDict = {};
var canExport = false;
var featureObj = {};var geeRunID;var outstandingGEERequests = 0;var geeTileLayersDownloading = 0;

var plotDictID = 1;
var exportID = 1;

// var metricOrImperial = 'metric';
var unitMultiplierDict = {imperial:
{area:[10.7639,0.000247105],distance:[3.28084,0.000621371]},
metric:
{area:[1,0.0001],distance:[1,0.001]}};

var unitNameDict = {imperial:
{area:['ft<sup>2</sup>','acres'],distance:['ft','miles']},
metric:
{area:['m<sup>2</sup>','hectares'],distance:['m','km']}};


//Chart variables
var plotRadius = 15;
var plotScale = 30;
var areaChartFormat = 'Percentage';
var areaChartFormatDict = {'Percentage': {'mult':100,'label':'% Area'}, 'Acres': {'mult':0.000247105,'label':'Acres'}, 'Hectares': {'mult':0.0001,'label':'Hectares'}};

var areaGeoJson;
var areaChartingCount = 0;
var center;var globalChartValues;

var chartTextColor = '#FFF';
var cssClassNames = {
'headerRow': 'googleChartTable',
'tableRow': 'googleChartTable',
'oddTableRow': 'googleChartTable',
'selectedTableRow': 'googleChartTable',
'hoverTableRow': 'googleChartTable',
'headerCell': 'googleChartTable',
'tableCell': 'googleChartTable',
'rowNumberCell': 'googleChartTable'};

var expandedWidth = $(window).width()/3;
var expandedHeight = $(window).height()/2;
var chartOptions = {
  title: uriName,
  titleTextStyle: {
	color: chartTextColor
},
  pointSize: 3,
  legend: { position: 'bottom',textStyle:{color: chartTextColor,fontSize:'12'} },
  dataOpacity: 1,
 hAxis:{title:'Year',
 				titleTextStyle:{color: chartTextColor},
				textStyle:{color: chartTextColor}
			},
	vAxis:{textStyle:{color: chartTextColor},titleTextStyle:{color: chartTextColor}},
	legend: {
        textStyle: {
            color: chartTextColor
        }
    },

   // width: 800, 
   height:250,
   bar: {groupWidth: "100%"},
   explorer: {  actions: [] },
    chartArea: {left:'5%',top:'10%',width:'75%',height:'70%'},
    legendArea:{width:'20%'},
   backgroundColor: { fill: "#1B1716" }

};
var tableOptions = {
	// width: 800, 
   // height:350,
    'allowHtml': true,
    'cssClassNames': cssClassNames};

// function updateProgress(pct) {
//     var elem = document.getElementById("Bar"); 
//     elem.style.width = pct + '%'; 
        
// }







var authProxyAPIURL = "https://rcr-ee-proxy.herokuapp.com/api";
var geeAPIURL = "https://earthengine.googleapis.com/map";
// var widgetsOn = true;
// var layersOn = true;
// var legendOn = true;
// var chartingOn = false;
// var distanceOn = false;
// var areaOn = false;
// var drawing = false;
var plotsOn = false;
// var helpOn = false;
// var queryOn = false;
// var areaChartingOn = false;
// var studyAreaName = 'BTNF'

/////////////////////////////////////////////////////
//Taken from: https://stackoverflow.com/questions/1669190/find-the-min-max-element-of-an-array-in-javascript
Array.prototype.max = function() {
  return Math.max.apply(null, this);
};

Array.prototype.min = function() {
  return Math.min.apply(null, this);
};
/////////////////////////////////////////////////////
//Taken from: https://stackoverflow.com/questions/2116558/fastest-method-to-replace-all-instances-of-a-character-in-a-string
String.prototype.replaceAll = function(str1, str2, ignore) 
{
    return this.replace(new RegExp(str1.replace(/([\/\,\!\\\^\$\{\}\[\]\(\)\.\*\+\?\|\<\>\-\&])/g,"\\$&"),(ignore?"gi":"g")),(typeof(str2)=="string")?str2.replace(/\$/g,"$$$$"):str2);
} 

Number.prototype.formatNumber = function(n){
  if(n === undefined || n === null){n = 2}
  return this.toFixed(n).replace(/(\d)(?=(\d{3})+(?!\d))/g, "$1,")
}