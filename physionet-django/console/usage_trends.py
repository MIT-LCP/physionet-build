"""Monthly registered dataset viewing, attributed to session start dates."""
import csv
from calendar import monthrange
from collections import Counter

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone

from console.usage import _demographics, dataset_logs
from project.models import PublishedProject
from user.models import COUNTRIES, CredentialApplication, User


def usage_trends(start_date, end_date):
    logs = dataset_logs(start_date, end_date)
    counts = {
        row['month'].strftime('%Y-%m'): (row['viewers'], row['sessions'])
        for row in logs.order_by().annotate(month=TruncMonth('creation_datetime'))
        .values('month').annotate(viewers=Count('user_id', distinct=True), sessions=Count('pk'))
    }
    rows = []
    year, month = start_date.year, start_date.month
    today = timezone.localdate()
    while (year, month) <= (end_date.year, end_date.month):
        first = start_date.replace(year=year, month=month, day=1)
        last = first.replace(day=monthrange(year, month)[1])
        partial = start_date > first or end_date < last or first <= today <= last
        label = f'{year:04d}-{month:02d}'
        viewers, sessions = counts.get(label, (0, 0))
        rows.append([label, viewers, sessions, 'Partial month' if partial else 'Full month'])
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    charts = []
    for index, name, identifier in (
            (1, 'Unique registered dataset viewers', 'usage-monthly-viewers'),
            (2, 'Dataset viewing sessions started', 'usage-monthly-sessions')):
        charts.append({
            'id': identifier, 'title': name + ' by month',
            'chart': {'labels': [row[0] for row in rows], 'integer': True, 'legend': False,
                      'partial': [row[3] == 'Partial month' for row in rows],
                      'period_unit': 'month', 'partial_through': end_date.isoformat(),
                      'series': [{'name': name, 'color': '#2563eb' if index == 1 else '#ea580c',
                                  'values': [row[index] for row in rows]}]},
        })
    return {'headers': ['Period (YYYY-MM)', 'Unique registered viewers', 'Sessions started', 'Period coverage'],
            'rows': rows, 'charts': charts, 'start_date': start_date, 'end_date': end_date,
            'description': (
                'Sessions spanning months are attributed only to their start month, not every month in between. '
                'These are registered file-access page views, not confirmed downloads. '
                'Do not sum monthly unique viewers to obtain unique viewers for the whole period. '
                'Partial months cover only the selected dates and are not directly comparable with complete months.')}


def usage_trends_csv(report, filename='usage-monthly-stats.csv'):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(report['headers'])
    writer.writerows(report['rows'])
    return response


def usage_monthly_demographics(start_date, end_date, monthly):
    """Count each viewer once per session-start month using current approved-profile fields."""
    logs = dataset_logs(start_date, end_date)
    recognized = {'country': dict(COUNTRIES), 'category': dict(CredentialApplication.RESEARCHER_CATEGORIES)}
    counts = {field: {row[0]: Counter() for row in monthly['rows']} for field in recognized}
    totals = {field: Counter() for field in recognized}
    users = _demographics(User.objects.filter(pk__in=logs.values('user_id')))
    profiles = {}
    query = users.values_list('pk', 'credential_id', 'credential_country', 'credential_category')
    for pk, approved, country, category in query.iterator(chunk_size=2000):
        profile = {}
        for field, value in (('country', country), ('category', category)):
            key = '__no_approval__' if approved is None else value if value in recognized[field] else '__missing__'
            profile[field] = key
            totals[field][key] += 1
        profiles[pk] = profile
    pairs = logs.order_by().annotate(month=TruncMonth('creation_datetime')).values_list('month', 'user_id').distinct()
    for month, user in pairs.iterator(chunk_size=2000):
        period = month.strftime('%Y-%m')
        for field in recognized:
            counts[field][period][profiles[user][field]] += 1
    return {'counts': counts, 'totals': totals}


