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
import boto3
import os
import re

import logging

LOGGER = logging.getLogger(__name__)
ROLES = ['roles/storage.legacyBucketReader',
         'roles/storage.legacyObjectReader',
         'roles/storage.objectViewer']


class DOIExistsError(Exception):
    pass


class DOICreationError(Exception):
    pass

# Manage AWS buckets and objects

def create_s3_access_object():
    """
    Create and return an AWS S3 client object.

    This function establishes a session with AWS using the specified AWS profile
    from the 'settings' module and initializes an S3 client object for interacting with
    Amazon S3 buckets and objects.

    Note:
    - Ensure that the AWS credentials (Access Key and Secret Key) are properly
      configured in the AWS CLI profile.
    - The AWS_PROFILE should be defined in the settings module.

    Returns:
        botocore.client.S3: An initialized AWS S3 client object.
    """
    session = boto3.Session(profile_name=settings.AWS_PROFILE)
    s3 = session.client('s3')
    return s3

def get_bucket_name(project):
    """
    Determine and return the S3 bucket name associated with a given project.

    This function calculates the S3 bucket name based on the project's slug and version.
    If the project has a specific access policy defined, the bucket name will be generated
    accordingly. For projects with an 'OPEN' access policy, the default bucket name is specified
    in settings.OPEN_ACCESS_DATA_BUCKET_NAME. For other access policies ('RESTRICTED', 'CREDENTIALED', 'CONTRIBUTOR_REVIEW'),
    the bucket name is constructed using the project's slug and version.

    Args:
        project (project.models.Project): The project for which to determine the S3 bucket name.

    Returns:
        str: The S3 bucket name associated with the project.

    Note:
    - This function does not create or verify the existence of the actual S3 bucket; it only provides
      the calculated bucket name based on project attributes.
    """
    from project.models import AccessPolicy

    bucket_name = project.slug + "-" + project.version

    if project.access_policy == AccessPolicy.OPEN:
        bucket_name = settings.OPEN_ACCESS_DATA_BUCKET_NAME
    elif project.access_policy == AccessPolicy.RESTRICTED or project.access_policy == AccessPolicy.CREDENTIALED or project.access_policy == AccessPolicy.CONTRIBUTOR_REVIEW:
        bucket_name = project.slug + "-" + project.version
    return bucket_name

def get_bucket_name_and_prefix(project):
    """
    Determine the S3 bucket name and optional prefix for a given project.

    This function calculates the S3 bucket name based on the project's attributes. If the project
    has an 'OPEN' access policy and a non-empty prefix defined, the bucket name includes the prefix.
    For all other access policies or if no prefix is defined, the bucket name consists of the
    calculated project-specific name only.

    Args:
        project (project.models.Project): The project for which to determine the S3 bucket name and prefix.

    Returns:
        str: The S3 bucket name and an optional prefix associated with the project.

    Note:
    - This function does not create or verify the existence of the actual S3 bucket; it only provides
      the calculated bucket name and prefix based on project attributes.
    """
    from project.models import AccessPolicy

    prefix = get_prefix_open_project(project)
    if project.access_policy == AccessPolicy.OPEN and prefix is not None:
        bucket_name = get_bucket_name(project) + "/" + prefix
    else:
        bucket_name = get_bucket_name(project)
    return bucket_name

def get_all_prefixes(project):
    """
    Retrieve a list of all prefixes (directories) for objects within the S3 bucket associated with the given project.

    This function checks if the S3 bucket for the project exists, and if so, it initializes an S3 client,
    specifies the bucket name, and lists the common prefixes (directories) within the bucket. The retrieved
    prefixes are returned as a list.

    Args:
        project (project.models.Project): The project for which to retrieve all prefixes.

    Returns:
        list: A list of common prefixes (directories) within the S3 bucket.

    Note:
    - This function does not create or modify objects within the S3 bucket, only retrieves directory-like prefixes.
    - Make sure that AWS credentials (Access Key and Secret Key) are properly configured for this function to work.
    - The S3 bucket should exist and be accessible based on the project's configuration.
    """
    common_prefixes = []
    if check_s3_bucket_exists(project):
        # Initialize the S3 client
        s3 = create_s3_access_object()

        # Specify the bucket name
        bucket_name = get_bucket_name(project)

        # List the prefixes (common prefixes or "directories")
        response = s3.list_objects_v2(
            Bucket=bucket_name,
            Delimiter='/'
        )

        # Extract the prefixes
        common_prefixes = response.get('CommonPrefixes', [])
    return common_prefixes

