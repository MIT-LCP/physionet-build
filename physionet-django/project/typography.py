import re


_apostrophe_trailing = re.compile(r"([^\s\(\[])'")
_doublequote_trailing = re.compile(r'([^\s\(\[])"')
_multiple_hyphens = re.compile(r'--+')
_spaced_hyphen = re.compile(r'(\s)-(\s)')


def autocorrect_punctuation(value):
    """
    Replace ASCII punctuation in a string with Unicode punctuation.

    This will attempt to guess which punctuation mark is appropriate,
    and make substitutions:
    - ASCII apostrophe (') is replaced with ‘ or ’
    - ASCII quotation mark (") is replaced with “ or ”
    - ASCII hyphen-minus (-) is replaced with – if appropriate

    In cases where a hyphen is appropriate, the ASCII hyphen-minus is
    left alone.  The two characters (- and ‐) are identical in most
    fonts, and changing hyphen-minus to hyphen could cause confusion
    and compatibility problems for little benefit.

    Note that this function only works for plain text (not HTML.)
    """

    # Replace ' with right single quote except after a space or open-paren.
    value = _apostrophe_trailing.sub(r"\1’", value)
    # Replace other ' with left double quote.
    value = value.replace("'", "‘")

    # Replace " with right double quote except after a space or open-paren.
    value = _doublequote_trailing.sub(r'\1”', value)
    # Replace other " with left double quote.
    value = value.replace('"', '”')

    # Replace multiple - with en dash.
    value = _multiple_hyphens.sub("–", value)
    # Replace spaced - with en dash.
    value = _spaced_hyphen.sub(r"\1–\2", value)
    # Other - are left alone.

    return value
