var center;var globalChartValues;
var chartTextColor = '#FFF';
var mapDiv = document.getElementById('map');
function updateProgress(pct) {
    var elem = document.getElementById("Bar"); 
    elem.style.width = pct + '%'; 
        
}
function sortFunction(a, b) {
    if (a[0] === b[0]) {
        return 0;
    }
    else {
        return (a[0] < b[0]) ? -1 : 1;
    }
}
function downloadURI() {
	if(uri != null && uri != undefined){
	  var link = document.createElement("a");
	  link.download = uriName + '.png';
	  link.href = uri;
	  link.click();
	  // document.body.removeChild(link);
	    delete link;
}
}
function downloadURI2(uri,uriName) {
	if(uri != null && uri != undefined){
	  var link = document.createElement("a");
	  link.download = uriName + '.png';
	  link.href = uri;
	  link.click();
	  // document.body.removeChild(link);
	    delete link;
}
}
for(var i = 0;i< 50;i++){
	eval("var dataTableT"+i+";")
	// eval("chartPopoutDiv"+i+".id = 'popoutDiv'+i")
};
var popoutI = 0;
var queryPopout = document.createElement('div');

var chartIDDict = {'time':'Year','id':'ID'}
function openDivInNewTab(dataTableT){
	// print('Opening: '	+dataTableT);
	// title = 'test';
	// xAxisLabel = 'test';
	// var chartOptions = {
	// 		title: title,
	// 		titleTextStyle: { color:chartTextColor},
	// 		height: 600,
	// 		width: 1200,
	// 		legend: { position: 'bottom',textStyle:{color: chartTextColor}},
	// 		hAxis:{title:chartIDDict[xAxisLabel],titleTextStyle:{color: chartTextColor},textStyle:{color: chartTextColor}},
	// 		vAxis:{title:'Values',titleTextStyle:{color: chartTextColor},textStyle:{color: chartTextColor}},
	// 		backgroundColor: { fill: "#333" }
	// 		}
						
	// var popoutDiv = document.createElement('DIV')
	// var time = (new Date()).getTime();
	// var id = 'div-' + time;
	var id = 'query-container'
	// popoutDiv.id = id;
	// var chart = new google.visualization.LineChart(popoutDiv);
	// chart.draw(dataTableT, chartOptions);

	
  	var wi = window.open();
  	var html = $('#'+id).html();
  	$(wi.document.body).html(html);
}
function clone(obj) {
    if (null == obj || "object" != typeof obj) return obj;
    var copy = obj.constructor();
    for (var attr in obj) {
        if (obj.hasOwnProperty(attr)) copy[attr] = obj[attr];
    }
    return copy;
}


