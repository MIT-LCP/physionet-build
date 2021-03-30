// Remove data saved by the ckeditor autosave plugin once the server
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

        // Each field is saved under a key such as
        // autosave_https://physionet.org/projects/create/_abstract
        // (see /static/ckeditor/ckeditor/plugins/autosave/plugin.js)
        for (var i = 0; i < saved.fields.length; i++) {
            var field = saved.fields[i];
            var key = 'autosave_' + form_url + '_' + field;
            try {
                localStorage.removeItem(key);
            }
            catch (e) {
            }
        }
    }
    document.cookie = 'saved_cke_fields=;path=/;SameSite=strict;' +
        'expires=Thu, 01 Jan 1970 00:00:00 GMT';
})();
