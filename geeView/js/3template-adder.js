$('body').append(staticTemplates.map);

$('body').append(staticTemplates.mainContainer);
$('body').append(staticTemplates.sidebarLeftContainer);

$('body').append(staticTemplates.geeSpinner);
$('body').append(staticTemplates.bottomBar);

$('#summary-spinner').show();

$('#main-container').append(staticTemplates.sidebarLeftToggler);

$('#sidebar-left-header').append(staticTemplates.topBanner);

// $('#title-banner').fitText(1.2);
// $('#studyAreaDropdownLabel').fitText(0.5);


$('#main-container').append(staticTemplates.introModal[mode]);

if(localStorage.showIntroModal == undefined){
  localStorage.showIntroModal = 'true';
  }

$('#dontShowAgainCheckbox').change(function(){
  console.log(this.checked)
  localStorage.showIntroModal  = !this.checked;
});
if(mode === 'LCMS'){
  $('#title-banner').append(staticTemplates.studyAreaDropdown);
  Object.keys(studyAreaDict).map(function(k){addStudyAreaToDropdown(k,studyAreaDict[k].popOver);});
}
$('#title-banner').append(staticTemplates.placesSearchDiv);
$('#title-banner').fitText(1.2);
$('#study-area-label').fitText(1.8);


function toggleAdvancedOn(){
    $("#threshold-container").slideDown();
    $("#advanced-radio-container").slideDown();  
}
function toggleAdvancedOff(){
    $("#threshold-container").slideUp();
    $("#advanced-radio-container").slideUp();  
}

