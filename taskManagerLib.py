"""
   Copyright 2019 Ian Housman & Leah Campbell

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
###############################################################################
#           TASKMANAGERLIB.PY
################################################################################
# Functions for GEE task management

import ee, time, re
from datetime import datetime, timedelta
ee.Initialize()


#------------------------------------------------------------------------------
#                     Standard Task Tracking 
#------------------------------------------------------------------------------
# Standard task tracker - prints number of ready and running tasks each 10 seconds
def trackTasks():
    x = 1
    while x <1000:
        tasks = ee.data.getTaskList()
        ready = [i for i in tasks if i['state'] == 'READY']
        running = [i for i in tasks if i['state'] == 'RUNNING']
        running_names = [[str(i['description']),str(timedelta(seconds = int(((time.time()*1000)-int(i['start_timestamp_ms']))/1000)))] for i in running]
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(len(ready),'tasks ready',now)
        print(len(running),'tasks running',now)
        print('Running names:')
        for rn in running_names:print(rn)
        print()
        print()
        time.sleep(10)
        x+=1

# Standard task tracker - prints number of ready and running tasks each 10 seconds
def failedTasks():
    tasks = ee.data.getTaskList()
    failed = [i for i in tasks if i['state'] == 'FAILED']
    failed_names = [[str(i['description']),str(timedelta(seconds = int(((time.time()*1000)-int(i['start_timestamp_ms']))/1000)))] for i in failed]
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print('Failed names:')
    for rn in failed: print(rn)



#------------------------------------------------------------------------------
#                  Cancel Tasks
#------------------------------------------------------------------------------
# Cancels all running tasks
def batchCancel():
    tasks = ee.data.getTaskList()
    ready = [str(i['id']) for i in tasks if i['state'] == 'READY']
    running = [str(i['id']) for i in tasks if i['state'] == 'RUNNING']
    print(ready)
    map(ee.data.cancelTask,running)
    map(ee.data.cancelTask,ready)

# Cancels all running tasks with identifier in their name
def cancelByName(nameIdentifier):
    cancelList = nameTaskList(nameIdentifier)
    if cancelList:
        for task in cancelList:
            print('Cancelling '+task['description'])
            ee.data.cancelTask(task['id'])
    else:
        print('No Tasks to Cancel')
#------------------------------------------------------------------------------
#                 Task Tracking Using Time Interval
#------------------------------------------------------------------------------    
# Get list of tasks started within a specified time interval
# Starttime and endtime must be python datetimes, in UTC, e.g. datetime.datetime.utcnow()
def timeTaskList(starttime, endtime):
    tasks = ee.data.getTaskList()
    epoch = datetime.utcfromtimestamp(0)
    starttime = (starttime - epoch).total_seconds() * 1000.
    endtime = (endtime - epoch).total_seconds() * 1000.
    thisList = [i for i in tasks if (i['creation_timestamp_ms'] >= starttime and i['creation_timestamp_ms'] <= endtime)]
    return thisList

# Using a start and end time, track the jobs that were started within that time interval
# Print status updates every minute
# Only move on when no 'ready' or 'running' jobs remain, i.e. all have completed or failed
# Then print status of all tasks 
# Starttime and endtime must be python datetimes, in UTC, e.g. datetime.datetime.utcnow()
# check_interval = seconds between status checks
def jobCompletionTracker(starttime, endtime, check_interval):
    thisTasklist = timeTaskList(starttime,endtime)
    for i in thisTasklist:
        print(i['description'], i['state'])
    currentJobs = 1
    while currentJobs > 0:
        time.sleep(check_interval)
        thisTasklist = timeTaskList(starttime,endtime)
        ready = [i for i in thisTasklist if (i['state'] == 'READY')]
        running = [i for i in thisTasklist if (i['state'] == 'RUNNING')]
        completed = [i for i in thisTasklist if (i['state'] == 'COMPLETED')]
        failed = [i for i in thisTasklist if (i['state'] == 'FAILED')]
        cancelled = [i for i in thisTasklist if (i['state'] == 'CANCELLED')]
        currentJobs = len(ready) + len(running)
        
        print(' ')
        print(datetime.now(), ':')
        print(len(ready),' tasks ready')
        print(len(running), ' tasks running')
               
    return [ready, running, completed, failed, cancelled, thisTasklist]

#------------------------------------------------------------------------------
#                 Task Tracking Using Task Name / Description
#------------------------------------------------------------------------------    
# Get list of tasks with specified name/description prefix (e.g. "description" passed to GEE export function)
def nameTaskList(nameIdentifier):
    tasks = ee.data.getTaskList()
    thisList = [i for i in tasks if re.findall(nameIdentifier, i['description']) and (i['state'] == 'READY' or i['state'] == 'RUNNING')]
    return thisList