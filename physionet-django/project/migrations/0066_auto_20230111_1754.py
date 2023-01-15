from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Renames the default manytomany table created by django and points i to ours,
    then adds the through relation as well as the temporary field.
    """

    dependencies = [
        ('user', '0048_auto_20221129_1512'),
        ('project', '0065_editor_permissions'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE project_activeproject_required_trainings '
                        'RENAME TO project_activeprojecttraining',
                    reverse_sql='ALTER TABLE project_activeprojecttraining RENAME '
                        'TO project_activeproject_required_trainings',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE project_archivedproject_required_trainings '
                        'RENAME TO project_archivedprojecttraining',
                    reverse_sql='ALTER TABLE project_archivedprojecttraining RENAME '
                        'TO project_archivedproject_required_trainings',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE project_publishedproject_required_trainings '
                        'RENAME TO project_publishedprojecttraining',
                    reverse_sql='ALTER TABLE project_publishedprojecttraining '
                        'RENAME TO project_publishedproject_required_trainings',
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='ActiveProjectTraining',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True,
                                                serialize=False, verbose_name='ID')),
                        ('activeproject', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            to='project.activeproject')),
                        ('trainingtype', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            to='user.trainingtype')),
                    ],
                ),
                migrations.CreateModel(
                    name='ArchivedProjectTraining',
                    fields=[
                        ('id', models.AutoField(
                            auto_created=True, primary_key=True,
                            serialize=False, verbose_name='ID')),
                        ('archivedproject', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            to='project.archivedproject')),
                        ('trainingtype', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            to='user.trainingtype')),
                    ],
                ),
                migrations.CreateModel(
                    name='PublishedProjectTraining',
                    fields=[
                        ('id', models.AutoField(
                            auto_created=True, primary_key=True,
                            serialize=False, verbose_name='ID')),
                        ('publishedproject', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            to='project.publishedproject')),
                        ('trainingtype', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            to='user.trainingtype')),
                    ],
                ),
                migrations.AlterField(
                    model_name='activeproject',
                    name='required_trainings',
                    field=models.ManyToManyField(
                        related_name='activeproject',
                        through='project.ActiveProjectTraining',
                        to='user.TrainingType'),
                ),
                migrations.AlterField(
                    model_name='archivedproject',
                    name='required_trainings',
                    field=models.ManyToManyField(
                        related_name='archivedproject',
                        through='project.ArchivedProjectTraining',
                        to='user.TrainingType'),
                ),
                migrations.AlterField(
                    model_name='publishedproject',
                    name='required_trainings',
                    field=models.ManyToManyField(
                        related_name='publishedproject',
                        through='project.PublishedProjectTraining',
                        to='user.TrainingType'),
                ),
            ]
        )
    ]
