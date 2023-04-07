# Import the necessary libraries
import requests
import xml.etree.ElementTree as ET
from django.conf import settings
from django.template import loader

def send_request(xml_payload):
    # Define the headers 
    headers = {
        'Content-Type': 'text/xml; charset=utf-8'
    }
 
    #URL for the request
    soap_request_url=settings.CITI_SOAP_URL

    # Send the POST request and get the response
    response = requests.request("POST", soap_request_url, headers=headers, data=xml_payload)

    # parse the XML response into an ElementTree object
    root = ET.fromstring(response.text)
    
    return root

def get_memberid(email):
    # Get username and password from Django settings
    username = settings.CITI_USERNAME
    password = settings.CITI_PASSWORD

    # get the member ID using email
    payload = loader.render_to_string(
        'user/citi/get_inst_member_by_email.xml', {
            'username': username,
            'password': password,
            'email': email,
        }
    )
    
    root=send_request(xml_payload=payload)

    # get the member ID
    memberid = root.find('.//intMemberID').text

    return memberid


def get_citiprogram_completion(email):
    # Get username and password from Django settings
    username = settings.CITI_USERNAME
    password = settings.CITI_PASSWORD
    memberid=get_memberid(email)
    
    # get the member courses using the member ID
    payload_courses =loader.render_to_string(
            'user/citi/get_courses_by_member.xml', {
                'username': username,
                'password': password,
                'memberid': memberid,
            }
        )

    # parse the XML response for the member courses
    root_courses = send_request(xml_payload=payload_courses)

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