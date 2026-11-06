"""
In-text citations in a project's description.

Authors cite references by key, such as [@moody2001] or
[@moody2001; @mark1997]. The citations are saved and published as they
are written. When a description is displayed, each cited key is linked
to its reference in the list.

Descriptions written before keys were introduced may cite references by
number, such as [1]. These are left as they are, and a warning asks
authors to cite by key instead.

Only plain text is affected: citations inside links, code, maths,
scripts and styles are left alone. A numbered citation must not follow
a letter, digit or ")" (as in "x[1]"), and its numbers must be no more
than MAX_CITATION_NUMBER (so "[2019]" is not a citation).
"""
import html.parser
import re
import unicodedata

from django.utils.html import escape

from project.validators import CITATION_YEAR_REGEX, REFERENCE_KEY_PATTERN, URL_IN_TEXT_REGEX

MAX_CITATION_NUMBER = 999

# The longest range written as "[a-b]" that is treated as a citation
MAX_CITATION_RANGE = 100

# Elements whose text never contains citations
SKIPPED_TAGS = {'a', 'code', 'pre', 'math', 'script', 'style'}

# A reference number (up to MAX_CITATION_NUMBER), and a number or range
# of numbers. Ranges use a hyphen or an en dash, which may be written as
# an HTML entity.
_NUMBER = r'[1-9]\d{0,2}'
_DASH = r'\s*(?:-|\u2013|&ndash;|&#8211;|&#x2013;)\s*'
_ITEM = _NUMBER + '(?:' + _DASH + _NUMBER + ')?'
CITATION_REGEX = re.compile(r'(?<![\w)])\[\s*' + _ITEM + r'(?:\s*,\s*' + _ITEM + r')*\s*\]')
ITEM_REGEX = re.compile('(' + _NUMBER + ')(?:(' + _DASH + ')(' + _NUMBER + '))?')


def citation_numbers(citation):
    """
    Return the reference numbers in a citation such as '[1, 3-5]', or
    None if it does not look like a citation.
    """
    numbers = []
    for match in ITEM_REGEX.finditer(citation):
        start = int(match.group(1))
        end = int(match.group(3) or start)
        if end < start or end - start > MAX_CITATION_RANGE:
            return None
        numbers.extend(range(start, end + 1))
    return numbers


class _CitationParser(html.parser.HTMLParser):
    """
    Copy an HTML fragment, passing the text that may contain citations
    to handle_text.

    The text is passed as it is written in the source (with entities
    such as "&amp;" unchanged), one run of text between tags at a time.
    """
    def __init__(self, handle_text):
        super().__init__(convert_charrefs=False)
        self.handle_text = handle_text
        self.result = []
        self.text = []
        self.skip_depth = 0

    def flush(self):
        text = ''.join(self.text)
        self.text = []
        if self.skip_depth:
            self.result.append(text)
        else:
            self.result.append(self.handle_text(text))

    def markup(self, markup):
        self.flush()
        self.result.append(markup)

    def handle_starttag(self, tag, attrs):
        self.markup(self.get_starttag_text())
        if tag in SKIPPED_TAGS:
            self.skip_depth += 1

    def handle_startendtag(self, tag, attrs):
        self.markup(self.get_starttag_text())

    def handle_endtag(self, tag):
        self.markup('</' + tag + '>')
        if tag in SKIPPED_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        self.text.append(data)

    def handle_entityref(self, name):
        self.text.append('&' + name + ';')

    def handle_charref(self, name):
        self.text.append('&#' + name + ';')

    def handle_comment(self, data):
        self.markup('<!--' + data + '-->')

    def handle_decl(self, decl):
        self.markup('<!' + decl + '>')

    def handle_pi(self, data):
        self.markup('<?' + data + '>')

    def unknown_decl(self, data):
        self.markup('<![' + data + ']>')

    def close(self):
        super().close()
        self.flush()


def _process(document, regex, replace):
    """
    Apply replace(match) to each match of regex in the text of an HTML
    fragment, and return the result.
    """
    def handle_text(text):
        return regex.sub(replace, text)

    parser = _CitationParser(handle_text)
    parser.feed(document or '')
    parser.close()
    return ''.join(parser.result)


def _link(key, number, reference):
    """
    Return a link to a cited key's item in the reference list.
    """
    # The title shows the citation when hovering over the link
    return '<a href="#ref-{0}" class="citation-link" title="{1}">@{2}</a>'.format(
        number, escape(str(reference)), key)


def _join(items):
    """
    Return a list of items as text, e.g. '3, 4 and 6'.
    """
    items = [str(item) for item in items]
    if len(items) == 1:
        return items[0]
    return ', '.join(items[:-1]) + ' and ' + items[-1]


# Numbered citations, such as [1] or [2, 4-6]

def find_citations(document):
    """
    Return the set of reference numbers cited in an HTML fragment.
    """
    cited = set()

    def replace(match):
        cited.update(citation_numbers(match.group(0)) or [])
        return match.group(0)

    _process(document, CITATION_REGEX, replace)
    return cited


# Citations by key, such as [@moody2001] or [@moody2001; @mark1997]

