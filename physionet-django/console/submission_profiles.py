"""Charts and display tables for the selected submission-contributor cohort."""
from copy import deepcopy
from urllib.parse import urlencode

from console.usage import submissions_metrics, usage_sections


CONTRIBUTOR_DEFINITION = (
    'Unique submitting authors of project versions first submitted during the selected dates. '
    'Revisions are not counted again. '
    'Activity charts above count edit-log submission events, which can differ from version milestones.'
)


def submission_profile_sections(start, end):
    sections = usage_sections(submissions_metrics(start, end), 'submissions')
    for section in sections:
        section['export_rows'] = deepcopy(section['rows'])
        section['profile_id'] = 'submission-profile-' + {
            'overview': 'overview', 'account_age': 'account-age', 'resource_type': 'resource-type',
            'country': 'country', 'category': 'researcher-category',
        }[section['key']]
        section['export_query'] = urlencode({
            'start_date': start.isoformat(), 'end_date': end.isoformat(),
            'export': 'contributor-data', 'section': section['profile_id'],
        })
        rows = section['rows']
        if section['has_coverage']:
            section['unavailable_rows'] = [row for row in rows if not row['information_available']]
            rows = [row for row in rows if row['information_available']]
            if section['key'] == 'country' and len(rows) > 10:
                other = sum(row['count'] for row in rows[10:])
                rows = rows[:10] + [{
                    'label': f'Other countries ({len(rows) - 10})', 'count': other,
                    'percentage': round(100 * other / section['coverage_total'], 2),
                    'available_percentage': round(100 * other / section['coverage_count'], 2),
                }]
                section['table_note'] = 'Top 10 countries plus Other; the CSV includes every country.'
            section['rows'] = rows
        if section['key'] == 'account_age':
            section['chart'] = {
                'type': 'pie', 'empty_label': 'No submitting authors in the selected period.',
                'series': [{'name': row['label'], 'values': [row['count']], 'color': color}
                           for row, color in zip(rows, ['#2563eb', '#ea580c', '#64748b'])],
            }
        else:
            section['chart'] = {
                'type': 'horizontal-bar', 'integer': True, 'legend': False,
                'row_height': 40, 'label_wrap': 44, 'label_font_size': 12, 'label_line_height': 14,
                'labels': [row['label'] for row in rows],
                'series': [{'name': section['count_header'], 'values': [row['count'] for row in rows],
                            'color': '#2563eb'}],
            }
        if section['key'] == 'overview':
            section['description'] = (
                'Counts of distinct institution names, submitted versions and unique submitting authors for the '
                'selected dates. These measures describe different populations and must not be added together. '
                'Institution names are self-reported, normalized for case and spacing only.')
    sections.sort(key=lambda section: section['chart']['type'] == 'pie')
    return sections