def get_prefix_open_project(project):
    """
    Retrieve the prefix (directory) specific to an open project.

    This function checks if the project's access policy is 'OPEN'. If it is, the function constructs
    the target prefix based on the project's slug and version, and then finds the matching prefix
    within the S3 bucket's list of prefixes (directories).

    Args:
        project (project.models.Project): The open project for which to retrieve the specific prefix.

    Returns:
        str or None: The matching prefix if the project is open; otherwise, None.

    Note:
    - This function is intended for open projects only; for other access policies, it returns None.
    - Ensure that the project's S3 bucket exists and is properly configured.
    """
    from project.models import AccessPolicy

    if project.access_policy != AccessPolicy.OPEN:
        return None
    else:
        target_prefix = project.slug + "-" + project.version + "/"
        matching_prefix = find_matching_prefix(get_all_prefixes(project), target_prefix)
    return matching_prefix

def find_matching_prefix(prefix_list, target_prefix):
    """
    Find and return the matching prefix within a list of prefixes for a given target prefix.

    This function iterates through a list of prefixes (commonly found in S3 bucket listings) and compares
    each prefix to the provided target prefix. If a match is found, the matching prefix is returned after
    stripping any trailing slashes ('/').

    Args:
        prefix_list (list): A list of prefixes to search through.
        target_prefix (str): The prefix to match against the list.

    Returns:
        str or None: The matching prefix without trailing slashes, or None if no match is found.
    """
    for prefix_info in prefix_list:
        prefix = prefix_info.get('Prefix', '')
        if prefix == target_prefix:
            return prefix.rstrip('/')
    return None

def get_list_prefixes(common_prefixes):
    """
    Extract and return a list of prefixes from a given list of common prefixes.

    This function takes a list of common prefixes (often obtained from S3 bucket listings)
    and extracts the 'Prefix' values from each element, returning them as a list.

    Args:
        common_prefixes (list): A list of common prefixes, typically from an S3 bucket listing.

    Returns:
        list: A list of extracted prefixes.
    """
    perfixes = [prefix.get('Prefix') for prefix in common_prefixes]
    return perfixes

def check_s3_bucket_exists(project):
    """
    Check the existence of an S3 bucket associated with the given project.

    This function uses the provided project to determine the S3 bucket's name. It then
    attempts to validate the existence of the bucket by sending a 'HEAD' request to AWS S3.
    If the bucket exists and is accessible, the function returns True; otherwise, it returns False.

    Args:
        project (project.models.Project): The project for which to check the S3 bucket's existence.

    Returns:
        bool: True if the S3 bucket exists and is accessible, False otherwise.

    Note:
    - Make sure that AWS credentials (Access Key and Secret Key) are properly configured
      for this function to work.
    - The S3 bucket should exist and be accessible based on the project's configuration.
    """
    s3 = create_s3_access_object()
    bucket_name = get_bucket_name(project)
    try:
        s3.head_bucket(Bucket=bucket_name)
        return True
    except:
        return False
    
def check_s3_bucket_with_prefix_exists(project):
    """
    Check the existence of an S3 bucket, considering the optional prefix for open projects.

    This function assesses whether an S3 bucket associated with the given project exists.
    If the project has an 'OPEN' access policy and a non-empty prefix defined, the function
    checks for the existence of the bucket along with the prefix. For all other access policies
    or if no prefix is defined, it checks only the existence of the bucket.

    Args:
        project (project.models.Project): The project for which to check the S3 bucket's existence.

    Returns:
        bool: True if the S3 bucket (and optional prefix) exists and is accessible, False otherwise.

    Note:
    - Make sure that AWS credentials (Access Key and Secret Key) are properly configured
      for this function to work.
    - The S3 bucket should exist and be accessible based on the project's configuration.
    """
    from project.models import AccessPolicy
    prefix = get_prefix_open_project(project)
    if project.access_policy == AccessPolicy.OPEN and prefix is None:
        return False
    else:
        return check_s3_bucket_exists(project)

