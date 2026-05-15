import hashlib
import json
from math import ceil
import os
import re
import typing

import boto3
import botocore
from botocore.exceptions import ClientError
from django.conf import settings
from django.db.models import Q

from project.authorization.access import can_view_project_files
from project.models import PublishedProject, AWS, AccessPolicy, AWSAccessPoint, AWSAccessPointUser
from user.models import (
    User,
    CloudInformation
)

MAX_PRINCIPALS_PER_AP_POLICY = 500
MAX_RETRIES = 500

# Manage AWS buckets and objects
def has_S3_open_data_bucket_name():
    """
    Check if the S3_OPEN_ACCESS_BUCKET setting has a value set in the project's settings.

    This method verifies whether an open data bucket name has been specified for S3 storage.

    Returns:
        bool: Returns True if the S3_OPEN_ACCESS_BUCKET setting is set
        (i.e., truthy), False otherwise.
    """
    return bool(settings.S3_OPEN_ACCESS_BUCKET)


def has_S3_controlled_data_bucket_name():
    """
    Check if the S3_CONTROLLED_ACCESS_BUCKET setting has a value set in the project's settings.

    This method verifies whether a controlled-access data bucket name has been specified
    for S3 storage.

    Returns:
        bool: Returns True if the S3_CONTROLLED_ACCESS_BUCKET setting is set, False otherwise.
    """
    return bool(settings.S3_CONTROLLED_ACCESS_BUCKET)


def has_S3_geo_restricted_data_bucket_name():
    """
    Check if the S3_OPEN_ACCESS_BUCKET_WITH_LOGIN setting has a value set in the project's settings.

    This method verifies whether a geo-restricted data bucket name has been specified for S3 storage.

    Returns:
        bool: Returns True if the S3_OPEN_ACCESS_BUCKET_WITH_LOGIN setting is set
        (i.e., truthy), False otherwise.
    """
    return bool(settings.S3_OPEN_ACCESS_BUCKET_WITH_LOGIN)


def has_s3_credentials():
    """
    Check if AWS credentials have been set in
    the project's settings.

    Returns:
        bool: True if AWS credentials are set, False otherwise.
    """
    return all(
        [
            settings.AWS_PROFILE,
            settings.AWS_ACCOUNT_ID,
            settings.S3_OPEN_ACCESS_BUCKET,
            settings.S3_SERVER_ACCESS_LOG_BUCKET,
            settings.S3_CONTROLLED_ACCESS_BUCKET,
            settings.S3_OPEN_ACCESS_BUCKET_WITH_LOGIN,
        ]
    )


def files_sent_to_S3(project):
    """
    Check if project files were sent to Amazon S3.

    Args:
       project: Project instance

    bool: True if files were sent, False otherwise
    """
    try:
        aws_instance = project.aws
        return bool(aws_instance.sent_files)
    except AWS.DoesNotExist:
        return False


def create_s3_client():
    """
    Create and return an AWS S3 client object if
    AWS_PROFILE is not None.

    This function establishes a session with AWS using the
    specified AWS profile from the 'settings' module and initializes
    an S3 client object for interacting with Amazon S3 buckets
    and objects.

    Note:
    - Ensure that the AWS credentials (Access Key and Secret
    Key) are properly configured in the AWS CLI profile.
    - The AWS_PROFILE should be defined in the settings module.

    Returns:
        botocore.client.S3: An initialized AWS S3 client object.

    Raises:
        botocore.exceptions.NoCredentialsError: If S3 credentials are undefined.
    """
    if has_s3_credentials():
        session = boto3.Session(profile_name=settings.AWS_PROFILE)
        s3 = session.client("s3", region_name="us-east-1")
        return s3
    raise botocore.exceptions.NoCredentialsError("S3 credentials are undefined.")


def create_s3_resource():
    """
    Creates and returns an AWS S3 resource if valid credentials are available.

    Returns:
        boto3.resources.base.ServiceResource:
            An S3 resource if credentials are valid.

    Raises:
        botocore.exceptions.NoCredentialsError: If S3 credentials are undefined.
    """
    if has_s3_credentials():
        session = boto3.Session(profile_name=settings.AWS_PROFILE)
        s3 = session.resource("s3", region_name="us-east-1")
        return s3
    raise botocore.exceptions.NoCredentialsError("S3 credentials are undefined.")


def create_s3_control_client():
    """
    Create and return an S3 Control client.

    Returns:
        An S3 Control client if credentials are valid.

    Raises:
        botocore.exceptions.NoCredentialsError: If S3 credentials are undefined.

    """
    if has_s3_credentials():
        session = boto3.Session(profile_name=settings.AWS_PROFILE)
        s3 = session.client("s3control", region_name="us-east-1")
        return s3
    raise botocore.exceptions.NoCredentialsError("S3 credentials are undefined.")


class S3ObjectInfo(typing.NamedTuple):
    """
    Metadata about an object (file) stored in an S3 bucket.

    Attributes:
        size (int): Size of file in bytes.
        etag (str): HTTP entity tag.
    """
    size: int
    etag: str

    def match_path(self, path):
        """
        Check whether the contents of the object match a local file.

        Note that because S3 uses the MD5 algorithm, it is possible
        for someone to deliberately construct two different files that
        have the same ETag, and this function will incorrectly return
        True.

        Also note that the hash is dependent on the parameters
        (multipart_threshold, multipart_chunksize) used when the file
        was uploaded to S3, so it is also possible that this function
        will return False when in fact the two files are identical.

        Args:
            path (str): Filesystem path of the local file.

        Returns:
            bool: True if the local file and remote file contents are
            identical (barring MD5 collisions.)
        """
        if self.size != os.path.getsize(path):
            return False
        with open(path, 'rb') as fileobj:
            return self.etag == s3_file_etag(fileobj)


