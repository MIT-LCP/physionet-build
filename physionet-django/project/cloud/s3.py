import boto3
import botocore
import re
import os
import json
from django.conf import settings
from project.models import PublishedProject, AccessPolicy, AccessPoint, AccessPointUser
from user.models import User
from project.authorization.access import can_view_project_files
from botocore.exceptions import ClientError
from math import ceil


# Manage AWS buckets and objects
def has_S3_open_data_bucket_name():
    """
    Check if the S3_OPEN_ACCESS_BUCKET setting has a value set in the project's settings.

    This method verifies whether an open data bucket name has been specified for S3 storage.

    Returns:
        bool: Returns True if the S3_OPEN_ACCESS_BUCKET setting is set (i.e., truthy), False otherwise.
    """
    return bool(settings.S3_OPEN_ACCESS_BUCKET)


def has_S3_controlled_data_bucket_name():
    """
    Check if the S3_CONTROLLED_ACCESS_BUCKET setting has a value set in the project's settings.

    This method verifies whether a controlled-access data bucket name has been specified for S3 storage.

    Returns:
        bool: Returns True if the S3_CONTROLLED_ACCESS_BUCKET setting is set, False otherwise.
    """
    return bool(settings.S3_CONTROLLED_ACCESS_BUCKET)


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
        ]
    )


def files_sent_to_S3(project):
    from project.models import AWS

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

    if project.access_policy == AccessPolicy.OPEN and has_S3_open_data_bucket_name():
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
            s3_key = os.path.join(f"{project.slug}/", zip_name)

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
                        f"s3:DataAccessPointAccount": "{settings.AWS_ACCOUNT_ID}"
                    }
                },
            }
        ],
    }

    # Convert the policy from JSON dict to string
    controlled_bucket_policy_str = json.dumps(controlled_bucket_policy)

    return controlled_bucket_policy_str


def get_access_point_name_for_user_and_project(aws_id, project_slug, project_version):
    """
    Retrieve the access point name associated with a specific user
    and project.

    This function fetches the access point name linked to a given
    user and project, based on the user's AWS ID and the project's
    slug and version.

    Args:
        aws_id (str): The AWS ID of the user.
        project_slug (str): The slug of the project.
        project_version (str): The version of the project.

    Returns:
        str: The name of the access point or an error message if
        the user or project is not found.

    Note:
    - Ensure that the user and project exist in the database.
    """
    try:
        # Retrieve the user by AWS ID
        user = AccessPointUser.objects.get(aws_id=aws_id)
    except AccessPointUser.DoesNotExist:
        return "No user found with that AWS ID"

    try:
        # Retrieve the project based on slug and version
        project = PublishedProject.objects.get(
            slug=project_slug, version=project_version
        )
    except PublishedProject.DoesNotExist:
        return "Project not found"

    # Retrieve the access point linked to this user and specific project
    access_point = AccessPoint.objects.filter(users=user, aws__project=project).first()

    if access_point:
        return access_point.name
    else:
        return "No access point found for this user with the specified project details"


def get_access_point_name(project):
    """
    Get the name of the access point for a given project.

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
    access_points = project.aws.access_points.all()

    if access_points is None:
        print("No access points found for project.")
        access_point_name = f"{project.slug}-v{project.version.replace('.', '-')}-01"

    elif access_points.count() == 1:
        access_point_name = project.aws.access_points.first().name
        print("Only one access point found for project: ", access_point_name)

    else:
        access_point_name = get_latest_access_point(project)

    return access_point_name


def get_latest_access_point(project):
    """
    Get the name of the access point for a given project.

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
    access_points = AccessPoint.objects.filter(name__startswith=base_name)

    # Check if any access points exist
    if access_points.exists():
        # Get the highest version number
        latest = access_points.order_by("-name").first().name
        version = int(pattern.search(latest).group(1))
        version = str(version).zfill(2)  # Pad the version number with zeros
    else:
        # If no access points exist, start numbering from '01'
        version = "01"

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

    # Use a regular expression to extract the version number from the access point name
    pattern = re.compile(r"(\d+)$")
    match = pattern.search(current_access_point_name)

    if match:
        # Extract the current version number and increment it
        current_version = int(match.group(1))
        next_version = str(current_version + 1).zfill(
            2
        )  # Increment and pad the version number
    else:
        # If no version number is found, start from '01'
        next_version = "01"

    # Construct the next access point name using the project details and the new version number
    next_access_point_name = (
        f"{project.slug}-v{project.version.replace('.', '-')}-{next_version}"
    )
    return next_access_point_name


