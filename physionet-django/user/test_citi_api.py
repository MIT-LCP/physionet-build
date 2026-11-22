import datetime
import unittest
from unittest.mock import patch

import requests
import requests_mock

from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from user import citi_training_module as citi
from user.citi_training_module import (
    CITICompletionResult,
    CITILookupResult,
    find_matching_completion,
    get_auto_approval_failures,
    lookup_citi_completions_for_user,
    normalize_name,
    parse_completions_xml,
    parse_member_profile_xml,
    verify_training_via_citi_api,
)
from user.enums import RequiredField, TrainingStatus
from user.models import (
    CITIGroupMapping,
    CITIVerification,
    Profile,
    Question,
    Training,
    TrainingQuestion,
    TrainingType,
    User,
)

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
                        <strLastII>Smith</strLastII>
                        <strFirstII>John</strFirstII>
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


fake_xml_bad_credentials = """<?xml version="1.0" encoding="utf-8"?>
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
                    <xs:element name="NewDataSet" msdata:IsDataSet="true"
                        msdata:UseCurrentLocale="true">
                        <xs:complexType>
                            <xs:choice minOccurs="0" maxOccurs="unbounded" />
                        </xs:complexType>
                    </xs:element>
                </xs:schema>
                <diffgr:diffgram
                    xmlns:msdata="urn:schemas-microsoft-com:xml-msdata"
                    xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1" />
            </GetInstMemberByEmailResult>
        </GetInstMemberByEmailResponse>
    </soap:Body>
</soap:Envelope>"""

fake_xml_no_member = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope
    xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <GetInstMemberByEmailResponse
            xmlns="https://webservices.citiprogram.org/">
            <GetInstMemberByEmailResult>
                <diffgr:diffgram
                    xmlns:msdata="urn:schemas-microsoft-com:xml-msdata"
                    xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
                    <NewDataSet xmlns="" />
                </diffgr:diffgram>
            </GetInstMemberByEmailResult>
        </GetInstMemberByEmailResponse>
    </soap:Body>
