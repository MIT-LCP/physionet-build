# Generated by Django 2.2.28 on 2022-05-29 02:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0044_orcid_datetime_added'),
    ]

    operations = [
        migrations.AlterField(
            model_name='credentialreview',
            name='appears_correct',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='course_name_provided',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='fields_complete',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='lang_understandable',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='ref_appropriate',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='ref_approves',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='ref_course_list',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='ref_has_papers',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='ref_is_supervisor',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='ref_knows_applicant',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='ref_searchable',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='ref_skipped',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='ref_understands_privacy',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='research_summary_clear',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='user_details_consistent',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='user_has_papers',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='user_org_known',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='user_searchable',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='credentialreview',
            name='user_understands_privacy',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='trainingquestion',
            name='answer',
            field=models.BooleanField(null=True),
        ),
    ]
