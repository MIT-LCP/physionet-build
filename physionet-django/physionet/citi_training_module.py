# Import the necessary libraries
import requests
import xml.etree.ElementTree as ET
from django.conf import settings


def get_citiprogram_completion(email):
    # Get username and password from Django settings
    username = settings.CITI_USERNAME
    password = settings.CITI_PASSWORD

    # SOAP request URL
    url = "https://webservices.citiprogram.org/SOAP/CITISOAPService.asmx"

    # structured XML
    payload = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
      <soap12:Body>
        <GetInstMemberByEmail xmlns="https://webservices.citiprogram.org/">
          <usr>{username}</usr>
          <pwd>{password}</pwd>
          <strEmail>{email}</strEmail>
        </GetInstMemberByEmail>
      </soap12:Body>
    </soap12:Envelope>"""

    # headers
    headers = {
        'Content-Type': 'text/xml; charset=utf-8'
    }

    # POST request
    response = requests.request("POST", url, headers=headers, data=payload)

    # parse the XML response
    root = ET.fromstring(response.text)

    # get the member ID
    memberid = root.find('.//intMemberID').text

    # get the member courses using the member ID
    payload_courses = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
      <soap12:Body>
        <GetMemberCoursesbyID xmlns="https://webservices.citiprogram.org/">
          <usr>{username}</usr>
          <pwd>{password}</pwd>
          <intMemberID>{memberid}</intMemberID>
        </GetMemberCoursesbyID>
      </soap12:Body>
    </soap12:Envelope>"""

    # headers for the member courses request
    headers = {
        'Content-Type': 'text/xml; charset=utf-8'
    }

    # POST request for the member courses
    response_courses = requests.request("POST", url, headers=headers, data=payload_courses)

    # parse the XML response for the member courses
    root_courses = ET.fromstring(response_courses.text)

    # find the completion information
    completion_info = []
    for crs in root_courses.findall('.//CRSMEMBERID'):
        report_elem = crs.find('strCompletionReport')
        group_elem = crs.find('strGroup')
        course_id = crs.find('intGroupID')
        mini_score_elem = crs.find('intPassingScore')
        score_elem = crs.find('intScore')
        passed_elem = crs.find('dtePassed')
        expire_elem = crs.find('dteExpiration')

        if group_elem is not None and course_id.text == '43007' and \
           group_elem.text == 'Data or Specimens Only Research':
            # append the completion information to the list
            completion_info.append({
                'report': report_elem.text,
                'group': group_elem.text,
                'course_id': course_id.text,
                'score': score_elem.text,
                'mini_passing_score': mini_score_elem.text,
                'passed_date': passed_elem.text,
                'expiration_date': expire_elem.text
            })

    return completion_info
