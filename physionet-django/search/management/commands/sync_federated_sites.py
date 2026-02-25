"""
Django management command to synchronize metadata from federated PhysioNet sites.

Usage:
    python manage.py sync_federated_sites                 # Sync all active sites (respects schedule)
    python manage.py sync_federated_sites --site <id>     # Sync specific site
    python manage.py sync_federated_sites --force         # Force sync (ignore schedule)
    python manage.py sync_federated_sites --dry-run       # Show what would be synced
"""
import requests

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from search.models import FederatedSite, FederatedProject, FederationSyncLog


class Command(BaseCommand):
    help = 'Synchronize project metadata from federated PhysioNet sites'

    def add_arguments(self, parser):
        parser.add_argument(
            '--site',
            type=str,
            help='Site identifier to sync (default: all active sites)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if not due per schedule',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes',
        )

    def handle(self, *args, **options):
        """Main command handler."""
        self.verbosity = options.get('verbosity', 1)
        site_id = options.get('site')
        force = options.get('force', False)
        dry_run = options.get('dry_run', False)

        # Check if federation sync is enabled
        if not getattr(settings, 'FEDERATION_SYNC_ENABLED', True):
            self.stdout.write(self.style.WARNING(
                'Federation sync is disabled in settings (FEDERATION_SYNC_ENABLED=False)'
            ))
            return

        # Get sites to sync
        if site_id:
            sites = FederatedSite.objects.filter(site_identifier=site_id)
            if not sites.exists():
                raise CommandError(f'Site "{site_id}" not found')
        else:
            sites = FederatedSite.objects.filter(is_active=True)

        if not sites.exists():
            self.stdout.write(self.style.WARNING('No active federated sites to sync'))
            return

        # Sync each site
        success_count = 0
        failure_count = 0

        for site in sites:
            if not force and not site.needs_sync():
                if self.verbosity >= 2:
                    self.stdout.write(
                        f'Skipping {site.site_name} (not due for sync)'
                    )
                continue

            if dry_run:
                self.stdout.write(f'[DRY RUN] Would sync: {site.site_name}')
                continue

            try:
                self.stdout.write(f'Syncing {site.site_name}...')
                self.sync_site(site)
                success_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Successfully synced {site.site_name}'
                ))
            except Exception as e:
                failure_count += 1
                self.stdout.write(self.style.ERROR(
                    f'✗ Failed to sync {site.site_name}: {str(e)}'
                ))
                if self.verbosity >= 2:
                    import traceback
                    traceback.print_exc()

        # Summary
        self.stdout.write('')
        self.stdout.write(f'Sync complete: {success_count} succeeded, {failure_count} failed')

    def sync_site(self, site):
        """
        Sync metadata from a single federated site.

        Args:
            site: FederatedSite instance to sync

        Raises:
            Exception: If sync fails
        """
        started_at = timezone.now()
        site.mark_sync_started()

        stats = {
            'fetched': 0,
            'created': 0,
            'updated': 0,
            'deleted': 0,
        }

        error_message = ''
        status = FederationSyncLog.STATUS_FAILED  # Default to failed, set to success if we complete

        try:
            # Fetch all projects from the site's federation API
            all_projects = self._fetch_all_projects(site)
            stats['fetched'] = len(all_projects)

            if self.verbosity >= 2:
                self.stdout.write(f'  Fetched {len(all_projects)} projects')

            # Full refresh: delete and recreate all projects for efficiency
            with transaction.atomic():
                # Delete all existing projects for this site
                deleted_count = FederatedProject.objects.filter(source_site=site).delete()[0]
                stats['deleted'] = deleted_count

                if self.verbosity >= 2 and deleted_count > 0:
                    self.stdout.write(f'  Deleted {deleted_count} existing projects')

                # Create all projects fresh
                for project_data in all_projects:
                    self._create_project(site, project_data)
                    stats['created'] += 1

            # Mark sync as successful
            site.mark_sync_success()
            status = FederationSyncLog.STATUS_SUCCESS

        except Exception as e:
            import traceback
            error_message = f"{str(e)}\n\n{traceback.format_exc()}"
            site.mark_sync_failed()
            status = FederationSyncLog.STATUS_FAILED
            raise

        finally:
            # Create sync log
            FederationSyncLog.objects.create(
                site=site,
                started_at=started_at,
                completed_at=timezone.now(),
                status=status,
                projects_fetched=stats['fetched'],
                projects_created=stats['created'],
                projects_updated=stats['updated'],
                projects_deleted=stats['deleted'],
                error_message=error_message
            )

            if self.verbosity >= 2:
                self.stdout.write(
                    f'  Created: {stats["created"]}, '
                    f'Deleted: {stats["deleted"]}'
                )

    def _fetch_all_projects(self, site):
        """
        Fetch all projects from a site's list endpoint.

        Fetches from /api/v1/project/published/ and validates source_url presence.
        Uses only the list endpoint for efficiency (avoids N+1 detail calls).

        Args:
            site: FederatedSite instance

        Returns:
            list: All project metadata dicts with source_url and public_project_uuid

        Raises:
            Exception: If API request fails or required fields are missing
        """
        all_projects = []
        next_url = site.get_api_endpoint()

        timeout = getattr(settings, 'FEDERATION_SYNC_TIMEOUT_SECONDS', 30)

        # Fetch project list (paginated or simple list)
        # Fail fast - if request fails, let scheduler retry later
        while next_url:
            # Make API request
            response = requests.get(
                next_url,
                timeout=timeout
            )
            response.raise_for_status()

            data = response.json()

            # Handle both paginated response (dict) and simple list response
            if isinstance(data, list):
                # Simple list response (no pagination)
                all_projects.extend(data)
                next_url = None
            else:
                # Paginated response (dict with 'results' and 'next')
                results = data.get('results', [])
                all_projects.extend(results)
                next_url = data.get('next')

                if self.verbosity >= 2 and next_url:
                    self.stdout.write(f'  Fetching page... ({len(all_projects)} projects so far)')

        # Validate that all projects have required fields
        for project in all_projects:
            # Validate source_url
            if 'source_url' not in project or not project['source_url']:
                slug = project.get('slug', 'unknown')
                version = project.get('version', 'unknown')
                raise ValueError(
                    f"Project {slug}/{version} is missing 'source_url' field. "
                    f"The federated site API must provide source_url for each project."
                )

            # Validate public_project_uuid
            if 'public_project_uuid' not in project or not project['public_project_uuid']:
                slug = project.get('slug', 'unknown')
                version = project.get('version', 'unknown')
                raise ValueError(
                    f"Project {slug}/{version} is missing 'public_project_uuid' field. "
                    f"The federated site API must provide public_project_uuid for each project."
                )

        return all_projects

    def _create_project(self, site, project_data):
        """
        Create a new FederatedProject from API data.

        Args:
            site: FederatedSite instance
            project_data: Project metadata dict from API

        Returns:
            FederatedProject: Created instance
        """
        # Map publish_date to publish_datetime and handle timezone
        publish_datetime = project_data.get('publish_datetime')
        if not publish_datetime and 'publish_date' in project_data:
            # Convert date string to datetime
            from datetime import datetime
            date_str = project_data['publish_date']
            publish_datetime = timezone.make_aware(datetime.strptime(date_str, '%Y-%m-%d'))

        # Handle topics - could be list, None, or missing
        topics = project_data.get('topics')
        if topics is None or topics == []:
            topics = []

        return FederatedProject.objects.create(
            source_site=site,
            public_project_uuid=project_data['public_project_uuid'],
            slug=project_data['slug'],
            version=project_data['version'],
            title=project_data['title'],
            abstract=project_data.get('abstract', ''),
            doi=project_data.get('version_doi') or project_data.get('doi'),
            source_url=project_data['source_url'],
            resource_type=project_data.get('resource_type'),  # String value from API
            access_policy=project_data.get('access_policy'),  # String value from API
            publish_datetime=publish_datetime,
            main_storage_size=project_data.get('main_storage_size', 0),
            topics=topics,  # Optional, defaults to empty list
        )
