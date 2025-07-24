import json
import logging
import os

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from google.cloud import storage

from project.models import PublishedProject, DataAccess, AccessPolicy
from project.cloud.gcp import bucket_info, create_access_group, add_email_bucket_access, remove_bucket_permissions
from project.utility import grant_gcp_group_access
from project.authorization.access import can_access_project
from user.models import User, AssociatedEmail

# Suppress googleapiclient file_cache warning
import warnings
warnings.filterwarnings('ignore', message='file_cache is unavailable when using oauth2client >= 4.0.0 or google-auth')
warnings.filterwarnings('ignore', message='file_cache is unavailable')
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
logging.getLogger('googleapiclient.discovery').setLevel(logging.ERROR)

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Remove all users from Google Cloud permission groups and recreate them with georestriction checks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--project-slug',
            type=str,
            help='Process only a specific project by slug',
        )
        parser.add_argument(
            '--project-version',
            type=str,
            help='Process a specific project version (e.g., "1.0.0"). If not specified, uses the latest version.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation even if no georestriction is needed',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        project_slug = options['project_slug']
        project_version = options['project_version']
        force = options['force']

        if not settings.GOOGLE_APPLICATION_CREDENTIALS:
            raise CommandError('Google Cloud credentials not configured')

        if not settings.GCP_DELEGATION_EMAIL:
            raise CommandError('GCP_DELEGATION_EMAIL not configured')

        # Get projects to process
        if project_slug:
            try:
                if project_version:
                    # Get specific project and version
                    projects = [PublishedProject.objects.get(slug=project_slug, version=project_version)]
                    self.stdout.write(f'Processing project "{project_slug}" version "{project_version}"')
                else:
                    # Get the latest version of the specific project
                    latest_project = PublishedProject.objects.filter(slug=project_slug).order_by('-version').first()
                    if not latest_project:
                        raise CommandError(f'Project with slug "{project_slug}" not found')
                    projects = [latest_project]
                    self.stdout.write(f'Processing project "{project_slug}" latest version "{latest_project.version}"')
            except ObjectDoesNotExist:
                if project_version:
                    raise CommandError(f'Project with slug "{project_slug}" and version "{project_version}" not found')
                else:
                    raise CommandError(f'Project with slug "{project_slug}" not found')
        else:
            # Get all published projects that have GCP integration
            projects = PublishedProject.objects.filter(
                gcp__isnull=False,
                gcp__access_group__isnull=False
            ).select_related('gcp')

        self.stdout.write(f'Found {len(projects)} projects with GCP integration')

        if dry_run:
            self.stdout.write('DRY RUN MODE - No changes will be made')

        for project in projects:
            self.process_project(project, dry_run, force)

        self.stdout.write('Completed processing all projects')

    def create_directory_service_with_delegation(self):
        """
        Create a directory service with proper domain-wide delegation
        """
        # Load service account credentials with proper delegation
        creds_file = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        credentials = service_account.Credentials.from_service_account_file(
            creds_file,
            scopes=['https://www.googleapis.com/auth/admin.directory.group',
                    'https://www.googleapis.com/auth/admin.directory.group.member']
        )

        # Set up domain-wide delegation
        delegation_email = getattr(settings, 'GCP_DELEGATION_EMAIL', 'ftorres@physionet.org')
        delegated_credentials = credentials.with_subject(delegation_email)

        return build('admin', 'directory_v1', credentials=delegated_credentials)

    def process_project(self, project, dry_run, force):
        """
        Process a single project's GCP access groups
        """
        self.stdout.write(f'\nProcessing project: {project.title} ({project.slug} v{project.version})')

        # Check if project has GCP integration
        if not hasattr(project, 'gcp') or not project.gcp.access_group:
            self.stdout.write('  - No GCP access group found, skipping')
            return

        access_group_email = project.gcp.access_group
        self.stdout.write(f'  - Access group: {access_group_email}')

        # Get all users who currently have access to this project
        current_members = self.get_group_members(access_group_email)
        if current_members is None:
            self.stdout.write('  - Failed to get current group members, skipping')
            return

        self.stdout.write(f'  - Current members: {len(current_members)}')

        # Check if any users should not have access
        users_without_access = []
        users_not_found = []
        if project.georestricted or project.access_policy != AccessPolicy.OPEN:
            users_without_access, users_not_found = self.check_georestricted_users(current_members, project)
            if users_without_access:
                self.stdout.write(f'  - Users without access: {len(users_without_access)}')
                for user_email in users_without_access:
                    self.stdout.write(f'    * {user_email}')
            if users_not_found:
                self.stdout.write(f'  - Users not found: {len(users_not_found)}')
                for user_email in users_not_found:
                    self.stdout.write(f'    * {user_email}')

        # If no users without access and no users not found and not forced, skip
        if not users_without_access and not users_not_found and not force:
            self.stdout.write('  - No users without access found and not forced, skipping')
            return

        if dry_run:
            self.stdout.write('  - DRY RUN: Would remove all users and recreate group')
            return

        # Remove all users from the group
        self.stdout.write('  - Removing all users from group...')
        if not self.remove_all_group_members(access_group_email):
            self.stdout.write('  - Failed to remove users from group')
            return

        # Delete and recreate the access group
        self.stdout.write('  - Recreating access group...')
        if not self.recreate_access_group(project):
            self.stdout.write('  - Failed to recreate access group')
            return

        # Re-add users who have access
        self.stdout.write('  - Re-adding eligible users...')
        eligible_users = [email for email in current_members if email not in users_without_access and email not in users_not_found]
        added_count = self.re_add_eligible_users(project, eligible_users)
        self.stdout.write(f'  - Re-added {added_count} eligible users')

        self.stdout.write(f'  - Successfully processed {project.title}')

    def get_group_members(self, group_email):
        """
        Get all members of a Google Cloud group
        """
        try:
            service = self.create_directory_service_with_delegation()
            members = []
            page_token = None

            while True:
                try:
                    if page_token:
                        result = service.members().list(
                            groupKey=group_email,
                            pageToken=page_token
                        ).execute()
                    else:
                        result = service.members().list(
                            groupKey=group_email
                        ).execute()

                    if 'members' in result:
                        members.extend([member['email'] for member in result['members']])

                    page_token = result.get('nextPageToken')
                    if not page_token:
                        break

                except HttpError as e:
                    if e.resp.status == 404:
                        # Group doesn't exist
                        return []
                    else:
                        LOGGER.error(f'Error getting members for group {group_email}: {e}')
                        return None

            return members

        except Exception as e:
            LOGGER.error(f'Error getting group members for {group_email}: {e}')
            return None

    def remove_all_group_members(self, group_email):
        """
        Remove all members from a Google Cloud group
        """
        try:
            service = self.create_directory_service_with_delegation()
            members = self.get_group_members(group_email)

            if members is None:
                return False

            for member_email in members:
                try:
                    service.members().delete(
                        groupKey=group_email,
                        memberKey=member_email
                    ).execute()
                except HttpError as e:
                    if e.resp.status != 404:  # Ignore if member doesn't exist
                        LOGGER.error(f'Error removing member {member_email} from group {group_email}: {e}')

            return True

        except Exception as e:
            LOGGER.error(f'Error removing group members for {group_email}: {e}')
            return False

    def recreate_access_group(self, project):
        """
        Delete and recreate the access group for a project
        """
        try:
            bucket_name, group_email = bucket_info(project.slug, project.version)
            service = self.create_directory_service_with_delegation()

            # Remove all bucket permissions before recreating the access group
            self.stdout.write('  - Removing all bucket permissions...')
            storage_client = storage.Client()
            bucket = storage_client.get_bucket(project.gcp.bucket_name)
            remove_bucket_permissions(bucket)
            self.stdout.write('  - Successfully removed all bucket permissions')

            # Delete the existing group
            try:
                service.groups().delete(groupKey=group_email).execute()
            except HttpError as e:
                # Ignore if group doesn't exist
                if e.resp.status != 404:
                    LOGGER.error(f'Error deleting group {group_email}: {e}')

            # Create the new group using the shared utility function
            new_group = create_access_group(bucket_name, project.slug, project.version, project.title)
            if new_group:
                # Update the database record
                project.gcp.access_group = new_group
                project.gcp.save()
                
                # Add the access group to the bucket
                bucket_access_granted = add_email_bucket_access(project, new_group, group=True)
                if bucket_access_granted:
                    self.stdout.write(f'  - Successfully added access group {new_group} to bucket')
                else:
                    self.stdout.write(f'  - Warning: Failed to add access group {new_group} to bucket')
                
                return True

            return False

        except Exception as e:
            LOGGER.error(f'Error recreating access group for {project.slug}: {e}')
            return False

    def check_georestricted_users(self, user_emails, project):
        """
        Check which users should not have access using can_access_project function
        """
        georestricted_users = []
        users_not_found = []

        for email in user_emails:
            try:
                # Find the user by associated email (GCP groups contain associated emails)
                # Use case-insensitive lookup
                associated_email = AssociatedEmail.objects.filter(email__iexact=email).first()
                if associated_email:
                    user = associated_email.user
                    # Create a mock request with the user's registration IP
                    mock_request = self.create_mock_request(user)
                    # Check if user can access the project
                    if not can_access_project(project, user, mock_request):
                        georestricted_users.append(email)
                        LOGGER.info(f'User {email} does not have access to project')
                else:
                    # Fallback: try to find user by primary email (case-insensitive)
                    user = User.objects.filter(email__iexact=email).first()
                    if user:
                        mock_request = self.create_mock_request(user)
                        if not can_access_project(project, user, mock_request):
                            georestricted_users.append(email)
                            LOGGER.info(f'User {email} does not have access to project')
                    else:
                        users_not_found.append(email)
                        LOGGER.warning(f'User not found for email: {email}')
            except Exception as e:
                LOGGER.error(f'Error checking access for user {email}: {e}')

        return georestricted_users, users_not_found

    def create_mock_request(self, user):
        """
        Create a mock request object with the user's registration IP
        """
        mock_request = HttpRequest()
        if hasattr(user, 'registration_ip') and user.registration_ip:
            # Set the registration IP as the client IP for georestriction checks
            mock_request.META = {
                'REMOTE_ADDR': user.registration_ip,
                'HTTP_X_FORWARDED_FOR': user.registration_ip,
                'HTTP_X_REAL_IP': user.registration_ip,
            }
        else:
            # If no registration IP, use a default IP (e.g., localhost)
            mock_request.META = {
                'REMOTE_ADDR': '127.0.0.1',
                'HTTP_X_FORWARDED_FOR': '127.0.0.1',
                'HTTP_X_REAL_IP': '127.0.0.1',
            }
        return mock_request

    def re_add_eligible_users(self, project, eligible_emails):
        """
        Re-add eligible users to the project's access group
        """
        added_count = 0

        # Get the data access record for this project
        try:
            data_access = DataAccess.objects.get(
                project=project,
                platform=3  # GCP bucket
            )
        except ObjectDoesNotExist:
            self.stdout.write('  - No GCP data access record found')
            return 0

        for email in eligible_emails:
            try:
                # Find the user by associated email (GCP groups contain associated emails)
                # Use case-insensitive lookup
                associated_email = AssociatedEmail.objects.filter(email__iexact=email).first()
                if associated_email:
                    user = associated_email.user
                    message, granted = grant_gcp_group_access(user, project, data_access)
                    if granted:
                        added_count += 1
                    else:
                        self.stdout.write(f'    - Failed to add {email}: {message}')
                else:
                    # Fallback: try to find user by primary email (case-insensitive)
                    user = User.objects.filter(email__iexact=email).first()
                    if user:
                        message, granted = grant_gcp_group_access(user, project, data_access)
                        if granted:
                            added_count += 1
                        else:
                            self.stdout.write(f'    - Failed to add {email}: {message}')
                    else:
                        self.stdout.write(f'    - User not found for email: {email}')

            except Exception as e:
                LOGGER.error(f'Error re-adding user {email}: {e}')
                self.stdout.write(f'    - Error adding {email}: {e}')

        return added_count
