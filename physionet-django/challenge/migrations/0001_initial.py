from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import project.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('project', '0104_assign_archive_permission'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Challenge',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('slug', models.SlugField(
                    max_length=100, unique=True,
                )),
                ('registration_open_datetime', models.DateTimeField(
                    blank=True, null=True,
                    help_text='When participants can start registering.',
                )),
                ('start_datetime', models.DateTimeField(
                    blank=True, null=True,
                    help_text='When the unofficial phase opens for submissions.',
                )),
                ('official_start_datetime', models.DateTimeField(
                    blank=True, null=True,
                    help_text='When the official phase begins.',
                )),
                ('end_datetime', models.DateTimeField(
                    blank=True, null=True,
                    help_text='When the challenge closes for submissions.',
                )),
                ('phase', models.CharField(
                    choices=[
                        ('registration', 'Registration'),
                        ('unofficial', 'Unofficial'),
                        ('official', 'Official'),
                        ('results', 'Results'),
                        ('archived', 'Archived'),
                    ],
                    default='registration',
                    help_text=(
                        'Source of truth for challenge state.'
                        ' The schedule datetimes are informational;'
                        ' a management command advances this field.'
                    ),
                    max_length=20,
                )),
                ('validation_data_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text='GCS path for the private validation data.',
                )),
                ('test_data_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text='GCS path for the private final test data.',
                )),
                ('validation_labels_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text=(
                        'GCS path for the validation ground-truth labels'
                        ' (kept separate from input data).'
                    ),
                )),
                ('test_labels_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text=(
                        'GCS path for the test ground-truth labels'
                        ' (kept separate from input data).'
                    ),
                )),
                ('rules', project.fields.SafeHTMLField(
                    blank=True, default='', max_length=50000,
                )),
                ('evaluation_description', project.fields.SafeHTMLField(
                    blank=True, default='', max_length=10000,
                )),
                ('prizes', project.fields.SafeHTMLField(
                    blank=True, default='', max_length=10000,
                )),
                ('max_submissions_per_day',
                    models.PositiveIntegerField(default=5)),
                ('max_total_submissions',
                    models.PositiveIntegerField(default=100)),
                ('max_submissions_to_advance', models.PositiveIntegerField(
                    default=1,
                    help_text=(
                        'Number of top submissions per participant/team'
                        ' to advance to test scoring.'
                    ),
                )),
                ('teams_enabled', models.BooleanField(default=False)),
                ('organizer_name', models.CharField(
                    blank=True, default='', max_length=200,
                )),
                ('is_active', models.BooleanField(default=True)),
                ('created_datetime',
                    models.DateTimeField(auto_now_add=True)),
                ('modified_datetime',
                    models.DateTimeField(auto_now=True)),
                ('organizer', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='organized_challenges',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('published_project', models.OneToOneField(
                    limit_choices_to={'resource_type': 2},
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='challenge',
                    to='project.publishedproject',
                )),
                ('training_dataset', models.ForeignKey(
                    blank=True, null=True,
                    help_text='Public training dataset for participants.',
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='challenge_training_for',
                    to='project.publishedproject',
                )),
            ],
            options={
                'permissions': [
                    ('manage_challenge', 'Can manage challenge configuration'),
                ],
            },
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('name', models.CharField(max_length=100)),
                ('created_datetime',
                    models.DateTimeField(auto_now_add=True)),
                ('is_active', models.BooleanField(default=True)),
                ('challenge', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='teams',
                    to='challenge.challenge',
                )),
            ],
            options={
                'unique_together': {('challenge', 'name')},
            },
        ),
        migrations.CreateModel(
            name='TeamInvitation',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('email', models.EmailField(max_length=255)),
                ('request_datetime',
                    models.DateTimeField(auto_now_add=True)),
                ('response_datetime', models.DateTimeField(
                    blank=True, null=True,
                )),
                ('response', models.BooleanField(null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('invited_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='challenge_team_invitations_sent',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('team', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='invitations',
                    to='challenge.team',
                )),
            ],
            options={
                'default_permissions': (),
            },
        ),
        migrations.CreateModel(
            name='SubmissionSpec',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('base_image', models.CharField(
                    default='python:3.11-slim', max_length=200,
                )),
                ('entrypoint_command', models.CharField(
                    default='python main.py', max_length=500,
                )),
                ('max_runtime_seconds',
                    models.PositiveIntegerField(default=3600)),
                ('max_memory_mb',
                    models.PositiveIntegerField(default=4096)),
                ('gpu_enabled', models.BooleanField(default=False)),
                ('gpu_type', models.CharField(
                    blank=True, default='', max_length=50,
                )),
                ('cpu_count',
                    models.PositiveIntegerField(default=2)),
                ('input_format', models.JSONField(
                    blank=True, default=dict,
                    help_text=(
                        'Describes the data structure that will be'
                        ' provided to participant code.'
                    ),
                )),
                ('output_format', models.JSONField(
                    blank=True, default=dict,
                    help_text=(
                        'Describes the output structure that participant'
                        ' code must produce.'
                    ),
                )),
                ('evaluation_script_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text='GCS path to the scoring script.',
                )),
                ('primary_metric', models.JSONField(
                    blank=True, default=dict,
                    help_text=(
                        'Primary metric for ranking. JSON object with'
                        ' name, display_name, and sort fields.'
                    ),
                )),
                ('additional_metrics', models.JSONField(
                    blank=True, default=list,
                    help_text=(
                        'Secondary scoring metrics. List of JSON objects,'
                        ' each with name, display_name, and sort fields.'
                    ),
                )),
                ('challenge', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='submission_spec',
                    to='challenge.challenge',
                )),
            ],
        ),
        migrations.CreateModel(
            name='Submission',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('code_archive_gcs_uri',
                    models.CharField(max_length=500)),
                ('code_archive_sha256', models.CharField(
                    blank=True, default='', max_length=64,
                )),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('building', 'Building'),
                        ('running', 'Running'),
                        ('scoring', 'Scoring'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed'),
                        ('cancelled', 'Cancelled'),
                        ('timed_out', 'Timed Out'),
                    ],
                    default='pending', max_length=20,
                )),
                ('cloud_run_job_name', models.CharField(
                    blank=True, default='', max_length=200,
                )),
                ('cloud_run_execution_name', models.CharField(
                    blank=True, default='', max_length=200,
                )),
                ('error_message', models.TextField(
                    blank=True, default='',
                )),
                ('container_log_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                )),
                ('created_datetime',
                    models.DateTimeField(auto_now_add=True)),
                ('started_datetime', models.DateTimeField(
                    blank=True, null=True,
                )),
                ('completed_datetime', models.DateTimeField(
                    blank=True, null=True,
                )),
                ('description', models.CharField(
                    blank=True, default='', max_length=500,
                )),
                ('is_selected', models.BooleanField(
                    default=False,
                    help_text=(
                        'Marks the active submission for the leaderboard.'
                    ),
                )),
                ('advanced_to_official', models.BooleanField(
                    default=False,
                    help_text=(
                        'Whether this submission was selected for test'
                        ' scoring in the official phase.'
                    ),
                )),
                ('challenge', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='submissions',
                    to='challenge.challenge',
                )),
                ('submitted_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='challenge_submissions',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('team', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='submissions',
                    to='challenge.team',
                )),
            ],
            options={
                'ordering': ['-created_datetime'],
            },
        ),
        migrations.CreateModel(
            name='ChallengeConfiguration',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('registration_open_datetime', models.DateTimeField(
                    blank=True, null=True,
                )),
                ('start_datetime', models.DateTimeField(
                    blank=True, null=True,
                )),
                ('official_start_datetime', models.DateTimeField(
                    blank=True, null=True,
                )),
                ('end_datetime', models.DateTimeField(
                    blank=True, null=True,
                )),
                ('max_submissions_per_day',
                    models.PositiveIntegerField(default=5)),
                ('max_total_submissions',
                    models.PositiveIntegerField(default=100)),
                ('max_submissions_to_advance', models.PositiveIntegerField(
                    default=1,
                    help_text=(
                        'Number of top submissions per participant/team'
                        ' to advance to test scoring.'
                    ),
                )),
                ('teams_enabled', models.BooleanField(default=False)),
                ('base_image', models.CharField(
                    default='python:3.11-slim', max_length=200,
                )),
                ('entrypoint_command', models.CharField(
                    default='python main.py', max_length=500,
                )),
                ('max_runtime_seconds',
                    models.PositiveIntegerField(default=3600)),
                ('max_memory_mb',
                    models.PositiveIntegerField(default=4096)),
                ('gpu_enabled', models.BooleanField(default=False)),
                ('gpu_type', models.CharField(
                    blank=True, default='', max_length=50,
                )),
                ('cpu_count',
                    models.PositiveIntegerField(default=2)),
                ('input_format', models.JSONField(
                    blank=True, default=dict,
                    help_text=(
                        'Describes the data structure that will be'
                        ' provided to participant code.'
                    ),
                )),
                ('output_format', models.JSONField(
                    blank=True, default=dict,
                    help_text=(
                        'Describes the output structure that participant'
                        ' code must produce.'
                    ),
                )),
                ('primary_metric', models.JSONField(
                    blank=True, default=dict,
                    help_text=(
                        'Primary metric for ranking. JSON object with'
                        ' name, display_name, and sort fields.'
                    ),
                )),
                ('additional_metrics', models.JSONField(
                    blank=True, default=list,
                    help_text=(
                        'Secondary scoring metrics. List of JSON objects,'
                        ' each with name, display_name, and sort fields.'
                    ),
                )),
                ('organizer_name', models.CharField(
                    blank=True, default='', max_length=200,
                )),
                ('validation_data_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text='GCS URI for the private validation data.',
                )),
                ('test_data_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text='GCS URI for the private final test data.',
                )),
                ('validation_labels_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text=(
                        'GCS URI for the validation ground-truth labels'
                        ' (kept separate from input data).'
                    ),
                )),
                ('test_labels_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text=(
                        'GCS URI for the test ground-truth labels'
                        ' (kept separate from input data).'
                    ),
                )),
                ('evaluation_script_gcs_uri', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text='GCS URI for the evaluation/scoring script.',
                )),
                ('active_project', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='challenge_config',
                    to='project.activeproject',
                )),
            ],
        ),
        migrations.CreateModel(
            name='Score',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('metric_name', models.CharField(max_length=100)),
                ('value', models.FloatField()),
                ('dataset', models.CharField(
                    choices=[
                        ('train', 'Training'),
                        ('val', 'Validation'),
                        ('test', 'Test'),
                    ],
                    max_length=5,
                )),
                ('submission', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='scores',
                    to='challenge.submission',
                )),
            ],
            options={
                'unique_together': {
                    ('submission', 'metric_name', 'dataset'),
                },
            },
        ),
        migrations.CreateModel(
            name='LeaderboardEntry',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('dataset', models.CharField(
                    choices=[
                        ('train', 'Training'),
                        ('val', 'Validation'),
                        ('test', 'Test'),
                    ],
                    max_length=5,
                )),
                ('primary_score', models.FloatField()),
                ('all_scores', models.JSONField(
                    blank=True, default=dict,
                )),
                ('rank', models.PositiveIntegerField(
                    blank=True, null=True,
                )),
                ('updated_datetime',
                    models.DateTimeField(auto_now=True)),
                ('challenge', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='leaderboard_entries',
                    to='challenge.challenge',
                )),
                ('submission', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='leaderboard_entries',
                    to='challenge.submission',
                )),
                ('team', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='leaderboard_entries',
                    to='challenge.team',
                )),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='challenge_leaderboard_entries',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'constraints': [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(('team__isnull', False), ('user__isnull', True)),
                            models.Q(('team__isnull', True), ('user__isnull', False)),
                            _connector='OR',
                        ),
                        name='leaderboardentry_team_xor_user',
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(('team__isnull', False)),
                        fields=('challenge', 'team', 'dataset'),
                        name='leaderboardentry_unique_team',
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(('user__isnull', False)),
                        fields=('challenge', 'user', 'dataset'),
                        name='leaderboardentry_unique_user',
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name='ChallengeParticipant',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('registered_datetime',
                    models.DateTimeField(auto_now_add=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_team_captain',
                    models.BooleanField(default=False)),
                ('challenge', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='participants',
                    to='challenge.challenge',
                )),
                ('team', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='members',
                    to='challenge.team',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='challenge_participations',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'unique_together': {('user', 'challenge')},
            },
        ),
    ]
