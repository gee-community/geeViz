//Wrapper for mapping functions
///////////////////////////////////////////////////////////////////
//Set up some globals
var fc;//Feature collection container for drawing on map and submitting tasks with user-defined vectors
var toExport;
var taskCount = 0;//Keeping track of the number of export tasks each session submitted
var canAddToMap = true;//Set whether addToMap function can add to the map
var canExport = false;//Set whether exports are allowed
var colorRampIndex = 1;
var NEXT_LAYER_ID = 1;var layerChildID = 0;
var layerCount = 0;var refreshNumber = 0;
var uri;var uriName;var csvName;var dataTable;var chartOptions;var infowindow
var outputURL;
var chartType = 'LineChart';//Options LineChart, BarChart, ScatterChart, Histogram, AreaChart, Table
var chartTypes = ['LineChart','Table'];//Options LineChart, BarChart, ScatterChart, Histogram, AreaChart, Table
var tableConverter = null;
var mapDiv = document.getElementById('map');
var groundOverlayOn = false;
tableConverter = function(dataTableT){

  // var x = [dataTableT[0]]
  // x[0][0] = 'Year'
  // dataTableT.slice(1).map(function(i){
    
  //   i[0] = (i[0].getYear()+1900).toString()
  //   x.push(i)
  // })
  // dataTableT   = x
var lcDict = {
  '0': 'No data',
'1': 'Barren',
'2': 'Grass/forb/herb',
'3': 'Impervious',
'4': 'Shrubs',
'5': 'Snow/ice',
'6': 'Trees',
'7': 'Water'
};

var luDict = {
  '0': 'No data',
'1': 'Agriculture',
'2': 'Developed',
'3': 'Forest',
'4': 'Non-forest wetland',
'5': 'Other',
'6': 'Rangeland'
};

var cpDict = {
  '0': 'No Data',
  '1': 'Stable',
  '2':'Growth/recovery',
  '3': 'Fire',
  '4': 'Harvest',
  '5': 'Other'
}

  // if(dataTableT[0].length > 5){
  if(analysisMode === 'advanced'){
    console.log('convertinggggggg tabbbbbbbble' );
    var isFirst = true;
    dataTableT = dataTableT.map(function(i){if(isFirst === false){i[3] = lcDict[parseInt(i[3]*10)]};isFirst = false;return i});
    var isFirst = true;
    dataTableT = dataTableT.map(function(i){if(isFirst === false){i[4] = luDict[parseInt(i[4]*10)]};isFirst = false;return i});
    var isFirst = true;
    // dataTableT = dataTableT.map(function(i){if(isFirst === false){i[5] = cpDict[parseInt(i[5]*10)]};isFirst = false;return i});
//       dataTableT = dataTableT.map(function(i){i[2] = cdlDict[i[2]];return i})
  }
  
// var mtbsDict = {'burnSeverity':'burnSeverity',null:'Unmapped','0':'Unburned','1':'Unburned','2':'Low','3':'Moderate','4':'High','5':'Increased Greenness', '6':'Non-Processing Area Mask'};
//       var cdlDict = {'cdl':'cdl','216': 'Peppers (216)', '217': 'Pomegranates (217)', '214': 'Broccoli (214)', '212': 'Oranges (212)', '213': 'Honeydew Melons (213)', '210': 'Prunes (210)', '211': 'Olives (211)', '218': 'Nectarines (218)', '219': 'Greens (219)', '131': 'Barren (131)', '24': 'Winter Wheat (24)', '25': 'Other Small Grains (25)', '26': 'Dbl Crop WinWht/Soybeans (26)', '27': 'Rye (27)', '21': 'Barley (21)', '22': 'Durum Wheat (22)', '23': 'Spring Wheat (23)', '223': 'Apricots (223)', '28': 'Oats (28)', '29': 'Millet (29)', '0': 'Background (0)', '4': 'Sorghum (4)', '121': 'Developed/Open Space (121)', '122': 'Developed/Low Intensity (122)', '123': 'Developed/Med Intensity (123)', '124': 'Developed/High Intensity (124)', '69': 'Grapes (69)', '59': 'Sod/Grass Seed (59)', '58': 'Clover/Wildflowers (58)', '55': 'Caneberries (55)', '54': 'Tomatoes (54)', '57': 'Herbs (57)', '56': 'Hops (56)', '51': 'Chick Peas (51)', '50': 'Cucumbers (50)', '53': 'Peas (53)', '52': 'Lentils (52)', '195': 'Herbaceous Wetlands (195)', '190': 'Woody Wetlands (190)', '252': ' (252)', '88': 'Nonag/Undefined (88)', '111': 'Open Water (111)', '112': 'Perennial Ice/Snow (112)', '82': 'Developed (82)', '83': 'Water (83)', '81': 'Clouds/No Data (81)', '87': 'Wetlands (87)', '204': 'Pistachios (204)', '206': 'Carrots (206)', '3': 'Rice (3)', '245': 'Celery (245)', '244': 'Cauliflower (244)', '247': 'Turnips (247)', '246': 'Radishes (246)', '241': 'Dbl Crop Corn/Soybeans (241)', '240': 'Dbl Crop Soybeans/Oats (240)', '243': 'Cabbage (243)', '242': 'Blueberries (242)', '249': 'Gourds (249)', '248': 'Eggplants (248)', '39': 'Buckwheat (39)', '38': 'Camelina (38)', '33': 'Safflower (33)', '32': 'Flaxseed (32)', '31': 'Canola (31)', '30': 'Speltz (30)', '37': 'Other Hay/Non Alfalfa (37)', '36': 'Alfalfa (36)', '35': 'Mustard (35)', '34': 'Rape Seed (34)', '60': 'Switchgrass (60)', '61': 'Fallow/Idle Cropland (61)', '63': 'Forest (63)', '64': 'Shrubland (64)', '65': 'Barren (65)', '66': 'Cherries (66)', '67': 'Peaches (67)', '68': 'Apples (68)', '176': 'Grassland/Pasture (176)', '250': 'Cranberries (250)', '251': ' (251)', '253': ' (253)', '254': 'Dbl Crop Barley/Soybeans (254)', '2': 'Cotton (2)', '6': 'Sunflower (6)', '229': 'Pumpkins (229)', '227': 'Lettuce (227)', '226': 'Dbl Crop Oats/Corn (226)', '225': 'Dbl Crop WinWht/Corn (225)', '92': 'Aquaculture (92)', '205': 'Triticale (205)', '222': 'Squash (222)', '221': 'Strawberries (221)', '220': 'Plums (220)', '11': 'Tobacco (11)', '10': 'Peanuts (10)', '13': 'Pop or Orn Corn (13)', '12': 'Sweet Corn (12)', '14': 'Mint (14)', '224': 'Vetch (224)', '152': 'Shrubland (152)', '238': 'Dbl Crop WinWht/Cotton (238)', '239': 'Dbl Crop Soybeans/Cotton (239)', '234': 'Dbl Crop Durum Wht/Sorghum (234)', '235': 'Dbl Crop Barley/Sorghum (235)', '236': 'Dbl Crop WinWht/Sorghum (236)', '237': 'Dbl Crop Barley/Corn (237)', '230': 'Dbl Crop Lettuce/Durum Wht (230)', '231': 'Dbl Crop Lettuce/Cantaloupe (231)', '232': 'Dbl Crop Lettuce/Cotton (232)', '233': 'Dbl Crop Lettuce/Barley (233)', '48': 'Watermelons (48)', '49': 'Onions (49)', '46': 'Sweet Potatoes (46)', '47': 'Misc Vegs &amp; Fruits (47)', '44': 'Other Crops (44)', '45': 'Sugarcane (45)', '42': 'Dry Beans (42)', '43': 'Potatoes (43)', '41': 'Sugarbeets (41)', '1': 'Corn (1)', '5': 'Soybeans (5)', '142': 'Evergreen Forest (142)', '143': 'Mixed Forest (143)', '207': 'Asparagus (207)', '141': 'Deciduous Forest (141)', '209': 'Cantaloupes (209)', '208': 'Garlic (208)', '77': 'Pears (77)', '76': 'Walnuts (76)', '75': 'Almonds (75)', '74': 'Pecans (74)', '72': 'Citrus (72)', '71': 'Other Tree Crops (71)', '70': 'Christmas Trees (70)'}
//       var nlcdDict = {'landcover':'landcover','11': 'Open Water (11)', '24': 'Developed High Intensity (24)', '12': 'Perennial Ice/Snow (12)', '81': 'Pasture/Hay (81)', '21': 'Developed, Open Space (21)', '22': 'Developed, Low Intensity (22)', '23': 'Developed, Medium Intensity  (23)', '51': 'Dwarf Scrub (51)', '31': 'Barren Land (Rock/Sand/Clay)  (31)', '42': 'Evergreen Forest (42)', '43': 'Mixed Forest (43)', '41': 'Deciduous Forest (41)', '74': 'Moss (74)', '73': 'Lichens (73)', '72': 'Sedge/Herbaceous (72)', '71': 'Grassland/Herbaceous (71)', '82': 'Cultivated Crops  (82)', '90': 'Woody Wetlands (90)', '52': 'Shrub/Scrub (52)', '95': 'Emergent Herbaceous Wetlands (95)'}
//       var globCoverDict ={'GlobCover':'GlobCover','150': 'Sparse (>15%) vegetation (woody vegetation, shrubs, grassland)  (150)', '210': 'Water bodies  (210)', '190': 'Artificial surfaces and associated areas (urban areas >50%) GLOBCOVER 2009  (190)', '60': 'Open (15-40%) broadleaved deciduous forest (>5m)  (60)', '130': 'Closed to open (>15%) shrubland (<5m)  (130)', '110': 'Mosaic Forest/Shrubland (50-70%) / Grassland (20-50%) (110)', '230': 'Unclassified (230)', '170': 'Closed (>40%) broadleaved semi-deciduous and/or evergreen forest regularly flooded - Saline water  (170)', '20': 'Mosaic Cropland (50-70%) / Vegetation (grassland, shrubland, forest) (20-50%)  (20)', '40': 'Closed to open (>15%) broadleaved evergreen and/or semi-deciduous forest (>5m)  (40)', '180': 'Closed to open (>15%) vegetation (grassland, shrubland, woody vegetation) on regularly flooded or waterlogged soil - Fresh, brackish or saline water (180)', '200': 'Bare areas  (200)', '140': 'Closed to open (>15%) grassland  (140)', '120': 'Mosaic Grassland (50-70%) / Forest/Shrubland (20-50%) (120)', '70': 'Closed (>40%) needleleaved evergreen forest (>5m)  (70)', '90': 'Open (15-40%) needleleaved deciduous or evergreen forest (>5m) (90)', '100': 'Closed to open (>15%) mixed broadleaved and needleleaved forest (>5m) (100)', '160': 'Closed (>40%) broadleaved forest regularly flooded - Fresh water (160)', '220': 'Permanent snow and ice (220)', '11': 'Post-flooding or irrigated croplands (11)', '14': 'Rainfed croplands (14)', '30': 'Mosaic Vegetation (grassland, shrubland, forest) (50-70%) / Cropland (20-50%)    (30)', '50': 'Closed (>40%) broadleaved deciduous forest (>5m) (50)'}
//       var fiaDict = {'FIA Forest Type':'FIA Frst Type','126': 'Tamarack (126)', '127': 'Northern white-cedar (127)', '224': 'Sugar pine (224)', '161': 'Loblolly pine (161)', '407': 'Slash pine / hardwood (407)', '406': 'Loblolly pine / hardwood (406)', '405': 'Virginia pine / southern red oak (405)', '404': 'Shortleaf pine / oak (404)', '403': 'Longleaf pine / oak (403)', '402': 'Eastern redcedar / hardwood (402)', '342': 'Giant sequoia (342)', '281': 'Lodgepole pine (281)', '932': 'Canyon live oak / interior live oak (932)', '931': 'Coast live oak (931)', '409': 'Other pine / hardwood (409)', '995': 'Other exotic hardwoods (995)', '991': 'Paulownia (991)', '993': 'Eucalyptus (993)', '992': 'Melaluca (992)', '263': 'Noble fir (263)', '121': 'Balsam fir (121)', '122': 'White spruce (122)', '123': 'Red spruce (123)', '267': 'Grand fir (267)', '125': 'Black spruce (125)', '265': 'Engelmann spruce (265)', '264': 'Pacific silver fir (264)', '269': 'Blue spruce (269)', '268': 'Subalpine fir (268)', '911': 'Red alder (911)', '371': 'California mixed conifer (371)', '921': 'Gray pine (921)', '922': 'California black oak (922)', '912': 'Bigleaf maple (912)', '924': 'Blue oak (924)', '925': 'Deciduous oak woodland (925)', '926': 'Evergreen oak woodland (926)', '989': 'Other tropical (989)', '708': 'Red maple / lowland (708)', '709': 'Cottonwood / willow (709)', '704': 'Willow (704)', '705': 'Sycamore / pecan / American elm (705)', '706': 'Sugarberry / hackberry / elm / green ash (706)', '707': 'Silver maple / American elm (707)', '701': 'Black ash / American elm / red maple (701)', '702': 'River birch / sycamore (702)', '703': 'Cottonwood (703)', '270': 'Mountain hemlock (270)', '271': 'Alaska-yellow-cedar (271)', '520': 'Mixed upland hardwoods (520)', '368': 'Misc. western softwoods (368)', '366': 'Limber pine (366)', '367': 'Whitebark pine (367)', '364': 'Monterey pine (364)', '365': 'Foxtail pine / bristlecone pine (365)', '362': 'Southwest white pine (362)', '363': 'Bishop pine (363)', '361': 'Knobcone pine (361)', '301': 'Western hemlock (301)', '304': 'Western redcedar (304)', '305': 'Sitka spruce (305)', '381': 'Scotch pine (381)', '382': 'Australian pine (382)', '383': 'Other exotic softwoods (383)', '384': 'Norway Spruce (384)', '385': 'Introduced larch (385)', '102': 'Red pine (102)', '103': 'Eastern white pine (103)', '101': 'Jack pine (101)', '104': 'Eastern White pine / Eastern hemlock (104)', '105': 'Eastern hemlock (105)', '902': 'Paper birch (902)', '901': 'Aspen (901)', '904': 'Balsam poplar (904)', '519': 'Red maple / oak (519)', '241': 'Western white pine (241)', '511': 'Yellow-poplar (511)', '510': 'Scarlet oak (510)', '513': 'Black locust (513)', '512': 'Black walnut (512)', '515': 'Chestnut oak / black oak / scarlet oak (515)', '514': 'Southern scrub oak (514)', '182': 'Rocky Mountain juniper (182)', '183': 'Western juniper (183)', '181': 'Eastern redcedar (181)', '162': 'Shortleaf pine (162)', '508': 'Sweetgum / yellow-poplar (508)', '185': 'Pinyon juniper woodland (185)', '506': 'Yellow-poplar / white oak / N. red oak (506)', '507': 'Sassafras / persimmon (507)', '504': 'White oak (504)', '505': 'Northern red oak (505)', '502': 'Chestnut oak (502)', '503': 'White oak / red oak / hickory (503)', '341': 'Redwood (341)', '981': 'Sabal palm (981)', '184': 'Juniper woodland (184)', '509': 'Bur oak (509)', '168': 'Spruce pine (168)', '164': 'Sand pine (164)', '165': 'Table-mountain pine (165)', '166': 'Pond pine (166)', '167': 'Pitch pine (167)', '223': 'Jeffrey pine / Coulter pine / bigcone Douglas-fir (223)', '222': 'Incense cedar (222)', '221': 'Ponderosa pine (221)', '163': 'Virginia pine (163)', '401': 'Eastern white pine / N. red oak / white ash (401)', '722': 'Oregon ash (722)', '501': 'Post oak / blackjack oak (501)', '605': 'Overcup oak / water hickory (605)', '607': 'Baldcypress / water tupelo (607)', '606': 'Atlantic white-cedar (606)', '601': 'Swamp chestnut oak / cherrybark oak (601)', '602': 'Sweetgum / Nuttall oak / willow oak (602)', '608': 'Sweetbay / swamp tupelo / red maple (608)', '943': 'Giant chinkapin (943)', '951': 'Pacific madrone (951)', '953': 'Cercocarpus woodland (953)', '952': 'Mesquite Woodland (952)', '955': 'Misc. western hardwood woodlands (955)', '954': 'Intermountain maple woodland (954)', '321': 'Western larch (321)', '201': 'Douglas-fir (201)', '202': 'Port-Orford-cedar (202)', '142': 'Slash pine (142)', '141': 'Longleaf pine (141)', '923': 'Oregon white oak (923)', '802': 'Black cherry (802)', '262': 'Red fir (262)', '982': 'Mangrove (982)', '942': 'Califonia laurel (942)', '261': 'White fir (261)', '941': 'Tanoak (941)', '809': 'Red maple / upland (809)', '803': 'Cherry / ash / yellow-poplar (803)', '124': 'Red spruce / balsam fir (124)', '801': 'Sugar maple / beech / yellow birch (801)', '807': 'Elm / ash / locust (807)', '805': 'Hard maple / basswood (805)', '266': 'Engelmann spruce / subalpine fir (266)'}
//       var idsSeverityDict = {'-1':'Very High','0':'High','1':'Moderate','2':'Low','3':'Low','4':'Very Low','11':'Very Low'};
//       var idsDamDict = {
//           '1':'Defoliation- % Unknown',
//           '2':  'Mortality',
//         '3' :'Crown Discoloration',
//         '4' :'Crown Dieback',
//         '5' :'Topkill',
//         '6' :'Branch Breakage',
//         '7' :'Main stem Broken or Uprooted',
//         '8' :'Branch flagging',
//         '9' :'No damage',
//         '11': 'Mortality - Previously Undocumented',
//         '12': 'Defoliation < 50% of leaves defoliated',
//         '13': 'Defoliation 50-75% of leaves defoliated',
//         '14': 'Defoliation > 75% of leaves defoliated',
//         '15': '15',
//         '16': '16',
//         '17': '17',
//         '18': 'Other Damage (known)',
//         '19': 'Unknown Damage'
//         };
//       var idsDCADict = {
//   '10':'General Insects',
//   '11':'Bark Beetles',
//   '12':'Defoliators',
//   '13': 'Chewing Insects',
//   '14':'Sap Feeding Insects',
//   '15': 'Boring Insects',
//   '16': 'Seed/Cone/Flower/Fruit Insects',
//   '17': 'Gallmaker Insects',
//   '18': 'Insect Predators',
//   '19': 'General Diseases',
//   '20': 'Biotic Damage',
//   '21': 'Root/Butt Diseases',
//   '22': 'Stem Decays/Cankers',
//   '23': 'Parsitic/Epiphytic Plants',
//   '24': 'Decline Complexes/Dieback/Wilts',
//   '25': 'Foliage Diseases',
//   '26': 'Stem Rusts',
//   '27': 'Broom Rusts',
//   '28': 'Terminal, Shoot, and Twig Insects',
//   '29': 'Root Insects',
//   '30': 'Fire',
//   '40': 'Wild Animals',
//   '50': 'Abiotic Damage',
//   '60': 'Competition',
//   '70': 'Human Activities',
//   '80': 'Multi-Damage (Insect/Disease)',
//   '85': 'Plants',
//   '90': 'Other Damages and Symptoms',
//   '99': 'No Damage'
// };
// var idsMortDamDict = idsDamDict;
// idsMortDamDict['mort_damage'] = 'IDS Mort Dam'
// var idsDefolDamDict = idsDamDict;
// idsDefolDamDict['defol_damage'] = 'IDS Defol Dam'

// var idsMortDCADict = idsDCADict;
// idsMortDCADict['mort_dca'] = 'IDS Mort DCA'
// var idsDefolDCADict = idsDCADict;
// idsDefolDCADict['defol_dca'] = 'IDS Defol DCA'

//       dataTableT = dataTableT.map(function(i){i[1] = mtbsDict[i[1]];return i})
//       dataTableT = dataTableT.map(function(i){i[2] = cdlDict[i[2]];return i})
//       dataTableT = dataTableT.map(function(i){i[3] = nlcdDict[i[3]];return i})
//       dataTableT = dataTableT.map(function(i){i[6] = globCoverDict[i[6]];return i})
//       dataTableT = dataTableT.map(function(i){i[7] = fiaDict[i[7]];return i})
//       dataTableT = dataTableT.map(function(i){i[8] = idsDefolDamDict[i[8]];return i})
//       dataTableT = dataTableT.map(function(i){i[9] = idsDefolDCADict[i[9]];return i})
//       dataTableT = dataTableT.map(function(i){i[10] = idsMortDamDict[i[10]];return i})
//       dataTableT = dataTableT.map(function(i){i[11] = idsMortDCADict[i[11]];return i})

      return dataTableT
    };

