var exportOuputName; var submitOutputName;var taskId;
var cancelAllTasks = function(){console.log('yay')};//showMessage('Completed','Tasks cancelled: 0');};
var downloadMetadata = function(){console.log('yay')};
var downloadTraining = function(){console.log('yay')};
var list = [];
var bucketName = 'test-bucket-housman2';//Will need to set permissions for reading and writing using: gsutil acl ch -u AllUsers:W gs://example-bucket and gsutil acl ch -u AllUsers:R gs://example-bucket
var eID = 1;
var exportFC;
///////////////////////////////////////////////////////////////////
var cachedEEExports = null;
    if(typeof(Storage) !== "undefined"){
        cachedEEExports = JSON.parse(localStorage.getItem("cachedEEExports"));
        
    }
    if(cachedEEExports === null){cachedEEExports = {};}
 

function updatePopup(value){
    var tempName = "EE_Export_Image_" + exportScale.toString() + 'm_' +exportCRS;
    var now = Date().split(' ');
    var nowSuffix = now[2]+'_'+now[1]+'_'+now[3]+'_'+now[4]
    exportOutputName = tempName+'_'+nowSuffix; //Add date
    
    document.getElementById('popup-text-input').value = exportOutputName;
}

function makePopup(){
    // document.getElementById('popup-text-input').value = 'testName';
    document.getElementById('popup').style.display = 'block';
    // var exportNameList = JSON.stringify({'ti':'ee.Image(1)'});
    
    var exportKeys = Object.keys(exportImageDict);
    exportKeys.map(function(k){
        var sExport = exportImageDict[k]['shouldExport'];
        if(sExport){
            var outputList = document.querySelector("popup-output-list");
            outputList.insertBefore("<input type='checkbox' checked = true value = '"+k+"'onclick='checkFunction(this);'>"+exportImageDict[k]["name"]+"</label>",outputList.firstChild);
            // $("#popupList").append("<input type='checkbox' checked = true value = '"+k+"'onclick='checkFunction(this);'>"+exportImageDict[k]["name"]+"</label>")
        }
        else{
            // $("#popupList").append("<input type='checkbox'  value = '"+k+"'onclick='checkFunction(this);'>"+exportImageDict[k]["name"]+"</label>")
        }
        // $("#popupList").append('<input type="checkbox" name="image" value="'+k+'" onclick="checkFunction(this)" onchange="checkFunction(this)"> '+k+'<br>');
    })
    
    

}
var selectedExportDict = {};
function checkFunction(v){
    console.log(v.checked +' ' + v.value);
    eval('addToMap(' + exportImageDict[v.value]['image']+')')
    exportImageDict[v.value]['shouldExport'] = v.checked
    console.log(exportImageDict);
}
function closePopup(){
    document.getElementById('export-list').style.display = 'none';
}
function showPopup(){
    document.getElementById('export-list').style.display = 'inline-block';
}
function interval2(func, wait, times){
        var interv = function(w, t){
            return function(){
                if(typeof t === "undefined" || t-- > 0 ){
                    setTimeout(interv, w);
                    try{
                        func.call(null);
                    }
                    catch(e){
                        t = 0;
                        throw e.toString();
                    }
                }
            };
        }(wait, times);

        setTimeout(interv, wait);
    };
