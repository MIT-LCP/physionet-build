import boto3
import botocore
import re
import os
import json
from django.conf import settings
from project.models import PublishedProject, AccessPolicy, AWS
from user.models import User
from project.authorization.access import can_view_project_files


# Manage AWS buckets and objects
def has_S3_open_data_bucket_name():
    """
    Check if AWS credentials (AWS_PROFILE) have been set in
    the project's settings.

    Returns:
        bool: True if AWS_PROFILE is set, False otherwise.
    """
    return bool(settings.S3_OPEN_ACCESS_BUCKET)


def has_s3_credentials():
    """
    Check if AWS credentials (AWS_PROFILE) have been set in
    the project's settings.

    Returns:
        bool: True if AWS_PROFILE is set, False otherwise.
    """
    return all([
        settings.AWS_PROFILE,
        settings.AWS_ACCOUNT_ID,
        settings.S3_OPEN_ACCESS_BUCKET,
        settings.S3_SERVER_ACCESS_LOG_BUCKET,
    ])


def files_sent_to_S3(project):
    """
    Get information about project files sent to Amazon S3
    for a project.

    Tries to access the AWS instance associated with the
    project to retrieve sent file information.
    Returns the information or None if it's not available.
    """
    try:
        aws_instance = project.aws
        sent_files_info = aws_instance.sent_files
    except AWS.DoesNotExist:
        sent_files_info = None
    return sent_files_info


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
        session = boto3.Session(
            profile_name=settings.AWS_PROFILE
        )
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
        session = boto3.Session(
            profile_name=settings.AWS_PROFILE
        )
        s3 = session.resource("s3", region_name="us-east-1")
        return s3
    raise botocore.exceptions.NoCredentialsError("S3 credentials are undefined.")


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
    the bucket name is constructed using the project's slug and version.

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

    if project.access_policy == AccessPolicy.OPEN and has_S3_open_data_bucket_name():
        bucket_name = settings.S3_OPEN_ACCESS_BUCKET
    else:
        bucket_name = project.slug
    return bucket_name


