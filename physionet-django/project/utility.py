import base64
import datetime
import errno
import html.parser
import json
import logging
import os
import pdb
import re
import shutil
import urllib.parse
import uuid

import requests
from console.utility import create_directory_service
from django.conf import settings
from django.contrib import auth, messages
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse
from django.utils.crypto import constant_time_compare
from googleapiclient.errors import HttpError
from oauth2_provider.oauth2_backends import get_oauthlib_core


LOGGER = logging.getLogger(__name__)


# Main-body fields normalized as a submission enters copyediting.
COPYEDIT_CONTENT_FIELDS = (
    'abstract', 'background', 'methods', 'content_description', 'usage_notes',
    'installation', 'release_notes', 'ethics_statement', 'acknowledgements',
    'conflicts_of_interest',
)
_VOID_HTML_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                   'link', 'meta', 'param', 'source', 'track', 'wbr'}
_EMPTY_INLINE_TAGS = {'b', 'code', 'em', 'i', 'strong', 'u'}
_MAX_COPYEDIT_HTML_DEPTH = 500
_COPYEDIT_NORMALIZATION_RULE_ORDER = (
    'replaced non-breaking spaces',
    'removed span wrappers',
    'removed empty formatting tags',
    'removed empty paragraphs',
    'trimmed trailing paragraph whitespace',
    'unwrapped a paragraph in a list item or table cell',
    'removed bold formatting from a heading',
)


class _CopyeditHTMLNode:
    def __init__(self, tag=None, attrs=(), data=None):
        self.tag, self.attrs, self.data = tag, list(attrs), data
        self.children = []
        self.changed = False
        self.rules = set()

    @property
    def is_text(self):
        return self.tag is None


class _CopyeditHTMLParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _CopyeditHTMLNode('fragment')
        self.stack = [self.root]
        self.excessively_nested = False

    def handle_starttag(self, tag, attrs):
        node = _CopyeditHTMLNode(tag.lower(), attrs)
        self.stack[-1].children.append(node)
        if node.tag not in _VOID_HTML_TAGS:
            self.stack.append(node)
            if len(self.stack) > _MAX_COPYEDIT_HTML_DEPTH:
                self.excessively_nested = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_HTML_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag.lower():
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(_CopyeditHTMLNode(data=data))


def _normalize_copyedit_node(node, parent=None, include_medium=False,
                             in_protected_content=False):
    if node.is_text:
        normalized = node.data.replace('\xa0', ' ')
        node.changed = normalized != node.data
        if node.changed:
            node.rules.add('replaced non-breaking spaces')
        node.data = normalized
        return [node]
    protected_content = in_protected_content or node.tag in {'math', 'pre'}
    normalized_children = []
    for child in node.children:
        child_results = _normalize_copyedit_node(
            child,
            node,
            include_medium,
            in_protected_content=protected_content,
        )
        if child.changed or len(child_results) != 1 or child_results[0] is not child:
            node.changed = True
        node.rules.update(child.rules)
        normalized_children.extend(child_results)
    node.children = normalized_children
    if node.tag == 'span':
        node.changed = True
        node.rules.add('removed span wrappers')
        return node.children
    if protected_content:
        return [node]
    if node.tag in _EMPTY_INLINE_TAGS and not _copyedit_has_content(node):
        node.changed = True
        node.rules.add('removed empty formatting tags')
        return []
    if include_medium and (
            node.tag == 'p' and parent and parent.tag in {'li', 'td', 'th'}
            and all(child is node or (child.is_text and not child.data.strip())
                    for child in parent.children)):
        node.changed = True
        node.rules.add('unwrapped a paragraph in a list item or table cell')
        return node.children
    if node.tag == 'p' and node.children and node.children[-1].is_text:
        trimmed = node.children[-1].data.rstrip()
        if trimmed != node.children[-1].data:
            node.children[-1].data = trimmed
            node.changed = True
            node.rules.add('trimmed trailing paragraph whitespace')
    if node.tag == 'p' and not any(
            not child.is_text or child.data for child in node.children):
        node.changed = True
        node.rules.add('removed empty paragraphs')
        return []
    if include_medium and node.tag in {'h3', 'h4', 'h5', 'h6'}:
        node.children = _unwrap_heading_bold(node.children, node)
    return [node]