def create_s3_bucket(s3, bucket_name):
    """
    Create a new Amazon S3 bucket with the specified name.

    This function uses the provided S3 client ('s3') to create a new S3 bucket
    with the given 'bucket_name'.

    Args:
        s3 (boto3.client.S3): An initialized AWS S3 client object.
        bucket_name (str): The desired name for the new S3 bucket.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key) are properly configured
      for the provided 's3' client to create the bucket.
    - Bucket names must be globally unique within AWS S3, so choose a unique name.
    """
    s3.create_bucket(Bucket=bucket_name)

def send_files_to_s3(folder_path, s3_prefix, bucket_name): 
    """
    Upload files from a local folder to an AWS S3 bucket with a specified prefix.

    This function walks through the files in the local 'folder_path' and uploads each file
    to the specified AWS S3 'bucket_name' under the 's3_prefix' directory. It uses an initialized
    AWS S3 client to perform the file uploads.

    Args:
        folder_path (str): The local folder containing the files to upload.
        s3_prefix (str): The prefix (directory) within the S3 bucket where files will be stored.
        bucket_name (str): The name of the AWS S3 bucket where files will be uploaded.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key) are properly configured for
      the S3 client used in this function.
    """
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            local_file_path = os.path.join(root, file_name)
            s3_key = os.path.join(s3_prefix, os.path.relpath(local_file_path, folder_path))
            create_s3_access_object().upload_file(
                Filename=local_file_path,
                Bucket=bucket_name,
                Key=s3_key,
            )

def get_aws_accounts_for_dataset(dataset_name):
    """
    Retrieve AWS account IDs associated with a given dataset's authorized users.

    This function identifies AWS account IDs associated with users who are authorized to access
    the specified project. It searches for AWS account IDs among users with cloud information 
    and permissions to view project files.

    Args:
        dataset_name (str): The name of the dataset for which to retrieve AWS account IDs.

    Returns:
        list: A list of AWS account IDs associated with authorized users of the dataset.

    Note:
    - This function assumes that AWS account IDs are 12-digit numerical values.
    - Users with the appropriate permissions and AWS account IDs are included in the result list.
    """
    from project.models import PublishedProject
    from user.models import User
    from project.authorization.access import can_view_project_files

    aws_accounts = []

    published_projects = PublishedProject.objects.all()
    users_with_awsid = User.objects.filter(cloud_information__aws_id__isnull=False)
    aws_id_pattern = r"\b\d{12}\b"

    for project in published_projects:
        project_name = project.slug + "-" + project.version
        if project_name == dataset_name:
            for user in users_with_awsid:
                if can_view_project_files(project, user):
                    if re.search(aws_id_pattern, user.cloud_information.aws_id):
                        aws_accounts.append(user.cloud_information.aws_id)
            break  # Stop iterating once the dataset is found
    
    return aws_accounts

def get_initial_bucket_policy(bucket_name):
    """
    Create an initial bucket policy for an AWS S3 bucket.
    """
    bucket_policy ={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "DenyListAndGetObject",
                "Effect": "Deny",
                "Principal": "*",
                "Action": [
                    "s3:Get*",
                    "s3:List*"
                ],
                "Resource": [
                    f'arn:aws:s3:::{bucket_name}',
                    f'arn:aws:s3:::{bucket_name}/*'
                ],
                "Condition": {
                "StringNotLike": {
                    "aws:PrincipalArn": "arn:aws:iam::724665945834:*"
                }
            }
            }
        ]
        }
    # Convert the policy from JSON dict to string
    bucket_policy_str = json.dumps(bucket_policy)

    return bucket_policy_str

def create_bucket_policy(bucket_name, aws_ids, public):
    """
    Generate an initial AWS S3 bucket policy that restricts access.

    This function creates a default AWS S3 bucket policy with restricted access. The policy denies
    list and get actions for all principals except for a specified AWS account, which is allowed
    to access the bucket.

    Args:
        bucket_name (str): The name of the AWS S3 bucket for which to generate the initial policy.

    Returns:
        str: A JSON-formatted string representing the initial bucket policy.

    Note:
    - This initial policy serves as a baseline and can be customized further to meet specific access
      requirements for the bucket.
    """
    user = None
    principal_value = '*' if public else {'AWS': [f'arn:aws:iam::{aws_id}:root' if user is None or user == '' else f'arn:aws:iam::{aws_id}:user/{user}' for aws_id in aws_ids]}
    
    bucket_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowReadOnlyAccess",
            "Effect": "Allow",
            'Principal': principal_value,
            'Action': ["s3:Get*", "s3:List*"],
            'Resource': [f'arn:aws:s3:::{bucket_name}', f'arn:aws:s3:::{bucket_name}/*']
        },
        {
            "Sid": "RestrictDeleteActions",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:Delete*",
            "Resource": f'arn:aws:s3:::{bucket_name}/*',
            "Condition": {
                "StringNotLike": {
                    "aws:PrincipalArn": "arn:aws:iam::724665945834:*"
                }
            }
        }
    ]
    }

    # Convert the policy from JSON dict to string
    bucket_policy_str = json.dumps(bucket_policy)

    return bucket_policy_str

