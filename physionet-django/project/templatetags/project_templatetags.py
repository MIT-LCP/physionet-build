from django import template

register = template.Library()

@register.filter(name='resource_icon')
def resource_icon(project):

    icons = {'Database': '<i class="fa fa-database"></i>',
        'Software': '<i class="fa fa-keyboard"></i>'}

    return icons[project.resource_type.description]
