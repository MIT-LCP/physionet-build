# Import the necessary libraries
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from django.conf import settings
from django.template import loader


def convert_data_time(str_date_time):
    # Convert the string date time to a datetime object
    datetime_object = datetime.strptime(str_date_time.text, '%Y-%m-%dT%H:%M:%S.%f%z')
    return datetime_object


def send_request(xml_payload):
    # Define the headers for the request
    headers = {
        'Content-Type': 'text/xml; charset=utf-8'
    }

    # URL for the request
    soap_request_url = settings.CITI_SOAP_URL

    # Send the POST request and get the response
    response = requests.request("POST", soap_request_url, headers=headers, data=xml_payload)

    # Parse the XML response into an ElementTree object
    root = ET.fromstring(response.text)

    return root


def get_memberid(email):
    # Get username and password from Django settings
    username = settings.CITI_USERNAME
    password = settings.CITI_PASSWORD

    # Get the member ID using email
    payload = loader.render_to_string(
        'user/citi/get_inst_member_by_email.xml', {
            'username': username,
            'password': password,
            'email': email,
        }
    )

    root = send_request(xml_payload=payload)

    # Get the member ID
    memberid = root.find('.//intMemberID')
    if memberid is None:
        return None
    return memberid.text


def get_citiprogram_completion(email):
    # Get username and password from Django settings
    username = settings.CITI_USERNAME
    password = settings.CITI_PASSWORD

    memberid = get_memberid(email)

    if memberid is None:
        return []

    # Get the member courses using the member ID
    payload_courses = loader.render_to_string('user/citi/get_courses_by_member.xml', {
        'username': username, 'password': password, 'memberid': memberid, })

    # parse the XML response for the member courses
    root_courses = send_request(xml_payload=payload_courses)

    # Creates a list of dictionarys for each CompletionReport
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
            'dtePassed': convert_data_time(dtePassed),
            'intScore': intScore.text,
            'intPassingScore': intPassingScore.text,
            'dteExpiration': convert_data_time(dteExpiration)})

    return completion_info
