"""
   Copyright 2019 Leah Campbell

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
"""
   Copyright 2019 Leah Campbell

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
###################################################################################
#                   GCPLIB.PY
####################################################################################
# Functions for Google Cloud Platform Operations
# Uses gsutil (first section) and google.cloud.storage (second section)
import os, subprocess


#------------------------------------------------------------------------------
#                   USING GSUTIL
#------------------------------------------------------------------------------
# download training tables from google cloud storage to local directory
def download_to_local(gsutil_dir, bucket_name, trainingDataPath, exportNamePrefix = ''):
    currentDir = os.getcwd()
    os.chdir(gsutil_dir)
    syncCommand = 'gsutil.cmd -m cp -n -r gs://'+bucket_name+'/'+exportNamePrefix+'* '+trainingDataPath
    subprocess.Popen(syncCommand, shell=True).wait()
    os.chdir(currentDir)
    
# delete all contents of GCS Bucket
def clearBucket(gsutil_dir, bucket_name):
    currentDir = os.getcwd()
    os.chdir(gsutil_dir)
    subprocess.Popen('gsutil.cmd rm -v gs://'+bucket_name+'/*').wait()
    os.chdir(currentDir)
