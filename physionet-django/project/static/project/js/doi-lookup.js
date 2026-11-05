// Fill in a reference's citation from its DOI, using the lookup URL in
// the DOI input's data-lookup-url attribute. Handlers are delegated so
// that they work for reference forms added or reloaded after page load.

function setDoiLookupStatus(status, message, isError) {
  status.empty().removeClass('text-danger text-muted');
  status.addClass(isError ? 'text-danger' : 'text-muted');
  status.text(message);
}

function lookupDoi(button) {
  var doiInput = button.siblings('input[name$="-doi"]');
  var status = button.siblings('.doi-lookup-status');
  var citationInput = button.closest('.reference-form').find('input[name$="-description"]');
  var doi = $.trim(doiInput.val());

  if (!doi) {
    setDoiLookupStatus(status, 'Enter a DOI first.', true);
    return;
  }

  button.prop('disabled', true);
  setDoiLookupStatus(status, 'Looking up citation...', false);

  $.getJSON(doiInput.data('lookup-url'), {doi: doi})
    .done(function(data) {
      if (data.error) {
        setDoiLookupStatus(status, data.error, true);
        return;
      }
      doiInput.val(data.doi);
      var current = $.trim(citationInput.val());
      if (!current || current === data.citation) {
        citationInput.val(data.citation);
        setDoiLookupStatus(status, 'Citation filled in from doi.org. Please check it before saving.', false);
        return;
      }
      // Don't overwrite a citation the author has written: offer it instead.
      setDoiLookupStatus(status, 'doi.org gives this citation: ', false);
      status.append($('<q>').text(data.citation)).append(' ');
      $('<button type="button" class="btn btn-link btn-sm p-0 align-baseline">Use this citation</button>')
        .on('click', function() {
          citationInput.val(data.citation);
          setDoiLookupStatus(status, 'Citation filled in from doi.org. Please check it before saving.', false);
        })
        .appendTo(status);
    })
    .fail(function() {
      setDoiLookupStatus(status, 'Could not look up this DOI. Please try again later.', true);
    })
    .always(function() {
      button.prop('disabled', false);
    });
}

$(document).on('click', '.doi-lookup-button', function() {
  lookupDoi($(this));
});

// Pressing Enter in the DOI box looks up the citation, instead of
// submitting the whole form.
$(document).on('keydown', 'input[name$="-doi"]', function(event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    lookupDoi($(this).siblings('.doi-lookup-button'));
  }
});