def create_data_access_point_policy(
    access_point_name, project_slug, project_version, aws_ids
):
    """
    Create a data access point policy for an S3 access point.

    This function generates a data access point policy that grants
    specific AWS users access to project data stored in an S3
    bucket.

    Args:
        access_point_name (str): The name of the access point.
        project_slug (str): The slug of the project.
        project_version (str): The version of the project.
        aws_ids (list): A list of AWS IDs to be included in the policy.

    Returns:
        str: A JSON string representing the data access point policy.

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in this function.
    """
    user = None
    principal_value = {
        "AWS": [
            f"arn:aws:iam::{aws_id}:root"
            if user is None or user == ""
            else f"arn:aws:iam::{aws_id}:user/{user}"
            for aws_id in aws_ids
        ]
    }
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowGetObject",
                "Effect": "Allow",
                "Principal": principal_value,
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    f"arn:aws:s3:us-east-1:{settings.AWS_ACCOUNT_ID}:accesspoint/{access_point_name}/object/{project_slug}/{project_version}/*",
                    f"arn:aws:s3:us-east-1:{settings.AWS_ACCOUNT_ID}:accesspoint/{access_point_name}",
                ],
            }
        ],
    }
    policy_str = json.dumps(policy)
    return policy_str


def set_data_access_point_policy(data_access_point_name, data_access_point_policy):
    """
    Apply a custom policy to an AWS S3 data access point.

    This function sets a custom access policy for the specified
    S3 data access point.

    Args:
        data_access_point_name (str): The name of the data access point.
        data_access_point_policy (str): The policy to be applied, in JSON string format.

    Returns:
        bool: True if the policy was successfully applied, False otherwise.

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in this function.
    """
    s3_control = create_s3_control_client()
    # Check if s3 is None
    if s3_control is None:
        return
    try:
        response = s3_control.put_access_point_policy(
            AccountId=settings.AWS_ACCOUNT_ID,
            Name=data_access_point_name,
            Policy=data_access_point_policy,
        )
        return True
    except Exception as e:
        print(f"Failed to apply policy: {e}")
        return False


def s3_bucket_has_access_point(project):
    """
    Check if an S3 bucket has an access point associated with the given project.

    This function determines whether an access point exists for the
    specified project within an S3 bucket.

    Args:
        project (object): The project object containing AWS and version information.

    Returns:
        bool: True if an access point exists, False otherwise.

    Note:
    - Ensure that the project object contains valid AWS and version information.
    """
    access_point_name = get_access_point_name(project)
    exists = AccessPoint.objects.filter(name=access_point_name).exists()
    return exists


def s3_bucket_has_credentialed_users(project):
    """
    Check if an S3 bucket has credentialed users associated with the given project.

    This function checks if there are credentialed users for the specified project.

    Args:
        project (object): The project object containing AWS and version information.

    Returns:
        bool: True if credentialed users exist, False otherwise.

    Note:
    - Ensure that the project object contains valid AWS and version information.
    """
    project_name = project.slug + "-" + project.version
    aws_ids = get_aws_accounts_for_dataset(project_name)
    return aws_ids != []


def create_first_data_access_point_policy(project):
    """
    Create the first data access point policy for a given project.

    This function generates and applies the initial data access point
    policy for the specified project.

    Args:
        project: The project containing AWS and
        version information.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in this function.
    """
    bucket_name = get_bucket_name(project)
    data_access_point_name = f"{project.slug}-v{project.version.replace('.', '-')}-01"
    try:
        create_s3_access_point(
            project, data_access_point_name, bucket_name, settings.AWS_ACCOUNT_ID
        )
    except Exception as e:
        print(
            f"Error while creating/accessing the access point {data_access_point_name}: {str(e)}"
        )