def _unwrap_heading_bold(children, heading):
    results = []
    for child in children:
        if child.is_text:
            results.append(child)
        elif child.tag in {'b', 'strong'}:
            heading.changed = True
            heading.rules.add('removed bold formatting from a heading')
            results.extend(_unwrap_heading_bold(child.children, heading))
        elif child.tag in {'math', 'pre'}:
            results.append(child)
        else:
            child.children = _unwrap_heading_bold(child.children, heading)
            results.append(child)
    return results


def _copyedit_has_content(node):
    if node.is_text:
        return bool(node.data.strip())
    # MathML has valid semantic elements with neither text nor descendants
    # (for example, mspace, none, and mprescripts).
    if node.tag == 'math':
        return True
    return node.tag in _VOID_HTML_TAGS or any(
        _copyedit_has_content(child) for child in node.children)


def _serialize_copyedit_node(node):
    if node.is_text:
        return html.escape(node.data, quote=False)
    if node.tag == 'fragment':
        return ''.join(_serialize_copyedit_node(c) for c in node.children)
    attrs = ''.join(' {}="{}"'.format(name, html.escape(value or '', quote=True)) for name, value in node.attrs)
    if node.tag in _VOID_HTML_TAGS:
        return '<{}{}>'.format(node.tag, attrs)
    return '<{}{}>{}</{}>'.format(
        node.tag,
        attrs,
        ''.join(_serialize_copyedit_node(c) for c in node.children),
        node.tag
    )


def normalize_copyedit_html(value, include_medium=False):
    """Return a normalized SafeHTMLField value."""
    return normalize_copyedit_html_with_rules(value, include_medium)[0]


def normalize_copyedit_html_with_rules(value, include_medium=False):
    """Normalize one already-sanitized SafeHTMLField value for copyediting.

    Low-risk rules are always applied. The two medium-risk rules are limited
    to acceptance-time backfill. Values without a matching rule are returned
    verbatim, so parser serialization cannot alter unrelated content.
    """
    try:
        parser = _CopyeditHTMLParser()
        parser.feed(value or '')
        parser.close()
        if parser.excessively_nested:
            LOGGER.warning('Skipped copyedit HTML normalization due to excessive nesting')
            return value or '', ()
        normalized_children = []
        for child in parser.root.children:
            results = _normalize_copyedit_node(child, include_medium=include_medium)
            if child.changed or len(results) != 1 or results[0] is not child:
                parser.root.changed = True
            parser.root.rules.update(child.rules)
            normalized_children.extend(results)
        parser.root.children = normalized_children
        if not _copyedit_node_changed(parser.root):
            return value or '', ()
        return (
            _serialize_copyedit_node(parser.root),
            tuple(rule for rule in _COPYEDIT_NORMALIZATION_RULE_ORDER
                  if rule in parser.root.rules),
        )
    except RecursionError:
        LOGGER.warning('Skipped copyedit HTML normalization due to excessive nesting')
        return value or '', ()


def normalize_project_content(project):
    """Normalize all project content fields without partially updating a project.

    Returns a field-to-rules mapping for the values that changed.
    """
    updates = {}
    for field in COPYEDIT_CONTENT_FIELDS:
        value = getattr(project, field)
        normalized, rules = normalize_copyedit_html_with_rules(
            value, include_medium=True)
        if normalized != value:
            updates[field] = (normalized, rules)
    for field, (normalized, _) in updates.items():
        setattr(project, field, normalized)
    return {field: rules for field, (_, rules) in updates.items()}


def _copyedit_node_changed(node):
    return node.changed or any(_copyedit_node_changed(child) for child in node.children)