def usage_country_trends(start_date, end_date, monthly, demographics=None):
    """Current institutional countries, applied to viewers of sessions starting each month."""
    data = demographics if demographics is not None else usage_monthly_demographics(start_date, end_date, monthly)
    countries = dict(COUNTRIES)
    labels = {code: str(name) for code, name in countries.items()}
    no_approval, missing = '__no_approval__', '__missing__'
    labels.update({no_approval: 'No approved credential application', missing: 'Information missing or unrecognized'})
    totals = data['totals']['country']
    top = sorted((code for code in totals if code in countries), key=lambda code: (-totals[code], code))[:5]
    months = data['counts']['country']
    table, exported, approved_rows, unapproved_rows = [], [], [], []
    all_codes = sorted(totals, key=lambda code: (code not in countries, labels[code]))
    for period, _, _, coverage in monthly['rows']:
        counts = months[period]
        total = sum(counts.values())
        known = sum(count for code, count in counts.items() if code in countries)
        percentage = round(100 * known / total, 2) if total else None
        table.append([period, *[counts[code] for code in top],
                      sum(count for code, count in counts.items() if code in countries and code not in top),
                      counts[no_approval] + counts[missing], total, known, percentage, coverage])
        approved = total - counts[no_approval]
        approved_rows.append([period, *[counts[code] for code in top],
                              sum(count for code, count in counts.items() if code in countries and code not in top),
                              counts[missing], approved, known,
                              round(100 * known / approved, 2) if approved else None, coverage])
        unapproved_rows.append([period, counts[no_approval], coverage])
        for code in all_codes:
            exported.append([
                period, labels[code], code if code in countries else '',
                'category' if code in countries else 'unavailable', counts[code],
                round(100 * counts[code] / total, 2) if total else None,
                round(100 * counts[code] / known, 2) if code in countries and known else None,
                known, total, percentage, coverage,
            ])
        if not all_codes:
            exported.append([period, '', '', 'empty', 0, None, None, 0, 0, None, coverage])
    colors = ['#2563eb', '#ea580c', '#15803d', '#b91c1c', '#7c3aed']
    short_names = {'US': 'United States', 'GB': 'United Kingdom'}
    return {
        'id': 'usage-country-monthly', 'title': 'Registered dataset viewers by country and month',
        'description': (
            'Top five recognized institutional countries by distinct viewers with sessions starting in the selected '
            'period. The same countries are shown in every month. '
            'Each person counts once per month across versions. '
            'Countries come from the latest currently approved credential application, not historical location, '
            'nationality, or country at the time of viewing. Changes can reflect missing information or later '
            'credential updates. The table shows other countries, unavailable information and monthly coverage. '
            'The CSV includes every country and separates the two unavailable groups.'),
        'chart': {'labels': list(months), 'partial': monthly['charts'][0]['chart']['partial'], 'integer': True,
                  'period_unit': 'month', 'partial_through': end_date.isoformat(), 'series': [
                      {'name': short_names.get(code, labels[code]), 'color': colors[index],
                       'marker': ['circle', 'square', 'triangle', 'diamond', 'circle'][index],
                       'values': [months[period][code] for period in months]}
                      for index, code in enumerate(top)]},
        'headers': ['Period (YYYY-MM)', *[labels[code] for code in top], 'Other countries',
                    'Without available information', 'All registered viewers', 'Viewers with country information',
                    'Coverage (%)', 'Period coverage'],
        'rows': table, 'has_countries': bool(top),
        'approved_headers': ['Period (YYYY-MM)', *[labels[code] for code in top], 'Other countries',
                             'Country missing or unrecognized', 'Viewers with an approved application',
                             'Viewers with country information', 'Country coverage among approved viewers (%)',
                             'Period coverage'],
        'approved_rows': approved_rows,
        'without_approval': {
            'id': 'usage-without-approval-monthly',
            'title': 'Registered viewers without an approved credential application',
            'description': (
                'Unique viewers with no currently approved credential application, not necessarily users who '
                'have never been credentialed. The classification uses records available now, not credential '
                'status at the time of each visit. Country cannot be supplied by the approved-application source '
                'for this group. The period total and the monthly chart both count sessions by their start date. '
                'Each person counts once per month; '
                'monthly counts are not additive.'),
            'chart': {'labels': list(months), 'partial': monthly['charts'][0]['chart']['partial'],
                      'integer': True, 'legend': False, 'period_unit': 'month',
                      'partial_through': end_date.isoformat(), 'series': [
                          {'name': 'Viewers without an approved application', 'color': '#64748b',
                           'values': [months[period][no_approval] for period in months]}]},
            'headers': ['Period (YYYY-MM)', 'Unique viewers without an approved application', 'Period coverage'],
            'rows': unapproved_rows,
        },
        'export': {'headers': ['Period (YYYY-MM)', 'Country', 'Country code', 'Row type',
                               'Unique registered viewers',
                               'All registered viewers (%)', 'With information (%)',
                               'Viewers with country information',
                               'All registered viewers', 'Coverage (%)', 'Period coverage'], 'rows': exported},
    }


