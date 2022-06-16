import io
import logging
import re
from typing import Optional

from pdfminer.high_level import extract_text
from pdfminer.pdfparser import PDFSyntaxError
from django.conf import settings

from user.models import Training
from physionet.settings.base import StorageTypes


logging.getLogger("pdfminer").setLevel(logging.WARNING)


def _get_regex_value_from_text(text: str, regex: str) -> Optional[str]:
    regex = re.compile(regex)
    match = regex.search(text)
    if match is None:
        return None
    if match.groups():
        # The parsed value consists of combined groups if the regex defines capture groups.
        # This is done to enable matching on surrounding text without including it in the extracted value.
        return ' '.join(match.groups())
    return match.group(0)


def _parse_pdf_to_string(training_path: str) -> str:
    try:
        text = extract_text(training_path)
    except PDFSyntaxError:
        text = ''
        logging.error(f'Failed to extract text from {training_path}')
    return ' '.join(text.split())


def get_info_from_certificate_pdf(training: Training) -> dict:
    if settings.STORAGE_TYPE == StorageTypes.GCP:
        report_path_or_io = io.BytesIO(training.completion_report.read())
    else:
        report_path_or_io = training.completion_report.path

    text = _parse_pdf_to_string(report_path_or_io)
    regexes = training.training_type.certificate_regexes.all().order_by('display_order')
    return {
        regex.name: _get_regex_value_from_text(text, regex.regex)
        for regex in regexes
    }