def copyedit_content_warnings(value):
    """Return higher-risk copyediting patterns that should be reviewed."""
    try:
        parser = _CopyeditHTMLParser()
        parser.feed(value or '')
        parser.close()
        if parser.excessively_nested:
            LOGGER.warning('Skipped copyedit HTML warnings due to excessive nesting')
            return set()
        warnings = set()

        def visit(node):
            if node.is_text:
                return
            if node.tag == 'div':
                warnings.add('contain div elements')
            if _has_bold_first_table_row(node):
                warnings.add('have a table whose first row appears to be a header')
            for child in node.children:
                visit(child)

        visit(parser.root)
        return warnings
    except RecursionError:
        LOGGER.warning('Skipped copyedit HTML warnings due to excessive nesting')
        return set()


def _has_bold_first_table_row(node):
    if node.tag != 'table' or any(child.tag == 'thead' for child in node.children):
        return False
    tbody = next((child for child in node.children if child.tag == 'tbody'), None)
    rows = [child for child in tbody.children if child.tag == 'tr'] if tbody else []
    if len(rows) < 2:
        return False
    cells = [child for child in rows[0].children if child.tag in {'td', 'th'}]
    return bool(cells) and all(_is_bold_header_cell(cell) for cell in cells)


def _is_bold_header_cell(cell):
    if cell.tag != 'td':
        return False
    contents = _significant_copyedit_children(cell)
    if len(contents) == 1 and contents[0].tag == 'p':
        contents = _significant_copyedit_children(contents[0])
    return (
        len(contents) == 1
        and contents[0].tag in {'b', 'strong'}
        and _copyedit_has_content(contents[0])
    )


def _significant_copyedit_children(node):
    return [
        child for child in node.children
        if not child.is_text or child.data.strip()
    ]


def move_author(author, authors, direction):
    """Move an author one position in the requested direction."""
    n_authors = authors.count()
    if n_authors <= 1:
        raise Http404()
    if direction == 'up' and 1 < author.display_order <= n_authors:
        swap_author = authors.get(display_order=author.display_order - 1)
    elif direction == 'down' and 1 <= author.display_order < n_authors:
        swap_author = authors.get(display_order=author.display_order + 1)
    else:
        raise Http404()

    with transaction.atomic():
        author_order = author.display_order
        swap_order = swap_author.display_order
        author.display_order = 0
        author.save(update_fields=('display_order',))
        swap_author.display_order = author_order
        swap_author.save(update_fields=('display_order',))
        author.display_order = swap_order
        author.save(update_fields=('display_order',))


class FileInfo():
    """
    For displaying lists of files in project pages
    All attributes are human readable strings
    """
    def __init__(self, name, size, last_modified):
        self.name = name
        self.size = size
        self.last_modified = last_modified

    def __lt__(self, other):
        return self.name < other.name


class DirectoryInfo():
    def __init__(self, name):
        self.name = name

    def __lt__(self, other):
        return self.name < other.name


class DirectoryBreadcrumb():
    """
    For navigating through project file directories
    """
    def __init__(self, name, rel_path, full_subdir, active=True):
        self.name = name
        self.rel_path = rel_path
        self.full_subdir = full_subdir
        self.active = active


def get_dir_breadcrumbs(path, directory=True):
    """
    Given a subdirectory, return all breadcrumb elements

    full_subdir for inputs:
    ''  -->
    d1  --> ['', 'd1']
    d1/  --> ['', 'd1']
    d1/d2/d3
    d1/d2/d3/
    """

    if path == '':
        return [DirectoryBreadcrumb(name='<base>', rel_path='',
                                    full_subdir='', active=False)]
    if path.endswith('/'):
        path = path[:-1]
    dirs = path.split('/')
    rel_path = '../' * len(dirs)
    if not directory:
        rel_path = (rel_path[3:] or './')
    dir_breadcrumbs = [DirectoryBreadcrumb(name='<base>', full_subdir='',
                                           rel_path=rel_path)]
    for i in range(len(dirs)):
        rel_path = (rel_path[3:] or './')
        dir_breadcrumbs.append(DirectoryBreadcrumb(
            name=dirs[i], rel_path=rel_path,
            full_subdir='/'.join([d.name for d in dir_breadcrumbs[1:]]+ [dirs[i]])))
    dir_breadcrumbs[-1].active = False
    return dir_breadcrumbs


