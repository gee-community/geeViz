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
# You must have gsutil set up so that the gsutil path is added to your system environment variables in order for this to work.
# download training tables from google cloud storage to local directory
def download_to_local(bucket_name, trainingDataPath, exportNamePrefix = ''):
    syncCommand = 'gsutil.cmd -m cp -n -r gs://'+bucket_name+'/'+exportNamePrefix+'* '+trainingDataPath
    subprocess.Popen(syncCommand, shell=True).wait()
    
# delete all contents of GCS Bucket
def clearBucket(bucket_name):
    subprocess.Popen('gsutil.cmd rm -v gs://'+bucket_name+'/*').wait()

