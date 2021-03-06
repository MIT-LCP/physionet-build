# Generated by Django 2.2.13 on 2021-02-01 19:37

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import user.validators


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0031_credentialreview'),
    ]

    operations = [
        migrations.CreateModel(
            name='Orcid',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('orcid_id', models.CharField(blank=True, default='', max_length=50, validators=[user.validators.validate_orcid_id])),
                ('name', models.CharField(blank=True, default='', max_length=50)),
                ('access_token', models.CharField(blank=True, default='', max_length=50, validators=[user.validators.validate_orcid_token])),
                ('refresh_token', models.CharField(blank=True, default='', max_length=50, validators=[user.validators.validate_orcid_token])),
                ('token_type', models.CharField(blank=True, default='', max_length=50)),
                ('token_scope', models.CharField(blank=True, default='', max_length=50)),
                ('token_expiration', models.DecimalField(decimal_places=40, default=0, max_digits=50)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='orcid', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
