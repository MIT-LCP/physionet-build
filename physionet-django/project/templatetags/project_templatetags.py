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

@register.filter(name='author_name')
def author_name(author):
    """
    Full name from author object
    """
    return author.get_full_name()

@register.filter(name='author_affiliations')
def author_affiliations(author):
    """
    A displayable list of author affiliations
    """
    affiliations = author.affiliations.all()

    return ', '.join([a.name for a in affiliations])
