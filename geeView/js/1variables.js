/*List global variables in this script for use throughout the viewers*/
var urlParamsObj = {};
var pageUrl = document.URL;
var tinyURL = '';
var urlParams = {};
function setUrl(url){
  var obj = { Title: 'test', Url: url };
  history.pushState(obj, obj.Title, obj.Url);
}
function baseUrl(){
  return window.location.protocol + "//" + window.location.host  + window.location.pathname
}
function eliminateSearchUrl(){
  setUrl(baseUrl())
}
function updatePageUrl(){
  pageUrl = window.location.protocol + "//" + window.location.host  + window.location.pathname + constructUrlSearch();
}
// new Proxy(urlParamsObj, {
//   set: function (target, key, value) {
//       // console.log(`${key} set to ${value}`);
//       //
//       target[key] = value;
//       // console.log(urlParams);
//        // var deepLink = [window.location.pathname,constructUrlSearch()].join('');
//        pageUrl = window.location.protocol + "//" + window.location.host  + window.location.pathname + constructUrlSearch()
//             // console.log(deepLink)
//             // var obj = { Title: 'test', Url: deepLink };
//             // history.pushState(obj, obj.Title, obj.Url);
//             // pageUrl = document.URL;
//             // console.log(pageUrl)
//       return true;
//   }
// }); 
function TweetThis(preURL,postURL,openInNewTab,showMessageBox){
    updatePageUrl();
    if(openInNewTab === undefined || openInNewTab === null){
        openInNewTab = false;
    };
    if(showMessageBox === undefined || showMessageBox === null){
        showMessageBox = true;
    };
    if(preURL === undefined || preURL === null){
        preURL = '';
    };
    if(postURL === undefined || postURL === null){
        postURL = '';
    }

    $.get(
        "https://tinyurl.com/api-create.php",
        {url: pageUrl},
        function(tinyURL){
            var key = tinyURL.split('https://tinyurl.com/')[1];
            var shareURL = pageUrl.split('?')[0] + '?id='+key;
            var fullURL = preURL+shareURL+postURL ;
            // console.log(fullURL);
            ga('send', 'event', mode + '-share', pageUrl, shareURL);
            console.log('shared')
            if(openInNewTab){
               var win = window.open(fullURL, '_blank');
               win.focus(); 
            }else if(showMessageBox){
                var message = `<div class="input-group-prepend" id = 'shareLinkMessageBox'>
                                <button onclick = 'copyText("shareLinkText","copiedMessageBox")'' title = 'Click to copy link to clipboard' class="py-0  fa fa-copy btn input-group-text bg-white"></button>
                                <input type="text" value="${fullURL}" id="shareLinkText" style = "max-width:70%;" class = "form-control mx-1">
                                
                                
                               </div>
                               <div id = 'copiedMessageBox' class = 'pl-4'</div>
                               `
               showMessage('Share link',message); 
               if(mode !== 'geeViz'){
                $('#shareLinkMessageBox').append(staticTemplates.shareButtons);

                }
               

            }
            if(openInNewTab === false){
              setUrl(fullURL);
            }
            
            
        }
    );
}
//Adapted from W3 Schools
function copyText(id,messageBoxId){
     /* Get the text field */
  var copyText = document.getElementById(id);

  /* Select the text field */
  copyText.select();
  copyText.setSelectionRange(0, 99999); /*For mobile devices*/

  /* Copy the text inside the text field */
  document.execCommand("copy");

    /* Alert the copied text */
  if(messageBoxId !== null && messageBoxId !== undefined){
    $('#'+messageBoxId).html("Copied text to clipboard")
  }
 
}
function parseUrlSearch(){
  // console.log(window.location.search == '')
    var urlParamsStr = window.location.search;
      console.log(urlParamsStr)
    if(urlParamsStr !== ''){
      urlParamsStr = urlParamsStr.split('?')[1].split('&');
    
    urlParamsStr.map(function(str){
        urlParams[str.split('=')[0]] = str.split('=')[1]
    })}
    if(urlParams.id !== undefined){
      
      window.open("https://tinyurl.com/"+urlParams.id,"_self");
       if(typeof(Storage) !== "undefined"){
        localStorage.setItem("cachedID",urlParams.id);
      }
    }
    else{
      // TweetThis(null,null,false,false);
      if(typeof(Storage) !== "undefined"){
        var id = localStorage.getItem("cachedID");
        if(id !== null && id !== undefined && id !== 'null'){
          setUrl(baseUrl() + '?id='+id);
          localStorage.setItem("cachedID",null)
        }
        
      }
    }
   
}
function constructUrlSearch(){
  var outURL = '?';
  Object.keys(urlParams).map(function(p){
    outURL += p+'='+urlParams[p] + '&'
  })
  outURL = outURL.slice(0,outURL.length-1)
  return outURL
}
/*Load global variables*/
var cachedSettingskey = 'settings';
var startYear = 1985;
var endYear = 2019;
var startJulian = 153;//190;
var endJulian = 274;//250;
var layerObj = null;
var queryObj = {};var timeLapseObj = {};
var addLCMSTimeLapsesOn;
parseUrlSearch()
var initialCenter = [37.5334105816903,-105.6787109375];
var initialZoomLevel = 5;
var studyAreaSpecificPage = false;
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
                                            	popOver:"Flathead National Forest buffered along with Glacier National Park buffered by 1km",
                                              addFastSlow:true,
                                              addGainThresh:true,
                                              compositeCollection:'projects/USFS/LCMS-NFS/R1/FNF/Composites/Composite-Collection-fmask-allL7',
                                              lcmsCollection:'projects/USFS/LCMS-NFS/R1/FNF/Landcover-Landuse-Change/Landcover-Landuse-Change-Collection-v2019-3',
                                              ltCollection:'projects/USFS/LCMS-NFS/R1/FNF/Base-Learners/LANDTRENDR-Collection-fmask-allL7',
                                              ltFormat:'landtrendr_vertex_format'
                                            },
                                              
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
                                              	  popOver:"Bridger-Teton National Forest boundary buffered by 5km plus Star Valley",
                                                  addFastSlow:true,
                                                  addGainThresh:true,
                                                  compositeCollection:'projects/USFS/LCMS-NFS/R4/Composites/Composite-Collection-fmask-allL7',
                                                  lcmsCollection:'projects/USFS/LCMS-NFS/R4/BT/Landcover-Landuse-Change/Landcover-Landuse-Change-Collection-v2019-3',
                                                  ltCollection:'projects/USFS/LCMS-NFS/R4/Base-Learners/LANDTRENDR-Collection-fmask-allL7',
                                                  ltFormat:'landtrendr_vertex_format'
                                            },
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
                                              	  popOver:"Manti-La Sal National Forest",
                                                  addFastSlow:true,
                                                  addGainThresh:true,
                                                  compositeCollection:'projects/USFS/LCMS-NFS/R4/Composites/Composite-Collection-fmask-allL7',
                                                  lcmsCollection: 'projects/USFS/LCMS-NFS/R4/MLS/Landcover-Landuse-Change/Landcover-Landuse-Change-Collection-v2019-3',
                                                  ltCollection:'projects/USFS/LCMS-NFS/R4/Base-Learners/LANDTRENDR-Collection-fmask-allL7',
                                                  ltFormat:'landtrendr_vertex_format'
                                            },
                  'Chugach National Forest - Kenai Peninsula':{
                                                name:'CNFKP',
                                                center:[60.4,-150.1, 9],
                                                crs:'EPSG:3338',
                                                lossThresh:0.35,
                                                gainThresh:0.45,
                                                startYear:1985,
                                                endYear:2019,
                                            	popOver:"Chugach National Forest - Kenai Peninsula",
                                              addFastSlow:true,
                                              addGainThresh:true,
                                              compositeCollection:'projects/USFS/LCMS-NFS/R10/CK/Composites/Composite-Collection-cloudScoreTDOM2',
                                              lcmsCollection:'projects/USFS/LCMS-NFS/R10/CK/Landcover-Landuse-Change/Landcover-Landuse-Change-Collection',
                                              ltCollection:'projects/USFS/LCMS-NFS/R10/CK/Base-Learners/LANDTRENDR-Collection2019',
                                              ltFormat:'landtrendr_vertex_format',
                                              lcmsSecondaryLandcoverCollection:'projects/USFS/LCMS-NFS/R10/CK/Landcover-Landuse-Change/Landcover_Probability',
                                              lcmsSecondaryLandcoverTreemask:'projects/USFS/LCMS-NFS/R10/CK/Landcover-Landuse-Change/Landcover_Probability_treemask_stack',
                                          
                                              lcmsSecondaryLandcoverDict:{
                                                          1: {'modelName': 'Trees',
                                                                  'legendName': 'Trees',
                                                                  'color': '005e00'},
                                                          2: {'modelName': 'TallShrubs-Trees',
                                                                  'legendName': 'Trees/Tall Shrubs Mix',
                                                                  'color': '008000'},
                                                          3: {'modelName': 'Shrubs-Trees',
                                                                  'legendName': 'Trees/Shrubs Mix',
                                                                  'color': '00cc00'},
                                                          4: {'modelName': 'Grass-Trees',
                                                                  'legendName': 'Trees/Grass Mix',
                                                                  'color': 'b3ff1a'},
                                                          5: {'modelName': 'Barren-Trees',
                                                                  'legendName': 'Trees/Barren Mix',
                                                                  'color': '99ff99'},
                                                          6: {'modelName': 'TallShrubs',
                                                                  'legendName': 'Tall Shrubs',
                                                                  'color': 'b30000'},               
                                                          7: {'modelName': 'Shrubs',
                                                                  'legendName': 'Shrubs',
                                                                  'color': 'e68a00'},//'a33d00'},
                                                          8: {'modelName': 'Grass-Shrubs',
                                                                  'legendName': 'Shrubs/Grass Mix',
                                                                  'color': 'ffad33'},//'e26b00'},
                                                          9: {'modelName': 'Barren-Shrubs',
                                                                  'legendName': 'Shrubs/Barren Mix',
                                                                  'color': 'ffe0b3'},//'f49b00'},               
                                                          10: {'modelName': 'Grass',
                                                                  'legendName': 'Grass',
                                                                  'color': 'FFFF00'},
                                                          11: {'modelName': 'Barren-Grass',
                                                                  'legendName': 'Grass/Barren Mix',
                                                                  'color': 'AA7700'},
                                                          12: {'modelName': 'Barren',
                                                                  'legendName': 'Barren or Impervious',
                                                                  'color': 'd3bf9b'},
                                                          13: {'modelName': 'Snow',
                                                                  'legendName': 'Snow/Ice',
                                                                  'color': 'ffffff'},
                                                          14: {'modelName': 'Water',
                                                                  'legendName': 'Water',
                                                                  'color': '4780f3'}
                                                                },
                                              lcmsSecondaryLandcoverTreeClassMax:6
                                            },
                  'USFS Intermountain Region':{
                                                name:'R4',
                                                center:[40.257866715877526,-114.51403372873794, 6],
                                                crs:'EPSG:26912',
                                                lossThresh:0.35,
                                                lossFastThresh :0.3,
                                                lossSlowThresh  :0.4,
                                                gainThresh:0.4,
                                                startYear:1985,
                                                endYear:2019,
                                              popOver:"US Forest Service Intermountain Region 4",
                                              addFastSlow:true,
                                              addGainThresh:true,
                                              compositeCollection:'projects/USFS/LCMS-NFS/R4/Composites/Composite-Collection-fmask-allL7',
                                              lcmsCollection:'projects/USFS/LCMS-NFS/R4/Landcover-Landuse-Change/R4_all_epwt_annualized',
                                              ltCollection:'projects/USFS/LCMS-NFS/R4/Base-Learners/LANDTRENDR-Collection-fmask-allL7',
                                              ltFormat:'landtrendr_vertex_format',
                                              lcmsSecondaryLandcoverCollection:'projects/USFS/LCMS-NFS/R4/Landcover-Landuse-Change/Landcover_Probability_epwt',
                                              lcmsSecondaryLandcoverTreemask:'projects/USFS/LCMS-NFS/R4/Landcover-Landuse-Change/Landcover_Probability_epwt_treemask_stack',
                                              lcmsSecondaryLandcoverDict:{1: {'modelName': 'Trees',
                                                                                  'legendName': 'Trees',
                                                                                  'color': '005e00'},
                                                                          2: {'modelName': 'Shrubs-Trees',
                                                                                  'legendName': 'Trees/Shrubs Mix',
                                                                                  'color': '008000'},
                                                                          3: {'modelName': 'Grass-Trees',
                                                                                  'legendName': 'Trees/Grass Mix',
                                                                                  'color': 'b3ff1a'},
                                                                          4: {'modelName': 'Barren-Trees',
                                                                                  'legendName': 'Trees/Barren Mix',
                                                                                  'color': '99ff99'},
                                                                          5: {'modelName': 'Shrubs',
                                                                                  'legendName': 'Shrubs',
                                                                                  'color': 'e68a00'},
                                                                          6: {'modelName': 'Grass-Shrubs',
                                                                                  'legendName': 'Shrubs/Grass Mix',
                                                                                  'color': 'ffad33'},
                                                                          7: {'modelName': 'Barren-Shrubs',
                                                                                  'legendName': 'Shrubs/Barren Mix',
                                                                                  'color': 'ffe0b3'},               
                                                                          8: {'modelName': 'Grass',
                                                                                  'legendName': 'Grass',
                                                                                  'color': 'FFFF00'},
                                                                          9: {'modelName': 'Barren-Grass',
                                                                                  'legendName': 'Grass/Barren Mix',
                                                                                  'color': 'AA7700'},
                                                                          10: {'modelName': 'Barren',
                                                                                  'legendName': 'Barren or Impervious',
                                                                                  'color': 'd3bf9b'},
                                                                          11: {'modelName': 'Water',
                                                                                  'legendName': 'Water',
                                                                                  'color': '4780f3'}},
                                              lcmsSecondaryLandcoverTreeClassMax:4
                                            },
                  'Science Team CONUS':{
                                                name:'CONUS',
                                                center:[37.5334105816903,-105.6787109375,5],
                                                crs:'EPSG:5070',
                                                lossThresh:0.30,
                                                gainThresh:0.30,
                                                startYear:1985,
                                                endYear:2019,
                                            	popOver:"2019 LCMS Science Team CONUS-wide loss",
                                              addFastSlow:false,
                                              addGainThresh:false,
                                              compositeCollection:'projects/LCMS/CONUS_MEDOID',
                                              lcmsCollection:'projects/LCMS/CONUS_Products/v20200120',
                                              ltCollection:'projects/LCMS/CONUS_Products/LT20200120'
                                            },
                    'USFS LCMS 1984-2020':{
                      isPilot: false,
                      name:'USFS LCMS 1984-2020',
                      center:[37.5334105816903,-105.6787109375,5],
                      crs:'EPSG:5070',
                      startYear:1985,
                      endYear:2020,

                      conusSA : 'projects/lcms-292214/assets/CONUS-Ancillary-Data/conus',
                      conusComposites:'projects/USFS/LCMS-NFS/CONUS-LCMS/Composites/LCMS-TCC-Composites',
                      conusChange :'projects/lcms-292214/assets/CONUS-LCMS/Landcover-Landuse-Change/DND-RNR-DNDSlow-DNDFast',//'projects/lcms-292214/assets/CONUS-LCMS/Landcover-Landuse-Change/LC-LU-DND-RNR-DNDSlow-DNDFast_InitialRun',
                      conusLC : 'projects/lcms-292214/assets/CONUS-LCMS/Landcover-Landuse-Change/Landcover_Probability',
                      conusLU :   'projects/lcms-292214/assets/CONUS-LCMS/Landcover-Landuse-Change/Landuse_Probability',
                      conusLT : 'projects/lcms-tcc-shared/assets/LandTrendr/LandTrendr-Collection-yesL7-1984-2020',
                      conusCCDC : "projects/CCDC/USA_V2",

                      conusChangeFinal : 'projects/lcms-292214/assets/Final_Outputs/2020-5/CONUS/Change',
                      conusLCFinal : 'projects/lcms-292214/assets/Final_Outputs/2020-5/CONUS/Land_Cover',
                      conusLUFinal :'projects/lcms-292214/assets/Final_Outputs/2020-5/CONUS/Land_Use',


                      conusLossThresh : 0.23,
                      conusFastLossThresh : 0.29,
                      conusSlowLossThresh : 0.18,
                      conusGainThresh : 0.29,

                      hiComposites:'',
                      otherComposites:'',

                      akSA :  'projects/lcms-292214/assets/R10/CoastalAK/TCC_Boundary',//'projects/lcms-292214/assets/R10/CoastalAK/CoastalAK_Simple_StudyArea',
                      akComposites:'projects/USFS/LCMS-NFS/R10/CoastalAK/Composites/Composite-Collection',
                      akChange : 'projects/lcms-292214/assets/R10/CoastalAK/Landcover-Landuse-Change/DND-RNR-DNDSlow-DNDFast-revisedSlowPlots',
                      akLC : 'projects/lcms-292214/assets/R10/CoastalAK/Landcover-Landuse-Change/Landcover_Probability',
                      akLU : 'projects/lcms-292214/assets/R10/CoastalAK/Landcover-Landuse-Change/Landuse_Probability',
                      akLT: 'projects/lcms-292214/assets/R10/CoastalAK/Base-Learners/LANDTRENDR-Collection-1984-2020',
                      akCCDC: 'projects/USFS/LCMS-NFS/R10/CoastalAK/Base-Learners/CCDC-Collection',
                      akChangeFinal :'projects/lcms-292214/assets/Final_Outputs/2020-5/SEAK/Change',
                      akLCFinal : 'projects/lcms-292214/assets/Final_Outputs/2020-5/SEAK/Land_Cover',
                      akLUFinal : 'projects/lcms-292214/assets/Final_Outputs/2020-5/SEAK/Land_Use',
                      akLossThresh : 0.26,
                      akFastLossThresh : 0.34,
                      akSlowLossThresh : 0.17,
                      akGainThresh : 0.24,


                      lcClassDict :{1: {'modelName': 'TREES','legendName': 'Trees','color': '005e00'},
                                  2: {'modelName': 'TS-TREES','legendName': 'Tall Shrubs & Trees Mix','color': '008000'},
                                  3: {'modelName': 'SHRUBS-TRE','legendName': 'Shrubs & Trees Mix','color': '00cc00'},
                                  4: {'modelName': 'GRASS-TREE','legendName': 'Grass/Forb/Herb & Trees Mix','color': 'b3ff1a'},
                                  5: {'modelName': 'BARREN-TRE','legendName': 'Barren & Trees Mix','color': '99ff99'},
                                  6: {'modelName': 'TS','legendName': 'Tall Shrubs','color': 'b30088'},//'b30000'},
                                  7: {'modelName': 'SHRUBS','legendName': 'Shrubs','color': 'e68a00'},
                                  8: {'modelName': 'GRASS-SHRU','legendName': 'Grass/Forb/Herb & Shrubs Mix','color': 'ffad33'},
                                  9: {'modelName': 'BARREN-SHR','legendName': 'Barren & Shrubs Mix','color': 'ffe0b3'},
                                  10: {'modelName': 'GRASS','legendName': 'Grass/Forb/Herb','color': 'ffff00'},
                                  11: {'modelName': 'BARREN-GRA','legendName': 'Barren & Grass/Forb/Herb Mix','color': 'AA7700'},
                                  12: {'modelName': 'BARREN-IMP','legendName': 'Barren or Impervious','color': 'd3bf9b'},
                                  13: {'modelName': 'SNOW','legendName': 'Snow or Ice','color': 'ffffff'},
                                  14: {'modelName': 'WATER','legendName': 'Water','color': '4780f3'}},

                      luClassDict :{1: {'modelName': 'Agriculture','legendName': 'Agriculture','color': 'efff6b'},
                                2: {'modelName': 'Developed','legendName': 'Developed','color': 'ff2ff8'},
                                3: {'modelName': 'Forest','legendName': 'Forest','color': '1b9d0c'},
                                4: {'modelName': 'Non_Forest_Wetland','legendName': 'Non-Forest Wetland','color': '97ffff'},
                                5: {'modelName': 'Other','legendName': 'Other','color': 'a1a1a1'},
                                6: {'modelName': 'Rangeland','legendName': 'Rangeland or Pasture','color': 'c2b34a'}}
                 
                    
                    }                        
                };

