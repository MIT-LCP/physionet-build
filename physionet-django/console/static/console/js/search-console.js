// Script to search lists in the console
// e.g. search users, news items, etc.

function search(url, value){
 var csrftoken = getCookie('csrftoken');
 $.ajax({
         type: "POST",
         url: url,
         data: {'csrfmiddlewaretoken':csrftoken,
                'search': value
         },
         success: function reloadSection(result){
             $("#searchitems").html(result);
         },
 });
}
