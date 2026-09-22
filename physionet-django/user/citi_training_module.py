import logging
import requests
from dataclasses import dataclass, field

from datetime import datetime
import xml.etree.ElementTree as ET

from django.conf import settings
from django.template import loader
from django.utils import timezone

from user.models import AssociatedEmail, CITIGroupMapping, CITIVerification

logger = logging.getLogger(__name__)

CITI_REQUEST_TIMEOUT = 30


@dataclass
class CITICompletionResult:
    """Result from get_citiprogram_completion()."""
    completions: list = field(default_factory=list)
    member_id: str = None
    member_profile: dict = None
    member_profile_xml: str = ''
    completions_xml: str = ''


@dataclass
class CITILookupResult:
    """Result from lookup_citi_completions_for_user()."""
    email_used: str = None
    completions: list = field(default_factory=list)
    member_id: str = None
    member_profile: dict = None
    member_profile_xml: str = ''
    completions_xml: str = ''
    error: str = None


def convert_date_time(str_date_time):
    """
    Converts a string in ISO 8601 format to a datetime object.

    Args:
        str_date_time (str): A string representing a date and time in the format
            'YYYY-MM-DDTHH:MM:SS[.ssssss]±HH:MM', where the fractional seconds
            are optional and ±HH:MM is the time zone offset.

    Returns:
        datetime: A datetime object corresponding to the input string.
    """
    return datetime.fromisoformat(str_date_time)


def send_request(xml_payload):
    """
    Sends a SOAP request to a CITI API endpoint with the specified XML payload
    and returns the parsed response along with the raw response text.

    Args:
        xml_payload (str): The XML payload to send in the SOAP request.

    Returns:
        A tuple of (root, response_text) where root is the parsed XML element
        and response_text is the raw XML string.
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

    return root, response.text


def _extract_profile_from_root(root):
    """
    Extract member profile fields from a parsed XML root element.

    Returns a dict with profile fields, or None if no CRS element is found.
    """
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


def _extract_completions_from_root(root):
    """
    Extract completion records from a parsed XML root element.

    Returns a list of dicts with string values for all fields.
    """
    completions = []
    for crs in root.findall('.//CRSMEMBERID'):
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

        completions.append({k: el.text for k, el in fields.items()})

    return completions


def get_member_profile(email):
    """
    Retrieves the CITI member profile associated with the given email address.

    Returns a tuple of (profile_dict, raw_xml) where profile_dict contains
    member profile fields, or (None, raw_xml) if no matching member is found.
    The dict includes: intMemberID, strFirstII, strLastII, strUsernameII,
    strmemberEmail, strInstEmail, dteAdded, dteAffiliated.
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

    root, raw_xml = send_request(xml_payload=payload)

    # A valid response contains the GetInstMemberByEmailResult element,
    # even when no member is found (the diffgram will simply be empty).
    # Note: the API returns the same empty structure for invalid
    # credentials, so we cannot distinguish auth errors from "not found".
    ns = 'https://webservices.citiprogram.org/'
    if root.find('.//{%s}GetInstMemberByEmailResult' % ns) is None:
        raise ValueError('CITI API: unexpected response format.')

    memberid = root.find('.//intMemberID')
    if memberid is None:
        return None, raw_xml

    profile = _extract_profile_from_root(root)
    return profile, raw_xml


def get_memberid(email):
    """
    Retrieves the CITI member ID associated with the given email address.

    Returns the member ID as a string, or None if no matching member is found.
    """
    profile, _ = get_member_profile(email)
    if profile is None:
        return None
    return profile['intMemberID']


