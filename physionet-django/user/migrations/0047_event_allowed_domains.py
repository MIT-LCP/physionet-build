# Generated by Django 3.1.14 on 2022-09-28 14:42
import re

from django.core.exceptions import ValidationError
from django.db import migrations, models


def validate_domain_list(value):
    """
    Validate a list of comma separated email domains ('mit.edu, buffalo.edu, gmail.com').
    """
    if not re.fullmatch(r'(\w+\.\w+,*\s*)*', value):
        raise ValidationError('Must be separated with commas.')


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0046_event_eventparticipant'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='allowed_domains',
            field=models.CharField(blank=True, max_length=100, null=True,
                                   validators=[validate_domain_list]),
        ),
    ]