def get_all_prefixes(project):
    """
    Retrieve a list of all prefixes (directories) for objects within
    the S3 bucket associated with the given project.

    This function checks if the S3 bucket for the project exists,
    and if so, it initializes an S3 client,specifies the bucket name,
    and lists the common prefixes (directories) within the bucket.
    The retrievedprefixes are returned as a list.

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
    prefixwithin the S3 bucket's list of prefixes (directories).

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
        'LoggingEnabled': {
            'TargetBucket': target_bucket,
            'TargetPrefix': target_prefix,
        },
    }

    # Enable bucket logging
    s3.put_bucket_logging(
        Bucket=bucket_name,
        BucketLoggingStatus=logging_config
    )


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
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            local_file_path = os.path.join(root, file_name)
            s3_key = os.path.join(
                s3_prefix, os.path.relpath(local_file_path, folder_path)
            )
            s3.upload_file(
                Filename=local_file_path,
                Bucket=bucket_name,
                Key=s3_key,
            )

    # If project has a ZIP file, upload it as well
    if project.compressed_storage_size:
        zip_name = project.zip_name(legacy=False)
        zip_file_path = project.zip_name(full=True)
        if project.access_policy == AccessPolicy.OPEN:
            s3_key = os.path.join(f"{project.slug}/", zip_name)
        else:
            s3_key = zip_name

        s3.upload_file(
            Filename=zip_file_path,
            Bucket=bucket_name,
            Key=s3_key,
        )


def get_aws_accounts_for_dataset(dataset_name):
    """
    Retrieve AWS account IDs associated with a given
    dataset's authorized users.

    This function identifies AWS account IDs associated with
    users who are authorized to access the specified project.
    It searches for AWS account IDs among users with cloud
    information and permissions to view project files.

    Args:
        dataset_name (str): The name of the dataset for which
        to retrieve AWS account IDs.

    Returns:
        list: A list of AWS account IDs associated with authorized
        users of the dataset.

    Note:
    - This function assumes that AWS account IDs are 12-digit
    numerical values.
    - Users with the appropriate permissions and AWS account IDs
    are included in the result list.
    """
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


def create_bucket_policy(bucket_name, aws_ids, public):
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
    user = None
    principal_value = (
        "*"
        if public
        else {
            "AWS": [
                f"arn:aws:iam::{aws_id}:root"
                if user is None or user == ""
                else f"arn:aws:iam::{aws_id}:user/{user}"
                for aws_id in aws_ids
            ]
        }
    )

    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowReadOnlyAccess",
                "Effect": "Allow",
                "Principal": principal_value,
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*",
                ]
            }
        ]
    }

    # Convert the policy from JSON dict to string
    bucket_policy_str = json.dumps(bucket_policy)

    return bucket_policy_str


def set_bucket_policy(bucket_name, bucket_policy):
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
    # Check if s3 is None
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


def update_bucket_policy(project, bucket_name):
    """
    Update the AWS S3 bucket's access policy based on the
    project's access policy.

    This function manages the AWS S3 bucket's access policy
    for the specified 'bucket_name' based on the 'project'
    object's access policy. It performs the following actions:
    - For projects with an 'OPEN' access policy, it allows public
    access by removing any public access blocks and applying
    a policy allowing public reads.
    - For projects with other access policies (e.g., 'CREDENTIALED',
    'RESTRICTED', 'CONTRIBUTOR_REVIEW'), it sets a policy
    that limits access to specific AWS accounts belonging to
    users authorized to access the specified project.

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
    project_name = project.slug + "-" + project.version
    aws_ids = get_aws_accounts_for_dataset(project_name)
    if project.access_policy == AccessPolicy.OPEN:
        s3 = create_s3_client()
        if s3 is None:
            return
        put_public_access_block(s3, bucket_name, False)
        bucket_policy = create_bucket_policy(bucket_name, aws_ids, True)
    elif (
        project.access_policy == AccessPolicy.CREDENTIALED
        or project.access_policy == AccessPolicy.RESTRICTED
        or project.access_policy == AccessPolicy.CONTRIBUTOR_REVIEW
    ):
        if aws_ids != []:
            bucket_policy = create_bucket_policy(bucket_name, aws_ids, False)

    if bucket_policy not in [None, ""]:
        set_bucket_policy(bucket_name, bucket_policy)


def upload_project_to_S3(project):
    """
    Upload project-related files to an AWS S3 bucket
    associated with the project.

    This function orchestrates the process of uploading project
    files to an AWS S3 bucket.
    It performs the following steps:
    1. Creates the S3 bucket if it doesn't exist.
    2. Uploads project files from the local directory to the S3 bucket.
    3. Updates the bucket's access policy to align with the
    project's requirements.

    Args:
        project (project.models.Project): The project for which
        to upload files to S3.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in
    this function.
    - The 'project_name' variable is created by concatenating
    the project's slug and version.
    - The 's3_prefix' is set only for projects with an 'OPEN'
    access policy, providing an optional prefix within the
    S3 bucket.
    """
    bucket_name = get_bucket_name(project)
    # create bucket if it does not exist
    s3 = create_s3_client()
    if s3 is None or bucket_name is None:
        return

    try:
        create_s3_bucket(s3, bucket_name)
    except s3.exceptions.BucketAlreadyExists:
        raise Exception(f"A bucket named {bucket_name} already exists.")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    put_bucket_logging(
        s3, bucket_name, settings.S3_SERVER_ACCESS_LOG_BUCKET, bucket_name + "/logs/"
    )
    # upload files to bucket
    folder_path = project.file_root()
    # set the prefix only for the projects
    # in the open data bucket
    if project.access_policy == AccessPolicy.OPEN:
        s3_prefix = f"{project.slug}/{project.version}/"
    else:
        s3_prefix = f"{project.version}/"
    send_files_to_s3(folder_path, s3_prefix, bucket_name, project)
    # update bucket's policy for projects
    update_bucket_policy(project, bucket_name)


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

    # Policy for logging - see:
    # https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-server-access-logging.html
    s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps({
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
    }))