def usage_category_trend(start_date, end_date, monthly, demographics=None):
    categories = dict(CredentialApplication.RESEARCHER_CATEGORIES)
    data = demographics if demographics is not None else usage_monthly_demographics(start_date, end_date, monthly)
    months = data['counts']['category']
    totals = data['totals']['category']
    ordered = sorted(categories, key=lambda key: (-totals[key], key))
    rows = []
    for period, _, _, coverage in monthly['rows']:
        counts = months[period]
        total = sum(counts.values())
        known = sum(counts[key] for key in categories)
        rows.append([period, *[counts[key] for key in ordered], counts['__missing__'], counts['__no_approval__'],
                     known, total, round(100 * known / total, 2) if total else None, coverage])
    colors = ['#2563eb', '#ea580c', '#15803d', '#b91c1c', '#7c3aed', '#0e7490', '#a16207', '#be185d']
    markers = ['circle', 'square', 'triangle', 'diamond', 'plus', 'cross', 'triangle-down', 'hexagon']
    return {
        'id': 'usage-category-monthly', 'title': 'Unique registered viewers by researcher category and month',
        'description': (
            'All recognized researcher categories are shown together, fixed across months. '
            'The legend is ordered by distinct viewers across the selected period, not the sum of monthly counts. '
            'Unchecking a category hides its line only; tables and CSV exports keep all categories. '
            'Each person is '
            'counted once per month across dataset versions, by session start date in the site time zone. '
            'Categories come from the latest currently approved credential application, not the category at '
            'the time of each visit. People without an approved application and missing or unrecognized '
            'categories are shown separately in the monthly table. Coverage uses all registered viewers '
            'with sessions starting that month.'),
        'chart': {'labels': list(months), 'partial': monthly['charts'][0]['chart']['partial'],
                  'integer': True, 'period_unit': 'month', 'partial_through': end_date.isoformat(),
                  'interactive_legend': True, 'plot_height': 440, 'line_width': 2,
                  'series': [{'name': str(categories[key]), 'period_count': totals[key],
                              'color': colors[index % len(colors)],
                              'marker': markers[index % len(markers)],
                              'values': [months[period][key] for period in months]}
                             for index, key in enumerate(ordered)]},
        'headers': ['Period (YYYY-MM)', *[str(categories[key]) for key in ordered],
                    'Category missing or unrecognized', 'No approved credential application',
                    'Viewers with category information', 'All registered viewers', 'Category coverage (%)',
                    'Period coverage'],
        'rows': rows,
    }


def usage_dataset_trends(start_date, end_date, monthly, dataset_rows, version_rows):
    """Plot the same top ten as the period rankings, with monthly session-start attribution."""
    logs = dataset_logs(start_date, end_date)
    datasets = PublishedProject.objects.filter(resource_type_id=0, logs__pk__in=logs.values('pk'))
    colors = ['#2563eb', '#ea580c', '#15803d', '#b91c1c', '#7c3aed', '#0e7490', '#a16207', '#be185d',
              '#475569', '#4338ca']
    markers = ['circle', 'square', 'triangle', 'diamond', 'plus', 'cross', 'triangle-down', 'hexagon',
               'pentagon', 'star']
    reports = {}
    for version, ranking in ((False, dataset_rows[:10]), (True, version_rows[:10])):
        labels = [row['label'] for row in ranking]
        slugs = [label.rsplit(' / ', 1)[0] if version else label for label in labels]
        query = datasets.filter(slug__in=slugs).order_by().annotate(month=TruncMonth('logs__creation_datetime'))
        fields = ['month', 'slug', *(['version'] if version else [])]
        counts = {}
        for row in query.values(*fields).annotate(viewers=Count('logs__user_id', distinct=True)):
            label = f"{row['slug']} / {row['version']}" if version else row['slug']
            counts[(row['month'].strftime('%Y-%m'), label)] = row['viewers']
        rows = [[month[0], *[counts.get((month[0], label), 0) for label in labels], month[3]]
                for month in monthly['rows']]
        key = 'versions' if version else 'datasets'
        reports[key] = {
            'id': 'usage-' + key + '-monthly',
            'title': 'Unique registered viewers by ' + ('dataset version' if version else 'dataset') + ' and month',
            'description': (
                'The top ten are ranked by distinct registered viewers with sessions starting in the selected dates. '
                'The same datasets or versions are shown in every month. Monthly points count each viewer once '
                'per dataset or version, by session start month in the site time zone. Sessions spanning months '
                'are not counted in every intervening month. Rankings and monthly sums therefore need not match. '
                'One person can appear in multiple datasets or versions; do not add these series to obtain unique '
                'viewers across the site. Checkboxes affect the plot only; tables and CSVs retain all ten series.'),
            'chart': {'labels': [row[0] for row in rows], 'partial': monthly['charts'][0]['chart']['partial'],
                      'integer': True, 'period_unit': 'month', 'partial_through': end_date.isoformat(),
                      'interactive_legend': True, 'plot_height': 440, 'line_width': 2,
                      'legend_title': 'Visible dataset versions' if version else 'Visible datasets',
                      'series': [{'name': row['label'], 'period_count': row['count'], 'color': colors[index],
                                  'marker': markers[index % len(markers)],
                                  'values': [counts.get((month[0], row['label']), 0) for month in monthly['rows']]}
                                 for index, row in enumerate(ranking)]},
            'headers': ['Period (YYYY-MM)', *labels, 'Period coverage'], 'rows': rows,
            'has_series': bool(ranking),
        }
    return reports