def s3_file_etag(fileobj, chunksize=(8 * 1024 * 1024)):
    """
    Calculate the ETag that S3 would use for a file.

    The ETag used by S3 is dependent on whether the file was uploaded
    as a single part or as multiple parts, and if multiple parts are
    used, depends on the chunk size.  The default behavior of boto3 is
    to use a chunk size of 8 MiB.

    Args:
        fileobj (io.BufferedIOBase): Readable binary file object.
        chunksize (int): Chunk size for multi-part uploads.

    Returns:
        str: Expected value of the ETag, if the given file were
        uploaded to S3.
    """
    # https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html#large-object-checksums
    meta_hash = hashlib.md5()
    part_hash = hashlib.md5()
    remaining = chunksize
    n_parts = 0
    while True:
        data = fileobj.read(min(remaining, 1024 * 1024))
        if not data:
            break
        part_hash.update(data)
        remaining -= len(data)
        if remaining == 0:
            meta_hash.update(part_hash.digest())
            part_hash = hashlib.md5()
            remaining = chunksize
            n_parts += 1
    if n_parts > 0 and remaining < chunksize:
        meta_hash.update(part_hash.digest())
        n_parts += 1

    # Quotation marks are part of the ETag value.
    if n_parts == 0:
        return '"{}"'.format(part_hash.hexdigest())
    else:
        return '"{}-{}"'.format(meta_hash.hexdigest(), n_parts)


def get_s3_object_info(s3, bucket_name, key):
    """
    Retrieve metadata of an object (file) stored in an S3 bucket.

    Args:
        s3 (boto3.client.S3): An initialized AWS S3 client object.
        bucket_name (str): Name of the bucket.
        key (str): Key of the object in the bucket.

    Returns:
        S3ObjectInfo: Metadata of the object.

    Raises:
        botocore.exceptions.ClientError: If the object does not exist
        or the client does not have permission to access it.

    Example:
        >>> get_s3_object_info(s3, "physionet-open", "mitdb/1.0.0/100.dat")
        S3ObjectInfo(size=1950000, etag='"4968ff1f99b15820d4a7a1d274d13d66"')
    """
    response = s3.head_object(Bucket=bucket_name, Key=key)
    return S3ObjectInfo(
        size=response['ContentLength'],
        etag=response['ETag'],
    )


def list_s3_subdir_object_info(s3, bucket_name, prefix):
    """
    Retrieve metadata of all files in a subdirectory of an S3 bucket.

    Args:
        s3 (boto3.client.S3): An initialized AWS S3 client object.
        bucket_name (str): Name of the bucket.
        prefix (str): Prefix of the directory within the bucket.

    Returns:
        files (dict): A dictionary mapping file paths (keys) to
        S3ObjectInfo.
        subdirs (list): A list of prefixes representing subdirectories
        of the given directory.

    Raises:
        botocore.exceptions.ClientError: If the bucket does not exist
        or the client does not have permission to access it.

    Example:
        >>> f, d = get_s3_object_info(s3, "physionet-open", "mitdb/1.0.0/")
        >>> f['mitdb/1.0.0/100.atr']
        S3ObjectInfo(size=4558, etag='"566dc5a685c634deba5a081b4ceec345"')
        >>> f['mitdb/1.0.0/100.dat']
        S3ObjectInfo(size=1950000, etag='"4968ff1f99b15820d4a7a1d274d13d66"')
        >>> d
        ['mitdb/1.0.0/mitdbdir/', 'mitdb/1.0.0/x_mitdb/']
    """
    pages = s3.get_paginator('list_objects_v2').paginate(
        Bucket=bucket_name,
        Prefix=prefix,
        Delimiter='/',
    )

    files = {}
    subdirs = []
    for page in pages:
        for file_data in page.get('Contents', []):
            files[file_data['Key']] = S3ObjectInfo(
                size=file_data['Size'],
                etag=file_data['ETag'],
            )
        subdirs += page.get('CommonPrefixes', [])

    return files, subdirs


def get_bucket_name(project):
    """
    Determine and return the S3 bucket name associated with
    a given project.

    This function calculates the S3 bucket name based on the
    project's slug and version.
    If the project has a specific access policy defined, the
    bucket name will be generated accordingly. For projects with
    an 'OPEN' access policy, the default bucket name is specified
    in settings.S3_OPEN_ACCESS_BUCKET. For other access
    policies ('RESTRICTED', 'CREDENTIALED', 'CONTRIBUTOR_REVIEW'),
    the default bucket name is specified in
    settings.S3_CONTROLLED_ACCESS_BUCKET.

    Args:
        project (project.models.Project): The project for which
        to determine the S3 bucket name.

    Returns:
        str: The S3 bucket name associated with the project.

    Note:
    - This function does not create or verify the existence of
    the actual S3 bucket; it only provides the calculated bucket
    name based on project attributes.
    """
    bucket_name = None

    if (project.georestricted
            and project.access_policy == AccessPolicy.OPEN
            and has_S3_geo_restricted_data_bucket_name()):
        bucket_name = settings.S3_OPEN_ACCESS_BUCKET_WITH_LOGIN
    elif project.access_policy == AccessPolicy.OPEN and has_S3_open_data_bucket_name():
        bucket_name = settings.S3_OPEN_ACCESS_BUCKET
    elif (
        project.access_policy != AccessPolicy.OPEN
        and has_S3_controlled_data_bucket_name()
    ):
        bucket_name = settings.S3_CONTROLLED_ACCESS_BUCKET
    return bucket_name


