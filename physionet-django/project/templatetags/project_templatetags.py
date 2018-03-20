from django import template

from project.models import Metadata


register = template.Library()

@register.filter(name='resource_icon')
def resource_icon(project):

    icons = {
        'Database': '<i class="fa fa-database"></i>',
        'Software': '<i class="fa fa-keyboard"></i>',
        'Tutorial': '<i class="fa fa-database"></i>',
        'Challenge': '<i class="fa fa-database"></i>',
    }

    return icons[project.resource_type]
