import boto3
import botocore
import os
from django.conf import settings
from project.utility import FileInfo, DirectoryInfo, readable_size

# One session per main django process.
# One resource per thread. https://boto3.amazonaws.com/v1/documentation/api/latest/guide/resources.html?highlight=multithreading#multithreading-or-multiprocessing-with-resources

if settings.STORAGE_TYPE == 'S3':
    session = boto3.Session(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

def get_s3_resource():
    config = botocore.config.Config(signature_version='s3v4', region_name='us-east-2')
    return session.resource('s3', config=config)

def s3_signed_url(bucket_name, key):
    return get_s3_resource().meta.client.generate_presigned_url('get_object', Params={'Bucket': bucket_name, 'Key': key}, ExpiresIn=3600)

def s3_directory_exists(bucket_name, path):
    """
    Returns true if there exists an object nested within path.
    """
    if not path.endswith('/'):
        path += '/'

    return session.resource('s3').meta.client.list_objects_v2(Bucket=bucket_name, Prefix=path, MaxKeys=1)['KeyCount']

def s3_file_exists(bucket_name, key):
    """
    Returns whether an object with a given key exists in the bucket.
    """
    try:
        session.resource('s3').meta.client.head_object(Bucket=bucket_name, Key=key)
        return True
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            raise e

def s3_directory_size(bucket_name, path):
    if not path.endswith('/'):
        path += '/'

    response = session.resource('s3').meta.client.list_objects_v2(Bucket=bucket_name, Prefix=path)
    return sum(obj['Size'] for obj in response['Contents'])

def s3_directory_exists(bucket_name, path):
    """
    Returns true if there exists an object nested within path.
    """
    if not path.endswith('/'):
        path += '/'

    return

def s3_upload_folder(bucket_name, path1, path2):
    """
    Upload files at path1 on the disk to path2 in the bucket.

    path1 should be an absolute path.
    """
    s3 = session.resource('s3')

    if path1.endswith('/') or path2.endswith('/'):
        raise ValueError('path1 and path2 must not end with "/"')

    for dirpath, subdirs, files in os.walk(path1):
        for f in files:
            src = os.path.join(dirpath, f)
            dst = os.path.join(dirpath.replace(path1, path2, 1), f)
            s3.meta.client.upload_file(src, bucket_name, dst)

def s3_mv_object(bucket_name, path1, path2):
    """
    Move object at path1 to path2 in a bucket.

    """
    if path1.endswith('/') or path2.endswith('/'):
        raise ValueError('path1 and path2 must not end with "/"')

    s3 = session.resource('s3')
    print('mv:', path1, '->', path2)
    # Copy object
    s3.Object(bucket_name, path2).copy_from(
        CopySource={'Bucket': bucket_name, 'Key': path1})
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

        print('mv:', src_key, '->', src_key.replace(path1, path2, 1))
        s3.Object(bucket_name, src_key.replace(path1, path2, 1)).copy_from(
            CopySource={'Bucket': bucket_name, 'Key': src_key})
        obj.delete()

def s3_mv_items(bucket_name, path1, path2):
    try:
        s3_mv_object(bucket_name, path1, path2)
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchKey':
            raise e
    s3_mv_folder(bucket_name, path1, path2)

def s3_rm(bucket_name, path):
    """
    Delete the object specified by path and all nested objects if path is a folder.
    """
    s3 = session.resource('s3')

    bucket = s3.Bucket(bucket_name)

    if not path.endswith('/'):
        bucket.Object(path).delete()
        path += '/'

    for obj in bucket.objects.filter(Prefix=path):
        obj.delete()

def s3_list_directory(bucket_name, path):
    """
    List all nested directories and files within 'folder' path.

    Works similarly to 'ls -al'.
    """

    if not path.endswith('/'):
        path += '/'

    s3 = session.resource('s3')

    result = s3.meta.client.list_objects_v2(
        Bucket=bucket_name,
        Prefix=path,
        Delimiter='/')

    print(result)

    files = [FileInfo(f['Key'].replace(path, '', 1), readable_size(f['Size']), f['LastModified'].strftime("%Y-%m-%d")) for f in result.get('Contents', []) if f['Key'].replace(path, '', 1) != '']
    dirs = [DirectoryInfo(d['Prefix'].replace(path, '', 1)[:-1]) for d in result.get('CommonPrefixes', [])]

    return files, dirs
