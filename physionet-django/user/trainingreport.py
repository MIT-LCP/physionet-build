import re

# Regular expression matching a training report URL.
# Currently (April 2020), it appears that CITI training reports
# always use a verification code beginning with 'k', whereas
# certificates use a verification code beginning with 'w'.
TRAINING_REPORT_URL = r'https://www\.citiprogram\.org/verify/\?k[\w-]+'

# Regular expression matching a training certificate URL.
TRAINING_CERTIFICATE_URL = r'https://www\.citiprogram\.org/verify/\?w[\w-]+'


def find_training_report_url(file):
    """
    Search for a recognized reference URL in a training report file.

    Training reports may include a link to the training organization's
    website, allowing someone to verify the report's authenticity.
    This function searches for such a URL in the input file.
    Currently, this will work for PDF training reports from
    citiprogram.org.

    file must be either be a binary file object, or a
    django.core.files.uploadfile.UploadedFile.

    If a training verification URL is found in the file, that URL is
    returned.

    CITI also issues "completion certificates" which have a similar
    format (including a verification link) but do not include details
    of the course completed.  If a "certificate" URL is found, but no
    "report" URL, then a TrainingCertificateError is raised.

    If neither a training report nor a training certificate URL is
    found, None is returned.
    """

    if hasattr(file, 'chunks'):         # UploadedFile
        chunks = file.chunks()
    else:                               # binary file object
        chunks = file_chunks(file)

    # Currently (April 2020), CITI training reports/certificates are
    # written as PDF 1.4 and the URL is written as a PostScript-style
    # string, so no more sophisticated parsing is needed.
    url_pattern = re.compile(rb'/URI\s*\(([^()\\]+)\)')

    report_pattern = re.compile(TRAINING_REPORT_URL.encode())
    certificate_pattern = re.compile(TRAINING_CERTIFICATE_URL.encode())

    certificate_url = None
    buf = b''
    for chunk in chunks:
        buf += chunk
        for match in url_pattern.finditer(buf):
            url = match.group(1)
            if report_pattern.fullmatch(url):
                return url.decode()
            elif certificate_pattern.fullmatch(url):
                certificate_url = url
        buf = buf[-512:]

    if certificate_url is not None:
        raise TrainingCertificateError()


def file_chunks(file, size=4096):
    """
    Iterate over a file object as a sequence of chunks.
    """
    data = file.read(size)
    while data:
        yield data
        data = file.read(size)


class TrainingCertificateError(Exception):
    """Exception raised if the file is a training certificate."""
    pass
