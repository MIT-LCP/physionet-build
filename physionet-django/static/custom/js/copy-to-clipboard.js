function copyToClipboard(str){
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(str);
  } else {
    var el = document.createElement('textarea');
    el.value = str;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
  }
}

document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.btn-copy-bibtex').forEach(function(btn) {
    var originalHTML = btn.innerHTML;
    var timer;
    btn.addEventListener('click', function() {
      var targetId = btn.getAttribute('data-clipboard-target');
      var text = document.getElementById(targetId).value;
      copyToClipboard(text);

      if (btn.classList.contains('btn-copy-bibtex-modal')) {
        btn.textContent = 'Copied!';
      } else {
        btn.innerHTML = '<i class="bi bi-check"></i> Copied';
      }
      clearTimeout(timer);
      timer = setTimeout(function() { btn.innerHTML = originalHTML; }, 2000);
    });
  });
});
