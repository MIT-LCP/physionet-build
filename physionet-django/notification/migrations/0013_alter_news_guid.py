import uuid

from django.db import migrations, models


def regenerate_duplicate_guids(apps, schema_editor):
    """
    Give every news item its own guid. 0004_news_guid added the field
    with a callable default, which Django evaluates only once, so all
    news items that existed at that point share the same guid.
    """
    News = apps.get_model('notification', 'News')
    seen = set()
    for news in News.objects.order_by('id'):
        if news.guid in seen:
            news.guid = str(uuid.uuid4())
            news.save(update_fields=['guid'])
        seen.add(news.guid)


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0012_notification'),
    ]

    operations = [
        migrations.RunPython(regenerate_duplicate_guids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='news',
            name='guid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
