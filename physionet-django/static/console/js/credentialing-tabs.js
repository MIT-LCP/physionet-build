$(function () {
  const targets = ['#credential-trends', '#credential-queue', '#repeated-applications', '#credential-annual'];
  const selected = !$('#metrics-period').data('invalid') && targets.includes(window.location.hash)
    ? window.location.hash : '#credential-trends';
  function showPeriod(target) {
    $('#metrics-period').prop('hidden', target === '#credential-queue' || target === '#credential-annual');
  }
  showPeriod(selected);
  $('#operational-date-form').attr('action', selected);
  $('a[data-toggle="tab"][href="' + selected + '"]').tab('show');
  $('a[data-toggle="tab"]').on('shown.bs.tab', function (event) {
    if (!targets.includes(event.target.hash)) return;
    history.replaceState(null, '', event.target.hash);
    showPeriod(event.target.hash);
    $('#operational-date-form').attr('action', event.target.hash);
  });
});
