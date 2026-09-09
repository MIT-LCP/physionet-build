import logging
import requests

from datetime import datetime
import xml.etree.ElementTree as ET

from django.conf import settings
from django.template import loader
from django.utils import timezone

from user.models import AssociatedEmail, CITIGroupMapping, CITIVerification

logger = logging.getLogger(__name__)

CITI_REQUEST_TIMEOUT = 30


def convert_date_time(str_date_time):
    """
    Converts a string in ISO 8601 format to a datetime object.

    Args:
        str_date_time (str): A string representing a date and time in the format
            'YYYY-MM-DDTHH:MM:SS.ssssss±HH:MM', where ±HH:MM is the time zone offset.

    Returns:
        datetime: A datetime object corresponding to the input string.
    """
    datetime_object = datetime.strptime(str_date_time, '%Y-%m-%dT%H:%M:%S.%f%z')
    return datetime_object


def send_request(xml_payload):
    """
    Sends a SOAP request to a CITI API endpoint with the specified XML payload and returns the parsed response.

    Args:
        xml_payload (str): The XML payload to send in the SOAP request.

    Returns:
        The root element of the parsed XML response.
    """
    headers = {
        'Content-Type': 'text/xml; charset=utf-8'
    }

    soap_request_url = settings.CITI_SOAP_URL

    response = requests.request(
        "POST", soap_request_url, headers=headers, data=xml_payload,
        timeout=CITI_REQUEST_TIMEOUT,
    )

    root = ET.fromstring(response.text)

    return root


def get_member_profile(email):
    """
    Retrieves the CITI member profile associated with the given email address.

    Returns a dict with member profile fields, or None if no matching member
    is found. The dict includes: intMemberID, strFirstII, strLastII,
    strUsernameII, strmemberEmail, strInstEmail, dteAdded, dteAffiliated.
    """
    username = settings.CITI_USERNAME
    password = settings.CITI_PASSWORD

    payload = loader.render_to_string(
        'user/citi/get_inst_member_by_email.xml', {
            'username': username,
            'password': password,
            'email': email,
        }
    )

    root = send_request(xml_payload=payload)

    memberid = root.find('.//intMemberID')
    if memberid is None:
        return None

    crs = root.find('.//CRS')
    if crs is None:
        return None

    def text(tag):
        el = crs.find(tag)
        return el.text if el is not None else ''

    return {
        'intMemberID': text('intMemberID'),
        'strFirstII': text('strFirstII'),
        'strLastII': text('strLastII'),
        'strUsernameII': text('strUsernameII'),
        'strmemberEmail': text('strmemberEmail'),
        'strInstEmail': text('strInstEmail'),
        'dteAdded': text('dteAdded'),
        'dteAffiliated': text('dteAffiliated'),
    }


def get_memberid(email):
    """
    Retrieves the CITI member ID associated with the given email address.

    Returns the member ID as a string, or None if no matching member is found.
    """
    profile = get_member_profile(email)
    if profile is None:
        return None
    return profile['intMemberID']


def get_citiprogram_completion(email):
    """
    Retrieves completion information for all CITI courses associated with the given email address.

    Returns a tuple of (completions, member_id, member_profile) where completions
    is a list of dicts, member_id is a string, and member_profile is a dict.
    If no member is found, returns ([], None, None).

    Each completion dict contains the following keys:
        FirstName, LastName, MemberID, memberEmail, strCompletionReport,
        intGroupID, strGroup, intStageID, intStageNumber, strStage,
        intCompletionReportID, intMemberStageID, dtePassed (datetime),
        intScore, intPassingScore, dteExpiration (datetime).
    """

    username = settings.CITI_USERNAME
    password = settings.CITI_PASSWORD

    member_profile = get_member_profile(email)

    if member_profile is None:
        return [], None, None

    memberid = member_profile['intMemberID']

    payload_courses = loader.render_to_string('user/citi/get_courses_by_member.xml', {
        'username': username, 'password': password, 'memberid': memberid, })

    root_courses = send_request(xml_payload=payload_courses)

    completion_info = []
    for crs in root_courses.findall('.//CRSMEMBERID'):
        fields = {
            'FirstName': crs.find('FirstName'),
            'LastName': crs.find('LastName'),
            'MemberID': crs.find('MemberID'),
            'memberEmail': crs.find('memberEmail'),
            'strCompletionReport': crs.find('strCompletionReport'),
            'strGroup': crs.find('strGroup'),
            'intGroupID': crs.find('intGroupID'),
            'intStageID': crs.find('intStageID'),
            'intStageNumber': crs.find('intStageNumber'),
            'strStage': crs.find('strStage'),
            'intCompletionReportID': crs.find('intCompletionReportID'),
            'intMemberStageID': crs.find('intMemberStageID'),
            'intScore': crs.find('intScore'),
            'intPassingScore': crs.find('intPassingScore'),
            'dtePassed': crs.find('dtePassed'),
            'dteExpiration': crs.find('dteExpiration'),
        }

        # Skip entries with missing required fields
        if any(v is None for v in fields.values()):
            continue

        completion_info.append({
            'FirstName': fields['FirstName'].text,
            'LastName': fields['LastName'].text,
            'MemberID': fields['MemberID'].text,
            'memberEmail': fields['memberEmail'].text,
            'strCompletionReport': fields['strCompletionReport'].text,
            'intGroupID': fields['intGroupID'].text,
            'strGroup': fields['strGroup'].text,
            'intStageID': fields['intStageID'].text,
            'intStageNumber': fields['intStageNumber'].text,
            'strStage': fields['strStage'].text,
            'intCompletionReportID': fields['intCompletionReportID'].text,
            'intMemberStageID': fields['intMemberStageID'].text,
            'dtePassed': convert_date_time(fields['dtePassed'].text),
            'intScore': fields['intScore'].text,
            'intPassingScore': fields['intPassingScore'].text,
            'dteExpiration': convert_date_time(fields['dteExpiration'].text),
        })

    return completion_info, memberid, member_profile