def set_bucket_policy(bucket_name, bucket_policy):
    """
    Apply a custom AWS S3 bucket policy to a specified bucket.

    This function utilizes an AWS S3 client to set the custom 'bucket_policy' for the
    specified 'bucket_name', effectively configuring access controls and permissions for
    objects within the bucket.

    Args:
        bucket_name (str): The name of the AWS S3 bucket for which to set the custom policy.
        bucket_policy (str): A JSON-formatted string representing the custom bucket policy.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key) are properly configured for
      the S3 client used in this function.
    - The 'bucket_policy' should be a valid JSON string adhering to AWS S3 policy syntax.
    """ 
    s3 = create_s3_access_object()
    s3.put_bucket_policy(Bucket=bucket_name, Policy=bucket_policy)

def put_public_access_block(client, bucket_name, configuration):
    """
    Configure Amazon S3 Block Public Access settings for a bucket.

    Amazon S3 Block Public Access provides settings for buckets to control and manage public access
    to Amazon S3 resources. By default, new buckets do not allow public access. This function
    sets the specified configuration for the given bucket to allow or restrict public access.

    Args:
        client (boto3.client.S3): An initialized AWS S3 client object.
        bucket_name (str): The name of the S3 bucket to configure.
        configuration (bool): The desired configuration for public access. Set to 'True' to allow
                             public access or 'False' to restrict public access.

    Returns:
        None

    Note:
    - To create a bucket that allows public access, you must set 'configuration' to 'True' for all four settings:
      'BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', and 'RestrictPublicBuckets'.
    - Ensure that AWS credentials (Access Key and Secret Key) are properly configured for the provided 'client'.
    """
    client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': configuration,
            'IgnorePublicAcls': configuration,
            'BlockPublicPolicy': configuration,
            'RestrictPublicBuckets': configuration
        }
    )

def update_bucket_policy(project, bucket_name):
    """
    Update the AWS S3 bucket's access policy based on the project's access policy.

    This function manages the AWS S3 bucket's access policy for the specified 'bucket_name'
    based on the 'project' object's access policy. It performs the following actions:
    - For projects with an 'OPEN' access policy, it allows public access by removing any
      public access blocks and applying a policy allowing public reads.
    - For projects with other access policies (e.g., 'CREDENTIALED', 'RESTRICTED', 'CONTRIBUTOR_REVIEW'),
      it sets a policy that limits access to specific AWS accounts belonging to users authorized to access
      the specified project.

    Args:
        project (project.models.Project): The project for which to update the bucket policy.
        bucket_name (str): The name of the AWS S3 bucket associated with the project.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key) are properly configured for
      the S3 client used in this function.
    """
    from project.models import AccessPolicy

    project_name = project.slug + "-" + project.version 
    aws_ids = get_aws_accounts_for_dataset(project_name)
    if project.access_policy == AccessPolicy.OPEN:
        put_public_access_block(create_s3_access_object(), bucket_name, False)
        bucket_policy = create_bucket_policy(bucket_name, aws_ids, True)
    elif project.access_policy == AccessPolicy.CREDENTIALED or project.access_policy == AccessPolicy.RESTRICTED or project.access_policy == AccessPolicy.CONTRIBUTOR_REVIEW:
        if aws_ids == []:
            bucket_policy = get_initial_bucket_policy(bucket_name)
        else:
            bucket_policy = create_bucket_policy(bucket_name, aws_ids, False)
        
    set_bucket_policy(bucket_name, bucket_policy)