class StorageInfo():
    """
    Object for storing display information about a project's storage.
    """
    def __init__(self, allowance, used, include_remaining=True,
                 main_used=None, compressed_used=None, published=0):
        """
        Initialize fields with optional args for published and
        unpublished projects

        The include_remaining argument has no effect and is kept for
        compatibility.
        """
        self.allowance = allowance
        self.readable_allowance = readable_size(allowance)
        self.published = published
        self.readable_published = readable_size(published)
        self.p_used_old = round(published * 100 / allowance)

        # Total used
        self.used = used
        if used is None:
            self.readable_used = 'unknown'
            self.remaining = None
            self.readable_remaining = 'unknown'
            self.p_used = '?'
            self.p_remaining = '?'
            self.p_used_new = '?'
        else:
            self.readable_used = readable_size(used)
            self.remaining = allowance - used
            self.readable_remaining = readable_size(self.remaining)
            self.p_used = round(used * 100 / allowance)
            self.p_remaining = round(self.remaining * 100 / allowance)
            self.p_used_new = self.p_used - self.p_used_old

        if main_used is not None:
            self.main_used = main_used
            self.readable_main_used = readable_size(main_used)

        if compressed_used is not None:
            self.compressed_used = compressed_used
            self.readable_compressed_used = readable_size(compressed_used)


def list_items(directory, return_separate=True):
    "List files and directories in a directory. Return separate or combine lists"
    if return_separate:
        dirs = []
        files = []
        for ent in os.scandir(directory):
            if ent.is_dir():
                dirs.append(ent.name)
            else:
                files.append(ent.name)
        return (sorted(files), sorted(dirs))
    else:
        return sorted(os.listdir(directory))

def remove_items(items, ignore_missing=True):
    """
    Delete the list of (full file path) files/directories.

    Args:
      items: Is a list of files or directories to delete.
      ignore_missing: Flag to ignore missing files or directories.
    """
    if isinstance(items,(tuple,list)):
        for item in items:
            try:
                os.unlink(item)
            except FileNotFoundError:
                if not ignore_missing:
                    raise
            except OSError as e:
                if e.errno not in (errno.EISDIR, errno.EPERM):
                    raise
                shutil.rmtree(item)
    else:
        LOGGER.info("Non list/tuple entered in remove items. The 'item' entered \
         was: {0}".format(items))
        raise TypeError

def clear_directory(directory):
    """
    Delete all files and folders in a directory.
    """
    for i in os.listdir(directory):
        remove_items([os.path.join(directory, i)])

def rename_file(old_path, new_path):
    """
    Rename a file, without overwriting an existing file.

    If the destination path already exists, this will attempt to raise
    a FileExistsError.  This is not guaranteed to work correctly in
    all cases.
    """
    if os.path.exists(new_path):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST),
                              old_path, new_path)
    os.rename(old_path, new_path)

def move_items(items, target_folder):
    """
    Move items (full path) into target folder (full path)
    """
    for item in items:
        rename_file(item, os.path.join(target_folder, os.path.split(item)[-1]))

def get_file_info(file_path):
    "Given a file path, get the information used to display it"
    name = os.path.split(file_path)[-1]
    size = readable_size(os.path.getsize(file_path))
    last_modified = datetime.date.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d")
    return FileInfo(name, size, last_modified)

def get_directory_info(dir_path):
    "Given a directory path, get the information used to display it"
    return DirectoryInfo(os.path.split(dir_path)[-1])

def get_tree_size(path):
    """Return total size of files in given path and subdirs."""
    total = 0
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            total += get_tree_size(entry.path)
        else:
            total += entry.stat(follow_symlinks=False).st_size
    return total


def readable_size(num, suffix='B'):
    "Display human readable size of byte number"
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024:
            readsize = '{0:g}'.format(num)

            if '.' not in readsize:
                return readsize+' '+unit+suffix
            else:
                return '{:3.1f} {:s}{:s}'.format(num, unit, suffix)

        num /= 1024.0
    return '{:.1f}{:s}{:s}'.format(num, 'Y', suffix)


