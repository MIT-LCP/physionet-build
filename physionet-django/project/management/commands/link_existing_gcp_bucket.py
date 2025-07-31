
import google.auth.transport.requests
from django.core.management.base import BaseCommand, CommandError
from project.cloud.gcp import ROLES, add_email_bucket_access
from project.modelcomponents.storage import GCP
from project.models import PublishedProject, DataAccess
from user.models import User


class Command(BaseCommand):
    help = 'Link an existing GCP bucket and group to a project.'

    def add_arguments(self, parser):
        parser.add_argument('--project-slug', required=True)
        parser.add_argument('--project-version', required=True)
        parser.add_argument('--group-email', required=True)
        parser.add_argument('--bucket-name', required=True)
        parser.add_argument('--user-email', required=True, help='Email of user to set as manager')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be changed')

    def handle(self, *args, **options):
        slug = options['project_slug']
        version = options['project_version']
        group_email = options['group_email']
        bucket_name = options['bucket_name']
        user_email = options['user_email']
        dry_run = options['dry_run']

        try:
            project = PublishedProject.objects.get(slug=slug, version=version)
        except PublishedProject.DoesNotExist:
            raise CommandError(f'Project {slug} v{version} not found')

        # Set manager (required)
        try:
            manager = User.objects.get(email=user_email)
        except User.DoesNotExist:
            raise CommandError(f'User {user_email} not found')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[DRY RUN] Would link project {slug} v{version} to bucket {bucket_name} with group {group_email}'))
            self.stdout.write(self.style.WARNING(f'[DRY RUN] Would set manager to {user_email}'))
            self.stdout.write(self.style.WARNING('[DRY RUN] Would create or update GCP record'))
            self.stdout.write(self.style.WARNING('[DRY RUN] Would create DataAccess record if not present'))
        else:
            # Create or update GCP record
            _, created = GCP.objects.update_or_create(
                project=project,
                defaults={
                    'bucket_name': bucket_name,
                    'access_group': group_email,
                    'managed_by': manager,
                    'is_private': True,
                    'sent_files': True,  # Assume bucket already has files. Can resend files from console if needed.
                    'sent_zip': False,   # Keep False since we didn't send zip through normal process
                }
            )
            self.stdout.write(self.style.SUCCESS(
                f'GCP record {"created" if created else "updated"} for project {slug} v{version}'
            ))

            # Create DataAccess record if not present
            _, da_created = DataAccess.objects.get_or_create(
                project=project,
                platform=3,  # 3 = GCP Bucket
                defaults={'location': group_email}
            )
            if da_created:
                self.stdout.write(self.style.SUCCESS('DataAccess record created.'))
            else:
                self.stdout.write('DataAccess record already exists.')

        # Add group to bucket IAM policy
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[DRY RUN] Would add group {group_email} to bucket {bucket_name} IAM policy'))
            for role in ROLES:
                self.stdout.write(self.style.WARNING(f'[DRY RUN] Would add group:{group_email} to {role}'))
        else:
            granted = add_email_bucket_access(project, group_email, group=True, user_project='physionet-data')
            if granted:
                self.stdout.write(self.style.SUCCESS(
                    f'Group {group_email} added to bucket {bucket_name} IAM policy with required roles.'))
            else:
                self.stdout.write(self.style.ERROR(f'Failed to add group {group_email} to bucket IAM policy.'))