def upload_project_to_S3(project):
    """
    Upload project-related files to an AWS S3 bucket associated with the project.

    This function orchestrates the process of uploading project files to an AWS S3 bucket.
    It performs the following steps:
    1. Creates the S3 bucket if it doesn't exist.
    2. Updates the bucket's access policy to align with the project's requirements.
    3. Uploads project files from the local directory to the S3 bucket.

    Args:
        project (project.models.Project): The project for which to upload files to S3.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key) are properly configured for
      the S3 client used in this function.
    - The 'project_name' variable is created by concatenating the project's slug and version.
    - The 's3_prefix' is set only for projects with an 'OPEN' access policy, providing
      an optional prefix within the S3 bucket.
    """
    from project.models import AccessPolicy
    bucket_name = get_bucket_name(project)
    # create bucket if it does not exist
    create_s3_bucket(create_s3_access_object(), bucket_name)

    # update bucket's policy for projects
    update_bucket_policy(project, bucket_name)

    # upload files to bucket
    folder_path = project.project_file_root()  # Folder containing files to upload
    project_name = project.slug + "-" + project.version 

    # set the prefix only for the projects in the open data bucket
    s3_prefix = ""
    if project.access_policy == AccessPolicy.OPEN:
        s3_prefix = f"{project_name}/"
    send_files_to_s3(folder_path, s3_prefix, bucket_name)

def upload_list_of_projects(projects):
    """
    Bulk upload a list of projects to AWS S3.

    This function iterates through the provided list of 'projects' and uploads each project's files
    to an AWS S3 bucket. It delegates the file upload process to the 'upload_project_to_S3' function.

    Args:
        projects (list of project.models.Project): A list of projects to upload to AWS S3.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key) are properly configured for
      the S3 client used in the 'upload_project_to_S3' function.
    """
    for project in projects:
        upload_project_to_S3(project)

def upload_all_projects():
    """
    Bulk upload all published projects to AWS S3.

    This function retrieves all published projects from the database and uploads the files
    associated with each project to an AWS S3 bucket. It leverages the 'upload_project_to_S3'
    function for the file upload process.

    Args:
        None

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key) are properly configured for
      the S3 client used in the 'upload_project_to_S3' function.
    """
    from project.models import PublishedProject
    published_projects = PublishedProject.objects.all()
    for project in published_projects:
        upload_project_to_S3(project)

def empty_s3_bucket(bucket):
    """
    Delete all objects (files) within an AWS S3 bucket.

    This function iterates through all objects within the specified 'bucket' and deletes each object,
    effectively emptying the bucket of its contents.

    Args:
        bucket (boto3.resources.factory.s3.Bucket): The AWS S3 bucket to empty.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key) with sufficient permissions
      are properly configured for the S3 client used in this function.
    """
    for key in bucket.objects.all():
        key.delete()

def empty_project_from_S3(project):
    """
    Empty an AWS S3 bucket associated with a project.

    This function removes all files within the AWS S3 bucket associated with the specified 'project',
    effectively emptying the bucket. It leverages the 'empty_s3_bucket' function for this purpose.

    Args:
        project (project.models.Project): The project for which to empty the associated AWS S3 bucket.

    Returns:
        None

    Note:
    - The function ensures that the AWS S3 bucket remains intact but contains no files after execution.
    - Ensure that AWS credentials (Access Key and Secret Key) with sufficient permissions
      are properly configured for the S3 client used in this function.
    """
    boto3.setup_default_session(settings.AWS_PROFILE)
    s3 = boto3.resource('s3')
    bucket_name = get_bucket_name(project)
    bucket = s3.Bucket(bucket_name)
    empty_s3_bucket(bucket)   

def empty_list_of_projects(projects):
    """
    Bulk empty AWS S3 buckets associated with a list of projects.

    This function takes a list of 'projects' and empties the AWS S3 buckets associated with each project,
    effectively removing all files within them. It delegates the emptying process to the 'empty_project_from_S3'
    function.

    Args:
        projects (list of project.models.Project): A list of projects for which to empty the associated AWS S3 buckets.

    Returns:
        None

    Note:
    - The function ensures that AWS S3 buckets remain intact but contain no files after execution.
    - Ensure that AWS credentials (Access Key and Secret Key) with sufficient permissions
      are properly configured for the S3 client used in this function.
    """
    for project in projects:
        empty_project_from_S3(project)

