/*This script constructs the page depending on the chosen mode*/
/*Put main elements on body*/
$('body').append(staticTemplates.map);

$('body').append(staticTemplates.mainContainer);
$('body').append(staticTemplates.sidebarLeftContainer);

$('body').append(staticTemplates.geeSpinner);
$('body').append(staticTemplates.bottomBar);

$('#summary-spinner').show();

$('#main-container').append(staticTemplates.sidebarLeftToggler);

$('#sidebar-left-header').append(staticTemplates.topBanner);

$('#main-container').append(staticTemplates.introModal[mode]);
/////////////////////////////////////////////////////////////////////
/*Check to see if modals should be shown*/
if(localStorage.showIntroModal == undefined){
  localStorage.showIntroModal = 'true';
  }

$('#dontShowAgainCheckbox').change(function(){
  console.log(this.checked)
  localStorage.showIntroModal  = !this.checked;
});
/////////////////////////////////////////////////////////////////////
/*Add study area dropdown if LCMS*/
if(mode === 'LCMS'){
  $('#title-banner').append(staticTemplates.studyAreaDropdown);
  if(studyAreaSpecificPage){
    $('#study-area-label').removeClass('dropdown-toggle');
  }else{
    Object.keys(studyAreaDict).map(function(k){addStudyAreaToDropdown(k,studyAreaDict[k].popOver);});
  }

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
/////////////////////////////////////////////////////////////////////
/*Start adding elements to page based on chosen mode*/
if(mode === 'LCMS'){
  var minYear = startYear;var maxYear = endYear;
  // console.log(urlParams)  
  if(urlParams.startYear == null || urlParams.startYear == undefined){
      urlParams.startYear = startYear;
  }
  if(urlParams.endYear == null || urlParams.endYear == undefined){
     urlParams.endYear = endYear;
  }
  // console.log(urlParams)
 
  /*Construct panes in left sidebar*/
  addCollapse('sidebar-left','parameters-collapse-label','parameters-collapse-div','PARAMETERS','<i class="fa fa-sliders mr-1" aria-hidden="true"></i>',false,null,'Adjust parameters used to filter and sort LCMS products');
  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div','LCMS DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,'LCMS DATA layers to view on map');
  // $('#layer-list-collapse-label').append(`<button class = 'btn' title = 'Refresh layers if tiles failed to load' id = 'refresh-tiles-button' onclick = 'jitterZoom()'><i class="fa fa-refresh"></i></button>`)
  addCollapse('sidebar-left','reference-layer-list-collapse-label','reference-layer-list-collapse-div','REFERENCE DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,false,null,'Additional relevant layers to view on map intended to provide context for LCMS DATA');
  
  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');

  addCollapse('sidebar-left','download-collapse-label','download-collapse-div','DOWNLOAD DATA',`<i class="fa fa-cloud-download mr-1" aria-hidden="true"></i>`,false,``,'Download LCMS products for further analysis');
  addCollapse('sidebar-left','support-collapse-label','support-collapse-div','SUPPORT',`<i class="fa fa-question-circle mr-1" aria-hidden="true"></i>`,false,``,'If you need any help');

  // $('#parameters-collapse-div').append(staticTemplates.paramsDiv);

  //Construct parameters form
 
  if(['standard','advanced'].indexOf(urlParams.analysisMode) === -1){
    urlParams.analysisMode = 'standard'
  }
  var tAnalysisMode = urlParams.analysisMode;
  addRadio('parameters-collapse-div','analysis-mode-radio','Choose which mode:','Standard','Advanced','urlParams.analysisMode','standard','advanced','toggleAdvancedOff()','toggleAdvancedOn()','Standard mode provides the core LCMS products based on carefully selected parameters. Advanced mode provides additional LCMS products and parameter options')

  urlParams.analysisMode = tAnalysisMode ;
  $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);

  addDualRangeSlider('parameters-collapse-div','Choose analysis year range:','urlParams.startYear','urlParams.endYear',minYear, maxYear, urlParams.startYear, urlParams.endYear, 1,'analysis-year-slider','null','Years of LCMS data to include for land cover, land use, loss, and gain')

  $('#parameters-collapse-div').append(`<div class="dropdown-divider"></div>
                                          <div id='threshold-container' style="display:none;width:100%"></div>
                                          <div id='advanced-radio-container' style="display: none;"></div>`)
  // console.log('here')
  // addRangeSlider('threshold-container','Choose loss threshold:','lowerThresholdDecline',0,1,lowerThresholdRecovery,0.05,'decline-threshold-slider','','The CCDC probabibility threshold to detect change.  Any probability for a given break greater than this threshold will be flagged as change') 
  
  // addRangeSlider('threshold-container','Choose loss threshold:','lowerThresholdDecline',0,1,lowerThresholdDecline,0.05,'decline-threshold-slider','null',"Threshold window for detecting loss.  Any loss probability greater than the specified threshold will be flagged as loss ") 
  // containerDivID,title,variable,min,max,defaultValue,step,sliderID,mode,tooltip
  addRangeSlider('threshold-container','Choose loss threshold:','lowerThresholdDecline',0, 1, lowerThresholdDecline, 0.05,'decline-threshold-slider','null',"Threshold window for detecting loss.  Any loss probability greater than or equal to this value will be flagged as loss ")
  $('#threshold-container').append(`<div class="dropdown-divider" ></div>`);
  addRangeSlider('threshold-container','Choose gain threshold:','lowerThresholdRecovery',0, 1, lowerThresholdRecovery, 0.05,'recovery-threshold-slider','null',"Threshold window for detecting gain.  Any gain probability greater than or equal to this value will be flagged as gain ")
  $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);
  $('#advanced-radio-container').append(`<div id = 'fast-slow-threshold-container' ></div>`);
  addRangeSlider('fast-slow-threshold-container','Choose slow loss threshold:','lowerThresholdSlowLoss',0, 1, lowerThresholdSlowLoss , 0.05,'slow-loss-threshold-slider','null',"Threshold window for detecting loss.  Any loss probability greater than or equal to this value will be flagged as loss ")
  $('#fast-slow-threshold-container').append(`<div class="dropdown-divider" ></div>`);
  addRangeSlider('fast-slow-threshold-container','Choose fast loss threshold:','lowerThresholdFastLoss',0, 1, lowerThresholdFastLoss, 0.05,'fast-loss-threshold-slider','null',"Threshold window for detecting loss.  Any loss probability greater than or equal to this value will be flagged as loss ")
  $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);
  addRadio('advanced-radio-container','treemask-radio','Constrain analysis to areas with trees:','Yes','No','applyTreeMask','yes','no','','','Whether to constrain LCMS products to only treed areas. Any area LCMS classified as tree cover 2 or more years will be considered tree. Will reduce commission errors typical in agricultural and water areas, but may also reduce changes of interest in these areas.')
  $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);
 
  
  addRadio('advanced-radio-container','summaryMethod-radio','Summary method:','Most recent year','Highest probability','summaryMethod','year','prob','','','How to choose which value for loss and gain to display/export.  Choose the value with the highest probability or from the most recent year above the specified threshold')
  $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);
  // addRadio('advanced-radio-container','whichIndex-radio','Index for charting:','NDVI','NBR','whichIndex','NDVI','NBR','','','The vegetation index that will be displayed in the "Query LCMS Time Series" tool')
  // $('#advanced-radio-container').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(staticTemplates.reRunButton);

  //Set up layer lists
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  $('#reference-layer-list-collapse-div').append(`<div id="reference-layer-list"></div>`);


  $('#download-collapse-div').append(staticTemplates.downloadDiv);
  $('#support-collapse-div').append(staticTemplates.supportDiv);

  if(tAnalysisMode === 'advanced'){
    $('#analysis-mode-radio-second_toggle_label').click();
  }

}else if(mode === 'lcms-base-learner'){
  canExport = true;
  startYear = 1984;endYear = 2020;
  var minYear = startYear;var maxYear = endYear;
  if(urlParams.startYear == null || urlParams.startYear == undefined){
      urlParams.startYear = startYear;// = parseInt(urlParams.startYear);
  }
  if(urlParams.endYear == null || urlParams.endYear == undefined){
     urlParams.endYear = endYear;// = parseInt(urlParams.endYear);
  }
  if(urlParams.lossMagThresh == null || urlParams.lossMagThresh == undefined){
     urlParams.lossMagThresh = -0.2;// = parseInt(urlParams.endYear);
  }
  if(urlParams.gainMagThresh == null || urlParams.gainMagThresh == undefined){
     urlParams.gainMagThresh = 0.1;// = parseInt(urlParams.endYear);
  }
  
  addCollapse('sidebar-left','parameters-collapse-label','parameters-collapse-div','PARAMETERS','<i class="fa fa-sliders mr-1" aria-hidden="true"></i>',false,null,'Adjust parameters used to filter and sort LCMS products');
  addDualRangeSlider('parameters-collapse-div','Choose analysis year range:','urlParams.startYear','urlParams.endYear',minYear, maxYear, urlParams.startYear, urlParams.endYear, 1,'analysis-year-slider','null','Years of LCMS data to include for land cover, land use, loss, and gain')

  addSubCollapse('parameters-collapse-div','lt-params-label','lt-params-div','LANDTRENDR Params', '',false,'')
  addSubCollapse('parameters-collapse-div','ccdc-params-label','ccdc-params-div','CCDC Params', '',false,'')
  
  addRangeSlider('lt-params-div','Loss Magnitude Threshold','urlParams.lossMagThresh',-0.8,-0.05,urlParams.lossMagThresh,0.05,'loss-mag-thresh-slider','','The threshold to detect loss for each LANDTRENDR segment.  Any difference for a given segement less than this threshold will be flagged as loss') 
  addRangeSlider('lt-params-div','Gain Magnitude Threshold','urlParams.gainMagThresh',0.05,0.8,urlParams.gainMagThresh,0.05,'gain-mag-thresh-slider','','The threshold to detect gain for each LANDTRENDR segment.  Any difference for a given segement greater than this threshold will be flagged as gain') 
  addCheckboxes('lt-params-div','index-choice-checkboxes','Choose which indices to analyze','whichIndices2',{'blue':false,'green':false,'red':false,'nir':false,'swir1':false,'swir2':false,'NBR':true,'NDVI':false,'NDMI':false,'brightness':false,'greenness':false,'wetness':false,'tcAngleBG':false})
  
  addRangeSlider('ccdc-params-div','Change Probability Threshold','ccdcChangeProbThresh',0,1,0.8,0.1,'ccdc-change-prob-thresh-slider','','The CCDC probabibility threshold to detect change.  Any probability for a given break greater than this threshold will be flagged as change') 
  
  // $('#lt-params-div').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(staticTemplates.reRunButton);

  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div','LCMS BASE LEARNER DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,'LCMS DATA layers to view on map');
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');
  addCollapse('sidebar-left','download-collapse-label','download-collapse-div','DOWNLOAD DATA',`<i class="fa fa-cloud-download mr-1" aria-hidden="true"></i>`,false,``,'Download '+mode+' products for further analysis');
  
}else if(mode === 'LT'){
  canExport = true;
  startYear = 1984;endYear = 2020;startJulian = 152;endJulian = 273;

  var minYear = startYear;var maxYear = endYear;
  if(urlParams.startYear == null || urlParams.startYear == undefined){
      urlParams.startYear = startYear;// = parseInt(urlParams.startYear);
  }
  if(urlParams.endYear == null || urlParams.endYear == undefined){
     urlParams.endYear = endYear;// = parseInt(urlParams.endYear);
  }
  if(urlParams.startJulian == null || urlParams.startJulian == undefined){
      urlParams.startJulian = startJulian;// = parseInt(urlParams.startYear);
  }
  if(urlParams.endJulian == null || urlParams.endJulian == undefined){
     urlParams.endJulian = endJulian;// = parseInt(urlParams.endYear);
  }
  addCollapse('sidebar-left','parameters-collapse-label','parameters-collapse-div','PARAMETERS','<i class="fa fa-sliders mr-1" aria-hidden="true"></i>',false,null,'Adjust parameters used to filter and sort '+mode+' products');
  
  addSubCollapse('parameters-collapse-div','comp-params-label','comp-params-div','Landsat Composite Params', '',false,'');
  $('#comp-params-div').append(`<div class="dropdown-divider" ></div>`);
  addDualRangeSlider('comp-params-div','Choose analysis year range:','urlParams.startYear','urlParams.endYear',minYear, maxYear, urlParams.startYear, urlParams.endYear, 1,'analysis-year-slider2','null','Years of '+mode+' data to include.')
  
  addDualRangeSlider('comp-params-div','Choose analysis date range:','urlParams.startJulian','urlParams.endJulian',1, 365, urlParams.startJulian, urlParams.endJulian, 1,'julian-day-slider','julian','Days of year of '+mode+' data to include for land cover, land use, loss, and gain')
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
}else if(mode === 'TEST' || mode === 'FHP'){
  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div',mode+' DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,mode+' DATA layers to view on map');
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);

  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');

}else if(mode === 'geeViz'){
  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div',mode+' DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,mode+' DATA layers to view on map');
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');
  
}
else if(mode === 'STORM'){
  canExport = true;
  function refineFeatures(features,interpProps){
          var left = features.slice(0,features.length-1);
          var right = features.slice(1,features.length);
          var f = [left[0]];
          left.forEach(function(fl,i){
            var fr = right[i];
            var coordsL = fl.geometry.coordinates;
            var coordsR = fr.geometry.coordinates;

            
            var fm =  JSON.parse(JSON.stringify(fl));
            fm.geometry.coordinates = [(coordsL[0]+coordsR[0])/2.0,(coordsL[1]+coordsR[1])/2.0];
            
            interpProps.map(function(prop){

              var lProp =fl.properties[prop];
              var rProp = fr.properties[prop];
              var m = (rProp+lProp)/2.0
              fm.properties[prop] = m
            })
            f.push([fm,fr]);
          })
          f = f.flat();
          // console.log(f);
          // console.log(left);
        return f
        }

  addCollapse('sidebar-left','parameters-collapse-label','parameters-collapse-div','PARAMETERS','<i class="fa fa-sliders mr-1" aria-hidden="true"></i>',true,null,'Adjust parameters used to prepare storm outputs');
  
   $('#parameters-collapse-div').append(`
    <label>Download storm track from <a href="https://www.wunderground.com/hurricane" target="_blank">here</a>. Copy and paste the storm track coordinates into a text editor. Save the table. Then upload that table below. <a href="./geojson/michael.txt" download="michael.txt" >Download test data here.</a></label>
    <input class = 'file-input my-1' type="file" id="stormTrackUpload" name="upload"  style="display: inline-block;" title = "Download storm track from https://www.wunderground.com/hurricane">
    <hr>
    <label>Provide name for storm (optional):</label>
    <input rel="txtTooltip" title = 'Provide a name for the storm. The name of the provided storm track file will be used if left blank.'  type="user-selected-area-name" class="form-control" id="storm-name"  placeholder="Name your storm!" style='width:80%;'><hr>`)
   addRangeSlider('parameters-collapse-div','Refinement iterations','refinementIterations',0, 10, 5, 1,'refinement-factor-slider','null',"Specify number of iterations to perform a linear interpolation of provided track. A higher number is needed for tracks with fewer real observations")
   addRangeSlider('parameters-collapse-div','Max distance (km)','maxDistance',50, 500, 200, 50,'max-distance-slider','null',"Specify max distance in km from storm track to include in output")
   addRangeSlider('parameters-collapse-div','Min wind (mph)','minWind',0, 75, 30, 5,'min-wind-slider','null',"Specify min wind speed in mph to include in output")
      $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>
      <button class = 'btn' style = 'margin-bottom: 0.5em!important;' onclick = 'ingestStormTrack()' rel="txtTooltip" title = 'Click to ingest storm track and map damage'>Ingest Storm Track</button>
      <button class = 'btn' style = 'margin-bottom: 0.5em!important;' onclick = 'reRun()' rel="txtTooltip" title = 'Click to remove existing layers and exports'>Clear All Layers/Exports</button><br>`);
   
    function ingestStormTrack() {
      $('#summary-spinner').show();
          if(jQuery('#stormTrackUpload')[0].files.length > 0){
               
            var fr=new FileReader(); 
            fr.onload=function(){ 
                var rows = fr.result.split('\n');
                rows =rows.filter(row => row.split('\t').length > 5);
                // console.log(fr.result) 
                // console.log(rows)
                rows = rows.map(function(row){
                  row = row.split('\t');
                  var out = {};
                  out.type = "Feature";
                  out.geometry = {};
                  out.geometry.type = 'Point';
                  out.geometry.coordinates = [parseFloat(row[3]), parseFloat(row[2])]
                  
                  out.properties = {};
                  out.properties.lat = parseFloat(row[2]);
                  out.properties.lon = parseFloat(row[3]);
                  out.properties.wspd = parseFloat(row[4]);
                  out.properties.pres = parseFloat(row[5]);
                  out.properties.category = row[6];
                  out.properties.date = new Date(row[0] + ' ' + row[1]).getTime();
                  out.properties.year = new Date(row[0] + ' ' + row[1]).getFullYear()
                  return out
                })
                // var sa = ee.Image('projects/USFS/LCMS-NFS/CONUS-Ancillary-Data/LANDFIRE/LF_US_EVH_200').geometry();
                // rows = ee.FeatureCollection(rows).filterBounds(sa).getInfo().features;
                // console.log(rows)
                // Map2.addLayer(rows)
                var iterations = refinementIterations;
                while(iterations > 0 && rows.length < 1000){
                  console.log('Refining');
                  console.log(refinementIterations);
                  rows = refineFeatures(rows,['lat','lon','wspd','pres','date','year']);
                  console.log(rows.length);
                  iterations--
                }
                showMessage('Refinement finished','Refined '+ (refinementIterations-iterations).toString() +'/'+ refinementIterations.toString()+' iterations.\nTotal number of refined track points is: '+rows.length.toString())
                // rows = refineFeatures(rows,['lat','lon','wspd','pres','date','year']);

                var rowsLeft = rows.slice(0,rows.length-1);
                var rowsRight = rows.slice(1);
                var zipped = ee.List.sequence(0,rowsLeft.length-1).getInfo().map(function(i){
                  
                  var out = {};
                  out.type = "Feature";
                  out.geometry = rowsLeft[i].geometry;

                  out.properties = {};

                  out.properties.current = rowsLeft[i].properties;
                  out.properties.future = rowsRight[i].properties;
                  
                  return out
                })
                // console.log(zipped)
                // Map2.addLayer(rows)
                 $('#summary-spinner').slideUp();
                 // console.log(zipped)
                createHurricaneDamageWrapper(ee.FeatureCollection(zipped));
            } 
              
            fr.readAsText(jQuery('#stormTrackUpload')[0].files[0]);
            }else{
              $('#summary-spinner').hide();
              showMessage('No storm track provided','Please download storm track from <a href="https://www.wunderground.com/hurricane" target="_blank">here</a> . Copy and paste the storm track coordinates into a text editor. Save the table. Then upload that table above.')}


        } 
  //   $('#parameters-collapse-div').append(`<label>Provide storm track geoJSON:</label>
  //                                       <input rel="txtTooltip" title = 'Provide storm track geoJSON'  type="user-selected-area-name" class="form-control"  id="storm-track" placeholder="Provide storm track geoJSON" style='width:80%;'>`)
  
  
  // function ingestStormTrak(){
  //     var months = {
  //     'JAN' : '01',
  //     'FEB' : '02',
  //     'MAR' : '03',
  //     'APR' : '04',
  //     'MAY' : '05',
  //     'JUN' : '06',
  //     'JUL' : '07',
  //     'AUG' : '08',
  //     'SEP' : '09',
  //     'OCT' : '10',
  //     'NOV' : '11',
  //     'DEC' : '12'
  //     }
  //   if(jQuery('#stormTrackUpload')[0].files.length > 0){
  //     $('#summary-spinner').slideDown();
  //     convertToGeoJSON('stormTrackUpload').done(function(converted){

  //       converted.features = converted.features.map(function(f){
  //         f.properties.HR = parseFloat(f.properties['HHMM'].slice(0,2));
  //         f.properties.MN = parseFloat(f.properties['HHMM'].slice(2));
  //         if(Object.keys(months).indexOf(f.properties.MONTH) > -1){
  //           f.properties.MONTH = months[f.properties.MONTH]
  //         }
  //         return f
  //       })
  //       console.log('successfully converted to JSON');
  //       console.log(converted);
        


  //       var iterations =0;
  //       // var sa = ee.FeatureCollection("TIGER/2018/States").geometry();
  //       var sa = ee.Image('projects/USFS/LCMS-NFS/CONUS-Ancillary-Data/LANDFIRE/LF_US_EVH_200').geometry();
  //       // converted.features = ee.FeatureCollection(converted.features).filterBounds(sa).getInfo().features;
  //       for(iterations; iterations > 0; iterations--){
  //         converted.features = refineFeatures(converted.features,['LAT','LON','YEAR','MONTH','DAY','INTENSITY','MSLP','HR','MN']);
          
          
          
  //         //{"date": "Aug 16:18:00 GMT", "lat": 10.9, "lon": -25.4, "wspd": 20.0, "pres": 0.0, "FO": "O"}
        
  //       }
        
  //       var rows = converted.features.map(function(f){
         
  //         var props = f.properties;
  //         f.properties.date = new Date(props.YEAR,props.MONTH-1,props.DAY,props.HR,props.MN)
  //         f.properties.lat = props.LAT;
  //         f.properties.lon = props.LON;
  //         f.properties.wspd = props.INTENSITY
  //         f.properties.pres = props.MSLP
  //         f.properties.name = props.STORMNAME
  //         f.properties.year = props.YEAR;
  //         return f;//ee.Feature(f).buffer(10000)
  //       });
        
        
  //       createHurricaneDamageWrapper(rows,true);
  //       $('#summary-spinner').slideUp(); 
       
        
  //         })
  //   }else{showMessage('No storm track provided','Please select a .zip shapefile or a .geojson file to summarize across')}
  // }                     
  // $('#parameters-collapse-div').append(`<label>Provide storm track geoJSON:</label>
  //                                       <input rel="txtTooltip" title = 'Provide storm track geoJSON'  type="user-selected-area-name" class="form-control" value = '${JSON.stringify(rows)}' id="storm-track" placeholder="Provide storm track geoJSON" style='width:80%;'>`)
  
  // $('#parameters-collapse-div').append(`<label>Provide name for storm (optional):</label>
  //                                       <input rel="txtTooltip" title = 'Provide a name for the storm. A default one will be provided if left blank.'  type="user-selected-area-name" class="form-control" id="storm-name" value = 'Michael' placeholder="Name your storm!" style='width:80%;'>`)
  // addRangeSlider('parameters-collapse-div','Choose storm year','stormYear',1980, 2030, 2018, 1,'storm-year-slider','null',"Specify year of storm")
  // $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  // $('#parameters-collapse-div').append(staticTemplates.reRunButton);
  addCollapse('sidebar-left','layer-list-collapse-label','layer-list-collapse-div',mode+' DATA',`<img style = 'width:1.1em;' class='image-icon mr-1' src="images/layer_icon.png">`,true,null,mode+' DATA layers to view on map');
  $('#layer-list-collapse-div').append(`<div id="layer-list"></div>`);
  addCollapse('sidebar-left','tools-collapse-label','tools-collapse-div','TOOLS',`<i class="fa fa-gear mr-1" aria-hidden="true"></i>`,false,'','Tools to measure and chart data provided on the map');
  addCollapse('sidebar-left','download-collapse-label','download-collapse-div','DOWNLOAD DATA',`<i class="fa fa-cloud-download mr-1" aria-hidden="true"></i>`,false,``,'Download '+mode+' products for further analysis');
 
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
/////////////////////////////////////////////////////////////////
//Construct tool options for different modes
 

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
// if(mode !== 'STORM'){
  addSubAccordianCard('tools-accordian','pixel-chart-label','pixel-chart-div','Query '+mode+' Time Series',staticTemplates.pixelChartDiv,false,`toggleTool(toolFunctions.pixel.chart)`,staticTemplates.pixelChartTipHover);
  addDropdown('pixel-chart-div','pixel-collection-dropdown','Choose which '+mode+' time series to chart','whichPixelChartCollection','Choose which '+mode+' time series to chart.');
 
// }
// $('#pixel-chart-div').append(staticTemplates.showChartButton);
// addAccordianContainer('area-tools-collapse-div','area-tools-accordian');
if(mode === 'geeViz'){
  $('#pixel-chart-label').remove();
  $('#share-button').remove();
}

if(mode === 'LCMS' || mode === 'MTBS'|| mode === 'lcms-base-learner' || mode === 'FHP'){
  $('#tools-accordian').append(`<h5 class = 'pt-2' style = 'border-top: 0.1em solid black;'>Area Tools</h5>`);
  addSubCollapse('tools-accordian','area-chart-params-label','area-chart-params-div','Area Tools Params', '',false,'')
  
  // $('#tools-accordian').append(`<div class="dropdown-divider" ></div>`);
  addDropdown('area-chart-params-div','area-collection-dropdown','Choose which '+mode+' product to summarize','whichAreaChartCollection','Choose which '+mode+' time series to summarize.');
  // $('#area-chart-params-div').append(`<div class="dropdown-divider" ></div>`);
  $('#parameters-collapse-div').append(`<div class="dropdown-divider" ></div>`);
  addMultiRadio('area-chart-params-div','area-summary-format','Area Units','areaChartFormat',{"Percentage":true,"Acres":false,"Hectares":false})
  $('#area-summary-format').prop('title','Choose how to summarize area- as a percentage of the area, acres, or hectares.')
  addSubAccordianCard('tools-accordian','user-defined-area-chart-label','user-defined-area-chart-div','User-Defined Area',staticTemplates.userDefinedAreaChartDiv,false,`toggleTool(toolFunctions.area.userDefined)`,staticTemplates.userDefinedAreaChartTipHover);
  addSubAccordianCard('tools-accordian','upload-area-chart-label','upload-area-chart-div','Upload an Area',staticTemplates.uploadAreaChartDiv,false,'toggleTool(toolFunctions.area.shpDefined)',staticTemplates.uploadAreaChartTipHover);
  // addSubAccordianCard('tools-accordian','select-area-dropdown-chart-label','select-area-dropdown-chart-div','Select an Area from Dropdown',staticTemplates.selectAreaDropdownChartDiv,false,'toggleTool(toolFunctions.area.selectDropdown)',staticTemplates.selectAreaDropdownChartTipHover);
  addSubAccordianCard('tools-accordian','select-area-interactive-chart-label','select-area-interactive-chart-div','Select an Area on Map',staticTemplates.selectAreaInteractiveChartDiv,false,'toggleTool(toolFunctions.area.selectInteractive)',staticTemplates.selectAreaInteractiveChartTipHover);

  addShapeEditToolbar('user-defined-edit-toolbar', 'user-defined-area-icon-bar','undoUserDefinedAreaCharting()','restartUserDefinedAreaCarting()')
  addColorPicker('user-defined-area-icon-bar','user-defined-color-picker','updateUDPColor',udpOptions.strokeColor);

  addShapeEditToolbar('select-features-edit-toolbar', 'select-area-interactive-chart-icon-bar','removeLastSelectArea()','clearSelectedAreas()','Click to unselect most recently selected polyogn','Click to clear all selected polygons');
}
//Add some logos for different modes
if(mode === 'MTBS' || mode === 'Ancillary'){
  $('#contributor-logos').prepend(`<a href="https://www.usgs.gov/" target="_blank" >
                                    <img src="images/usgslogo.png" class = 'image-icon-bar'  href="#"  rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="Click to learn more about the US Geological Survey">
                                  </a>`)
  $('#contributor-logos').prepend(`<a href="https://www.mtbs.gov/" target="_blank" >
                                    <img src="images/mtbs-logo.png" class = 'image-icon-bar'  href="#"  rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="Click to learn more about the US Geological Survey">
                                  </a>`)
}
//Handle exporting if chosen
if(canExport){
  // console.log('here')
   $('#download-collapse-div').append(staticTemplates.exportContainer);
   if(localStorage.export_crs !== undefined && localStorage.export_crs !== null && localStorage.export_crs.indexOf('EPSG') > -1){
    $('#export-crs').val(localStorage.export_crs)
  }else{localStorage.export_crs = $('#export-crs').val()};
   function cacheCRS(){
    localStorage.export_crs = $('#export-crs').val();
   }
   if(mode === 'STORM'){
     $('#export-area-drawing-div').append(`<hr>
                                            <button class = 'btn' onclick = 'addTrackBounds()' rel="txtTooltip" title = 'Add bounds of storm track for export area.'><i class="pr-1 fa fa-square-o" aria-hidden="true"></i> Use storm track bound as area to download</button>
                                            `)
     $('#export-button-div').append(`<hr>`);
     addRangeSlider('export-button-div','Quick look spatial resolution','quickLookRes',1200, 6000, 3000, 300,'quick-look-res-slider','null',"Specify spatial resolution for quick look downloads.")
     $('#export-button-div').append(`<button class = 'btn' onclick = 'downloadQuickLooks()' rel="txtTooltip" title = 'Quickly download outputs at coarse resolution'><i class="pr-1 fa fa-cloud-download" aria-hidden="true"></i>Download Quick Look Outputs</button>
                                            `)
     
   }
}

if(urlParams.showSidebar === undefined || urlParams.showSidebar === null){
  urlParams.showSidebar = 'true'
}

function toggleSidebar(){
  $('#sidebar-left').toggle('collapse');
  if(urlParams.showSidebar === 'false'){
    urlParams.showSidebar = 'true'
  }else{
    urlParams.showSidebar = 'false'
  }
};
if(urlParams.showSidebar === 'false'){
  $('#sidebar-left').hide();
}


