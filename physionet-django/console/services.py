import logging
import re
from typing import Optional

from pdfminer.high_level import extract_text

from user.models import Training

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
    text = extract_text(training_path)
    return ' '.join(text.split())


def get_info_from_certificate_pdf(training: Training) -> dict:
    text = _parse_pdf_to_string(training.completion_report.path)
    regexes = training.training_type.certificate_regexes.all()
    return {regex.name: _get_regex_value_from_text(text, regex.regex) for regex in regexes}
