from django import template

register = template.Library()

# The dictionary item filter
@register.filter
def dict_item(dictionary, key):
    return dictionary.get(key)