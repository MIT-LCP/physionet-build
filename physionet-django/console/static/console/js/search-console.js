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