def write_uploaded_file(file, write_file_path, overwrite=True):
    """
    file: request.FILE
    write_file_path: full file path to be written
    """
    if overwrite:
        try:
            os.unlink(write_file_path)
        except FileNotFoundError:
            pass
    with open(write_file_path, 'xb') as destination:
        for chunk in file.chunks():
            destination.write(chunk)


def get_form_errors(form):
    """
    Extract all errors from a form with errors
    """
    all_errors = []
    for field in form.errors:
        all_errors += form.errors[field]
    return all_errors


def grant_aws_open_data_access(user, project):
    """
    Function to grant a AWS ID access to the bukets in the Open Data
    AWS platform.

    This function returns a tuple containing a message and a boolean indicating
    whether access was successfully granted.

    Possible responses from the AWS API are:

    b'{"error": "Unexpected error: An error occurred (MalformedPolicy) when
        calling the PutBucketPolicy operation: Invalid principal in policy",
        "message": null}'
    b'{"error": "None", "message": "Accounts [\'XXXYYYZZZ\'] have been added,
        accounts [] have been skipped since already exist, accounts [] have
        been deleted since policy is too large"}'
    b'{"error": "None", "message": "No new accounts to add"}'
    """
    url = settings.AWS_CLOUD_FORMATION
    # The payload has to be a string in an array
    payload = {'accountid': ["{}".format(user.cloud_information.aws_id)]}
    # Custom headers set as a key for a lambda function in AWS to grant access
    headers = {settings.AWS_HEADER_KEY: settings.AWS_HEADER_VALUE,
        settings.AWS_HEADER_KEY2: settings.AWS_HEADER_VALUE2}
    # Do a request to AWS and try to add the user ID to the bucket
    response = requests.post(url, data=json.dumps(payload), headers=headers)

    # Exit early if we received a response from AWS indicating an error.
    if response.status_code < 200 or response.status_code >= 300:
        LOGGER.info("Error sending adding the AWS ID to the Bucket Policy."
                    "The request payload is {0}\nThe error is the following: "
                    "{1}\n".format(payload, response.content))
        return "Access could not be granted.", False

    # The following if block will:
    #   (1) create a notification to send the user
    #   (2) set a boolean to True/False, indicating if access was granted (True)
    aws_response = response.json()['message']
    if aws_response == "No new accounts to add":
        LOGGER.info("AWS response adding {0} to project {1}\n{2}".format(
            user.cloud_information.aws_id, project, aws_response))
        granted_access = True
        access_message = aws_response
    elif "Accounts ['{}'] have been added".format(user.cloud_information.aws_id) in aws_response:
        LOGGER.info("AWS response adding {0} to project {1}\n{2}".format(
            user.cloud_information.aws_id, project, aws_response))
        granted_access = True
        access_message = aws_response.split(',')[0]
    else:
        LOGGER.info('Unknown response from AWS - {0}\nThe payload is {1}'.format(
            payload, response.content))
        granted_access = False
        access_message = "Access could not be granted."

    return access_message, granted_access


