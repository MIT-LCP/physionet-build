"""Chart presentations of the existing credentialing aggregates and CSVs."""
from copy import deepcopy

from django.utils import timezone

from console.credential_metrics import (
    credential_annual_report, credential_flow_report, credential_queue_summary,
    credential_reapplication_reports, credential_stage_report, credential_trend,
)

COLORS = ['#2563eb', '#ea580c', '#15803d', '#b91c1c', '#7c3aed']
MARKERS = ['circle', 'square', 'triangle', 'diamond', 'plus']


def chart_report(report, columns=None, chart_type=None, integer=False):
    report = deepcopy(report)
    if columns is not None:
        report['chart'] = {
            'labels': [str(row[0]) for row in report['rows']], 'integer': integer,
            'series': [{'name': name, 'values': [row[index] for row in report['rows']]}
                       for name, index in columns],
        }
    chart = report['chart']
    if chart_type:
        chart['type'] = chart_type
    chart.update({'plot_height': 300, 'line_width': 2,
                  'interactive_legend': len(chart['series']) > 1, 'legend_title': 'Visible series'})
    for index, series in enumerate(chart['series']):
        series.update({'color': COLORS[index % len(COLORS)], 'marker': MARKERS[index % len(MARKERS)]})
    return report


def credential_chart_panels(start, end, stats, now):
    monthly = chart_report(credential_trend(start, end))
    flow = chart_report(credential_flow_report(start, end))
    for report in (monthly, flow):
        report['chart'].update({'period_unit': 'month', 'partial_through': end.isoformat()})
        report['export'] = 'monthly' if report is monthly else 'flow'
        report['start_date'], report['end_date'] = start, end
    stages = chart_report(credential_stage_report(start, end),
                          [('Median days', 2), ('P90 days', 3)], 'horizontal-bar')
    stages['export'] = 'stages'
    stages['start_date'], stages['end_date'] = start, end
    queue = chart_report(credential_queue_summary(now),
                         [('Under 7 days', 1), ('7–29 days', 2), ('30–89 days', 3), ('90+ days', 4)],
                         'horizontal-stacked-bar', integer=True)
    # The total is retained in the table and CSV, not plotted as a fourth stage.
    queue['chart']['labels'] = queue['chart']['labels'][:-1]
    for series in queue['chart']['series']:
        series['values'] = series['values'][:-1]
    queue['export'] = 'queue-summary'
    queue['snapshot'] = now
    queue['start_date'] = queue['end_date'] = timezone.localdate(now)
    repeated = []
    for index, table in enumerate(credential_reapplication_reports(start, end)):
        table = chart_report(table, [('People', 1)], 'horizontal-bar', integer=True)
        table['export'] = f'reapplication-{index + 1}'
        table['start_date'], table['end_date'] = start, end
        repeated.append(table)
    annual = credential_annual_report(stats)
    definitions = (
        'All application years in the site time zone, using each application’s current status. '
        'Years use the site time zone, which can differ from UTC near New Year. '
        'Recent cohorts are incomplete. Approved includes accepted and later-revoked credentials; '
        'handled = accepted + revoked + rejected. Pending and withdrawn applications are excluded from '
        'decision times. Missing or negative timestamp pairs are excluded. Each interval uses its own '
        'observations; medians are not additive. Counts, valid observation counts (n), and coverage '
        'are retained in the tables and CSV. Reference response is measured in hours; other times are days.'
    )
    annual_specs = [
        ('credentialing-annual-outcomes', 'Applications by current status and submission year',
         [('Accepted', 2), ('Revoked', 3), ('Rejected', 4), ('Withdrawn', 5), ('Pending', 6)], 'stacked-bar', True),
        ('credentialing-annual-approval-share', 'Ever approved among handled applications by submission year (%)',
         [('Ever approved among handled (%)', 8)], None, False),
        ('credentialing-annual-days', 'Median processing times by application year (days)',
         [('Decision median days', 9), ('Reference contact median days', 11)], None, False),
        ('credentialing-annual-response', 'Median reference response by application year (hours)',
         [('Reference response median hours', 13)], None, False),
    ]
    annual_panels = []
    for identifier, title, columns, kind, integer in annual_specs:
        report = chart_report({**annual, 'id': identifier, 'title': title, 'description': definitions,
                               'summary': 'All application years; the selected dates do not filter these cohorts.'},
                              columns, kind, integer)
        report['chart'].update({'partial': [year == timezone.localdate(now).year for year in stats],
                                'period_unit': 'year', 'partial_through': timezone.localdate(now).isoformat()})
        report['export'] = identifier.removeprefix('credentialing-')
        report['start_date'] = None
        report['end_date'] = None
        annual_panels.append(report)
    return {'monthly_panels': [monthly, flow, stages], 'queue_panel': queue,
            'reapplication_panels': repeated, 'annual_panels': annual_panels,
            'annual_definition': definitions}