if(mode === 'LCMS'){


  addCollapse('sidebar-left','parameters-collapse-label','parameters-collapse-div','PARAMETERS','<i class="fa fa-sliders mr-1" aria-hidden="true"></i>',false,null,'Adjust parameters used to filter and sort LCMS products');
  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div','LCMS DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,'LCMS DATA layers to view on map');
  
  addCollapse('sidebar-left','reference-layer-list-collapse-label','reference-layer-list-collapse-div','REFERENCE DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,false,null,'Additional relevant layers to view on map intended to provide context for LCMS DATA');

  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');

  addCollapse('sidebar-left','download-collapse-label','download-collapse-div','DOWNLOAD DATA',`<i class="fa fa-cloud-download mr-1" aria-hidden="true"></i>`,false,``,'Download LCMS products for further analysis');
  addCollapse('sidebar-left','support-collapse-label','support-collapse-div','SUPPORT',`<i class="fa fa-question-circle mr-1" aria-hidden="true"></i>`,false,``,'If you need any help');

  // $('#parameters-collapse-div').append(staticTemplates.paramsDiv);

  //Construct parameters form
  addRadio('parameters-collapse-div','analysis-mode-radio','Choose which mode:','Standard','Advanced','analysisMode','standard','advanced','toggleAdvancedOff()','toggleAdvancedOn()','Standard mode provides the core LCMS products based on carefully selected parameters. Advanced mode provides additional LCMS products and parameter options')
  $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  addDualRangeSlider('parameters-collapse-div','Choose analysis year range:','startYear','endYear',startYear, endYear, startYear, endYear, 1,'analysis-year-slider','null','Years of LCMS data to include for land cover, land use, loss, and gain')

  $('#parameters-collapse-div').append(`<div class="dropdown-divider"></div>
                                          <div id='threshold-container' style="display:none;width:100%"></div>
                                          <div id='advanced-radio-container' style="display: none;"></div>`)
  addDualRangeSlider('threshold-container','Choose loss threshold:','lowerThresholdDecline','upperThresholdDecline',0, 1, lowerThresholdDecline, upperThresholdDecline, 0.05,'decline-threshold-slider','null',"Threshold window for detecting loss.  Any loss probability within the specified window will be flagged as loss ")
  $('#threshold-container').append(`<div class="dropdown-divider" ></div>`);
  addDualRangeSlider('threshold-container','Choose gain threshold:','lowerThresholdRecovery','upperThresholdRecovery',0, 1, lowerThresholdRecovery, upperThresholdRecovery, 0.05,'recovery-threshold-slider','null',"Threshold window for detecting gain.  Any gain probability within the specified window will be flagged as gain ")
  $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);

  addRadio('advanced-radio-container','treemask-radio','Constrain analysis to areas with trees:','Yes','No','applyTreeMask','yes','no','','','Whether to constrain LCMS products to only treed areas. Any area LCMS classified as tree cover 2 or more years will be considered tree. Will reduce commission errors typical in agricultural and water areas, but may also reduce changes of interest in these areas.')
  $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);
  addRadio('advanced-radio-container','viewBeta-radio','View beta outputs:','No','Yes','viewBeta','no','yes','','','Whether to view products that are currently in beta development')
  $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);
  addRadio('advanced-radio-container','summaryMethod-radio','Summary method:','Most recent year','Highest probability','summaryMethod','year','prob','','','How to choose which value for loss and gain to display/export.  Choose the value with the highest probability or from the most recent year above the specified threshold')
  $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);
  addRadio('advanced-radio-container','whichIndex-radio','Index for charting:','NDVI','NBR','whichIndex','NDVI','NBR','','','The vegetation index that will be displayed in the "Query LCMS Time Series" tool')
  $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(staticTemplates.reRunButton);

  //Set up layer lists
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  $('#reference-layer-list-collapse-div').append(`<div id="reference-layer-list"></div>`);


  $('#download-collapse-div').append(staticTemplates.downloadDiv);
  $('#support-collapse-div').append(staticTemplates.supportDiv);

}else if(mode === 'lcms-base-learner'){
  canExport = true;
  addCollapse('sidebar-left','parameters-collapse-label','parameters-collapse-div','PARAMETERS','<i class="fa fa-sliders mr-1" aria-hidden="true"></i>',false,null,'Adjust parameters used to filter and sort LCMS products');
  addDualRangeSlider('parameters-collapse-div','Choose analysis year range:','startYear','endYear',startYear, endYear, startYear, endYear, 1,'analysis-year-slider','null','Years of LCMS data to include for land cover, land use, loss, and gain')

  addSubCollapse('parameters-collapse-div','lt-params-label','lt-params-div','LANDTRENDR Params', '',false,'')
  addSubCollapse('parameters-collapse-div','ccdc-params-label','ccdc-params-div','CCDC Params', '',false,'')
  
  addRangeSlider('lt-params-div','Loss Magnitude Threshold','lossMagThresh',-0.8,0,-0.2,0.01,'loss-mag-thresh-slider','','The threshold to detect loss for each LANDTRENDR segment.  Any difference for a given segement less than this threshold will be flagged as loss') 
  addRangeSlider('lt-params-div','Gain Magnitude Threshold','gainMagThresh',0,0.8,0.1,0.01,'gain-mag-thresh-slider','','The threshold to detect gain for each LANDTRENDR segment.  Any difference for a given segement greater than this threshold will be flagged as gain') 
   addCheckboxes('lt-params-div','index-choice-checkboxes','Choose which indices to analyze','whichIndices',{'B1':false,'B2':false,'B3':false,'B4':false,'B5':false,'B7':false,'NBR':true,'NDVI':false,'NDMI':false,'TCB':false,'TCG':false,'TCW':false,'TCA':false})
  // $('#lt-params-div').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(staticTemplates.reRunButton);

  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div','LCMS BASE LEARNER DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,'LCMS DATA layers to view on map');
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');
  addCollapse('sidebar-left','download-collapse-label','download-collapse-div','DOWNLOAD DATA',`<i class="fa fa-cloud-download mr-1" aria-hidden="true"></i>`,false,``,'Download '+mode+' products for further analysis');
  
}else if(mode === 'LT'){
  canExport = true;
  addCollapse('sidebar-left','parameters-collapse-label','parameters-collapse-div','PARAMETERS','<i class="fa fa-sliders mr-1" aria-hidden="true"></i>',false,null,'Adjust parameters used to filter and sort '+mode+' products');
  
  addSubCollapse('parameters-collapse-div','comp-params-label','comp-params-div','Landsat Composite Params', '',false,'')
  addDualRangeSlider('comp-params-div','Choose analysis year range:','startYear','endYear',startYear, endYear, startYear, endYear, 1,'analysis-year-slider','null','Years of '+mode+' data to include.')
  $('#comp-params-div').append(`<div class="dropdown-divider" ></div>`);
  addDualRangeSlider('comp-params-div','Choose analysis date range:','startJulian','endJulian',1, 365, startJulian, endJulian, 1,'julian-day-slider','julian','Days of year of '+mode+' data to include for land cover, land use, loss, and gain')
    $('#comp-params-div').append(`<div class="dropdown-divider" ></div>`);
    addCheckboxes('comp-params-div','which-sensor-method-radio','Choose which Landsat platforms to include','whichPlatforms',{"L5":true,"L7-SLC-On":true,'L7-SLC-Off':false,'L8':true});
    $('#comp-params-div').append(`<div class="dropdown-divider" ></div>`);
    addRangeSlider('comp-params-div','Composite Year Buffer','yearBuffer',0,2,0,1,'year-buffer-slider','','The number of adjacent years to include in a given year composite. (E.g. a value of 1 would mean the 2015 composite would have imagery from 2015 +- 1 year - 2014 to 2016)') 
   $('#comp-params-div').append(`<div class="dropdown-divider" ></div>`);
   addRangeSlider('comp-params-div','Minimum Number of Observations','minObs',0,5,3,1,'min-obs-slider','','Minimum number of observations needed for a pixel to be included. This helps reduce noise in composites. Any number less than 3 can result in poor composite quality') 
    $('#comp-params-div').append(`<div class="dropdown-divider" ></div>`);
  addMultiRadio('comp-params-div','comp-method-radio','Compositing method','compMethod',{"Median":false,"Medoid":true})
   $('#comp-params-div').append(`<div class="dropdown-divider" ></div>`);
  addCheckboxes('comp-params-div','cloud-masking-checkboxes','Choose which cloud masking methods to use','whichCloudMasks',{'fMask-Snow':true,'cloudScore':false,'fMask-Cloud':true,'TDOM':false,'fMask-Cloud-Shadow':true})
   $('#comp-params-div').append(`<div class="dropdown-divider" ></div>`);
  addMultiRadio('comp-params-div','water-mask-radio','Mask out water','maskWater',{"No":false,"Yes":true})
  
  // $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  // addRadio('parameters-collapse-div','cloudScore-cloud-radio','Apply CloudScore','No','Yes','applyCloudScore','no','yes','','',"Whether to apply Google's Landsat CloudScore algorithm")
  // $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  // addRadio('parameters-collapse-div','fmask-cloud-radio','Apply Fmask cloud mask','Yes','No','applyFmaskCloud','yes','no','','','Whether to apply Fmask cloud mask')
  // $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  // addRadio('parameters-collapse-div','fmask-cloud-shadow-radio','Apply Fmask cloud shadow mask','Yes','No','applyFmaskCloudShadow','yes','no','','','Whether to apply Fmask cloud shadow mask')
  
 
  
  addSubCollapse('parameters-collapse-div','lt-params-label','lt-params-div','LANDTRENDR Params', '',false,'')
    
  addCheckboxes('lt-params-div','index-choice-checkboxes','Choose which indices to analyze','whichIndices',{'NBR':true,'NDVI':false,'NDMI':false,'NDSI':false,'brightness':false,'greenness':false,'wetness':false,'tcAngleBG':false})
  $('#lt-params-div').append(`<div class="dropdown-divider" ></div>`);
  addMultiRadio('lt-params-div','lt-sort-radio','Choose method to summarize LANDTRENDR change','LTSortBy',{"largest":true,"steepest":false,"newest":false, "oldest":false,  "shortest":false, "longest":false})
   
  addRangeSlider('lt-params-div','Loss Magnitude Threshold','lossMagThresh',-0.8,0,-0.15,0.01,'loss-mag-thresh-slider','','The threshold to detect loss for each LANDTRENDR segment.  Any difference between start and end values for a given segement less than this threshold will be flagged as loss') 
  addRangeSlider('lt-params-div','Loss Slope Threshold','lossSlopeThresh',-0.8,0,-0.10,0.01,'loss-slope-thresh-slider','','The threshold to detect loss for each LANDTRENDR segment.  Any slope of a given segement less than this threshold will be flagged as loss') 
  
  addRangeSlider('lt-params-div','Gain Magnitude Threshold','gainMagThresh',0.01,0.8,0.1,0.01,'gain-mag-thresh-slider','','The threshold to detect gain for each LANDTRENDR segment.  Any difference between start and end values for a given segement greater than this threshold will be flagged as gain') 
  addRangeSlider('lt-params-div','Gain Slope Threshold','gainSlopeThresh',0.01,0.8,0.1,0.01,'gain-slope-thresh-slider','','The threshold to detect gain for each LANDTRENDR segment.  Any slope of a given segement greater than this threshold will be flagged as gain') 
  
  addRangeSlider('lt-params-div','How Many','howManyToPull',1,3,2,1,'how-many-slider','','The number of gains and losses to show. Typically an area only experiences a single loss/gain event, but in the cases where there are multiple above the specified thresholds, they can be shown.') 
  addRangeSlider('lt-params-div','Max LANDTRENDR Segments','maxSegments',1,8,6,1,'max-segments-slider','','The max number of segments LANDTRENDR can break time series into.  Generally 3-6 works well. Use a smaller number of characterizing long-term trends is the primary focus and a larger number if characterizing every little change is the primary focus.') 
  
  $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(staticTemplates.reRunButton);
  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div','MAP DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,mode+' DATA layers to view on map');
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);

  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');
  addCollapse('sidebar-left','download-collapse-label','download-collapse-div','DOWNLOAD DATA',`<i class="fa fa-cloud-download mr-1" aria-hidden="true"></i>`,false,``,'Download '+mode+' products for further analysis');
  
}else if(mode === 'MTBS'){
  startYear = 1984;
  endYear = 2017;
  
  
  addCollapse('sidebar-left','parameters-collapse-label','parameters-collapse-div','PARAMETERS','<i class="fa fa-sliders mr-1" aria-hidden="true"></i>',false,null,'Adjust parameters used to filter and sort MTBS products');
  
  var mtbsZoomToDict ={"All":true,"CONUS":false,"Alaska":false,"Hawaii":false,"Puerto-Rico":false};

  addMultiRadio('parameters-collapse-div','mtbs-zoom-to-radio','Zoom to MTBS Mapping Area','mtbsMappingArea',mtbsZoomToDict)
  $('#mtbs-zoom-to-radio').prop('title','Zoom to MTBS region')
  $( "#mtbs-zoom-to-radio" ).change(function() {
    console.log(mtbsMappingArea);
    synchronousCenterObject(clientBoundsDict[mtbsMappingArea])
  });
  $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  
  addDualRangeSlider('parameters-collapse-div','Choose analysis year range:','startYear','endYear',startYear, endYear, startYear, endYear, 1,'analysis-year-slider','null','Years of MTBS data to include')
  addMultiRadio('parameters-collapse-div','mtbs-summary-method-radio','How to summarize MTBS data','mtbsSummaryMethod',{"Highest-Severity":true,"Most-Recent":false,"Oldest":false})

  $('#mtbs-summary-method-radio').prop('title','Select how to summarize MTBS raster data in areas with multiple fires.  Each summary method is applied on a pixel basis. "Highest-Severity" will show the severity and fire year corresponding to the highest severity. "Most-Recent" will show the severity and fire year corresponding to the most recently mapped fire. "Oldest" will show the severity and fire year corresponding to the oldest mapped fire.')
  $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(staticTemplates.reRunButton);

  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div',mode+' DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,mode+' DATA layers to view on map');
  addCollapse('sidebar-left','reference-layer-list-collapse-label','reference-layer-list-collapse-div','REFERENCE DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,false,null,'Additional relevant layers to view on map intended to provide context for '+mode+' DATA');
  
  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');
  addCollapse('sidebar-left','support-collapse-label','support-collapse-div','SUPPORT',`<i class="fa fa-question-circle mr-1" aria-hidden="true"></i>`,false,``,'If you need any help');

  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  $('#reference-layer-list-collapse-div').append(`<div id="reference-layer-list"></div>`);
  
  $('#support-collapse-div').append(staticTemplates.walkThroughButton);
  $('#support-collapse-div').append(`<div class="dropdown-divider"</div>`);
  $('#support-collapse-div').append(`<a href="https://www.mtbs.gov/contact" target="_blank" title = 'If you have any questions or comments, feel free to contact us'>Contact Us</a>`)
  $('#support-collapse-div').append(`<div class="dropdown-divider mb-2"</div>`);
  $('#introModal-body').append(staticTemplates.walkThroughButton);
}else if(mode === 'TEST'){
  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div',mode+' DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,mode+' DATA layers to view on map');
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');

}else if(mode === 'geeViz'){
  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div',mode+' DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,mode+' DATA layers to view on map');
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');
  
}else{
  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div','ANCILLARY DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,mode+' DATA layers to view on map');
  addCollapse('sidebar-left','reference-layer-list-collapse-label','reference-layer-list-collapse-div','PLOT DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,false,null,'Additional relevant layers to view on map intended to provide context for '+mode+' DATA');
  
  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');

  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  $('#reference-layer-list-collapse-div').append(`<div id="reference-layer-list"></div>`);
  plotsOn = true;
}

