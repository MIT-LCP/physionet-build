from os import walk, chdir, listdir, path
from requests.auth import HTTPBasicAuth
from requests import post, put, get
import json

import google.auth
import google.auth.impersonated_credentials
from google.api_core.exceptions import BadRequest
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from django.utils import timezone
from google.cloud import storage
from django.contrib.sites.models import Site
from django.conf import settings
from django.urls import reverse
from project.validators import validate_doi

import logging

LOGGER = logging.getLogger(__name__)
ROLES = ['roles/storage.legacyBucketReader',
         'roles/storage.legacyObjectReader',
         'roles/storage.objectViewer']

# Manage GCP buckets

def check_bucket_exists(project, version):
    """
    Check if a bucket exists.
    """
    storage_client = storage.Client()
    bucket_name, email = bucket_info(project, version)
    if storage_client.lookup_bucket(bucket_name):
        return True
    return False

def create_bucket(project, version, title, protected=True):
    """
    Create a bucket with either public or private permissions.

    There are two different types of buckets:
     - Public which are open to the world.
     - Private which access is handled by an organizational email.
    """
    storage_client = storage.Client()
    bucket_name, email = bucket_info(project, version)

    bucket = storage_client.bucket(bucket_name)
    # Only bucket-level permissions are enforced; there are no per-file ACLs.
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
    # Clients accessing this bucket will be billed for download costs.
    bucket.requester_pays = True
    storage_client.create_bucket(bucket)

    LOGGER.info("Created bucket {0} for project {1}".format(
        bucket_name.lower(), project))
    if protected:
        remove_bucket_permissions(bucket)
        group = create_access_group(bucket, project, version, title)
        LOGGER.info("Removed permissions from bucket {0} and created {1} "
                    "for read access".format(bucket_name.lower(), group))
    else:
        make_bucket_public(bucket)
        LOGGER.info("Made bucket {0} public".format(bucket_name.lower()))


def bucket_info(project, version):
    """
    Generate the bucket name or the email for managing access to the bucket.

    Returns the bucketname and the email if the project is not public.
    """
    name = '{0}{1}-{2}'.format(settings.GCP_BUCKET_PREFIX, project, version)
    email = '{0}@{1}'.format(name, settings.GCP_DOMAIN)
    bucket = '{0}.{1}'.format(name, settings.GCP_DOMAIN)

    return bucket, email


def make_bucket_public(bucket):
    """
    Make a bucket public to all users.
    """
    policy = bucket.get_iam_policy()
    for role in ROLES:
        policy[role].add('allUsers')
    bucket.set_iam_policy(policy)
    LOGGER.info("Made bucket {} public".format(bucket.name))


def remove_bucket_permissions(bucket):
    """
    Remove all permissions from a bucket for everyone except the owner.
    """
    policy = bucket.get_iam_policy()
    to_remove = []

    for role in policy:
        if role != 'roles/storage.legacyBucketOwner':
            for member in policy[role]:
                to_remove.append([role, member])

    for item in to_remove:
        policy[item[0]].discard(item[1])

    if to_remove:
        bucket.set_iam_policy(policy)
        LOGGER.info("Removed all read permissions from "
                    "bucket {}".format(bucket.name))


def create_access_group(bucket, project, version, title):
    """
    Create an access group with appropriate permissions, if the group does not
    already exist.

    Returns:
        bool: False if there was an error or change to the API. True otherwise.
    """
    bucket_name, email = bucket_info(project, version)
    service = create_directory_service(settings.GCP_DELEGATION_EMAIL)

    # Get all the members of the Google group
    try:
        outcome = service.groups().list(domain=settings.GCP_DOMAIN).execute()
        if not any(group['email'] in email for group in outcome['groups']):
            creation = service.groups().insert(body={
                'email': email,
                'name': '{0} v{1}'.format(title, version),
                'description': "Access group for the project {0} version "
                               "{1}.".format(title, version)}).execute()
            if creation['kind'] != 'admin#directory#group':
                LOGGER.info("Error {0} creating the "
                            "group {1}.".format(creation, email))
                return False
            LOGGER.info("Access group {0} was created.".format(email))
            if update_access_group(email):
                LOGGER.info("Access group {0} was updated.".format(email))
        else:
            LOGGER.info("Access group {0} already exists.".format(email))
    except HttpError as e:
        if json.loads(e.content)['error']['message'] != 'Member already exists.':
            LOGGER.info("Error {0} creating the access group {1} for "
                        "{1}.".format(e.content, email, project))
            raise e
        else:
            LOGGER.info("Access group {0} already exists.".format(email))

    return email


def update_access_group(email):
    """
    Set permissions for an access group.

    Returns:
        bool: False if there was an error or change to the API. True otherwise.
    """
    service = create_directory_service(settings.GCP_DELEGATION_EMAIL,
                                       group=True)
    update = service.groups().update(groupUniqueId=email, body={
        'allowExternalMembers': 'true',
        'whoCanPostMessage': 'ALL_OWNERS_CAN_POST',
        'whoCanModerateMembers': 'OWNERS_AND_MANAGERS',
        'whoCanJoin': 'INVITED_CAN_JOIN'}).execute()

    if update['kind'] != 'groupsSettings#groups':
        LOGGER.info("Error {0} setting the permissions for group "
                    "{1}".format(update, email))
        return False

    return True


def add_email_bucket_access(project, email, group=False):
    """
    Grant access to a bucket for the specified email address.

    Returns:
        bool: True is access is successfully granted. False otherwise.
    """
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(project.gcp.bucket_name)
    policy = bucket.get_iam_policy()

    if group:
        for role in ROLES:
            policy[role].add('group:'+email)
    else:
        for role in ROLES:
            policy[role].add('user:'+email)

    try:
        bucket.set_iam_policy(policy)
        LOGGER.info("Added email {0} to the project {1} access list".format(
            email, project))
        return True
    except BadRequest:
        LOGGER.info("Error in the request. The email {} was "
                    "ignored.".format(email))
        return False


def upload_files(project):
    """
    Upload files to a bucket. Gets a list of all the files under the project
    root directory, then sends each file individually. Check storage size to
    confirm that the zip file was created.
    """
    file_root = project.file_root()
    subfolders_fullpath = [x[0] for x in walk(file_root)]
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(project.gcp.bucket_name)

    for indx, location in enumerate(subfolders_fullpath):
        chdir(location)
        files = [f for f in listdir('.') if path.isfile(f)]
        for file in files:
            temp_dir = location.replace(file_root, '')
            if temp_dir != '':
                blob = bucket.blob(path.join(temp_dir, file)[1:])
                blob.upload_from_filename(file)
            else:
                blob = bucket.blob(file)
                blob.upload_from_filename(file)

    if project.compressed_storage_size:
        zip_name = project.zip_name()
        chdir(project.project_file_root())
        blob = bucket.blob(zip_name)
        blob.upload_from_filename(zip_name)


def create_directory_service(user_email, group=False):
    """
    Create an Admin SDK Directory Service object authorized with the service
    accounts that act on behalf of the given user.

    Args:
        user_email: The user's email address. Needs permission to access the
                    Admin API.
    Returns:
        Admin SDK Directory Service object.
    """
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
    credentials, _  = google.auth.default(scopes=[
        'https://www.googleapis.com/auth/admin.directory.group',
        'https://www.googleapis.com/auth/apps.groups.settings',
    ])

    # The email for delegating credentials to the service account is required.
    credentials = credentials.with_claims({'sub': user_email})

    if group:
        return build('groupssettings', 'v1', credentials=credentials)
    return build('admin', 'directory_v1', credentials=credentials)
