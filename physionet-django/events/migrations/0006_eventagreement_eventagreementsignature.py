# Generated by Django 3.2.16 on 2023-02-22 22:46

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import project.modelcomponents.fields
import project.validators


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0005_eventdataset'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventAgreement',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('slug', models.SlugField(max_length=120, unique=True,
                                          validators=[project.validators.validate_slug])),
                ('version', models.CharField(default='', max_length=15,
                                             validators=[project.validators.validate_version])),
                ('is_active', models.BooleanField(default=True)),
                ('html_content', project.modelcomponents.fields.SafeHTMLField(default='')),
                ('access_template', project.modelcomponents.fields.SafeHTMLField(default='')),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'default_permissions': ('add',),
                'unique_together': {('name', 'version')},
            },
        ),
        migrations.CreateModel(
            name='EventAgreementSignature',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sign_datetime', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='events.event')),
                ('event_agreement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                      to='events.eventagreement')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                           related_name='event_agreement_signatures', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'default_permissions': (),
            },
        ),
    ]