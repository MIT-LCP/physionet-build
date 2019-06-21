import chardet

from project.fileviews.base import FileView

MAX_SIZE = 1024 * 1024


class TextFileView(FileView):
    """
    Class for displaying plain text files.

    This class is the default view for unknown file types.

    The character encoding is heuristically determined by the chardet
    library.

    The file contents will be displayed inline if:
    - it is at most 1 MB in size
    - it "mostly" consists of ASCII or UTF-8 text
    - it uses character encoding that chardet recognizes
    """

    def render(self, request):
        text = self.file.read(4096)
        if probably_binary(text):
            return super().render(request, show_plain=False)

        if self.size() > MAX_SIZE:
            return super().render(request)

        text += self.file.read()
        encoding = chardet.detect(text)['encoding']
        if encoding:
            text = text.decode(encoding, errors='replace')
        else:
            return super().render(request)

        if text[-1] == '\n':
            text = text[:-1]
            if text[-1] == '\r':
                text = text[:-1]
            missing_newline = False
        else:
            missing_newline = True

        return super().render(request, 'project/file_view_text.html',
                              text=text, missing_newline=missing_newline)


# ascii control characters excluding \t, \n, \r
_control_chars = bytes(range(0, 9)) + b'\f\v' + bytes(range(14, 32)) + b'\177'
_eight_bit = bytes(range(128, 256))


def probably_binary(text):
    # binary if more than 1% control characters
    printable = text.translate(None, _control_chars)
    n = len(text)
    if len(printable) < n - (n // 100):
        return True

    # text if valid UTF-8
    try:
        text.decode()
        return False
    except UnicodeDecodeError as e:
        if e.end == n:
            return False

    # binary if more than 25% eight-bit characters
    sevenbit = text.translate(None, _eight_bit)
    return (len(sevenbit) < n - (n // 4))