var chartIncludeDate = true;var chartCollection;var exportImage;var exportVizParams;var eeBoundsPoly;var shapesMap;
var mouseLat;var mouseLng;var distancePolyline; var area = 0;var distance = 0;var areaPolygon; var markerList = [];var distancePolylineT;var clickCoords;var distanceUpdater;
var updateArea;var updateDistance;var areaPolygonObj = {}
///////////////////////////////////////////////////////////////////
//Function to compute range list on client side
function range(start, stop, step){
  start = parseInt(start);
  stop = parseInt(stop);
    if (typeof stop=='undefined'){
        // one param defined
        stop = start;
        start = 0;
    }
    if (typeof step=='undefined'){
        step = 1;
    }
    if ((step>0 && start>=stop) || (step<0 && start<=stop)){
        return [];
    }
    var result = [];
    for (var i=start; step>0 ? i<stop : i>stop; i+=step){
        result.push(i);
    }
    return result;
}

function llToNAD83(x,y){
      var vertex = [x,y];
      var smRadius = 6378136.98;
      var smRange = smRadius * Math.PI * 2.0;
      var smLonToX = smRange / 360.0;
      var smRadiansOverDegrees = Math.PI / 180.0;


      // compute x-map-unit
      vertex[0] *= smLonToX;

      var y = vertex[1];

      // compute y-map-unit
      if (y > 86.0)
      {
      vertex[1] = smRange;
      }
      else if (y < -86.0)
      {
      vertex[1] = -smRange;
      }
      else
      {
      y *= smRadiansOverDegrees;
      y = Math.log(Math.tan(y) + (1.0 / Math.cos(y)), Math.E);
      vertex[1] = y * smRadius; 
      }
      return {'x':vertex[0],'y':vertex[1]}
    }