var  getQueryImages = function(lng,lat){
	var lngLat = [lng, lat];
	popoutI = 0;
	var outDict = {};
	var coordNameEnd = ' lng: '+lng.toFixed(3).toString() + ' lat: '+lat.toFixed(3).toString()
	$('#query-container').text('');
	$('#query-container').append('Queried values for'+coordNameEnd);
	var keys = Object.keys(queryObj);
	var keysToShow = [];
	keys.map(function(k){
		var q = queryObj[k];
		if(q[0]){keysToShow.push(k);}
	})

	var lastKey = keysToShow[keysToShow.length-1];

	keysToShow.map(function(k){
		var q = queryObj[k];
	

		if(q[0]){
			print('type');
			// var eeType = q[1].getInfo().type;
			q[1].evaluate(function(eeType){
				eeType = eeType.type;
			
			print(eeType);
			if(eeType === 'Image'){
				var img = ee.Image(q[1]);
				var value = ee.Feature(img.sampleRegions(ee.FeatureCollection([ee.Feature(ee.Geometry.Point(lngLat))]), null, 30, 'EPSG:4326').first()).evaluate(function(value){
					if(value != null){
						// console.log(value)
					value = value['properties'];

					// if(Object.keys(value).length > 1){value = null;show = false;}
					// else{value = Object.values(value)[0];}
					
				};
				
					if(value === null){
					$('#query-container').append("<div style='width:100%;height:2px;border-radius:5px;margin:2px;background-color:#fff'></div>" +k+ ': null <br>');
					}
					else if(Object.keys(value).length === 1 ){
					$('#query-container').append("<div style='width:100%;height:2px;border-radius:5px;margin:2px;background-color:#fff'></div>" +k+ ': '+JSON.stringify(Object.values(value)[0]) + "<br>");
					}
					else{
						$('#query-container').append("<div style='width:100%;height:2px;border-radius:5px;margin:2px;background-color:#fff'></div>" +k+ ':<br>');
						Object.keys(value).map(function(kt){
							var v = value[kt].toFixed(2).toString();
							$('#query-container').append( kt+ ': '+v + "<br>");
						})
					}

				
				
				if(k == lastKey){
					map.setOptions({draggableCursor:'help'});
	 			map.setOptions({cursor:'help'});
				}
				})
			
			
			}
			else if(eeType === 'ImageCollection'){
				var img = ee.ImageCollection(q[1]);
				
				img.getRegion(ee.Geometry.Point(lngLat), 30, 'EPSG:4326').evaluate(function(values){
					if(values.length > 1){
						var dataTableT = values;

						var bandNames = ee.Image(img.first()).bandNames().getInfo()
						var header = values[0]
						values = values.slice(1,values.length);
						
						var xAxisLabel = 'time';
						if(values[0][header.indexOf('time')] === null){
							xAxisLabel = 'id';	
						}
						
						var bandIndices = bandNames.map(function(bn){return header.indexOf(bn)});

						var pullIndices = [header.indexOf(xAxisLabel)];
						pullIndices = pullIndices.concat(bandIndices)
						dataTableT = dataTableT.map(function(row){
							var outLine = pullIndices.map(function(i){return row[i]})
							
							return outLine})
						if(xAxisLabel === 'time'){
							dataTableT = dataTableT.map(function(row){
								var t = row[0];
								row[0] = new Date(t);
								return row
							})
						}
					
						
						var data = google.visualization.arrayToDataTable(dataTableT);
						var time = (new Date()).getTime();
		     			var id = 'div-' + time;
		     			var popout_id ='div-popout-' + time; 
		     			
		     			
		     			
		     			var chartOptions = {
								title: k + coordNameEnd,
								titleTextStyle: { color:chartTextColor},
								height: '500',
								width: '100%',
								chartArea: {width:'85%',height:'80%'},
								legend: { position: 'bottom',textStyle:{color: chartTextColor}},
								hAxis:{title:chartIDDict[xAxisLabel],titleTextStyle:{color: chartTextColor},textStyle:{color: chartTextColor}},
								vAxis:{title:'Values',titleTextStyle:{color: chartTextColor},textStyle:{color: chartTextColor}},
								backgroundColor: { fill: "#333" }
								}
						// var chartOptionsPopout= clone(chartOptions);
						// chartOptionsPopout.height = 600;
						// chartOptionsPopout.width = 1200;
		     			
						$('#query-container').append("<div style='width:100%;height:2px;border-radius:5px;margin:2px;background-color:#fff'></div>");
						// $('#query-popout-container').append("<div style='width:100%;height:2px;border-radius:5px;margin:2px;background-color:#fff'></div>");
		     	// 		$('#query-container').append('<a href="https://earthengine.google.com/" target="_blank">\
							 // <img src="images/popout.png" alt="Powered by Google Earth Engine" style="height:20px;width:20px;right:0%;background-color:rgba(200,200,200,0.7);border-radius: 5px;"\
							 //      href="#" class "dual-range-slider-container" rel="txtTooltip" data-toggle="tooltip" data-placement="top" title="Click to learn more about Google Earth Engine">\
							 //    </a>')
						var popoutDivID = 'popoutDiv'+popoutI
						eval('dataTableT'+popoutI + ' = dataTableT');
						// eval('var chartPopout = new google.visualization.LineChart(chartPopoutDiv'+popoutI+');');
						// chartPopout.draw(data, chartOptionsPopout);
						var funString = 'openDivInNewTab()';
						print(funString	);
						$("#query-container").append('<input type="image" onclick = "'+funString	+'" style="height:20px;width:20px;" src="images/popout.png" alt="Powered by Google Earth Engine" />');
		     			
		     			// $("#query-container").append('<button class="button" onclick="openDivInNewTab('+id+');" style= "position:inline-block;float:right;">Close Chart')
		     			var chartDiv = document.getElementById('query-container').appendChild(document.createElement('DIV'));
		     			chartDiv.id = id
		     			// var chartPopoutDiv = document.getElementById('query-popout-container').appendChild(document.createElement('DIV'));
		     			// chartPopoutDiv.id = popout_id
		     			$('#query-container').append("<div style='width:100%;height:2px;border-radius:5px;margin:2px;background-color:#fff'></div>");
		     			// $('#query-popout-container').append("<div style='width:100%;height:2px;border-radius:5px;margin:2px;background-color:#fff'></div>");
		     			
		     			
		     			
		     			

						var chart = new google.visualization.LineChart(chartDiv);
						chart.draw(data, chartOptions);
						$(window).resize(function(){
  						drawChart();
							});
						// var chartPopout = new google.visualization.LineChart(chartPopoutDiv);
						// chartPopout.draw(data, chartOptions);
						
						popoutI ++;
						// var uriT = 'uri'+time;
		    //  			var uriNameT = 'uriName'+time;
		    //  			var csvNameT = 'csvName'+time;
		    //  			var dataTableNameT = 'dataTableT' + time;
		    //  			eval("var "+uriT+" = chart.getImageURI();");
						// eval("var "+uriNameT+" = k+' ' +lng.toFixed(4).toString() + ' ' + lat.toFixed(4).toString() ;");
						// eval("var "+csvNameT+" = uriName + '.csv';");
						// eval("var "+dataTableNameT+ " = dataTableT;");

						// $('#query-container').append('<br><br>')

	 	   //     			$('#query-container').append('<button class="button" onclick="downloadURI2('+uriT+','+uriNameT+');" style= "position:inline-block;">Download PNG')
	 	   //     			$('#query-container').append('<button class="button" onclick="exportToCsv('+csvNameT+', '+dataTableNameT+');" style= "position:inline-block;">Download CSV')
	        			
		        // document.getElementById('curve_chart').style.display = 'inline-block';
		       
		        // eval("var chart = new google.visualization."+chartType+"(document.getElementById('curve_chart'));")
	    			}
					// if(k == lastKey){
					// 	map.setOptions({draggableCursor:'help'});
		 		// 		map.setOptions({cursor:'help'});
					// }
				})
				
			}
			
			})

		}

	})
	
	
	
	
}
function startQuery(){
	map.setOptions({draggableCursor:'help'});
 	map.setOptions({cursor:'help'});
	google.maps.event.addDomListener(mapDiv,"dblclick", function (e) {
			map.setOptions({draggableCursor:'progress'});
			map.setOptions({cursor:'progress'});
			print('Map was double clicked');
			var x =e.clientX;
        	var y = e.clientY;console.log(x);
        	center =point2LatLng(x,y);

			// center = e.latLng;
			marker.setMap(null);
			marker=new google.maps.Circle({
  				center:{lat:center.lat(),lng:center.lng()},
  				radius:plotRadius,
  				strokeColor: '#FF0',
  				fillOpacity:0
  				});

			marker.setMap(map);
			sleep(2000);
			getQueryImages(center.lng(),center.lat());


		})
	document.getElementById('query-container').style.display = 'block';

}
function stopQuery(){
	print('stopping');
	map.setOptions({draggableCursor:'hand'});
	map.setOptions({cursor:'hand'});
	$('#query-container').text('');

	google.maps.event.clearListeners(mapDiv, 'dblclick');
	map.setOptions({cursor:'hand'});
	document.getElementById('query-container').style.display = 'none';
}
function getImageCollectionValuesForCharting(pt){
	
	// var timeSeries = years.map(function(yr){
	// 	var imageT = l5s.filterDate(ee.Date.fromYMD(yr,1,1),ee.Date.fromYMD(yr,12,31)).median().set('system:time_start',ee.Date.fromYMD(yr,6,1).millis());
	// 	return imageT
	// })
	// timeSeries = ee.ImageCollection.fromImages(timeSeries);
	var icT = ee.ImageCollection(chartCollection.filterBounds(pt));
	var tryCount = 2;
	// print(icT.getRegion(pt.buffer(plotRadius),plotScale))
	try{var allValues = icT.getRegion(pt,null,'EPSG:5070',[30,0,-2361915.0,0,-30,3177735.0]).evaluate();
		print(allValues)
		return allValues}
	catch(err){showMessage('Charting error',err.message)};//reRun();setTimeout(function(){icT.getRegion(pt.buffer(plotRadius),plotScale).getInfo();},5000)}
	

}
Date.prototype.yyyymmdd = function() {
  var mm = this.getMonth() + 1; // getMonth() is zero-based
  var dd = this.getDate();

  return [this.getFullYear(), !mm[1] && '0', mm, !dd[1] && '0', dd].join(''); // padding
};
function getDataTable(pt){
	// var chartScale = plotScale;
	// var chartPtSize = plotRadius;
	// addToMap(pt.buffer(chartPtSize));

	
	var values = getImageCollectionValuesForCharting(pt);
	globalChartValues	 = values;
	// var values = imageCollectionForCharting.getRegion(pt.buffer(chartPtSize),chartScale).getInfo();
	
	if(chartIncludeDate){var startColumn = 3}else{var startColumn = 4};
	var header = values[0].slice(startColumn);

	values = values.slice(1).map(function(v){return v.slice(startColumn)}).sort(sortFunction);




	print(values)
	if(chartIncludeDate){
	values = values.map(function(v){
			  var d = [new Date(v[0])];
			  v.slice(1).map(function(vt){d.push(vt)})
			  return d})
	}

	var forChart = [header];
	values.map(function(v){forChart.push(v)});
	
	return forChart
}

