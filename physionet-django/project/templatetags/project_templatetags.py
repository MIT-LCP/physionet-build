from django import template


register = template.Library()


@register.filter(name='resource_badge')
def resource_badge(resource_type):
    badges = {
        0: '<span class="badge badge-dark"><i class="fa fa-database"></i> Database</span>',
        1: '<span class="badge badge-dark"><i class="fa fa-keyboard"></i> Software</span>',
    }
    return badges[resource_type]

@register.filter(name='delimit')
def delimit(items):
    """
    Delimit the iterable of strings
    """
    return '; '.join(i for i in items)

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

@register.filter(name='submission_result_label')
def submission_result_label(submission):
    """
    Shows a word label for the result of a submission given its status
    """
    if submission.status == 5:
        result = 'Accepted and published'
    elif submission.status == 1:
        result == 'Rejected'
    else:
        result = 'Ongoing'
    return result


def author_popover(author, include_email=False, show_corresponding=False):
    """
    Helper function for the popover of show_author_info and
    show_all_author_info
    """
    affiliation_info = '<b>Affiliations</b><p>' + '<br>'.join(a for a in author.text_affiliations) + '</p>'
    profile_info = '<p><b>PhysioNet Profile</b><br><a href=/users/{} target=_blank>{}</a></p>'.format(author.username, author.username)
    popover_body = ''.join((affiliation_info, profile_info))

    if include_email:
        popover_body += '<p><strong>User Email</strong><br> {}</p>'.format(author.email)

    if show_corresponding and author.is_corresponding:
        popover_body += '<p><strong>Corresponding Email</strong><br> {}</p>'.format(author.corresponding_email)

    return '{} <i class="fas fa-info-circle" data-toggle="popover" data-original-title="<strong>Author Info</strong>" data-placement="bottom" data-content="{}" data-html="true" style="cursor: pointer;"></i>'.format(
        author.name, popover_body)


@register.filter(name='show_author_info')
def show_author_info(author):
    """
    Display the author's name, and a popover icon with their
    affiliation and profile info, for public view.

    Requires set_display_info method to be called by author beforehand.
    """
    return author_popover(author, include_email=False)


@register.filter(name='show_all_author_info')
def show_all_author_info(author):
    """
    Display information about the author, for the editor panel.

    Requires set_display_info method to be called by author beforehand.
    """
    return author_popover(author, include_email=True, show_corresponding=True)
