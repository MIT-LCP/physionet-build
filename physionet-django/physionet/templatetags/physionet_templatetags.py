from django import template
from physionet.models import StaticPage

register = template.Library()

@register.simple_tag
def get_static_page():
    static_page_obj = StaticPage.objects.all()
    return static_page_obj