function CopyAnArray (ari1) {
   var mxx4 = [];
   for (var i=0;i<ari1.length;i++) {
      var nads2 = [];
      for (var j=0;j<ari1[0].length;j++) {
         nads2.push(ari1[i][j]);
      }
      mxx4.push(nads2);
   }
   return mxx4;
}
//Source: http://bcdcspatial.blogspot.com/2012/01/onlineoffline-mapping-map-tiles-and.html
function tileXYZToQuadKey(x, y, z){
        var quadKey = '';
         for(var i = z;i > 0;i--){
             var digit = 0;
              var mask = 1 << (i - 1);
              // print(mask);
              // print(i);
              if((x & mask)  != 0){
                        digit = digit + 1
                      }
              // print((x & mask))
              // print(digit)
              if((y & mask) != 0){
                        digit =digit + 2
                    
                  }
              // print(digit)
              quadKey = quadKey  + digit.toString();
            }
                return quadKey
       }

//Function for centering map
function centerMap(lng,lat,zoom){
    map.setCenter({lat:lat,lng:lng});
    map.setZoom(zoom);
}
function showMessage(title,message){
    $( "#message" ).append( message + '<br>' );
    if(title != null && title != undefined){
      $( "#message-title" ).html( title );
    }
    
    // document.getElementById('messageBox').style.display = 'block';
    $("#messageBox").slideDown();
};

