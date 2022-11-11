from django import template

register = template.Library()

@register.filter
def underscore(str_var):
    str_under = str_var.replace(' ', '_')
    return str_under