def get_all_prefixes(project):
    """
    Retrieve a list of all prefixes (directories) for objects within
    the S3 bucket associated with the given project.

    This function checks if the S3 bucket for the project exists,
    and if so, it initializes an S3 client, specifies the bucket name,
    and lists the common prefixes (directories) within the bucket.
    The retrieved prefixes are returned as a list.

    Args:
        project (project.models.Project): The project for which to
        retrieve all prefixes.

    Returns:
        list: A list of common prefixes (directories) within
        the S3 bucket.

    Note:
    - This function does not create or modify objects within the
    S3 bucket, only retrieves directory-like prefixes.
    - Make sure that AWS credentials (Access Key and Secret Key)
    are properly configured for this function to work.
    - The S3 bucket should exist and be accessible based on the
    project's configuration.
    """
    common_prefixes = []
    if check_s3_bucket_exists(project):
        # Initialize the S3 client
        s3 = create_s3_client()

        # Check if s3 is None
        if s3 is None:
            return

        # Specify the bucket name
        bucket_name = get_bucket_name(project)

        # List the prefixes (common prefixes or "directories")
        response = s3.list_objects_v2(Bucket=bucket_name, Delimiter="/")

        # Extract the prefixes
        common_prefixes = response.get("CommonPrefixes", [])
    return common_prefixes


def get_prefix_open_project(project):
    """
    Retrieve the prefix (directory) specific to an open project.

    This function checks if the project's access policy is 'OPEN'.
    If it is, the function constructsthe target prefix based on
    the project's slug and version, and then finds the matching
    prefix within the S3 bucket's list of prefixes (directories).

    Args:
        project (project.models.Project): The open project for which
        to retrieve the specific prefix.

    Returns:
        str or None: The matching prefix if the project is open;
        otherwise, None.

    Note:
    - This function is intended for open projects only; for other
    access policies, it returns None.
    - Ensure that the project's S3 bucket exists and is properly
    configured.
    """
    if project.access_policy != AccessPolicy.OPEN:
        return None
    else:
        target_prefix = project.slug + "/"
        matching_prefix = find_matching_prefix(get_all_prefixes(project), target_prefix)
    return matching_prefix


def find_matching_prefix(prefix_list, target_prefix):
    """
    Find and return the matching prefix within a list of prefixes
    for a given target prefix.

    This function iterates through a list of prefixes (commonly
    found in S3 bucket listings) and compares each prefix to
    the provided target prefix. If a match is found, the matching
    prefix is returned after stripping any trailing slashes ('/').

    Args:
        prefix_list (list): A list of prefixes to search through.
        target_prefix (str): The prefix to match against the list.

    Returns:
        str or None: The matching prefix without trailing slashes,
        or None if no match is found.
    """
    for prefix_info in prefix_list:
        prefix = prefix_info.get("Prefix", "")
        if prefix == target_prefix:
            return prefix.rstrip("/")
    return None


def check_s3_bucket_exists(project):
    """
    Check the existence of an S3 bucket associated with the
    given project.

    This function uses the provided project to determine the S3
    bucket's name. It then attempts to validate the existence of
    the bucket by sending a 'HEAD' request to AWS S3.
    If the bucket exists and is accessible, the function returns
    True; otherwise, it returns False.

    Args:
        project (project.models.Project): The project for which to
        check the S3 bucket's existence.

    Returns:
        bool: True if the S3 bucket exists and is accessible,
        False otherwise.

    Note:
    - Make sure that AWS credentials (Access Key and Secret Key)
    are properly configured for this function to work.
    - The S3 bucket should exist and be accessible based on the
    project's configuration.
    """
    s3 = create_s3_client()
    # Check if s3 is None
    if s3 is None:
        return
    bucket_name = get_bucket_name(project)
    try:
        s3.head_bucket(Bucket=bucket_name)
        return True
    except botocore.exceptions.ClientError:
        return False


def create_s3_bucket(s3, bucket_name):
    """
    Create a new Amazon S3 bucket with the specified name.

    This function uses the provided S3 client ('s3') to create
    a new S3 bucket with the given 'bucket_name'.

    Args:
        s3 (boto3.client.S3): An initialized AWS S3 client object.
        bucket_name (str): The desired name for the new S3 bucket.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the provided 's3' client to
    create the bucket.
    - Bucket names must be globally unique within AWS S3, so
    choose a unique name.
    """
    s3.create_bucket(Bucket=bucket_name)


def put_bucket_logging(s3, bucket_name, target_bucket, target_prefix):
    """
    Configures server access logging for an Amazon S3 bucket.

    Args:
        s3 (boto3.client): The Amazon S3 client.
        bucket_name (str): The name of the source bucket.
        target_bucket (str): The name of the bucket where log
        files will be stored.
        target_prefix (str): The prefix for log file names within the
        target bucket.

    Returns:
        None

    Note:
        This method utilizes the `put_bucket_logging` operation to enable
        server access logging for the specified source bucket, directing
        logs to the specified target bucket and prefix.

    Example:
        put_bucket_logging(s3_client, 'source_bucket', 'log_bucket', 'logs/')
    """
    logging_config = {
        "LoggingEnabled": {
            "TargetBucket": target_bucket,
            "TargetPrefix": target_prefix,
        },
    }

    # Enable bucket logging
    s3.put_bucket_logging(Bucket=bucket_name, BucketLoggingStatus=logging_config)