function closeMessage(){
  $("#messageBox").slideUp();
    $( "#message" ).html('');
     $( "#message-title" ).html( '' );
    
    
    // document.getElementById('messageBox').style.display = 'none';
}
/////////////////////////////////////////////////////////////////////////////////////////////
//Function for creating color ramp generally for a map legend
function createColorRamp(styleName, colorList, width,height){
    var myCss = 
        
        "background-image:\
      linear-gradient(\
      to right, ";
     
    for(var i = 0; i< colorList.length;i++){myCss = myCss + '#'+colorList[i].toLowerCase() + ',';}
    myCss = myCss.slice(0,-1) + ");";



return myCss
}
//////////////////////////////////////////////////////
//Wrappers for printing and printing to console
function printImage(message){print(message)};
function print(message){
    console.log(message)
}
/////////////////////////////////////////////////////
function getRandomArbitrary(min, max) {
    return Math.random() * (max - min) + min;
}
    function clearPlots(){
var plotElements = document.getElementById("pt-list");;
                print(plotElements);
                while(plotElements.firstChild){
                    // print('removing')
                    plotElements.removeChild(plotElements.firstChild);
                    }
    plotDictID = 1;
    plotIDList = [];
    plotID =1;
}
var plotDictID = 1;
function addPlotProject(plotProjectName,plotProjectPts){
  
  var projectElement = document.createElement("ee-pt-project");
  projectElement.name = plotProjectName;
  projectElement.plotList = plotProjectPts;
  projectElement.ID = plotProjectID;
  var ptList = document.querySelector("pt-project-list");
  ptList.insertBefore(projectElement,ptList.firstChild);
  plotProjectID++;

}
function addPlot(latLng){
  // plotDict[plotDictID] = false;
 
  var ptElement = document.createElement("ee-pt");
  
  ptElement.name = latLng;
  // print(latLng);
  ptElement.ID = plotDictID;
  // ptElement.isOn = false;
  var ptList = document.querySelector("pt-list");
    ptList.insertBefore(ptElement,ptList.firstChild);
   plotDictID ++;
}
function setPlotColor(ID){
    var plotElements = document.getElementsByTagName("ee-pt");
      
  for(var i = 0;i<plotElements.length;i++){
    plotElements[i].style.outline = 'none';
    
  }
  // console.log(plotElements[0])
  plotElements[plotElements.length-ID].style.outline = '#FFF solid';
   
}
function setPlotProjectColor(ID){
    var plotElements = document.getElementsByTagName("ee-pt-project");
      
  for(var i = 0;i<plotElements.length;i++){
    plotElements[i].style.outline = 'none';
    
  }
  // console.log(plotElements[0])
  plotElements[plotElements.length-ID].style.outline = '#FFF dotted';
   
}
/////////////////////////////////////////////////////
var exportID = 1;
//Taken from: https://stackoverflow.com/questions/2116558/fastest-method-to-replace-all-instances-of-a-character-in-a-string
String.prototype.replaceAll = function(str1, str2, ignore) 
{
    return this.replace(new RegExp(str1.replace(/([\/\,\!\\\^\$\{\}\[\]\(\)\.\*\+\?\|\<\>\-\&])/g,"\\$&"),(ignore?"gi":"g")),(typeof(str2)=="string")?str2.replace(/\$/g,"$$$$"):str2);
} 
/////////////////////////////////////
function addExport(eeImage,name,res,resMin,resMax,resStep,Export,vizParams){
  var exportElement = document.createElement("ee-export");
  
  if(resMin === null || resMin === undefined){
    resMin = 0;
  }
  if(resMax === null || resMax === undefined){
    resMax = 1000;
  }
  if(resStep === null || resStep === undefined){
    resStep = 15;
  }
  if(Export === null || Export === undefined){
    Export = true;
  }
   if(vizParams === null || vizParams === undefined){
    vizParams = {};
  }
  var now = Date().split(' ');
  var nowSuffix = '_'+now[2]+'_'+now[1]+'_'+now[3]+'_'+now[4]

  name = name;//+ nowSuffix
  name = name.replace(/\s+/g,'_')
  name = name.replaceAll('(','_')
  name = name.replaceAll(')','_')
  exportElement.res = res;
  exportElement.name = name;
  exportElement.min = resMin;
  exportElement.max = resMax;
  exportElement.eeImage = eeImage;
  exportElement.step = resStep;
  exportElement.Export = Export;
  exportElement.ID = exportID;
  
  exportImageDict[exportID] = {'eeImage':eeImage,'name':name,'res':res,'shouldExport':Export,'vizParams':vizParams}
  var exportList = document.querySelector("export-list");
    exportList.insertBefore(exportElement,exportList.firstChild);
  exportID ++;
}
/////////////////////////////////////////////////////
//Function to add ee object ot map
function addRasterToMap(item,viz,name,visible,label,fontColor,helpBox,whichLayerList){
    if(whichLayerList === null || whichLayerList === undefined){whichLayerList = "layer-list"}
    // print(item.getInfo().type)
    // if(item.getInfo().type === 'ImageCollection'){print('It is a collection')}
    if(name == null){
        name = "Layer "+NEXT_LAYER_ID;
        NEXT_LAYER_ID += 1;
    }

    if(visible == null){
        visible = true;
    }
    if(helpBox == null){helpBox = ''};
    var layer = document.createElement("ee-layer");
    layer.ID = NEXT_LAYER_ID;
    layer.layerChildID = layerChildID;
    layerChildID++
    layer.name = name ;
    layer.map = map;
    layer.helpBoxMessage = helpBox;
    layer.visible = visible;
    layer.label = label;
    layer.fontColor = fontColor;
    layer.helpBox = helpBox;
    // layer.viz = JSON.stringify(viz);
    // layer.viz  = viz;

    // if(viz.min !== null && viz.min !== undefined){
    //   layer.min = viz.min;
    // }
    // else{layer.min = 0;}
    if(viz != null && viz.bands == null && viz.addToLegend != false){
        var legend = document.createElement("ee-legend");
        legend.name = name;
        legend.helpBoxMessage = helpBox
        if(viz.palette != null){
            var palette = viz.palette;
        } else{var palette = '000,FFF';}
        var paletteList = palette.split(',');
        if(paletteList.length == 1){paletteList = [paletteList[0],paletteList[0]];}
        var colorRamp = createColorRamp('colorRamp'+colorRampIndex.toString(),paletteList,180,20);
        
        legend.colorRamp = colorRamp;


        if(label != null && viz.min != null){
            legend.min = viz.min + ' ' +label;
        } else if(label != null && viz.min == null){
            legend.min = minLabel;
        } else if(label == null && viz.min != null){
            legend.min = viz.min;
        } 

        if(label != null && viz.max != null){
            legend.max = viz.max + ' ' +label;
        } else if(label != null && viz.max == null){
            legend.max = maxLabel;
        } else if(label == null && viz.max != null){
            legend.max = viz.max;
        } 
        if(legend.min ==null){legend.min = 'min'};
        if(legend.max ==null){legend.max = 'max'};
    
    if(fontColor != null){legend.fontColor = "color:#" +fontColor + ";" }
        else{legend.fontColor    = "color:#808080;"}
    
    var legendList = document.querySelector("legend-list");
    legendList.insertBefore(legend,legendList.firstChild);
    }
    
   
    layer.visible = visible;
    layer.item = item;
    layer.name = name;
    
    var layerList = document.querySelector(whichLayerList);
    
    
    layerList.insertBefore(layer,layerList.firstChild);
    layerCount ++;
    item.getMap(viz,function(eeLayer){
        layer.setLayer(eeLayer);
    });
}

function addIDTokenToMap(mapid,token,viz,name,visible,label,fontColor,helpBox,whichLayerList){
    if(whichLayerList === null || whichLayerList === undefined){whichLayerList = "layer-list"}
    // print(item.getInfo().type)
    // if(item.getInfo().type === 'ImageCollection'){print('It is a collection')}
    if(name == null){
        name = "Layer "+NEXT_LAYER_ID;
        NEXT_LAYER_ID += 1;
    }
    
    if(visible == null){
        visible = true;
    }
    if(helpBox == null){helpBox = ''};
    var layer = document.createElement("ee-layer");
    layer.ID = NEXT_LAYER_ID;
    layer.layerChildID = layerChildID;
    layerChildID++
    layer.name = name ;
    layer.map = map;
    layer.helpBoxMessage = helpBox;
    layer.visible = visible;
    layer.label = label;
    layer.fontColor = fontColor;
    layer.helpBox = helpBox;
    // layer.viz = JSON.stringify(viz);
    // layer.viz  = viz;

    // if(viz.min !== null && viz.min !== undefined){
    //   layer.min = viz.min;
    // }
    // else{layer.min = 0;}
    if(viz != null && viz.bands == null && viz.addToLegend != false){
        var legend = document.createElement("ee-legend");
        legend.name = name;
        legend.helpBoxMessage = helpBox
        if(viz.palette != null){
            var palette = viz.palette;
        } else{var palette = '000,FFF';}
        var paletteList = palette.split(',');
        if(paletteList.length == 1){paletteList = [paletteList[0],paletteList[0]];}
        var colorRamp = createColorRamp('colorRamp'+colorRampIndex.toString(),paletteList,180,20);
        
        legend.colorRamp = colorRamp;


        if(label != null && viz.min != null){
            legend.min = viz.min + ' ' +label;
        } else if(label != null && viz.min == null){
            legend.min = minLabel;
        } else if(label == null && viz.min != null){
            legend.min = viz.min;
        } 

        if(label != null && viz.max != null){
            legend.max = viz.max + ' ' +label;
        } else if(label != null && viz.max == null){
            legend.max = maxLabel;
        } else if(label == null && viz.max != null){
            legend.max = viz.max;
        } 
        if(legend.min ==null){legend.min = 'min'};
        if(legend.max ==null){legend.max = 'max'};
    
    if(fontColor != null){legend.fontColor = "color:#" +fontColor + ";" }
        else{legend.fontColor    = "color:#808080;"}
    
    var legendList = document.querySelector("legend-list");
    legendList.insertBefore(legend,legendList.firstChild);
    }
    
   
    layer.visible = visible;
    layer.mapid = mapid;
    layer.token = token;
    
    layer.name = name;
    
    var layerList = document.querySelector(whichLayerList);
    
    
    layerList.insertBefore(layer,layerList.firstChild);
    layerCount ++;
    layer.setLayer(layer);
    
}
//////////////////////////////////////////////////////
function standardTileURLFunction(url,xThenY){
              if(xThenY === null || xThenY === undefined  ){xThenY  = false;}
              return function(coord, zoom) {
                    // "Wrap" x (logitude) at 180th meridian properly
                    // NB: Don't touch coord.x because coord param is by reference, and changing its x property breakes something in Google's lib 
                    var tilesPerGlobe = 1 << zoom;
                    var x = coord.x % tilesPerGlobe;
                    if (x < 0) {
                        x = tilesPerGlobe+x;
                    }
                    // Wrap y (latitude) in a like manner if you want to enable vertical infinite scroll
                    // return "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/256/" + zoom + "/" + x + "/" + coord.y + "?access_token=pk.eyJ1IjoiaWhvdXNtYW4iLCJhIjoiY2ltcXQ0cnljMDBwNHZsbTQwYXRtb3FhYiJ9.Sql6G9QR_TQ-OaT5wT6f5Q"
                    if(xThenY ){
                        return url+ zoom + "/" + x + "/" + coord.y +".png?";
                    }
                    else{return url+ zoom + "/" + coord.y + "/" +x  +".png?";}//+ (new Date()).getTime();
                    
                }
            }
