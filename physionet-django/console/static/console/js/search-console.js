// Script to search lists in the console
// e.g. search users, news items, etc.

function search(url, value){
  var csrftoken = getCookie('csrftoken');
  var data = {'csrfmiddlewaretoken':csrftoken, 'search': value};
  $('#searchitems').load(url, data);
}
