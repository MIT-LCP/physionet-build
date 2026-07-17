import bleach
from django import forms
from django.conf import settings
from django.contrib.admin.widgets import AdminTextareaWidget
from django.db import models
from tinymce.widgets import AdminTinyMCE, TinyMCE

from project.utility import LinkFilter


class SafeHTMLField(models.TextField):
    """
    An HTML text field that permits only "safe" content.

    On the client side, this field is displayed as an interactive
    WYSIWYG editor (TinyMCE.)

    On the server side, the HTML text is "cleaned" using the bleach
    library to ensure that all tags are properly closed, entities are
    well-formed, etc., and to remove or escape any unsafe tags or
    attributes.

    The permitted sets of tags and attributes are defined by
    settings.HTML_ALLOWED_CONTENT.  For example:

        HTML_ALLOWED_CONTENT = {
            'default': {
                'a': {'attributes': ['href']},
                'em': True,
                '*': {'attributes': ['title']},
            },
        }

    This would permit the use of 'a' and 'em' tags (all other tags are
    forbidden.)  'a' tags are permitted to have an 'href' attribute,
    and any tag is permitted to have a 'title' attribute.
    """

    # The following protocols may be used in 'href', 'src', and
    # similar attributes.
    _protocols = ['http', 'https', 'ftp', 'mailto']

    # The following attributes are forbidden on the server side even
    # if permitted on client side.  (This is a kludge; permitting
    # 'width' to be set on the client side makes editing tables
    # easier.)
    _attribute_blacklist = {('table', 'width')}

    # The following CSS properties may be set via inline styles (but
    # only on elements for which the 'style' attribute itself is
    # permitted.)
    _allowed_css_properties = ['text-align']

    def __init__(self, config_name='default', strip=False,
                 strip_comments=True, **kwargs):
        super().__init__(**kwargs)

        # Create a bleach.Cleaner for the allowed content, which is
        # used to clean data (on the server side) when submitting the
        # form.

        allowed_content = settings.HTML_ALLOWED_CONTENT[config_name]
        tags = []
        attrs = {}
        for (tag, props) in allowed_content.items():
            if tag != '*':
                tags.append(tag)
            if isinstance(props, dict) and 'attributes' in props:
                attrs[tag] = []
                for attr in props['attributes']:
                    if (tag, attr) not in self._attribute_blacklist:
                        attrs[tag].append(attr)

        try:
            from bleach.css_sanitizer import CSSSanitizer
            css_kwargs = {
                'css_sanitizer': CSSSanitizer(
                    allowed_css_properties=self._allowed_css_properties,
                ),
            }
        except ImportError:
            css_kwargs = {'styles': self._allowed_css_properties}

        self._cleaner = bleach.Cleaner(tags=tags, attributes=attrs,
                                       **css_kwargs,
                                       protocols=self._protocols,
                                       strip=strip,
                                       strip_comments=strip_comments)

        # Create a corresponding filter expression (for cleaning data
        # on the client side, e.g. when copying/pasting HTML):
        # https://www.tiny.cloud/docs/tinymce/6/content-filtering/#valid_elements
        # For example, "@[title|lang],a[href],em" permits only the 'a'
        # and 'em' tags; 'a' tags are permitted to have an 'href'
        # attribute, and any tag is permitted to have 'title' and/or
        # 'lang' attributes.

        valid_elements = []
        if '*' in attrs:
            valid_elements.append('@[' + '|'.join(attrs['*']) + ']')
        for tag in tags:
            tag_attrs = attrs.get(tag)
            if tag_attrs:
                expr = tag + '[' + '|'.join(tag_attrs) + ']'
            else:
                expr = tag
            valid_elements.append(expr)

        self._widget_mce_attrs = {
            'valid_elements': ','.join(valid_elements)
        }

    def formfield(self, widget=None, **kwargs):
        widget = widget or TinyMCE
        if widget == AdminTextareaWidget:
            widget = AdminTinyMCE
        if isinstance(widget, type) and issubclass(widget, TinyMCE):
            widget = widget(mce_attrs=self._widget_mce_attrs)
        return super().formfield(widget=widget, **kwargs)

    def clean(self, value, model_instance):
        value = self._cleaner.clean(value)

        # Remove scheme/hostname from internal links, and forbid
        # external subresources
        lf = LinkFilter()
        value = lf.convert(value)

        return super().clean(value, model_instance)
