import unittest
import requests_mock
import datetime

from django.conf import settings

from user import citi_training_module as citi

fake_xml_memberid = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope
    xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <GetInstMemberByEmailResponse
            xmlns="https://webservices.citiprogram.org/">
            <GetInstMemberByEmailResult>
                <xs:schema id="NewDataSet"
                    xmlns=""
                    xmlns:xs="http://www.w3.org/2001/XMLSchema"
                    xmlns:msdata="urn:schemas-microsoft-com:xml-msdata">
                    <xs:element name="NewDataSet" msdata:IsDataSet="true" msdata:UseCurrentLocale="true">
                        <xs:complexType>
                            <xs:choice minOccurs="0" maxOccurs="unbounded">
                                <xs:element name="CRS">
                                    <xs:complexType>
                                        <xs:sequence>
                                            <xs:element name="intMemberID" type="xs:int" minOccurs="0" />
                                            <xs:element name="strLastII" type="xs:string" minOccurs="0" />
                                            <xs:element name="strFirstII" type="xs:string" minOccurs="0" />
                                            <xs:element name="strUsernameII" type="xs:string" minOccurs="0" />
                                            <xs:element name="strmemberEmail" type="xs:string" minOccurs="0" />
                                            <xs:element name="strInstUsername" type="xs:string" minOccurs="0" />
                                            <xs:element name="strInstEmail" type="xs:string" minOccurs="0" />
                                            <xs:element name="dteAdded" type="xs:string" minOccurs="0" />
                                            <xs:element name="dteAffiliated" type="xs:string" minOccurs="0" />
                                            <xs:element name="dteLastLogin" type="xs:string" minOccurs="0" />
                                            <xs:element name="strCustom1" type="xs:string" minOccurs="0" />
                                            <xs:element name="strCustom2" type="xs:string" minOccurs="0" />
                                            <xs:element name="strCustom3" type="xs:string" minOccurs="0" />
                                            <xs:element name="strCustom4" type="xs:string" minOccurs="0" />
                                            <xs:element name="strCustom5" type="xs:string" minOccurs="0" />
                                            <xs:element name="strSSOCustomAttrib1" type="xs:string" minOccurs="0" />
                                            <xs:element name="strSSOCustomAttrib2" type="xs:string" minOccurs="0" />
                                            <xs:element name="strEmployeeNum" type="xs:string" minOccurs="0" />
                                            <xs:element name="ORCIDiD" type="xs:string" minOccurs="0" />
                                        </xs:sequence>
                                    </xs:complexType>
                                </xs:element>
                            </xs:choice>
                        </xs:complexType>
                    </xs:element>
                </xs:schema>
                <diffgr:diffgram
                    xmlns:msdata="urn:schemas-microsoft-com:xml-msdata"
                    xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
                    <NewDataSet xmlns="">
                    <CRS diffgr:id="CRS1" msdata:rowOrder="0">
                        <intMemberID>12102652</intMemberID>
                        <strLastII>John</strLastII>
                        <strFirstII>Smith</strFirstII>
                        <strUsernameII>fakeusername</strUsernameII>
                        <strmemberEmail />
                        <strInstUsername />
                        <strInstEmail>tester@mit.edu</strInstEmail>
                        <dteAdded>03/12/23</dteAdded>
                        <dteAffiliated>03/13/23</dteAffiliated>
                        <dteLastLogin>03/13/23</dteLastLogin>
                        <strCustom1 />
                        <strCustom2 />
                        <strCustom3 />
                        <strCustom4 />
                        <strCustom5 />
                        <strEmployeeNum />
                    </CRS>
                    </NewDataSet>
                </diffgr:diffgram>
            </GetInstMemberByEmailResult>
            </GetInstMemberByEmailResponse>
    </soap:Body>
