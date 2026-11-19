"""New user accounts by join date and the current last-login snapshot."""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Max, Min, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from console.reporting import month_labels, trend_report
from user.models import User

USER_DESCRIPTION = (
    'Accounts are grouped by join date in the site time zone. Activated means the account is active now, so '
    'accounts deactivated later are not counted as activated and recent months can still change as people '
    'confirm their email. Single sign-on accounts were created through an institutional login. Deleted accounts '
    'are not counted in any month. Registered accounts at month end count every account that joined on or '
    'before the last day of the month and still exists today.'
)

USER_DATES_CACHE_KEY = 'console:users:record-dates:v1'

LOGIN_BANDS = (('Within 30 days', 0, 30), ('30–89 days', 30, 90), ('90–364 days', 90, 365),
               ('365 days or more', 365, None))


def user_record_dates():
    bounds = cache.get(USER_DATES_CACHE_KEY)
    if bounds is None:
        bounds = User.objects.aggregate(first=Min('join_date'), last=Max('join_date'))
        cache.set(USER_DATES_CACHE_KEY, bounds, 300)
    return bounds


def user_trend(start_date, end_date):
    counts = {month: [0, 0, 0] for month in month_labels(start_date, end_date)}
    joined = (User.objects.filter(join_date__gte=start_date, join_date__lte=end_date).order_by()
              .annotate(month=TruncMonth('join_date')).values('month')
              .annotate(new=Count('pk'), active=Count('pk', filter=Q(is_active=True)),
                        sso=Count('pk', filter=Q(sso_id__isnull=False))))
    for row in joined:
        counts[row['month'].strftime('%Y-%m')] = [row['new'], row['active'], row['sso']]
    total = User.objects.filter(join_date__lt=start_date).count()
    rows = []
    for month, values in counts.items():
        total += values[0]
        rows.append([month, *values, total])
    report = trend_report(
        'users-monthly', 'New user accounts by month',
        'New accounts by join month, with those active now and those created through single sign-on. '
        + USER_DESCRIPTION,
        ['Period (YYYY-MM)', 'New accounts', 'Activated accounts', 'Single sign-on accounts',
         'Registered accounts at month end'], rows,
        [('New accounts', 1), ('Activated accounts', 2), ('Single sign-on accounts', 3)],
        start_date, end_date, integer=True,
    )
    report['chart'].update({'period_unit': 'month', 'partial_through': end_date.isoformat(),
                            'interactive_legend': True, 'plot_height': 320,
                            'legend_title': 'Visible account series'})
    for series, color, marker in zip(report['chart']['series'],
                                     ('#2563eb', '#15803d', '#7c3aed'), ('circle', 'triangle', 'square')):
        series.update({'color': color, 'marker': marker})

    total_report = trend_report(
        'users-total-monthly', 'Registered accounts at month end',
        'Every account that joined on or before the last day of each month and still exists today. '
        + USER_DESCRIPTION,
        ['Period (YYYY-MM)', 'Registered accounts at month end'], [[row[0], row[4]] for row in rows],
        [('Registered accounts at month end', 1)], start_date, end_date, integer=True,
    )
    total_report['chart'].update({'period_unit': 'month', 'partial_through': end_date.isoformat(), 'legend': False})
    total_report['chart']['series'][0]['color'] = '#475569'
    return report, total_report


def last_login_summary(now=None):
    """Current snapshot of active accounts by time since their last login."""
    now = now or timezone.now()
    users = User.objects.filter(is_active=True)
    rows = []
    for label, low, high in LOGIN_BANDS:
        band = users.filter(last_login__isnull=False)
        if low:
            band = band.filter(last_login__lte=now - timedelta(days=low))
        if high is not None:
            band = band.filter(last_login__gt=now - timedelta(days=high))
        rows.append([label, band.count()])
    rows.append(['Never logged in', users.filter(last_login__isnull=True).count()])
    total = sum(count for _, count in rows)
    return {
        'id': 'users-last-login', 'title': 'Active accounts by last login', 'snapshot': now, 'total': total,
        'chart': {'type': 'horizontal-bar', 'integer': True, 'legend': False, 'row_height': 40,
                  'labels': [label for label, _ in rows],
                  'series': [{'name': 'Active accounts', 'values': [count for _, count in rows], 'color': '#2563eb'}]},
        'headers': ['Last login', 'Accounts', 'Share (%)'],
        'rows': [[label, count, round(100 * count / total, 1) if total else None] for label, count in rows],
        'description': ('Current snapshot of active accounts, independent of the selected dates. PhysioNet keeps '
                        'only the latest login of each account, so this cannot show how many people logged in '
                        'during past months. Logins in the future, from clock differences, count as within 30 days.'),
    }
