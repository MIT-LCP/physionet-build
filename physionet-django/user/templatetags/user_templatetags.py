from django import template


register = template.Library()


@register.inclusion_tag('user/settings_tabs.html')
def settings_tabs(hide_password_settings: bool):
    default_tabs = ['Profile', 'Emails', 'Username', 'Cloud', 'ORCID', 'Credentialing', 'Training',
                    'Certification', 'Agreements']
    if not hide_password_settings:
        default_tabs.insert(1, 'Password')
    return {'settings_tabs': default_tabs}


@register.filter(name='has_group')
def has_group(user, group_name):
    return user.groups.filter(name=group_name).exists()
