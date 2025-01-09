"""
Monitor and manage tasks programatically

geeViz.taskManagerLib facilitates the monitoring and deleting of GEE export tasks.
"""

"""
   Copyright 2025 Ian Housman & Leah Campbell

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

import geeViz.geeView as gv
import ee, time, re, os
from datetime import datetime, timedelta


# ------------------------------------------------------------------------------
#                     Standard Task Tracking
# ------------------------------------------------------------------------------
# Standard task tracker - prints number of ready and running tasks each 10 seconds
def now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def trackTasks():
    x = 1
    while x < 1000:
        tasks = ee.data.getTaskList()
        ready = [i for i in tasks if i["state"] == "READY"]
        running = [i for i in tasks if i["state"] == "RUNNING"]
        running_names = [
            [
                str(i["description"]),
                str(timedelta(seconds=int(((time.time() * 1000) - int(i["start_timestamp_ms"])) / 1000))),
            ]
            for i in running
        ]
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(len(ready), "tasks ready", now)
        print(len(running), "tasks running", now)
        print("Running names:")
        for rn in running_names:
            print(rn)
        print()
        print()
        time.sleep(10)
        x += 1


def trackTasks2(credential_name=None, id_list=None, task_count=1):
    while task_count > 0:
        tasks = ee.data.getTaskList()
        if id_list != None:
            tasks = [i for i in tasks if i["description"] in id_list]
        ready = [i for i in tasks if i["state"] == "READY"]
        running = [i for i in tasks if i["state"] == "RUNNING"]
        running_names = [
            [
                str(i["description"]),
                str(timedelta(seconds=int(((time.time() * 1000) - int(i["start_timestamp_ms"])) / 1000))),
            ]
            for i in running
        ]
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        if credential_name != None:
            print(credential_name)
        print(len(ready), "tasks ready", now)
        print(len(running), "tasks running", now)
        print("Running names:")
        for rn in running_names:
            print(rn)
        print()
        print()
        time.sleep(5)
        task_count = len(ready) + len(running)


# Get tasks in an easy-to-use format
def getTasks(id_list=None):
    tasks = ee.data.getTaskList()
    if id_list != None:
        tasks = [i for i in tasks if i["description"] in id_list]
    out = {}
    out["ready"] = [i["description"] for i in tasks if i["state"] == "READY"]
    out["running"] = [i["description"] for i in tasks if i["state"] == "RUNNING"]
    out["failed"] = [i["description"] for i in tasks if i["state"] == "FAILED"]
    out["completed"] = [i["description"] for i in tasks if i["state"] == "COMPLETED"]
    return out


# Standard task tracker - prints number of ready and running tasks each 10 seconds
def failedTasks():
    tasks = ee.data.getTaskList()
    failed = [i for i in tasks if i["state"] == "FAILED"]
    failed_names = [
        [
            str(i["description"]),
            str(timedelta(seconds=int(((time.time() * 1000) - int(i["start_timestamp_ms"])) / 1000))),
        ]
        for i in failed
    ]
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print("Failed names:")
    for rn in failed:
        print(rn)


# ------------------------------------------------------------------------------
#                  Cancel Tasks
# ------------------------------------------------------------------------------
# Cancels all running tasks
def batchCancel():
    tasks = ee.data.getTaskList()
    cancelledTasks = []
    for ind, i in enumerate(tasks):
        if i["state"] == "READY" or i["state"] == "RUNNING":
            cancelledTasks.append(ind)
            print("Cancelling:", i["description"])
            ee.data.cancelTask(i["id"])
            # ee.data.cancelOperation(ee._cloud_api_utils.convert_task_id_to_operation_name(i['id'])) # this was the workaround for a bug with cancelTask in earthengine-api v0.1.225
    tasks2 = ee.data.getTaskList()
    for ind in cancelledTasks:
        print(tasks2[ind]["state"] + ": " + tasks2[ind]["description"])


# Cancels all running tasks with identifier in their name
def cancelByName(nameIdentifier):
    cancelList = nameTaskList(nameIdentifier)
    if cancelList:
        for task in cancelList:
            print("Cancelling " + task["description"])
            ee.data.cancelTask(task["id"])
    else:
        print("No Tasks to Cancel")


# ------------------------------------------------------------------------------
#                 Task Tracking Using Time Interval
# ------------------------------------------------------------------------------
# Get list of tasks started within a specified time interval
# Starttime and endtime must be python datetimes, in UTC, e.g. datetime.datetime.utcnow()
def timeTaskList(starttime, endtime):
    tasks = ee.data.getTaskList()
    epoch = datetime.utcfromtimestamp(0)
    starttime = (starttime - epoch).total_seconds() * 1000.0
    endtime = (endtime - epoch).total_seconds() * 1000.0
    thisList = [i for i in tasks if (i["creation_timestamp_ms"] >= starttime and i["creation_timestamp_ms"] <= endtime)]
    return thisList


# Using a start and end time, track the jobs that were started within that time interval
# Print status updates every minute
# Only move on when no 'ready' or 'running' jobs remain, i.e. all have completed or failed
# Then print status of all tasks
# Starttime and endtime must be python datetimes, in UTC, e.g. datetime.datetime.utcnow()
# check_interval = seconds between status checks
def jobCompletionTracker(starttime, endtime, check_interval):
    timeStart = datetime.utcnow()
    thisTasklist = timeTaskList(starttime, endtime)
    for i in thisTasklist:
        print(i["description"], i["state"])
    currentJobs = 1

    while currentJobs > 0:
        time.sleep(check_interval)
        thisTasklist = timeTaskList(starttime, endtime)
        ready = [i for i in thisTasklist if (i["state"] == "READY")]
        running = [i for i in thisTasklist if (i["state"] == "RUNNING")]
        completed = [i for i in thisTasklist if (i["state"] == "COMPLETED")]
        failed = [i for i in thisTasklist if (i["state"] == "FAILED")]
        cancelled = [i for i in thisTasklist if (i["state"] == "CANCELLED")]
        currentJobs = len(ready) + len(running)

        print(" ")
        print(datetime.now(), ":")
        print(len(ready), " tasks ready")
        # print(len(running), ' tasks running')
        running_names = [
            [
                str(i["description"]),
                str(timedelta(seconds=int(((time.time() * 1000) - int(i["start_timestamp_ms"])) / 1000))),
            ]
            for i in running
        ]
        for rn in running_names:
            print(rn)

    timeEnd = datetime.utcnow()
    print("Process Time:")
    print(timeEnd - timeStart)
    return [ready, running, completed, failed, cancelled, thisTasklist]


# ------------------------------------------------------------------------------
#                 Task Tracking Using Task Name / Description
# ------------------------------------------------------------------------------
# Get list of tasks with specified name/description prefix (e.g. "description" passed to GEE export function)
def nameTaskList(nameIdentifier):
    tasks = ee.data.getTaskList()
    thisList = [i for i in tasks if re.findall(nameIdentifier, i["description"]) and (i["state"] == "READY" or i["state"] == "RUNNING")]
    return thisList


# Function to create a table of successful exports, how long it took, and the EECUs used
def getEECUS(output_table_name, nameFind=None, overwrite=False):
    if os.path.splitext(output_table_name)[1] != ".csv":
        print("Only output extension allowed is .csv. Changing extension to .csv")
        output_table_name = os.path.splitext(output_table_name)[0] + ".csv"
    if not os.path.exists(output_table_name) or overwrite:
        operations = ee.data.listOperations()
        print(ee.data.getTaskList())
        completed = [i for i in operations if i["metadata"]["state"] == "SUCCEEDED"]

        if nameFind != None:
            completed = [i for i in completed if i["metadata"]["description"].find(nameFind) > -1]
        output_table_name = os.path.splitext(output_table_name)[0] + ".csv"
        out_lines = "Name,Run Time, EECU Seconds,Size (megaBytes)\n"

        for task in completed:
            try:
                uri = task["metadata"]["destinationUris"][0].split("?asset=")[1]
                info = ee.data.getAsset(uri)
                size = float(info["sizeBytes"]) * 1e-6
            except:
                size = "NA"

            startTime = datetime.fromisoformat(task["metadata"]["startTime"][:-1])
            endTime = datetime.fromisoformat(task["metadata"]["endTime"][:-1])
            out_lines += "{},{},{},{}\n".format(
                task["metadata"]["description"],
                endTime - startTime,
                task["metadata"]["batchEecuUsageSeconds"],
                size,
            )
        o = open(output_table_name, "w")
        o.write(out_lines)
        o.close()
    else:
        print("Output table already exists and overwite is set to False")
