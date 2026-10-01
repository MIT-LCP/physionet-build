from django import template
from django.utils.html import format_html
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
def startswith(value, prefix):
    """Return True if the string value starts with the given prefix."""
    if not prefix:
        return False
    return str(value).startswith(str(prefix))


@register.filter
def default_tag(value, html_tag='span'):
    """
    If the value is a plain text string, enclose it in HTML tags.
    If the value is a safe string, keep the existing HTML formatting.
    """
    if hasattr(value, '__html__'):
        return value
    return format_html('<{1}>{0}</{1}>', value, html_tag)
