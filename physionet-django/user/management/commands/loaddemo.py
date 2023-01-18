"""
Command to:
- load all fixtures named 'demo-*.*'
- create copy the demo media files

This should only be called in a clean database, such as after
`resetdb` is run. This should generally only be used in
development environments.

"""
import os
import shutil

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from lightwave.views import DBCAL_FILE, ORIGINAL_DBCAL_FILE
from physionet.utility import get_project_apps

from user.models import Training, TrainingType, TrainingQuestion, CredentialApplication
from user.enums import TrainingStatus


class Command(BaseCommand):

    def handle(self, *args, **options):
        # If not in development, prompt warning messages twice
        if 'development' not in settings.ENVIRONMENT:
            warning_messages = ['You are NOT in the development environment. Are you sure you want to insert demo data? [y/n]',
                                'The demo data will be mixed with existing data. Are you sure? [y/n]',
                                'Final warning. Are you ABSOLUTELY SURE? [y/n]']
            for i in range(3):
                choice = input(warning_messages[i]).lower()
                if choice != 'y':
                    sys.exit('Exiting from load. No actions applied.')
            print('Continuing loading demo data')

        # Pre-populate the database
        pre_load_data()

        # Load licences and software languages
        site_data_fixtures = os.path.join(settings.BASE_DIR, 'project',
                                          'fixtures', 'site-data.json')
        call_command('loaddata', site_data_fixtures, verbosity=1)

        # Load fixtures for default project types
        project_types_fixtures = os.path.join(settings.BASE_DIR, 'project',
                                              'fixtures', 'project-types.json')
        call_command('loaddata', project_types_fixtures, verbosity=1)

        # Load fixtures for default sites
        site_fixtures = os.path.join(settings.BASE_DIR, 'physionet',
                                     'fixtures', 'sites.json')
        call_command('loaddata', site_fixtures, verbosity=1)

        # Load SSO login instruction static page
        if settings.ENABLE_SSO:
            sso_fixtures = os.path.join(settings.BASE_DIR, 'physionet',
                                        'fixtures', 'login-instruction-static-page.json')
            call_command('loaddata', sso_fixtures, verbosity=1)

        # Load other app fixtures
        project_apps = get_project_apps()
        demo_fixtures = find_demo_fixtures(project_apps)
        call_command('loaddata', *demo_fixtures, verbosity=1)

        # Copy the demo media and static content
        copy_demo_media()
        copy_demo_static()
        print('Copied demo media and static files.')
        # Make symlink of wfdbcal for lightwave
        if os.path.exists(ORIGINAL_DBCAL_FILE):
            os.symlink(ORIGINAL_DBCAL_FILE, DBCAL_FILE)

def find_demo_fixtures(project_apps):
    """
    Find non-empty demo fixtures
    """
    demo_fixtures = []
    for app in project_apps:
        fixture = 'demo-{}'.format(app)
        file_name = os.path.join(settings.BASE_DIR, app,
                                 'fixtures', '{}.json'.format(fixture))
        if os.path.exists(file_name) and open(file_name).read(4) != '[\n]\n':
            demo_fixtures.append(fixture)

    return demo_fixtures


def copy_demo_media():
    """
    Copy the demo media files into the media root.

    Copy all items from within the immediate subfolders of the demo
    media root.

    """
    demo_media_root = os.path.join(settings.DEMO_FILE_ROOT, 'media')
    for subdir in os.listdir(demo_media_root):
        demo_subdir = os.path.join(demo_media_root, subdir)
        target_subdir = os.path.join(settings.MEDIA_ROOT, subdir)
        for item in [i for i in os.listdir(demo_subdir) if i != '.gitkeep']:
            path = os.path.join(demo_subdir, item)
            if os.path.isdir(path):
                shutil.copytree(os.path.join(demo_subdir, item),
                                os.path.join(target_subdir, item))
            else:
                shutil.copy(path, target_subdir)

    # Published project files should have been made read-only at
    # the time of publication
    ppdir = os.path.join(settings.MEDIA_ROOT, 'published-projects')
    for dirpath, subdirs, files in os.walk(ppdir):
        if dirpath != ppdir:
            for f in files:
                os.chmod(os.path.join(dirpath, f), 0o444)
            for d in subdirs:
                os.chmod(os.path.join(dirpath, d), 0o555)


def copy_demo_static():
    """
    Copy the demo static files into the effective static root.

    """
    demo_static_root = os.path.join(settings.DEMO_FILE_ROOT, 'static')

    # Either the actual static root if defined, or the staticfiles_dirs
    effective_static_root = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATICFILES_DIRS[0]

    for subdir in os.listdir(demo_static_root):
        demo_subdir = os.path.join(demo_static_root, subdir)
        target_subdir = os.path.join(effective_static_root, subdir)

        for item in [i for i in os.listdir(demo_subdir) if i != '.gitkeep']:
            shutil.copytree(os.path.join(demo_subdir, item),
                            os.path.join(target_subdir, item))

    # Published project files should have been made read-only at
    # the time of publication
    ppdir = os.path.join(effective_static_root, 'published-projects')
    for dirpath, subdirs, files in os.walk(ppdir):
        if dirpath != ppdir:
            for f in files:
                os.chmod(os.path.join(dirpath, f), 0o444)
            for d in subdirs:
                os.chmod(os.path.join(dirpath, d), 0o555)


def pre_load_data():
    """Pre populate the data base before loading other data."""

    call_command('loaddata', os.path.join(settings.BASE_DIR, 'project',
                                          'fixtures', 'project-types.json'))

    call_command('loaddata', os.path.join(settings.BASE_DIR, 'user',
                                          'fixtures', 'demo-training-type.json'))

    training_type = TrainingType.objects.first()

    status_mapping = {
        0: TrainingStatus.REVIEW,
        1: TrainingStatus.REJECTED,
        2: TrainingStatus.ACCEPTED,
        3: TrainingStatus.WITHDRAWN,
        4: TrainingStatus.REJECTED
    }

    for credential_application in CredentialApplication.objects.all():
        report_url = (
            ""
            if credential_application.training_completion_report_url is None
            else credential_application.training_completion_report_url
        )

        training = Training.objects.create(
            slug=credential_application.slug,
            training_type=training_type,
            user=credential_application.user,
            completion_report=credential_application.training_completion_report,
            completion_report_url=report_url,
            application_datetime=credential_application.training_completion_date,
            process_datetime=credential_application.decision_datetime,
            status=status_mapping[credential_application.status],
        )

        training_questions = []
        for question in training.training_type.questions.all():
            training_questions.append(TrainingQuestion(training=training, question=question))

        TrainingQuestion.objects.bulk_create(training_questions)
