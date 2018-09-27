from django import template


register = template.Library()


@register.filter(name='resource_badge')
def resource_badge(resource_type):
    badges = {
        0: '<span class="badge badge-dark"><i class="fa fa-database"></i> Database</span>',
        1: '<span class="badge badge-dark"><i class="fa fa-keyboard"></i> Software</span>',
    }
    return badges[resource_type]

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
def access_badge(access_policy):
    badges = {
        0: '<span class="badge badge-success"><i class="fas fa-lock-open"></i> Open Access</span>',
        1: '<span class="badge badge-warning"><i class="fas fa-unlock-alt"></i> Restricted Access</span>',
        2: '<span class="badge badge-danger"><i class="fas fa-lock"></i> Credentialed Access</span>',
    }
    return badges[access_policy]

@register.filter(name='access_description')
def access_description(access_policy):
    descriptions = {
        0: 'Anyone can access the files, as long as they conform to the terms of the specified license.',
        1: 'Only logged in users who sign the specified data use agreement can access the files.',
        2: 'Only PhysioNet credentialed users who sign the specified DUA can access the files.',
    }
    return descriptions[access_policy]

@register.filter(name='mb_to_gb')
def mb_to_gb(storage_allowance):
    """
    Convert storage allowance mb to a readable gb value
    """
    return '{:.2f}'.format(storage_allowance / 1024)
