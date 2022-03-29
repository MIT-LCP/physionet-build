// Scripts for adding and removing formset forms dynamically via js
// and/or AJAX

/** Clone a form element to a formset

 @constructor
 @param {string} selector - The selector used to get the element to clone.
 @param {string} form_name - The name of the forms. May be more complicated
 for modelforms, inline_formsets, and genericinline_formsets.
*/
function cloneFormElement(selector, form_name){
  var newElement = $(selector).clone(true);
  var total_forms = $('#id_' + form_name + '-TOTAL_FORMS').val();

  // Set the names and ids of each input element of the new form
  newElement.find('input, select').each(function() {
      var name = $(this).attr('name').replace('-' + (total_forms-1) + '-', '-' + total_forms + '-');
      var id = 'id_' + name;
      // What about the actual object id hidden input?
      
      $(this).attr({'name': name, 'id': id}).val('').removeAttr('checked');
  });

  newElement.find('span').remove();
  // Update the formset total forms indicator
  $('#id_' + form_name + '-TOTAL_FORMS').val(++total_forms);
  // Insert the new content after the original selected content
  $(selector).after(newElement);
}


// Add another form to a formset
function addItem(trigger_button, item, form_name, max_forms, add_item_url){
  var total_forms = parseInt($('#id_' + form_name + '-TOTAL_FORMS').val())

  if (total_forms < max_forms){
    if (total_forms > 0){
      // Clone the existing html
      cloneFormElement("." + item + "-body:last", form_name);
      // Change the number id and display label of the newly cloned element
      new_item_div = document.getElementsByClassName(item + "-body")[total_forms];
      total_forms++;
      new_item_div.id = item + "-" + (total_forms);
      new_item_div.getElementsByClassName(item + "-number")[0].innerHTML = total_forms + ".";
      if (total_forms == max_forms){
        trigger_button.disabled = true;
      }
    }
    // Reload the item list section with an additional form
    else{
      var csrftoken = getCookie('csrftoken');
      $.ajax({
              type: "GET",
              url: add_item_url,
              data: {'csrfmiddlewaretoken':csrftoken,
                     'add_first':true, 'item':item
              },
              success: function reloadSection(result){
                  $("#" + item + "-list").replaceWith(result);
                  $('[data-toggle="popover"]').popover();
                  if (max_forms == 1) {
                    document.getElementById("add-" + item + "-button").disabled = true;
                  }
              },
      });
    }
  }
};

// Delete a form from a formset, and possibly an associated object
function removeItem(trigger_button, item, form_name, remove_item_url){
  // The div encapsulating the entire item element
  var item_div = trigger_button.parentElement.parentElement;
  // The div containing the form input elements
  var form_div = item_div.getElementsByClassName(item + "-form")[0];
  // Get the item instance id if it exists, ie. it is already saved
  for (i=0; i<form_div.children.length; i++) {
    form_input = form_div.children[i];
    if (form_input.id.startsWith('id') && form_input.id.endsWith('id')) {
      var item_instance_id = form_input.value;
    }
  }
  // The object has not been saved. Just edit html.
  if (item_instance_id == ""){
    // The item/form number on the page to be deleted. The div id is
    // {{ item }}-%d
    var item_number = parseInt(item_div.id.substring(item.length + 1));
    var item_list_div = item_div.parentElement;
    var total_forms = item_list_div.getElementsByClassName(item + "-body").length;
    // delete the selected item's html
    item_div.remove();
    // All item forms with greater numbers must be decremented
    for (i=item_number+1; i<total_forms+1; i++){
      var higher_item_div = document.getElementById(item + "-" + i);
      higher_item_div.getElementsByClassName(item + "-number")[0].innerHTML = (i-1) + ".";
      higher_item_div.id = item + "-" + (i-1);
    }
    // update the form count
    total_forms--;
    $('#id_' + form_name + '-TOTAL_FORMS').val(total_forms);
    document.getElementById('add-' + item + '-button').disabled = false;
  }
  // The item object exists. Send ajax query to remove it and
  // reload the page section.
  else{
    var csrftoken = getCookie('csrftoken');
    $.ajax({
            type: "POST",
            url: remove_item_url,
            data: {'csrfmiddlewaretoken':csrftoken, 'item':item,
                   'remove_id':item_instance_id
            },
            success: function reloadSection(result){
                $("#" + item + "-list").replaceWith(result);
                $('[data-toggle="popover"]').popover()
            },
    });
  }
};


// Block submission of a formset if there are duplicate items
function validateItems(list_div_id, input_id_suffix, item_name) {
  item_div = document.getElementById(list_div_id);
  item_inputs = item_div.getElementsByTagName("input");
  var counts = {};

  for (var i=0; i < item_inputs.length; i++) {
      if (item_inputs[i].id.endsWith(input_id_suffix) && item_inputs[i].value){
        if (counts[item_inputs[i].value] === undefined) {
          counts[item_inputs[i].value] = 1;
        }
        else{
           item_inputs[i].select();
           alert(item_name + " must be unique");
           return false;
        }
    }
  }
  return true;
}


// Disable the dynamic formset add buttons, if the number of forms
// matches the max number of forms. Called once when page loads.
function disableAddButtons() {
  var maxFormInputs = $( "input[name$='MAX_NUM_FORMS']" );
  for (var i = 0; i < maxFormInputs.length; i += 1) {
    var maxFormInput = maxFormInputs[i];
    var itemListDiv = maxFormInput.parentElement;
    var totalFormInput = itemListDiv.querySelector("[name$=TOTAL_FORMS]");
    if (totalFormInput.value == maxFormInput.value) {
      itemListDiv.querySelector("[id$=-button]").disabled = true;
    }

  }

}
