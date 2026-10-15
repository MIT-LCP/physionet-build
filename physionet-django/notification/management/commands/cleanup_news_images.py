import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from datetime import timedelta

from notification.models import News, NewsImage


class Command(BaseCommand):
    help = 'Remove orphaned news images not referenced by any news item.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=24,
            help='Only consider images older than this many hours (default: 24).',
        )

    def handle(self, *args, **options):
        max_age_hours = options['max_age_hours']
        cutoff = timezone.now() - timedelta(hours=max_age_hours)
        candidates = NewsImage.objects.filter(uploaded_at__lt=cutoff)

        all_content = News.objects.values_list('content', flat=True)
        content_blob = '\n'.join(all_content)

        deleted_count = 0
        for image in candidates:
            if image.filename not in content_blob:
                filepath = os.path.join(
                    settings.MEDIA_ROOT, 'news', 'images', image.filename
                )
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    self.stdout.write(f'Deleted file: {image.filename}')
                image.delete()
                deleted_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Cleaned up {deleted_count} orphaned image(s).')
        )
