import datetime as dt

from django.conf import settings
from storages.backends.gcloud import GoogleCloudStorage


class MediaStorage(GoogleCloudStorage):
    bucket_name = settings.GCP_STORAGE_BUCKET_NAME
    location = ''

class StaticStorage(GoogleCloudStorage):
    bucket_name = settings.GCP_STATIC_BUCKET_NAME
    default_acl = 'publicRead'
    location = ''


def generate_signed_url_helper(blob_name, size, expiration, version='v4') -> str:
    """
    Generate a signed URL to access project files on GCS

    Parameters:
        blob_name (str): The name/path of the blob to be uploaded.
        size (int): The size of the blob to be uploaded.
        expiration (datetime.timedelta): The time until the signed URL expires.

    Returns:
        str: The signed URL.
    """
    storage = MediaStorage()
    blob = storage.bucket.blob(blob_name)

    url = blob.generate_signed_url(
        api_access_endpoint='https://storage.googleapis.com',
        expiration=expiration,
        method='PUT',
        headers={'X-Upload-Content-Length': str(size)},
        version=version
    )
    return url