def lookup_citi_completions_for_user(user):
    """
    Look up CITI completions for a user by trying all their verified emails.

    Tries the primary email first, then other verified associated emails.

    Returns:
        (email_used, completions_list, member_id, member_profile, error_message)
    """
    verified_emails = list(
        AssociatedEmail.objects.filter(
            user=user, is_verified=True
        ).order_by('-is_primary_email').values_list('email', flat=True)
    )

    if not verified_emails:
        return None, [], None, None, 'No verified emails found on your account.'

    last_error = None
    for email in verified_emails:
        try:
            completions, member_id, member_profile = get_citiprogram_completion(email)
            if completions:
                return email, completions, member_id, member_profile, None
        except (requests.RequestException, ET.ParseError) as e:
            logger.error('CITI API error for email %s: %s', email, str(e))
            last_error = str(e)

    if last_error:
        return None, [], None, None, 'Error communicating with CITI API. Please try again later.'

    return None, [], None, None, 'No CITI training records found for any of your verified emails.'


def find_matching_completion(completions, training_type):
    """
    Find a completion that matches the given training type via CITIGroupMapping.

    Returns the matching completion with the latest non-expired dteExpiration,
    or None if no match is found.
    """

    mapped_group_ids = set(
        CITIGroupMapping.objects.filter(
            training_type=training_type
        ).values_list('citi_group_id', flat=True)
    )

    if not mapped_group_ids:
        return None

    now = timezone.now()
    best_match = None

    for completion in completions:
        try:
            group_id = int(completion['intGroupID'])
        except (ValueError, TypeError):
            continue

        if group_id not in mapped_group_ids:
            continue

        expiration = completion.get('dteExpiration')
        if expiration and expiration < now:
            continue

        if best_match is None or completion['dteExpiration'] > best_match['dteExpiration']:
            best_match = completion

    return best_match


def serialize_completions(completions):
    """
    Convert datetime objects to ISO strings for JSON storage.
    """
    serialized = []
    for completion in completions:
        entry = {}
        for key, value in completion.items():
            if isinstance(value, datetime):
                entry[key] = value.isoformat()
            else:
                entry[key] = value
        serialized.append(entry)
    return serialized


def verify_training_via_citi_api(training):
    """
    Run CITI API verification for a training submission and store the results.

    Called after a CITI training is saved (with PDF). Looks up the user's
    verified emails in the CITI API and stores any matching completion data.
    Failure does not block the PDF-based submission.
    """

    # Only run for training types that have CITI group mappings
    if not CITIGroupMapping.objects.filter(training_type=training.training_type).exists():
        return

    verification, _ = CITIVerification.objects.get_or_create(training=training)

    try:
        email_used, completions, member_id, member_profile, error = (
            lookup_citi_completions_for_user(training.user)
        )
    except Exception as e:
        logger.error('CITI API verification failed for training %s: %s', training.pk, str(e))
        verification.api_error = str(e)[:512]
        verification.save(update_fields=['api_error'])
        return

    if error:
        verification.api_error = error[:512]
        verification.save(update_fields=['api_error'])
        return

    verification.lookup_email = email_used or ''
    verification.member_id = member_id or ''
    verification.api_error = ''
    verification.completion_data = None
    verification.completion_report_id = ''

    citi_data = {}
    if completions:
        citi_data['completions'] = serialize_completions(completions)
    if member_profile:
        citi_data['member_profile'] = member_profile
    if citi_data:
        verification.completion_data = citi_data

    match = find_matching_completion(completions, training.training_type)
    if match:
        verification.completion_report_id = match.get('intCompletionReportID', '')

    verification.save(update_fields=[
        'lookup_email', 'member_id', 'completion_report_id',
        'completion_data', 'api_error',
    ])
