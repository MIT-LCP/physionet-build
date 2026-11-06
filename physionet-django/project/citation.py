"""
Look up the formatted citation for a DOI, using DOI content negotiation
(https://citation.crosscite.org/docs.html). This works for DOIs
registered with Crossref and DataCite, which covers most articles and
datasets.
"""
import html
import logging
from urllib.parse import quote

import requests
from django.utils.html import strip_tags

LOGGER = logging.getLogger(__name__)

DOI_RESOLVER_URL = 'https://doi.org/'
CITATION_CONTENT_TYPE = 'text/x-bibliography'
TIMEOUT = 15


class CitationLookupError(Exception):
    """A citation could not be found for a DOI. The message is shown to the user."""


def clean_citation(text):
    """
    Return a citation as a single line of plain text.
    """
    return ' '.join(strip_tags(html.unescape(text)).split())


def fetch_citation(doi, style='apa'):
    """
    Return the citation for a DOI, formatted in the given CSL style.

    Raises CitationLookupError if the DOI does not exist, or no citation
    is available for it.
    """
    try:
        response = requests.get(
            DOI_RESOLVER_URL + quote(doi, safe='/:;()'),
            headers={'Accept': '{}; style={}; locale=en-US'.format(CITATION_CONTENT_TYPE, style)},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        LOGGER.warning('Citation lookup failed for DOI %s', doi, exc_info=True)
        raise CitationLookupError('Could not reach doi.org. Please try again later.')

    if response.status_code == 404:
        raise CitationLookupError('This DOI was not found.')
    content_type = response.headers.get('Content-Type', '')
    if response.status_code != 200 or not content_type.startswith(CITATION_CONTENT_TYPE):
        # Some registration agencies do not support content negotiation,
        # and redirect to the landing page instead.
        raise CitationLookupError(
            'No citation is available for this DOI. Please enter it by hand.')

    # The content type often omits the charset, but the text is UTF-8.
    response.encoding = 'utf-8'
    citation = clean_citation(response.text)
    if not citation:
        raise CitationLookupError(
            'No citation is available for this DOI. Please enter it by hand.')
    return citation
