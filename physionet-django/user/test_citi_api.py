import unittest
import requests_mock

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
                    <NewDataSet
                        xmlns="">
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

soap_request_url = settings.CITI_SOAP_URL


@requests_mock.Mocker()
class TestUtils(unittest.TestCase):
    """Test cases for TestUtils."""

    def test_function_memberid(self, mocker):
        """
        Test the function get_memberid.
        """
        mocker.register_uri('POST', soap_request_url, text=fake_xml_memberid)
        memberid = citi.get_memberid('tester@mit.edu')
        self.assertEqual(memberid, '12102652')