$('body').append(`<div class = 'legendDiv flexcroll col-sm-5 col-md-4 col-lg-3 col-xl-2 p-0 m-0' id = 'legendDiv'></div>`);
$('.legendDiv').css('bottom',$('.bottombar').height());
$('.sidebar').css('max-height',$('body').height()-$('.bottombar').height());
addLegendCollapse();

//Add tool tabs
 

addAccordianContainer('tools-collapse-div','tools-accordian')
$('#tools-accordian').append(`<h5 class = 'pt-2' style = 'border-top: 0.1em solid black;'>Measuring Tools</h5>`);
// $('#tools-accordian').append(staticTemplates.imperialMetricToggle);
addSubAccordianCard('tools-accordian','measure-distance-label','measure-distance-div','Distance Measuring',staticTemplates.distanceDiv,false,`toggleTool(toolFunctions.measuring.distance)`,staticTemplates.distanceTipHover);

// <variable-radio onclick1 = 'updateDistance()' onclick2 = 'updateDistance()'var='metricOrImperialDistance' title2='' name2='Metric' name1='Imperial' value2='metric' value1='imperial' type='string' href="#" rel="txtTooltip" data-toggle="tooltip" data-placement="top" title='Toggle between imperial or metric units'></variable-radio>
addSubAccordianCard('tools-accordian','measure-area-label','measure-area-div','Area Measuring',staticTemplates.areaDiv,false,`toggleTool(toolFunctions.measuring.area)`,staticTemplates.areaTipHover);
addRadio('measure-distance-div','metricOrImperialDistance-radio','','Imperial','Metric','metricOrImperialDistance','imperial','metric','updateDistance()','updateDistance()','Toggle between imperial or metric units')

