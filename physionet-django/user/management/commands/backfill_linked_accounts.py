from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from user.linked_accounts import CREATED, DELETED, PROVIDERS, UNCHANGED, UPDATED, LinkedAccountError, sync_user
from user.models import LinkedAccount, User


class Command(BaseCommand):
    help = (
        "Copy every ORCID and KHDP link from the old tables to the linked account table. "
        "Each user is synced on their own; a user whose links can't be copied is listed and skipped, "
        "and the command fails at the end if any were skipped. Safe to run again."
    )

    def handle(self, *args, **options):
        user_ids = set()
        for mapping in PROVIDERS.values():
            user_ids.update(mapping.old_model.objects.values_list('user_id', flat=True))
        user_ids.update(LinkedAccount.objects.values_list('user_id', flat=True))

        counts = Counter()
        skipped = []
        for user in User.objects.filter(pk__in=user_ids).order_by('pk'):
            provider = None
            results = []
            try:
                with transaction.atomic():
                    for provider in PROVIDERS:
                        results.append(sync_user(user, provider))
            except (LinkedAccountError, IntegrityError) as error:
                skipped.append(f"{user.username} (user {user.pk}), {PROVIDERS[provider].describe()}: {error}")
                continue
            counts.update(results)

        self.stdout.write(
            f"created {counts[CREATED]}, updated {counts[UPDATED]}, deleted {counts[DELETED]}, "
            f"unchanged {counts[UNCHANGED]}, skipped {len(skipped)} user(s)."
        )
        if skipped:
            self.stdout.write("Skipped (nothing changed for these users):")
            for line in skipped:
                self.stdout.write(f"  {line}")
            raise CommandError(f"Skipped {len(skipped)} user(s); see the list above.")