def grant_gcp_group_access(user, project, data_access):
    """
    Add a specific email address to a organizational google group in G Suite
    Possible access types would be:
    - 3 is for the GCP Bucket
    - 4 is for the GCP Big Query

    This function returns a tuple containing a message and a boolean indicating
    whether access was successfully granted.
    """
    gcp_access_messages = {
        3: "Access to the GCP bucket",
        4: "Access to the GCP BigQuery"
    }
    # Return early if we are passed a non-GCP data access platform
    if data_access.platform not in gcp_access_messages:
        return "Invalid data access platform for GCP", False

    access_message = gcp_access_messages[data_access.platform]
    # Indicate whether we successfully granted access to the user
    granted_access = False

    # Initialize a service for interacting with Google Admin
    email = user.cloud_information.gcp_email.email
    service = create_directory_service(settings.GCP_DELEGATION_EMAIL)

    try:
        group_members = service.members()
        outcome = group_members.insert(groupKey=data_access.location, body={
            "email": email, "delivery_settings": "NONE"}).execute()
        if outcome['role'] == "MEMBER":
            access_message = '{0} has been granted to {1} for project: {2}'.format(
                access_message, email, project)
            granted_access = True
            LOGGER.info("{0} email {1}".format(access_message, data_access.location))
        else:
            raise Exception('Wrong access granted to {0} in GCP email {1}'.format(
                email, data_access.location))
    except HttpError as error:
        if json.loads(error.content)['error']['message'] == 'Member already exists.':
            granted_access = True
            access_message = '{0} was previously awarded to {1} for project: {2}'.format(
                access_message, email, project)
        elif error.resp.status == 412:
            # Google has a somewhat cryptic 412 error: "Condition not met"
            # In our experience, this occurred when the user specified a non-Google
            # e-mail in their cloud profile which could not be added to the group.
            access_message = (
                'Unable to provision access, please verify '
                '{0} is a valid Google account'.format(email)
            )
        else:
            access_message = 'Unable to grant {0} access to {1} for {2}'.format(
                access_message, email, project)

    return access_message, granted_access


# The following regular expression defines user agents that are
# permitted to use HTTP authentication for accessing protected
# databases.  This list should not include web browsers.  (If you are
# writing a new program for accessing protected databases, please use
# a distinctive UA string so that your program can be whitelisted
# here.  Do not use the generic UA string provided by your HTTP client
# library.)
HTTP_AUTH_USER_AGENT = re.compile('|'.join((
    'Wget/',
    'libwfdb/',
    'PhysioNet-Python-Client/',
)))


def http_auth_allowed(request):
    """
    Check if HTTP authentication is permitted for the given request.

    Web browsers typically don't implement HTTP authentication in a
    very user-friendly or secure way, so this mechanism is only
    permitted for specific non-interactive user agents.  For safety,
    HTTP authentication is only permitted for GET and HEAD requests,
    and (unless settings.DEBUG is set) only via HTTPS.
    """

    if request.method not in ('GET', 'HEAD'):
        return False
    if not request.is_secure() and not settings.DEBUG:
        return False

    ua = request.META.get('HTTP_USER_AGENT', '')
    if HTTP_AUTH_USER_AGENT.match(ua):
        return True
    else:
        return False


# OAuth scope that lets an access token download project files.
DOWNLOAD_TOKEN_SCOPE = 'data:download'


def check_bearer_token(request):
    """
    Set request.user from an OAuth access token with the download scope.

    Browsers do not send bearer tokens on their own, so any user agent
    may use one.  For safety, tokens are only accepted for GET and HEAD
    requests and (unless settings.DEBUG is set) only via HTTPS.
    """
    if request.method not in ('GET', 'HEAD'):
        return
    if not request.is_secure() and not settings.DEBUG:
        return
    if request.user.is_authenticated:
        return

    valid, oauth_request = get_oauthlib_core().verify_request(
        request, scopes=[DOWNLOAD_TOKEN_SCOPE])
    if valid and oauth_request.access_token.user.is_active:
        request.user = oauth_request.access_token.user