KEY_PATTERN = REFERENCE_KEY_PATTERN
KEY_CITATION_REGEX = re.compile(
    r'\[\s*@' + KEY_PATTERN + r'(?:\s*[;,]\s*@' + KEY_PATTERN + r')*\s*\]')
KEY_ITEM_REGEX = re.compile('@(' + KEY_PATTERN + ')')


def find_cited_keys(document):
    """
    Return the keys cited in an HTML fragment, in lower case, in the
    order they are first cited.
    """
    keys = []

    def replace(match):
        for key in KEY_ITEM_REGEX.findall(match.group(0)):
            if key.lower() not in keys:
                keys.append(key.lower())
        return match.group(0)

    _process(document, KEY_CITATION_REGEX, replace)
    return keys


def link_citations(document, references):
    """
    Return an HTML fragment with each key in its citations, such as
    [@moody2001; @mark1997], linked to the reference list, whose items
    have the IDs 'ref-1', 'ref-2', and so on.

    references is the list of references, in display order. Keys that
    are not in the list are not linked.
    """
    references = list(references)
    numbers = {r.key.lower(): n for n, r in enumerate(references, start=1) if r.key}
    if not numbers:
        return document

    def link_key(match):
        key = match.group(1)
        number = numbers.get(key.lower())
        if number is None:
            return match.group(0)
        return _link(key, number, references[number - 1])

    def replace(match):
        # Link each key, keeping the brackets and separators
        return KEY_ITEM_REGEX.sub(link_key, match.group(0))

    return _process(document, KEY_CITATION_REGEX, replace)


# Keys for new references

# Letters that Unicode normalization does not reduce to ASCII
_LETTERS = str.maketrans({
    'ø': 'o', 'Ø': 'O', 'æ': 'ae', 'Æ': 'Ae', 'œ': 'oe', 'Œ': 'Oe', 'ß': 'ss',
    'ł': 'l', 'Ł': 'L', 'đ': 'd', 'Đ': 'D', 'ð': 'd', 'Ð': 'D', 'þ': 'th', 'Þ': 'Th',
})


def suggest_key(description, taken=()):
    """
    Return a key for a reference, made from the first author's surname
    and the year in its citation (e.g. 'moody2001'), that is not one of
    the keys in taken (compared in lower case). A letter is added if
    needed (e.g. 'moody2001b').
    """
    text = URL_IN_TEXT_REGEX.sub(' ', description or '')
    # The first author's surname comes before the first comma or full stop
    surname = re.split(r'[,.(]', text.strip(), maxsplit=1)[0]
    # Drop initials written after the surname, as in 'Moody GB'
    surname = re.sub(r'\s+[A-Z]{1,3}$', '', surname.strip())
    surname = surname.translate(_LETTERS)
    surname = unicodedata.normalize('NFKD', surname).encode('ascii', 'ignore').decode()
    surname = re.sub(r'[^a-z0-9]', '', surname.lower())[:30]
    year = CITATION_YEAR_REGEX.search(text)
    year = re.sub(r'[^a-z0-9]', '', year.group(0).lower()) if year else ''
    base = (surname + year) or 'ref'
    if not base[0].isalnum():
        base = 'ref' + base

    taken = {key.lower() for key in taken}
    if base not in taken:
        return base
    for suffix in 'bcdefghijklmnopqrstuvwxyz':
        if base + suffix not in taken:
            return base + suffix
    number = 2
    while '{}{}'.format(base, number) in taken:
        number += 1
    return '{}{}'.format(base, number)


# Checks before submission

def citation_problems(documents, references):
    """
    Return (errors, warnings) about the citations in a project's
    description, given its HTML sections and its references.

    Errors are citations of keys that no reference has. Warnings are
    references that are not cited, and numbered citations such as [1],
    which should be keys.
    """
    documents = [document for document in documents if document]
    references = list(references)
    keys = {r.key.lower() for r in references if r.key}

    cited = []
    for document in documents:
        cited += [key for key in find_cited_keys(document) if key not in cited]
    numbered = any(find_citations(document) for document in documents)

    errors, warnings = [], []
    unknown = ['@' + key for key in cited if key not in keys]
    if len(unknown) == 1:
        errors.append('The description cites {}, but no reference has that key.'.format(unknown[0]))
    elif unknown:
        errors.append('The description cites {}, but no references have those keys.'.format(_join(unknown)))

    example = '[@{}]'.format(references[0].key if references and references[0].key else 'moody2001')
    if numbered:
        warnings.append('The description uses numbered citations such as [1]. Cite references '
                        'by key instead, for example {}.'.format(example))
    elif references and not cited:
        warnings.append('The references are not cited in the description. Cite them by key, '
                        'for example {}.'.format(example))
    elif references:
        uncited = ['@' + r.key for r in references if r.key and r.key.lower() not in cited]
        if len(uncited) == 1:
            warnings.append('Reference {} is not cited in the description.'.format(uncited[0]))
        elif uncited:
            warnings.append('References {} are not cited in the description.'.format(_join(uncited)))
    return errors, warnings