</soap:Envelope>"""

fake_xml_courseinfo = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope
    xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <GetMemberCoursesbyIDResponse
            xmlns="https://webservices.citiprogram.org/">
            <GetMemberCoursesbyIDResult>
                <xs:schema id="NewDataSet"
                    xmlns=""
                    xmlns:xs="http://www.w3.org/2001/XMLSchema"
                    xmlns:msdata="urn:schemas-microsoft-com:xml-msdata">
                    <xs:element name="NewDataSet" msdata:IsDataSet="true" msdata:UseCurrentLocale="true">
                        <xs:complexType>
                            <xs:choice minOccurs="0" maxOccurs="unbounded">
                                <xs:element name="CRSMEMBERID">
                                    <xs:complexType>
                                        <xs:sequence>
                                            <xs:element name="CR_InstitutionID" type="xs:int" minOccurs="0" />
                                            <xs:element name="MemberID" type="xs:int" minOccurs="0" />
                                            <xs:element name="EmplID" type="xs:string" minOccurs="0" />
                                            <xs:element name="StudentID" type="xs:string" minOccurs="0" />
                                            <xs:element name="InstitutionUserName" type="xs:string" minOccurs="0" />
                                            <xs:element name="FirstName" type="xs:string" minOccurs="0" />
                                            <xs:element name="LastName" type="xs:string" minOccurs="0" />
                                            <xs:element name="memberEmail" type="xs:string" minOccurs="0" />
                                            <xs:element name="AddedMember" type="xs:dateTime" minOccurs="0" />
                                            <xs:element name="strCompletionReport" type="xs:string" minOccurs="0" />
                                            <xs:element name="intGroupID" type="xs:int" minOccurs="0" />
                                            <xs:element name="strGroup" type="xs:string" minOccurs="0" />
                                            <xs:element name="intStageID" type="xs:int" minOccurs="0" />
                                            <xs:element name="intStageNumber" type="xs:int" minOccurs="0" />
                                            <xs:element name="strStage" type="xs:string" minOccurs="0" />
                                            <xs:element name="intCompletionReportID" type="xs:int" minOccurs="0" />
                                            <xs:element name="intMemberStageID" type="xs:int" minOccurs="0" />
                                            <xs:element name="dtePassed" type="xs:dateTime" minOccurs="0" />
                                            <xs:element name="intScore" type="xs:int" minOccurs="0" />
                                            <xs:element name="intPassingScore" type="xs:int" minOccurs="0" />
                                            <xs:element name="dteExpiration" type="xs:dateTime" minOccurs="0" />
                                        </xs:sequence>
                                    </xs:complexType>
                                </xs:element>
                            </xs:choice>
                        </xs:complexType>
                    </xs:element>
                </xs:schema>
                <diffgr:diffgram
                    xmlns:msdata="urn:schemas-microsoft-com:xml-msdata"
                    xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
                    <NewDataSet xmlns="">
                        <CRSMEMBERID diffgr:id="CRSMEMBERID1" msdata:rowOrder="0">
                        <CR_InstitutionID>1912</CR_InstitutionID>
                        <MemberID>12102652</MemberID>
                        <InstitutionUserName />
                        <FirstName>John</FirstName>
                        <LastName>Smith</LastName>
                        <memberEmail>tester@mit.edu</memberEmail>
                        <AddedMember>2023-03-12T23:25:15.747-04:00</AddedMember>
                        <strCompletionReport>Human Research</strCompletionReport>
                        <intGroupID>43007</intGroupID>
                        <strGroup>Data or Specimens Only Research</strGroup>
                        <intStageID>106240</intStageID>
                        <intStageNumber>1</intStageNumber>
                        <strStage>Basic Course</strStage>
                        <intCompletionReportID>34125</intCompletionReportID>
                        <intMemberStageID>54899005</intMemberStageID>
                        <dtePassed>2023-03-13T17:03:34.18-04:00</dtePassed>
                        <intScore>95</intScore>
                        <intPassingScore>90</intPassingScore>
                        <dteExpiration>2026-03-13T17:03:34.18-04:00</dteExpiration>
                        </CRSMEMBERID>
                    </NewDataSet>
                </diffgr:diffgram>
        </GetMemberCoursesbyIDResult>
        </GetMemberCoursesbyIDResponse>
    </soap:Body>
</soap:Envelope>"""

soap_request_url = settings.CITI_SOAP_URL


def match_member_email(request):
    """
    Matches the XML feature GetInstMemberByEmail for additional matcher callback
    """
    return ('<GetInstMemberByEmail' in request.text)


def match_member_courseinfo(request):
    """
    Matches the XML feature GetMemberCoursesbyID for additional matcher callback
    """
    return ('<GetMemberCoursesbyID' in request.text)


@requests_mock.Mocker()
class TestUtils(unittest.TestCase):
    """Test cases for TestUtils."""
    def test_function_memberid(self, mocker):
        """
        Test the function get_memberid.
        """
        mocker.register_uri('POST', soap_request_url, text=fake_xml_memberid, additional_matcher=match_member_email)
        memberid = citi.get_memberid('tester@mit.edu')
        self.assertEqual(memberid, '12102652')

    def test_function_courseinfo(self, mocker):
        """
        Test the function get_citiprogram_completion.
        """
        mocker.register_uri('POST', soap_request_url, text=fake_xml_memberid, additional_matcher=match_member_email)
        mocker.register_uri('POST', soap_request_url, text=fake_xml_courseinfo,
                            additional_matcher=match_member_courseinfo)
        course_info = citi.get_citiprogram_completion('tester@mit.edu')
        list_courses = [
            {
                'FirstName': 'John',
                'LastName': 'Smith',
                'MemberID': '12102652',
                'memberEmail': 'tester@mit.edu',
                'strCompletionReport': 'Human Research',
                'intGroupID': '43007',
                'strGroup': 'Data or Specimens Only Research',
                'intStageID': '106240',
                'intStageNumber': '1',
                'strStage': 'Basic Course',
                'intCompletionReportID': '34125',
                'intMemberStageID': '54899005',
                'dtePassed': datetime.datetime(
                    2023, 3, 13, 17, 3, 34, 180000,
                    tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=72000))
                ),
                'intScore': '95',
                'intPassingScore': '90',
                'dteExpiration': datetime.datetime(
                    2026, 3, 13, 17, 3, 34, 180000,
                    tzinfo=datetime.timezone(datetime.timedelta(days=-1, seconds=72000))
                )
            }
        ]
        self.assertEqual(course_info, list_courses)
