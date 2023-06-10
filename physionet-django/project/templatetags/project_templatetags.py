import os

from django import template
from django.shortcuts import reverse
from django.utils.html import format_html, escape
from django.utils.http import urlencode
import html2text

from project.authorization.access import can_view_project_files as can_view_project_files_func
from project.models import AccessPolicy
from notification.utility import mailto_url


register = template.Library()


@register.filter(name='html_to_text')
def html_to_text(html):
    """
    Convert HTML to plain text.
    """
    parser = html2text.HTML2Text()
    parser.ignore_links = True
    parser.ignore_emphasis = True

    return parser.handle(html).replace('\n', '')

@register.filter(name='nbsp')
def nbsp(text):
    """
    Replace spaces in the input text with non-breaking spaces.
    """
    return str(text).replace(' ', '\N{NO-BREAK SPACE}')

@register.filter(name='resource_badge')
def resource_badge(resource_type):
    badges = {
        0: '<span class="badge badge-dark"><i class="fa fa-database"></i> Database</span>',
        1: '<span class="badge badge-dark"><i class="fa fa-code"></i> Software</span>',
        2: '<span class="badge badge-dark"><i class="fa fa-bullseye"></i> Challenge</span>',
        3: '<span class="badge badge-dark"><i class="fa fa-project-diagram"></i> Model</span>',
    }
    return badges[resource_type]

@register.filter(name='topic_badge')
def topic_badge(topic, show_count=False):
    url = (reverse('content_index')
           + '?' + urlencode({'topic': topic.description}))
    if show_count:
        badge = '<a href="{}"><span class="badge badge-pn">{} ({})</span></a>'.format(
            url, topic.description, topic.project_count)
    else:
        badge = '<a href="{}"><span class="badge badge-pn">{}</span></a>'.format(
            url, topic.description)
    return badge

@register.filter(name='delimit')
def delimit(items):
    """
    Delimit the iterable of strings
    """
    return '; '.join(i for i in items)

@register.filter(name='access_badge')
def access_badge(access_policy):
    badges = {
        AccessPolicy.OPEN: '<span class="badge badge-success"><i class="fas fa-lock-open"></i> Open Access</span>',
        AccessPolicy.RESTRICTED: (
            '<span class="badge badge-warning"><i class="fas fa-unlock-alt"></i> Restricted Access</span>'
        ),
        AccessPolicy.CREDENTIALED: (
            '<span class="badge badge-danger"><i class="fas fa-lock"></i> Credentialed Access</span>'
        ),
        AccessPolicy.CONTRIBUTOR_REVIEW: (
            '<span class="badge badge-danger"><i class="fas fa-lock"></i> Contributor Review</span>'
        ),
    }
    try:
        return badges[access_policy]
    except KeyError:
        return format_html('<!-- unknown access_policy: {} -->', access_policy)


@register.filter(name='access_description')
def access_description(access_policy):
    descriptions = {
        AccessPolicy.OPEN: (
            'Anyone can access the files, as long as they conform to the terms of the specified license.'
        ),
        AccessPolicy.RESTRICTED: (
            'Only registered users who sign the specified data use agreement can access the files.'
        ),
        AccessPolicy.CREDENTIALED: ('Only credentialed users who sign the DUA can access the files.'),
        AccessPolicy.CONTRIBUTOR_REVIEW: (
            'Only credentialed users who sign the DUA can access the files. '
            'In addition, users must have individual studies reviewed by the contributor.'
        ),
    }
    try:
        return descriptions[access_policy]
    except KeyError:
        return format_html('<!-- unknown access_policy: {} -->', access_policy)

@register.filter(name='bytes_to_gb')
def bytes_to_gb(n_bytes):
    """
    Convert storage allowance bytes to a readable gb value
    """
    if n_bytes < 1073741824:
        return '{:.2f}'.format(n_bytes / 1073741824)
    else:
        return '{:d}'.format(int(n_bytes / 1073741824))

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


def author_popover(author, show_submitting=False, show_email=False,
                   show_corresponding=False):
    """
    Helper function for the popover of show_author_info and
    show_all_author_info
    """
    affiliation_info = escape('<b>Affiliations</b><p>{}</p>'.format('<br>'.join(escape(a) for a in author.text_affiliations)))
    profile_info = '<p><b>Profile</b><br><a href=/users/{} target=_blank>{}</a></p>'.format(author.username, author.username)
    popover_body = ''.join((affiliation_info, profile_info))

    if show_submitting and author.is_submitting:
        popover_body = '<p><strong>Submitting Author</strong></p>' + popover_body

    if show_email:
        popover_body += '<p><strong>User Email</strong><br> {}</p>'.format(author.email)

    if show_corresponding and author.is_corresponding:
        popover_body += '<p><strong>Corresponding Email</strong><br> {}</p>'.format(author.corresponding_email)

    return '<a class="author">{}</a> <i class="fas fa-info-circle" data-toggle="popover" data-original-title="<strong>Author Info</strong>" data-placement="bottom" data-content="{}" data-html="true" style="cursor: pointer;"></i>'.format(
        author.name, popover_body)


@register.filter(name='show_author_info')
def show_author_info(author):
    """
    Display the author's name, and a popover icon with their
    affiliation and profile info, for public view.

    Requires set_display_info method to be called by author beforehand.
    """
    return author_popover(author)


@register.filter(name='show_all_author_info')
def show_all_author_info(author):
    """
    Display information about the author, for the editor panel.

    Requires set_display_info method to be called by author beforehand.
    """
    return author_popover(author, show_submitting=True, show_email=True,
                          show_corresponding=True)


@register.simple_tag(name='mailto_link')
def mailto_link(*recipients, **params):
    """
    Format an email address as an HTML link.

    The recipient address(es) are specified as positional arguments.
    Additional header fields (such as 'subject') and the special
    pseudo-header 'body' may be specified as keyword arguments.

    For example, {% mailto_link "alice@example.com" %}
    yields "<a href="mailto:alice@example.com">alice@example.com</a>".
    """
    url = mailto_url(*recipients, **params)
    label = ', '.join(recipients)
    return format_html('<a href="{0}">{1}</a>', url, label)


@register.filter
def filename(value):
    return os.path.basename(value.name)


@register.simple_tag
def call_method(obj, method_name, *args):
    """
    This provides a means to pass an argument to a method when calling it

    Parameters:
        obj: an object created from a model class
        method_name: method available to the object
        args: arguments to be passed to the method

    Example:
        {% call_method published_project 'can_view_files' request.user as user_can_view_files %}
    """
    method = getattr(obj, method_name)
    return method(*args)


@register.simple_tag(name='can_view_project_files')
def can_view_project_files(project, user):
    return can_view_project_files_func(project, user)
