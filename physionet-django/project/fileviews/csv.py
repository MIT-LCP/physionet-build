import csv

import chardet

from project.fileviews.base import FileView, GzippedFileView
from project.fileviews.text import probably_binary

MAX_ROWS = 500
MAX_COLUMNS = 50
MAX_BYTES = 512 * 1024


class CSVFileView(FileView):
    """
    Class for displaying comma-separated tables.

    The file contents will be displayed as an HTML table.  Large files
    (more than 50 columns, 500 rows, or 512 kilobytes in total) will
    be truncated to avoid overloading the browser.

    The character encoding is heuristically determined by the chardet
    library.  Format variations are heuristically determined by the
    csv library.
    """

    def render(self, request, delimiters=[',']):
        # Read an initial chunk of the file and check if it looks binary
        text = self.file.read(16384)
        if probably_binary(text) or b'\n' not in text:
            return super().render(request)

        detector = chardet.UniversalDetector()
        detector.feed(text)

        # Decode initial text as Latin-1 and try to detect format
        text = text.decode('ISO-8859-1')
        s = csv.Sniffer()
        try:
            dialect = s.sniff(text, delimiters=delimiters)
            has_header = s.has_header(text)
        except csv.Error:
            dialect = None
            has_header = False

        # Read lines from input, stopping after reading at most MAX_BYTES
        def wrapper(file, text):
            limit = MAX_BYTES - len(text)
            while text:
                lines = text.split('\n')
                text = lines.pop()
                yield from lines
                ntext = file.read(4096)
                limit -= len(ntext)
                if limit < 0:
                    raise SizeLimitExceeded()
                if not ntext and text:
                    yield text
                    raise MissingNewline()
                detector.feed(ntext)
                text += ntext.decode('ISO-8859-1')

        # Read data and parse at most MAX_ROWS
        truncated_rows = None
        truncated_columns = None
        missing_newline = False
        rows = []
        try:
            reader = csv.reader(wrapper(self.file, text), dialect=dialect)
            for row in reader:
                if len(rows) >= MAX_ROWS:
                    raise SizeLimitExceeded()
                if len(row) > MAX_COLUMNS:
                    truncated_columns = MAX_COLUMNS
                    row = row[0:MAX_COLUMNS]
                rows.append(row)
        except SizeLimitExceeded:
            truncated_rows = len(rows)
        except MissingNewline:
            missing_newline = True

        # Try to guess encoding
        detector.close()
        encoding = detector.result['encoding']
        if not encoding or not rows:
            return super().render(request)

        # If encoding is not Latin-1, recode the parsed strings
        if encoding.upper() not in ('ISO-8859-1', 'ASCII'):
            rows = ((v.encode('ISO-8859-1').decode(encoding) for v in r)
                    for r in rows)

        rows = iter(rows)
        if has_header:
            header_row = next(rows)
        else:
            header_row = None

        return super().render(request, 'project/file_view_csv.html',
                              header_row=header_row,
                              data_rows=rows,
                              missing_newline=missing_newline,
                              truncated_rows=truncated_rows,
                              truncated_columns=truncated_columns)


class GzippedCSVFileView(GzippedFileView, CSVFileView):
    pass


class SizeLimitExceeded(Exception):
    pass


class MissingNewline(Exception):
    pass
