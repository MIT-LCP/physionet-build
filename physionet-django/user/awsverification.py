import json
import re
import urllib.parse

import boto3
from django.conf import settings
from django.forms import ValidationError
import requests


# As of January 2024, boto3 (and older versions of awscli) cannot
# generate correct signed URLs for arbitrary AWS regions.  Always use
# us-east-1 for compatibility.
AWS_VERIFICATION_BUCKET_REGION = 'us-east-1'


def aws_verification_available():
    """
    Check whether the site is configured for AWS account authentication.
    """
    return bool(settings.AWS_VERIFICATION_BUCKET_NAME)


def parse_aws_user_arn(aws_user_arn, aws_account):
    """
    Check whether an AWS identity is supported for verification.

    AWS clients support numerous types of identities, described by
    ARNs (Amazon Resource Names).  For identity verification purposes,
    only "IAM user" identities are supported.  If the given ARN refers
    to an IAM user, this function returns a dictionary containing the
    account number and username.  Otherwise an UnsupportedUserARN
    exception is raised.
    """
    # This must match the principal pattern in the bucket policy
    # (see configure_aws_verification_bucket below).
    # For the set of characters allowed in path and username, see:
    # https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreateUser.html
    match = re.fullmatch(r'arn:aws:iam::(?P<account>[0-9]+):user/'
                         r'(?:[\x21-\x2e\x30-\x7e]*/)*'
                         r'(?P<username>[0-9a-zA-Z+=,.@_\-]+)',
                         aws_user_arn)
    if not match or match['account'] != aws_account:
        raise UnsupportedUserARN
    return match.groupdict()


def get_aws_verification_key(site_domain, user_email,
                             aws_account, aws_userid, aws_user_arn):
    """
    Generate an S3 key used to authenticate an AWS user.

    This is a string that must be signed by the user, and then
    verified by Amazon S3, to verify the user's credentials.
    """
    info = parse_aws_user_arn(aws_user_arn, aws_account)
    aws_username = info['username']

    # user_email is quoted to avoid slashes, as well as any shell
    # metacharacters in the verification command.  (The other
    # variables used here shouldn't contain any slashes or shell
    # metacharacters.)  This is unrelated to the URL-encoding
    # performed by S3 itself.
    quoted_email = urllib.parse.quote(user_email, safe='@:+,')

    # This must match the resource pattern in the bucket policy
    # (see configure_aws_verification_bucket below).
    return (f'{site_domain}-verification/'
            f'email={quoted_email}/'
            f'userid={aws_userid}/'
            f'account={aws_account}/'
            f'username={aws_username}/')


def get_aws_verification_command(site_domain, user_email,
                                 aws_account, aws_userid, aws_user_arn):
    """
    Generate a shell command used to authenticate an AWS user.

    After the user enters their account ID and user ID, they will be
    asked to run this command and copy its output into the form.  The
    output of the command is a signed URL: it proves that the person
    who generated it has appropriate AWS credentials, without
    revealing the person's secret key.
    """
    bucket = settings.AWS_VERIFICATION_BUCKET_NAME
    region = AWS_VERIFICATION_BUCKET_REGION
    if not bucket or not region:
        raise AWSVerificationNotConfigured

    key = get_aws_verification_key(site_domain, user_email,
                                   aws_account, aws_userid, aws_user_arn)
    return f'aws s3 presign s3://{bucket}/{key} --region {region}'