/////////////////////////////////////////////////////
//Function to add ee object ot map
function addRESTToMap(tileURLFunction,name,visible,maxZoom,helpBox,whichLayerList){
  var viz = {};var item = ee.Image();
  if(whichLayerList === null || whichLayerList === undefined){whichLayerList = "layer-list"}
    // print(item.getInfo().type)
    // if(item.getInfo().type === 'ImageCollection'){print('It is a collection')}
    if(name === null || name === undefined){
        name = "Layer "+NEXT_LAYER_ID;
        NEXT_LAYER_ID += 1;
    }

    if(visible === null || visible === undefined){
        visible = true;
    }
    if(maxZoom === null || maxZoom === undefined){
        maxZoom = 18;
    }
    if(helpBox == null){helpBox = ''};
    var layer = document.createElement("REST-layer");
    layer.tileURLFunction = tileURLFunction;
    layer.ID = NEXT_LAYER_ID;
    layer.layerChildID = layerChildID;
    layerChildID++
    layer.name = name ;
    layer.map = map;
    layer.helpBoxMessage = helpBox;
    layer.visible = visible;
    // layer.label = label;
    // layer.fontColor = fontColor;
    layer.helpBox = helpBox;
      layer.maxZoom = maxZoom;
   
    layer.visible = visible;
    layer.item = item;
    layer.name = name;
    
    var layerList = document.querySelector(whichLayerList);
    
    
    layerList.insertBefore(layer,layerList.firstChild);
    layerCount ++;
    item.getMap(viz,function(eeLayer){
        layer.setLayer(eeLayer);
    });
}
//////////////////////////////////////////////////////
function point2LatLng(x,y) {
  
  var topRight = map.getProjection().fromLatLngToPoint(map.getBounds().getNorthEast());
  var bottomLeft = map.getProjection().fromLatLngToPoint(map.getBounds().getSouthWest());
  var scale = Math.pow(2, map.getZoom());
  var worldPoint = new google.maps.Point(x / scale + bottomLeft.x, y / scale + topRight.y);
  var out = map.getProjection().fromPointToLatLng(worldPoint);
  return out;
}
//////////////////////////////////////////////////////
function getGroundOverlay(baseUrl,minZoom){
  if(map.getZoom()>=minZoom){

  var mapHeight = $('#map').height();
  var mapWidth = $('#map').width();

  var bounds = map.getBounds();

  var ulxy = [bounds.fa.j,bounds.ma.j];
  var lrxy = [bounds.fa.l,bounds.ma.l];
  var ulxyMercator = llToNAD83(ulxy[0],ulxy[1]);
  var lrxyMercator = llToNAD83(lrxy[0],lrxy[1]);
  
  
  var url = baseUrl+
  
  ulxyMercator.x.toString()+'%2C'+lrxyMercator.y.toString()+
  '%2C'+
  
  
  lrxyMercator.x.toString()+'%2C'+ulxyMercator.y.toString()+
  '&bboxSR=3857&imageSR=3857&size='+mapWidth.toString()+'%2C'+mapHeight.toString()+'&f=image'

  // console.log('url '+url)
  overlay = new google.maps.GroundOverlay(url,bounds);
  return overlay
}
else{
  url = '../images/blank.png';
  overlay = new google.maps.GroundOverlay(url,map.getBounds())
  return overlay
}
}
//////////////////////////////////////////////////////
/////////////////////////////////////////////////////
//Function to add dynamic object mapping service to map
function addDynamicToMap(baseUrl1,baseUrl2, minZoom1,minZoom2,name,visible,helpBox,whichLayerList){
  if(whichLayerList === null || whichLayerList === undefined){whichLayerList = "layer-list"}
var viz = {};var item = ee.Image();
    // print(item.getInfo().type)
    // if(item.getInfo().type === 'ImageCollection'){print('It is a collection')}
    if(name === null || name === undefined){
        name = "Layer "+NEXT_LAYER_ID;
        NEXT_LAYER_ID += 1;
    }

    if(visible === null || visible === undefined){
        visible = true;
    }
    // if(minZoom === null || minZoom === undefined){
    //     minZoom = 8;
    // }
    if(helpBox == null){helpBox = ''};
    function groundOverlayWrapper(){
      if(map.getZoom() > minZoom2){
        return getGroundOverlay(baseUrl2,minZoom2)
      }
      else{
        return getGroundOverlay(baseUrl1,minZoom1)
      }
      }
    var layer = document.createElement("dynamic-layer");
    
    layer.ID = NEXT_LAYER_ID;
    layer.layerChildID = layerChildID;
    layerChildID++
    layer.name = name ;
    layer.map = map;
    layer.helpBoxMessage = helpBox;
    layer.visible = visible;
    layer.groundOverlayFunction = groundOverlayWrapper;
    layer.helpBox = helpBox;
     
   // layer.baseUrl = baseUrl;
    layer.visible = visible;
    layer.item = item;
    layer.name = name;
    
    var layerList = document.querySelector(whichLayerList);
    
    
    layerList.insertBefore(layer,layerList.firstChild);
    layerCount ++;
    layer.startUp();
   
}
//////////////////////////////////////////////////////
//Function for adding ee object to map
//Will handle vectors by converting them to rasters
function addToMap(item,viz,name,visible,label,fontColor,helpBox,whichLayerList){
    if(canAddToMap){
    try{var t = item.bandNames();
        
        addRasterToMap(item,viz,name,visible,label,fontColor,helpBox,whichLayerList);}
    catch(err){
        try{
        item = ee.Image().paint(item,3,3);
        addToMap(item,viz,name,visible,label,fontColor,helpBox,whichLayerList)
      }
    catch(err){
      item = ee.Image().paint(ee.FeatureCollection([item]),3,3);
        addToMap(item,viz,name,visible,label,fontColor,helpBox,whichLayerList)
    }
    };
}
    
}
function mp(){
  this.addLayer = function(item,viz,name,visible,label,fontColor,helpBox,whichLayerList){
    addToMap(item,viz,name,visible,label,fontColor,helpBox,whichLayerList);
  };
  this.addREST = function(tileURLFunction,name,visible,maxZoom,helpBox,whichLayerList){
    addRESTToMap(tileURLFunction,name,visible,maxZoom,helpBox,whichLayerList);
  };
  this.addExport = function(eeImage,name,res,resMin,resMax,resStep,Export,vizParams){
    addExport(eeImage,name,res,resMin,resMax,resStep,Export,vizParams);
  };
  this.addPlot = function(nameLngLat){
    addPlot(nameLngLat);

  }
}
var Map2 = new mp();

function sleep(delay) {
        var start = new Date().getTime();
        while (new Date().getTime() < start + delay);
      }
function stringToBoolean(string){
    switch(string.toLowerCase().trim()){
        case "true": case "yes": case "1": return true;
        case "false": case "no": case "0": case null: return false;
        default: return Boolean(string);
    }
}
// function refreshLayerToMap()
function reRun(){
  layerChildID = 0;
	var layers = document.getElementById("layers");
  var referenceLayers = document.getElementById("reference-layers");
  var exportLayers = document.getElementById("export-layers");
    console.log('layers');
    console.log(layers);
    // console.log(layers.firstChild);
    var legend = document.getElementById("legend");
    var exports = document.getElementById("export-list");
    var overlayIndex = 0;
	while(layers.firstChild){
        
		layers.removeChild(layers.firstChild);
        // var thisOverlay = map.overlayMapTypes.b[overlayIndex];
        
        // console.log(layerCount);
        // setInterval(function(){if(map.overlayMapTypes.b.length >= layerCount){
        //     console.log('waiting')
        // }
        // console.log(map.overlayMapTypes.b.length)
        // this.map.overlayMapTypes.removeAt(foundIndex);
        // console.log(thisOverlay)
        overlayIndex++

	}
  // while(exportLayers.firstChild){
        
  //   exportLayers.removeChild(exportLayers.firstChild);
  //       // var thisOverlay = map.overlayMapTypes.b[overlayIndex];
        
  //       // console.log(layerCount);
  //       // setInterval(function(){if(map.overlayMapTypes.b.length >= layerCount){
  //       //     console.log('waiting')
  //       // }
  //       // console.log(map.overlayMapTypes.b.length)
  //       // this.map.overlayMapTypes.removeAt(foundIndex);
  //       // console.log(thisOverlay)
  //       // overlayIndex++

  // }
  while(referenceLayers.firstChild){
        
    referenceLayers.removeChild(referenceLayers.firstChild);
        // var thisOverlay = map.overlayMapTypes.b[overlayIndex];
        
        // console.log(layerCount);
        // setInterval(function(){if(map.overlayMapTypes.b.length >= layerCount){
        //     console.log('waiting')
        // }
        // console.log(map.overlayMapTypes.b.length)
        // this.map.overlayMapTypes.removeAt(foundIndex);
        // console.log(thisOverlay)
        // overlayIndex++

  }
  while(exports.firstChild){
        
    exports.removeChild(exports.firstChild);

  }
    console.log(layerCount);
    console.log(refreshNumber);
    while(legend.firstChild){
        legend.removeChild(legend.firstChild);
    }
    refreshNumber   ++;layerCount = 0;
  exportImageDict = {};
	run();


//     var whileCount = 0;
//     while(whileCount < 5000){
    // while(map.overlayMapTypes.b.length < layerCount*(refreshNumber+1)){}
    interval2(function(){
      map.overlayMapTypes.j.slice(0,map.overlayMapTypes.j.length-layerCount).forEach(function(element,index){
                    
                    if(element !== undefined && element !== null){
                        console.log('removing');
                    console.log(index);
                    map.overlayMapTypes.setAt(index,null);
                };
                    
                });  
  },2000,20)
    
//     whileCount++;
// }
    // processFeatures(fc);
   
}
var metricOrImperial = 'metric';
var unitMultiplierDict = {imperial:
{area:[10.7639,0.000247105],distance:[3.28084,0.000621371]},
metric:
{area:[1,0.0001],distance:[1,0.001]}};

var unitNameDict = {imperial:
{area:['ft<sup>2</sup>','acres'],distance:['ft','miles']},
metric:
{area:['m<sup>2</sup>','hectares'],distance:['m','km']}};