addRadio('measure-area-div','metricOrImperialArea-radio','','Imperial','Metric','metricOrImperialArea','imperial','metric','updateArea()','updateArea()','Toggle between imperial or metric units')

addShapeEditToolbar('measure-distance-div', 'measure-distance-div-icon-bar','undoDistanceMeasuring()','resetPolyline()')
addColorPicker('measure-distance-div-icon-bar','distance-color-picker','updateDistanceColor',distancePolylineOptions.strokeColor);

addShapeEditToolbar('measure-area-div', 'measure-area-div-icon-bar','undoAreaMeasuring()','resetPolys()')
addColorPicker('measure-area-div-icon-bar','area-color-picker','updateAreaColor',areaPolygonOptions.strokeColor);

// addAccordianContainer('pixel-tools-collapse-div','pixel-tools-accordian');
$('#tools-accordian').append(`<h5 class = 'pt-2' style = 'border-top: 0.1em solid black;'>Pixel Tools</h5>`);
addSubAccordianCard('tools-accordian','query-label','query-div','Query Visible Map Layers',staticTemplates.queryDiv,false,`toggleTool(toolFunctions.pixel.query)`,staticTemplates.queryTipHover);
addSubAccordianCard('tools-accordian','pixel-chart-label','pixel-chart-div','Query '+mode+' Time Series',staticTemplates.pixelChartDiv,false,`toggleTool(toolFunctions.pixel.chart)`,staticTemplates.pixelChartTipHover);
// $('#pixel-chart-div').append(staticTemplates.showChartButton);
// addAccordianContainer('area-tools-collapse-div','area-tools-accordian');
if(mode === 'geeViz'){
  $('#pixel-chart-label').remove();
}

