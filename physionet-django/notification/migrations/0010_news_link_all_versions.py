# Generated by Django 4.1.10 on 2024-01-30 20:50

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notification", "0009_alter_news_slug"),
    ]

    operations = [
        migrations.AddField(
            model_name="news",
            name="link_all_versions",
            field=models.BooleanField(
                default=False,
                help_text="Check this to link the news item to all versions of the selected project",
            ),
        ),
    ]