////////////////////////////////////////////////
//Function to look for running ee tasks and request cancellation
cancelAllTasks = function(){
    var tasksCancelled = 0;
    var tasksCancelledList = '\nIDs:';
    var taskList = ee.data.getTaskList().tasks;
    taskList.map(function(task){
        if((task.state === 'RUNNING' || task.state === 'READY') &&  Object.keys(cachedEEExports).indexOf(task.id) >-1){
            print('Cancelling task: ' + task.id)
            ee.data.cancelTask(task.id);
            tasksCancelledList = tasksCancelledList +'\n'+ task.id;
            tasksCancelled++;
        }
    })
    // taskCount = 0;
    // updateSpinner();
    showMessage('Cancelling Completed','Tasks cancelled: ' + tasksCancelled.toString() +'\n'+ tasksCancelledList);
    trackExports();
}
downloadMetadata = function(){
    console.log('downloading metadta');
    var url='images/lcms_metadata_beta.pdf';    
    var link=document.createElement('a');
    link.href = url;
    link.download = url.substr(url.lastIndexOf('/') + 1);
    link.click(); 

}
downloadTraining = function(){
   console.log('downloading training');
    var url='images/LCMS_Data_Explorer_exercise1.pdf';    
    var link=document.createElement('a');
    link.href = url;
    link.download = url.substr(url.lastIndexOf('/') + 1);
    link.click();  
}
////////////////////////////////////////////////
function trackExports(){
    exportList = [];
    var taskIDList  = 'Exporting: ';
    taskCount = 0;
    var taskList = ee.data.getTaskList().tasks
    if(taskList.length > 10){taskList = taskList.slice(0,20);}
    

    taskList.map(function(t){

        // if(Object.keys(cachedEEExports).indexOf(t.id) >-1 ){
        //     console.log('adding task to past ee export list')
        //     pastEEExports[t.id] = [t.state,false,t.description];
        //     }
        if(Object.keys(cachedEEExports).indexOf(t.id) >-1){
            var cachedEEExport = cachedEEExports[t.id]

            if(t.state === 'RUNNING' || t.state === 'READY'  ){
                taskCount ++;
                // cachedEEExport.status = t.status
                var st = cachedEEExport['start-time']
                var now = new Date();
                var timeDiff = now-st;
                
                timeDiff = new Date(timeDiff);
                var timeDiffShow = zeroPad(timeDiff.getMinutes(),2) + ':' +zeroPad(timeDiff.getSeconds(),2)
                taskIDList = taskIDList+ '\n' + t.description  + ' Processing Time: ' + timeDiffShow;
                }
        else if(t.state === 'COMPLETED'  && cachedEEExport.downloaded === false ){
            
            var tOutputName = 'https://console.cloud.google.com/m/cloudstorage/b/'+bucketName+'/o/'+cachedEEExports[t.id].outputName +'.tif'
            showMessage('SUCCESS!',
                 '<p style = "margin:5px;">'+ cachedEEExports[t.id].outputName + ' has successfully exported! </p><p style = "margin:3px;">Download link below:</p> <a target="_blank" href="'+tOutputName+'">'+cachedEEExports[t.id].outputName+'</a>'
                 )  
             // sleep(2000);
              // window.open(tOutputName);
              cachedEEExports[t.id]['downloaded'] = true;
            }
            
        }
        

        });

    // Object.keys(pastEEExports).map(function(k){
    //     var pe = pastEEExports[k]
    //     // console.log(k)
    //     // console.log(pe)
    //     if(pe[0] === 'COMPLETED' && pe[1] === false){
    //         var tOutputName = 'https://console.cloud.google.com/m/cloudstorage/b/'+bucketName+'/o/'+pe[2] +'.tif'
    //         // console.log('Exporting ' + pe[2]);
    //         pastEEExports[k] = [pe[0],true,pe[2]];
           
    //         showMessage('SUCCESS!',
    //              '<p style = "margin:5px;">'+ pe[2] + ' has successfully exported! </p><p style = "margin:3px;">If download does not work automatically, try following this link:</p> <a target="_blank" href="'+tOutputName+'">'+pe[2]+'</a>'
    //              )  
    //          sleep(2000);
    //           window.open(tOutputName);
    //     }
    //     // else if(pe[0] === 'FAILED' && pe[1] === false){
    //     //     showMessage('FAILED',pe[0] + ' failed')
    //     // }

    // })
    
        
    // localStorage.setItem("pastEEExports",JSON.stringify(pastEEExports));
    document.getElementById('download-spinner').title = taskIDList;
    localStorage.setItem("cachedEEExports",JSON.stringify(cachedEEExports));
    // console.log('just ran export checker');
    updateSpinner();
}
function cacheExport(id,outputName){
    cachedEEExports[id] = {'status': 'submitted', 'downloaded': false,'start-time':Date.parse(new Date()),'outputName':outputName}
    localStorage.setItem("cachedEEExports",JSON.stringify(cachedEEExports));
    trackExports();
}
if(exportCapability){interval2(trackExports, 15000, 100000)};

function updateSpinner(){

            if(taskCount === 0){$('#download-spinner').css({'visibility': 'hidden'});}
            else if(taskCount > 0 && taskCount <= 5){
                    $('#download-spinner').css({'visibility': 'visible'});
                    $('#download-spinner').attr('src', 'images/spinner'+taskCount.toString()+'.gif');
            }else{$('#download-spinner').attr('src', 'images/spinnerGT5.gif');}
           
    }


/////////////////////////////////////////////////////////////////////////////////////////////
function getIDAndParams(eeImage,exportOutputName,exportCRS,exportScale,fc){
    
    eeImage = eeImage.clip(fc);
    var imageJson = ee.Serializer.toJSON(eeImage);

    outputURL = 'https://console.cloud.google.com/m/cloudstorage/b/'+bucketName+'/o/'+exportOutputName +'.tif'//Currently cannot handle multiple tile exports for very large exports
    var region = JSON.stringify(fc.bounds().getInfo());
    //Set up parameter object
    var params = {
        json:imageJson,
        type:'EXPORT_IMAGE',
        description:exportOutputName,
        region:region,
        outputBucket:bucketName ,
        maxPixels : 1e13,
        outputPrefix: exportOutputName,
        crs:exportCRS,
        scale: exportScale
        
        }

    //Set up a task and update the spinner
    taskId = ee.data.newTaskId(1)
    return {'id':taskId,'params':params}
}
function exportImages(){
    closePopup();
    console.log(exportImageDict);
    console.log('yay');
    var now = Date().split(' ');
    var nowSuffix = '_'+now[2]+'_'+now[1]+'_'+now[3]+'_'+now[4];

    Object.keys(exportImageDict).map(function(k){
        var exportObject = exportImageDict[k];
        if(exportObject['shouldExport'] === true){
            var IDAndParams = getIDAndParams(exportObject['eeImage'],exportObject['name']+nowSuffix,exportCRS,exportObject['res'],fc);
            //Start processing
            ee.data.startProcessing(IDAndParams['id'], IDAndParams['params']);
            cacheExport(IDAndParams['id'],exportObject['name']+nowSuffix);
    // }
        }
    })
}
function processFeatures2(fc,shoudExport){
    exportFC = fc;
    print('yay');
    showPopup();

}

function displayExports(fc){
    Object.keys(exportImageDict).map(function(k){
        var exportObject = exportImageDict[k];
        var now = Date().split(' ');
        var nowSuffix = '_'+now[2]+'_'+now[1]+'_'+now[3]+'_'+now[4];
        addToMap(exportObject['eeImage'].clip(fc),exportObject['vizParams'],exportObject['name']+nowSuffix,false,null,null,null,'export-layer-list')
        
    })
}
