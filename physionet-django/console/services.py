import logging
import re
from typing import Optional

from pdfminer.high_level import extract_text

from user.models import Training

logging.getLogger("pdfminer").setLevel(logging.WARNING)


def _get_regex_value_from_text(text: str, regex: str) -> str:
    result = None
    try:
        regex = re.compile(regex)
        result = regex.search(text)
        if len(result.groups()) >= 1:
            result = regex.search(text).group(1)
    except Exception:
        pass
    return result


def _parse_certificate(training: Training) -> dict:
    text = _parse_pdf_to_string(training.completion_report.path)
    result2 = {}
    for regex in training.training_type.certificate_regexes.all():
        result2[regex.name] = _get_regex_value_from_text(text, regex.regex)
    return result2


def _parse_pdf_to_string(training_path: str) -> str:
    text = extract_text(training_path)
    return ' '.join(text.split())


def get_info_from_certificate_pdf(training: Training) -> dict:
    return _parse_certificate(training)