def check_http_auth(request):
    """
    Check if a request includes HTTP authentication.

    If HTTP authentication is permitted for the given request, and a
    valid username and password are provided, set request.user to the
    corresponding user object.  Otherwise, the request is not
    modified.

    For safety, HTTP authentication is only used for certain requests
    from non-interactive user agents; see http_auth_allowed().  OAuth
    access tokens are also accepted; see check_bearer_token().

    This should be invoked at the start of the view before checking
    user credentials, and should be paired with require_http_auth().
    """
    from user.models import User

    auth_scheme = request.META.get('HTTP_AUTHORIZATION', '').split(' ', 1)[0]
    if auth_scheme.lower() == 'bearer':
        check_bearer_token(request)
        return

    if 'HTTP_AUTHORIZATION' in request.META:
        # If an Authorization header is supplied, but this request is
        # not allowed to use HTTP authentication, ignore the header.
        if not http_auth_allowed(request):
            return

        # If the user is already authenticated, ignore the header.
        if request.user.is_authenticated:
            return

        try:
            uid = request.session['pn_httpauth_uid']
            authhash = request.session['pn_httpauth_hash']
            user = User.objects.get(id=uid)
        except (KeyError, User.DoesNotExist):
            pass
        else:
            # Existing session is valid only if the password has not
            # changed.
            if constant_time_compare(user.get_session_auth_hash(),
                                     authhash) and user.is_active:
                request.user = user
                return

        tokens = request.META['HTTP_AUTHORIZATION'].split()
        if len(tokens) == 2 and tokens[0].lower() == 'basic':
            try:
                data = base64.b64decode(tokens[1], validate=True).decode()
                username, password = data.split(':', 1)
            except Exception:
                return

            user = auth.authenticate(request=request,
                                     username=username,
                                     password=password)
            if user and user.is_active:
                request.user = user

                # If the client supports cookies, save the state so
                # that we don't have to verify the password on
                # subsequent requests.  If the client doesn't support
                # cookies, don't bother.
                if request.COOKIES:
                    # We don't invoke auth.login() here, specifically
                    # so that this session ID cannot be reused to
                    # access URLs that don't permit HTTP
                    # authentication.
                    request.session['pn_httpauth_uid'] = user.id
                    request.session['pn_httpauth_hash'] \
                        = user.get_session_auth_hash()


def require_http_auth(request):
    """
    Ask the client to authenticate itself and retry the request.

    For safety, HTTP authentication is only allowed for certain
    requests from non-interactive user agents; see
    http_auth_allowed().  If this request is not allowed, or if the
    user is already authenticated, raise PermissionDenied.

    Otherwise, return an HttpResponse with status 401 (Unauthorized),
    which indicates the client should repeat the request with a
    username and password.

    This should be invoked after check_http_auth(), if the user is
    unknown or is not authorized to view the given resource.
    """

    if http_auth_allowed(request) and not request.user.is_authenticated:
        site = get_current_site(request)
        response = HttpResponse(status=401)
        response['WWW-Authenticate'] = (
            'Basic realm="{}", charset="UTF-8"'.format(site.name)
        )
        # Check whether the client supports cookies.
        response.set_cookie('testcookie', '1', secure=(not settings.DEBUG),
                            httponly=True, samesite='Lax')
        return response
    else:
        raise PermissionDenied()