def send_files_to_s3(folder_path, s3_prefix, bucket_name, project):
    """
    Upload files from a local folder to an AWS S3 bucket with
    a specified prefix.

    This function walks through the files in the local
    'folder_path' and uploads each file to the specified AWS S3
    'bucket_name' under the 's3_prefix' directory. It uses an
    initialized AWS S3 client to perform the file uploads.

    Args:
        folder_path (str): The local folder containing the
        files to upload.
        s3_prefix (str): The prefix (directory) within the S3 bucket
        where files will be stored.
        bucket_name (str): The name of the AWS S3 bucket where
        files will be uploaded.

    Raises:
        ValueError: If AWS_PROFILE is undefined.

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key) are
    properly configured for the S3 client used in this function.
    """
    if not has_s3_credentials():
        raise ValueError("AWS_PROFILE is undefined. Please set it in your settings.")

    s3 = create_s3_client()
    for root, subdirs, files in os.walk(folder_path):
        subdirs.sort()
        files.sort()

        if root == folder_path:
            dir_prefix = s3_prefix
        else:
            dir_prefix = os.path.join(
                s3_prefix, os.path.relpath(root, folder_path), ''
            )
        existing_files, existing_subdirs = list_s3_subdir_object_info(
            s3, bucket_name, dir_prefix
        )

        for file_name in files:
            local_file_path = os.path.join(root, file_name)
            s3_key = os.path.join(
                s3_prefix, os.path.relpath(local_file_path, folder_path)
            )

            # Upload file if not already up-to-date
            send_file_to_s3(
                s3, bucket_name, s3_key, local_file_path,
                existing_files.get(s3_key)
            )

    # If project has a ZIP file, upload it as well
    if project.compressed_storage_size:
        zip_name = project.zip_name(legacy=False)
        zip_file_path = project.zip_name(full=True)
        if project.access_policy == AccessPolicy.OPEN:
            s3_key = os.path.join(f"{project.slug}/", zip_name)
        else:
            s3_key = os.path.join(f"{project.slug}/", zip_name)

        # Upload file if not already up-to-date
        try:
            existing_file = get_s3_object_info(s3, bucket_name, s3_key)
        except s3.exceptions.ClientError:
            existing_file = None
        send_file_to_s3(s3, bucket_name, s3_key, zip_file_path, existing_file)


def send_file_to_s3(s3, bucket_name, key, file_path, existing_file=None):
    """
    Upload a local file to an AWS S3 bucket.

    If the remote file already exists and matches the contents of the
    local file, the remote file is not modified.

    Args:
        s3 (boto3.client.S3): An initialized AWS S3 client object.
        bucket_name (str): Destination bucket name.
        key (str): Destination key within the bucket.
        file_path (str): Filesystem path of the local file.
        existing_file (S3ObjectInfo or None): Metadata of the existing
        object, if any.

    Returns:
        None
    """
    if existing_file is not None and existing_file.match_path(file_path):
        return
    s3.upload_file(
        Filename=file_path,
        Bucket=bucket_name,
        Key=key,
    )


def get_aws_accounts_for_access_point(access_point_name):
    """
    Retrieve AWS account IDs and user IDs associated with a
    specific access point.

    This function identifies AWS account IDs and user IDs
    associated with users who are authorized to access the
    specified access point.

    Args:
        access_point_name (str): The name of the access point
        for which to retrieve AWS accounts.

    Returns:
        list: A list of dictionaries, each containing 'aws_id'
        and 'aws_userid' keys for authorized users.

    Note:
    - This function assumes that AWS account IDs are 12-digit
    numerical values.
    """
    aws_accounts = []
    aws_id_pattern = r"\b\d{12}\b"

    # Retrieve the access point object by name
    try:
        access_point = AWSAccessPoint.objects.get(name=access_point_name)
    except AWSAccessPoint.DoesNotExist:
        return aws_accounts

    # Get the users associated with the access point
    users_with_cloud_info = access_point.users.filter(
        cloud_information__aws_verification_datetime__isnull=False
    )

    for user in users_with_cloud_info:
        aws_id = user.cloud_information.aws_id
        aws_userid = (
            user.cloud_information.aws_userid
            if user.cloud_information.aws_userid
            else None
        )
        if aws_id and re.search(aws_id_pattern, aws_id):
            aws_accounts.append({'aws_id': aws_id, 'aws_userid': aws_userid})

    return aws_accounts


def get_aws_accounts_for_dataset(dataset_name):
    """
    Retrieve AWS account IDs and user IDs associated with
    a given dataset's authorized users.

    This function identifies AWS account IDs and user IDs
    associated with users who are authorized to access the
    specified project.

    Args:
        dataset_name (str): The name of the dataset for which
        to retrieve AWS IDs.

    Returns:
        list: A list of dictionaries, each containing 'aws_id'
        and 'aws_userid' keys for authorized users.

    Note:
    - This function assumes that AWS account IDs are 12-digit
    numerical values.
    """
    aws_accounts = []
    published_projects = PublishedProject.objects.all()
    users_with_cloud_info = User.objects.filter(
        cloud_information__aws_verification_datetime__isnull=False
    )
    aws_id_pattern = r"\b\d{12}\b"

    for project in published_projects:
        project_name = project.slug + "-" + project.version
        if project_name == dataset_name:
            for user in users_with_cloud_info:
                if can_view_project_files(project, user):
                    aws_id = user.cloud_information.aws_id
                    if user.cloud_information.aws_userid:
                        aws_userid = user.cloud_information.aws_userid
                    else:
                        aws_userid = None
                    if aws_id and re.search(aws_id_pattern, aws_id):
                        aws_accounts.append({'aws_id': aws_id, 'aws_userid': aws_userid})
            break  # Stop iterating once the dataset is found

    return aws_accounts