def empty_all_projects_from_S3():
    """
    Bulk empty all AWS S3 buckets associated with published projects.

    This function iterates through all published projects in the database and empties the AWS S3
    buckets associated with each project, effectively removing all files within them. It leverages
    the 'empty_project_from_S3' function for this purpose.

    Args:
        None

    Returns:
        None

    Note:
    - The function ensures that AWS S3 buckets remain intact but contain no files after execution.
    - Ensure that AWS credentials (Access Key and Secret Key) with sufficient permissions
      are properly configured for the S3 client used in this function.
    """
    from project.models import PublishedProject
    # Retrieve all published projects from the database
    published_projects = PublishedProject.objects.all()
    # Empty the AWS S3 buckets associated with each published project
    for project in published_projects:
        empty_project_from_S3(project)

def delete_project_from_S3(project):
    """
    Delete a project's files and associated AWS S3 bucket.

    This function cleans up and removes all files associated with the specified 'project' from an
    AWS S3 bucket. It then deletes the empty S3 bucket itself.

    Args:
        project (project.models.Project): The project for which to delete files and the associated bucket.

    Returns:
        None

    Note:
    - The function leverages the 'delete_s3_bucket' method to perform the deletion.
    - Ensure that AWS credentials (Access Key and Secret Key) with sufficient permissions
      are properly configured for the S3 client used in this function.
    """
    boto3.setup_default_session(settings.AWS_PROFILE)
    s3 = boto3.resource('s3')
    bucket_name = get_bucket_name(project)
    bucket = s3.Bucket(bucket_name)
    # Empty the specified AWS S3 'bucket' by deleting all objects (files) within it
    empty_s3_bucket(bucket)
    # Delete the empty bucket itself
    bucket.delete()   

def delete_list_of_projects_from_s3(projects):
    """"
    Bulk delete a list of projects from AWS S3.

    This function deletes a list of projects, including their files and associated AWS S3 buckets.
    If the list includes open projects, the 'delete_project_from_S3' function will be called only once
    for the first open project encountered.

    Args:
        projects (list of project.models.Project): A list of projects to delete from AWS S3.

    Returns:
        None

    Note:
    - The function leverages the 'delete_project_from_S3' method to perform project deletions.
    - Ensure that AWS credentials (Access Key and Secret Key) with sufficient permissions
      are properly configured for the S3 client used in this function.
    """
    for project in projects:
        delete_project_from_S3(project)
        if project.access_policy == AccessPolicy.OPEN:
            break

def delete_all_projects_from_S3():
    """
    Bulk delete all published projects from AWS S3.

    This function deletes all published projects, including their files and associated AWS S3 buckets.
    It distinguishes between open and non-open projects, calling the 'delete_project_from_S3' function
    accordingly. Non-open projects, such as 'RESTRICTED', 'CREDENTIALED', or 'CONTRIBUTOR_REVIEW', are
    deleted individually. Open projects are stored in the same S3 bucket, so only one delete operation
    is needed, which is performed by passing the first open project.

    Args:
        None

    Returns:
        None

    Note:
    - The function leverages the 'delete_project_from_S3' method to perform project deletions.
    - Ensure that AWS credentials (Access Key and Secret Key) with sufficient permissions
      are properly configured for the S3 client used in this function.
    """
    from project.models import PublishedProject, AccessPolicy
    not_open_published_projects = PublishedProject.objects.filter(access_policy=AccessPolicy.RESTRICTED) | PublishedProject.objects.filter(access_policy=AccessPolicy.CREDENTIALED) | PublishedProject.objects.filter(access_policy=AccessPolicy.CONTRIBUTOR_REVIEW)
    for project in not_open_published_projects:
        delete_project_from_S3(project)
    # since all open projects are stored in the same bucket, we only need to delete the bucket once
    # by passing the first open project
    delete_project_from_S3(PublishedProject.objects.filter(access_policy=AccessPolicy.OPEN)[0])

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


