
function stopAllTools(){
  stopArea();
  stopDistance();
  stopQuery();
  stopCharting();
  stopAreaCharting();
  stopCharting();
  clearQueryGeoJSON();
  // clearQueryGeoJSON();
  // clearSelectedAreas();
  turnOffSelectLayers();
  turnOffSelectGeoJSON();

  Object.keys(toolFunctions).map(function(t){Object.keys(toolFunctions[t]).map(function(tt){toolFunctions[t][tt]['state'] = false})});
  updateToolStatusBar();
  
}
var toolFunctions = {'measuring':
                    {'area':
                      {'on':'stopAllTools();startArea();showTip("AREA MEASURING",staticTemplates.areaTip);',
                      'off':'stopAllTools();',
                      'state':false,
                      'title': 'Measuring Tools-Area Measuring'
                      },
                    'distance':
                      {'on':'stopAllTools();startDistance();showTip("DISTANCE MEASURING",staticTemplates.distanceTip);',
                      'off':'stopAllTools()',
                      'state':false,
                      'title': 'Measuring Tools-Distance Measuring'
                      }
                    },
                  'pixel':
                    {
                      'query':{
                        'on':'stopAllTools();startQuery();showTip("QUERY VISIBLE MAP LAYERS",staticTemplates.queryTip);',
                        'off':'stopAllTools()',
                        'state':false,
                        'title': 'Pixel Tools-Query Visible Map Layers'
                      },
                      'chart':{
                        'on':'stopAllTools();startPixelChartCollection();showTip("QUERY "+mode+" TIME SERIES",staticTemplates.pixelChartTip);',
                        'off':'stopAllTools()',
                        'state':false,
                        'title': 'Pixel Tools-Query '+mode+' Time Series'
                      }
                    },
                    'area':
                    {
                      'userDefined':{
                        'on':'stopAllTools();areaChartingTabSelect("#user-defined");showTip("SUMMARIZE BY USER-DEFINED AREA",staticTemplates.userDefinedAreaChartTip);',
                        'off':'stopAllTools()',
                        'state':false,
                        'title': 'Area Tools-User Defined Area Tool'
                      },
                      'shpDefined':{
                        'on':'stopAllTools();areaChartingTabSelect("#shp-defined");showTip("SUMMARIZE BY UPLOADED AREA",staticTemplates.uploadAreaChartTip);',
                        'off':'stopAllTools()',
                        'state':false,
                        'title': 'Area Tools-Upload an Area'
                      },
                      'selectDropdown':{
                        'on':'stopAllTools();areaChartingTabSelect("#pre-defined");showTip("SUMMARIZE BY PRE-DEFINED AREA",staticTemplates.selectAreaDropdownChartTip);',
                        'off':'stopAllTools()',
                        'state':false,
                        'title': 'Area Tools-Select an Area from Dropdown'
                      },
                      'selectInteractive':{
                        'on':'stopAllTools();turnOffVectorLayers();turnOnSelectGeoJSON();areaChartingTabSelect("#user-selected");showTip("SUMMARIZE BY PRE-DEFINED AREA",staticTemplates.selectAreaInteractiveChartTip);',
                        'off':'stopAllTools();turnOffSelectLayers();',
                        'state':false,
                        'title': 'Area Tools-Select an Area on map'
                      },
                    }
                  }
function updateToolStatusBar(){
  var somethingShown = false;
  $('#current-tool-selection').empty();
  $('#current-tool-selection').append(`Currently active tools: `)
  Object.keys(toolFunctions).map(function(t){Object.keys(toolFunctions[t]).map(function(tt){
                                                                        var state = toolFunctions[t][tt]['state'];
                                                                        var title = toolFunctions[t][tt]['title'];
                                                                        if(state){
                                                                          $('#current-tool-selection').append(`${title}`)
                                                                          somethingShown = true
                                                                        } 
                                                                        
                                                                      })});
  if(!somethingShown){$('#current-tool-selection').append(`No active tools`)}
}
function toggleTool(tool){

  if(tool.state){
    eval(tool.off);

    // tool.state = false
  }else{
    eval(tool.on);
    tool.state = true
  };
  updateToolStatusBar();
}


updateToolStatusBar();
// var paragraphs = document.getElementsByClassName("collapse-title");
// for (var i = 0; i < paragraphs.length; i++) {
//   var paragraph = paragraphs.item(i);
//   paragraph.style.setProperty("font-size", "0.5em", null);
//   paragraph.style.setProperty("padding", "0.0em", null);
//   paragraph.style.setProperty("margin", "0.0em", null);
// }