def check_aws_verification_url(site_domain, user_email,
                               aws_account, aws_userid, aws_user_arn,
                               signed_url):
    """
    Verify a signed URL to determine a user's AWS identity.

    To verify their AWS identity, the user is asked to generate a
    specific signed URL.  If the URL is correct and valid, this
    function returns a dictionary containing the person's verified
    identity information.

    For this to work, the verification bucket must be configured by
    calling configure_aws_verification_bucket().

    Note that only the "account" and "username" portions of
    aws_user_arn are verified (not the "path").
    """
    bucket = settings.AWS_VERIFICATION_BUCKET_NAME
    region = AWS_VERIFICATION_BUCKET_REGION
    if not bucket or not region:
        raise AWSVerificationNotConfigured

    try:
        unsigned_url, query = signed_url.split('?')
        query_dict = urllib.parse.parse_qs(query)
    except ValueError:
        raise InvalidSignedURL

    # Check whether this appears to be an AWS signed URL (either old
    # or new format).
    query_keys = set(query_dict.keys())
    if query_keys >= {'X-Amz-Algorithm', 'X-Amz-Credential',
                      'X-Amz-Date', 'X-Amz-Expires',
                      'X-Amz-SignedHeaders', 'X-Amz-Signature'}:
        pass
    elif query_keys >= {'AWSAccessKeyId', 'Signature', 'Expires'}:
        pass
    else:
        raise InvalidSignedURL

    # Check whether the URL corresponds to the correct bucket name.
    # Any of these base URLs might be used depending on the region and
    # the client configuration.
    base_urls = [
        f'https://{bucket}.s3.{region}.amazonaws.com/',
        f'https://s3.{region}.amazonaws.com/{bucket}/',
        f'https://{bucket}.s3.amazonaws.com/',
        f'https://s3.amazonaws.com/{bucket}/',
    ]
    for base_url in base_urls:
        if unsigned_url.startswith(base_url):
            key = unsigned_url[len(base_url):]
            break
    else:
        raise InvalidS3Hostname

    # Check that the URL path matches the expected key.  ('aws s3
    # presign' uses escaping identical to urllib.parse.quote.)

    expected_key = get_aws_verification_key(site_domain, user_email,
                                            aws_account, aws_userid,
                                            aws_user_arn)
    if key != urllib.parse.quote(expected_key):
        raise InvalidVerificationKey

    # Finally, verify the signature.

    with requests.Session() as session:
        # If the signature is correct, and the identity is correct as
        # determined by the bucket policy, then S3 should return a 404
        # response (because the resource doesn't, in fact, exist.)
        response = session.get(signed_url)
        if response.status_code != 404:
            raise InvalidAWSSignature

        # As a sanity check, verify that S3 returns a 403 response if
        # the AWS signature is missing.
        response = session.get(unsigned_url)
        if response.status_code != 403:
            raise BadBucketPolicy

    return {
        'account': aws_account,
        'userid': aws_userid,
        'arn': aws_user_arn,
    }


class AWSVerificationFailed(ValidationError):
    """Generic exception used if AWS user cannot be verified."""


class AWSVerificationNotConfigured(AWSVerificationFailed):
    """Required settings for AWS verification are not defined."""
    def __init__(self):
        super().__init__(
            'AWS identity verification is currently unavailable.'
        )


class UnsupportedUserARN(AWSVerificationFailed):
    """Client-supplied ARN is not valid or cannot be verified."""
    def __init__(self):
        super().__init__(
            'Invalid ARN.  Please use an IAM user identity '
            '(arn:aws:iam::111111111111:user/NAME) rather than '
            'a root user or IAM role.'
        )


class InvalidSignedURL(AWSVerificationFailed):
    """Client-supplied URL does not appear to be an AWS signed URL."""
    def __init__(self):
        super().__init__(
            'Invalid verification code (not an AWS signed URL). '
            'Please run the command exactly as shown, and copy '
            'and paste the output.'
        )


class InvalidS3Hostname(AWSVerificationFailed):
    """Client-supplied URL does not match expected S3 hostname."""
    def __init__(self):
        super().__init__(
            'Invalid verification code (incorrect hostname). '
            'Please run the command exactly as shown, and copy '
            'and paste the output.'
        )


class InvalidVerificationKey(AWSVerificationFailed):
    """Client-supplied URL does not match expected verification key."""
    def __init__(self):
        super().__init__(
            'Invalid verification code (incorrect path). '
            'Please run the command exactly as shown, and copy '
            'and paste the output.'
        )


class InvalidAWSSignature(AWSVerificationFailed):
    """Client-supplied URL cannot be verified by AWS."""
    def __init__(self):
        super().__init__(
            'Invalid verification code (incorrect signature). '
            'Please run the command exactly as shown, and copy '
            'and paste the output.'
        )


class BadBucketPolicy(AWSVerificationFailed):
    """Verification bucket is not correctly configured."""
    def __init__(self):
        super().__init__(
            'AWS identity verification is currently unavailable.'
        )