</soap:Envelope>"""


@requests_mock.Mocker()
class TestUtils(unittest.TestCase):
    """Test cases for CITI SOAP API functions."""
    def test_function_memberid(self, mocker):
        mocker.register_uri('POST', soap_request_url, text=fake_xml_memberid, additional_matcher=match_member_email)
        memberid = citi.get_memberid('tester@mit.edu')
        self.assertEqual(memberid, '12102652')

    def test_get_member_profile(self, mocker):
        mocker.register_uri('POST', soap_request_url, text=fake_xml_memberid, additional_matcher=match_member_email)
        profile, raw_xml = citi.get_member_profile('tester@mit.edu')
        self.assertIsNotNone(profile)
        self.assertEqual(profile['intMemberID'], '12102652')
        self.assertEqual(profile['strFirstII'], 'John')
        self.assertEqual(profile['strLastII'], 'Smith')
        self.assertEqual(profile['strUsernameII'], 'fakeusername')
        self.assertEqual(profile['strInstEmail'], 'tester@mit.edu')
        self.assertEqual(raw_xml, fake_xml_memberid)

    def test_get_member_profile_not_found(self, mocker):
        mocker.register_uri('POST', soap_request_url, text=fake_xml_no_member, additional_matcher=match_member_email)
        profile, raw_xml = citi.get_member_profile('unknown@example.com')
        self.assertIsNone(profile)
        self.assertEqual(raw_xml, fake_xml_no_member)

    def test_get_member_profile_bad_credentials(self, mocker):
        """Bad credentials return the same empty response as 'member not found'."""
        mocker.register_uri('POST', soap_request_url, text=fake_xml_bad_credentials,
                            additional_matcher=match_member_email)
        profile, raw_xml = citi.get_member_profile('test@example.com')
        self.assertIsNone(profile)
        self.assertEqual(raw_xml, fake_xml_bad_credentials)

    def test_get_memberid_not_found(self, mocker):
        mocker.register_uri('POST', soap_request_url, text=fake_xml_no_member, additional_matcher=match_member_email)
        memberid = citi.get_memberid('unknown@example.com')
        self.assertIsNone(memberid)

    def test_function_courseinfo(self, mocker):
        mocker.register_uri('POST', soap_request_url, text=fake_xml_memberid, additional_matcher=match_member_email)
        mocker.register_uri('POST', soap_request_url, text=fake_xml_courseinfo,
                            additional_matcher=match_member_courseinfo)
        result = citi.get_citiprogram_completion('tester@mit.edu')
        self.assertEqual(result.member_id, '12102652')
        self.assertEqual(result.member_profile['strFirstII'], 'John')
        self.assertEqual(result.member_profile['strLastII'], 'Smith')
        self.assertEqual(result.member_profile['strInstEmail'], 'tester@mit.edu')
        self.assertEqual(result.member_profile_xml, fake_xml_memberid)
        self.assertEqual(result.completions_xml, fake_xml_courseinfo)
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
        self.assertEqual(result.completions, list_courses)


def make_completion(group_id='43007', group_name='Data or Specimens Only Research',
                    expiration=None, member_id='12345', completion_report_id='99999'):
    if expiration is None:
        expiration = timezone.now() + datetime.timedelta(days=365)
    passed = timezone.now() - datetime.timedelta(days=30)
    return {
        'FirstName': 'Test',
        'LastName': 'User',
        'MemberID': member_id,
        'memberEmail': 'test@example.com',
        'strCompletionReport': 'Human Research',
        'intGroupID': str(group_id),
        'strGroup': group_name,
        'intStageID': '106240',
        'intStageNumber': '1',
        'strStage': 'Basic Course',
        'intCompletionReportID': completion_report_id,
        'intMemberStageID': '555',
        'dtePassed': passed,
        'intScore': '95',
        'intPassingScore': '80',
        'dteExpiration': expiration,
    }


class TestFindMatchingCompletion(TestCase):
    TEST_GROUP_ID = 99901

    @classmethod
    def setUpTestData(cls):
        cls.training_type = TrainingType.objects.create(
            name='CITI Test',
            valid_duration=datetime.timedelta(days=365),
            required_field=RequiredField.DOCUMENT,
        )
        cls.mapping = CITIGroupMapping.objects.create(
            citi_group_id=cls.TEST_GROUP_ID,
            training_type=cls.training_type,
            citi_group_name='Test Group',
        )

    def test_match_found(self):
        completions = [make_completion(group_id=str(self.TEST_GROUP_ID))]
        result = find_matching_completion(completions, self.training_type)
        self.assertIsNotNone(result)
        self.assertEqual(result['intGroupID'], str(self.TEST_GROUP_ID))

    def test_no_match_wrong_group(self):
        completions = [make_completion(group_id='88888')]
        result = find_matching_completion(completions, self.training_type)
        self.assertIsNone(result)

    def test_no_match_expired(self):
        expired = timezone.now() - datetime.timedelta(days=1)
        completions = [make_completion(group_id=str(self.TEST_GROUP_ID), expiration=expired)]
        result = find_matching_completion(completions, self.training_type)
        self.assertIsNone(result)

    def test_picks_latest_expiration(self):
        earlier = timezone.now() + datetime.timedelta(days=100)
        later = timezone.now() + datetime.timedelta(days=500)
        completions = [
            make_completion(group_id=str(self.TEST_GROUP_ID), expiration=earlier, completion_report_id='1'),
            make_completion(group_id=str(self.TEST_GROUP_ID), expiration=later, completion_report_id='2'),
        ]
        result = find_matching_completion(completions, self.training_type)
        self.assertEqual(result['intCompletionReportID'], '2')

    def test_no_mapping_configured(self):
        other_type = TrainingType.objects.create(
            name='Other',
            valid_duration=datetime.timedelta(days=365),
            required_field=RequiredField.DOCUMENT,
        )
        completions = [make_completion(group_id=str(self.TEST_GROUP_ID))]
        result = find_matching_completion(completions, other_type)
        self.assertIsNone(result)


class TestLookupCITICompletionsForUser(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username='citiuser', email='citiuser@example.com', is_active=True)
        Profile.objects.create(user=cls.user, first_names='Test', last_name='User')

    @patch('user.citi_training_module.get_citiprogram_completion')
    def test_success(self, mock_get):
        completions = [make_completion()]
        mock_get.return_value = CITICompletionResult(
            completions=completions, member_id='12345',
            member_profile={'strFirstII': 'Test', 'strLastII': 'User'},
            member_profile_xml='<member_xml/>', completions_xml='<completions_xml/>',
        )

        result = lookup_citi_completions_for_user(self.user)
        self.assertEqual(result.email_used, 'citiuser@example.com')
        self.assertEqual(len(result.completions), 1)
        self.assertEqual(result.member_id, '12345')
        self.assertEqual(result.member_profile_xml, '<member_xml/>')
        self.assertEqual(result.completions_xml, '<completions_xml/>')
        self.assertIsNone(result.error)

    @patch('user.citi_training_module.get_citiprogram_completion')
    def test_no_completions(self, mock_get):
        mock_get.return_value = CITICompletionResult()

        result = lookup_citi_completions_for_user(self.user)
        self.assertIsNone(result.email_used)
        self.assertEqual(result.completions, [])
        self.assertIn('No CITI training records found', result.error)

    @patch('user.citi_training_module.get_citiprogram_completion')
    def test_api_error(self, mock_get):
        mock_get.side_effect = requests.RequestException('Connection timeout')

        result = lookup_citi_completions_for_user(self.user)
        self.assertIsNone(result.email_used)
        self.assertIn('Error communicating with CITI API', result.error)

    def test_no_verified_emails(self):
        user2 = User.objects.create(username='noemails', email='noemails@example.com')
        Profile.objects.create(user=user2, first_names='No', last_name='Emails')

        result = lookup_citi_completions_for_user(user2)
        self.assertIsNone(result.email_used)
        self.assertIn('No verified emails', result.error)


class TestParseMemberProfileXml(TestCase):
    def test_parses_valid_xml(self):
        result = parse_member_profile_xml(fake_xml_memberid)
        self.assertIsNotNone(result)
        self.assertEqual(result['intMemberID'], '12102652')
        self.assertEqual(result['strFirstII'], 'John')
        self.assertEqual(result['strLastII'], 'Smith')
        self.assertEqual(result['strInstEmail'], 'tester@mit.edu')

    def test_returns_none_for_empty_string(self):
        self.assertIsNone(parse_member_profile_xml(''))

    def test_returns_none_for_no_member(self):
        self.assertIsNone(parse_member_profile_xml(fake_xml_no_member))

    def test_returns_none_for_invalid_xml(self):
        self.assertIsNone(parse_member_profile_xml('not xml'))


class TestParseCompletionsXml(TestCase):
    def test_parses_valid_xml(self):
        result = parse_completions_xml(fake_xml_courseinfo)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['MemberID'], '12102652')
        self.assertEqual(result[0]['intGroupID'], '43007')
        self.assertEqual(result[0]['strGroup'], 'Data or Specimens Only Research')
        self.assertEqual(result[0]['intScore'], '95')
        # Dates are returned as strings in the parsing helpers
        self.assertIsInstance(result[0]['dtePassed'], str)

    def test_returns_empty_for_empty_string(self):
        self.assertEqual(parse_completions_xml(''), [])

    def test_returns_empty_for_invalid_xml(self):
        self.assertEqual(parse_completions_xml('not xml'), [])


@override_settings(CITI_USERNAME='testuser', CITI_PASSWORD='testpass', CITI_SOAP_URL='https://test.citiprogram.org')
class TestVerifyTrainingViaCITIAPI(TestCase):
    TEST_GROUP_ID = 99902

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username='verifyuser', email='verifyuser@example.com', is_active=True)
        Profile.objects.create(user=cls.user, first_names='Verify', last_name='User')
        cls.training_type = TrainingType.objects.create(
            name='CITI Verify Test',
            valid_duration=datetime.timedelta(days=365),
            required_field=RequiredField.DOCUMENT,
        )
        CITIGroupMapping.objects.create(
            citi_group_id=cls.TEST_GROUP_ID,
            training_type=cls.training_type,
            citi_group_name='Test Verify Group',
        )

    @patch('user.citi_training_module.lookup_citi_completions_for_user')
    def test_populates_fields_on_success(self, mock_lookup):

        completion = make_completion(
            group_id=str(self.TEST_GROUP_ID),
            completion_report_id='77777',
        )
        member_profile = {'strFirstII': 'Verify', 'strLastII': 'User', 'strmemberEmail': 'verifyuser@example.com'}
        mock_lookup.return_value = CITILookupResult(
            email_used='verifyuser@example.com', completions=[completion],
            member_id='12345', member_profile=member_profile,
            member_profile_xml=fake_xml_memberid, completions_xml=fake_xml_courseinfo,
        )

        training = Training.objects.create(
            training_type=self.training_type,
            user=self.user,
            status=TrainingStatus.REVIEW,
        )
        verify_training_via_citi_api(training)

        verification = CITIVerification.objects.get(training=training)
        self.assertEqual(verification.lookup_email, 'verifyuser@example.com')
        self.assertEqual(verification.member_id, '12345')
        self.assertEqual(verification.completion_report_id, '77777')
        self.assertEqual(verification.member_profile_xml, fake_xml_memberid)
        self.assertEqual(verification.completions_xml, fake_xml_courseinfo)
        self.assertEqual(verification.api_error, '')

    @patch('user.citi_training_module.lookup_citi_completions_for_user')
    def test_stores_error_on_failure(self, mock_lookup):

        mock_lookup.return_value = CITILookupResult(
            error='No CITI training records found for any of your verified emails.',
        )

        training = Training.objects.create(
            training_type=self.training_type,
            user=self.user,
            status=TrainingStatus.REVIEW,
        )
        verify_training_via_citi_api(training)

        verification = CITIVerification.objects.get(training=training)
        self.assertIn('No CITI training records found', verification.api_error)
        self.assertEqual(verification.member_profile_xml, '')
        self.assertEqual(verification.completions_xml, '')

    @patch('user.citi_training_module.lookup_citi_completions_for_user')
    def test_handles_api_exception(self, mock_lookup):
        mock_lookup.side_effect = requests.RequestException('Connection timeout')

        training = Training.objects.create(
            training_type=self.training_type,
            user=self.user,
            status=TrainingStatus.REVIEW,
        )
        verify_training_via_citi_api(training)

        verification = CITIVerification.objects.get(training=training)
        self.assertIn('Connection timeout', verification.api_error)

    def test_skips_non_citi_training_types(self):

        other_type = TrainingType.objects.create(
            name='Non-CITI',
            valid_duration=datetime.timedelta(days=365),
            required_field=RequiredField.DOCUMENT,
        )
        training = Training.objects.create(
            training_type=other_type,
            user=self.user,
            status=TrainingStatus.REVIEW,
        )
        # Should return without making any API calls or creating a verification
        verify_training_via_citi_api(training)

        self.assertFalse(CITIVerification.objects.filter(training=training).exists())

    @patch('user.citi_training_module.lookup_citi_completions_for_user')
    def test_skips_when_citi_not_configured(self, mock_lookup):
        training = Training.objects.create(
            training_type=self.training_type,
            user=self.user,
            status=TrainingStatus.REVIEW,
        )
        with self.settings(CITI_USERNAME='', CITI_PASSWORD='pass', CITI_SOAP_URL='http://example.com'):
            verify_training_via_citi_api(training)
        mock_lookup.assert_not_called()
        self.assertFalse(CITIVerification.objects.filter(training=training).exists())


class TestTrainingProcessCITIRendering(TestCase):
    """Smoke tests that training_process.html renders for each CITI card state."""

    TEST_GROUP_ID = 99903

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_admin(
            username='citiadmin', email='citiadmin@example.com', password='Tester11!',
        )
        cls.user = User.objects.create(
            username='citirenduser', email='citirenduser@example.com', is_active=True,
        )
        Profile.objects.create(user=cls.user, first_names='Render', last_name='User')

        cls.training_type = TrainingType.objects.create(
            name='CITI Render Test',
            valid_duration=datetime.timedelta(days=365),
            required_field=RequiredField.DOCUMENT,
        )
        question = Question.objects.create(content='Test question?')
        cls.training_type.questions.add(question)

        CITIGroupMapping.objects.create(
            citi_group_id=cls.TEST_GROUP_ID,
            training_type=cls.training_type,
            citi_group_name='Test Render Group',
        )

    def _create_training(self, verification_kwargs=None):
        training = Training.objects.create(
            training_type=self.training_type,
            user=self.user,
            status=TrainingStatus.REVIEW,
        )
        question = self.training_type.questions.first()
        TrainingQuestion.objects.create(training=training, question=question)
        if verification_kwargs is not None:
            CITIVerification.objects.create(training=training, **verification_kwargs)
        return training

    def test_renders_with_citi_api_data(self):
        training = self._create_training(verification_kwargs={
            'lookup_email': 'citirenduser@example.com',
            'member_id': '12345',
            'completion_report_id': '77777',
            'member_profile_xml': fake_xml_memberid,
            'completions_xml': fake_xml_courseinfo,
        })
        self.client.force_login(self.admin)
        url = reverse('training_process', kwargs={'pk': training.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CITI API Verification')
        self.assertContains(response, 'citirenduser@example.com')
        self.assertContains(response, '12345')

    def test_renders_with_citi_error(self):
        training = self._create_training(verification_kwargs={
            'api_error': 'Error communicating with CITI API. Please try again later.',
        })
        self.client.force_login(self.admin)
        url = reverse('training_process', kwargs={'pk': training.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CITI API Verification')
        self.assertContains(response, 'Error communicating with CITI API')

    def test_renders_with_no_citi_data(self):
        training = self._create_training()
        self.client.force_login(self.admin)
        url = reverse('training_process', kwargs={'pk': training.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CITI API Verification')
        self.assertContains(response, 'No CITI API data available')

    def test_citi_email_still_verified_true(self):
        training = self._create_training(verification_kwargs={
            'lookup_email': 'citirenduser@example.com',
            'member_id': '12345',
            'completions_xml': fake_xml_courseinfo,
        })
        self.client.force_login(self.admin)
        url = reverse('training_process', kwargs={'pk': training.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Email no longer verified on account')

    def test_citi_email_no_longer_verified(self):
        training = self._create_training(verification_kwargs={
            'lookup_email': 'removed@example.com',
            'member_id': '12345',
            'completions_xml': fake_xml_courseinfo,
        })
        self.client.force_login(self.admin)
        url = reverse('training_process', kwargs={'pk': training.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email no longer verified on account')


class TestNormalizeName(unittest.TestCase):
    def test_ignores_case_accents_and_punctuation(self):
        self.assertEqual(normalize_name("  José  O'Brien-Smith "), 'jose o brien smith')
        self.assertEqual(normalize_name('JOSE O BRIEN SMITH'), 'jose o brien smith')

    def test_handles_empty_values(self):
        self.assertEqual(normalize_name(None), '')
        self.assertEqual(normalize_name(''), '')


@override_settings(CITI_USERNAME='testuser', CITI_PASSWORD='testpass', CITI_SOAP_URL='https://test.citiprogram.org')
class TestCITIAutoApproval(TestCase):
    TEST_GROUP_ID = 99904

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username='autouser', email='autouser@example.com', is_active=True)
        Profile.objects.create(user=cls.user, first_names='Test', last_name='User')
        cls.training_type = TrainingType.objects.create(
            name='CITI Auto Test',
            valid_duration=datetime.timedelta(days=365 * 3),
            required_field=RequiredField.DOCUMENT,
        )
        CITIGroupMapping.objects.create(
            citi_group_id=cls.TEST_GROUP_ID,
            training_type=cls.training_type,
            citi_group_name='Test Auto Group',
        )

    def _create_training(self):
        return Training.objects.create(
            training_type=self.training_type,
            user=self.user,
            status=TrainingStatus.REVIEW,
        )

    def _completion(self, **overrides):
        completion = make_completion(group_id=str(self.TEST_GROUP_ID))
        completion.update(overrides)
        return completion

    def _lookup_result(self, completion, member_profile=None):
        return CITILookupResult(
            email_used='autouser@example.com', completions=[completion],
            member_id='12345', member_profile=member_profile or self._member_profile(),
            member_profile_xml=fake_xml_memberid, completions_xml=fake_xml_courseinfo,
        )

    def _member_profile(self, first='Test', last='User'):
        return {'intMemberID': '12345', 'strFirstII': first, 'strLastII': last}

    def _failures(self, training, completion=None, member_profile=None):
        if completion is None:
            completion = self._completion()
        if member_profile is None:
            member_profile = self._member_profile()
        return get_auto_approval_failures(training, completion, member_profile)

    # Eligibility checks

    def test_clear_case_is_eligible(self):
        training = self._create_training()
        self.assertEqual(self._failures(training), [])

    def test_name_matching_ignores_case_and_accents(self):
        training = self._create_training()
        self.assertEqual(self._failures(training, member_profile=self._member_profile('TÉST', 'user')), [])

    def test_name_mismatch_not_eligible(self):
        training = self._create_training()
        failures = self._failures(training, member_profile=self._member_profile(last='Other'))
        self.assertEqual(len(failures), 1)
        self.assertIn('does not match profile', failures[0])

    def test_partial_first_name_not_eligible(self):
        training = self._create_training()
        failures = self._failures(training, member_profile=self._member_profile(first='Test Middle'))
        self.assertIn('does not match profile', failures[0])

    def test_missing_member_profile_not_eligible(self):
        training = self._create_training()
        failures = get_auto_approval_failures(training, self._completion(), None)
        self.assertIn('does not match profile', failures[0])

    def test_member_profile_name_mismatch_not_eligible(self):
        # A matching name on the completion record is not enough on its own.
        training = self._create_training()
        failures = self._failures(training, member_profile=self._member_profile('Someone', 'Else'))
        self.assertEqual(len(failures), 1)
        self.assertIn('CITI member profile', failures[0])

    def test_completion_record_name_mismatch_not_eligible(self):
        # A matching name on the member profile is not enough on its own.
        training = self._create_training()
        completion = self._completion(FirstName='Other', LastName='Name')
        failures = self._failures(training, completion=completion)
        self.assertEqual(len(failures), 1)
        self.assertIn('CITI completion record', failures[0])

    def test_completion_record_name_matching_ignores_case_and_accents(self):
        training = self._create_training()
        completion = self._completion(FirstName='TÉST', LastName='USER')
        self.assertEqual(self._failures(training, completion=completion), [])

    def test_failing_score_not_eligible(self):
        training = self._create_training()
        failures = self._failures(training, self._completion(intScore='79'))
        self.assertIn('below the passing score', failures[0])

    def test_unreadable_score_not_eligible(self):
        training = self._create_training()
        failures = self._failures(training, self._completion(intScore=''))
        self.assertIn('could not be read', failures[0])

    def test_zero_passing_score_not_eligible(self):
        training = self._create_training()
        failures = self._failures(training, self._completion(intPassingScore='0'))
        self.assertIn('below the passing score', failures[0])

    def test_completed_before_validity_period_not_eligible(self):
        training = self._create_training()
        passed = timezone.now() - datetime.timedelta(days=365 * 3 + 1)
        failures = self._failures(training, self._completion(dtePassed=passed))
        self.assertIn('validity period', failures[0])

    def test_no_completion_not_eligible(self):
        training = self._create_training()
        failures = get_auto_approval_failures(training, None, self._member_profile())
        self.assertIn('No unexpired CITI completion', failures[0])

    # End-to-end via verify_training_via_citi_api

    @override_settings(CITI_AUTO_APPROVE=True)
    @patch('user.citi_training_module.lookup_citi_completions_for_user')
    def test_clear_case_is_approved(self, mock_lookup):
        mock_lookup.return_value = self._lookup_result(self._completion())
        training = self._create_training()

        verify_training_via_citi_api(training)

        training.refresh_from_db()
        verification = training.citi_verification
        self.assertEqual(training.status, TrainingStatus.ACCEPTED)
        self.assertIsNone(training.reviewer)
        self.assertIsNotNone(training.process_datetime)
        self.assertTrue(verification.auto_approved)
        self.assertEqual(verification.auto_approval_notes, '')
        self.assertIsNotNone(verification.auto_approval_checked_datetime)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)

    @override_settings(CITI_AUTO_APPROVE=True)
    @patch('user.citi_training_module.lookup_citi_completions_for_user')
    def test_unclear_case_left_for_review(self, mock_lookup):
        mock_lookup.return_value = self._lookup_result(
            self._completion(), member_profile=self._member_profile(last='Other'),
        )
        training = self._create_training()

        verify_training_via_citi_api(training)

        training.refresh_from_db()
        verification = training.citi_verification
        self.assertEqual(training.status, TrainingStatus.REVIEW)
        self.assertFalse(verification.auto_approved)
        self.assertIn('does not match profile', verification.auto_approval_notes)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(CITI_AUTO_APPROVE=False)
    @patch('user.citi_training_module.lookup_citi_completions_for_user')
    def test_disabled_records_eligibility_without_approving(self, mock_lookup):
        mock_lookup.return_value = self._lookup_result(self._completion())
        training = self._create_training()

        verify_training_via_citi_api(training)

        training.refresh_from_db()
        verification = training.citi_verification
        self.assertEqual(training.status, TrainingStatus.REVIEW)
        self.assertFalse(verification.auto_approved)
        self.assertEqual(verification.auto_approval_notes, '')
        self.assertIsNotNone(verification.auto_approval_checked_datetime)

    @override_settings(CITI_AUTO_APPROVE=True)
    @patch('user.citi_training_module.lookup_citi_completions_for_user')
    def test_withdrawn_training_not_approved(self, mock_lookup):
        mock_lookup.return_value = self._lookup_result(self._completion())
        training = self._create_training()
        # Simulate the user withdrawing after the background task loaded the training.
        Training.objects.filter(pk=training.pk).update(status=TrainingStatus.WITHDRAWN)

        verify_training_via_citi_api(training)

        training.refresh_from_db()
        self.assertEqual(training.status, TrainingStatus.WITHDRAWN)
        self.assertFalse(training.citi_verification.auto_approved)

    @override_settings(CITI_AUTO_APPROVE=True)
    @patch('user.citi_training_module.lookup_citi_completions_for_user')
    def test_api_error_left_for_review(self, mock_lookup):
        mock_lookup.return_value = CITILookupResult(error='Error communicating with CITI API.')
        training = self._create_training()

        verify_training_via_citi_api(training)

        training.refresh_from_db()
        self.assertEqual(training.status, TrainingStatus.REVIEW)
        self.assertIsNone(training.citi_verification.auto_approval_checked_datetime)


class TestTrainingConsoleAutoApprovalRendering(TestCase):
    TEST_GROUP_ID = 99905

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_admin(
            username='autoadmin', email='autoadmin@example.com', password='Tester11!',
        )
        cls.user = User.objects.create(username='autorend', email='autorend@example.com', is_active=True)
        Profile.objects.create(user=cls.user, first_names='Render', last_name='User')
        cls.training_type = TrainingType.objects.create(
            name='CITI Auto Render Test',
            valid_duration=datetime.timedelta(days=365),
            required_field=RequiredField.DOCUMENT,
        )
        CITIGroupMapping.objects.create(
            citi_group_id=cls.TEST_GROUP_ID, training_type=cls.training_type, citi_group_name='Group',
        )

    def _create_training(self, status=TrainingStatus.REVIEW, **verification_kwargs):
        training = Training.objects.create(training_type=self.training_type, user=self.user, status=status)
        CITIVerification.objects.create(
            training=training, lookup_email='autorend@example.com', member_id='12345',
            member_profile_xml=fake_xml_memberid, completions_xml=fake_xml_courseinfo,
            **verification_kwargs,
        )
        return training

    def test_process_page_shows_failures(self):
        training = self._create_training(
            auto_approval_checked_datetime=timezone.now(),
            auto_approval_notes='Name on CITI record (A B) does not match profile (Render User).',
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse('training_process', kwargs={'pk': training.pk}))
        self.assertContains(response, 'Not eligible for automatic approval')
        self.assertContains(response, 'does not match profile')

    @override_settings(CITI_AUTO_APPROVE=False)
    def test_process_page_shows_eligible_but_disabled(self):
        training = self._create_training(auto_approval_checked_datetime=timezone.now())
        self.client.force_login(self.admin)
        response = self.client.get(reverse('training_process', kwargs={'pk': training.pk}))
        self.assertContains(response, 'All automatic approval checks passed')
        self.assertContains(response, 'Automatic approval is currently disabled')

    def test_process_page_hides_section_when_not_checked(self):
        training = self._create_training()
        self.client.force_login(self.admin)
        response = self.client.get(reverse('training_process', kwargs={'pk': training.pk}))
        self.assertNotContains(response, 'Automatic Approval')

    def test_detail_page_shows_auto_approved(self):
        training = self._create_training(status=TrainingStatus.ACCEPTED, auto_approved=True)
        Training.objects.filter(pk=training.pk).update(process_datetime=timezone.now())
        self.client.force_login(self.admin)
        response = self.client.get(reverse('training_detail', kwargs={'pk': training.pk}))
        self.assertContains(response, 'Automatically approved using the CITI API')

    @override_settings(CITI_AUTO_APPROVE=False)
    def test_detail_page_shows_citi_data_after_processing(self):
        training = self._create_training(
            status=TrainingStatus.ACCEPTED,
            auto_approval_checked_datetime=timezone.now(),
        )
        Training.objects.filter(pk=training.pk).update(process_datetime=timezone.now())
        self.client.force_login(self.admin)
        response = self.client.get(reverse('training_detail', kwargs={'pk': training.pk}))
        self.assertContains(response, 'CITI API Verification')
        self.assertContains(response, 'autorend@example.com')
        self.assertContains(response, 'Data or Specimens Only Research')
        self.assertContains(response, 'All automatic approval checks passed')
        # The training has been processed, so it no longer needs manual review.
        self.assertNotContains(response, 'Automatic approval is currently disabled')

    def test_detail_page_shows_auto_approval_failures(self):
        training = self._create_training(
            status=TrainingStatus.REJECTED,
            auto_approval_checked_datetime=timezone.now(),
            auto_approval_notes='CITI score (50) is below the passing score (80).',
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse('training_detail', kwargs={'pk': training.pk}))
        self.assertContains(response, 'Not eligible for automatic approval')
        self.assertContains(response, 'below the passing score')
