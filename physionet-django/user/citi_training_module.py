import requests

from datetime import datetime
import xml.etree.ElementTree as ET

from django.conf import settings
from django.template import loader


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

    response = requests.request("POST", soap_request_url, headers=headers, data=xml_payload)

    root = ET.fromstring(response.text)

    return root


def get_memberid(email):
    """
    Retrieves the CITI member ID associated with the given email address.

    Args:
        email (str): The email address to search for.

    Returns:
        The member ID as a string, or None if no matching member is found.
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
    return memberid.text


def get_citiprogram_completion(email):
    """
    Retrieves completion information for all CITI courses associated with the given email address.

    Args:
        email (str): The email address to search for.

    Returns:
        A list of dictionaries containing completion information for each course.
        Each dictionary contains the following keys:
        - 'FirstName': The first name of the user who completed the course.
        - 'LastName': The last name of the user who completed the course.
        - 'MemberID': The CITI member ID of the user who completed the course.
        - 'memberEmail': The email address of the user who completed the course.
        - 'strCompletionReport': The completion status of the course (e.g.,'Human Research').
        - 'intGroupID': The ID of the course group (e.g., '43007').
        - 'strGroup': The name of the course group (e.g., 'Data or Specimens Only Research').
        - 'intStageID': The ID of the course stage (e.g., '106240').
        - 'intStageNumber': The number of the course stage within the group (e.g., '1').
        - 'strStage': The name of the course stage (e.g., 'Basic Course').
        - 'intCompletionReportID': The ID of the completion report.
        - 'intMemberStageID': The ID of the member stage.
        - 'dtePassed': The date and time the course was completed, as a datetime object.
        - 'intScore': The score earned for the course.
        - 'intPassingScore': The passing score for the course.
        - 'dteExpiration': The date and time the course will expire, as a datetime object.

        If no courses are found for the given email address, returns an empty list.
    """

    username = settings.CITI_USERNAME
    password = settings.CITI_PASSWORD

    memberid = get_memberid(email)

    if memberid is None:
        return []

    payload_courses = loader.render_to_string('user/citi/get_courses_by_member.xml', {
        'username': username, 'password': password, 'memberid': memberid, })

    root_courses = send_request(xml_payload=payload_courses)

    completion_info = []
    for crs in root_courses.findall('.//CRSMEMBERID'):
        FirstName = crs.find('FirstName')
        LastName = crs.find('LastName')
        MemberID = crs.find('MemberID')
        memberEmail = crs.find('memberEmail')
        strCompletionReport = crs.find('strCompletionReport')
        strGroup = crs.find('strGroup')
        intGroupID = crs.find('intGroupID')
        intStageID = crs.find('intStageID')
        intStageNumber = crs.find('intStageNumber')
        strStage = crs.find('strStage')
        intCompletionReportID = crs.find('intCompletionReportID')
        intMemberStageID = crs.find('intMemberStageID')
        intScore = crs.find('intScore')
        intPassingScore = crs.find('intPassingScore')
        dtePassed = crs.find('dtePassed')
        dteExpiration = crs.find('dteExpiration')

        completion_info.append({
            'FirstName': FirstName.text,
            'LastName': LastName.text,
            'MemberID': MemberID.text,
            'memberEmail': memberEmail.text,
            'strCompletionReport': strCompletionReport.text,
            'intGroupID': intGroupID.text,
            'strGroup': strGroup.text,
            'intStageID': intStageID.text,
            'intStageNumber': intStageNumber.text,
            'strStage': strStage.text,
            'intCompletionReportID': intCompletionReportID.text,
            'intMemberStageID': intMemberStageID.text,
            'dtePassed': convert_date_time(dtePassed.text),
            'intScore': intScore.text,
            'intPassingScore': intPassingScore.text,
            'dteExpiration': convert_date_time(dteExpiration.text)})

    return completion_info
