"""
In-text citations in a project's description.

While a project is edited, authors cite references by key, such as
[@moody2001] or [@moody2001; @mark1997]. The preview shows these as
numbers, such as [1] or [1, 2], with the references listed in the order
they are first cited. When the project is published, the citations are
saved as those numbers, so published descriptions contain numbered
citations, which are linked to the reference list when displayed. When
a new version is created, the numbers are turned back into keys.

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


def _link(number, references):
    """
    Return a link to item number of the reference list, or the number
    alone if there is no such item.
    """
    if not 1 <= number <= len(references):
        return str(number)
    # The title shows the citation when hovering over the link
    title = escape(str(references[number - 1]))
    return '<a href="#ref-{0}" class="citation-link" title="{1}">{0}</a>'.format(number, title)


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


def _link_numbers(document, references):
    def replace(match):
        citation = match.group(0)
        if citation_numbers(citation) is None:
            return citation
        # Link each number, keeping the brackets, commas and dashes
        return ITEM_REGEX.sub(
            lambda m: _link(int(m.group(1)), references) + (
                m.group(2) + _link(int(m.group(3)), references) if m.group(3) else ''),
            citation)

    return _process(document, CITATION_REGEX, replace)


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


def order_references(documents, references):
    """
    Return a project's references in the order they are first cited in
    its description (a list of HTML fragments), followed by those that
    are not cited, in their original order.
    """
    references = list(references)
    by_key = {r.key.lower(): r for r in references if r.key}
    ordered = []
    for document in documents:
        for key in find_cited_keys(document):
            reference = by_key.get(key)
            if reference is not None and reference not in ordered:
                ordered.append(reference)
    return ordered + [r for r in references if r not in ordered]


def _format_numbers(numbers, format_number=str):
    """
    Return a list of citation numbers as text, e.g. '1, 3–5', with runs
    of three or more numbers shown as a range.
    """
    numbers = sorted(set(numbers))
    parts = []
    start = 0
    while start < len(numbers):
        end = start
        while end + 1 < len(numbers) and numbers[end + 1] == numbers[end] + 1:
            end += 1
        if end - start >= 2:
            parts.append(format_number(numbers[start]) + '–' + format_number(numbers[end]))
            start = end + 1
        else:
            parts.append(format_number(numbers[start]))
            start += 1
    return ', '.join(parts)


def number_key_citations(document, references, link=False):
    """
    Return an HTML fragment with its key citations, such as
    [@moody2001; @mark1997], replaced by the references' numbers in the
    list, such as [1, 2]. If link is true, the numbers are linked to the
    list.

    references is the list of references, in display order. Citations
    of keys that are not in the list are left unchanged.
    """
    references = list(references)
    numbers = {r.key.lower(): n for n, r in enumerate(references, start=1) if r.key}

    def replace(match):
        keys = [key.lower() for key in KEY_ITEM_REGEX.findall(match.group(0))]
        if any(key not in numbers for key in keys):
            return match.group(0)
        if link:
            text = _format_numbers((numbers[key] for key in keys), lambda n: _link(n, references))
        else:
            text = _format_numbers(numbers[key] for key in keys)
        return '[' + text + ']'

    return _process(document, KEY_CITATION_REGEX, replace)


def key_numbered_citations(document, references):
    """
    Return an HTML fragment with its numbered citations, such as [1, 2],
    replaced by the keys of those items in the reference list, such as
    [@moody2001; @mark1997].

    This is the reverse of number_key_citations, used when a published
    description becomes editable again. Citations of numbers that are
    not in the list, or of references without a key, are left unchanged.
    """
    references = list(references)

    def replace(match):
        numbers = citation_numbers(match.group(0))
        if not numbers or any(n > len(references) or not references[n - 1].key for n in numbers):
            return match.group(0)
        keys = []
        for n in numbers:
            if references[n - 1].key not in keys:
                keys.append(references[n - 1].key)
        return '[' + '; '.join('@' + key for key in keys) + ']'

    return _process(document, CITATION_REGEX, replace)


def link_citations(document, references):
    """
    Return an HTML fragment with its citations linked to the reference
    list, whose items have the IDs 'ref-1', 'ref-2', and so on.

    Key citations, such as [@moody2001], are shown as numbers. Numbered
    citations, such as [1], are linked as they are.

    references is the list of references, in display order. Numbers and
    keys that are not in the list are not linked.
    """
    references = list(references)
    if not references:
        return document
    document = number_key_citations(document, references, link=True)
    return _link_numbers(document, references)


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

    Errors are citations of keys that no reference has, which would be
    published as they are. Warnings are references that are not cited,
    and numbered citations such as [1], which should be keys.
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
