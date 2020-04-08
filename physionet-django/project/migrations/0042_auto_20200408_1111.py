# Generated by Django 2.2.10 on 2020-04-08 15:11

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0041_auto_20200317_0834'),
    ]

    operations = [
        migrations.AlterField(
            model_name='authorinvitation',
            name='inviter',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='author_invitations', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='dataaccessrequest',
            name='requester',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='data_access_requests_requester', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='dataaccessrequest',
            name='responder',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='data_access_requests_responder', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='duasignature',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dua_saignee', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='storagerequest',
            name='responder',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='storage_responder', to=settings.AUTH_USER_MODEL),
        ),
    ]
