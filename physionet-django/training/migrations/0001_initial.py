# Generated by Django 4.1.5 on 2023-02-14 13:52

import ckeditor_uploader.fields
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('user', '0051_alter_trainingtype_required_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='OnPlatformTraining',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.FloatField(default=1.0)),
                ('training', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='op_trainings', to='user.trainingtype')),
            ],
            options={
                'default_permissions': ('change',),
            },
        ),
        migrations.CreateModel(
            name='Quiz',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', ckeditor_uploader.fields.RichTextUploadingField()),
                ('order', models.PositiveIntegerField()),
                ('training', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='quizzes', to='training.onplatformtraining')),
            ],
        ),
        migrations.CreateModel(
            name='QuizChoice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField()),
                ('is_correct', models.BooleanField(default=False, verbose_name='Correct Choice?')),
                ('quiz', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='choices', to='training.quiz')),
            ],
        ),
        migrations.CreateModel(
            name='ContentBlock',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', ckeditor_uploader.fields.RichTextUploadingField()),
                ('order', models.PositiveIntegerField()),
                ('training', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contents', to='training.onplatformtraining')),
            ],
        ),
    ]