def get_citiprogram_completion(email):
    """
    Retrieves completion information for all CITI courses associated with the given email address.

    Returns a CITICompletionResult. Each completion dict contains:
        FirstName, LastName, MemberID, memberEmail, strCompletionReport,
        intGroupID, strGroup, intStageID, intStageNumber, strStage,
        intCompletionReportID, intMemberStageID, dtePassed (datetime),
        intScore, intPassingScore, dteExpiration (datetime).
    """

    username = settings.CITI_USERNAME
    password = settings.CITI_PASSWORD

    member_profile, member_profile_xml = get_member_profile(email)

    if member_profile is None:
        return CITICompletionResult(member_profile_xml=member_profile_xml)

    memberid = member_profile['intMemberID']

    payload_courses = loader.render_to_string('user/citi/get_courses_by_member.xml', {
        'username': username, 'password': password, 'memberid': memberid, })

    root_courses, completions_xml = send_request(xml_payload=payload_courses)

    completion_info = _extract_completions_from_root(root_courses)
    for entry in completion_info:
        entry['dtePassed'] = convert_date_time(entry['dtePassed'])
        entry['dteExpiration'] = convert_date_time(entry['dteExpiration'])

    return CITICompletionResult(
        completions=completion_info,
        member_id=memberid,
        member_profile=member_profile,
        member_profile_xml=member_profile_xml,
        completions_xml=completions_xml,
    )


def lookup_citi_completions_for_user(user):
    """
    Look up CITI completions for a user by trying all their verified emails.

    Tries the primary email first, then other verified associated emails.

    Returns a CITILookupResult.
    """
    verified_emails = list(
        AssociatedEmail.objects.filter(
            user=user, is_verified=True
        ).order_by('-is_primary_email').values_list('email', flat=True)
    )

    if not verified_emails:
        return CITILookupResult(error='No verified emails found on your account.')

    last_error = None
    for email in verified_emails:
        try:
            result = get_citiprogram_completion(email)
            if result.completions:
                return CITILookupResult(
                    email_used=email,
                    completions=result.completions,
                    member_id=result.member_id,
                    member_profile=result.member_profile,
                    member_profile_xml=result.member_profile_xml,
                    completions_xml=result.completions_xml,
                )
        except (requests.RequestException, ET.ParseError, ValueError) as e:
            logger.error('CITI API error for email %s: %s', email, str(e))
            last_error = str(e)

    if last_error:
        return CITILookupResult(error='Error communicating with CITI API. Please try again later.')

    return CITILookupResult(error='No CITI training records found for any of your verified emails.')


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


def parse_member_profile_xml(xml_string):
    """
    Parse stored member profile XML into a dict for template rendering.

    Returns a dict with member profile fields, or None if parsing fails
    or no profile data is present.
    """
    if not xml_string:
        return None

    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        return None

    return _extract_profile_from_root(root)


def parse_completions_xml(xml_string):
    """
    Parse stored completions XML into a list of dicts for template rendering.

    Returns a list of completion dicts, or an empty list if parsing fails
    or no completion data is present. Datetime fields are returned as strings.
    """
    if not xml_string:
        return []

    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        return []

    return _extract_completions_from_root(root)


def verify_training_via_citi_api(training):
    """
    Run CITI API verification for a training submission and store the results.

    Called after a CITI training is saved (with PDF). Looks up the user's
    verified emails in the CITI API and stores any matching completion data.
    Failure does not block the PDF-based submission.
    """

    # Skip if CITI API credentials are not configured
    if not all([settings.CITI_USERNAME, settings.CITI_PASSWORD, settings.CITI_SOAP_URL]):
        return

    # Only run for training types that have CITI group mappings
    if not CITIGroupMapping.objects.filter(training_type=training.training_type).exists():
        return

    verification, _ = CITIVerification.objects.get_or_create(training=training)

    try:
        result = lookup_citi_completions_for_user(training.user)
    except Exception as e:
        logger.error('CITI API verification failed for training %s: %s', training.pk, str(e))
        verification.api_error = str(e)[:512]
        verification.save(update_fields=['api_error'])
        return

    if result.error:
        verification.api_error = result.error[:512]
        verification.save(update_fields=['api_error'])
        return

    verification.lookup_email = result.email_used or ''
    verification.member_id = result.member_id or ''
    verification.api_error = ''
    verification.member_profile_xml = result.member_profile_xml
    verification.completions_xml = result.completions_xml
    verification.completion_report_id = ''

    match = find_matching_completion(result.completions, training.training_type)
    if match:
        verification.completion_report_id = match.get('intCompletionReportID', '')

    verification.save(update_fields=[
        'lookup_email', 'member_id', 'completion_report_id',
        'member_profile_xml', 'completions_xml', 'api_error',
    ])
