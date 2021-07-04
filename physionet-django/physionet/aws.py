import boto3
from django.conf import settings

# One session per main django process.
# One resource per thread. https://boto3.amazonaws.com/v1/documentation/api/latest/guide/resources.html?highlight=multithreading#multithreading-or-multiprocessing-with-resources
session = boto3.Session(
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
)


def s3_mv_object(bucket_name, path1, path2):
    """
    Move object at path1 to path2 in a bucket.

    """
    if path1.endswith('/') or path2.endswith('/'):
        raise ValueError('path1 and path2 must not end with "/"')

    s3 = session.resource('s3')
    # Copy object
    s3.Object(bucket_name, path2).copy_from(
        CopySource={'Bucket':bucket_name, 'Key':path1})
    # Delete original
    s3.Object(bucket_name, path1).delete()

def s3_mv_folder(bucket_name, path1, path2):
    """
    Move all objects within 'folder' path1 to 'folder' path2.

    Aka, copy and delete all objects with prefix path1 to prefix path2.

    eg. s3_mv_folder('mybucket', 'a/b', 'A') applied to:
    - a/b/c/hello1.txt
    - a/b/hello2.txt

    Produces:
    - A/c/hello1.txt
    - A/hello2.txt

    """
    if path1.endswith('/') or path2.endswith('/'):
        raise ValueError('path1 and path2 must not end with "/"')
    # Ensure this is only moving items within 'folders'.
    path1 += '/'
    path2 += '/'

    s3 = session.resource('s3')

    bucket = s3.Bucket(bucket_name)

    for obj in bucket.objects.filter(Prefix=path1):
        src_key = obj.key
        if src_key.endswith('/'):
            continue

        s3.Object(bucket_name, src_key.replace(path1, path2, 1)).copy_from(
            CopySource={ 'Bucket':bucket_name, 'Key': src_key })
        obj.delete()