if(mode === 'LCMS' || mode === 'MTBS' ){
  $('#tools-accordian').append(`<h5 class = 'pt-2' style = 'border-top: 0.1em solid black;'>Area Tools</h5>`);
  $('#tools-accordian').append(`<div class="dropdown-divider" ></div>`);
  addDropdown('tools-accordian','area-collection-dropdown','Choose which '+mode+' product to summarize','whichAreaChartCollection','Choose which '+mode+' time series to summarize.');
  $('#tools-accordian').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  addMultiRadio('tools-accordian','area-summary-format','Area Units','areaChartFormat',{"Percentage":true,"Acres":false,"Hectares":false})
  $('#area-summary-format').prop('title','Choose how to summarize area- as a percentage of the area, acres, or hectares.')
  addSubAccordianCard('tools-accordian','user-defined-area-chart-label','user-defined-area-chart-div','User-Defined Area',staticTemplates.userDefinedAreaChartDiv,false,`toggleTool(toolFunctions.area.userDefined)`,staticTemplates.userDefinedAreaChartTipHover);
  addSubAccordianCard('tools-accordian','upload-area-chart-label','upload-area-chart-div','Upload an Area',staticTemplates.uploadAreaChartDiv,false,'toggleTool(toolFunctions.area.shpDefined)',staticTemplates.uploadAreaChartTipHover);
  // addSubAccordianCard('tools-accordian','select-area-dropdown-chart-label','select-area-dropdown-chart-div','Select an Area from Dropdown',staticTemplates.selectAreaDropdownChartDiv,false,'toggleTool(toolFunctions.area.selectDropdown)',staticTemplates.selectAreaDropdownChartTipHover);
  addSubAccordianCard('tools-accordian','select-area-interactive-chart-label','select-area-interactive-chart-div','Select an Area on Map',staticTemplates.selectAreaInteractiveChartDiv,false,'toggleTool(toolFunctions.area.selectInteractive)',staticTemplates.selectAreaInteractiveChartTipHover);

  addShapeEditToolbar('user-defined-edit-toolbar', 'user-defined-area-icon-bar','undoUserDefinedAreaCharting()','restartUserDefinedAreaCarting()')
  addColorPicker('user-defined-area-icon-bar','user-defined-color-picker','updateUDPColor',udpOptions.strokeColor);

  addShapeEditToolbar('select-features-edit-toolbar', 'select-area-interactive-chart-icon-bar','removeLastSelectArea()','clearSelectedAreas()','Click to unselect most recently selected polyogn','Click to clear all selected polygons')
  
  // $('#user-defined-area-chart-div').append(staticTemplates.showChartButton);
  // $('#upload-area-chart-div').append(staticTemplates.showChartButton);
  // $('#select-area-dropdown-chart-div').append(staticTemplates.showChartButton);
  // $('#select-area-interactive-chart-div').append(staticTemplates.showChartButton);
  // $('#tools-accordian').append(staticTemplates.showChartButton);

}
if(mode === 'MTBS' || mode === 'Ancillary'){
  $('#contributor-logos').prepend(`<a href="https://www.usgs.gov/" target="_blank" >
                                    <img src="images/usgslogo.png" class = 'image-icon-bar'  href="#"  rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="Click to learn more about the US Geological Survey">
                                  </a>`)
  $('#contributor-logos').prepend(`<a href="https://www.mtbs.gov/" target="_blank" >
                                    <img src="images/mtbs-logo.png" class = 'image-icon-bar'  href="#"  rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="Click to learn more about the US Geological Survey">
                                  </a>`)
}
if(canExport){
   $('#download-collapse-div').append(staticTemplates.exportContainer);
   if(localStorage.export_crs !== undefined && localStorage.export_crs !== null && localStorage.export_crs.indexOf('EPSG') > -1){
    $('#export-crs').val(localStorage.export_crs)
  }else{localStorage.export_crs = $('#export-crs').val()};
   function cacheCRS(){
    localStorage.export_crs = $('#export-crs').val();
   }
}

