from django import template
from django.utils.html import strip_tags
import re
import html
from physionet.models import StaticPage

register = template.Library()


@register.simple_tag
def get_static_page():
    static_page_obj = StaticPage.objects.all().order_by('nav_order')
    return static_page_obj


@register.filter
def underscore(str_var):
    str_under = str_var.replace(' ', '_')
    return str_under


@register.filter
def news_preview(content, max_length=200):
    """
    Filter to create a preview of news content for the front page.
    Removes images, strips HTML tags, and truncates.
    """
    if not content:
        return ""

    # Remove img tags and their content
    content = re.sub(r'<img[^>]*>', '', content)

    # Strip all HTML tags
    text_content = strip_tags(content)

    # Decode HTML entities
    text_content = html.unescape(text_content)

    # Remove extra whitespace
    text_content = re.sub(r'\s+', ' ', text_content).strip()

    # Truncate to max_length
    if len(text_content) > max_length:
        text_content = text_content[:max_length].rsplit(' ', 1)[0] + '...'

    return text_content
