// Script to search lists in the console
// e.g. search users, news items, etc.

// Init a timeout variable to be used below
var loadresults = null;

function search(url, value){
    var csrftoken = getCookie('csrftoken');

    // Clear the timeout if it has already been set.
    // This will prevent the previous task from executing
    // if it has been less than <MILLISECONDS>
    clearTimeout(loadresults);

    // Make a new timeout set to go off in <N>ms
    loadresults = setTimeout(function(){
        var data = {'csrfmiddlewaretoken':csrftoken, 'search': value};
        $('#searchitems').load(url, data);
    }, 500);
}

// Search the submitted-projects page: Displays only the projects
// that match the search and updates each tab's badge count/color to
// reflect how many matches fall in that status/hold bucket.
function searchSubmitted(url, value) {
    var csrftoken = getCookie('csrftoken');

    clearTimeout(loadresults);
    loadresults = setTimeout(function () {

        if (!value.trim()) {
            // Restore all hidden rows, remove messages, restore hidden tables
            $('[data-project-id]').show();
            $('.search-no-results-msg').remove();
            $('.search-hidden-table').show().removeClass('search-hidden-table');
            // Restore original badge counts and colors
            $('[id^="badge-"]').each(function () {
                var original = $(this).data('original');
                var badge = $(this).find('.badge');
                badge.text(original);
                badge.removeClass('badge-success badge-danger badge-info')
                     .addClass(original > 0 ? 'badge-danger' : 'badge-success');
            });
            return;
        }

        $.post(url, { 'csrfmiddlewaretoken': csrftoken, 'search': value }, function (data) {
            var matchingIds = data.ids.map(String);

            // Clean up from any previous search
            $('.search-no-results-msg').remove();
            $('.search-hidden-table').show().removeClass('search-hidden-table');

            // Show/hide rows based on returned ids
            $('[data-project-id]').each(function () {
                var rowId = String($(this).data('project-id'));
                $(this).toggle(matchingIds.includes(rowId));
            });

            // Check each table by comparing its row ids against matchingIds directly,
            // rather than using :visible which is affected by which tab is active
            $('tbody').each(function () {
                var tbody = $(this);
                var table = tbody.closest('table');
                var allRows = tbody.find('[data-project-id]');

                if (allRows.length === 0) return;

                var hasMatch = allRows.filter(function () {
                    return matchingIds.includes(String($(this).data('project-id')));
                }).length > 0;

                if (!hasMatch) {
                    table.addClass('search-hidden-table').hide();
                    table.after(
                        '<p class="search-no-results-msg">' +
                        '<i class="fas fa-check" style="color:green"></i> No projects found.' +
                        '</p>'
                    );
                }
            });

            // Update badge counts and colors
            $.each(data.counts, function (key, count) {
                var badgeWrapper = $('#badge-' + key);
                var badge = badgeWrapper.find('.badge');
                var original = parseInt(badgeWrapper.data('original'));
                badge.text(count);
                badge.removeClass('badge-info badge-danger')
                if (count > 0) {
                    // Results found for this search
                    badge.addClass('badge-danger');
                } else if (original === 0) {
                    // Was already empty before the search
                    badge.addClass('badge-success');
                } else {
                    // Had projects originally but none match the search
                    badge.addClass('badge-info');
                }
            });
        });

    }, 500);
}
