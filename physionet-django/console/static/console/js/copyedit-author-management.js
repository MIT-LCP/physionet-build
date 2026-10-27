document.addEventListener('DOMContentLoaded', function() {
  if (window.location.hash) {
    document.querySelectorAll('.nav-tabs a[data-toggle="tab"]').forEach(
      function(tab) {
        if (tab.getAttribute('href') === window.location.hash) {
          $(tab).tab('show');
        }
      });
  }

  var authorList = document.getElementById('author-list');
  var orderForm = document.getElementById('save-author-order-form');
  var orderButton = document.getElementById('save-author-order-button');
  if (!authorList || !orderForm || !orderButton) return;
  var authorOrderChanged = false;

  function markAuthorOrderChanged() {
    authorOrderChanged = true;
    orderButton.classList.remove('btn-primary');
    orderButton.classList.add('btn-warning');
  }

  window.addEventListener('beforeunload', function(event) {
    if (!authorOrderChanged) return;
    event.preventDefault();
    event.returnValue = '';
  });

  function updateAuthorControls() {
    var authors = authorList.querySelectorAll('[data-author-id]');
    authors.forEach(function(author, index) {
      [['up', index === 0], ['down', index === authors.length - 1]].forEach(
        function(control) {
          var button = author.querySelector(
            '[data-editor-direction="' + control[0] + '"]');
          button.disabled = control[1];
          button.style.color = control[1] ? 'white' : '';
        });
    });
  }

  authorList.addEventListener('click', function(event) {
    var button = event.target.closest('[data-editor-direction]');
    if (!button) return;
    var author = button.closest('[data-author-id]');
    var sibling = button.dataset.editorDirection === 'up'
      ? author.previousElementSibling : author.nextElementSibling;
    if (!sibling) return;
    if (button.dataset.editorDirection === 'up') {
      author.parentNode.insertBefore(author, sibling);
    } else {
      author.parentNode.insertBefore(sibling, author);
    }
    updateAuthorControls();
    markAuthorOrderChanged();
  });

  orderForm.addEventListener('submit', function() {
    authorOrderChanged = false;
    orderForm.querySelectorAll('input[name="author_order"]').forEach(function(input) {
      input.remove();
    });
    authorList.querySelectorAll('[data-author-id]').forEach(function(author) {
      var input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'author_order';
      input.value = author.dataset.authorId;
      orderForm.appendChild(input);
    });
  });
});
