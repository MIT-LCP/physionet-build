from google.cloud import storage
from os import walk, chdir, listdir, path

import requests 
import json
import os
import pickle
import logging

logger = logging.getLogger(__name__)

def check_bucket(project):
    """
    Function to check if a bucket already exists 
    """
    storage_client = storage.Client()
    bucket_name = 'physionet-data-' + project
    exists = storage_client.lookup_bucket(bucket_name)
    if exists:
        return True
    return False

def create_bucket(project, protected=False, group=''):
    """
    Function to create a bucket and set its permissions
    """
    storage_client = storage.Client()
    bucket_name = 'physionet-data-' + project
    bucket = storage_client.create_bucket(bucket_name)
    logger.info("Created bucket {0} for project {1}".format(bucket_name, project))
    if not protected:
        bucket.acl.all().grant_read()
        bucket.acl.save()
    else:
        set_bucket_permissions(bucket_name, group)
    return bucket_name

def list_bucket_permissions(bucket_name):
    """
    Function to list the permissions of a bucket
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    policy = bucket.get_iam_policy()
    for role in policy:
        members = policy[role]
        print('Role: {}, Members: {}'.format(role, members))

def set_bucket_permissions(bucket_name, group):
    """
    Function to set the permissions of a bucket to a specific group
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    bucket.acl.group(group).grant_read()
    bucket.acl.save()

def upload_files(project):
    """
    Function to send files to a bucket. 
    """
    root_dir = project.project_file_root()
    version = project.version
    working_path = os.path.join(root_dir, version)
    subfolders_fullpath = [x[0] for x in walk(root_dir)]
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(project.gcp.bucket_name)
    for indx, location in enumerate(subfolders_fullpath):
        chdir(location)
        files = [f for f in listdir('.') if path.isfile(f)]
        for file in files:
            temp_dir = location.replace(root_dir,'')
            if temp_dir != '':
                os.path.join(temp_dir, file)
                blob = bucket.blob(os.path.join(temp_dir, file)[1:])
                blob.upload_from_filename(file)
            else:
                blob = bucket.blob(file)
                blob.upload_from_filename(file)

