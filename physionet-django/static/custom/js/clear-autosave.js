// Remove data saved by the TinyMCE autosave plugin once the server
// has acknowledged that the form has been saved.
// Requires: /static/custom/js/cookie.js
(function() {
    'use strict';

    // The saved_cke_fields cookie should contain a URL-encoded JSON
    // object such as
    // {"url": "/projects/create/", "fields": ["id_abstract"]}
    var saved = getCookie('saved_cke_fields');
    if (saved !== null) {
        saved = JSON.parse(saved);

        // convert to absolute URL
        var a = document.createElement('a');
        a.href = saved.url;
        var form_url = a.href;

        for (var i = 0; i < saved.fields.length; i++) {
            var field = saved.fields[i];

            // TinyMCE: Each field is saved under a key such as
            // tinymce-autosave-/projects/create/-id_abstract-draft and
            // tinymce-autosave-/projects/create/-id_abstract-time

            // CKEditor 4 (obsolete): Each field is saved under a key such
            // as autosave_https://physionet.org/projects/create/_id_abstract

            var keys = [
                'tinymce-autosave-' + saved.url + '-' + field + '-draft',
                'tinymce-autosave-' + saved.url + '-' + field + '-time',
                'autosave_' + form_url + '_' + field,
            ];
            for (var j = 0; j < keys.length; j++) {
                try {
                    localStorage.removeItem(keys[j]);
                }
                catch (e) {
                }
            }
        }
    }
    document.cookie = 'saved_cke_fields=;path=/;SameSite=strict;' +
        'expires=Thu, 01 Jan 1970 00:00:00 GMT';
})();
