import html
import re

from django import template
from django.utils.html import escape, format_html, strip_tags
from django.utils.safestring import mark_safe

from search.views import split_search_terms

register = template.Library()


@register.filter(name='highlight')
def highlight(text, search_term):
    """
    Wrap occurrences of each search term in <mark> tags for highlighting.

    Handles HTML-safe text by escaping first, then inserting mark tags.
    Search terms are split on whitespace/punctuation to match individual words.
    Matching is case-insensitive.

    Usage: {{ project.title|highlight:search_term }}
    """
    if not search_term or not text:
        return text

    text = str(text)

    terms = split_search_terms(search_term)
    if not terms:
        return text

    # Match against the raw text, then escape each piece separately, so a
    # term can never match inside an HTML entity such as &amp; or &#x27;
    pattern = '|'.join(re.escape(term) for term in terms)
    parts = re.split(f'({pattern})', text, flags=re.IGNORECASE)
    return mark_safe(''.join(
        format_html('<mark>{}</mark>', part) if i % 2 else escape(part)
        for i, part in enumerate(parts)
    ))


@register.filter(name='html_to_text')
def html_to_text(value):
    """
    Strip HTML tags and decode HTML entities, returning plain text.

    Usage: {{ project.abstract|html_to_text|truncatechars:250 }}
    """
    return html.unescape(strip_tags(value))
