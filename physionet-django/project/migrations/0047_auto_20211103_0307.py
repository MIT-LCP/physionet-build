# Generated by Django 2.2.24 on 2021-11-03 07:07

from django.db import migrations, models
import project.modelcomponents.fields


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0046_auto_20210504_1504'),
    ]

    operations = [
        migrations.AddField(
            model_name='activeproject',
            name='data_sharing_agreement',
            field=models.FileField(blank=True, null=True, upload_to='approvals/'),
        ),
        migrations.AddField(
            model_name='activeproject',
            name='explanation',
            field=project.modelcomponents.fields.SafeHTMLField(blank=True),
        ),
        migrations.AddField(
            model_name='activeproject',
            name='reb_approval_letter',
            field=models.FileField(blank=True, null=True, upload_to='approvals/'),
        ),
        migrations.AddField(
            model_name='archivedproject',
            name='data_sharing_agreement',
            field=models.FileField(blank=True, null=True, upload_to='approvals/'),
        ),
        migrations.AddField(
            model_name='archivedproject',
            name='explanation',
            field=project.modelcomponents.fields.SafeHTMLField(blank=True),
        ),
        migrations.AddField(
            model_name='archivedproject',
            name='reb_approval_letter',
            field=models.FileField(blank=True, null=True, upload_to='approvals/'),
        ),
        migrations.AddField(
            model_name='publishedproject',
            name='data_sharing_agreement',
            field=models.FileField(blank=True, null=True, upload_to='approvals/'),
        ),
        migrations.AddField(
            model_name='publishedproject',
            name='explanation',
            field=project.modelcomponents.fields.SafeHTMLField(blank=True),
        ),
        migrations.AddField(
            model_name='publishedproject',
            name='reb_approval_letter',
            field=models.FileField(blank=True, null=True, upload_to='approvals/'),
        ),
    ]