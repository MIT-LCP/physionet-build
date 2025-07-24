"""
Tests for the GCP access group management command.
"""

import os
import tempfile
import json
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.core.management import call_command
from django.core.management.base import CommandError

from project.models import PublishedProject, DataAccess
from project.models import CoreProject, ProjectType
from user.models import User


class GCPManagementCommandTest(TestCase):
    """Test cases for the GCP access group management command."""

    def setUp(self):
        """Set up test data."""
        # Create test users
        self.user1 = User.objects.create_user(
            username='testuser1',
            email='testuser1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='testuser2',
            email='testuser2@example.com',
            password='testpass123'
        )
        self.user3 = User.objects.create_user(
            username='testuser3',
            email='testuser3@example.com',
            password='testpass123'
        )

        # Get or create required objects
        self.core_project = CoreProject.objects.create()
        self.resource_type = ProjectType.objects.get(id=0)  # Database type

        self.project = PublishedProject.objects.create(
            slug='test-project',
            version='1.0.0',
            title='Test Project',
            georestricted=True,
            resource_type=self.resource_type,
            core_project=self.core_project
        )

        # Create GCP integration for the project
        from project.models import GCP
        self.gcp = GCP.objects.create(
            project=self.project,
            access_group='test-project-1.0.0@physionet.org',
            managed_by=self.user1
        )

        # Create data access record
        self.data_access = DataAccess.objects.create(
            project=self.project,
            platform=3,  # GCP bucket
            location='https://storage.googleapis.com/test-bucket'
        )

        # Create temporary credentials file
        self.creds_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        creds_data = {
            'type': 'service_account',
            'project_id': 'test-project',
            'private_key_id': 'test-key-id',
            'private_key': '-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n',
            'client_email': 'test@test-project.iam.gserviceaccount.com',
            'client_id': '123456789',
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
            'client_x509_cert_url': (
                'https://www.googleapis.com/robot/v1/metadata/x509/'
                'test%40test-project.iam.gserviceaccount.com'
            )
        }
        json.dump(creds_data, self.creds_file)
        self.creds_file.close()

    def tearDown(self):
        """Clean up test data."""
        # Remove temporary credentials file
        if os.path.exists(self.creds_file.name):
            os.unlink(self.creds_file.name)

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS=None,
        GCP_DELEGATION_EMAIL=None,
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    def test_missing_credentials_configuration(self):
        """Test that command fails when credentials are not configured."""
        with self.assertRaises(CommandError) as cm:
            call_command('refresh_gcp_access_groups', dry_run=True)

        self.assertIn('Google Cloud credentials not configured', str(cm.exception))

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL=None,
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    def test_missing_delegation_email(self):
        """Test that command fails when delegation email is not configured."""
        with self.assertRaises(CommandError) as cm:
            call_command('refresh_gcp_access_groups', dry_run=True)

        self.assertIn('GCP_DELEGATION_EMAIL not configured', str(cm.exception))

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    def test_get_group_members_success(self, mock_create_service):
        """Test successful retrieval of group members."""
        from project.management.commands.refresh_gcp_access_groups import Command

        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Mock the API response
        mock_service.members().list().execute.return_value = {
            'members': [
                {'email': 'user1@example.com'},
                {'email': 'user2@example.com'},
                {'email': 'user3@example.com'}
            ]
        }

        command = Command()
        members = command.get_group_members('test-group@physionet.org')

        self.assertEqual(members, ['user1@example.com', 'user2@example.com', 'user3@example.com'])

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    def test_get_group_members_empty(self, mock_create_service):
        """Test retrieval of group members when group is empty."""
        from project.management.commands.refresh_gcp_access_groups import Command

        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Mock the API response for empty group
        mock_service.members().list().execute.return_value = {}

        command = Command()
        members = command.get_group_members('test-group@physionet.org')

        self.assertEqual(members, [])

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    def test_get_group_members_group_not_found(self, mock_create_service):
        """Test handling when group doesn't exist."""
        from project.management.commands.refresh_gcp_access_groups import Command
        from googleapiclient.errors import HttpError

        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Mock 404 error
        mock_response = MagicMock()
        mock_response.status = 404
        mock_service.members().list().execute.side_effect = HttpError(mock_response, b'Not Found')

        command = Command()
        members = command.get_group_members('nonexistent-group@physionet.org')

        self.assertEqual(members, [])

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['localhost']
    )
    def test_check_georestricted_users(self):
        """Test georestriction checking logic."""
        from project.management.commands.refresh_gcp_access_groups import Command

        # Ensure the project is georestricted
        self.project.georestricted = True
        self.project.save()

        # Set up users with different registration IPs
        self.user1.registration_ip = '8.8.8.8'  # US - not blocked
        self.user1.save()

        self.user2.registration_ip = '8.8.4.4'  # US - not blocked
        self.user2.save()

        # Create a user with a blocked country IP (mock the get_country_code function)
        with patch('physionet.utility.get_country_code') as mock_get_country:
            mock_get_country.side_effect = lambda ip: 'localhost' if ip == '127.0.0.1' else 'US'

            self.user3.registration_ip = '127.0.0.1'  # localhost - blocked
            self.user3.save()

            command = Command()
            user_emails = ['testuser1@example.com', 'testuser2@example.com', 'testuser3@example.com']

            georestricted, users_not_found = command.check_georestricted_users(user_emails, self.project)

            self.assertEqual(len(georestricted), 1)
            self.assertIn('testuser3@example.com', georestricted)
            self.assertEqual(len(users_not_found), 0)

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    def test_check_georestricted_users_no_blocked_regions(self):
        """Test georestriction checking when no regions are blocked."""
        from project.management.commands.refresh_gcp_access_groups import Command

        with override_settings(BLOCKED_REGIONS=None):
            command = Command()
            user_emails = ['testuser1@example.com', 'testuser2@example.com']
            
            georestricted, users_not_found = command.check_georestricted_users(user_emails, self.project)

            self.assertEqual(len(georestricted), 0)
            self.assertEqual(len(users_not_found), 0)

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    def test_check_georestricted_users_user_not_found(self):
        """Test georestriction checking when user is not found."""
        from project.management.commands.refresh_gcp_access_groups import Command

        command = Command()
        user_emails = ['nonexistent@example.com']

        georestricted, users_not_found = command.check_georestricted_users(user_emails, self.project)

        self.assertEqual(len(georestricted), 0)
        self.assertEqual(len(users_not_found), 1)
        self.assertIn('nonexistent@example.com', users_not_found)

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    @patch('project.management.commands.refresh_gcp_access_groups.grant_gcp_group_access')
    def test_re_add_eligible_users(self, mock_grant_access, mock_create_service):
        """Test re-adding eligible users to access group."""
        from project.management.commands.refresh_gcp_access_groups import Command

        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Mock successful access grant
        mock_grant_access.return_value = ('Access granted', True)

        command = Command()
        eligible_emails = ['testuser1@example.com', 'testuser2@example.com']

        added_count = command.re_add_eligible_users(self.project, eligible_emails)

        self.assertEqual(added_count, 2)
        mock_grant_access.assert_called()

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    def test_re_add_eligible_users_no_data_access(self, mock_create_service):
        """Test re-adding users when no data access record exists."""
        from project.management.commands.refresh_gcp_access_groups import Command

        # Delete the data access record
        self.data_access.delete()

        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        command = Command()
        eligible_emails = ['testuser1@example.com']

        added_count = command.re_add_eligible_users(self.project, eligible_emails)

        self.assertEqual(added_count, 0)

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    def test_remove_all_group_members(self, mock_create_service):
        """Test removing all members from a group."""
        from project.management.commands.refresh_gcp_access_groups import Command

        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Mock get_group_members to return some members
        with patch.object(Command, 'get_group_members') as mock_get_members:
            mock_get_members.return_value = ['user1@example.com', 'user2@example.com']

            command = Command()
            result = command.remove_all_group_members('test-group@physionet.org')

            self.assertTrue(result)
            # Verify delete was called for each member
            self.assertEqual(mock_service.members().delete.call_count, 2)

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    @patch('project.management.commands.refresh_gcp_access_groups.create_access_group')
    def test_recreate_access_group(self, mock_create_group, mock_create_service):
        """Test recreating an access group."""
        from project.management.commands.refresh_gcp_access_groups import Command

        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Mock successful group creation
        mock_create_group.return_value = 'new-group@physionet.org'

        command = Command()
        result = command.recreate_access_group(self.project)

        self.assertTrue(result)
        mock_create_group.assert_called_once()

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    def test_command_with_specific_project(self, mock_create_service):
        """Test command with specific project slug."""
        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Mock empty group members
        mock_service.members().list().execute.return_value = {}

        # Capture output
        from io import StringIO
        out = StringIO()

        call_command('refresh_gcp_access_groups',
                     project_slug='test-project',
                     dry_run=True,
                     stdout=out)
        output = out.getvalue()

        self.assertIn('Processing project: Test Project', output)

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    def test_command_with_nonexistent_project(self):
        """Test command with non-existent project slug."""
        with self.assertRaises(CommandError) as cm:
            call_command('refresh_gcp_access_groups', project_slug='nonexistent-project')

        self.assertIn('Project with slug "nonexistent-project" not found', str(cm.exception))

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    def test_dry_run_mode(self, mock_create_service):
        """Test that dry run mode doesn't make actual changes."""
        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Mock empty group members
        mock_service.members().list().execute.return_value = {}

        # Capture output
        from io import StringIO
        out = StringIO()

        call_command('refresh_gcp_access_groups', dry_run=True, stdout=out)
        output = out.getvalue()

        self.assertIn('DRY RUN MODE - No changes will be made', output)
        # Verify no actual API calls were made for destructive operations
        mock_service.members().delete.assert_not_called()
        mock_service.groups().delete.assert_not_called()

    @override_settings(
        GOOGLE_APPLICATION_CREDENTIALS='test-credentials.json',
        GCP_DELEGATION_EMAIL='test@physionet.org',
        BLOCKED_REGIONS=['RU', 'CN', 'IR']
    )
    @patch('project.management.commands.refresh_gcp_access_groups.Command.create_directory_service_with_delegation')
    def test_force_flag_without_georestricted_users(self, mock_create_service):
        """Test force flag when no georestricted users are found."""
        # Mock the service
        mock_service = MagicMock()
        mock_create_service.return_value = mock_service

        # Mock empty group members
        mock_service.members().list().execute.return_value = {}

        # Capture output
        from io import StringIO
        out = StringIO()

        call_command('refresh_gcp_access_groups', force=True, dry_run=True, stdout=out)
        output = out.getvalue()

        self.assertIn('DRY RUN: Would remove all users and recreate group', output)
