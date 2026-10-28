"""
Client for finding works that cite a project, using the OpenAlex API
(https://docs.openalex.org).
"""
import html
import logging
import re
from urllib.parse import quote

import requests
from django.conf import settings
from django.utils.dateparse import parse_date
from django.utils.html import strip_tags

LOGGER = logging.getLogger(__name__)

DOI_REGEX = re.compile(r'10\.\d{4,9}/[^\s"<>?#]+', re.IGNORECASE)

# Fields requested for each citing work
CITING_WORK_FIELDS = 'id,doi,display_name,publication_date,authorships,primary_location'

# Maximum number of results OpenAlex returns per page
PAGE_SIZE = 200

# Stop paging after this many citing works, as a guard against runaway
# requests. Far above the most-cited PhysioNet projects.
MAX_CITING_WORKS = 50000

# OpenAlex's limit on results reachable by page number (without an API key)
NO_KEY_MAX_RESULTS = 10000

# Number of author names stored before "et al."
MAX_AUTHORS = 3


def extract_doi(text):
    """
    Return the DOI in a string such as 'https://doi.org/10.1234/abc', in
    lower case, or None if there is none.
    """
    match = DOI_REGEX.search(text or '')
    if not match:
        return None
    return match.group(0).rstrip('.,;').lower()


def api_get(path, params=None):
    """
    Make a GET request to the OpenAlex API and return the JSON response.
    """
    params = dict(params or {})
    if settings.OPENALEX_API_KEY:
        params['api_key'] = settings.OPENALEX_API_KEY
    response = requests.get(f'{settings.OPENALEX_API_URL}/{path}', params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def short_id(openalex_url):
    """
    Return the short form of an OpenAlex ID, e.g. 'W123' for
    'https://openalex.org/W123'.
    """
    return openalex_url.rsplit('/', 1)[-1]


def find_work_ids(dois):
    """
    Return the set of OpenAlex work IDs for a list of DOIs.

    DOIs that OpenAlex does not know are skipped. Several DOIs may map
    to one work (OpenAlex merges the version DOIs of a dataset).
    """
    ids = set()
    for doi in sorted(set(dois)):
        try:
            work = api_get(f"works/doi:{quote(doi, safe='/')}", {'select': 'id'})
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                continue
            raise
        ids.add(short_id(work['id']))
    return ids


def iter_citing_works(work_ids):
    """
    Yield the OpenAlex records of works citing any of `work_ids`.

    OpenAlex only allows cursor paging with an API key. Without one,
    numbered pages are used, which OpenAlex limits to the first
    NO_KEY_MAX_RESULTS results.
    """
    params = {
        'filter': 'cites:' + '|'.join(sorted(work_ids)),
        'select': CITING_WORK_FIELDS,
        'per-page': PAGE_SIZE,
    }
    use_cursor = bool(settings.OPENALEX_API_KEY)
    max_results = MAX_CITING_WORKS if use_cursor else NO_KEY_MAX_RESULTS
    cursor = '*'
    page = 1
    count = 0
    while True:
        if use_cursor:
            params['cursor'] = cursor
        else:
            params['page'] = page
        data = api_get('works', params)
        results = data.get('results') or []
        for work in results:
            yield work
        count += len(results)
        cursor = data.get('meta', {}).get('next_cursor')
        page += 1
        if not results or (use_cursor and not cursor):
            return
        if count >= max_results:
            LOGGER.warning('Stopped fetching works citing %s after %d results', work_ids, count)
            return


def parse_work(work):
    """
    Convert an OpenAlex work record to CitingWork field values.
    """
    names = [
        a['author']['display_name']
        for a in work.get('authorships') or []
        if (a.get('author') or {}).get('display_name')
    ]
    authors = ', '.join(names[:MAX_AUTHORS])
    if len(names) > MAX_AUTHORS:
        authors += ' et al.'

    source = ((work.get('primary_location') or {}).get('source') or {})
    doi = extract_doi(work.get('doi')) or ''
    title = html.unescape(strip_tags(work.get('display_name') or '')).strip() or 'Untitled'

    return {
        'openalex_id': short_id(work['id']),
        'doi': doi[:255],
        'title': title[:1000],
        'authors': authors[:1000],
        'venue': (source.get('display_name') or '')[:500],
        'publication_date': parse_date(work.get('publication_date') or ''),
    }


def fetch_citing_works(dataset_dois, publication_dois):
    """
    Return the works citing a project, as a dict of CitingWork field
    values keyed by OpenAlex ID.

    `dataset_dois` are the project's own DOIs, and `publication_dois`
    the DOIs of its primary publication. Each work is flagged with
    which of the two it cites. The project's own works are excluded.
    """
    dataset_ids = find_work_ids(dataset_dois)
    publication_ids = find_work_ids(publication_dois) - dataset_ids
    own_ids = dataset_ids | publication_ids

    works = {}
    for target_ids, flag in ((dataset_ids, 'cites_dataset'),
                             (publication_ids, 'cites_publication')):
        if not target_ids:
            continue
        for record in iter_citing_works(target_ids):
            fields = parse_work(record)
            if fields['openalex_id'] in own_ids:
                continue
            work = works.setdefault(fields['openalex_id'], fields)
            work[flag] = True
    return works
