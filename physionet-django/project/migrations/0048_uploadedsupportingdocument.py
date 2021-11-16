# Generated by Django 2.2.24 on 2021-11-15 11:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('project', '0047_auto_20211115_0536'),
    ]

    operations = [
        migrations.CreateModel(
            name='UploadedSupportingDocument',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('document', models.FileField(upload_to='')),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
                ('supporting_document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='project.SupportingDocument')),
            ],
        ),
    ]