function changeChartType(newType){
	newType.checked = true;
	$(newType).checked = true;
	chartType = newType.value;
	uriName = chartType + ' ' +center.lng().toFixed(4).toString() + ' ' + center.lat().toFixed(4).toString() + ' Res: ' +plotScale.toString() + '(m) Radius: ' + plotRadius	.toString() + '(m)';
	csvName = uriName + '.csv'
	document.getElementById('curve_chart').style.display = 'none';
	setTimeout(function(){updateProgress(80);},0);
	Chart()
}

function Chart(){
	document.getElementById('curve_chart').style.display = 'none';

	// updateProgress(75);
	
	var cssClassNames = {
    'headerRow': 'googleChartTable',
    'tableRow': 'googleChartTable',
    'oddTableRow': 'googleChartTable',
    'selectedTableRow': 'googleChartTable',
    'hoverTableRow': 'googleChartTable',
    'headerCell': 'googleChartTable',
    'tableCell': 'googleChartTable',
    'rowNumberCell': 'googleChartTable'};

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

	           width: 800, 
	           height:350,
	           bar: {groupWidth: "100%"},
	           explorer: {  actions: [] },
	            chartArea: {left:'5%',top:'10%',width:'75%',height:'70%'},
	            legendArea:{width:'20%'},
	           backgroundColor: { fill: "#888" }

	        };
	        var tableOptions = {width: 800, 
	           height:350,
	            'allowHtml': true,
	            'cssClassNames': cssClassNames}
			var chartOptionsT;
			// chartType = 'Table'
			setTimeout(function(){updateProgress(80);},0);
			dataTableT = null;
			dataTableT = CopyAnArray (dataTable)
			if(chartType === 'Histogram' || chartType === 'ScatterChart' && dataTable[0][0] === 'time'){
				dataTableT = dataTableT.map(function(row){return row.slice(1)})
			} 
			else if(chartType === 'Table'){
			if(tableConverter != null && tableConverter != undefined){
				dataTableT	= tableConverter(dataTableT)
			}
			
				}
			// else{dataTableT = dataTableT.slice(0)};
			chartOptionsT = chartOptions;
			if(chartType === 'Histogram'){chartOptionsT.hAxis.title = 'Value'}
				else if(chartType === 'ScatterChart'){chartOptionsT.hAxis.title = dataTableT[0][0];chartOptionsT.opacity = 0.1}
				else if(chartType === 'Table'){chartOptionsT = tableOptions}
				else{chartOptionsT.hAxis.title = 'Time'};
			
			
			var data = google.visualization.arrayToDataTable(dataTableT);
	       	console.log('data');
	       	console.log(dataTableT);

	        document.getElementById('curve_chart').style.display = 'inline-block';
	       
	        eval("var chart = new google.visualization."+chartType+"(document.getElementById('curve_chart'));")



	        
	       google.visualization.events.addListener(chart, 'ready', function () {
    		if(chartType != 'Table'){uri = chart.getImageURI();}

    		// printImage(imageUri);
    		// downloadURI( "helloWorld.png");
    		// do something with the image URI, like:
    		
			});
	       setTimeout(function(){updateProgress(90);},0);
	        chart.draw(data, chartOptionsT);
	        setTimeout(function(){updateProgress(100);},0);
			
			$('#curve_chart').append('<br><br>')

 	       	if(chartType != 'Table'){$("#curve_chart").append('<button class="button" onclick="downloadURI();" style= "position:inline-block;">Download PNG')}
 	       	$("#curve_chart").append('<button class="button" onclick="exportToCsv(csvName, dataTableT);" style= "position:inline-block;">Download CSV')
 	       	// $('#curve_chart').append('<p></p>')
 	       	if(chartTypeOptions){
 	       		chartTypes.map(function(ct){
 	       			$("#curve_chart").append('<input class="button" type="button"  value = "'+ct+'" onclick = "changeChartType(this);" >')
 	       		})
 	       		// $("#curve_chart").append(
 	       		// 					'<input class="button" type="button"  value = "LineChart" onclick = "changeChartType(this);" >\n\
 	       		// 					<input class="button" type="button" value = "ScatterChart" onclick = "changeChartType(this);" >\n\
 	       		// 					<input class="button" type="button" value = "Histogram" onclick = "changeChartType(this);" >\n\
 	       		// 					<input class="button" type="button" value = "Table" onclick = "changeChartType(this);" >\n\
 	       		// 					<input class="button" type="button"  value = "ColumnChart" onclick = "changeChartType(this);">')
 	       
 	       	}
 	       	$("#curve_chart").append('<button class="button" onclick="closeChart();" style= "position:inline-block;float:right;">Close Chart')
 	       	
 			map.setOptions({draggableCursor:'help'});
 			map.setOptions({cursor:'help'});
			// $("#curve_chart").append('<variable-range id = "graphControls" name="Chart plot radius (m)" var="plotRadius" default="15" min="30" max="300" step = "30"></variable-range>');
 	       	// $("input[name='gender']").change(function(){this.checked = true;changeChartType(this);})
 	       	// $("#curve_chart").append('<label class="radio-inline"><input type="radio" name="chartTypeR">Option 2</label>')
 	       	// $("#curve_chart").append('<label class="radio-inline"><input type="radio" name="chartTypeR">Option 3</label>')

	        // $('#download-spinner').css({'visibility': 'hidden'});
        // updateProgress(100);
}
function chartIt(){

		// modal.style.display = "block";

		// $('#download-spinner').css({'visibility': 'visible'});
         // $('#download-spinner').attr('src', 'images/spinnerGT5.gif');
         
    
    	
    	


		var pt = ee.Geometry.Point([center.lng(),center.lat()]);
		var icT = ee.ImageCollection(chartCollection.filterBounds(pt));
		try{
		icT.getRegion(pt.buffer(plotRadius),plotScale).evaluate(
			function(values){
					// globalChartValues	 = values;
	// var values = imageCollectionForCharting.getRegion(pt.buffer(chartPtSize),chartScale).getInfo();
	
	if(chartIncludeDate){var startColumn = 3}else{var startColumn = 4};
	print('Extracted values:',values)
	if(values.length !== 1){
		var header = values[0].slice(startColumn);

	values = values.slice(1).map(function(v){return v.slice(startColumn)}).sort(sortFunction);




	
	if(chartIncludeDate){
	values = values.map(function(v){
			  // var d = [new Date(v[0])];
			  // v.slice(1).map(function(vt){d.push(vt)})
			  v[0] = (new Date(v[0]).getYear()+1900).toString();
			  return v;
			})
	}

	var forChart = [header];
	values.map(function(v){forChart.push(v)});
	dataTable	=forChart;
	
	
		uriName = chartType + ' for lng ' +center.lng().toFixed(4).toString() + ', lat ' + center.lat().toFixed(4).toString();// + ' Res: ' +plotScale.toString() + '(m) Radius: ' + plotRadius	.toString() + '(m)';
		csvName = uriName + '.csv'
		
	     
	    // interval2(Chart, 1000, 1)
		Chart();
		// console.log(dataTable)

			}
	else{
		// print('Plot radius too small.  Increasing radius by 5 m');
		showMessage('Charting error','Clicked between two pixels.  Try double clicking centered on a pixel')
		// plotRadius	+=5;
		// chartIt()
		};
		});
	}
	
	
		catch(err){showMessage('Charting error',err.message)};//reRun();setTimeout(function(){icT.getRegion(pt.buffer(plotRadius),plotScale).getInfo();},5000)}
	

		// dataTable = getDataTable(pt);
		
		// map.setOptions({draggableCursor:'help'});
	
		// uriName = chartType + ' ' +center.lng().toFixed(4).toString() + ' ' + center.lat().toFixed(4).toString() + ' Res: ' +plotScale.toString() + '(m) Radius: ' + plotRadius	.toString() + '(m)';
		// csvName = uriName + '.csv'
		
	     
	 //    interval2(Chart, 1000, 1)
		// Chart();
		
		
}
// var cT = 
var marker=new google.maps.Circle({
  				center:{lat:45,lng:-111},
  				radius:5
  				});