// addToggle('measure-distance-div','toggler-distance-units','Toggle imperial or metric units: ',"Imperial",'Metric','true','metricOrImperialDistance','imperial','metric','updateDistance()');
// addToggle('measure-area-div','toggler-area-units','Toggle imperial or metric units: ',"Imperial",'Metric','true','metricOrImperialArea','imperial','metric','updateArea()');


// $('#sidebar-left').append(`<button onclick="getLocation()">Try It</button><p id="demo"></p>`)
// var x = document.getElementById("demo");

function getLocation() {
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(showPosition, showError);
  } else { 
    x.innerHTML = "Geolocation is not supported by this browser.";
  }
}

function showPosition(position) {
  x.innerHTML = "Latitude: " + position.coords.latitude + 
  "<br>Longitude: " + position.coords.longitude;
}

function showError(error) {
  switch(error.code) {
    case error.PERMISSION_DENIED:
      x.innerHTML = "User denied the request for Geolocation."
      break;
    case error.POSITION_UNAVAILABLE:
      x.innerHTML = "Location information is unavailable."
      break;
    case error.TIMEOUT:
      x.innerHTML = "The request to get user location timed out."
      break;
    case error.UNKNOWN_ERROR:
      x.innerHTML = "An unknown error occurred."
      break;
  }
}