////////////////////////////////////////////////////////////////////////////////
/*Initialize parameters for loading study area when none is chosen or chached*/
var defaultStudyArea = 'USFS Intermountain Region';
var studyAreaName = studyAreaDict[defaultStudyArea].name;
var longStudyAreaName = defaultStudyArea;
var cachedStudyAreaName = null;
var viewBeta = 'yes';

var lowerThresholdDecline = studyAreaDict[defaultStudyArea].lossThresh;
var upperThresholdDecline = 1.0;
var lowerThresholdRecovery = studyAreaDict[defaultStudyArea].gainThresh;
var upperThresholdRecovery = 1.0;

var lowerThresholdSlowLoss = studyAreaDict[defaultStudyArea].lossSlowThresh;
var upperThresholdSlowLoss = 1.0;
var lowerThresholdFastLoss = studyAreaDict[defaultStudyArea].lossFastThresh;
var upperThresholdFastLoss = 1.0;
if(lowerThresholdSlowLoss === undefined){lowerThresholdSlowLoss = lowerThresholdDecline}
if(lowerThresholdFastLoss === undefined){lowerThresholdFastLoss = lowerThresholdDecline} 

 
/*Set up some boundaries of different areas to zoom to*/
var clientBoundsDict = {'All':{"geodesic": false,"type": "Polygon","coordinates": [[[-169.215141654273, 71.75307977193499],
        [-169.215141654273, 15.643479915898974],
        [-63.043266654273, 15.643479915898974],
        [-63.043266654273, 71.75307977193499]]]},
                    'CONUS':{"geodesic": false,"type": "Polygon","coordinates": [[[-148.04139715349993,30.214881196707502],[-63.66639715349993,30.214881196707502],[-63.66639715349993,47.18482008797388],[-148.04139715349993,47.18482008797388],[-148.04139715349993,30.214881196707502]]]},
                    'Alaska':{"geodesic": false,"type": "Polygon","coordinates": [[[-168.91542059099993, 71.62680009186087],
        [-168.91542059099993, 52.67867842404269],
        [-129.54042059099993, 52.67867842404269],
        [-129.54042059099993, 71.62680009186087]]]},
                    'CONUS_SEAK':{"type":"Polygon","coordinates":[[[171.00872335506813,59.78242951494817],[171.00872335506813,26.87020622017523],[-53.99127664493189,26.87020622017523],[-53.99127664493189,59.78242951494817],[171.00872335506813,59.78242951494817]]]},
                    'Hawaii':{"geodesic": false,"type": "Polygon","coordinates": [[[-162.7925163471209,18.935659110261664],[-152.2511345111834,18.935659110261664],[-152.2511345111834,22.134763696750557],[-162.7925163471209,22.134763696750557],[-162.7925163471209,18.935659110261664]]]},
                    'Puerto-Rico':{"geodesic": false,"type": "Polygon","coordinates": [[[-67.98169635150003,17.751237971831113],[-65.34635089251566,17.751237971831113],[-65.34635089251566,18.532938160084615],[-67.98169635150003,18.532938160084615],[-67.98169635150003,17.751237971831113]]]},
                    'R4':{
  "geodesic": false,
  "type": "Polygon",
  "coordinates": [
    [
      [
        -120.14785145677105,
        35.00187373433839
      ],
      [
        -108.8802160007048,
        35.00187373433839
      ],
      [
        -108.8802160007048,
        45.70613418897154
      ],
      [
        -120.14785145677105,
        45.70613418897154
      ],
      [
        -120.14785145677105,
        35.00187373433839
      ]
    ]
  ]
}
         }
