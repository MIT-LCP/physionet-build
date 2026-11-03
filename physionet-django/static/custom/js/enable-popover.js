// Enables popovers (help text, author info).
// Popovers open on click, and close when clicking elsewhere, pressing
// Escape, or opening another popover.
(function ($) {
  var SELECTOR = '[data-toggle="popover"]';

  function hideAllExcept(keep) {
    $(SELECTOR).each(function () {
      if (this !== keep && $(this).attr('aria-expanded') === 'true') {
        $(this).popover('hide');
      }
    });
  }

  // Initialise popovers inside `root` (defaults to the whole page).
  // Safe to call again after adding new content.
  window.enablePopovers = function (root) {
    $(root || document).find(SELECTOR).popover();
  };

  $(function () {
    window.enablePopovers();

    $(document)
      .on('show.bs.popover', SELECTOR, function () {
        hideAllExcept(this);
      })
      .on('shown.bs.popover', SELECTOR, function () {
        $(this).attr('aria-expanded', 'true');
      })
      .on('hidden.bs.popover', SELECTOR, function () {
        $(this).attr('aria-expanded', 'false');
      })
      // Close when clicking outside both the trigger and the popover,
      // so links inside the popover still work.
      .on('click', function (e) {
        var $target = $(e.target);
        if ($target.closest(SELECTOR).length || $target.closest('.popover').length) {
          return;
        }
        hideAllExcept(null);
      })
      .on('keydown', function (e) {
        if (e.key === 'Escape' || e.keyCode === 27) {
          var $open = $(SELECTOR + '[aria-expanded="true"]');
          if ($open.length) {
            hideAllExcept(null);
            $open.first().trigger('focus');
          }
        }
      });

    // Clicks inside iframes (e.g. rich text editors) don't reach the
    // document, but they do blur the window.
    $(window).on('blur', function () {
      hideAllExcept(null);
    });
  });
})(jQuery);
