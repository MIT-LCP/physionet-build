from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from user.linked_accounts import PROVIDERS
from user.models import LinkedAccount


class Command(BaseCommand):
    help = (
        "Rebuild missing ORCID and KHDP rows in the old tables from the linked account table. "
        "Existing old rows are never changed. Fails at the end if any row was skipped."
    )

    def handle(self, *args, **options):
        restored = 0
        kept = 0
        skipped = []
        for linked in LinkedAccount.objects.select_related('user').order_by('user_id', 'provider'):
            who = f"{linked.user.username} (user {linked.user_id})"
            mapping = PROVIDERS.get(linked.provider)
            if mapping is None:
                skipped.append(f"{who}: unknown provider {linked.provider!r}")
                continue
            if mapping.old_model.objects.filter(user_id=linked.user_id).exists():
                kept += 1
                continue
            try:
                with transaction.atomic():
                    old = mapping.old_model.objects.create(user_id=linked.user_id, **mapping.values_to_old(linked))
                    # datetime_added is auto_now_add, so the original date
                    # can only be set by a second write.
                    mapping.old_model.objects.filter(pk=old.pk).update(datetime_added=linked.linked_at)
            except IntegrityError as error:
                skipped.append(f"{who}, {mapping.describe()}: {error}")
                continue
            restored += 1

        self.stdout.write(f"Restored {restored}, already present {kept}, skipped {len(skipped)}.")
        if skipped:
            self.stdout.write("Skipped:")
            for line in skipped:
                self.stdout.write(f"  {line}")
            raise CommandError(f"Skipped {len(skipped)} row(s); see the list above.")
