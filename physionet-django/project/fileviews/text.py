import chardet
from django.shortcuts import render

from project.fileviews.base import render_unknown

MAX_SIZE = 1024 * 1024


def render_text(request, infile, context):
    text = infile.read(4096)
    if probably_binary(text):
        return render_unknown(request, infile, context)

    if context['size'] > MAX_SIZE:
        return render_unknown(request, infile, context, show_plain=True)

    text += infile.read()
    encoding = chardet.detect(text)['encoding']
    if encoding:
        text = text.decode(encoding, errors='replace')
    else:
        return render_unknown(request, infile, context)

    if text[-1] == '\n':
        text = text[:-1]
        if text[-1] == '\r':
            text = text[:-1]
    else:
        context['missing_newline'] = True

    context['text'] = text
    return render(request, 'project/file_view_text.html', context)


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