function toggleUnits(){
  if(metricOrImperial === 'metric'){metricOrImperial = 'imperial'}
    else{metricOrImperial = 'metric'};
}
function toggleAreaUnits(v){
  console.log(v);
  toggleUnits();
  updateArea();
  
}
function toggleDistanceAreaUnits(value){
  // console.log(value);
  toggleUnits();
  if(value === 'a'){updateArea();}
  else{updateDistance();}
  
  
}
function getRandomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}
function padLeft(nr, n, str){
    return Array(n-String(nr).length+1).join(str||'0')+nr;
}
function rgbToHex(r,g,b) {
    return "#"+("00000"+(r<<16|g<<8|b).toString(16)).slice(-6);
}
function randomColor(){
  var r = getRandomInt(100, 255);
  var g = getRandomInt(100, 255);
  var b = getRandomInt(100, 255);
  var c = rgbToHex(r,g,b)
  return c
}
function randomColors(n){
  var out = [];
  while(n>0){
    out.push(randomColor());
    n = n-1;
  }
  return out
}

var polyNumber = 1;
var polyOn = false;

var colorList = randomColors(50);
var colorMod = colorList.length;
var currentColor =  colorList[colorMod%colorList.length];
colorMod++;
var areaPolygonOptions = {
              strokeColor:currentColor,
                fillOpacity:0.2,
              strokeOpacity: 1,
              strokeWeight: 3,
              draggable: true,
              editable: true,
              geodesic:true,
              polyNumber: polyNumber
            
            };
function startArea(){
  if(polyOn === false){
    $( "#distance-area-measurement" ).html( 'Click on map to start measuring<br>Press "Delete" or "d" button to clear<br>Press "u" to undo last vertex placement<br>Press "None" radio button to stop measuring');
    polyOn = true;
  }
  // 
   // $( "#distance-area-measurement" ).style.width = '0px';
  document.getElementById('distance-area-measurement').style.display = 'block';
  document.getElementById('distance-area-measurement').value = 'a';
  currentColor =  colorList[colorMod%colorList.length];
    areaPolygonOptions = {
              strokeColor:currentColor,
                fillOpacity:0.2,
              strokeOpacity: 1,
              strokeWeight: 3,
              draggable: true,
              editable: true,
              geodesic:true,
              polyNumber: polyNumber
            };
        
        colorMod++;
    map.setOptions({draggableCursor:'crosshair'});
    map.setOptions({disableDoubleClickZoom: true });

    // Construct the polygon.
        areaPolygonObj[polyNumber] = new google.maps.Polyline(areaPolygonOptions);
        areaPolygonObj[polyNumber].setMap(map);

        // areaPolygon = new google.maps.Polygon(areaPolygonOptions);
        // areaPolygon.setMap(map);

    updateArea = function(){
      var unitName;var unitMultiplier;
        var keys = Object.keys(areaPolygonObj);
        var totalArea = 0;
        var totalWithArea = 0;
        var outString = ''
        function areaWrapper(key){
        // print('Adding in: '+key.toString());
        var pathT = areaPolygonObj[key].getPath().j
        clickCoords = pathT[pathT.length-1]
        area = google.maps.geometry.spherical.computeArea(areaPolygonObj[key].getPath());
        
        var unitNames = unitNameDict[metricOrImperial].area;
        var unitMultipliers = unitMultiplierDict[metricOrImperial].area;
        // console.log(unitNames);
        // console.log(unitMultipliers);
        // console.log(area)
        
        if(totalArea >= 1){
          unitName = unitNames[1];
          unitMultiplier = unitMultipliers[1];
        }
        else{
          unitName = unitNames[0];
          unitMultiplier = unitMultipliers[0];
          }
        if(area >= 1){
          var unitNameT = unitNames[1];
          var unitMultiplierT = unitMultipliers[1];
        }
        else{
          var unitNameT = unitNames[0];
          var unitMultiplierT = unitMultipliers[0];
          };
        area = area;//*unitMultiplier
        // console.log(unitName);
        // console.log(unitMultiplier);
        if(area>0){
          totalWithArea++;
          outString  = outString + area*unitMultiplierT.toFixed(4).toString() + ' ' + unitNameT + '<br>'
        }
        totalArea = totalArea + area

        // console.log(totalArea);
      }
      keys.map(areaWrapper)
      var pixelProp = totalArea/9;
      totalArea = totalArea*unitMultiplier;
        // if(infowindow != undefined){infowindow.close()}
        // if(totalArea > 0){
            // infowindow = new google.maps.InfoWindow({
            // content: area.toFixed(2) + unit,
            // position: clickCoords
            // });
            // infowindow.open(map);
             totalArea = totalArea.toFixed(4).toString();

          var polyString = 'polygon';
          if(keys.length>1){
            polyString = 'polygons';
          }
          $( "#distance-area-measurement" ).html(totalWithArea.toString()+' '+polyString+' <br>'+totalArea +' '+unitName );//+' <br>' +pixelProp.toFixed(2) + '%pixel');
    
      
            // }       
    }
    // function newPoly(){
    //   areaPolygonObj[polyNumber].setMap(null);
    //   areaPolygonObj[polyNumber] = new google.maps.Polygon(areaPolygonOptions);
    //   areaPolygonObj[polyNumber].setMap(map);
    //   google.maps.event.addListener(areaPolygon, 'dblclick', function() {
    //     console.log('doubleClicked');
    //     newPoly();
    //     // resetPolygon();
    // });
    // }
  startListening();
}
function setToPolygon(id){
        if(id == undefined || id == null){id = polyNumber};
        console.log('Setting '+id.toString()+' to polygon');
        areaPolygonOptions.strokeColor = areaPolygonObj[id].strokeColor;
        var path = areaPolygonObj[id].getPath();
        areaPolygonObj[id].setMap(null);
        areaPolygonObj[id] = new google.maps.Polygon(areaPolygonOptions);
        areaPolygonObj[id].setPath(path);
        areaPolygonObj[id].setMap(map);
}
function setToPolyline(id){
        if(id == undefined || id == null){id = polyNumber};
        areaPolygonOptions.strokeColor = areaPolygonObj[id].strokeColor;
        var path = areaPolygonObj[polyNumber].getPath();
        areaPolygonObj[id].setMap(null);
        areaPolygonObj[id] = new google.maps.Polyline(areaPolygonOptions);
        areaPolygonObj[id].setPath(path);
        areaPolygonObj[id].setMap(map);
}


function startListening(){
    // google.maps.event.addDomListener(map, 'click', function(event) {
    //     // console.log(event)
    //     // var path = areaPolygonObj[polyNumber].getPath();
    //     // path.push(event.latLng);
    //     // updateArea();
    //     console.log(event.latLng)
   
    
    // });
    google.maps.event.addDomListener(mapDiv, 'click', function(event) {
        
        

        var path = areaPolygonObj[polyNumber].getPath();
        var x =event.clientX;
        var y = event.clientY;
        clickLngLat =point2LatLng(x,y)
        path.push(clickLngLat);
        updateArea();
    
    });
    google.maps.event.addDomListener(mapDiv, 'dblclick', function() {
        // console.log('doubleClicked');
        // newPoly();
        // startArea();
        
   
        
        setToPolygon()
        
        resetPolygon();

    });


    // var thisPoly = areaPolygonObj[polyNumber]
    // if(thisPoly.getPath().length > 2){
      // google.maps.event.addListener(thisPoly, "click", function(){activatePoly(thisPoly)});
    // }
    google.maps.event.addListener(areaPolygonObj[polyNumber], "click", updateArea);
 
    google.maps.event.addListener(areaPolygonObj[polyNumber], "mouseup", updateArea);
    google.maps.event.addListener(areaPolygonObj[polyNumber], "dragend", updateArea);
    google.maps.event.addListener(areaPolygonObj[polyNumber].getPath(), 'set_at',  updateArea);

    window.addEventListener("keydown", resetPolys);
    window.addEventListener("keydown", deleteLastVertex);

}
function resetPolys(e){
 
     
      if( e.key == 'Delete'|| e.key == 'd' ){
        stopArea();
        startArea();
      }
    }
function deleteLastVertex(e){
 
      
      if(e.key == 'u' || e.key == 'z' ){
        if(areaPolygonObj[polyNumber].getPath().length >0){
          areaPolygonObj[polyNumber].getPath().pop(1);
          updateArea();
        }

        else if(polyNumber > 1){
          stopListening();
          polyNumber = polyNumber -1;
          setToPolyline()
          startListening();
        }
        
      }
    }
