// Fill in a citation from its DOI, for the reference forms and the
// publication form. The DOI box is rendered by DoiLookupInput, and the
// lookup URL is in its data-lookup-url attribute.
//
// Handlers are delegated so that they work for forms added or reloaded
// after the page loads.

// The form that a DOI box belongs to, and its citation and URL inputs
// (references have no URL input, since their URL comes from the DOI)
function doiLookupForm(element) {
  var form = element.closest('.reference-form, .publication-form');
  return {
    doi: form.find('input[name$="-doi"]'),
    status: form.find('.doi-lookup-status'),
    citation: form.find('[name$="-description"], [name$="-citation"]'),
    url: form.find('input[name$="-url"]'),
    button: form.find('.doi-lookup-button'),
  };
}

function setDoiLookupStatus(status, message, isError) {
  status.empty().removeClass('text-danger text-muted');
  status.addClass(isError ? 'text-danger' : 'text-muted');
  status.text(message);
}

// Fill in the citation, and the URL if it is blank
function fillFromDoi(form, data) {
  form.citation.val(data.citation);
  var message = 'Citation filled in from doi.org. Please check it before saving.';
  if (form.url.length && !$.trim(form.url.val())) {
    form.url.val(data.url);
    message = 'Citation and URL filled in from doi.org. Please check them before saving.';
  }
  setDoiLookupStatus(form.status, message, false);
}

function lookupDoi(button) {
  var form = doiLookupForm(button);
  var doi = $.trim(form.doi.val());

  if (!doi) {
    setDoiLookupStatus(form.status, 'Enter a DOI first.', true);
    return;
  }

  button.prop('disabled', true);
  setDoiLookupStatus(form.status, 'Looking up citation...', false);

  $.getJSON(form.doi.data('lookup-url'), {doi: doi})
    .done(function(data) {
      if (data.error) {
        setDoiLookupStatus(form.status, data.error, true);
        return;
      }
      form.doi.val(data.doi);
      var current = $.trim(form.citation.val());
      if (!current || current === data.citation) {
        fillFromDoi(form, data);
        return;
      }
      // Don't overwrite a citation the author has written: offer it instead.
      setDoiLookupStatus(form.status, 'doi.org gives this citation: ', false);
      form.status.append($('<q>').text(data.citation)).append(' ');
      $('<button type="button" class="btn btn-link btn-sm p-0 align-baseline">Use this citation</button>')
        .on('click', function() {
          fillFromDoi(form, data);
        })
        .appendTo(form.status);
    })
    .fail(function() {
      setDoiLookupStatus(form.status, 'Could not look up this DOI. Please try again later.', true);
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
    lookupDoi(doiLookupForm($(this)).button);
  }
});
