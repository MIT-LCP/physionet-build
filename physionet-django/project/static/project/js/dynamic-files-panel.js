(function() {
    'use strict';

    var panel = $('#files-panel');
    var cur_dir = panel.find('[data-dfp-cur-dir]').data('dfp-cur-dir');
    var panel_url = panel.find('[data-dfp-panel-url]').data('dfp-panel-url');

    function navigateDir(subdir, page_url, push_history) {
        $.ajax({
            type: 'GET',
            url: panel_url,
            data: {'subdir': subdir, 'v': '2'},
            success: function(result) {
                if (push_history)
                    history.pushState(subdir, '', page_url);
                else
                    history.replaceState(subdir, '', page_url);
                panel.html(result);
                setClickHandlers();
            },
        });
    }

    function setClickHandlers() {
        panel.find('a[data-dfp-dir]').click(function(event) {
            navigateDir($(this).data('dfp-dir'), this.href, true);
            event.preventDefault();
        });
    }
    setClickHandlers();

    window.onpopstate = function(event) {
        if (event.state !== null) {
            navigateDir(event.state, window.location, false);
        }
    };
    history.replaceState(cur_dir, '');
})();