/*Initialize a bunch of variables*/
var toExport;
var exportArea;
var taskCount = 0;//Keeping track of the number of export tasks each session submitted
var canAddToMap = true;//Set whether addToMap function can add to the map
var canExport = false;//Set whether exports are allowed
var colorRampIndex = 1;
var NEXT_LAYER_ID = 1;var layerChildID = 0;
var layerCount = 0;var refreshNumber = 0;
var uri;var uriName;var csvName;var dataTable;var chartOptions;var infowindow;var queryGeoJSON;var marker;var mtbsSummaryMethod;


var selectedFeaturesJSON = {};
var selectionTracker = {};

var selectionUNID = 1;


var outputURL;
var tableConverter = null;
var groundOverlayOn = false;

var chartIncludeDate = true;var chartCollection;var pixelChartCollections = {};var whichPixelChartCollection;var areaChartCollections = {};var whichAreaChartCollection;var queryClassDict = {};var exportImage;var exportVizParams;var eeBoundsPoly;var shapesMap;
var mouseLat;var mouseLng; var area = 0;var distance = 0;var areaPolygon; var markerList = [];var distancePolylineT;var clickCoords;var distanceUpdater;
var updateArea;var updateDistance;var areaPolygonObj = {};var udpPolygonObj = {};var udpPolygonNumber = 1;var mapHammer;var chartMTBS;var chartMTBSByNLCD;var chartMTBSByAspect;
var walkThroughAdded = false;
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