def register_doi(payload, project):
    """
    Create a DOI with basic project information via a POST request. Saves
    the DOI to the project.doi field.

    Args:
        payload (dict): The metadata to be sent to the DataCite API.
        project (obj): The ActiveProject, PublishedProject, or CoreProject
            that is associated with the payload.

    Example of the API return response.
    {
       'data':{
          'id':'10.7966/v2jx-h492',
          'type':'dois',
          'attributes':{
             'doi':'10.7966/v2jx-h492',
             'prefix':'10.7966',
             'suffix':'v2jx-h492',
             'identifiers':None,
             'creators':[ ],
             'titles':[ { 'title':'Example title' } ],
             'publisher':'PhysioNet-dev',
             'container':{ },
             'publicationYear':2020,
             'subjects':None,
             'contributors':[ ],
             'dates':None,
             'language':None,
             'types':{ 'resourceTypeGeneral':'Dataset' },
             'relatedIdentifiers':None,
             'sizes':None,
             'formats':None,
             'version':None,
             'rightsList':[ ],
             'descriptions':None,
             'geoLocations':None,
             'fundingReferences':None,
             'xml':'',
             'url':None,
             'contentUrl':None,
             'metadataVersion':0,
             'schemaVersion':None,
             'source':None,
             'isActive':False,
             'state':'draft',
             'reason':None,
             'landingPage':None,
             'viewCount':0,
             'downloadCount':0,
             'referenceCount':0,
             'citationCount':0,
             'partCount':0,
             'partOfCount':0,
             'versionCount':0,
             'versionOfCount':0,
             'viewsOverTime':[ ],
             'downloadsOverTime':[ ],
             'created':'2020-02-09T15:24:49.000Z',
             'registered':None,
             'published':'2020',
             'updated':'2020-02-09T15:24:49.000Z'
          },
          'relationships':{
             'client':{
                'data':{
                   'id':'XYZ.XYZ',
                   'type':'clients'
                }
             },
             'media':{
                'data':{
                   'id':'10.7966/v2jx-h492',
                   'type':'media'
                }
             },
             'references':{ 'data':[ ] },
             'citations':{ 'data':[ ] },
             'parts':{ 'data':[ ] },
             'versions':{ 'data':[ ] }
          }
       },
       'included':[
          {
             'id':'XYZ.XYZ',
             'type':'clients',
             'attributes':{
                'name':'XYZ',
                'symbol':'XYZ.XYZ',
                'year':2019,
                'contactEmail':'XYZ@XYZ.XYZ',
                'alternateName':None,
                'description':None,
                'language':None,
                'clientType':'repository',
                'domains':'*',
                're3data':None,
                'opendoar':None,
                'issn':{ },
                'url':'https://www.physionet.org/',
                'created':'2019-02-25T18:25:27.000Z',
                'updated':'2020-01-23T20:10:43.000Z',
                'isActive':True,
                'hasPassword':True
             },
             'relationships':{
                'provider':{
                   'data':{
                      'id':'XYZ',
                      'type':'providers'
                   }
                },
                'prefixes':{
                   'data':[
                      {
                         'id':'10.7966',
                         'type':'prefixes'
                      }
                   ]
                }
             }
          }
       ]
    }
    """
    headers = {'Content-Type': 'application/vnd.api+json'}
    request_url = settings.DATACITE_API_URL

    # Check whether the project already has a DOI assigned.
    # type(project) returns CoreProject, ActiveProject, or PublishedProject
    queryset = type(project).objects.filter(id=project.id, doi=None)

    # Hold DOI field to prevent multiple calls from registering multiple DOIs.
    if queryset.update(doi='PENDING') != 1:
        raise DOIExistsError('Project already has a DOI')
    doi = None

    try:
        response = post(request_url, data=json.dumps(payload), headers=headers,
                        auth=HTTPBasicAuth(settings.DATACITE_USER,
                        settings.DATACITE_PASS))

        if response.status_code < 200 or response.status_code >= 300:
            # Remove the pending status
            raise DOICreationError("""There was an unknown error creating the
                DOI. Here is the response text: {}""".format(response.text))

        content = json.loads(response.text)
        doi = content['data']['attributes']['doi']
        validate_doi(doi)

        event = payload['data']['attributes']['event']
        title = payload['data']['attributes']['titles'][0]['title']
        LOGGER.info("DOI ({0}) for project '{1}' created: {2}.".format(event,
                                                                       title,
                                                                       doi))
    finally:
        # Update the DOI field for the project
        queryset = type(project).objects.filter(id=project.id, doi='PENDING')
        queryset.update(doi=doi)


def update_doi(doi, payload):
    """
    Update metadata for a registered DOI via a PUT request.

    Args:
        doi (str): The doi to be updated.
        payload (dict): The metadata to be sent to the DataCite API.
    """
    headers = {'Content-Type': 'application/vnd.api+json'}
    request_url = '{0}/{1}'.format(settings.DATACITE_API_URL, doi)

    response = put(request_url, data=json.dumps(payload), headers=headers,
                   auth=HTTPBasicAuth(settings.DATACITE_USER,
                   settings.DATACITE_PASS))

    if response.status_code < 200 or response.status_code >= 300:
        raise Exception("""There was an unknown error updating the DOI. Here
            is the response text: {0}""".format(response.text))

    event = payload['data']['attributes']['event']
    title = payload['data']['attributes']['titles'][0]['title']

    LOGGER.info("DOI ({0}) for project '{1}' updated: {2}.".format(event,
                                                                   title, doi))


