$(function () {
  const targets = ['#credential-trends', '#credential-queue', '#repeated-applications', '#credential-annual'];
  const selected = targets.includes(window.location.hash) ? window.location.hash : '#credential-trends';
  $('#operational-date-form').attr('action', selected);
  $('a[data-toggle="tab"][href="' + selected + '"]').tab('show');
  $('a[data-toggle="tab"]').on('shown.bs.tab', function (event) {
    if (!targets.includes(event.target.hash)) return;
    history.replaceState(null, '', event.target.hash);
    $('#operational-date-form').attr('action', event.target.hash);
  });
});
