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

def now():
    """Get the current time as a formatted string.

    Returns:
        str: Current time in "%Y-%m-%d %H:%M:%S" format.

    Example:
        >>> now()
        '2025-06-01 12:34:56'
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def trackTasks():
    """Track and print the number of ready and running tasks every 10 seconds, up to 1000 times.

    Example:
        >>> trackTasks()
        2 tasks ready 2025-06-01 12:34:56
        1 tasks running 2025-06-01 12:34:56
        Running names:
        ['ExportImage', '0:01:23']
        ...
    """
    x = 1
    while x < 1000:
        tasks = ee.data.getTaskList()  # Get all current tasks
        ready = [i for i in tasks if i["state"] == "READY"]  # Tasks waiting to run
        running = [i for i in tasks if i["state"] == "RUNNING"]  # Tasks currently running
        running_names = [
            [
                str(i["description"]),
                str(timedelta(seconds=int(((time.time() * 1000) - int(i["start_timestamp_ms"])) / 1000))),
            ]
            for i in running
        ]  # List of running task descriptions and their run times
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(len(ready), "tasks ready", now)
        print(len(running), "tasks running", now)
        print("Running names:")
        for rn in running_names:
            print(rn)
        print()
        print()
        time.sleep(10)  # Wait 10 seconds before next check
        x += 1


def trackTasks2(credential_name=None, id_list=None, task_count=1):
    """Track tasks for a specific credential or list of task IDs, printing status every 5 seconds.

    Args:
        credential_name (str, optional): Name of the credential to print.
        id_list (list, optional): List of task descriptions to filter.
        task_count (int, optional): Initial task count to start tracking.

    Example:
        >>> trackTasks2(credential_name='user', id_list=['ExportImage'], task_count=1)
        user
        1 tasks ready 2025-06-01 12:34:56
        0 tasks running 2025-06-01 12:34:56
        Running names:
        ...
    """
    while task_count > 0:
        tasks = ee.data.getTaskList()
        if id_list != None:
            tasks = [i for i in tasks if i["description"] in id_list]  # Filter by provided IDs
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
        time.sleep(5)  # Wait 5 seconds before next check
        task_count = len(ready) + len(running)  # Continue until no ready or running tasks


def getTasks(id_list=None):
    """Get a dictionary of tasks grouped by their state.

    Args:
        id_list (list, optional): List of task descriptions to filter.

    Returns:
        dict: Dictionary with keys 'ready', 'running', 'failed', 'completed'.

    Example:
        >>> getTasks()
        {'ready': ['ExportImage'], 'running': [], 'failed': [], 'completed': ['ExportTable']}
    """
    tasks = ee.data.getTaskList()
    if id_list != None:
        tasks = [i for i in tasks if i["description"] in id_list]
    out = {}
    out["ready"] = [i["description"] for i in tasks if i["state"] == "READY"]
    out["running"] = [i["description"] for i in tasks if i["state"] == "RUNNING"]
    out["failed"] = [i["description"] for i in tasks if i["state"] == "FAILED"]
    out["completed"] = [i["description"] for i in tasks if i["state"] == "COMPLETED"]
    return out


def failedTasks():
    """Print all failed tasks and their run times.

    Example:
        >>> failedTasks()
        Failed names:
        {'id': 'ABCD', 'state': 'FAILED', ...}
        ...
    """
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

def batchCancel():
    """Cancel all tasks that are either ready or running.

    Example:
        >>> batchCancel()
        Cancelling: ExportImage
        READY: ExportImage
        ...
    """
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


def cancelByName(nameIdentifier):
    """Cancel all tasks whose description contains the given identifier.

    Args:
        nameIdentifier (str): Substring to search for in task descriptions.

    Example:
        >>> cancelByName('ExportImage')
        Cancelling ExportImage
        ...
    """
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

def timeTaskList(starttime, endtime):
    """Get list of tasks started within a specified time interval.

    Args:
        starttime (datetime): UTC datetime object for interval start.
        endtime (datetime): UTC datetime object for interval end.

    Returns:
        list: List of task dicts started within the interval.

    Example:
        >>> from datetime import datetime, timedelta
        >>> start = datetime.utcnow() - timedelta(hours=1)
        >>> end = datetime.utcnow()
        >>> timeTaskList(start, end)
        [{'id': 'ABCD', ...}, ...]
    """
    tasks = ee.data.getTaskList()
    epoch = datetime.utcfromtimestamp(0)
    starttime = (starttime - epoch).total_seconds() * 1000.0  # Convert to ms since epoch
    endtime = (endtime - epoch).total_seconds() * 1000.0
    thisList = [i for i in tasks if (i["creation_timestamp_ms"] >= starttime and i["creation_timestamp_ms"] <= endtime)]
    return thisList


def jobCompletionTracker(starttime, endtime, check_interval):
    """Track completion of all jobs started within a time interval.

    Args:
        starttime (datetime): UTC datetime object for interval start.
        endtime (datetime): UTC datetime object for interval end.
        check_interval (int): Seconds between status checks.

    Returns:
        list: Lists of ready, running, completed, failed, cancelled, and all tasks.

    Example:
        >>> from datetime import datetime, timedelta
        >>> start = datetime.utcnow() - timedelta(hours=1)
        >>> end = datetime.utcnow()
        >>> jobCompletionTracker(start, end, 10)
        ...
    """
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

def nameTaskList(nameIdentifier):
    """Get list of tasks with specified name/description prefix.

    Args:
        nameIdentifier (str): Substring to search for in task descriptions.

    Returns:
        list: List of matching task dicts.

    Example:
        >>> nameTaskList('ExportImage')
        [{'id': 'ABCD', ...}, ...]
    """
    tasks = ee.data.getTaskList()
    # Find tasks whose description matches the identifier and are ready or running
    thisList = [i for i in tasks if re.findall(nameIdentifier, i["description"]) and (i["state"] == "READY" or i["state"] == "RUNNING")]
    return thisList


def getEECUS(output_table_name, nameFind=None, overwrite=False):
    """Create a CSV table of successful exports, including run time, EECU usage, and output size.

    Args:
        output_table_name (str): Path to output CSV file.
        nameFind (str, optional): Substring to filter task descriptions.
        overwrite (bool, optional): Overwrite existing file if True.

    Example:
        >>> getEECUS('output.csv', nameFind='ExportImage', overwrite=True)
        Only output extension allowed is .csv. Changing extension to .csv
        ...
    """
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
                size = float(info["sizeBytes"]) * 1e-6  # Convert bytes to megabytes
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
