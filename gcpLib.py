###################################################################################
#                   GCPLIB.PY
####################################################################################
# Functions for Google Cloud Platform Operations
# Uses gsutil (first section) and google.cloud.storage (second section)
import os, subprocess


#------------------------------------------------------------------------------
#                   USING GSUTIL
#------------------------------------------------------------------------------
#gsutil_dir = e.g., 'C:/Users/leahcampbell/home/scripts' - where gsutil.cmd lives
#bucket_name = 'training_data_tables'

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
#------------------------------------------------------------------------------
#                   USING GOOGLE-CLOUD-STORAGE
#------------------------------------------------------------------------------
#localPath = 'Z:/Projects/06_LCMS_4_NFS/R4/08_BridgerTetonNF/01_TrainingData'
#bucket_name = 'training_data_tables'
#table_id='LCMS-BT-Export'
#jsonPath = 'C:\Users\leahcampbell\home\scripts\gcloud_service_accounts\LCMS-17c672d969ba.json'

## Download training tables from Cloud Storage to the NAS using google-cloud-storage module
def downloadFromBucket(jsonPath, localPath, bucket_name, table_id = None):
    from google.cloud import storage
    
    storage_client = storage.Client.from_service_account_json(jsonPath)
    bucket=storage_client.get_bucket(bucket_name)
    blobs=bucket.list_blobs()
    blobs=bucket.list_blobs(prefix=table_id, delimiter='/') #List all objects that satisfy the filter.
    for blob in blobs:
        print(blob.name)
        blob.download_to_filename(localPath+'/'+blob.name)
