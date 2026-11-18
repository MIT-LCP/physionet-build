"""Annual editorial values, with optional event-date bounds for the charts."""
from collections import OrderedDict
from statistics import median

from django.db.models import Min, Q
from django.utils import timezone

from project.models import ActiveProject, PublishedProject


def editorial_annual_stats(start=None, end=None):
    """Publications use publication dates; first decisions use decision dates."""
    published = PublishedProject.objects.filter(is_legacy=False)
    publication_cohort = published
    if start is not None:
        publication_cohort = publication_cohort.filter(publish_datetime__gte=start, publish_datetime__lt=end)
    groups = {}

    def group(year):
        return groups.setdefault(year, {'count': 0, 'assignment': [], 'publication': [], 'decision': []})

    for publication, submitted, assigned in publication_cohort.values_list(
            'publish_datetime', 'submission_datetime', 'editor_assignment_datetime').iterator(chunk_size=1000):
        values = group(timezone.localtime(publication).year)
        values['count'] += 1
        if submitted:
            for key, finished in (('assignment', assigned), ('publication', publication)):
                if finished and finished >= submitted:
                    values[key].append((finished - submitted).days)
    for projects in (published, ActiveProject.objects.all()):
        decisions = projects.filter(submission_datetime__isnull=False).annotate(
            first_decision=Min('edit_logs__decision_datetime', filter=Q(edit_logs__decision__isnull=False)),
        )
        if start is not None:
            decisions = decisions.filter(first_decision__gte=start, first_decision__lt=end)
        for submitted, decided in decisions.values_list('submission_datetime', 'first_decision').iterator(
                chunk_size=1000):
            if decided and decided >= submitted:
                group(timezone.localtime(decided).year)['decision'].append((decided - submitted).days)
    result = OrderedDict()
    for year, values in sorted(groups.items()):
        durations = [median(values[key]) if values[key] else None
                     for key in ('assignment', 'publication', 'decision')]
        result[year] = [values['count'], *durations]
    return result
