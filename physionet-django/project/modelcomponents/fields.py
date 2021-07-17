import ckeditor.fields

import bleach
from django.conf import settings

from project.utility import LinkFilter


class SafeHTMLField(ckeditor.fields.RichTextField):
    """
    An HTML text field that permits only "safe" content.

    On the client side, this field is displayed as an interactive
    WYSIWYG editor (see ckeditor.fields.RichTextField.)

    On the server side, the HTML text is "cleaned" using the bleach
    library to ensure that all tags are properly closed, entities are
    well-formed, etc., and to remove or escape any unsafe tags or
    attributes.

    The permitted set of tags and attributes is generated from the
    corresponding 'allowedContent' rules in settings.CKEDITOR_CONFIGS
    (which also defines the client-side whitelisting rules and the set
    of options that are visible to the user.)  For example:

        'allowedContent': {
            'a': {'attributes': ['href']},
            'em': True,
            '*': {'attributes': ['title']},
        }

    This would permit the use of 'a' and 'em' tags (all other tags are
    forbidden.)  'a' tags are permitted to have an 'href' attribute,
    and any tag is permitted to have a 'title' attribute.

    NOTE: This class does not use ckeditor's 'disallowedContent'
    rules.  Those rules can be used to perform tag/attribute
    blacklisting on the client side, but will not be enforced on the
    server side.
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
    _styles = ['text-align']

    def __init__(self, config_name='default', strip=False,
                 strip_comments=True, **kwargs):
        super().__init__(config_name=config_name, **kwargs)

        conf = settings.CKEDITOR_CONFIGS[config_name]
        tags = []
        attrs = {}
        for (tag, props) in conf['allowedContent'].items():
            if tag != '*':
                tags.append(tag)
            if isinstance(props, dict) and 'attributes' in props:
                attrs[tag] = []
                for attr in props['attributes']:
                    if (tag, attr) not in self._attribute_blacklist:
                        attrs[tag].append(attr)

        self._cleaner = bleach.Cleaner(tags=tags, attributes=attrs,
                                       styles=self._styles,
                                       protocols=self._protocols,
                                       strip=strip,
                                       strip_comments=strip_comments)

    def clean(self, value, model_instance):
        value = self._cleaner.clean(value)

        # Remove scheme/hostname from internal links, and forbid
        # external subresources
        lf = LinkFilter()
        value = lf.convert(value)

        return super().clean(value, model_instance)
