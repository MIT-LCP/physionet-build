// Script to search lists in the console
// e.g. search users, news items, etc.

function search(args){
 var csrftoken = getCookie('csrftoken');
 $.ajax({
         type: "POST",
         url: args[0],
         data: {'csrfmiddlewaretoken':csrftoken,
                'search':args[1]
         },
         success: function reloadSection(result){
             $("#searchitems").html(result);
         },
 });
}
