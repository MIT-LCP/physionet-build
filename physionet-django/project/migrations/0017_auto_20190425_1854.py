# Generated by Django 2.1.7 on 2019-04-25 22:54

from django.db import migrations, models
import user.validators


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0016_auto_20190422_1607'),
    ]

    operations = [
        migrations.AddField(
            model_name='activeproject',
            name='parent_projects',
            field=models.ManyToManyField(blank=True, related_name='derived_activeprojects', to='project.PublishedProject'),
        ),
        migrations.AddField(
            model_name='archivedproject',
            name='parent_projects',
            field=models.ManyToManyField(blank=True, related_name='derived_archivedprojects', to='project.PublishedProject'),
        ),
        migrations.AddField(
            model_name='publishedproject',
            name='parent_projects',
            field=models.ManyToManyField(blank=True, related_name='derived_publishedprojects', to='project.PublishedProject'),
        ),
        migrations.AlterField(
            model_name='activeproject',
            name='programming_languages',
            field=models.ManyToManyField(blank=True, related_name='activeprojects', to='project.ProgrammingLanguage'),
        ),
        migrations.AlterField(
            model_name='activeproject',
            name='short_description',
            field=models.CharField(blank=True, default='', max_length=250, validators=[user.validators.validate_alphaplusplus]),
        ),
        migrations.AlterField(
            model_name='archivedproject',
            name='programming_languages',
            field=models.ManyToManyField(blank=True, related_name='archivedprojects', to='project.ProgrammingLanguage'),
        ),
        migrations.AlterField(
            model_name='archivedproject',
            name='short_description',
            field=models.CharField(blank=True, default='', max_length=250, validators=[user.validators.validate_alphaplusplus]),
        ),
        migrations.AlterField(
            model_name='publishedproject',
            name='programming_languages',
            field=models.ManyToManyField(blank=True, related_name='publishedprojects', to='project.ProgrammingLanguage'),
        ),
        migrations.AlterField(
            model_name='publishedproject',
            name='short_description',
            field=models.CharField(blank=True, default='', max_length=250, validators=[user.validators.validate_alphaplusplus]),
        ),
    ]
