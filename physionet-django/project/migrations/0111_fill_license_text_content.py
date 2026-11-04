from django.db import migrations

from project.license_content import license_html_to_text


def fill_license_text_content(apps, schema_editor):
    License = apps.get_model('project', 'License')
    licenses = License.objects.using(schema_editor.connection.alias)
    for license in licenses.filter(text_content='').iterator():
        licenses.filter(pk=license.pk, text_content='').update(
            text_content=license_html_to_text(license.html_content),
        )


class Migration(migrations.Migration):
    dependencies = [
        ('project', '0110_deposit_terms'),
    ]

    operations = [
        migrations.RunPython(fill_license_text_content, migrations.RunPython.noop),
    ]
