"""
Helpful functions for managing Google Cloud Storage (GCS) buckets and blobs

geeViz.cloudStorageManagerLib includes functions for renaming, seeing if a blob exists, and deleting blobs.
"""

"""
   Copyright 2026 Ian Housman

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
# Script to help with basic cloudStorage management
# Intended to work within the geeViz package
######################################################################
import geeViz.geeView
import re
from google.cloud import storage


######################################################################
# Function to list all blobs in a bucket
# Returns a list of blob objects
# Use the blob.name to get the name
def list_blobs(bucket_name: str) -> list:
    """
    Lists all blob objects in a bucket.

    Args:
        bucket_name (str): The name of the GCS bucket.

    Returns:
        list: A list of blob objects in the bucket.

    Example:
        >>> blobs = list_blobs("my-bucket")
        >>> for blob in blobs:
        ...     print(blob.name)
    """
    # storage client instance
    storage_client = storage.Client(project=geeViz.geeView.ee.data._get_state().cloud_api_user_project)

    # get bucket by name
    bucket = storage_client.get_bucket(bucket_name)

    # list files stored in bucket
    all_blobs = bucket.list_blobs()
    return list(all_blobs)


def list_files(bucket_name: str) -> list[str]:
    """
    Lists filenames in a bucket.

    Args:
        bucket_name (str): The name of the GCS bucket.

    Returns:
        list[str]: A list of filenames in the bucket.

    Example:
        >>> files = list_files("my-bucket")
        >>> for file in files:
        ...     print(file)
    """
    return [f.name for f in list_blobs(bucket_name)]


######################################################################
def bucket_exists(bucket_name: str) -> bool:
    """
    Checks if a GCS bucket exists.

    Args:
        bucket_name (str): The name of the GCS bucket.

    Returns:
        bool: True if the bucket exists, False otherwise.

    Example:
        >>> if bucket_exists("my-bucket"):
        ...     print("Bucket exists.")
        ... else:
        ...     print("Bucket does not exist.")
    """
    # storage client instance
    storage_client = storage.Client(project=geeViz.geeView.ee.data._get_state().cloud_api_user_project)

    # get bucket by name
    bucket = storage_client.bucket(bucket_name)

    return bucket.exists()


######################################################################
def create_bucket(bucket_name: str):
    """
    Creates a GCS bucket.

    Args:
        bucket_name (str): The name of the GCS bucket to create.

    Returns:
        google.cloud.storage.bucket.Bucket: The created bucket object.

    Example:
        >>> bucket = create_bucket("my-new-bucket")
        >>> print(f"Created bucket: {bucket.name}")
    """
    # Initialize a client
    storage_client = storage.Client(project=geeViz.geeView.ee.data._get_state().cloud_api_user_project)

    # Create a new bucket
    bucket = storage_client.create_bucket(bucket_name)

    print(f"Bucket {bucket.name} created.")
    return bucket


######################################################################
# Function to batch rename blobs in a bucket
def rename_blobs(bucket_name, old_name, new_name):
    """
    Renames a group of blobs in a bucket.

    Args:
        bucket_name (str): The name of the GCS bucket.
        old_name (str): The substring to replace in blob names.
        new_name (str): The new substring to use in blob names.

    Example:
        >>> rename_blobs("my-bucket", "old_prefix", "new_prefix")
    """
    # storage client instance
    storage_client = storage.Client(project=geeViz.geeView.ee.data._get_state().cloud_api_user_project)

    # get bucket by name
    bucket = storage_client.get_bucket(bucket_name)

    # list files stored in bucket
    all_blobs = list(bucket.list_blobs())

    # Renaming all files to lowercase:
    for blob in all_blobs:
        on = str(blob.name)
        nn = on.replace(old_name, new_name)
        new_blob = bucket.rename_blob(blob, new_name=nn)
        print("Blob {} has been renamed to {}".format(on, nn))


######################################################################
# Return wether a filename exists or not
def gcs_exists(bucket, filename):
    """
    Checks if a specific file exists in a GCS bucket.

    Args:
        bucket (str): The name of the GCS bucket.
        filename (str): The name of the file to check.

    Returns:
        bool: True if the file exists, False otherwise.

    Example:
        >>> if gcs_exists("my-bucket", "file.txt"):
        ...     print("File exists.")
        ... else:
        ...     print("File does not exist.")
    """
    storage_client = storage.Client(project=geeViz.geeView.ee.data._get_state().cloud_api_user_project)
    stats = storage.Blob(bucket=storage_client.bucket(bucket), name=filename).exists(storage_client)
    return stats
######################################################################
# !! Dangerous !! - cannot be undone
# Delete a specified filename
def delete_blob(bucket, filename):
    """
    Deletes a specified file from a GCS bucket.

    Args:
        bucket (str): The name of the GCS bucket.
        filename (str): The name of the file to delete.

    Example:
        >>> delete_blob("my-bucket", "file.txt")
        >>> print("File deleted.")
    """
    storage_client = storage.Client(project=geeViz.geeView.ee.data._get_state().cloud_api_user_project)
    out = storage.Blob(bucket=storage_client.bucket(bucket), name=filename).delete(storage_client)
    print("Deleted:", filename)


######################################################################

def download_blob(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the bucket.
    Args:
        bucket_name (str): The name of the GCS bucket.
        source_blob_name (str): The name of the blob in the GCS bucket.
        destination_file_name (str): The local path to save the downloaded file.
    Example:
        download_blob('my-bucket', 'path/to/blob', 'local/path/to/file')
    """
    storage_client = storage.Client(project=geeViz.geeView.ee.data._get_state().cloud_api_user_project)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)
    print(f"Downloaded {source_blob_name} to {destination_file_name}.")

