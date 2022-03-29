from django.conf import settings
from storages.backends.gcloud import GoogleCloudStorage


class MediaStorage(GoogleCloudStorage):
    bucket_name = settings.GCP_STORAGE_BUCKET_NAME
    location = ''

class StaticStorage(GoogleCloudStorage):
    bucket_name = settings.GCP_STATIC_BUCKET_NAME
    default_acl = 'publicRead'
    location = ''
