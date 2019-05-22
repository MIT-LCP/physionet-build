import csv
import gzip

import chardet
from django.shortcuts import render

from project.fileviews.base import render_unknown
from project.fileviews.text import probably_binary

MAX_ROWS = 500
MAX_BYTES = 512 * 1024


def render_csv(request, infile, context):
    return render_table(request, infile, context,
                        delimiters=[','])


def render_csv_gz(request, infile, context):
    context['show_plain'] = False
    try:
        with gzip.GzipFile(fileobj=infile, mode='rb') as csvdata:
            return render_table(request, csvdata, context,
                                delimiters=[','])
    except OSError:
        # not a gzip file, corrupted, etc.
        return render_unknown(request, infile, context)


def render_table(request, infile, context, delimiters):
    # Read an initial chunk of the file and check if it looks binary
    text = infile.read(16384)
    if probably_binary(text) or b'\n' not in text:
        return render_unknown(request, infile, context)

    detector = chardet.UniversalDetector()
    detector.feed(text)

    # Decode initial text as Latin-1 and try to detect format
    text = text.decode('ISO-8859-1')
    s = csv.Sniffer()
    dialect = s.sniff(text, delimiters=delimiters)
    has_header = s.has_header(text)

    # Read lines from input, stopping after reading at most MAX_BYTES
    def wrapper(infile, text):
        limit = MAX_BYTES - len(text)
        while text:
            lines = text.split('\n')
            text = lines.pop()
            yield from lines
            ntext = infile.read(4096)
            limit -= len(ntext)
            if limit < 0:
                raise SizeLimitExceeded()
            detector.feed(ntext)
            text += ntext.decode('ISO-8859-1')

    # Read data and parse at most MAX_ROWS
    rows = []
    try:
        reader = csv.reader(wrapper(infile, text), dialect=dialect)
        for row in reader:
            rows.append(row)
            if len(rows) >= MAX_ROWS:
                raise SizeLimitExceeded()
    except SizeLimitExceeded:
        context['truncated_rows'] = len(rows)

    # Try to guess encoding
    detector.close()
    encoding = detector.result['encoding']
    if not encoding or not rows:
        return render_unknown(request, infile, context)

    # If encoding is not Latin-1, recode the parsed strings
    if encoding.upper() not in ('ISO-8859-1', 'ASCII'):
        rows = ((v.encode('ISO-8859-1').decode(encoding) for v in r)
                for r in rows)

    rows = iter(rows)
    if has_header:
        context['header_row'] = next(rows)
    context['data_rows'] = rows

    return render(request, 'project/file_view_csv.html', context)


class SizeLimitExceeded(Exception):
    pass
