from django import template


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

@register.filter(name='access_badge')
def access_badge(project):
    badges = {
        0: '<span class="badge badge-success"><i class="fas fa-lock-open"></i> Open Access</span>',
        1: '<span class="badge badge-warning"><i class="fas fa-unlock-alt"></i> Restricted Access</span>',
        2: '<span class="badge badge-danger"><i class="fas fa-lock"></i> Credentialed Access</span>',
    }
    return badges[project.access_policy]

@register.filter(name='access_description')
def access_description(project):
    descriptions = {
        0: 'Anyone can access the files, as long as they conform to the terms of the specified license.',
        1: 'Only logged in users who sign the specified data use agreement can access the files.',
        2: 'Only PhysioNet credentialed users who sign the specified DUA can access the files.',
    }
    return descriptions[project.access_policy]