def generate_doi_payload(project, core_project=False, event="draft"):
    """
    Generate a payload for registering or updating a DOI.

    Args:
        project (obj): Project object.
        core_project (bool): If the metadata relates to the core project
            then core_project=True, else core_project=False.
        event (str): Either "draft" or "publish".

    Returns:
        payload (dict): The metadata to be sent to the DataCite API.
    """
    current_site = Site.objects.get_current()

    if event == "publish" and core_project:
        project_url = "https://{0}{1}".format(current_site, reverse(
            'published_project_latest', args=(project.slug,)))
    elif event == "publish":
        project_url = "https://{0}{1}".format(current_site, reverse(
            'published_project', args=(project.slug, project.version)))
    else:
        project_url = ""

    if core_project:
        version = "latest"
    else:
        version = project.version

    authors = []
    if event == "publish":
        author_list = project.author_list().order_by('display_order')
        for author in author_list:
            author_metadata = {"givenName": author.first_names,
                               "familyName": author.last_name,
                               "name": author.get_full_name(reverse=True)}
            if author.user.has_orcid():
                author_metadata["nameIdentifiers"] = [{
                    "nameIdentifier": f'https://orcid.org/{author.user.get_orcid_id()}',
                    "nameIdentifierScheme": "ORCID",
                    "schemeUri": "https://orcid.org/"
                }]
            authors.append(author_metadata)

    # link to parent or child projects
    if event == "publish" and core_project:
        # add children if core project
        versions = project.core_project.get_published_versions()
        relation = []
        for v in versions:
            relation.append({"relationType": "HasVersion",
                             "relatedIdentifier": v.doi,
                             "relatedIdentifierType": "DOI"})
    elif event == "publish":
        # add parent if not core project
        relation = [{
          "relationType": "IsVersionOf",
          "relatedIdentifier": project.core_project.doi,
          "relatedIdentifierType": "DOI"
        }]
    else:
        relation = []

    # projects from which this project is derived
    for parent_project in project.parent_projects.all():
        if parent_project.doi:
            relation.append({
                "relationType": "IsDerivedFrom",
                "relatedIdentifier": parent_project.doi,
                "relatedIdentifierType": "DOI",
            })
        else:
            url = "https://{0}{1}".format(current_site, reverse(
                'published_project',
                args=(parent_project.slug, parent_project.version)))
            relation.append({
                "relationType": "IsDerivedFrom",
                "relatedIdentifier": url,
                "relatedIdentifierType": "URL",
            })

    resource_type = 'Dataset'
    if project.resource_type.name == 'Software':
        resource_type = 'Software'

    payload = {
        "data": {
            "type": "dois",
            "attributes": {
                "event": event,
                "prefix": settings.DATACITE_PREFIX,
                "titles": [{
                    "title": project.title
                }],
                "publisher": current_site.name,
                "publicationYear": timezone.now().year,
                "types": {
                    "resourceTypeGeneral": resource_type
                },
                "creators": authors,
                "version": version,
                "descriptions": [{
                    "description": project.abstract_text_content(),
                    "descriptionType": "Abstract"
                }],
                "url": project_url,
                "relatedIdentifiers": relation,
            }
        }
    }

    return payload


def get_doi_status(project_doi):
    """
    Get the status of a DOI which can be draft, registered or findable.
    """
    headers = {'Content-Type': 'application/vnd.api+json'}
    url = '{0}/{1}'.format(settings.DATACITE_API_URL, project_doi)
    response = get(url, headers=headers, auth=HTTPBasicAuth(
        settings.DATACITE_USER, settings.DATACITE_PASS))
    if response.status_code < 200 or response.status_code >= 300:
        if response.status_code == 404:
            raise Exception("DOI {} not found.".format(project_doi))
        raise Exception("There was an unknown error updating the DOI, here is \
            the response text: {0}".format(response.text))
    content = json.loads(response.text)
    state = content['data']['attributes']['state']
    if state and isinstance(state, str):
        return state
    raise Exception('Unkown state of the DOI')