class LinkFilter:
    """
    Class for transforming links in an HTML document.

    To filter an HTML document (or fragment), create an instance of
    LinkFilter and call convert().  The input should be valid HTML to
    begin with (e.g., preprocessed using bleach.)

    Several transformations can be performed.  First, if base_url is
    specified, all relative URLs in the input are converted to
    absolute URLs:

    >>> f = LinkFilter(base_url='https://example.com/foo/')
    >>> f.convert('<a href="123">')
    '<a href="https://example.com/foo/123">'

    >>> f = LinkFilter(base_url='/foo/')
    >>> f.convert('<a href="../bar">')
    '<a href="/bar">'

    If my_hostnames is specified, any HTTP or HTTPS link that points
    to one of the specified hostnames is converted into a
    host-relative URL:

    >>> f = LinkFilter(my_hostnames=['example.com'])
    >>> f.convert('<a href="https://example.com/foo/123">')
    '<a href="/foo/123">'

    >>> f = LinkFilter(my_hostnames=['example.com'],
    ...                base_url='http://example.com:8080/foo/')
    >>> f.convert('<a href="123">')
    '<a href="/foo/123">'

    Any 'src' attributes that do not point to one of my_hostnames are
    deleted:

    >>> f = LinkFilter(my_hostnames=['example.com'])
    >>> f.convert('<img src="https://example.com/foo.jpg">')
    '<img src="/foo.jpg">'
    >>> f.convert('<img src="/foo.jpg">')
    '<img src="/foo.jpg">'
    >>> f.convert('<img src="https://unsafe.example.org/bar.jpg">')
    '<img>'

    If prefix_map is specified, it can be used to remap URLs within
    the given prefixes:

    >>> f = LinkFilter(my_hostnames=['example.com'],
    ...                prefix_map={'/foo/': '/bar/'})
    >>> f.convert('<a href="http://example.com/foo/123">')
    '<a href="/bar/123">'

    Other links are not affected:

    >>> f.convert('<a href="https://example.org/foo/">')
    '<a href="https://example.org/foo/">'

    Other input text is not affected:

    >>> f.convert('x &amp; y & z < <a b c> &#65;')
    'x &amp; y & z < <a b c> &#65;'
    """

    def __init__(self, base_url=None, my_hostnames=None, prefix_map=None):
        # If my_hostnames is not specified, default to the value of
        # settings.ALLOWED_HOSTS.  If that is set to '*' (development
        # server), default to localhost.
        if my_hostnames is None:
            my_hostnames = settings.ALLOWED_HOSTS
            if my_hostnames == ['*']:
                my_hostnames = ['localhost', '127.0.0.1']

        # Set my_netloc_re to a regular expression that matches either
        # the empty string, or any of the specified hostnames with an
        # optional port
        if my_hostnames:
            hostname_patterns = [re.escape(h) for h in my_hostnames]
            hostname_pattern = '(?:' + '|'.join(hostname_patterns) + ')'
            netloc_pattern = '(?:' + hostname_pattern + '(?::[0-9]+)?)?'
            self.my_netloc_re = re.compile(netloc_pattern, re.A | re.I)
        else:
            # Only match the empty string
            self.my_netloc_re = re.compile('')

        self.base_url = base_url

        self.path_subs = []
        if prefix_map:
            for (oldpath, newpath) in reversed(sorted(prefix_map.items())):
                # Ignore trailing slashes
                oldpath = oldpath.rstrip('/')
                newpath = newpath.rstrip('/')
                # Match either oldpath exactly, or a string starting
                # with oldpath followed by a slash, question mark, or
                # number sign
                oldpath_pattern = '^' + re.escape(oldpath) + '(?![^/?#])'
                oldpath_re = re.compile(oldpath_pattern)
                self.path_subs.append((oldpath_re, newpath))

    def convert(self, document):
        parser = self.Parser(self)
        parser.feed(document)
        return ''.join(parser.result)

    class Parser(html.parser.HTMLParser):
        def __init__(self, converter):
            super().__init__(convert_charrefs=False)
            self.result = []
            self.converter = converter

        def handle_starttag(self, tag, attrs):
            self.result.append('<' + tag)
            self._handle_attrs(attrs)
            self.result.append('>')

        def handle_startendtag(self, tag, attrs):
            self.result.append('<' + tag)
            self._handle_attrs(attrs)
            self.result.append('/>')

        def handle_endtag(self, tag):
            self.result.append('</' + tag + '>')

        def handle_data(self, data):
            self.result.append(data)

        def handle_entityref(self, name):
            self.result.append('&' + name + ';')

        def handle_charref(self, name):
            self.result.append('&#' + name + ';')

        def handle_comment(self, data):
            self.result.append('<!--' + data + '-->')

        def _handle_attrs(self, attrs):
            for (name, value) in attrs:
                if value is None:
                    self.result.append(' {}'.format(name))
                else:
                    if name in ('href', 'src'):
                        value = self.converter.convert_url(name, value)
                    if value is not None:
                        self.result.append(' {}="{}"'.format(
                            name, html.escape(value)))

    def convert_url(self, attr_name, url):
        # Join to base_url
        if self.base_url:
            url = urllib.parse.urljoin(self.base_url, url)

        # Remove scheme/netloc if netloc matches my_netloc_re
        (scheme, netloc, path, params, query, fragment) = \
            urllib.parse.urlparse(url)
        if scheme in ('http', 'https') and self.my_netloc_re.fullmatch(netloc):
            url = urllib.parse.urlunparse(('', '', path, params,
                                           query, fragment))
        elif (scheme or netloc) and attr_name == 'src':
            # Discard cross-domain subresources
            return None

        # Apply path substitutions
        for (pattern, replacement) in self.path_subs:
            newurl = pattern.sub(replacement, url)
            if newurl != url:
                return newurl
        return url