def create_open_bucket_policy(bucket_name):
    """
    Generate an initial AWS S3 bucket policy that restricts
    access.

    This function creates a default AWS S3 bucket policy with
    restricted access. The policy denies list and get actions for
    all principals except for a specified AWS account, which is
    allowed to access the bucket.

    Args:
        bucket_name (str): The name of the AWS S3 bucket for
        which to generate the initial policy.
        aws_ids (list): A list of AWS account IDs and user names
        allowed to access the bucket.
        public (bool): True if the bucket should be made public,
        False otherwise.

    Returns:
        str: A JSON-formatted string representing the initial
        bucket policy.

    Note:
    - This initial policy serves as a baseline and can be customized
    further to meet specific access requirements for the bucket.
    - If 'public' is True, the policy allows public access to the
    bucket. If 'public' is False, it restricts access to the specified
    AWS accounts and users.
    """
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowReadOnlyAccess",
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*",
                ],
            }
        ],
    }

    # Convert the policy from JSON dict to string
    bucket_policy_str = json.dumps(bucket_policy)

    return bucket_policy_str


def set_open_bucket_policy(bucket_name, bucket_policy):
    """
    Apply a custom AWS S3 bucket policy to a specified bucket.

    This function utilizes an AWS S3 client to set the custom
    'bucket_policy' for the specified 'bucket_name', effectively
    configuring access controls and permissions for objects
    within the bucket.

    Args:
        bucket_name (str): The name of the AWS S3 bucket for
        which to set the custom policy.
        bucket_policy (str): A JSON-formatted string representing
        the custom bucket policy.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in
    this function.
    - The 'bucket_policy' should be a valid JSON string adhering
    to AWS S3 policy syntax.
    """
    s3 = create_s3_client()
    if s3 is None:
        return
    s3.put_bucket_policy(Bucket=bucket_name, Policy=bucket_policy)


def put_public_access_block(client, bucket_name, configuration):
    """
    Configure Amazon S3 Block Public Access settings
    for a bucket.

    Amazon S3 Block Public Access provides settings for buckets
    to control and manage public access to Amazon S3 resources.
    By default, new buckets do not allow public access.
    This function sets the specified configuration for the given
    bucket to allow or restrict public access.

    Args:
        client (boto3.client.S3): An initialized AWS S3
        client object.
        bucket_name (str): The name of the S3 bucket
        to configure.
        configuration (bool): The PublicAccessBlock configuration
        to be applied to the S3 bucket.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the provided 'client'.
    """
    client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": configuration,
            "IgnorePublicAcls": configuration,
            "BlockPublicPolicy": configuration,
            "RestrictPublicBuckets": configuration,
        },
    )


def update_open_bucket_policy(project, bucket_name):
    """
    Update the AWS S3 bucket's access policy based on the
    project's access policy.

    This function manages the AWS S3 bucket's access policy
    for the specified 'bucket_name' based on the 'project'
    object's access policy. It performs the following actions:
    - For projects with an 'OPEN' access policy, it allows public
    access by removing any public access blocks and applying
    a policy allowing public reads.

    Args:
        project (project.models.Project): The project for which
        to update the bucket policy.
        bucket_name (str): The name of the AWS S3 bucket
        associated with the project.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in this function.
    """
    bucket_policy = ""
    if project.access_policy == AccessPolicy.OPEN:
        s3 = create_s3_client()
        if s3 is None:
            return
        put_public_access_block(s3, bucket_name, False)
        bucket_policy = create_open_bucket_policy(bucket_name)

    if bucket_policy not in [None, ""]:
        set_open_bucket_policy(bucket_name, bucket_policy)


def create_controlled_bucket_policy(bucket_name):
    """
    Create a controlled bucket policy for an S3 bucket.

    This function generates a controlled bucket policy that restricts
    access to specific actions and resources within the given S3
    bucket.

    Args:
        bucket_name (str): The name of the S3 bucket for which
        to create the policy.

    Returns:
        str: A JSON string representing the controlled bucket policy.

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in this function.
    """
    controlled_bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "DelegateToAccessPoints",
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetBucket*", "s3:GetObject*", "s3:List*"],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*",
                ],
                "Condition": {
                    "StringEquals": {
                        "s3:DataAccessPointAccount": settings.AWS_ACCOUNT_ID
                    }
                },
            }
        ],
    }

    # Convert the policy from JSON dict to string
    controlled_bucket_policy_str = json.dumps(controlled_bucket_policy)

    return controlled_bucket_policy_str


def get_latest_access_point(project):
    """
    This function retrieves the name of the access point associated
    with the specified project. It handles scenarios where there are
    multiple access points, only one access point, or none.

    Args:
        project (object): The project object containing AWS and
        version information.

    Returns:
        str: The name of the access point.

    Note:
    - Ensure that the project object contains valid AWS and
    version information.

    """
    # Generate the base name for the access point from the project slug and version
    base_name = f"{project.slug}-v{project.version.replace('.', '-')}"

    # Pattern to extract the numeric version part from names
    pattern = re.compile(r"(\d+)$")

    # Filter access points starting with the base name and ending with a version number
    access_points = AWSAccessPoint.objects.filter(name__startswith=base_name)

    # Check if any access points exist
    if access_points.exists():
        # Get the highest version number
        latest = access_points.order_by("-name").first().name
        version = int(pattern.search(latest).group(1))
        version = str(version).zfill(2)  # Pad the version number with zeros
    else:
        return None

    data_access_point_name = (
        f"{project.slug}-v{project.version.replace('.', '-')}-{version}"
    )
    return data_access_point_name


