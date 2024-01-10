import functools

from django.conf import settings
from django.urls import get_resolver, reverse
from django.utils.translation import gettext_lazy as _

from physionet.settings.base import StorageTypes


class NavLink:
    """
    A link to be displayed in the navigation menu.

    The exact URL of the link is determined by reversing the view
    name.

    The use of view_args is deprecated, and provided for compatibility
    with existing views that require a static URL argument.  Don't use
    view_args for newly added items.

    The link will only be displayed in the menu if the logged-in user
    has permission to access that URL.  This means that the
    corresponding view function must be decorated with the
    console_permission_required decorator.

    The link will appear as "active" if the request URL matches the
    link URL or a descendant.
    """
    def __init__(self, title, view_name, icon=None, *,
                 enabled=True, view_args=()):
        self.title = title
        self.icon = icon
        self.enabled = enabled
        self.view_name = view_name
        self.view_args = view_args
        if self.view_args:
            self.name = self.view_name + '__' + '_'.join(self.view_args)
        else:
            self.name = self.view_name

    @functools.cached_property
    def url(self):
        return reverse(self.view_name, args=self.view_args)

    @functools.cached_property
    def required_permission(self):
        view = get_resolver().resolve(self.url).func
        return view.required_permission

    def is_visible(self, request):
        return self.enabled and request.user.has_perm(self.required_permission)

    def is_active(self, request):
        return request.path.startswith(self.url)


class NavHomeLink(NavLink):
    """
    Variant of NavLink that does not include sub-pages.
    """
    def is_active(self, request):
        return request.path == self.url


class NavSubmenu:
    """
    A collection of links to be displayed as a submenu.
    """
    def __init__(self, title, name, icon=None, items=[]):
        self.title = title
        self.name = name
        self.icon = icon
        self.items = items


class NavMenu:
    """
    A collection of links and submenus for navigation.
    """
    def __init__(self, items):
        self.items = items

    def get_menu_items(self, request):
        """
        Return the navigation menu items for an HTTP request.

        This returns a list of dictionaries, each of which represents
        either a page link or a submenu.

        For a page link, the dictionary contains:
         - 'title': human readable title
         - 'name': unique name (corresponding to the view name)
         - 'icon': icon name
         - 'url': page URL
         - 'active': true if this page is currently active

        For a submenu, the dictionary contains:
         - 'title': human readable title
         - 'name': unique name
         - 'icon': icon name
         - 'subitems': list of page links
         - 'active': true if this submenu is currently active
        """
        visible_items = []

        for item in self.items:
            if isinstance(item, NavSubmenu):
                subitems = item.items
            elif isinstance(item, NavLink):
                subitems = [item]
            else:
                raise TypeError(item)

            visible_subitems = []
            active = False
            for subitem in subitems:
                if subitem.is_visible(request):
                    subitem_active = subitem.is_active(request)
                    active = active or subitem_active
                    visible_subitems.append({
                        'title': subitem.title,
                        'name': subitem.name,
                        'icon': subitem.icon,
                        'url': subitem.url,
                        'active': subitem_active,
                    })

            if visible_subitems:
                if isinstance(item, NavSubmenu):
                    visible_items.append({
                        'title': item.title,
                        'name': item.name,
                        'icon': item.icon,
                        'subitems': visible_subitems,
                        'active': active,
                    })
                else:
                    visible_items += visible_subitems

        return visible_items


CONSOLE_NAV_MENU = NavMenu([
    NavHomeLink(_('Home'), 'console_home', 'book-open'),

    NavLink(_('Editor Home'), 'editor_home', 'book-open'),

    NavSubmenu(_('Projects'), 'projects', 'clipboard-list', [
        NavLink(_('Unsubmitted'), 'unsubmitted_projects'),
        NavLink(_('Submitted'), 'submitted_projects'),
        NavLink(_('Published'), 'published_projects'),
        NavLink(_('Archived'), 'archived_submissions'),
    ]),

    NavLink(_('Storage'), 'storage_requests', 'cube'),

    NavSubmenu(_('Cloud'), 'cloud', 'cloud', [
        NavLink(_('Mirrors'), 'cloud_mirrors'),
    ]),

    NavSubmenu(_('Identity check'), 'identity', 'hand-paper', [
        NavLink(_('Processing'), 'credential_processing'),
        NavLink(_('All Applications'), 'credential_applications',
                view_args=['successful']),
        NavLink(_('Known References'), 'known_references'),
    ]),

    NavLink(_('Training check'), 'training_list', 'school',
            view_args=['review']),

    NavSubmenu(_('Events'), 'events', 'clipboard-list', [
        NavLink(_('Active'), 'event_active'),
        NavLink(_('Archived'), 'event_archive'),
    ]),

    NavSubmenu(_('Legal'), 'legal', 'handshake', [
        NavLink(_('Licenses'), 'license_list'),
        NavLink(_('DUAs'), 'dua_list'),
        NavLink(_('Code of Conduct'), 'code_of_conduct_list'),
        NavLink(_('Event Agreements'), 'event_agreement_list'),
    ]),

    NavSubmenu(_('Logs'), 'logs', 'fingerprint', [
        NavLink(_('Project Logs'), 'project_access_logs'),
        NavLink(_('Access Requests'), 'project_access_requests_list'),
        NavLink(_('User Logs'), 'user_access_logs'),
        NavLink(_('GCP Logs'), 'gcp_signed_urls_logs',
                enabled=(settings.STORAGE_TYPE == StorageTypes.GCP)),
    ]),

    NavSubmenu(_('Users'), 'users', 'user-check', [
        NavLink(_('Active Users'), 'users', view_args=['active']),
        NavLink(_('Inactive Users'), 'users', view_args=['inactive']),
        NavLink(_('All Users'), 'users', view_args=['all']),
        NavLink(_('User Groups'), 'user_groups'),
        NavLink(_('Administrators'), 'users', view_args=['admin']),
    ]),

    NavLink(_('Featured Content'), 'featured_content', 'star'),

    NavSubmenu(_('Guidelines'), 'guidelines', 'book', [
        NavLink(_('Project review'), 'guidelines_review'),
    ]),

    NavSubmenu(_('Usage Stats'), 'stats', 'chart-area', [
        NavLink(_('Editorial'), 'editorial_stats'),
        NavLink(_('Credentialing'), 'credentialing_stats'),
        NavLink(_('Submissions'), 'submission_stats'),
    ]),

    NavSubmenu(_('Pages'), 'pages', 'window-maximize', [
        NavLink(_('Static Pages'), 'static_pages'),
        NavLink(_('Frontpage Buttons'), 'frontpage_buttons'),
        NavLink(_('Redirects'), 'redirects'),
    ]),

    NavLink(_('News'), 'news_console', 'newspaper'),
])
