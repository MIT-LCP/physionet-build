from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0098_add_review_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='affiliation',
            name='country',
            field=models.CharField(blank=True, default='', max_length=2),
        ),
        migrations.AddField(
            model_name='publishedaffiliation',
            name='country',
            field=models.CharField(blank=True, default='', max_length=2),
        ),
    ]
