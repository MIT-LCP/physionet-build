from django.db import migrations
from html2text import html2text


def fill_license_text_content(apps, schema_editor):
    License = apps.get_model('project', 'License')
    licenses = License.objects.using(schema_editor.connection.alias)
    for license in licenses.filter(text_content='').iterator():
        licenses.filter(pk=license.pk, text_content='').update(
            text_content=html2text(license.html_content),
        )


class Migration(migrations.Migration):
    dependencies = [
        ('project', '0110_deposit_terms'),
    ]

    operations = [
        migrations.RunPython(fill_license_text_content, migrations.RunPython.noop),
    ]