function activatePoly(poly){
  // stopListening();
  // var keys = Object.keys(areaPolygonObj);
  // keys.map(function(k){
  //   setToPolygon(k)
  //   areaPolygonObj[k].setEditable(false);
  //   areaPolygonObj[k].setDraggable(false);
    

  // })
  // polyNumber = poly.polyNumber;
  // areaPolygonObj[poly.polyNumber].setEditable(true);
  // areaPolygonObj[poly.polyNumber].setDraggable(true);
  // setToPolyline()
  // startListening();
 
 
  
  console.log(poly.polyNumber)
}
function stopListening(){
    // areaPolygonObj[polyNumber].setEditable(false);
    // areaPolygonObj[polyNumber].setDraggable(false);
    console.log(areaPolygonObj[polyNumber].polyNumber);
    google.maps.event.clearListeners(areaPolygonObj[polyNumber], 'dblclick');
    google.maps.event.clearListeners(areaPolygonObj[polyNumber], 'click');
    google.maps.event.clearListeners(mapDiv, 'click');
    google.maps.event.clearListeners(areaPolygonObj[polyNumber], 'mouseup');
    google.maps.event.clearListeners(areaPolygonObj[polyNumber], 'dragend');
    if(infowindow != undefined){infowindow.close()}
    window.removeEventListener('keydown',resetPolys);
    window.removeEventListener('keydown',deleteLastVertex);
    // var thisPoly = areaPolygonObj[polyNumber]
    // if(thisPoly.getPath().length > 2){
    //   google.maps.event.addListener(thisPoly, "click", function(){activatePoly(thisPoly)});
    // }
    
}
function clearPoly(id){

  areaPolygonObj[id].setMap(null);
  areaPolygonObj[id].setPath([]);
  updateArea();
  google.maps.event.clearListeners(areaPolygonObj[id], 'click');
}
function clearPolys(){
  stopListening();
  var keys = Object.keys(areaPolygonObj);
  keys.map(function(k){areaPolygonObj[k].setMap(null);})
  areaPolygonObj = {};
  polyNumber = 1;
  polyOn = false;

}
function stopArea(){
  
  $( "#distance-area-measurement" ).html( '');
  document.getElementById('distance-area-measurement').style.display = 'none';
  map.setOptions({disableDoubleClickZoom: true });
  
  clearPolys();
   
  // map.setOptions({draggableCursor:'hand'});
  
}

function resetPolygon(){
    stopListening();
    var keys = Object.keys(areaPolygonObj);
    var lastKey = keys[keys.length-1];
    console.log('last key '+lastKey.toString());
    polyNumber = parseInt(lastKey);
    polyNumber++;
    startArea();
    console.log(areaPolygonObj)
}
function newPolygon(){
  stopArea();

}
///////////////////////////////////////////////////////////////////////////////////
function startDistance(){
  $( "#distance-area-measurement" ).html( 'Click on map to start measuring<br>Double click to finish measurement');
  document.getElementById('distance-area-measurement').style.display = 'inline-block';
  document.getElementById('distance-area-measurement').value = 'd';
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
    map.setOptions({draggableCursor:'crosshair'});
    distancePolyline = new google.maps.Polyline(distancePolylineOptions);
    distancePolyline.setMap(map);


    google.maps.event.addDomListener(mapDiv, 'click', function(event) {
        console.log('clicked');
        
        

        
    
   
        var path = distancePolyline.getPath();
        var x =event.clientX;
        var y = event.clientY;
        clickLngLat =point2LatLng(x,y)
        path.push(clickLngLat);
        updateDistance();
 
   
    
    });
    // google.maps.event.addDomListener(distancePolyline, 'dblclick', function() {
    //     console.log('doubleClicked')
    //     resetPolyline();
    
    // });

    map.setOptions({disableDoubleClickZoom: true });



    google.maps.event.addListener(distancePolyline, "click", updateDistance);
    google.maps.event.addDomListener(mapDiv, "dblclick", resetPolyline);
    google.maps.event.addListener(distancePolyline, "mouseup", updateDistance);
    google.maps.event.addListener(distancePolyline, "dragend", updateDistance);
    google.maps.event.addListener(distancePolyline.getPath(), 'set_at',  updateDistance);

    // distanceUpdater = setInterval(function(){updateMarkerPositionList();updateDistance();},500);

    }

function stopDistance(){
  $( "#distance-area-measurement" ).html( '');
  document.getElementById('distance-area-measurement').style.display = 'none';
    map.setOptions({disableDoubleClickZoom: true });
    google.maps.event.clearListeners(mapDiv, 'dblclick');
    google.maps.event.clearListeners(distancePolyline, 'click');
    google.maps.event.clearListeners(mapDiv, 'click');
    google.maps.event.clearListeners(distancePolyline, 'mouseup');
    google.maps.event.clearListeners(distancePolyline, 'dragend');
    if(infowindow != undefined){infowindow.close()}
    distancePolyline.setMap(null);
    // clearInterval(distanceUpdater);
    map.setOptions({draggableCursor:'hand'});
}

function resetPolyline(){
    stopDistance();startDistance();
}
    
// function updateMarkerPositionList(){
//     var distance = google.maps.geometry.spherical.computeLength(distancePolyline.getPath());
//     console.log(distance);
//     var pathT = distancePolyline.getPath().b
//     markerPositionList = pathT.map(function(xy){return [xy.lat(),xy.lng()]})
//     clickCoords = distancePolyline.getPath().b[pathT.length-1]
// }
updateDistance = function(){
    distance = google.maps.geometry.spherical.computeLength(distancePolyline.getPath());
    var pathT = distancePolyline.getPath().j
    clickCoords = pathT[pathT.length-1]
    
    var unitNames = unitNameDict[metricOrImperial].distance;
    var unitMultipliers = unitMultiplierDict[metricOrImperial].distance;
    // console.log(unitNames);
    // console.log(unitMultipliers);
    // console.log(area)
        
    if(distance >= 10000){
      var unitName = unitNames[1];
      var unitMultiplier = unitMultipliers[1];
    }
    else{
      var unitName = unitNames[0];
      var unitMultiplier = unitMultipliers[0];
      }
    distance = distance*unitMultiplier
    // console.log(unitName);
    // console.log(unitMultiplier);

    if(distance > 0){
     

          $( "#distance-area-measurement" ).html(distance.toFixed(4) + ' ' + unitName );
    




    }

}
function getDistance(lat1,lon1,lat2,lon2){
    var R = 6371e3; // metres
    var phi1 = lat1* Math.PI / 180;
    var phi2 = lat2* Math.PI / 180;
    var deltaPhi = (lat2-lat1)* Math.PI / 180;
    var deltaLambda = (lon2-lon1)* Math.PI / 180;

    var a = Math.sin(deltaPhi/2) * Math.sin(deltaPhi/2) +
            Math.cos(phi1) * Math.cos(phi2) *
            Math.sin(deltaLambda/2) * Math.sin(deltaLambda/2);
    var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

    var d = R * c;
    return d
}


function addFusionTable1(id){
var layer1 = new google.maps.FusionTablesLayer({
          query: {
            select: 'geometry',
            from: id
          },
          styles: [{
      polygonOptions: {
        // fillColor: '#00FF00',
        fillOpacity: 0.0000000000001,
        strokeColor:'#FF0000',
        strokeWeight : 2
      }
    }]
    // map:map
        });
    layer1.setMap(map);
    }
function addFusionTable2(id){
var layer2 = new google.maps.FusionTablesLayer({
          query: {
            select: 'geometry',
            from: id
          },
          styles: [{
      polygonOptions: {
        // fillColor: '#00FF00',
        fillOpacity: 0.0000000000001,
        strokeColor:'#FF0000',
        strokeWeight : 2
      }
    }]
        });
layer2.setMap(map);
    
    }