function drawChart() {
		// if(chartType.toLowerCase() === 'histogram'){chartIncludeDate = false};
		// document.getElementById('charting-parameters').style.display = 'inline-block';
		$("#charting-parameters").slideDown();
		

		 map.setOptions({draggableCursor:'help'});
		google.maps.event.addDomListener(mapDiv,"dblclick", function (e) {
			closeChart();
			print('Map was double clicked');
			var x =e.clientX;
        	var y = e.clientY;console.log(x);
        	center =point2LatLng(x,y);

			// center = e.latLng;
			marker.setMap(null);
			marker=new google.maps.Circle({
  				center:{lat:center.lat(),lng:center.lng()},
  				radius:plotRadius,
  				strokeColor: '#FF0',
  				fillOpacity:0
  				});

			marker.setMap(map);

			map.setOptions({draggableCursor:'progress'});
			updateProgress(25)
			var p = 25
			// interval2(function(){updateProgress(p);p= p + 10}, 1000, 5)
			setTimeout(function(){chartIt();updateProgress(75);},3000);
			
			// ee.data.newTaskId(null,move);
			// ee.data.newTaskId(null,chartIt);
		
		});
		
		
      }

function closeChart(){

	try{document.getElementById('curve_chart').style.display = 'none';}
	catch(err){console.log('No charts to close')}
	
}
function stopCharting(){
	// document.getElementById('charting-parameters').style.display = 'none';
	$("#charting-parameters").slideUp();
	marker.setMap(null);
	google.maps.event.clearListeners(mapDiv, 'dblclick');
	map.setOptions({draggableCursor:'hand'});
	updateProgress(1)
	closeChart()
}

function exportToCsv(filename, rows) {
        var processRow = function (row) {
            var finalVal = '';
            for (var j = 0; j < row.length; j++) {
                var innerValue = row[j] === null || row[j] === undefined ? '' : row[j].toString();
                if (row[j] instanceof Date) {
                    innerValue = row[j].toLocaleString();
                };
                var result = innerValue.replace(/"/g, '""');
                if (result.search(/("|,|\n)/g) >= 0)
                    result = '"' + result + '"';
                if (j > 0)
                    finalVal += ',';
                finalVal += result;
            }
            return finalVal + '\n';
        };

        var csvFile = '';
        for (var i = 0; i < rows.length; i++) {
            csvFile += processRow(rows[i]);
        }

        var blob = new Blob([csvFile], { type: 'text/csv;charset=utf-8;' });
        if (navigator.msSaveBlob) { // IE 10+
            navigator.msSaveBlob(blob, filename);
        } else {
            var link = document.createElement("a");
            if (link.download !== undefined) { // feature detection
                // Browsers that support HTML5 download attribute
                var url = URL.createObjectURL(blob);
                link.setAttribute("href", url);
                link.setAttribute("download", filename);
                link.style.visibility = 'hidden';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
        }
    }