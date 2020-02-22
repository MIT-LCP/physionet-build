from django.db import migrations, models
import django.db.models.deletion

from project.models import PublishedProject

def parse_legacy(apps, schema_editor):
    projects = PublishedProject.objects.filter(is_legacy=True)
    for p in projects:
        p.parse_legacy_content()

def unparse_legacy(apps, schema_editor):
    projects = PublishedProject.objects.filter(is_legacy=True)
    for p in projects:
        p.project_content.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('project', '0043_auto_20200221_1957'),
    ]

    operations = [
        migrations.RunPython(parse_legacy, reverse_code=unparse_legacy),
    ]
