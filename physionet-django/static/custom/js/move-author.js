// Reorder a project's authors and replace the author-list fragment.
function moveAuthor(authorId, direction) {
  var $authorList = $('#author-list');

  $.ajax({
    type: 'POST',
    url: $authorList.data('move-author-url'),
    data: {
      csrfmiddlewaretoken: getCookie('csrftoken'),
      author_id: authorId,
      direction: direction
    },
    success: function(result) {
      $('#author-list-error').remove();
      $authorList.replaceWith(result);
    },
    error: function() {
      $('#author-list-error').remove();
      $authorList.before(
        '<div id="author-list-error" class="alert alert-danger" role="alert">'
        + 'Unable to reorder authors. Please reload the page and try again.</div>'
      );
    }
  });
}
