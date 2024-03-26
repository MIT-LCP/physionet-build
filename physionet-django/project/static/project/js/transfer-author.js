$(document).ready(function() {
  // Function to update the displayed author name when a new author is selected
  function set_transfer_author() {
    var selectedAuthorName = $("#transfer_author_id option:selected").text();
    $('#project_author').text(selectedAuthorName);
  }

  // Attach the change event to the author select dropdown to update the name on change
  $("#transfer_author_id").change(set_transfer_author);

  // Prevent the default form submission and show the confirmation modal
  $('#authorTransferForm').on('submit', function(e) {
    e.preventDefault();
    $('#transfer_author_modal').modal('show');
  });

  // When the confirmation button is clicked, submit the form
  $('#confirmAuthorTransfer').on('click', function() {
    $('#authorTransferForm').off('submit').submit();
  });
});

