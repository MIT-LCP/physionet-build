// Scripts for the reference forms (project/reference_form.html). The DOI
// lookup is in doi-lookup.js. Handlers are delegated so that they work
// for reference forms added or reloaded after the page loads.

// Copy a reference's citation key, e.g. "[@moody2001]", to paste into
// the description.
$(document).on('click', '.reference-copy-key', function() {
  var button = $(this);
  navigator.clipboard.writeText(button.data('cite')).then(function() {
    button.text('Copied');
    setTimeout(function() { button.text('Copy'); }, 1500);
  });
});