def configure_aws_verification_bucket(bucket_name):
    """
    Configure an S3 bucket to be used for identity verification.
    """
    s3 = boto3.client('s3', region_name=AWS_VERIFICATION_BUCKET_REGION)
    try:
        s3.create_bucket(Bucket=bucket_name)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass

    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": False,
            "IgnorePublicAcls": False,
            "BlockPublicPolicy": False,
            "RestrictPublicBuckets": False,
        },
    )

    # This must match the set of allowed principals
    # (see parse_aws_user_arn above).
    principal = "*"

    # This must match the required verification key
    # (see get_aws_verification_key above).
    resource = ("*-verification/"
                + "email=*/"
                + "userid=${aws:userid}/"
                + "account=${aws:PrincipalAccount}/"
                + "username=${aws:username}/")

    # https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html:
    #
    #     You need the relevant read object (or version) permission
    #     for [the GetObject] operation. For more information, see
    #     Specifying Permissions in a Policy. If the object that you
    #     request doesn't exist, the error that Amazon S3 returns
    #     depends on whether you also have the s3:ListBucket
    #     permission.
    #
    #     If you have the s3:ListBucket permission on the bucket,
    #     Amazon S3 returns an HTTP status code 404 (Not Found) error.
    #
    #     If you don't have the s3:ListBucket permission, Amazon S3
    #     returns an HTTP status code 403 ("access denied") error.
    #
    # The documentation doesn't say so, but (as of November 2023) it
    # appears sufficient for the client to have permission to perform
    # an s3:ListBucket action with s3:prefix exactly equal to the
    # requested key.
    #
    # For example, assuming the object doesn't exist,
    # https://xxxx.s3.amazonaws.com/a/b/c returns 404 if
    # https://xxxx.s3.amazonaws.com/?prefix=a/b/c returns 200.
    #
    # Moreover, the s3:GetObject permission may not actually be
    # required in this case.  Both the s3:GetObject and s3:ListBucket
    # permissions are included here for future-proofing.

    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": principal,
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket_name}/{resource}",
            },
            {
                "Effect": "Allow",
                "Principal": principal,
                "Action": "s3:ListBucket",
                "Resource": f"arn:aws:s3:::{bucket_name}",
                "Condition": {
                    "StringLike": {
                        "s3:prefix": resource,
                    },
                },
            },
        ],
    })

    s3.put_bucket_policy(Bucket=bucket_name, Policy=policy)


def test_aws_verification_bucket(bucket_name):
    """
    Test functionality of an identity verification bucket.
    """
    s3 = boto3.client('s3', region_name=AWS_VERIFICATION_BUCKET_REGION)
    sts = boto3.client('sts')

    identity = sts.get_caller_identity()
    aws_account = identity['Account']
    aws_userid = identity['UserId']
    aws_arn = identity['Arn']

    def assert_response(url, expected_status):
        response = requests.get(url)
        if response.status_code != expected_status:
            raise Exception(
                f"Expected {expected_status} for {url}, got instead:\n"
                f" {response.status_code} {response.reason}\n\n"
                f" {response.content}\n"
            )

    def tweak(string):
        return string.translate({ord(i): ord(j) for i, j in zip(
            '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+/',
            '1032547698BADCFEHGJILKNMPORQTSVUXWZYbadcfehgjilknmporqtsvuxwzy/+'
        )})

    def tweak_part(string, sep, n):
        parts = string.split(sep)
        parts[n] = tweak(parts[n])
        return sep.join(parts)

    site_domain = 'physionet.org'
    user_email = 'root@example.com'

    # Correct signed URL should give a 404
    signed_url = s3.generate_presigned_url('get_object', Params={
        'Bucket': bucket_name,
        'Key': get_aws_verification_key(site_domain, user_email,
                                        aws_account, aws_userid, aws_arn),
    })
    assert_response(signed_url, 404)

    # URL without signature should give a 403
    unsigned_url, query = signed_url.split('?')
    assert_response(unsigned_url, 403)

    # Wrong signature should give a 403
    query_dict = dict(urllib.parse.parse_qsl(query))
    for key in ('Signature', 'X-Amz-Signature'):
        if key in query_dict:
            query_dict[key] = tweak(query_dict[key])
    wrong_url = unsigned_url + '?' + urllib.parse.urlencode(query_dict)
    assert_response(wrong_url, 403)

    # Signed URL with wrong user ID should give a 403
    wrong_userid = tweak(aws_userid)
    wrong_url = s3.generate_presigned_url('get_object', Params={
        'Bucket': bucket_name,
        'Key': get_aws_verification_key(site_domain, user_email,
                                        aws_account, wrong_userid, aws_arn),
    })
    assert_response(wrong_url, 403)

    # Signed URL with wrong account ID should give a 403
    wrong_account = tweak(aws_account)
    wrong_arn = tweak_part(aws_arn, ':', 4)
    wrong_url = s3.generate_presigned_url('get_object', Params={
        'Bucket': bucket_name,
        'Key': get_aws_verification_key(site_domain, user_email,
                                        wrong_account, aws_userid, wrong_arn),
    })
    assert_response(wrong_url, 403)

    # Signed URL with wrong username should give a 403
    wrong_arn = tweak_part(aws_arn, '/', -1)
    wrong_url = s3.generate_presigned_url('get_object', Params={
        'Bucket': bucket_name,
        'Key': get_aws_verification_key(site_domain, user_email,
                                        aws_account, aws_userid, wrong_arn),
    })
    assert_response(wrong_url, 403)