def get_next_access_point_version(project):
    """
    Generate the name of the next access point version for a
    given project.

    This function constructs the name version for the specified
    project by incrementing the latest version number.

    Args:
        project (object): The project object containing AWS and
        version information.

    Returns:
        str: The name of the next access point version.

    Note:
    - Ensure that the project object contains valid AWS and
    version information.
    """
    # Call the existing function to get the latest access point name
    current_access_point_name = get_latest_access_point(project)
    if current_access_point_name is None:
        next_version = "01"
    else:
        # Use a regular expression to extract the version number from the access point name
        pattern = re.compile(r"(\d+)$")
        match = pattern.search(current_access_point_name)

        if match:
            # Extract the current version number and increment it
            current_version = int(match.group(1))
            next_version = str(current_version + 1).zfill(
                2
            )  # Increment and pad the version number
    # Construct the next access point name using the project details and the new version number
    next_access_point_name = (
        f"{project.slug}-v{project.version.replace('.', '-')}-{next_version}"
    )
    return next_access_point_name


def create_data_access_point_policy(
    access_point_name, project_slug, project_version, aws_accounts
):
    """
    Create a data access point policy for an S3 access point.

    This function generates a data access point policy that grants
    specific AWS users access to project data stored in an S3 bucket.

    Args:
        access_point_name (str): The name of the access point.
        project_slug (str): The slug of the project.
        project_version (str): The version of the project.
        aws_accounts (list): A list of dictionaries containing 'aws_id' and 'aws_userid'.

    Returns:
        str: A JSON string representing the data access point policy.
    """
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "DenyListBucketOutsideProject",
                "Effect": "Deny",
                "Principal": "*",
                "Action": ["s3:ListBucket"],
                "Resource": f"arn:aws:s3:us-east-1:{settings.AWS_ACCOUNT_ID}:accesspoint/{access_point_name}",
                "Condition": {
                    "StringNotLike": {
                        "s3:prefix": f"{project_slug}/{project_version}/*"
                    }
                }
            },
            {
                "Sid": "AllowGetObject",
                "Effect": "Allow",
                "Principal": {
                    "AWS": [account['aws_userid'] for account in aws_accounts]
                },
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    (
                        f"arn:aws:s3:us-east-1:{settings.AWS_ACCOUNT_ID}:accesspoint/"
                        f"{access_point_name}/object/{project_slug}/{project_version}/*"
                    ),
                    (
                        f"arn:aws:s3:us-east-1:{settings.AWS_ACCOUNT_ID}:accesspoint/"
                        f"{access_point_name}"
                    )
                ]
            }
        ]
    }
    policy_str = json.dumps(policy)
    return policy_str


def extract_invalid_userid(client_error):
    """
    Extract the invalid AWS user ID from the ClientError detail.

    Args:
        client_error (ClientError): The boto3 ClientError exception

    Returns:
        str or None: The invalid user ID if found, None otherwise
    """
    try:
        detail = client_error.response['Error']['Detail']
        import re
        match = re.search(r'"AWS"\s*:\s*"([^"]+)"', detail)
        if match:
            return match.group(1)
    except (KeyError, AttributeError):
        pass
    return None


def mark_user_unverified(invalid_userid):
    """
    Mark a user as unverified based on their AWS user ID.

    Args:
        invalid_userid (str): The AWS user ID that's invalid

    Returns:
        bool: True if user was found and marked as unverified, False otherwise
    """
    try:
        cloud_info = CloudInformation.objects.get(aws_userid=invalid_userid)
        cloud_info.aws_verification_datetime = None
        cloud_info.save()
        return True
    except CloudInformation.DoesNotExist:
        return False


def set_data_access_point_policy(data_access_point_name, data_access_point_policy):
    """
    Apply a custom policy to an AWS S3 data access point.

    Args:
        data_access_point_name (str): The name of the data access point.
        data_access_point_policy (str): The policy to be applied, in JSON string format.

    Returns:
        bool: True if the policy was successfully applied, False otherwise.
    """
    s3_control = create_s3_control_client()

    try:
        s3_control.put_access_point_policy(
            AccountId=settings.AWS_ACCOUNT_ID,
            Name=data_access_point_name,
            Policy=data_access_point_policy,
        )
        return True
    except ClientError:
        raise


def add_user_to_access_point_policy(project, user):
    """
    Add a user to an existing access point or create a new one if no access point has capacity.

    Args:
        project (PublishedProject): The project associated with the access points.
        user_aws_id (str): The AWS ID of the user to be added.

    Returns:
        dict: A dictionary containing the access point information where the user was added.
        None: If the process failed.
    """
    cloud_info = user.cloud_information

    aws_account = {
        'aws_userid': cloud_info.aws_userid
    }
    # Check if there is an access point with capacity
    access_point_data = get_access_point_with_capacity(project)
    if access_point_data:
        # If an access point with capacity exists, add the user
        access_point = access_point_data['access_point']
        data_access_point_name = access_point_data['name']
        # Get the existing AWS IDs and include the new user
        existing_users = get_aws_accounts_for_access_point(data_access_point_name)
        all_users = existing_users + [aws_account]
        # Use insert_access_point_policy to update policy and associate the user
        insert_access_point_policy(
            access_point,
            data_access_point_name,
            project,
            all_users,
        )

        return {
            "access_point": access_point,
            "name": data_access_point_name,
            "users": all_users,
        }

    else:
        next_access_point_name = get_next_access_point_version(project)
        bucket_name = get_bucket_name(project)
        # Create the new access point
        new_access_point = create_s3_access_point(
            project,
            next_access_point_name,
            bucket_name,
            settings.AWS_ACCOUNT_ID,
        )
        if not new_access_point:
            return None

        # Use insert_access_point_policy for the new access point
        insert_access_point_policy(
            new_access_point,
            next_access_point_name,
            project,
            [aws_account],
        )
        return {
            "access_point": new_access_point,
            "name": next_access_point_name,
            "users": [aws_account],
        }