//Chart color properties
var chartColorI = 0;
var chartColorsDict = {
  'standard':['#050','#0A0','#e6194B','#14d4f4'],
  'advanced':['#050','#0A0','#9A6324','#6f6f6f','#e6194B','#14d4f4'],
  'advancedBeta':['#050','#0A0','#9A6324','#6f6f6f','#e6194B','#14d4f4','#808','#f58231'],
  'coreLossGain':['#050','#0A0','#e6194B','#14d4f4'],
  'allLossGain':['#050','#0A0','#e6194B','#808','#f58231','#14d4f4'],
  'allLossGain2':['#050','#0A0','#0E0','f39268','d54309','00a398'],
  'allLossGain2Area':['f39268','d54309','00a398','ffbe2e'],
  'test':['#9A6324','#6f6f6f','#e6194B','#14d4f4','#880088','#f58231'],
  'testArea':['#e6194B','#14d4f4','#880088','#f58231'],
  'ancillary':['#cc0066','#660033','#9933ff','#330080','#ff3300','#47d147','#00cc99','#ff9966','#b37700']
  }

var chartColors = chartColorsDict.standard;


//Dictionary of zoom level map scales
var zoomDict = {20 : '1,128.49',
                19 : '2,256.99',
                18 : '4,513.98',
                17 : '9,027.97',
                16 : '18,055.95',
                15 : '36,111.91',
                14 : '72,223.82',
                13 : '144,447.64',
                12 : '288,895.28',
                11 : '577,790.57',
                10 : '1,155,581.15',
                9  : '2,311,162.30',
                8  : '4,622,324.61',
                7  : '9,244,649.22',
                6  : '18,489,298.45',
                5  : '36,978,596.91',
                4  : '73,957,193.82',
                3  : '147,914,387.60',
                2  : '295,828,775.30',
                1  : '591,657,550.50'}


var authProxyAPIURL = "https://rcr-ee-proxy-2.herokuapp.com";
// var geeAPIURL = "https://earthengine.googleapis.com/map";
// var geeAPIURL = "https://earthengine.googleapis.com/map";
var geeAPIURL = "https://earthengine.googleapis.com";
// https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/
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
//Taken from: https://stackoverflow.com/questions/196972/convert-string-to-title-case-with-javascript/6475125
String.prototype.toProperCase = function () {
    return this.replace(/\w\S*/g, function(txt){return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();});
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
//Taken from: https://stackoverflow.com/questions/196972/convert-string-to-title-case-with-javascript 
String.prototype.toTitle = function() {
  return this.replace(/(^|\s)\S/g, function(t) { return t.toUpperCase() });
}