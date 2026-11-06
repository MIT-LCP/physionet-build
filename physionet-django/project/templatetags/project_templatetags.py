import os

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.shortcuts import reverse
from django.utils import timezone
from django.utils.html import format_html, escape
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
import html2text

from project.authorization.access import can_view_project_files as can_view_project_files_func
from project.models import AccessPolicy
from notification.utility import mailto_url
from datetime import timedelta


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


@register.simple_tag
def dataset_index_badge(project, scholar_data):
    """
    Badge showing a project's Dataset Index (D-Index) from stored
    Scholar Data, linking to the project's metrics page.

    Returns an empty string if no score is available.
    """
    d_index = (scholar_data or {}).get('latestDIndex') or {}
    score = d_index.get('score')
    if not isinstance(score, (int, float)):
        return ''
    url = reverse('published_project_metrics', args=(project.slug, project.version))
    year = d_index.get('year')
    title = f'Dataset Index ({year}) from Scholar Data' if year else 'Dataset Index from Scholar Data'
    return format_html(
        '<a href="{}" class="badge badge-dataset-index" title="{}">'
        '<span class="badge-dataset-index-label"><i class="fas fa-chart-line"></i> Dataset Index</span>'
        '<span class="badge-dataset-index-value">{}</span></a>',
        url, title, round(score),
    )


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
    show_all_author_info.

    The author's name is rendered as a button that opens a popover
    with their affiliations and profile link.
    """
    parts = []
    if show_submitting and author.is_submitting:
        parts.append(mark_safe('<p><strong>Submitting Author</strong></p>'))

    affiliations = format_html(
        '<p><strong>Affiliations</strong><br>{}</p>',
        mark_safe('<br>'.join(escape(a) for a in author.text_affiliations)),
    )
    parts.append(affiliations)
    parts.append(format_html(
        '<p><strong>Profile</strong><br><a href="{}" target="_blank">{}</a></p>',
        reverse('public_profile', args=[author.username]), author.username,
    ))

    if show_email:
        parts.append(format_html('<p><strong>User Email</strong><br>{}</p>', author.email))

    if show_corresponding and author.is_corresponding:
        parts.append(format_html('<p><strong>Corresponding Email</strong><br>{}</p>',
                                 author.corresponding_email))

    popover_body = ''.join(parts)

    trigger = format_html(
        '<button type="button" class="author-popover-trigger" data-toggle="popover" '
        'data-placement="bottom" data-html="true" data-content="{}" '
        'aria-label="{}: show author information" aria-expanded="false">'
        '{}<i class="fas fa-caret-down" aria-hidden="true"></i></button>',
        popover_body, author.name, author.name,
    )
    return format_html('{}{}', trigger, orcid_icon_link(author))


def orcid_icon_link(author):
    """
    Return a small ORCID iD icon linking to the author's ORCID record,
    or an empty string if the author has no linked ORCID iD.
    """
    orcid_id = getattr(author, 'orcid_id', None)
    if not orcid_id:
        return ''
    url = f'{settings.ORCID_DOMAIN}/{orcid_id}'
    return format_html(
        '<a class="author-orcid" href="{}" target="_blank" rel="noopener" title="ORCID iD: {}">'
        '<img src="{}" alt="ORCID iD for {}" width="16" height="16"></a>',
        url, url, static('images/orcid-id-icon.svg'), author.name,
    )


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


PROJECT_SETTINGS_STEPS = [
    ('authors', 'Authors'),
    ('content', 'Content'),
    ('access', 'Access'),
    ('discovery', 'Discovery'),
    ('ethics', 'Ethics'),
    ('upload_agreement', 'Upload Agreement'),
    ('files', 'Files'),
    ('proofread', 'Proofread'),
]

CHALLENGE_STEP = ('challenge_config', 'Challenge Setup')
CHALLENGE_STEP_INDEX = 5  # after Ethics


def _get_settings_steps(project=None):
    steps = list(PROJECT_SETTINGS_STEPS)
    if project and getattr(project, 'resource_type_id', None) == 2:
        steps.insert(CHALLENGE_STEP_INDEX, CHALLENGE_STEP)
    return steps


@register.simple_tag(name='project_settings_steps')
def project_settings_steps(project=None):
    """Return the ordered list of project settings steps."""
    return _get_settings_steps(project)


@register.simple_tag(name='project_step_header', takes_context=True)
def project_step_header(context, key):
    """Return the step heading string (e.g. '7. Files') for a given key."""
    steps = dict((k, (i, label)) for i, (k, label) in enumerate(_get_settings_steps(context.get('project')), 1))
    if key not in steps:
        raise KeyError(f"Unknown project step: {key!r}")
    i, label = steps[key]
    return f'{i}. {label}'


@register.simple_tag(name='can_view_project_files')
def can_view_project_files(project, user, request=None):
    return can_view_project_files_func(project, user, request)


@register.filter(name='is_within_days')
def is_within_days(date_value, days):
    """
    Check if date is within N days of now
    """
    if not date_value:
        return False
    days_since = (timezone.now() - date_value).days
    return 0 <= days_since < int(days)


@register.filter(name='get_item')
def get_item(dictionary, key):
    """Variable-key dict lookup for use in templates."""
    if dictionary is None:
        return None
    return dictionary.get(key)
