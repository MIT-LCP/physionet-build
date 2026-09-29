import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

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

    # Convert to plain text (strip any HTML) then escape for safe output
    text = str(text)

    # Split search terms the same way the search view does
    terms = [t.strip() for t in re.split(r'[\s;,]+', search_term) if t.strip()]
    if not terms:
        return text

    # Escape the text first so we're working with safe HTML
    escaped = escape(text)

    # Build a single regex pattern matching any of the terms
    pattern = '|'.join(re.escape(term) for term in terms)
    highlighted = re.sub(
        f'({pattern})',
        r'<mark>\1</mark>',
        escaped,
        flags=re.IGNORECASE,
    )

    return mark_safe(highlighted)
