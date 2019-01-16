var center;var globalChartValues;
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
function getImageCollectionValuesForCharting(pt){
	
	// var timeSeries = years.map(function(yr){
	// 	var imageT = l5s.filterDate(ee.Date.fromYMD(yr,1,1),ee.Date.fromYMD(yr,12,31)).median().set('system:time_start',ee.Date.fromYMD(yr,6,1).millis());
	// 	return imageT
	// })
	// timeSeries = ee.ImageCollection.fromImages(timeSeries);
	var icT = ee.ImageCollection(chartCollection.filterBounds(pt));
	var tryCount = 2;
	// print(icT.getRegion(pt.buffer(plotRadius),plotScale))
	try{var allValues = icT.getRegion(pt.buffer(plotRadius+1),plotScale).evaluate();
		print(allValues)
		return allValues}
	catch(err){showMessage('Charting error',err)};//reRun();setTimeout(function(){icT.getRegion(pt.buffer(plotRadius),plotScale).getInfo();},5000)}
	

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
	// updateProgress(75);
	var chartTextColor = '#FFF';

	
	chartOptions = {
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
	     	vAxis:{textStyle:{color: '#FFF'},titleTextStyle:{color: chartTextColor}},
	           width: 1400, 
	           height:400,
	           bar: {groupWidth: "100%"},
	           explorer: { },
	           backgroundColor: { fill: "#888" }
	         
	   //         histogram: {
      
    //   maxNumBuckets: 5,
    //   bucketSize: 0.05,
    // }
	        };
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
				else{chartOptionsT.hAxis.title = 'Time'};
			
			print(chartOptionsT.hAxis.title,dataTableT)
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
			$("#curve_chart").append('<button class="button" onclick="closeChart();" style= "position:absolute;vertical-align:top;right:0%;top:0%">X')
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
 	       	
 			map.setOptions({draggableCursor:'help'});
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
	
	
		uriName = chartType + ' ' +center.lng().toFixed(4).toString() + ' ' + center.lat().toFixed(4).toString() + ' Res: ' +plotScale.toString() + '(m) Radius: ' + plotRadius	.toString() + '(m)';
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
	
	
		catch(err){showMessage('Charting error',err)};//reRun();setTimeout(function(){icT.getRegion(pt.buffer(plotRadius),plotScale).getInfo();},5000)}
	

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