def get_access_point_with_capacity(project):
    """
    Finds an access point associated with the project that can add a new user.

    Args:
        project (PublishedProject): The project to check.

    Returns:
        dict: A dictionary containing:
            - 'access_point': The access point object
            - 'name': The name of the access point
            - 'users': A list of associated usernames
        None: If no access point meets the criteria.
    """
    try:
        # Retrieve the AWS instance associated with the project
        aws_instance = AWS.objects.get(project=project)
        # Retrieve all access points associated with the AWS instance
        access_points = AWSAccessPoint.objects.filter(aws=aws_instance)
        for access_point in access_points:
            # Count the number of users associated with the access point
            user_count = access_point.users.count()

            if user_count < MAX_PRINCIPALS_PER_AP_POLICY:
                # Get the list of usernames associated with the access point
                users = list(access_point.users.values_list('username', flat=True))
                return {
                    'access_point': access_point,
                    'name': access_point.name,
                    'users': users,
                }

        # Return None if no access point meets the criteria
        return None

    except AWS.DoesNotExist:
        return None


def insert_access_point_policy(access_point, data_access_point_name, project, subset_aws_ids):
    """
    Set policies and associate users for an access point.
    Handles invalid users by retrying with them removed from the list.
    """
    # Work with a copy to avoid modifying the original list
    working_aws_ids = subset_aws_ids.copy()
    for attempt in range(MAX_RETRIES):
        if not working_aws_ids:
            # No valid users left
            return True

        access_point_policy = create_data_access_point_policy(
            data_access_point_name, project.slug, project.version, working_aws_ids
        )
        try:
            valid_ap_policy = set_data_access_point_policy(
                data_access_point_name, access_point_policy
            )
            if valid_ap_policy:
                associate_aws_users_with_data_access_point(access_point, working_aws_ids)
                return True
            else:
                return False

        except ClientError as e:
            if e.response['Error']['Code'] == 'MalformedPolicy':
                invalid_userid = extract_invalid_userid(e)
                if invalid_userid:
                    # Mark user as unverified
                    mark_user_unverified(invalid_userid)

                    # Remove the invalid user
                    working_aws_ids = [
                        user for user in working_aws_ids
                        if user['aws_userid'] != invalid_userid
                    ]
                    # Continue to next attempt with reduced user list
                    continue
                else:
                    return False
            else:
                raise

    # Exceeded max retries
    return False


def initialize_access_points(project):
    project_name = project.slug + "-" + project.version
    aws_ids = get_aws_accounts_for_dataset(project_name)
    number_of_access_points_needed = ceil(len(aws_ids) / MAX_PRINCIPALS_PER_AP_POLICY)
    bucket_name = get_bucket_name(project)
    for i in range(number_of_access_points_needed):
        data_access_point_version = str(i + 1).zfill(2)
        data_access_point_name = (
            f"{project.slug}-v{project.version.replace('.', '-')}-"
            f"{data_access_point_version}"
        )

        subset_aws_ids = aws_ids[
            i * MAX_PRINCIPALS_PER_AP_POLICY: (i + 1) * MAX_PRINCIPALS_PER_AP_POLICY
        ]
        access_point = AWSAccessPoint.objects.filter(
            name=data_access_point_name, aws__project=project
        ).first()
        if not access_point:
            access_point = create_s3_access_point(
                project,
                data_access_point_name,
                bucket_name,
                settings.AWS_ACCOUNT_ID,
            )

        # Set policies and associate users for the newly created access point
        insert_access_point_policy(access_point, data_access_point_name, project, subset_aws_ids)


def associate_aws_users_with_data_access_point(access_point, aws_accounts):
    """
    Associates a list of `aws_accounts` with the `AWSAccessPoint`.

    Args:
        access_point (AWSAccessPoint): The access point to which
        the accounts will be associated.
        aws_accounts (list): List of dictionaries containing `aws_userid`.
    """
    # Iterate through the AWS accounts
    for aws_account in aws_accounts:
        aws_userid = aws_account.get("aws_userid")

        # Fetch the user related to the aws_userid
        try:
            cloud_info = CloudInformation.objects.get(aws_userid=aws_userid)
        except CloudInformation.DoesNotExist:
            continue

        user = cloud_info.user

        # Get the AWS instance associated with the access point
        aws_instance = access_point.aws

        # Check if the user is already associated with the access_point
        existing_association = AWSAccessPointUser.objects.filter(
            access_point=access_point,
            user=user,
            aws=aws_instance
        ).first()

        if not existing_association:
            # Create the association with the required fields
            AWSAccessPointUser.objects.create(
                access_point=access_point,
                user=user,
                aws=aws_instance
            )


