import json
import urllib.parse

import ckeditor.fields
from django.conf import settings


def set_saved_fields_cookie(form, form_url, response):
    """
    Set a cookie to indicate that rich text fields have been saved.

    The ckeditor autosave plugin will attempt to automatically save
    form fields that have been modified; once the form is actually
    saved to the server, we want to clear the autosave state so that
    the plugin won't try to restore it when the same form is loaded
    again.

    This requires that:
     - the view that handles the POST request should invoke this
       function on the HTTP response
     - the page that is loaded after submitting the form should
       include /static/custom/js/clear-autosave.js

    form should be the django.forms.Form that was just saved.

    form_url should be the path to the page on which the form fields
    appear (which is usually, but not necessarily, the same as the URL
    to which the form is POSTed.)

    response should be a django.http.HttpResponse.
    """

    # Find all rich text fields in the form
    field_names = []
    for (name, field) in form.fields.items():
        if isinstance(field, ckeditor.fields.RichTextFormField):
            # This is a bit weird and confusing, but I think it's
            # correct: bound_field.id_for_label is the 'id' attribute
            # of the textarea element, and that is what ckeditor uses
            # as 'editor.name', and that is what the autosave plugin
            # uses to construct the local storage key.
            bound_field = field.get_bound_field(form, name)
            html_id = bound_field.id_for_label
            field_names.append(html_id)

    value = json.dumps({'url': form_url, 'fields': field_names})
    value = urllib.parse.quote(value, safe='')
    response.set_cookie('saved_cke_fields', value, max_age=(10 * 60),
                        samesite='strict', secure=(not settings.DEBUG))
    return response