function initialize() {
    var center = new google.maps.LatLng(initialCenter[0],initialCenter[1]);
    var zoom = initialZoomLevel;//8;

    var settings = null;
    // var randomID = null;
    if(typeof(Storage) !== "undefined"){
        settings = JSON.parse(localStorage.getItem("settings"));
        // randomID = JSON.parse(localStorage.getItem("randomID"));
    }

    if(settings != null && settings.center != null && settings.zoom != null){
        center = settings.center;
        zoom  = settings.zoom;
    }

  // var mapTypeIds = [];
  //           for(var type in google.maps.MapTypeId) {
  //               mapTypeIds.push(google.maps.MapTypeId[type]);
  //           }
    // mapTypeIds.push("Bing Satellite");
    // mapTypeIds.push("Mapbox Satellite");         
    
    // [1,2,3,4,5,6,7,8,9].map(function(n){mapTypeIds.push("Placeholder"+n.toString());})
   
    

	var mapOptions = {
	  center: center,
	  zoom: zoom,
	  minZoom: 2,
    disableDoubleClickZoom: true,
      // maxZoom: 15,
      mapTypeId: google.maps.MapTypeId.HYBRID,
	  streetViewControl: true,
    // fullscreenControl: false,
    fullscreenControlOptions:{position: google.maps.ControlPosition.LEFT_TOP},
    streetViewControlOptions:{position: google.maps.ControlPosition.LEFT_TOP},
    zoomControlOptions:{position: google.maps.ControlPosition.LEFT_TOP},
    tilt:0,
    // mapTypeId: "OSM",
    // mapTypeControlOptions: {
    //                 mapTypeIds: mapTypeIds,
    //                 // style: google.maps.MapTypeControlStyle.DROPDOWN_MENU,
    //                 // position: google.maps.ControlPosition.TOP_CENTER
    //             },
                scaleControl: true,
	};
    

    map = new google.maps.Map(document.getElementById("map"),
                                  mapOptions);

    
       
   //  var testUrl = 'https://ecos.fws.gov/arcgis/rest/services/cap/cap/MapServer/0?f=pjson'
   // var ctaLayer = new google.maps.KmlLayer({
   //        url: '../layers/change_no_change_shp2_k.kml',
   //        map: map
   //      });
            placeholderID = 1;


            function addWMS(url,name,maxZoom,xThenY){
              if(maxZoom === null || maxZoom === undefined  ){
                maxZoom = 19;
              }
              if(xThenY === null || xThenY === undefined  ){
                xThenY = false;
              }
                var imageMapType =  new google.maps.ImageMapType({
                getTileUrl: function(coord, zoom) {
                    // "Wrap" x (logitude) at 180th meridian properly
                    // NB: Don't touch coord.x because coord param is by reference, and changing its x property breakes something in Google's lib 
                    var tilesPerGlobe = 1 << zoom;
                    var x = coord.x % tilesPerGlobe;
                    if (x < 0) {
                        x = tilesPerGlobe+x;
                    }
                    // Wrap y (latitude) in a like manner if you want to enable vertical infinite scroll
                    // return "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/256/" + zoom + "/" + x + "/" + coord.y + "?access_token=pk.eyJ1IjoiaWhvdXNtYW4iLCJhIjoiY2ltcXQ0cnljMDBwNHZsbTQwYXRtb3FhYiJ9.Sql6G9QR_TQ-OaT5wT6f5Q"
                    if(xThenY ){
                        return url+ zoom + "/" + x + "/" + coord.y +".png?";
                    }
                    else{return url+ zoom + "/" + coord.y + "/" +x  +".png?";}//+ (new Date()).getTime();
                    
                },
                tileSize: new google.maps.Size(256, 256),
                name: name,
                maxZoom: maxZoom
            
            })

                   
                map.mapTypes.set('Placeholder' + placeholderID.toString(),imageMapType )
                placeholderID  ++;
            }
              
        var input = document.getElementById('pac-input');
        var searchBox = new google.maps.places.SearchBox(input);
        map.controls[google.maps.ControlPosition.TOP_LEFT].push(input);

        // Bias the SearchBox results towards current map's viewport.
        map.addListener('bounds_changed', function() {
          searchBox.setBounds(map.getBounds());
        });

        var markers = [];
        // Listen for the event fired when the user selects a prediction and retrieve
        // more details for that place.
        searchBox.addListener('places_changed', function() {
          var places = searchBox.getPlaces();

          if (places.length == 0) {
            return;
          }

          // Clear out the old markers.
          markers.forEach(function(marker) {
            marker.setMap(null);
          });
          markers = [];

          // For each place, get the icon, name and location.
          var bounds = new google.maps.LatLngBounds();
          places.forEach(function(place) {
            var icon = {
              url: place.icon,
              size: new google.maps.Size(71, 71),
              origin: new google.maps.Point(0, 0),
              anchor: new google.maps.Point(17, 34),
              scaledSize: new google.maps.Size(25, 25)
            };

            // Create a marker for each place.
            markers.push(new google.maps.Marker({
              map: map,
              icon: icon,
              title: place.name,
              position: place.geometry.location
            }));

            if (place.geometry.viewport) {
              // Only geocodes have viewport.
              bounds.union(place.geometry.viewport);
            } else {
              bounds.extend(place.geometry.location);
            }
          });
          
          map.fitBounds(bounds);
          console.log(bounds);
          var bounds = map.getBounds();
          eeBoundsPoly = ee.Geometry.Rectangle([bounds.fa.j,bounds.ma.j,bounds.fa.l,bounds.ma.l]);
          reRun();
        });
        if(helpBox){
          // document.getElementById('helpBoxButton').style.display = 'inline-block';
        }
        if(useShapes){
          
            document.getElementById('shape-edit-container').style.display = 'inline-block';
            
            shapesMap = new ShapesMap(
            map, 
            document.getElementById("delete-button"),
            document.getElementById("clear-button"),
            document.getElementById("process-button"),
            document.getElementById("export-button"),
            document.getElementById("toggle-drawing-button"),
            document.getElementById("console"));

            if(exportCapability){
              document.getElementById('export-container').style.display = 'block';
             //    document.getElementById('process-button').style.display = 'inline-block';
             // document.getElementById('export-button').style.display = 'inline-block';
             // document.getElementById('cancel-tasks-button').style.display = 'inline-block';
             // document.getElementById('export-scale').style.display = 'inline-block';


             // document.getElementById('export-crs').style.display = 'inline-block';

            
         }
    }
    if(userCharting){
       // document.getElementById('plot-radius').style.display = 'inline-block';
       // document.getElementById('plot-scale').style.display = 'inline-block'; 
        // document.getElementById('charting-radio').style.display = 'inline-block';
        document.getElementById('charting-label').style.display = 'inline-block';
        document.getElementById('Progress').style.display = 'inline-block';
    }
    if(includeTools){
         // document.getElementById('tool-area').style.display = 'inline-block';
    }
    if(includeLegend){
        document.getElementById('legend').style.display = 'inline-block';
        // document.getElementById('legend-button').style.display = 'inline-block';
    }
    if(displayParameters){
      // document.getElementById('parameters-only').style.display = 'inline-block';
    }
    if(plotNavigation){
      // document.getElementById('pt-list').style.display = 'inline-block';
      // document.getElementById('pt-project-list').style.display = 'inline-block';
      document.getElementById('plot-container').style.display = 'inline-block';
      document.getElementById('toggle-plot-list-button').style.display = 'inline-block';
    }
        // var shapesMap = new ShapesMap(
        // map, 
        // document.getElementById("delete-button"),
        // document.getElementById("clear-button"),
        // document.getElementById("process-button"),
        // document.getElementById("export-button"),
        // document.getElementById("stop-drawing-button"),
        // document.getElementById("console"));
        //     var panorama = new google.maps.StreetViewPanorama(
        //     document.getElementById('pano'), {
              
        //       pov: {
        //         heading: 34,
        //         pitch: 10
        //       }
        //     });
        // map.setStreetView(panorama);
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

        
        function updateMousePositionAndZoom(cLng,cLat,zoom,elevation){
                  
                $( "#current-mouse-position" ).html( 'Lng: ' +cLng + ', Lat: ' + cLat +', '+elevation+ 'Zoom: ' +zoom +', 1:'+zoomDict[zoom]);
        }
        
        // var elevationAPIKey = 'AIzaSyBiTunmJOy6JFGYWy2ms4_ScCOqK4rFf3w';
        // var elevationAPIKey = 'AIzaSyCXwPx9_pOQsvd-b_bG8ueGI82JnJO2mess';
        var elevator = new google.maps.ElevationService;
        var lastElevation = 0;
        var elevationCheckTime = 0
        function getElevation(center){
        mouseLat = center.lat().toFixed(4).toString();
        elevator.getElevationForLocations({
        'locations': [center]
        }, function(results, status) {
            // console.log(status);
        if(status === 'OVER_QUERY_LIMIT'){
          lastElevation = '';
          updateMousePositionAndZoom(mouseLng,mouseLat,zoom,'');
        }
        else if (status === 'OK') {
          // Retrieve the first result
          if (results[0]) {
            // Open the infowindow indicating the elevation at the clicked position.
                var thisElevation = results[0].elevation.toFixed(1);
                var thisElevationFt = (thisElevation*3.28084).toFixed(1);
                lastElevation = 'Elevation: '+thisElevation.toString()+'(m),'+thisElevationFt.toString()+'(ft),';
                updateMousePositionAndZoom(mouseLng,mouseLat,zoom,lastElevation)
                
          } else {
            updateMousePositionAndZoom(mouseLng,mouseLat,zoom,'No results found');
          }
        } 
        else {
          updateMousePositionAndZoom(mouseLng,mouseLat,zoom,lastElevation);
        }
        });
        }
        google.maps.event.addDomListener(mapDiv,'mousemove',function(event){
            var x =event.clientX;
            var y = event.clientY;
            var center =point2LatLng(x,y);
            var zoom = map.getZoom();
            // var center = event.latLng;
            mouseLat = center.lat().toFixed(4).toString();
            mouseLng = center.lng().toFixed(4).toString();
            var now = new Date().getTime()
            var dt = now - elevationCheckTime  ;
            
            if(dt > 2000){
              getElevation(center);
              elevationCheckTime = now;
            }
            else{updateMousePositionAndZoom(mouseLng,mouseLat,zoom,lastElevation)}
            
        })
        google.maps.event.addListener(map,'zoom_changed',function(){
            var zoom = map.getZoom();
            
            console.log('zoom changed')
            
            updateMousePositionAndZoom(mouseLng,mouseLat,zoom,lastElevation)
        })

    google.maps.event.addListener(map,'bounds_changed',function(){
        zoom = map.getZoom();
        console.log('bounds changed');
       var bounds = map.getBounds();
        // eeBoundsPoly = ee.Geometry.Rectangle([bounds.fa.j,bounds.ma.j,bounds.fa.l,bounds.ma.l]);

        if(typeof(Storage) == "undefined") return;
        localStorage.setItem("settings",JSON.stringify({center:{lat:map.getCenter().lat(),lng:map.getCenter().lng()},zoom:map.getZoom()}));
    });

    
    
        
    // if(randomID === null){randomID = parseInt(Math.random()*1000000)}
    // localStorage.setItem("randomID",JSON.stringify(randomID));

    //Specify proxy server location
    //Proxy server used for EE and GCS auth
    //RCR appspot proxy costs $$
	// ee.initialize("https://rcr-ee-proxy-server2.appspot.com/api","https://earthengine.googleapis.com/map",function(){
    // ee.initialize("https://rcr-ee-proxy.herokuapp.com/api","https://earthengine.googleapis.com/map",function(){
    
    // ee.initialize("http://localhost:8080/api","https://earthengine.googleapis.com/map",function(){
  run();
	// plotPlots()
	// });

}

google.maps.event.addDomListener(window, 'load', function(){
  
  initialize();
  
  });