def create_s3_access_point(project, access_point_name, bucket_name, account_id):
    """
    Create an S3 access point for a specified bucket and project.

    This function creates an S3 access point for the given bucket
    and project, applying necessary public access block configurations.

    Args:
        project (object): The project object containing AWS and version information.
        access_point_name (str): The name of the access point.
        bucket_name (str): The name of the S3 bucket.
        account_id (str): The AWS account ID.

    Returns:
        object: The created access point object, or None if an error occurred.

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in this function.
    - Ensure that the bucket name and account ID are valid.
    """
    s3 = create_s3_control_client()

    s3.create_access_point(
        AccountId=account_id,
        Bucket=bucket_name,
        Name=access_point_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    # Create and save AccessPoint model instance
    access_point, created = AWSAccessPoint.objects.get_or_create(
        aws=project.aws, name=access_point_name
    )
    return access_point


def upload_project_to_S3(project):
    """
        Upload project files to an S3 bucket and configure access policies.

    This function manages the upload of project files to a specified S3 bucket
    and configures the necessary access policies based on the project's access policy.

    Args:
        project (object): The project object containing AWS and version information.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in this function.
    - Ensure that the project object contains valid AWS and version information.
    """
    bucket_name = get_bucket_name(project)
    s3 = create_s3_client()
    if s3 is None or bucket_name is None:
        return

    bucket_created = False

    try:
        create_s3_bucket(s3, bucket_name)
        bucket_created = True
    except s3.exceptions.BucketAlreadyExists:
        raise Exception(f"A bucket named {bucket_name} already exists.")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        bucket_created = False

    # Set the bucket policy only if the bucket was newly created
    # and has controlled access
    if bucket_created and project.access_policy != AccessPolicy.OPEN or project.georestricted:
        controlled_policy = create_controlled_bucket_policy(bucket_name)
        s3.put_bucket_policy(Bucket=bucket_name, Policy=controlled_policy)

    put_bucket_logging(
        s3, bucket_name, settings.S3_SERVER_ACCESS_LOG_BUCKET, bucket_name + "/logs/"
    )
    folder_path = project.file_root()
    s3_prefix = f"{project.slug}/{project.version}/"
    send_files_to_s3(folder_path, s3_prefix, bucket_name, project)
    if project.access_policy == AccessPolicy.OPEN and not project.georestricted:
        update_open_bucket_policy(project, bucket_name)
    else:
        initialize_access_points(project)


def upload_list_of_projects(projects):
    """
    Bulk upload a list of projects to AWS S3.

    This function iterates through the provided list of
    'projects' and uploads each project's files
    to an AWS S3 bucket. It delegates the file upload process
    to the 'upload_project_to_S3' function.

    Args:
        projects (list of project.models.Project): A list of
        projects to upload to AWS S3.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for
      the S3 client used in the 'upload_project_to_S3'
      function.
    """
    for project in projects:
        upload_project_to_S3(project)


def upload_all_projects():
    """
    Bulk upload all published projects to AWS S3.

    This function retrieves all published projects from the
    database and uploads the files associated with each project
    to an AWS S3 bucket. It leverages the 'upload_project_to_S3'
    function for the file upload process.

    Args:
        None

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in the
    'upload_project_to_S3' function.
    """
    published_projects = PublishedProject.objects.all()
    for project in published_projects:
        upload_project_to_S3(project)


def create_s3_server_access_log_bucket():
    """
    Create the bucket for server access logs.

    This creates the bucket designated by S3_SERVER_ACCESS_LOG_BUCKET,
    and allows it to be used to deposit S3 server access logs.  Only
    buckets owned by the AWS_ACCOUNT_ID account will be allowed to
    store logs in this bucket.

    If the bucket already exists, an exception will be raised.
    """
    s3 = create_s3_client()

    bucket_name = settings.S3_SERVER_ACCESS_LOG_BUCKET
    source_accounts = [settings.AWS_ACCOUNT_ID]

    s3.create_bucket(Bucket=bucket_name)

    put_public_access_block(s3, bucket_name, True)

    s3.put_bucket_policy(
        Bucket=bucket_name,
        Policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "logging.s3.amazonaws.com",
                        },
                        "Action": [
                            "s3:PutObject",
                        ],
                        "Resource": f"arn:aws:s3:::{bucket_name}/*",
                        "Condition": {
                            "ArnLike": {
                                "aws:SourceArn": "arn:aws:s3:::*",
                            },
                            "StringEquals": {
                                "aws:SourceAccount": source_accounts,
                            },
                        },
                    },
                ],
            }
        ),
    )


def delete_project_files_from_s3(project):
    """
    Delete all files under the project's prefix from its S3 bucket.

    Args:
        project (PublishedProject): The project whose files will be deleted.
    """
    if not check_s3_bucket_exists(project):
        return
    s3 = create_s3_resource()
    bucket_name = get_bucket_name(project)
    prefix = f"{project.slug}/{project.version}/"
    bucket = s3.Bucket(bucket_name)
    bucket.objects.filter(Prefix=prefix).delete()

    # Delete zip file if it was uploaded
    if project.aws.sent_zip:
        zip_key = os.path.join(f"{project.slug}/", project.zip_name(legacy=False))
        bucket.Object(zip_key).delete()

    if project.aws.is_private:
        delete_project_access_points(project)
    else:
        project.aws.delete()


def delete_project_access_points(project):
    """
    Delete all S3 access points associated with a project and remove
    the corresponding AWS records from the database.

    Args:
        project (PublishedProject): The project whose access points
        will be deleted.
    """
    s3control = create_s3_control_client()

    for ap in project.aws.access_points.all():
        s3control.delete_access_point(
            AccountId=settings.AWS_ACCOUNT_ID,
            Name=ap.name
        )

    # Deletes AWS, AWSAccessPoint, and AWSAccessPointUser
    # from our database as well via CASCADE
    project.aws.delete()
