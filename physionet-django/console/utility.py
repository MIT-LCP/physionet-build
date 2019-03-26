from google.cloud import storage
from os import walk, chdir, listdir, path

import requests 
import json
import os
import pickle
import logging

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

# New_Project = 'ecgiddb'
# bucket_name='physionet-data-{0}'.format(New_Project)

logger = logging.getLogger(__name__)

def check_bucket(project):
    storage_client = storage.Client()
    bucket_name = 'physionet-data-' + project
    exists = storage_client.lookup_bucket(bucket_name)
    if exists:
        return True
    return False

def create_bucket(project, protected=False, group=''):
    """Creates a new bucket."""
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
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    policy = bucket.get_iam_policy()
    for role in policy:
        members = policy[role]
        print('Role: {}, Members: {}'.format(role, members))

def set_bucket_permissions(bucket_name, group):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    bucket.acl.group(group).grant_read()
    bucket.acl.save()

def upload_files(bucket_name, New_Project):
    root_dir = '/data/pn-static/published-projects/'
    file_dir = '/files/'
    working_dir = root_dir + New_Project + file_dir
    subfolders_fullpath = [x[0] for x in walk(working_dir)]
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    for indx, location in enumerate(subfolders_fullpath):
        chdir(location)
        files = [f for f in listdir('.') if path.isfile(f)]
        for file in files:
            temp_dir = location.replace(working_dir,'')
            if temp_dir != '':
                blob = bucket.blob(temp_dir + '/' + file)
                blob.upload_from_filename(file)
            else:
                blob = bucket.blob(file)
                blob.upload_from_filename(file)