def exportToCloudStorageWrapper(
    imageForExport: geeViz.geeView.ee.Image,
    outputName: str,
    bucketName: str,
    roi: geeViz.geeView.ee.Geometry,
    scale: float | None = None,
    crs: str | None = None,
    transform: list | None = None,
    outputNoData: int = -32768,
    fileFormat: str = "GeoTIFF",
    formatOptions: dict = {"cloudOptimized": True},
    overwrite: bool = False,
):
    """Exports an image to Google Cloud Storage.

    This function exports an Earth Engine Image to a specified Google Cloud Storage bucket.

    Args:
        imageForExport: The Earth Engine Image to export.
        outputName: The desired name for the exported file.
        bucketName: The name of the Google Cloud Storage bucket.
        roi: The Earth Engine Geometry defining the region of interest.
        scale: The desired export scale in meters.
        crs: The desired coordinate reference system for the export.
        transform: The desired transform for the export.
        outputNoData: The no data value to use for the export.
        fileFormat: The desired output file format (e.g., "GeoTIFF", "TFRecord").
        formatOptions: Additional format options for the export.
        overwrite: A boolean indicating whether to overwrite an existing file.

    Returns:
        None. The function starts the export task.
    """
    import geeViz.taskManagerLib as tml

    outputName = re.sub(r'\s+', '-', outputName)  # Replace whitespace with hyphens
    outputNameDescription = outputName.replace("/", "_")  # Get rid of any slashes for description; compatibility for exporting to folders

    extension_dict = {"GeoTIFF": [".tif"], "TFRecord": [".tfrecord", ".json"]}
    extensions = extension_dict[fileFormat]

    # Pull geometry if feature or featureCollection
    try:
        roi = roi.geometry()
    except Exception:
        pass

    # Make sure image is clipped to roi in case it's a multi-part polygon
    imageForExport = imageForExport.clip(roi).unmask(outputNoData, False)

    if transform != None and (str(type(transform)) == "<type 'list'>" or str(type(transform)) == "<class 'list'>"):
        transform = str(transform)

    # Ensure bounds are in export projection
    outRegion = roi.bounds(100, crs)

    # Handle different instances of an blob either already existing or currently being exported and whether it should be overwritten
    currently_exporting = outputName in tml.getTasks()["running"] or outputName in tml.getTasks()["ready"]
    currently_exists = gcs_exists(bucketName, outputName + extensions[0])

    if overwrite and currently_exists:
        for extension in extensions:
            delete_blob(bucketName, outputName + extension)
    if overwrite and currently_exporting:
        tml.cancelByName(outputName)
    if overwrite or (not currently_exists and not currently_exporting):
        t = geeViz.geeView.ee.batch.Export.image.toCloudStorage(
            imageForExport,
            outputNameDescription,
            bucketName,
            outputName,
            None,
            outRegion,
            scale,
            crs,
            transform,
            1e13,
            fileFormat=fileFormat,
            formatOptions=formatOptions,
        )
        print("Exporting:", outputName)
        print(t)
        t.start()