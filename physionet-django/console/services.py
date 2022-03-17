import logging
import re
from typing import Optional

from pdfminer.high_level import extract_text

from user.enums import TrainingCertificateType

logging.getLogger("pdfminer").setLevel(logging.WARNING)


TCPS_USERNAME_REGEX = r'(?<=certifies that )(.*?)(?= successfully)'
TCPS_FULL_NAME_REGEX = r'(?<=completed the )(.*?)(?= Certificate)'
TCPS_SHORT_NAME_REGEX = r'(?=\()(.*?)(?<=\))'
TCPS_ID_AND_DATE = r'(?<=Certificate # )(.*)'

CITI_USERNAME_REGEX = r'(?<=Name: )(.*?)(?= \()'
CITI_INSITUTION_REGEX = r'(?<=Institution Affiliation: )(.*?)(?= \()'
CITI_EMAIL_REGEX = r'^(.*?)(?= • Institution Email:)'
CITI_CERT_INFO_REGEX = r'(?<=Reported Score\*: )(.*)(?= REQUIRED )'
CITI_FULL_NAME_REGEX = r'^(.*?)(\(CITI PROGRAM)\)'
CITI_SHORT_NAME_REGEX = r'(?=\()(.*)(?<=\))'

OCAP_USERNAME_REGEX = r'(?<=Achievement to )(.*?)(?= upon the)'
OCAP_CERT_NAME_REGEX = r'(?<=completion of )(.*?)(?<= OCAP)'
OCAP_DATE_REGEX = r'(?<=Signed at )(.*)'


def _get_regex_value_from_text(text: str, regex: str) -> str:
    result = None
    try:
        regex = re.compile(regex)
        result = regex.search(text).group()
    except Exception:
        pass
    return result


def _parse_ocap_certificate(text: str) -> dict:
    result = {
        'username': _get_regex_value_from_text(text, OCAP_USERNAME_REGEX),
        'date': _get_regex_value_from_text(text, OCAP_DATE_REGEX),
        'shortname': _get_regex_value_from_text(text, OCAP_CERT_NAME_REGEX),
    }
    return result


def _parse_citi_certificate(text: str) -> dict:
    full_name = _get_regex_value_from_text(text, CITI_FULL_NAME_REGEX)
    short_name = _get_regex_value_from_text(full_name, CITI_SHORT_NAME_REGEX)
    result = {
        'username': _get_regex_value_from_text(text, CITI_USERNAME_REGEX),
        'email': _get_regex_value_from_text(text, CITI_EMAIL_REGEX).split(' ')[-1],
        'institution': _get_regex_value_from_text(text, CITI_INSITUTION_REGEX),
        'date': _get_regex_value_from_text(text, CITI_CERT_INFO_REGEX).split()[1],
        'expiration_date': _get_regex_value_from_text(text, CITI_CERT_INFO_REGEX).split()[2],
        'reported_score': _get_regex_value_from_text(text, CITI_CERT_INFO_REGEX).split()[4] + '%',
        'shortname': short_name[1:-1],
        'fullname': full_name.replace(short_name, ''),
    }
    return result


def _parse_tcps_certificate(text: str) -> dict:
    id_and_date = _get_regex_value_from_text(text, TCPS_ID_AND_DATE).split()
    full_name = _get_regex_value_from_text(text, TCPS_FULL_NAME_REGEX)
    short_name = _get_regex_value_from_text(full_name, TCPS_SHORT_NAME_REGEX)
    result = {
        'username': _get_regex_value_from_text(text, TCPS_USERNAME_REGEX),
        'certificate_id': id_and_date[0],
        'date': ' '.join(id_and_date[1:]),
        'shortname': short_name[1:-1],
        'fullname': full_name.replace(short_name, ''),
    }
    return result


def _get_certificate_type(text: str) -> Optional[TrainingCertificateType]:
    # TODO it's buggy - what if something will
    #  change and CITI cert will have "TCPS" or someone's name contains some type :/
    if TrainingCertificateType.TCPS.value in text:
        return TrainingCertificateType.TCPS
    if TrainingCertificateType.CITI.value in text:
        return TrainingCertificateType.CITI
    if TrainingCertificateType.OCAP.value in text:
        return TrainingCertificateType.OCAP
    return None


def _parse_pdf_to_string(training_path: str) -> str:
    text = extract_text(training_path)
    # maybe we should not 'join' the text so we can use \n in regexes (?)
    return ' '.join(text.split())


def get_info_from_certificate_pdf(training_path: str) -> dict:
    text = _parse_pdf_to_string(training_path)
    certificate_type = _get_certificate_type(text)
    if certificate_type is TrainingCertificateType.TCPS:
        return _parse_tcps_certificate(text)
    if certificate_type is TrainingCertificateType.CITI:
        return _parse_citi_certificate(text)
    if certificate_type is TrainingCertificateType.OCAP:
        return _parse_ocap_certificate(text)
    return {
        'unknown_cert_type': True
    }