def update_data_access_point_policy(project):
    """
    Update the data access point policy for a given project.

    This function updates the data access point policy for the specified project,
    potentially creating multiple access points if necessary.

    Args:
        project: The project containing AWS and
        version information.

    Returns:
        None

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in this function.
    - Ensure that the project object contains valid AWS and
    version information.
    """
    MAX_PRINCIPALS_PER_AP_POLICY = 500
    project_name = project.slug + "-" + project.version
    aws_ids = get_aws_accounts_for_dataset(project_name)
    number_of_access_points_needed = ceil(len(aws_ids) / MAX_PRINCIPALS_PER_AP_POLICY)
    bucket_name = get_bucket_name(project)
    for i in range(number_of_access_points_needed):
        data_access_point_version = str(i + 1).zfill(2)
        data_access_point_name = f"{project.slug}-v{project.version.replace('.', '-')}-{data_access_point_version}"
        subset_aws_ids = aws_ids[
            i * MAX_PRINCIPALS_PER_AP_POLICY : (i + 1) * MAX_PRINCIPALS_PER_AP_POLICY
        ]

        access_point = AccessPoint.objects.filter(
            name=data_access_point_name, aws__project=project
        ).first()
        if not access_point:
            print("Access point doesn't exist, try to creat it:", access_point)
            try:
                access_point = create_s3_access_point(
                    project,
                    data_access_point_name,
                    bucket_name,
                    settings.AWS_ACCOUNT_ID,
                )
            except Exception as e:
                print(
                    f"Error while creating/accessing the access point {data_access_point_name}: {str(e)}"
                )
                if not access_point:
                    print(
                        f"Failed to retrieve the existing access point: {data_access_point_name}"
                    )
                    continue

        if not access_point or aws_ids is None:
            print("Access point or AWS IDs not found.")
            continue

        # Set policies and associate users for the newly created access point
        access_point_policy = create_data_access_point_policy(
            data_access_point_name, project.slug, project.version, subset_aws_ids
        )
        valid_ap_policy = set_data_access_point_policy(
            data_access_point_name, access_point_policy
        )
        if valid_ap_policy:
            associate_aws_users_with_data_access_point(access_point, subset_aws_ids)


def associate_aws_users_with_data_access_point(access_point, aws_ids):
    """
    Associate AWS users with a specified data access point.

    This function links AWS users to the specified data access point,
    creating new user entries if necessary.

    Args:
        access_point (object): The access point object.
        aws_ids (list): A list of AWS IDs to be associated with the access point.

    Returns:
        None

    Note:
    - Ensure that the access point and AWS IDs are valid.

    """
    existing_user_ids = set(access_point.users.values_list("aws_id", flat=True))
    new_user_ids = set(aws_ids) - existing_user_ids
    for aws_id in new_user_ids:
        user, created = AccessPointUser.objects.get_or_create(aws_id=aws_id)
        access_point.users.add(user)
    access_point.save()


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
    try:
        response = s3.create_access_point(
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
        access_point, created = AccessPoint.objects.get_or_create(
            aws=project.aws, name=access_point_name
        )
        return access_point
    except Exception as e:
        print("Error creating Access Point:", e)
        return None


def list_access_points(s3_control, account_id):
    """
    List all access points for the AWS account.

    This function retrieves a list of all access points associated
    with the specified AWS account.

    Args:
        s3_control (object): The S3 control client.
        account_id (str): The AWS account ID.

    Returns:
        list: A list of access points for the AWS account.

    Note:
    - Ensure that AWS credentials (Access Key and Secret Key)
    are properly configured for the S3 client used in this function.
    """
    try:
        response = s3_control.list_access_points(AccountId=account_id)
        return response["AccessPointList"]
    except ClientError as e:
        print("Error listing Access Points:", e)
        return []


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

    try:
        create_s3_bucket(s3, bucket_name)
    except s3.exceptions.BucketAlreadyExists:
        raise Exception(f"A bucket named {bucket_name} already exists.")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    put_bucket_logging(
        s3, bucket_name, settings.S3_SERVER_ACCESS_LOG_BUCKET, bucket_name + "/logs/"
    )
    folder_path = project.file_root()
    s3_prefix = f"{project.slug}/{project.version}/"
    send_files_to_s3(folder_path, s3_prefix, bucket_name, project)
    if project.access_policy == AccessPolicy.OPEN:
        update_open_bucket_policy(project, bucket_name)

    else:
        if s3_bucket_has_credentialed_users(project):
            update_data_access_point_policy(project)


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


def validade_aws_id(data_access_point_name, project_slug, project_version, aws_id):
    access_point_policy = create_data_access_point_policy(
        data_access_point_name, project_slug, project_version, aws_id
    )
    return set_data_access_point_policy(data_access_point_name, access_point_policy)
