/*Templates for elements and various functions to create more pre-defined elements*/
/////////////////////////////////////////////////////////////////////
/*Provide titles to be shown for each mode*/
var  titles = {
	'LCMS': {
		    leftWords: 'LCMS',
		    centerWords: 'DATA',
		    rightWords:'Explorer',
		    title:'LCMS Data Explorer'
			},
    'lcms-base-learner': {
            leftWords: 'LCMS',
            centerWords: 'Base-Learner',
            rightWords:'Explorer',
            title:'LCMS Base Learner Explorer'
            },
	'Ancillary': {
		    leftWords: 'Ancillary',
		    centerWords: 'DATA',
		    rightWords:'Viewer',
		    title:'TimeSync Ancillary Data Viewer'
			},
    'LT': {
            leftWords: 'LANDTRENDR',
            centerWords: 'DATA',
            rightWords:'Viewer',
            title:'LANDTRENDR Data Viewer'
            },
    'MTBS': {
            leftWords: 'MTBS',
            centerWords: 'DATA',
            rightWords:'Explorer',
            title:'TimeSync Ancillary Data Viewer'
            },
    'TEST': {
            leftWords: 'TEST',
            centerWords: 'DATA',
            rightWords:'Explorer',
            title:'TEST Data Viewer'
            },
    'FHP' : {
            leftWords: 'FHP',
            centerWords: 'DATA',
            rightWords:'Explorer',
            title:'Forest Health Protection Data Viewer'
            },
    'geeViz': {
            leftWords: 'geeViz',
            centerWords: 'DATA',
            rightWords:'Viewer',
            title:'geeViz Data Viewer'
            }     
}
/////////////////////////////////////////////////////////////////////
/*Add anything to head not already there*/
$('head').append(`<title>${titles[mode].title}</title>`);
$('head').append(`<script type="text/javascript" src="./js/gena-gee-palettes.js"></script>`);
var topBannerParams = titles[mode];
var  studyAreaDropdownLabel = `<h5 class = 'teal p-0 caret nav-link dropdown-toggle ' id = 'studyAreaDropdownLabel'>Bridger-Teton National Forest</h5> `;
/////////////////////////////////////////////////////////////////////
//Provide a bunch of templates to use for various elements
var staticTemplates = {
	map:`<div onclick = "$('#study-area-list').hide();" class = 'map' id = 'map'> </div>`,

	mainContainer: `<div class = 'container main-container' id = 'main-container'></div>`,
	sidebarLeftToggler:`<div href="#" class="fa fa-bars m-0 px-1 py-2 m-0 sidebar-toggler " onclick = 'toggleSidebar()'></div>`,

    sidebarLeftContainer: `
						<div onclick = "$('#study-area-list').hide();" class = 'col-sm-7 col-md-5 col-lg-4 col-xl-3 sidebar  p-0 m-0 flexcroll  ' id = 'sidebar-left-container' >
					        <div id = 'sidebar-left-header'></div>
                            
					        <div id = 'sidebar-left'></div>
					    </div>`,

	geeSpinner : `<img rel="txtTooltip" data-toggle="tooltip"  title="Background processing is occurring in Google Earth Engine"id='summary-spinner' class="fa fa-spin" src="images/GEE_logo_transparent.png" alt="" style='position:absolute;display: none;right:40%; bottom:40%;width:8rem;height:8rem;z-index:10000000;'>`,


	exportContainer:`<div class = 'dropdown-divider'></div>
                    <div class = 'py-2' id = 'export-list-container'>
                        <h5>Choose which images to export:</h5>
                        <div class = 'py-2' id="export-list"></div>
                        <div class = 'dropdown-divider'></div>
                        <div class = 'pl-3'>
                            <form class="form-inline" title = 'Provide projection. Web mercator: "EPSG:4326", USGS Albers: "EPSG:5070", WGS 84 UTM Northern Hemisphere: "EPSG:326" + zone number (e.g. zone 17 would be EPSG:32617), NAD 83 UTM Northern Hemisphere: "EPSG:269" + zone number (e.g. zone 17 would be EPSG:26917) '>
                              <label for="export-crs">Projection: </label>
                              <div class="form-group pl-1">
                                <input type="text" id="export-crs" oninput = 'cacheCRS()' name="rg-from" value="EPSG:4326" class="form-control">
                              </div> 
                              
                            </form>
                            <div class = 'py-2'>
                                <button class = 'btn' onclick = 'selectExportArea()' rel="txtTooltip" title = 'Draw polygon by clicking on map. Double-click to complete polygon, press ctrl+z to undo most recent point, press Delete or Backspace to start over.'><i class="pr-1 fa fa-pencil" aria-hidden="true"></i> Draw area to download</button>
                                <a href="#" onclick = 'undoExportArea()' rel="txtTooltip" title = 'Click to undo last drawn point (ctrl z)'><i class="btn fa fa-undo"></i></a>
                                <a href="#" onclick = 'deleteExportArea()' rel="txtTooltip" title = 'Click to clear current drawing'><i class="btn fa fa-trash"></i></a>
                            </div>
                            <div class = 'dropdown-divider'></div>
                            <div class = 'pt-1 pb-3'>
                                <button class = 'btn' onclick = 'exportImages()' rel="txtTooltip" title = 'Click to export selected images across selected area'><i class="pr-1 fa fa-cloud-download" aria-hidden="true"></i>Export Images</button>
                                <button class = 'btn' onclick = 'cancelAllTasks()' rel="txtTooltip" title = 'Click to cancel all active exports'></i>Cancel All Exports</button>
                                <span style = 'display:none;' class="fa-stack fa-2x py-0" id='export-spinner' data-toggle="tooltip"  title="">
						    		<img rel="txtTooltip"   class="fa fa-spin fa-stack-2x" src="images/GEE_logo_transparent.png" alt="" style='width:2em;height:2em;'>
						   			<strong id = 'export-count'  class="fa-stack-1x" style = 'padding-left: 0.2em;padding-top: 0.1em;cursor:pointer;'></strong>
								</span>
                            </div>
                            
                        </div>
                        
                    </div>`,

	topBanner:`<h1 id = 'title-banner' data-toggle="tooltip" title="" class = 'gray pl-4 pb-0 m-0 text-center' style="font-weight:100;font-family: 'Roboto';">${topBannerParams.leftWords}<span class = 'gray' style="font-weight:1000;font-family: 'Roboto Black', sans-serif;"> ${topBannerParams.centerWords} </span>${topBannerParams.rightWords} </h1>
		        
		        `,
	studyAreaDropdown:`<li   id = 'study-area-dropdown' class="nav-item dropdown navbar-dark navbar-nav nav-link p-0 col-12  "  data-toggle="dropdown">
		                <h5 href = '#' onclick = "$('#sidebar-left').show('fade');$('#study-area-list').toggle();" class = 'teal p-0 caret nav-link dropdown-toggle ' id='study-area-label'  ></h5> 
		                <div class="dropdown-menu" id="study-area-list"  >  
		                </div>
		            </li>
			    `,
	placesSearchDiv:`<div class="input-group px-4 pb-2 text-center"">
			            <div class="input-group-prepend">


                            <button onclick = 'getLocation()' title = 'Click to center map at your location' class=" btn input-group-text bg-white search-box pr-1 pl-2" id="get-location-button"><i class="fa fa-map-marker text-black "></i></button>
	    					<button onclick = 'TweetThis()' title = 'Click to share your current view' class=" btn input-group-text bg-white search-box pr-1 pl-2" id="share-button"><i class="fa fa-share-alt teal "></i></button>
                            
                            <span class="input-group-text bg-white search-box" id="search-icon"><i class="fa fa-search text-black "></i></span>
	  					</div>

			            <input id = 'pac-input' class="form-control bg-white search-box" type="text" placeholder="Search Places">
                        </div>
                        <p class = 'mt-0 mb-1' style = 'display:none;font-size:0.8em;font-weight:bold' id = 'time-lapse-year-label'></p>`,
	introModal:{'LCMS':`<div class="modal fade "  id="introModal" tabindex="-1" role="dialog" >
                <div class="modal-dialog modal-md " role="document">
                    <div class="modal-content text-dark" style = 'background-color:rgba(230,230,230,0.95);'>
                        <button type="button" class="close p-2 ml-auto text-dark" data-dismiss="modal">&times;</button>
                        <div class = 'modal-header'>
                            <h3 class="mb-0 ">Welcome to the Landscape Change Monitoring System (LCMS) Data Explorer!</h3>
                        </div>

                        <div class="modal-body" id = 'introModal-body'>
                            <p class="pb-3 ">LCMS is a landscape change detection program developed by the USDA Forest Service. This application is designed to provide a visualization of the Landscape Change products, related geospatial data, and provide a portal to download the data.</p>
                        	<button class = 'btn' onclick = 'downloadTutorial()' rel="txtTooltip" data-toggle="tooltip" title="Click to launch tutorial that explains how to utilize the Data Explorer">Launch Tutorial</button>
                        </div>
                        <div class = 'modal-footer' id = 'introModal-footer'>
                        
						<div class="form-check  mr-0">
                                <input type="checkbox" class="form-check-input" id="dontShowAgainCheckbox"   name = 'dontShowAgain' value = 'true'>
                                <label class=" text-uppercase form-check-label " for="dontShowAgainCheckbox" >Don't show again</label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>`,
            'Ancillary':`<div class="modal fade "  id="introModal" tabindex="-1" role="dialog" >
                <div class="modal-dialog modal-md " role="document">
                    <div class="modal-content text-dark" style = 'background-color:rgba(230,230,230,0.95);'>
                        <button type="button" class="close p-2 ml-auto text-dark" data-dismiss="modal">&times;</button>
                        <div class = 'modal-header'>
                            <h3 class="mb-0 ">Welcome to the TimeSync Ancillary Data Viewer!</h3>
                        </div>

                        <div class="modal-body" id = 'introModal-body'>
                            <p class="pb-2 ">This viewer is intended to provide an efficient way of looking at ancillary data to help with responses for the TimeSync tool.</p>
                        	
                        </div>
                        <div class = 'modal-footer' id = 'introModal-footer'>
                      
						<div class="form-check  mr-0">
                                <input type="checkbox" class="form-check-input" id="dontShowAgainCheckbox"   name = 'dontShowAgain' value = 'true'>
                                <label class=" text-uppercase form-check-label " for="dontShowAgainCheckbox" >Don't show again</label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>`,
            'LT':`<div class="modal fade "  id="introModal" tabindex="-1" role="dialog" >
                <div class="modal-dialog modal-md " role="document">
                    <div class="modal-content text-dark" style = 'background-color:rgba(230,230,230,0.95);'>
                        <button type="button" class="close p-2 ml-auto text-dark" data-dismiss="modal">&times;</button>
                        <div class = 'modal-header'>
                            <h3 class="mb-0 ">Welcome to the Landsat Data Explorer!</h3>
                        </div>

                        <div class="modal-body" id = 'introModal-body' >
                            <p class="pb-2 ">This tool is intended to allow for quick exploration of the Landsat time series and long-term trends. Any area on earth can be mapped.</p>
                            
                        </div>
                        <div class = 'modal-footer' id = 'introModal-footer'>
                      
                        <div class="form-check  mr-0">
                                <input type="checkbox" class="form-check-input" id="dontShowAgainCheckbox"   name = 'dontShowAgain' value = 'true'>
                                <label class=" text-uppercase form-check-label " for="dontShowAgainCheckbox" >Don't show again</label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>`,
            'MTBS':`<div class="modal fade "  id="introModal" tabindex="-1" role="dialog" >
                <div class="modal-dialog modal-md " role="document">
                    <div class="modal-content text-dark" style = 'background-color:rgba(230,230,230,0.95);'>
                        <button type="button" class="close p-2 ml-auto text-dark" data-dismiss="modal">&times;</button>
                        <div class = 'modal-header'>
                            <h3 class="mb-0 ">Welcome to the MTBS Data Explorer!</h3>
                        </div>

                        <div class="modal-body" id = 'introModal-body'>
                            <p class="pb-2 ">This tool is intended to allow for interactive exploration of the Monitoring Trends in Burn Severity (MTBS) data record.</p>
                            
                        </div>
                        <div class = 'modal-footer' id = 'introModal-footer'>
                      
                        <div class="form-check  mr-0">
                                <input type="checkbox" class="form-check-input" id="dontShowAgainCheckbox"   name = 'dontShowAgain' value = 'true'>
                                <label class=" text-uppercase form-check-label " for="dontShowAgainCheckbox" >Don't show again</label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>`
        },
	bottomBar:`<div class = 'bottombar'  id = 'bottombar' >
                   
        			<span class = 'px-2'  id='current-tool-selection' rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="Any tool that is currently active is shown here."></span>
        			<span class = 'px-2'  rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="All map layers are dynamically requested from Google Earth Engine.  The number of outstanding requests is shown here.">Queue length for maps from GEE: <span id='outstanding-gee-requests'>0</span></span>
                    <span class = 'px-2'  rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="The number of outstanding map layers currently loading tiles.">Number of map layers loading tiles: <span id='number-gee-tiles-downloading'>0</span></span>
                    <span class = 'px-2'  id='current-mouse-position'  ></span>
                    <span id = 'contributor-logos' > 
                        <a href="http://www.fs.fed.us//" target="_blank">
                            <img src="images/usfslogo.png" class = 'image-icon-bar'  href="#"   title="Click to learn more about the US Forest Service">
                        </a>
                        <a href="https://www.fs.fed.us/gstc/" target="_blank">
                            <img src="images/GTAC_Logo.png" class = 'image-icon-bar' alt="GTAC Logo"  href="#"  title="Click to learn more about the Geospatial Technology and Applications Center (GTAC)">
                        </a>
                        <a href="https://www.redcastleresources.com/" target="_blank">
                            <img src="images/RCR-logo.jpg"  class = 'image-icon-bar'alt="RedCastle Inc. Logo"  href="#"   title="Click to learn more about RedCastle Resources Inc.">
                        </a>
                        <a href="https://earthengine.google.com/" target="_blank">
                            <img src="images/GEE.png"   class = 'image-icon-bar' alt="Powered by Google Earth Engine"  href="#" title="Click to learn more about Google Earth Engine">
                        </a>
                    </span>

                    
                 
                    
            </div>`,
        walkThroughPopup:`
                    
                    	<div class = 'walk-through-popup'>
                          
                            <div id = 'walk-through-popup-content' class = 'walk-through-popup-content'></div>
	                       		<div class = 'dropdown-divider'></div>
		                        <div class="icon-bar py-1 ">
								  <a onclick = 'previousWalkThrough()' title = 'Previous tutorial slide'><i class="fa fa-chevron-left text-black"></i></a>
								  <a onclick = 'nextWalkThrough()'  title = 'Next tutorial slide'><i class="fa fa-chevron-right text-black"></i></a>
								  <a id = 'walk-through-popup-progress'></a>
                                  <a onclick = 'removeWalkThroughCollapse()' style = 'float:right;'  title = 'Turn off Walk-Through'><i class="fa fa-stop text-black" aria-hidden="true"></i></a>
                                  
                                </div>
						</div>
	                       
                    	`,
        studyAreaDropdownButtonEnabledTooltip:`Choose your study area`,
        studyAreaDropdownButtonDisabledTooltip:`Still waiting on previous map layer requests. Can change study area once the previous requests are finished.`,
        reRunButtonEnabledTooltip:`Once finished changing parameters, press this button to refresh map layers`,
        reRunButtonDisabledTooltip:`Still waiting on previous map layer requests. Can re-submit once the previous requests are finished.`,
        reRunButton:`<button id = 'reRun-button' onclick = 'reRun()' class = 'mb-1 ml-1 btn ' href="#" rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="">Submit</button>`,
        downloadDiv :`<div class = 'py-2'>
                        <a id = 'product-descriptions' target = '_blank'>Detailed Product Description</a>
        				<div class = 'dropdown-divider'></div>
                        <label  title = 'Choose from dropdown below to download LCMS products. There can be a small delay before a download will begin, especially over slower networks.' for="downloadDropdown">Select product to download:</label>
    					<select class="form-control" id = "downloadDropdown" onchange = "downloadSelectedArea()""></select>
    				 </div>`,
        supportDiv :`<div class = 'p-0 pb-2' >
        				<a style = 'color:var(--deep-brown-100)!important;' rel="txtTooltip" data-toggle="tooltip" title = "Send us an E-mail" href = "mailto: sm.fs.lcms@usda.gov">
        					<br>
        					<i class="fa fa-envelope" style = 'color:var(--deep-brown-100)!important;'aria-hidden="true"></i>
        					Please contact the LCMS help desk <span href = "mailto: sm.fs.lcms@usda.gov">(sm.fs.lcms@usda.gov)</span> if you have questions or comments about LCMS products, the LCMS program, or feedback on the LCMS Data Explorer</a>
        				<div class="dropdown-divider"></div>
                        <button class = 'btn' onclick = 'downloadTutorial()' rel="txtTooltip" data-toggle="tooltip" title="Click to launch tutorial that explains how to utilize the Data Explorer">Launch Tutorial</button>
        				<div class="dropdown-divider"></div>
                        <label class = 'mt-2'>If you turned off tool tips, but want them back:</label>
        				<button  class = 'btn  bg-black' onclick = 'showToolTipsAgain()'>Show tooltips</button>
        			</div>`,
        walkThroughButton:`<div class = pb-2>
                            <div class="dropdown-divider"></div>
                            <label class = 'mt-2'>Run a walk-through of the ${mode} Data Explorer's features</label>
                            <button  class = 'btn  bg-black' onclick = 'toggleWalkThroughCollapse()' title = 'Run interactive walk-through of the features of the ${mode} Data Explorer'>Run Walk-Through</button>
                          </div>`,
        distanceDiv : `Click on map to measure distance`,
        distanceTip : "Click on map to measure distance. Press <kbd>ctrl+z</kbd> to undo most recent point. Double-click, press <kbd>Delete</kbd>, or press <kbd>Backspace</kbd> to clear measurment and start over.",
        areaDiv : `Click on map to measure area<variable-radio onclick1 = 'updateArea()' onclick2 = 'updateArea()' var='metricOrImperialArea' title2='' name2='Metric' name1='Imperial' value2='metric' value1='imperial' type='string' href="#" rel="txtTooltip" data-toggle="tooltip" data-placement="top" title='Toggle between imperial or metric units'></variable-radio>`,
        areaTip : "Click on map to measure area. Double-click to complete polygon, press <kbd>ctrl+z</kbd> to undo most recent point, press <kbd>Delete</kbd> or <kbd>Backspace</kbd> to start over. Any number of polygons can be defined by repeating this process.",
        queryDiv : "<div>Double-click on map to query values of displayed layers at that location</div>",
        queryTip : 'Double-click on map to query the values of the visible layers.  Only layers that are turned on will be queried.',
        pixelChartDiv : `<div>Double-click on map to query ${mode} data time series<br></div>`,
        pixelChartTip : 'Double-click on map to look at the full time series of '+mode+' outputs for a pixel.',
        userDefinedAreaChartDiv : `<div  id="user-defined" >
                                            
                                            <label>Provide name for area selected for charting (optional):</label>
                                            <input rel="txtTooltip" title = 'Provide a name for your chart. A default one will be provided if left blank.'  type="user-defined-area-name" class="form-control my-1" id="user-defined-area-name" placeholder="Name your charting area!" style='width:80%;'>
                                            <div class = 'dropdown-divider'></div>
                                            <div>Total area selected: <i id = "user-defined-area-spinner" style = 'display:none;' class="fa fa-spinner fa-spin text-dark pl-1"></i></div>
                                            <div id = 'user-defined-features-area' class = 'select-layer-name'>0 hectares / 0 acres</div>
                                            <div id = 'user-defined-edit-toolbar'></div>
                                            <button class = 'btn' style = 'margin-bottom: 0.5em!important;' onclick = 'chartUserDefinedArea()' rel="txtTooltip" title = 'Click to summarize across drawn polygons'>Chart Selected Areas</button>
                                
        		            			</div>
                                	</div>`,
        showChartButton:`<div class = 'py-2'>
                                <button onclick = "$('#chart-modal').modal()" class = 'btn bg-black' rel="txtTooltip" data-toggle="tooltip" title = "If you turned off the chart, but want to show it again" >Turn on Chart</button>
                                </div>`,
        userDefinedAreaChartTip : 'Click on map to select an area to summarize '+mode+' products across. Press <kbd>ctrl+z</kbd> to undo most recent point.  Press <kbd>Delete</kbd>, or press <kbd>Backspace</kbd> to start over. Double-click to finish polygon. Any number of polygons can be defined by repeating this process. Once finished defining areas, click on the <kbd>Chart Selected Areas</kbd> button to create chart.',

        uploadAreaChartDiv : `<div class = 'dropdown-divider'></div>
                                <label>Choose a zipped shapefile or geoJSON file to summarize across.  Then hit "Summarize across chosen file" button below to produce chart.</label>
                                <input class = 'file-input my-1' type="file" id="areaUpload" name="upload" accept=".zip,.geojson,.json" style="display: inline-block;">
                                <div class = 'dropdown-divider'></div>
                                <button class = 'btn' style = 'margin-bottom: 0.5em!important;' onclick = 'runShpDefinedCharting()' rel="txtTooltip" title = 'Click to summarize across chosen .zip shapefile or .geojson.'>Chart across chosen file</button>
                                `,
        uploadAreaChartTip : 'Select zipped shapefile (zip into .zip all files related to the shapefile) or a single .geojson file to summarize products across.',
        selectAreaDropdownChartDiv : `<i rel="txtTooltip" data-toggle="tooltip"  title="Selecting pre-defined summary areas for chosen study area" id = "select-area-spinner" class="text-dark px-2 fa fa-spin fa-spinner"></i>
                            <select class = 'form-control' style = 'width:100%;'  id='forestBoundaries' onchange='chartChosenArea()'></select>
                            <div class = 'dropdown-divider'></div>`,
        selectAreaDropdownChartTip : 'Select from pre-defined areas to summarize products across.',
        selectAreaInteractiveChartDiv : `<div>Choose from layers below and click on map to select areas to include in chart</div>
                                        <div class = 'dropdown-divider'></div>
                                        <label>Provide name for area selected for charting (optional):</label>
                                        <input rel="txtTooltip" title = 'Provide a name for your chart. A default one will be provided if left blank.'  type="user-selected-area-name" class="form-control" id="user-selected-area-name" placeholder="Name your charting area!" style='width:80%;'>
                                        <div class = 'dropdown-divider'></div>  
                                        <div id="area-charting-select-layer-list"></div>
                                        <div class = 'dropdown-divider'></div>
                                        <div>Selected area names:</div>
                                        <i id = "select-features-list-spinner" style = 'display:none;' class="fa fa-spinner fa-spin text-dark"></i>
                                        <li class = 'selected-features-list' id = 'selected-features-list'></li>
                                        <div class = 'dropdown-divider'></div>
                                        <div>Total area selected: <i id = "select-features-area-spinner" style = 'display:none;' class="fa fa-spinner fa-spin text-dark pl-1"></i></div>
                                        <div id = 'selected-features-area' class = 'select-layer-name'>0 hectares / 0 acres</div>
                                        <div id = 'select-features-edit-toolbar'></div>
                                        <button class = 'btn' onclick = 'chartSelectedAreas()'>Chart Selected Areas</button>
                                        <div class = 'dropdown-divider'></div>`,
        selectAreaInteractiveChartTip : 'Select from pre-defined areas on map to summarize products across.',
        shareButtons : `    
                        
                        <!-- Email -->
                        <a title = 'Share via E-mail' onclick = 'TweetThis("mailto:?Subject=USDA Forest Service Landscape Change Monitoring System&amp;Body=I%20saw%20this%20and%20thought%20you%20might%20be%20interested.%20 ","",true)'>
                            <img class = 'image-icon-bar' src="./images/email.png" alt="Email" />
                        </a>

                        <!-- Reddit -->
                        <a title = 'Share on Reddit' onclick = 'TweetThis("http://reddit.com/submit?url=","&amp;title=USDA Forest Service Landscape Change Monitoring System",true)' >
                            <img class = 'image-icon-bar' src="./images/reddit.png" alt="Reddit" />
                        </a>

                         <!-- Twitter -->
                        <a title = 'Share on Twitter' onclick = 'TweetThis("https://twitter.com/share?url=","&amp;text=USDA Forest Service Landscape Change Monitoring System&amp;hashtags=USFSLCMS",true)' >
                            <img class = 'image-icon-bar' src="./images/twitter.png" alt="Twitter" />
                        </a>

                        <!-- Facebook -->
                        <a  title = 'Share on Facebook' onclick = 'TweetThis("http://www.facebook.com/sharer.php?u=","",true)' >
                            <img class = 'image-icon-bar' src="./images/facebook.png" alt="Facebook" />
                        </a>
                            
                        
                        `



        
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Go through each tip and remove kbd tag for shoing in hover titles
Object.keys(staticTemplates).filter(word => word.indexOf('Tip') > -1).map(function(t){
	var tip = staticTemplates[t].replaceAll(`<kbd>`,``);
	tip = tip.replaceAll(`</kbd>`,``);
	staticTemplates[t+'Hover'] = tip
})
//////////////////////////////////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////////////////////////////
//Start functions that add/remove and control elements
//////////////////////////////////////////////////////////////////////////////////////////////
//Center map on user's location
//Adapted from https://www.w3schools.com/html/html5_geolocation.asp
function getLocation() {
    if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(showPosition, showLocationError);
  } else { 
    showMessage('Cannot acquire location','Geolocation is not supported by this browser.');
  }
}
function showPosition(position) {
    var pt = {lng:position.coords.longitude,lat:position.coords.latitude};
    var locationMarker  = new google.maps.Marker({
              map: map,
              position: pt,
              icon: {
                  path: google.maps.SymbolPath.CIRCLE,
                  scale: 5,
                  strokeColor: '#FF0',
                  map: map
                }
            });
    map.setCenter(pt);
    map.setZoom(10);
    showMessage('Acquired location',"Latitude: " + position.coords.latitude + 
  "<br>Longitude: " + position.coords.longitude)
  
}
function showLocationError(error) {
    switch(error.code) {
    case error.PERMISSION_DENIED:
        showMessage('Cannot acquire location','User denied the request for Geolocation.');
        break;
    case error.POSITION_UNAVAILABLE:
        showMessage('Cannot acquire location','Location information is unavailable.');
        break;
    case error.TIMEOUT:
        showMessage('Cannot acquire location','The request to get user location timed out.');
        break;
    case error.UNKNOWN_ERROR:
        showMessage('Cannot acquire location','An unknown error occurred.');
        break;
  }
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Function to add a Bootstrap dropdown
function addDropdown(containerID,dropdownID,dropdownLabel,variable,tooltip){
	if(tooltip === undefined || tooltip === null){tooltip = ''}
	$('#' + containerID).append(`<div id="${dropdownID}-container" class="form-group" data-toggle="tooltip" data-placement="top" title="${tooltip}">
								  <label for="${dropdownID}">${dropdownLabel}:</label>
								  <select class="form-control" id="${dropdownID}"></select>
								</div>`)
	
	  $("select#"+dropdownID).on("change", function(value) {
	  	eval(`window.${variable} = $(this).val()`);
	  });
	
}
//Function to add an item to a dropdown
function addDropdownItem(dropdownID,label,value,tooltip){
    if(tooltip === undefined || tooltip === null){tooltip = ''};
	$('#'+dropdownID).append(`<option title = '${tooltip}' value = "${value}">${label}</option>`)
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Function to add a standard shape editor toolbar
function addShapeEditToolbar(containerID, toolbarID,undoFunction,restartFunction,undoTip,deleteTip){
    if(undoTip === undefined || undoTip === null){undoTip = 'Click to undo last drawn point (ctrl z)'};
    if(deleteTip === undefined || deleteTip === null){deleteTip = 'Click to clear current drawing and start a new one (Delete, or Backspace)'};
	$('#'+containerID).append(`<div class = 'dropdown-divider'></div>
								    <div id = '${toolbarID}' class="icon-bar ">
								    	<a href="#" onclick = '${undoFunction}' rel="txtTooltip" title = '${undoTip}''><i class="btn fa fa-undo"></i></a>
									  	<a href="#" onclick = '${restartFunction}' rel="txtTooltip" title = '${deleteTip}'><i class="btn fa fa-trash"></i></a>
									</div>
									<div class = 'dropdown-divider'></div>`);
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Function to set up a custom toggle radio
const setRadioValue =function(variable,value){
	console.log(value)
	window[variable] = value;
	};
function getRadio(id,label,name1,name2,variable,value1,value2){
	return `<div class = 'container'><div id = '${id}-row' class = 'row'>
		<label class="col-sm-4">${label}</label>
		<div class = 'col-sm-8'>
		<div  id = '${id}' class="toggle_radio">

	  	
	    <input type="radio" checked class="toggle_option first_toggle" id="first_toggle${id}" name="toggle_option" onclick="setRadioValue('${variable}','${value1}')"  >
	    <input type="radio"  class="toggle_option second_toggle" id="second_toggle${id}" name="toggle_option" onclick="setRadioValue('${variable}','${value2}')"  >
	    
	    <label for="first_toggle${id}"><p>${name1}</p></label>
	    <label for="second_toggle${id}"><p>${name2}</p></label>
	    
	    <div class="toggle_option_slider">
	    </div>
	    </div>
 
	</div>
	</div>
	</div>`
	}
//////////////////////////////////////////////////////////////////////////////////////////////
function getDiv(containerID,divID,label,variable,value){
	eval(`var ${variable} = ${value}`);
	console.log(eval(variable));
	var div = `<div id = "${divID}">${label}</div>`;
	$('#'+containerID).append(div);
	$('#'+ divID).click(function(){eval(`${variable}++`);console.log(eval(variable));$('#'+divID).append(eval(variable));})
}
//////////////////////////////////////////////////////////////////////////////////////////////
function getToggle(containerID,toggleID,onLabel,offLabel,onValue,offValue,variable,checked){
	if(checked === undefined || checked === null || checked === 'true' || checked === 'checked'){
		checked = true;
	}
	else if(checked === 'false' || checked === ''){
		checked = false;
	}

	var valueDict = {true:onValue,false:offValue};

	eval(`window.${variable} = valueDict[checked]`)
	var toggle = `<input id = "${toggleID}" class = 'p-0 m-0' type="checkbox"  data-toggle="toggle" data-on="${onLabel}" data-off="${offLabel}" data-onstyle="toggle-on" data-offstyle="toggle-off"><br>`;
	$('#'+containerID).append(toggle);
	if(checked){
		$('#'+toggleID).bootstrapToggle('on')
	}
	$('#'+containerID).click(function(){
		var value = $('#'+toggleID).prop('checked');
		console.log(value);
		eval(`window.${variable} = valueDict[${value}]`)

	})
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Provide color picker and allow updating of drawn polygons
function updateDistanceColor(jscolor) {
    distancePolylineOptions.strokeColor = '#' + jscolor;
    if(distancePolyline !== undefined){
        distancePolyline.setOptions(distancePolylineOptions);
    }
}
function updateUDPColor(jscolor) {
    udpOptions.strokeColor = '#' + jscolor;
    Object.keys(udpPolygonObj).map(function(k){
        udpPolygonObj[k].setOptions(udpOptions) ;       
    })
}
function updateAreaColor(jscolor) {
    areaPolygonOptions.strokeColor = '#' + jscolor;

    Object.keys(areaPolygonObj).map(function(k){
    	areaPolygonObj[k].setOptions(areaPolygonOptions) ;

    	console.log(areaPolygonObj[k])
    })
}
function addColorPicker(containerID,pickerID,updateFunction,value){
	if(value === undefined	|| value === null){value = 'FFFF00'}
	$('#'+containerID).append(`<button id = '${pickerID}' data-toggle="tooltip" title="If needed, change the color of shape you are drawing"
							    class=" fa fa-paint-brush text-dark color-button jscolor {valueElement:null,value:'${value}',onFineChange:'${updateFunction}(this)'} "
							    ></button>`);
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Functions to add and change content of BS modals
function addModal(containerID,modalID,bodyOnly){
	if(bodyOnly === null || bodyOnly === undefined){bodyOnly = false};
	if(containerID === null || containerID === undefined){containerID = 'main-container'};
	if(modalID === null || modalID === undefined){modalID = 'modal-id'};
	$('#'+modalID).remove();
	if(bodyOnly){
	$('#'+ containerID).append(`<div id = "${modalID}" class="modal fade " role="dialog">
            	<div class="modal-dialog modal-md ">
            		<div class="modal-content bg-white">
            			
	            		<div style = ' border-bottom: 0 none;'class="modal-header pb-0" id ="${modalID}-header">
	            			<button style = 'float:right;' type="button" class="close text-dark" data-dismiss="modal">&times;</button>
	            		</div>
	      				<div id ="${modalID}-body" class="modal-body bg-white " ></div>
			          	
        			</div>
        		</div> 
        	</div>`
        	)
	}else{
	$('#'+ containerID).append(`
            <div id = "${modalID}" class="modal fade " role="dialog">
            	<div class="modal-dialog modal-lg ">
            		<div class="modal-content bg-black">
            		<button type="button" class="close p-2 ml-auto" data-dismiss="modal">&times;</button>
	            		<div class="modal-header py-0" id ="${modalID}-header"></div>
	      				<div id ="${modalID}-body" class="modal-body " style = 'background:#DDD;' ></div>
			          	<div class="modal-footer" id ="${modalID}-footer"></div>
        			</div>
        		</div> 
        	</div>`
        	)
	}
}
function addModalTitle(modalID,title){
	if(modalID === null || modalID === undefined){modalID = 'modal-id'};
	// $('#'+modalID+' .modal-title').html('');
	$('#'+modalID+' .modal-header').prepend(`<h4 class="modal-title" id = '${modalID}-title'>${title}</h4>`);

}

function clearModal(modalID){
	if(modalID === null || modalID === undefined){modalID = 'modal-id'};
	// $('#'+modalID).empty();

	$('#'+modalID+'-title .modal-title').html('')
	$('#'+modalID+'-header').html('');
	$('#'+modalID+'-body').html('');
	$('#'+modalID+'-footer').html('');
	$('.modal').modal('hide');
	$('.modal-backdrop').remove()
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Function to plae a message in a BS modal and show it
function showMessage(title,message,modalID,show){
	if(title === undefined || title === null){title = ''}
	if(message === undefined || message === null){message = ''}
	if(show === undefined || show === null){show = true}
	if(modalID === undefined || modalID === null){modalID = 'error-modal'}
	
	clearModal(modalID);
	addModal('main-container',modalID,true);
	addModalTitle(modalID,title);
	$('#'+modalID+'-body').append(message);
	if(show){$('#'+modalID).modal();}

};
//////////////////////////////////////////////////////////////////////////////////////////////
//Show a basic tip BS modal
function showTip(title,message){
	showMessage('','<span class = "font-weight-bold text-uppercase" >'+ title +' </span><span>' +message + '</span>','tip-modal',false)

	$('#tip-modal-body').append(`<form class="form-inline pt-3 pb-0">
								  
								  <div class="form-check  mr-0">
                                	<input type="checkbox" class="form-check-input" id="dontShowTipAgainCheckbox"   name = 'dontShowAgain' value = 'true'>
                                	<label class=" text-uppercase form-check-label " for="dontShowTipAgainCheckbox" >Turn off tips</label>
                            		</div>
								    
								  
								</form>`);
	if(localStorage.showToolTipModal == undefined || localStorage.showToolTipModal == "undefined"){
	  localStorage.showToolTipModal = 'true';
	  }
	if(localStorage.showToolTipModal === 'true' && walkThroughAdded == false){
	  $('#tip-modal').modal().show();
	}
	$('#dontShowTipAgainCheckbox').change(function(){
	  console.log(this.checked)
	  localStorage.showToolTipModal  = !this.checked;
    });
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Function to add a given study area to the study area dropdown
function addStudyAreaToDropdown(name,toolTip){
	var id = name.replaceAll(' ','-');
	$('#study-area-list').append(`<a id = '${id}' name = '${name}' class="dropdown-item "   data-toggle="tooltip" title="${toolTip}">${name}</a>`)
  	$('#'+id).on('click',function(){
  		$('#summary-spinner').show();
  		$('#study-area-list').hide();
        longStudyAreaName = this.name;
    	dropdownUpdateStudyArea(this.name);
    }) 
 }
 //////////////////////////////////////////////////////////////////////////////////////////////
 function addToggle(containerDivID,toggleID,title,onLabel,offLabel,on,variable,valueOn,valueOff,onChangeFunction,tooltip){
    var valueDict = {true:valueOn,false:valueOff};
    var checked;
    if(tooltip === undefined || tooltip === null){tooltip = ''}
    if(on === null || on === undefined || on === 'checked' || on === 'true'){on = true;checked = 'checked';}
    else {on = false;checked = ''};
    // console.log('on');console.log(on);console.log(valueDict[on]);
    eval(`window.${variable} = valueDict[on];`);
    // try{
    // 	eval(`${onChangeFunction}`);
    // }catch(err){
    // 	console.log('Adding toggle error: ' + err);
    // }
    
    $('#'+containerDivID).append(`<div data-toggle="tooltip" data-placement="top" title="${tooltip}" >${title}<input  id = "${toggleID}" data-onstyle="dark" data-offstyle="light" data-style="border" type="checkbox" data-on="${onLabel}" data-off="${offLabel}"  ${checked} data-toggle="toggle" data-width="100" data-onstyle="dark" data-offstyle="light" data-style="border" data-size="small" ></div>`)
    $('#'+toggleID).change(function(){
        var value = valueDict[$('#'+toggleID).prop('checked')];
        eval(`window.${variable} = value;`);
        eval(`${onChangeFunction}`); 
    })
}
//////////////////////////////////////////////////////////////////////////////////////////////
function addRadio(containerDivID,radioID,title,onLabel,offLabel,variable,valueOn,valueOff,onFunction,offFunction,tooltip){
	// var valueDict = {true:valueOn,false:valueOff};
	eval(`window.${variable} = '${valueOn}';`);
	// console.log(valueDict);
	
	$('#'+containerDivID).append(`<div class = 'row' id = '${radioID}-container' rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="${tooltip}">
		<label class="col-12 pb-0">${title} </label>
		<div class = 'col-12 pt-0'>
		<div  id = '#${radioID}'  class="toggle_radio p-0">

	  	
	    <input type="radio" class = "first_toggle" checked class="toggle_option" id="${radioID}-first_toggle" name="${radioID}-toggle_option"  value="1" >
	    <input type="radio" class="toggle_option second_toggle" id="${radioID}-second_toggle" name="${radioID}-toggle_option"  value="2" >
	    
	    <label for="${radioID}-first_toggle" id = '${radioID}-first_toggle_label'><p>${onLabel}</p></label>
	    <label for="${radioID}-second_toggle"  id = '${radioID}-second_toggle_label'><p>${offLabel}</p></label>
	    
	    <div class="toggle_option_slider">
	    </div>
	    </div>
 
	</div>
	</div>`)

	$('#'+radioID + '-first_toggle').change(function(){
		// console.log('first');
		eval(`window.${variable} = '${valueOn}';`);
		eval(`${onFunction}`);
	})
	$('#'+radioID + '-second_toggle').change(function(){
		// console.log('second');
		eval(`window.${variable} = '${valueOff}';`);
		eval(`${offFunction}`);
	})
	
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Function to set up a checkbox list
//Will set up an object under the variable name with the optionList that is updated
//Option list is formatted as {'Label 1': true, 'Label 2':false...etc}
function addCheckboxes(containerID,checkboxID,title,variable,optionList){
    $('#'+containerID).append(`<form  id = '${checkboxID}'>${title}<br></form>`);
    eval(`window.${variable} = []`);
    Object.keys(optionList).map(function(k){
      // console.log(k)
      var checkboxCheckboxID = k + '-checkbox';
      var checkboxLabelID = checkboxCheckboxID + '-label'
      var checked = optionList[k];
      if(checked){checked = 'checked';}
        else{checked = ''};
        eval(`window.${variable} = optionList`)
      $('#'+checkboxID).append(`
                                 <input  id="${checkboxCheckboxID}" type="checkbox" ${checked} value = '${k}' />
                                 <label  id="${checkboxLabelID}" style = 'margin-bottom:0px;'  for="${checkboxCheckboxID}" >${k}</label>
                               `)

      $('#'+checkboxCheckboxID).change( function() {
                                      var v = $(this).val();
                                      var checked = $(this)[0].checked;
                                      optionList[v] = checked;
                                      eval(`window.${variable} = optionList`)
                                    });
    })
  }
//////////////////////////////////////////////////////////////////////////////////////////////
//Similar to the addCheckboxes only with radio buttons
//The variable assumes the value of the key of the object that is selected instead of the entire optionList object
//e.g. if optionList = {'hello':true,'there':false} then the variable = 'hello'
function addMultiRadio(containerID,radioID,title,variable,optionList){
    $('#'+containerID).append(`<form  class = 'py-2' id = '${radioID}'>${title}<br></form>`);

    eval(`window.${variable} = '';`);
    Object.keys(optionList).map(function(k){
      var radioCheckboxID = k + '-checkbox';
      var radioLabelID = radioCheckboxID + '-label'
      var checked = optionList[k];
      if(checked){
        checked = 'checked';
        eval(`window.${variable} = "${k}"`)
      }else{checked = ''};
      
      $('#'+radioID).append(`<div class="form-check form-check-inline">
                              <input class="form-check-input" type="radio" name="inlineRadioOptions" id="${radioCheckboxID}" ${checked} value="${k}">
                              <label class="form-check-label" for="${radioCheckboxID}">${k}</label>
                            </div>`);
      $('#'+radioCheckboxID).change( function() {
                                      var v = $(this).val();
                                      eval(`window.${variable} = "${v}"`)
                                    });
})
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Some basic formatting functions
function zeroPad(num, places) {
  var zero = places - num.toString().length + 1;
  return Array(+(zero > 0 && zero)).join("0") + num;
}
function formatDT(__dt) {
    var year = __dt.getFullYear();
    var month = zeroPad(__dt.getMonth()+1, 2);
    var date = zeroPad(__dt.getDate(), 2);
    // var hours = zeroPad(__dt.getHours(), 2);
    // var minutes = zeroPad(__dt.getMinutes(), 2);
    // var seconds = zeroPad(__dt.getSeconds(), 2);
    return   month + '/'+ date + '/'+ year.toString().slice(2,4) //+ ' ' + hours + ':' + minutes + ':' + seconds;
};
function formatDTJulian(__dt) {
    // var year = __dt.getFullYear();
    var month = zeroPad(__dt.getMonth()+1, 2);
    var date = zeroPad(__dt.getDate(), 2);
    // var hours = zeroPad(__dt.getHours(), 2);
    // var minutes = zeroPad(__dt.getMinutes(), 2);
    // var seconds = zeroPad(__dt.getSeconds(), 2);
    return  month + '/' + date ;//+ ' ' + hours + ':' + minutes + ':' + seconds;
};

Date.fromDayofYear= function(n, y){
    if(!y) y= new Date().getFullYear();
    var d= new Date(y, 0, 1);
    return new Date(d.setMonth(0, n));
}
Date.prototype.dayofYear= function(){
    var d= new Date(this.getFullYear(), 0, 0);
    return Math.floor((this-d)/8.64e+7);
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Create a dual range slider
//Possible modes are : 'date','julian',or null
//Default mode is 'date', must specify mode as null to use vanilla numbers
function setUpDualRangeSlider(var1,var2,min,max,defaultMin,defaultMax,step,sliderID,updateID,mode){
    // var dt_from = "2000/11/01";
  // var dt_to = "2015/11/24";
// $("#"+updateID +" .ui-slider .ui-slider-handle").css( {"width": '3px'} );
  if(mode === undefined  || mode === null){mode = 'date'};
  if(defaultMin === undefined  || defaultMin   === null){defaultMin  = min};
  if(defaultMax === undefined  || defaultMax   === null){defaultMax  = max};
  // if(step === undefined  || step === null){step = 1};

  if(mode === 'date'){
    min = new Date(min);
    max = new Date(max);
    step = step *24*60*60;
    defaultMin   = new Date(defaultMin);
    defaultMax   = new Date(defaultMax);
    // step = step*60*60*24
    $( "#"+updateID).html(formatDT(defaultMin)+ ' - ' + formatDT(defaultMax));
  }
  else if(mode === 'julian'){
    min = Date.fromDayofYear(min);
    max = Date.fromDayofYear(max);
    step = step *24*60*60;
    defaultMin = Date.fromDayofYear(defaultMin);
    defaultMax = Date.fromDayofYear(defaultMax);
    $( "#"+updateID).html(formatDTJulian(defaultMin)+ ' - ' + formatDTJulian(defaultMax));
  }
  else{$( "#"+updateID).html(defaultMin.toString()+ ' - ' + defaultMax.toString());}
  
  if(mode === 'date' || mode === 'julian'){
  var minVal = Date.parse(min)/1000;
  var maxVal = Date.parse(max)/1000;
  var minDefault = Date.parse(defaultMin)/1000;
  var maxDefault = Date.parse(defaultMax)/1000;
  }
  else{
    var minVal = min;
    var maxVal = max;
    var minDefault = defaultMin;
    var maxDefault = defaultMax;
  }

      $("#"+sliderID).slider({
        range:true,
         min: minVal,
    max: maxVal,
    step: step,
    values: [minDefault, maxDefault],

    slide: function(e,ui){

      if(mode === 'date'){
      var value1 = ui.values[0]*1000;
      var value2 = ui.values[1]*1000;

      var value1Show  = formatDT(new Date(value1));
      var value2Show  = formatDT(new Date(value2));

      // value1 = new Date(value1);
      // value2 = new Date(value2);
      $( "#"+updateID ).html(value1Show.toString() + ' - ' + value2Show.toString());
      
      eval(var1 + '= new Date('+ value1.toString()+')');
      eval(var2 + '= new Date('+ value2.toString()+')');
        }
      else if(mode === 'julian'){
      var value1 = new Date(ui.values[0]*1000);
      var value2 = new Date(ui.values[1]*1000);

      var value1Show  = formatDTJulian(value1);
      var value2Show  = formatDTJulian(value2);
      value1 =value1.dayofYear();
      value2 = value2.dayofYear();
      
    $( "#"+updateID ).html(value1Show.toString() + ' - ' + value2Show.toString());
          
          eval(var1 + '= '+ value1.toString());
          eval(var2 + '= '+ value2.toString());
            }
          else{
          var value1 = ui.values[0];
          var value2 = ui.values[1];

          var value1Show  = value1;
          var value2Show  = value2;

          $( "#"+updateID ).html(value1Show.toString() + ' - ' + value2Show.toString());
          
          eval(var1 + '= '+ value1.toString());
          eval(var2 + '= '+ value2.toString());
          }
        }
          }); 
  }
//Wrapper function to add a dual range slider
function addDualRangeSlider(containerDivID,title,var1,var2,min,max,defaultMin,defaultMax,step,sliderID,mode,tooltip){
	if(tooltip === null || tooltip === undefined){tooltip = ''};
	
	// setUpRangeSlider('startYear', 'endYear', 1985, 2018, startYear, endYear, 1, 'slider1', 'date-range-value1', 'null');
	$('#'+containerDivID).append(`<div  id="${sliderID}-container"class='dual-range-slider-container px-1' rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="${tooltip}">
							        <div class='dual-range-slider-name py-2'>${title}</div>
							        <div id="${sliderID}" class='dual-range-slider-slider' href = '#'></div>
							        <div id='${sliderID}-update' class='dual-range-slider-value p-2'></div>
							    </div>`);
	setUpDualRangeSlider(var1,var2,min,max,defaultMin,defaultMax,step,sliderID,sliderID+ '-update',mode)

}
//////////////////////////////////////////////////////////////////////////////////////////////
//Function to add single range slider
function setUpRangeSlider(variable,min,max,defaultValue,step,sliderID,mode){
    eval(`window.${variable} = ${defaultValue};`);
    $('#'+sliderID + '-update').html(defaultValue);
    $("#"+sliderID).slider({
        min: min,
        max:max,
        step: step,
        value: defaultValue,
        slide: function(e,ui){
            eval(`window.${variable} = ${ui.value};`);
            $('#'+sliderID + '-update').empty();
            $('#'+sliderID + '-update').html(ui.value);
        }
    })
}
//Wrapper for single range slider
function addRangeSlider(containerDivID,title,variable,min,max,defaultValue,step,sliderID,mode,tooltip){
    $('#'+containerDivID).append(`<div  class='dual-range-slider-container px-1' rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="${tooltip}">
                                    <div class='dual-range-slider-name py-2'>${title}</div>
                                    <div id="${sliderID}" class='dual-range-slider-slider' href = '#'></div>
                                    <div id='${sliderID}-update' class='dual-range-slider-value p-2'></div>
                                </div>`);
    setUpRangeSlider(variable,min,max,defaultValue,step,sliderID,mode);
}
 //////////////////////////////////////////////////////////////////////////////////////////////
//More Bootstrap element creators
//Function to add tab to list
function addTab(tabTitle,tabListID, divListID,tabID, divID,tabOnClick,divHTML,tabToolTip,selected){  
  if(!tabToolTip){tabToolTip = ''};
  var show;
  if(selected || selected === 'true'){show = 'active show'}else{show = ''};

  $("#" + tabListID ).append(`<li class="nav-item"><a onclick = '${tabOnClick}' class="nav-link text-left text-dark tab-nav-link ${show}" id="'+tabID+'" data-toggle="tab" href="#${divID}" role="tab" aria-controls="${divID}" aria-selected="false" rel="txtTooltip" data-toggle="tooltip"  title="${tabToolTip}">${tabTitle}</a></li>`);

  $('#'+divListID).append($(`<div class="tab-pane fade ${show}" id="${divID}" role="tabpanel" aria-labelledby="${tabID}" rel="txtTooltip" data-toggle="tooltip"  title="${tabToolTip}"></div>`).append(divHTML))

    };
/////////////////////////////////////////////////////////////////////////////////////////////
function addTabContainer(containerID,tabListID,divListID){
	$('#'+ containerID).append(`<ul class="pb-1 nav nav-tabs flex-column nav-justified md-tabs" id="${tabListID}" role="tablist">  
    </ul>
    <div class = 'tab-content card' id = '${divListID}'>
    </div>`);
}
// function addAccordianContainer(containerID,tabListID,divListID){
// 	$('#'+ containerID).append(`<ul class="pb-1 nav nav-tabs flex-column nav-justified md-tabs" id="${tabListID}" role="tablist">  
//     </ul>
//     <div class = 'tab-content card' id = '${divListID}'>
//     </div>`);
// }
//////////////////////////////////////////////////////////////////////////////////////////////
function addCollapse(containerID,collapseLabelID,collapseID,collapseLabel, collapseLabelIcon,show,onclick,toolTip){
	var collapsed;
	if(toolTip === undefined || toolTip === null){toolTip = ''}
	if(show === true || show === 'true' || show === 'show'){show = 'show';collapsed = ''; }else{show = '';collapsed='collapsed'}
	var collapseTitleDiv = `<div   rel="txtTooltip" data-toggle="tooltip"  title="${toolTip}" class="panel-heading px-3 py-2 " role="tab" id="${collapseLabelID}" onclick = '${onclick}'>
	<h5 class="p-0 m-0 panel-title  ${collapsed}" data-toggle="collapse"  href="#${collapseID}" aria-expanded="false" aria-controls="${collapseID}"> <a class = 'collapse-title' >
	${collapseLabelIcon} ${collapseLabel} </a></h5></div>`;

	var collapseDiv =`<div id="${collapseID}" class="panel-collapse collapse panel-body ${show} px-5 py-0" role="tabpanel" aria-labelledby="${collapseLabelID}"></div>`;
	$('#'+containerID).append(collapseTitleDiv);
	$('#'+containerID).append(collapseDiv);
}
//////////////////////////////////////////////////////////////////////////////////////////////
function addSubCollapse(containerID,collapseLabelID,collapseID,collapseLabel, collapseLabelIcon,show,onclick){
	var collapsed;
	if(show === true || show === 'true' || show === 'show'){show = 'show';collapsed = ''; }else{show = '';collapsed='collapsed'}


	var collapseTitleDiv = `<div >
                                <div   class="panel-heading px-0 py-2 " role="tab" id="${collapseLabelID}" onclick = '${onclick}'>
	                           <h5 class="sub-panel-title ${collapsed}" data-toggle="collapse"  href="#${collapseID}" aria-expanded="false" aria-controls="${collapseID}" > <a class = 'collapse-title' >${collapseLabelIcon} ${collapseLabel} </a></h5>
                                </div>
                            </div`;

	var collapseDiv =`<div id="${collapseID}" class="panel-collapse collapse panel-body ${show} px-1 py-0" role="tabpanel" aria-labelledby="${collapseLabelID}"></div>`;
	$('#'+containerID).append(collapseTitleDiv);
	$('#'+containerID).append(collapseDiv);
}
//////////////////////////////////////////////////////////////////////////////////////////////
function addAccordianContainer(parentContainerID,accordianContainerID){
  $('#' + parentContainerID).append(`<div class="accordion" id="${accordianContainerID}"></div>`);
    
}
//////////////////////////////////////////////////////////////////////////////////////////////
var panelCollapseI = 1;
function addAccordianCard(accordianContainerID,accordianCardHeaderID, accordianCardBodyID,accordianCardHeaderContent,accordianCardBodyContent,show,onclick,toolTip){
  var collapsed;
  if(toolTip === undefined || toolTip === null){toolTip = '';}
  if(show === true || show === 'true' || show === 'show'){show = 'show';collapsed = ''; }else{show = '';collapsed='collapsed'}
  $('#' + accordianContainerID).append(`
    <div>
      <div class=" px-0 py-2 sub-panel-title ${collapsed}" id="${accordianCardHeaderID}" data-toggle="collapse" data-target="#${accordianCardBodyID}"
        aria-expanded="false" aria-controls="${accordianCardBodyID}" onclick = '${onclick}'>
      <a class = 'collapse-title' rel="txtTooltip" data-toggle="tooltip"  title="${toolTip}"  >
        ${accordianCardHeaderContent} </a>
      </div>
      <div id="${accordianCardBodyID}" class="panel-collapse-${panelCollapseI} super-panel-collapse panel-collapse collapse panel-body pl-3 py-0  ${show} bg-black" aria-labelledby="${accordianCardHeaderID}"
        data-parent="#${accordianContainerID}">
        <div rel="txtTooltip" data-toggle="tooltip"  title="${toolTip}">${accordianCardBodyContent}</div>
      </div>
    </div>`)
  // $('#'+accordianCardBodyID+'.super-panel-collapse').on('hidden.bs.collapse', function () {
  	// find the children and close them
  	// $(!this).find('.show').collapse('hide');
  	// console.log('hello')
  	// $('.panel-collapse.show.collapse.toggle-collapse').collapse('hide');
  	// stopAllTools();
	// });
  panelCollapseI++;
}
//////////////////////////////////////////////////////////////////////////////////////////////
function addSubAccordianCard(accordianContainerID,accordianCardHeaderID, accordianCardBodyID,accordianCardHeaderContent,accordianCardBodyContent,show,onclick,toolTip){
  var collapsed;
  if(toolTip === undefined || toolTip === null){toolTip = '';}
  if(show === true || show === 'true' || show === 'show'){show = 'show';collapsed = ''; }else{show = '';collapsed='collapsed'}
  $('#' + accordianContainerID).append(`
    <div>
      <div class=" px-0 py-2 sub-sub-panel-title ${collapsed}" id="${accordianCardHeaderID}" data-toggle="collapse" data-target="#${accordianCardBodyID}"
        aria-expanded="false" aria-controls="${accordianCardBodyID}" onclick = '${onclick}'>
      <a class = 'collapse-title' rel="txtTooltip" data-toggle="tooltip"  title="${toolTip}"  >
        ${accordianCardHeaderContent} </a>
      </div>
      <div id="${accordianCardBodyID}" class="panel-collapse-${panelCollapseI} toggle-collapse panel-collapse collapse panel-body pl-3 py-0  ${show} bg-black" aria-labelledby="${accordianCardHeaderID}"
        data-parent="#${accordianContainerID}">
        <div rel="txtTooltip" data-toggle="tooltip"  title="${toolTip}">${accordianCardBodyContent}</div>
      </div>
    </div>`)
 //  $('.panel-collapse.toggle-collapse').on('hidden.bs.collapse', function () {
 //  	console.log('hello')
 //  	// find the children and close them
 //  	$(this).find('.show').collapse('hide');
 //  	// $('.panel-collapse.show.collapse.toggle-collapse').collapse('hide');
	// });
  
  panelCollapseI++;
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Functions to run the walk through
function getWalkThroughCollapseContainerID(){
    var collapseContainer;
    if($(window).width() < 576){collapseContainer = 'sidebar-left' }
    else{collapseContainer = 'legendDiv';}
    return collapseContainer
}
function moveCollapse(baseID){
    var collapseContainer =getWalkThroughCollapseContainerID();
    $('#'+baseID+'-label').detach().appendTo('#'+collapseContainer);
    $('#'+baseID+'-div').detach().appendTo('#'+collapseContainer);
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Legend functions
function addLegendCollapse(){
    var collapseContainer =getWalkThroughCollapseContainerID(); 
    addCollapse(collapseContainer,'legend-collapse-label','legend-collapse-div','LEGEND','<i class="fa fa-location-arrow fa-rotate-45 mx-1" aria-hidden="true"></i>',true,``,'LEGEND of the layers displayed on the map')
    // $('#legend-collapse-div').append(`<legend-list   id="legend"></legend-list>`)
    $('#legend-collapse-div').append(`<div id="legend-layer-list"></div>`);
    $('#legend-collapse-div').append(`<div id="legend-reference-layer-list"></div>`);
    $('#legend-collapse-div').append(`<div id="legend-fhp-div"></div>`);
    $('#legend-collapse-div').append(`<div id="time-lapse-legend-list"></div>`);
    $('#legend-collapse-div').append(`<div id="legend-area-charting-select-layer-list"></div>`);
}
function addLegendContainer(legendContainerID,containerID,show,toolTip){
	if(containerID === undefined || containerID === null){containerID = 'legend-collapse-div'}
	if(show === undefined || show === null){show = true}
	if(show){show = 'block'}
	else{show = 'none'}
	$('#' + containerID).prepend(`<div class = 'py-2 row' href="#" rel="txtTooltip" data-toggle="tooltip" data-placement="top" title= '${toolTip}' style = 'display:${show};' id = '${legendContainerID}'>
								</div>`);
}

function addClassLegendContainer(classLegendContainerID,legendContainerID,classLegendTitle){
	$('#'+legendContainerID).append(`<div class='my-legend'>
										<div class = 'legend-title'>${classLegendTitle}</div>
										<div class='legend-scale'>
									  		<ul class='legend-labels' id = '${classLegendContainerID}'></ul>
										</div>
									</div>`)
}
function addClassLegendEntry(classLegendContainerID,obj){
	$('#'+classLegendContainerID).append(`<li><span style='border: ${obj.classStrokeWeight}px solid #${obj.classStrokeColor};background:#${obj.classColor};'></span>${obj.className}</li>`)
}

function addColorRampLegendEntry(legendContainerID,obj){
	$('#'+legendContainerID).append(`<li class = 'legend-colorRamp' href="#" rel="txtTooltip" data-toggle="tooltip" data-placement="top" title= '${obj.helpBoxMessage}'>
							            <div class = 'legend-title'>${obj.name}</div>
							            <div class = 'colorRamp'style='${obj.colorRamp};'></div>
							            <div>
							                <span class = 'leftLabel'>${obj.min}</span>
							                <span class = 'rightLabel'>${obj.max}</span>
							            </div>
							            
							        </li> `)
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Function to disable rerun button when there are still outstanding GEE requests
function regulateReRunButton(){
	if(outstandingGEERequests > 0){
		$('#reRun-button').prop('disabled',true);
		$('#reRun-button').prop('title',staticTemplates.reRunButtonDisabledTooltip);
	}
	else{
		$('#reRun-button').prop('disabled',false);
		$('#reRun-button').prop('title',staticTemplates.reRunButtonEnabledTooltip);
	}
} 
//Function to help keep track of GEE requests
function updateOutstandingGEERequests(){
	$('#outstanding-gee-requests').html(outstandingGEERequests);
	regulateReRunButton();
}
function updateGEETileLayersLoading(){
	$('#number-gee-tiles-downloading').html(geeTileLayersDownloading);
}
function incrementOutstandingGEERequests(){
	outstandingGEERequests ++;updateOutstandingGEERequests();
}
function decrementOutstandingGEERequests(){
	outstandingGEERequests --;updateOutstandingGEERequests();
}

function incrementGEETileLayersLoading(){
	geeTileLayersDownloading++;updateGEETileLayersLoading();
}
function decrementGEETileLayersLoading(){
	geeTileLayersDownloading--;updateGEETileLayersLoading();
}
function updateGEETileLayersDownloading(){
    geeTileLayersDownloading = Object.values(layerObj).filter(function(v){return v.loading}).length;
    updateGEETileLayersLoading();
}
//////////////////////////////////////////////////////////////////////////////////////////////
//Function for adding map layers of various sorts to the map
//Map layers can be ee objects, geojson, dynamic map services, and tile map services

function addLayer(layer){
    //Initialize a bunch of variables
    layer.loadError = false;
	var id = layer.legendDivID;
    layer.id = id;
    var queryID = id + '-'+layer.ID;
	var containerID = id + '-container-'+layer.ID;
	var opacityID = id + '-opacity-'+layer.ID;
	var visibleID = id + '-visible-'+layer.ID;
	var spanID = id + '-span-'+layer.ID;
	var visibleLabelID = visibleID + '-label-'+layer.ID;
	var spinnerID = id + '-spinner-'+layer.ID;
    var selectionID = id + '-selection-list-'+layer.ID;
	var checked = '';
    layerObj[id] = layer;
    layer.wasJittered = false;
    layer.loading = false;
    layer.refreshNumber = refreshNumber;
	if(layer.visible){checked = 'checked'}
    
    if(layer.viz.isTimeLapse){
        // console.log(timeLapseObj[layer.viz.timeLapseID]);
        timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs.push(id);
        timeLapseObj[layer.viz.timeLapseID].sliders.push(opacityID);
        timeLapseObj[layer.viz.timeLapseID].layerVisibleIDs.push(visibleID);

    }

    //Set up layer control container
	$('#'+ layer.whichLayerList).prepend(`<li id = '${containerID}'class = 'layer-container' rel="txtTooltip" data-toggle="tooltip"  title= '${layer.helpBoxMessage}'>
								           
								           <div id="${opacityID}" class = 'simple-layer-opacity-range'></div>
								           <input  id="${visibleID}" type="checkbox" ${checked}  />
								            <label class = 'layer-checkbox' id="${visibleLabelID}" style = 'margin-bottom:0px;display:none;'  for="${visibleID}"></label>
								            <i id = "${spinnerID}" class="fa fa-spinner fa-spin layer-spinner" rel="txtTooltip" data-toggle="tooltip"  title='Waiting for layer service from Google Earth Engine'></i>
								            <i id = "${spinnerID}2" style = 'display:none;' class="fa fa-cog fa-spin layer-spinner" rel="txtTooltip" data-toggle="tooltip"  title='Waiting for map tiles from Google Earth Engine'></i>
								            <i id = "${spinnerID}3" style = 'display:none;' class="fa fa-cog fa-spin layer-spinner" rel="txtTooltip" data-toggle="tooltip"  title='Waiting for map tiles from Google Earth Engine'></i>
                                            
								            <span id = '${spanID}' class = 'layer-span'>${layer.name}</span>
								       </li>`);
    //Set up opacity slider
	$("#"+opacityID).slider({
        min: 0,
        max: 100,
        step: 1,
        value: layer.opacity*100,
    	slide: function(e,ui){
    		layer.opacity = ui.value/100;
    		// console.log(layer.opacity);
    		 if(layer.layerType !== 'geeVector' && layer.layerType !== 'geoJSONVector'){
                layer.layer.setOpacity(layer.opacity);
                
                
              }else{
    	            var style = layer.layer.getStyle();
    	            style.strokeOpacity = layer.opacity;
    	            style.fillOpacity = layer.opacity/layer.viz.opacityRatio;
    	            layer.layer.setStyle(style);
    	            if(layer.visible){layer.range}
                    }
            if(layer.visible){
            	layer.rangeOpacity = layer.opacity;
            }     
            layerObj[id].visible = layer.visible;
            layerObj[id].opacity = layer.opacity;
    		setRangeSliderThumbOpacity();
    		}
	})
	function setRangeSliderThumbOpacity(){
		$('#'+opacityID).css("background-color", 'rgba(55, 46, 44,'+layer.rangeOpacity+')')
	}
    //Progress bar controller
	function updateProgress(){
		var pct = layer.percent;
        if(pct === 100 && (layer.layerType === 'geeImage' || layer.layerType === 'geeVectorImage' || layer.layerType === 'geeImageCollection')){jitterZoom()}
		$('#'+containerID).css('background',`-webkit-linear-gradient(left, #FFF, #FFF ${pct}%, transparent ${pct}%, transparent 100%)`)
	}
	//Function for zooming to object
	function zoomFunction(){

		if(layer.layerType === 'geeVector' ){
			centerObject(layer.item)
		}else if(layer.layerType === 'geoJSONVector'){
			// centerObject(ee.FeatureCollection(layer.item.features.map(function(t){return ee.Feature(t).dissolve(100,ee.Projection('EPSG:4326'))})).geometry().bounds())
			// synchronousCenterObject(layer.item.features[0].geometry)
		}else{
          
			if(layer.item.args !== undefined && layer.item.args.value !== null && layer.item.args.value !== undefined){
				synchronousCenterObject(layer.item.args.value)
			}
            else if(layer.item.args !== undefined &&layer.item.args.featureCollection !== undefined &&layer.item.args.featureCollection.args !== undefined && layer.item.args.featureCollection.args.value !== undefined && layer.item.args.featureCollection.args.value !== undefined){
                synchronousCenterObject(layer.item.args.featureCollection.args.value);
            };
		}
	}
    //Try to handle load failures
    function loadFailure(){
        layer.loadError = true;
        console.log('GEE Tile Service request failed for '+layer.name);
        $('#'+containerID).css('background-color','red');
        $('#'+containerID).attr('title','Layer failed to load. Try zooming in to a smaller extent and then hitting the "Submit" button in the "PARAMETERS" menu.')
        // getGEEMapService();
    }
    //Function to handle turning off of different types of layers
    function turnOff(){
        if(layer.layerType === 'dynamicMapService'){
            layer.layer.setMap(null);
            layer.visible = false;
            layer.percent = 0;
            layer.rangeOpacity = 0;
            setRangeSliderThumbOpacity();
            updateProgress();
            $('#'+layer.legendDivID).hide();
        } else if(layer.layerType !== 'geeVector' && layer.layerType !== 'geoJSONVector'){
            layer.visible = false;
            layer.map.overlayMapTypes.setAt(layer.layerId,null);
            layer.percent = 0;
            updateProgress();
            $('#'+layer.legendDivID).hide();
            layer.rangeOpacity = 0;
            if(layer.layerType !== 'tileMapService' && layer.layerType !== 'dynamicMapService' && layer.canQuery){
             queryObj[queryID].visible = layer.visible;
            }
        }else{
            layer.visible = false;
            
            layer.percent = 0;
            updateProgress();
            $('#'+layer.legendDivID).hide();
            layer.layer.setMap(null);
            layer.rangeOpacity = 0;
            $('#' + spinnerID+'2').hide();
            // geeTileLayersDownloading = 0;
            // updateGEETileLayersLoading();
            if(layer.layerType === 'geeVector' && layer.canQuery){
                queryObj[queryID].visible = layer.visible;
            }
            
        }
        layer.loading = false;
        updateGEETileLayersDownloading();
            
        $('#'+spinnerID + '2').hide();
        $('#'+spinnerID + '3').hide();
        vizToggleCleanup();
    }
    //Function to handle turning on different layer types
    function turnOn(){
        if(!layer.viz.isTimeLapse){
            turnOffTimeLapseCheckboxes();
        }
        if(layer.layerType === 'dynamicMapService'){
            layer.layer.setMap(map);
            layer.visible = true;
            layer.percent = 100;
            layer.rangeOpacity = layer.opacity;
            setRangeSliderThumbOpacity();
            updateProgress();
            $('#'+layer.legendDivID).show();
        } else if(layer.layerType !== 'geeVector' && layer.layerType !== 'geoJSONVector'){
            layer.visible = true;
            layer.map.overlayMapTypes.setAt(layer.layerId,layer.layer);
            $('#'+layer.legendDivID).show();
            layer.rangeOpacity = layer.opacity;
            if(layer.isTileMapService){layer.percent = 100;updateProgress();}
            layer.layer.setOpacity(layer.opacity); 
            if(layer.layerType !== 'tileMapService' && layer.layerType !== 'dynamicMapService' && layer.canQuery){
             queryObj[queryID].visible = layer.visible;
            }
        }else{

           layer.visible = true;
            layer.percent = 100;
            updateProgress();
            $('#'+layer.legendDivID).show();
            layer.layer.setMap(layer.map);
            layer.rangeOpacity = layer.opacity;
            if(layer.layerType === 'geeVector' && layer.canQuery){
                queryObj[queryID].visible = layer.visible;
            }
        }
        vizToggleCleanup();
    }
    //Some functions to keep layers tidy
    function vizToggleCleanup(){
        setRangeSliderThumbOpacity();
        layerObj[id].visible = layer.visible;
        layerObj[id].opacity = layer.opacity;
    }
	function checkFunction(){
        if(!layer.loadError){
            if(layer.visible){
                turnOff();
            }else{turnOn()}  
        }
            
	}
    function turnOffAll(){  
        if(layer.visible){
            $('#'+visibleID).click();
        }
    }
    function turnOnAll(){
        if(!layer.visible){
            $('#'+visibleID).click();
        }
    }
	$("#"+ opacityID).val(layer.opacity * 100);

    //Handle double clicking
	var prevent = false;
	var delay = 200;
	$('#'+ spanID).click(function(){
		setTimeout(function(){
			if(!prevent){
				$('#'+visibleID).click();
			}
		},delay)
		
	});
    $('#'+ spinnerID + '2').click(function(){$('#'+visibleID).click();});
    //Try to zoom to layer if double clicked
	$('#'+ spanID).dblclick(function(){
            zoomFunction();
			prevent = true;
			zoomFunction();
			if(!layer.visible){$('#'+visibleID).click();}
			setTimeout(function(){prevent = false},delay)
		})

	//If checkbox is toggled
	$('#'+visibleID).change( function() {checkFunction();});
   

	layerObj[id].visible = layer.visible;
    layerObj[id].opacity = layer.opacity;
	
    //Handle different scenarios where all layers need turned off or on
    if(!layer.viz.isTimeLapse){
        $('.layer-checkbox').on('turnOffAll',function(){turnOffAll()});
    }
    if(layer.layerType === 'geeVector' || layer.layerType === 'geeVectorImage' || layer.layerType === 'geoJSONVector'){
        $('#'+visibleLabelID).addClass('vector-layer-checkbox');
        $('.vector-layer-checkbox').on('turnOffAll',function(){turnOffAll()});
        $('.vector-layer-checkbox').on('turnOnAll',function(){turnOnAll()});
        $('.vector-layer-checkbox').on('turnOffAllVectors',function(){turnOffAll()});
        $('.vector-layer-checkbox').on('turnOnAllVectors',function(){turnOnAll()});
    }
    //Handle different object types
	if(layer.layerType === 'geeImage' || layer.layerType === 'geeVectorImage' || layer.layerType === 'geeImageCollection'){
        //Handle image colletions
        if(layer.layerType === 'geeImageCollection'){
            layer.imageCollection = layer.item;

            if(layer.viz.reducer === null || layer.viz.reducer === undefined){
                layer.viz.reducer = ee.Reducer.firstNonNull();
            }
            var bandNames = ee.Image(layer.item.first()).bandNames();
            layer.item = ee.ImageCollection(layer.item).reduce(layer.viz.reducer).rename(bandNames);
        //Handle vectors
        } else if(layer.layerType === 'geeVectorImage' || layer.layerType === 'geeVector'){
            if(layer.viz.isSelectLayer){
                
                selectedFeaturesJSON[layer.name] = {'geoJSON':new google.maps.Data(),'id':layer.id,'rawGeoJSON':{},'eeFeatureCollection':ee.FeatureCollection([])}
                selectedFeaturesJSON[layer.name].geoJSON.setMap(layer.map);

                // layer.infoWindow = getInfoWindow(infoWindowXOffset);
                // infoWindowXOffset += 30;
                selectedFeaturesJSON[layer.name].geoJSON.setStyle({strokeColor:invertColor(layer.viz.strokeColor)});
                // layer.queryVector = layer.item;  
                $('#'+visibleLabelID).addClass('select-layer-checkbox');
                $('.select-layer-checkbox').on('turnOffAll',function(){turnOffAll()});
                $('.select-layer-checkbox').on('turnOnAll',function(){turnOnAll()});
            }
            layer.queryItem = layer.item;
            if(layer.layerType === 'geeVectorImage'){
                layer.item = ee.Image().paint(layer.item,null,layer.viz.strokeWeight);
                layer.viz.palette = layer.viz.strokeColor;
            }
            //Add functionality for select layers to be clicked and selected
            if(layer.viz.isSelectLayer){
                
                selectedFeaturesJSON[layer.name].geoJSON.addListener('click',function(event){
                    console.log(event);
                    var name = event.feature.j.selectionTrackingName;
                    delete selectedFeaturesJSON[layer.name].rawGeoJSON[name]
                    selectedFeaturesJSON[layer.name].geoJSON.remove(event.feature);
                    updateSelectedAreasNameList();
                    updateSelectedAreaArea();

                });
                map.addListener('click',function(event){
                    // console.log(layer.name);console.log(event);
                    if(layer.currentGEERunID === geeRunID){
                            //     layer.infoWindow.setMap(null);
                        if(layer.visible && toolFunctions.area.selectInteractive.state){
                            $('#'+spinnerID + '3').show();
                            $('#select-features-list-spinner').show();
                            // layer.queryGeoJSON.forEach(function(f){layer.queryGeoJSON.remove(f)});

                            var features = layer.queryItem.filterBounds(ee.Geometry.Point([event.latLng.lng(),event.latLng.lat()]));
                            selectedFeaturesJSON[layer.name].eeFeatureCollection =selectedFeaturesJSON[layer.name].eeFeatureCollection.merge(features);
                            
                            features.evaluate(function(values){
                                var features = values.features;
                                var dummyNameI = 1;
                                features.map(function(f){
                                    var name;
                                    // selectedFeatures.features.push(f);
                                    Object.keys(f.properties).map(function(p){
                                        if(p.toLowerCase().indexOf('name') !== -1){name = f.properties[p]}
                                    })
                                    if(name === undefined){name = dummyNameI.toString();dummyNameI++;}
                                    // console.log(name)
                                    if(name !== undefined){
                                    }
                                    if(getSelectedAreasNameList(false).indexOf(name) !== -1){
                                        name += '-'+selectionUNID.toString();
                                        selectionUNID++;
                                    }
                                    f.properties.selectionTrackingName = name
                                    

                                    selectedFeaturesJSON[layer.name].geoJSON.addGeoJson(f);
                                    selectedFeaturesJSON[layer.name].rawGeoJSON[name]= f;
                                });
                                updateSelectedAreasNameList();    
    
                                $('#'+spinnerID + '3').hide();
                                $('#select-features-list-spinner').hide();
                                updateSelectedAreaArea();
                            })
                        }
                    }
                
                })
            }   
        };
        //Add layer to query object if it can be queried
        if(layer.canQuery){
          queryObj[queryID] = {'visible':layer.visible,'queryItem':layer.queryItem,'queryDict':layer.viz.queryDict,'type':layer.layerType,'name':layer.name};  
        }
		incrementOutstandingGEERequests();

		//Handle creating GEE map services
		function getGEEMapServiceCallback(eeLayer){
            decrementOutstandingGEERequests();
            $('#' + spinnerID).hide();
            if(layer.viz.isTimeLapse){
                timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs = timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs.filter(timeLapseLayerID => timeLapseLayerID !== id)
                var prop = parseInt((1-timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs.length /timeLapseObj[layer.viz.timeLapseID].nFrames)*100);
                // $('#'+layer.viz.timeLapseID+'-loading-progress').css('width', prop+'%').attr('aria-valuenow', prop).html(prop+'% frames loaded');   
                $('#'+layer.viz.timeLapseID+ '-collapse-label').css('background',`-webkit-linear-gradient(left, #FFF, #FFF ${prop}%, transparent ${prop}%, transparent 100%)`)
                            
                // $('#'+layer.viz.timeLapseID+'-loading-count').html(`${timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs.length}/${timeLapseObj[layer.viz.timeLapseID].nFrames} layers to load`)
                if(timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs.length === 0){
                    $('#'+layer.viz.timeLapseID+'-loading-spinner').hide();
                    $('#'+layer.viz.timeLapseID+'-year-label').hide();
                    // $('#'+layer.viz.timeLapseID+'-loading-progress-container').hide();
                    $('#'+layer.viz.timeLapseID+ '-collapse-label').css('background',`-webkit-linear-gradient(left, #FFF, #FFF ${0}%, transparent ${0}%, transparent 100%)`)
                            
                    // $('#'+layer.viz.timeLapseID+'-icon-bar').show();
                    // $('#'+layer.viz.timeLapseID+'-time-lapse-layer-range-container').show();
                    $('#'+layer.viz.timeLapseID+'-toggle-checkbox-label').show();
                    
                    
                    timeLapseObj[layer.viz.timeLapseID].isReady = true;
                };
            }
            $('#' + visibleLabelID).show();
            
            if(layer.currentGEERunID === geeRunID){
                if(eeLayer === undefined){
                    loadFailure();
                }
                else{
                    //Set up GEE map service
                    var MAPID = eeLayer.mapid;
                    var TOKEN = eeLayer.token;
                    layer.highWaterMark = 0;
                    var tileIncremented = false;
                    var eeTileSource = new ee.layers.EarthEngineTileSource(eeLayer);
                    // console.log(eeTileSource)
                    layer.layer = new ee.layers.ImageOverlay(eeTileSource)
                    var overlay = layer.layer;
                    //Set up callback to keep track of tile downloading
                    layer.layer.addTileCallback(function(event){

                        event.count = event.loadingTileCount;
                        if(event.count > layer.highWaterMark){
                            layer.highWaterMark = event.count;
                        }

                        layer.percent = 100-((event.count / layer.highWaterMark) * 100);
                        if(event.count ===0 && layer.highWaterMark !== 0){layer.highWaterMark = 0}

                        if(layer.percent !== 100){
                            layer.loading = true;
                            $('#' + spinnerID+'2').show();
                            if(!tileIncremented){
                                incrementGEETileLayersLoading();
                                tileIncremented = true;
                                if(layer.viz.isTimeLapse){
                                    timeLapseObj[layer.viz.timeLapseID].loadingTilesLayerIDs.push(id);

                                }
                            }
                        }else{
                            layer.loading = false;
                            $('#' + spinnerID+'2').hide();
                            decrementGEETileLayersLoading();
                            if(layer.viz.isTimeLapse){
                                    timeLapseObj[layer.viz.timeLapseID].loadingTilesLayerIDs = timeLapseObj[layer.viz.timeLapseID].loadingTilesLayerIDs.filter(timeLapseLayerID => timeLapseLayerID !== id)
                
                                }
                            tileIncremented = false;
                        }
                        //Handle the setup of layers within a time lapse
                        if(layer.viz.isTimeLapse){
                            var loadingTimelapseLayers = Object.values(layerObj).filter(function(v){return v.loading && v.viz.isTimeLapse && v.whichLayerList === layer.whichLayerList});
                            var loadingTimelapseLayersYears = loadingTimelapseLayers.map(function(f){return [f.viz.year,f.percent].join(':')}).join(', ');
                            var notLoadingTimelapseLayers = Object.values(layerObj).filter(function(v){return !v.loading && v.viz.isTimeLapse && v.whichLayerList === layer.whichLayerList});
                            var notLoadingTimelapseLayersYears = notLoadingTimelapseLayers.map(function(f){return [f.viz.year,f.percent].join(':')}).join(', ');
                            $('#'+layer.viz.timeLapseID + '-message-div').html('Loading:<br>'+loadingTimelapseLayersYears+'<hr>Not Loading:<br>'+notLoadingTimelapseLayersYears);
                            var propTiles = parseInt((1-(timeLapseObj[layer.viz.timeLapseID].loadingTilesLayerIDs.length/timeLapseObj[layer.viz.timeLapseID].nFrames))*100);
                            // $('#'+layer.viz.timeLapseID+'-loading-progress').css('width', propTiles+'%').attr('aria-valuenow', propTiles).html(propTiles+'% tiles loaded');
                            $('#'+layer.viz.timeLapseID+ '-loading-gear').show();
                            
                            $('#'+layer.viz.timeLapseID+ '-collapse-label').css('background',`-webkit-linear-gradient(90deg, #FFF, #FFF ${propTiles}%, transparent ${propTiles}%, transparent 100%)`)
                            if(propTiles < 100){
                                // console.log(propTiles)
                                // if(timeLapseObj[layer.viz.timeLapseID] === 'play'){
                                // pauseButtonFunction();  
                                // }
                            }else{
                                $('#'+layer.viz.timeLapseID+ '-loading-gear').hide();
                            }
                        }

                        // var loadingLayers = Object.values(layerObj).filter(function(v){return v.loading});
                        // console.log(loadingLayers);
                        updateProgress();
                        // console.log(event.count);
                        // console.log(inst.highWaterMark);
                        // console.log(event.count / inst.highWaterMark);
                        // console.log(layer.percent)
                    });
                    if(layer.visible){
                            layer.map.overlayMapTypes.setAt(layer.layerId, layer.layer);
                            $('#'+layer.legendDivID).show();
                            layer.rangeOpacity = layer.opacity; 
                            
                            layer.layer.setOpacity(layer.opacity); 
                        }else{
                          $('#'+layer.legendDivID).hide();
                          layer.rangeOpacity = 0;
                          
                        }
                        setRangeSliderThumbOpacity(); 
                }
                
            }
        }
        function updateTimeLapseLoadingProgress(){
            var loadingTimelapseLayers = Object.values(layerObj).filter(function(v){return v.loading && v.viz.isTimeLapse && v.whichLayerList === layer.whichLayerList}).length;
            var notLoadingTimelapseLayers = Object.values(layerObj).filter(function(v){return !v.loading && v.viz.isTimeLapse && v.whichLayerList === layer.whichLayerList}).length;
            var total = loadingTimelapseLayers+notLoadingTimelapseLayers
            var propTiles = (1-(loadingTimelapseLayers/timeLapseObj[layer.viz.timeLapseID].nFrames))*100
            
            $('#'+layer.viz.timeLapseID+ '-collapse-label').css('background',`-webkit-linear-gradient(0deg, #FFF, #FFF ${propTiles}%, transparent ${propTiles}%, transparent 100%)`)
            if(propTiles < 100){
                $('#'+layer.viz.timeLapseID+ '-loading-gear').show();
                // console.log(propTiles)
                // if(timeLapseObj[layer.viz.timeLapseID] === 'play'){
                // pauseButtonFunction();  
                // }
            }else{
                $('#'+layer.viz.timeLapseID+ '-loading-gear').hide();
            }
            }
        //Handle alternative GEE tile service format
        function geeAltService(eeLayer){
            decrementOutstandingGEERequests();
            $('#' + spinnerID).hide();
            if(layer.viz.isTimeLapse){
                timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs = timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs.filter(timeLapseLayerID => timeLapseLayerID !== id)
                var prop = parseInt((1-timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs.length /timeLapseObj[layer.viz.timeLapseID].nFrames)*100);
                // $('#'+layer.viz.timeLapseID+'-loading-progress').css('width', prop+'%').attr('aria-valuenow', prop).html(prop+'% frames loaded');   
                $('#'+layer.viz.timeLapseID+ '-collapse-label').css('background',`-webkit-linear-gradient(left, #FFF, #FFF ${prop}%, transparent ${prop}%, transparent 100%)`)
                            
                // $('#'+layer.viz.timeLapseID+'-loading-count').html(`${timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs.length}/${timeLapseObj[layer.viz.timeLapseID].nFrames} layers to load`)
                if(timeLapseObj[layer.viz.timeLapseID].loadingLayerIDs.length === 0){
                    $('#'+layer.viz.timeLapseID+'-loading-spinner').hide();
                    $('#'+layer.viz.timeLapseID+'-year-label').hide();
                    // $('#'+layer.viz.timeLapseID+'-loading-progress-container').hide();
                    $('#'+layer.viz.timeLapseID+ '-collapse-label').css('background',`-webkit-linear-gradient(left, #FFF, #FFF ${0}%, transparent ${0}%, transparent 100%)`)
                            
                    // $('#'+layer.viz.timeLapseID+'-icon-bar').show();
                    // $('#'+layer.viz.timeLapseID+'-time-lapse-layer-range-container').show();
                    $('#'+layer.viz.timeLapseID+'-toggle-checkbox-label').show();
                    
                    
                    timeLapseObj[layer.viz.timeLapseID].isReady = true;
                };
            }
            $('#' + visibleLabelID).show();
            
            if(layer.currentGEERunID === geeRunID){
                if(eeLayer === undefined){
                    loadFailure();
                }
                else{
                    const tilesUrl = eeLayer.urlFormat;
                    
                    var getTileUrlFun = function(coord, zoom) {
                    let url = tilesUrl
                                .replace('{x}', coord.x)
                                .replace('{y}', coord.y)
                                .replace('{z}', zoom);
                    if(!layer.loading){
                        layer.loading = true;
                        layer.percent = 10;
                        $('#' + spinnerID+'2').show();
                        updateGEETileLayersDownloading();
                        updateProgress();
                        if(layer.viz.isTimeLapse){
                            updateTimeLapseLoadingProgress();  
                        }
                    }
                    
                    return url
                }
                    layer.layer = new google.maps.ImageMapType({
                            getTileUrl:getTileUrlFun
                        })
                    layer.layer.addListener('tilesloaded',function(){
                        layer.percent = 100;
                        layer.loading = false;
                        $('#' + spinnerID+'2').hide();
                        updateGEETileLayersDownloading();
                        updateProgress();
                        if(layer.viz.isTimeLapse){
                            updateTimeLapseLoadingProgress();  
                        }
                    })
                    
                    
                    if(layer.visible){
                        layer.map.overlayMapTypes.setAt(layer.layerId, layer.layer);
                        layer.rangeOpacity = layer.opacity; 
                        layer.layer.setOpacity(layer.opacity);
                        $('#'+layer.legendDivID).show();
                         }else{layer.rangeOpacity = 0;}
                         $('#' + spinnerID).hide();
                        $('#' + visibleLabelID).show();

                        setRangeSliderThumbOpacity();
                }
            }
        }
        //Asynchronous wrapper function to get GEE map service
        layer.mapServiceTryNumber = 0;
        function getGEEMapService(){
            // layer.item.getMap(layer.viz,function(eeLayer){getGEEMapServiceCallback(eeLayer)});
            layer.item.getMap(layer.viz,function(eeLayer){
                if(eeLayer === undefined && layer.mapServiceTryNumber <=1){
                    queryObj[queryID].queryItem = layer.item;
                    layer.item = layer.item.visualize();
                        getGEEMapService();
                }else{
                    geeAltService(eeLayer);
                }  
            });

            // layer.item.getMap(layer.viz,function(eeLayer){
                // console.log(eeLayer)
                // console.log(ee.data.getTileUrl(eeLayer))
            // })
            layer.mapServiceTryNumber++;
        };
        getGEEMapService();

    //Handle different vector formats
	}else if(layer.layerType === 'geeVector' || layer.layerType === 'geoJSONVector'){
        if(layer.canQuery){
          queryObj[queryID] = {'visible':layer.visible,'queryItem':layer.queryItem,'queryDict':layer.viz.queryDict,'type':layer.layerType,'name':layer.name};  
        }
		incrementOutstandingGEERequests();
        //Handle adding geoJSON to map
		function addGeoJsonToMap(v){
			$('#' + spinnerID).hide();
			$('#' + visibleLabelID).show();

			if(layer.currentGEERunID === geeRunID){
                if(v === undefined){loadFailure()}
				layer.layer = new google.maps.Data();
		        layer.layer.setStyle(layer.viz);
		      
		      	layer.layer.addGeoJson(v);
                if(layer.viz.clickQuery){
                    map.addListener('click',function(){
                        infowindow.setMap(null);
                    })
                    layer.layer.addListener('click', function(event) {
                        console.log(event);
                        infowindow.setPosition(event.latLng);
                        var infoContent = `<table class="table table-hover bg-white">
                            <tbody>`
                        var info = event.feature.h;
                        Object.keys(info).map(function(name){
                            var value = info[name];
                            infoContent +=`<tr><th>${name}</th><td>${value}</td></tr>`;
                        });
                        infoContent +=`</tbody></table>`;
                        infowindow.setContent(infoContent);
                        infowindow.open(map);
                    })  
                }
		      	featureObj[layer.name] = layer.layer
		      	// console.log(this.viz);
		      
		      	if(layer.visible){
		        	layer.layer.setMap(layer.map);
		        	layer.rangeOpacity = layer.viz.strokeOpacity;
		        	layer.percent = 100;
		        	updateProgress();
		        	$('#'+layer.legendDivID).show();
		      	}else{
		        	layer.rangeOpacity = 0;
		        	layer.percent = 0;
		        	$('#'+layer.legendDivID).hide();
		      		}
		      	setRangeSliderThumbOpacity();
		      	}
  		}
  		if(layer.layerType === 'geeVector'){
            decrementOutstandingGEERequests();
  			layer.item.evaluate(function(v){addGeoJsonToMap(v)})
  		}else{decrementOutstandingGEERequests();addGeoJsonToMap(layer.item)}
	//Handle non GEE tile services	
	}else if(layer.layerType === 'tileMapService'){
		layer.layer = new google.maps.ImageMapType({
                getTileUrl: layer.item,
                tileSize: new google.maps.Size(256, 256),
                // tileSize: new google.maps.Size($('#map').width(),$('#map').height()),
                maxZoom: 15
            
            })
		if(layer.visible){
        	
        	layer.map.overlayMapTypes.setAt(layer.layerId, layer.layer);
        	layer.rangeOpacity = layer.opacity; 
        	layer.layer.setOpacity(layer.opacity); 
             }else{layer.rangeOpacity = 0;}
             $('#' + spinnerID).hide();
			$('#' + visibleLabelID).show();
			setRangeSliderThumbOpacity();
                
	//Handle dynamic map services
	}else if(layer.layerType === 'dynamicMapService'){
		function groundOverlayWrapper(){
	      if(map.getZoom() > layer.item[1].minZoom){
	        return getGroundOverlay(layer.item[1].baseURL,layer.item[1].minZoom)
	      }
	      else{
	        return getGroundOverlay(layer.item[0].baseURL,layer.item[0].minZoom)
	      }
	      };
	      function updateGroundOverlay(){
                if(layer.layer !== null && layer.layer !== undefined){
                    layer.layer.setMap(null);
                }
                
                layer.layer =groundOverlayWrapper();
                if(layer.visible){
                	layer.layer.setMap(map);
                	layer.percent = 100;
					updateProgress();
                	groundOverlayOn = true
              		$('#'+layer.legendDivID).show();
                	layer.layer.setOpacity(layer.opacity);
                	layer.rangeOpacity = layer.opacity;
                	
                }else{layer.rangeOpacity = 0};
                   setRangeSliderThumbOpacity();          

            };
            updateGroundOverlay();
            // if(layer.visible){layer.opacity = 1}
                // else{this.opacity = 0}
            google.maps.event.addListener(map,'zoom_changed',function(){updateGroundOverlay()});

            google.maps.event.addListener(map,'dragend',function(){updateGroundOverlay()});
             $('#' + spinnerID).hide();
			$('#' + visibleLabelID).show();
			setRangeSliderThumbOpacity();
	}
}


