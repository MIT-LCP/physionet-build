from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from user.linked_accounts import PROVIDERS, LinkedAccountError
from user.models import LinkedAccount, Orcid
from user.validators import validate_orcid_id


def describe_user(user):
    return f"{user.username} (user {user.pk})"


class Command(BaseCommand):
    help = (
        "Check the ORCID and KHDP links before and after copying them to the linked account table. "
        "Reports problems in the old data that block copying, warnings, and differences between "
        "the old and new rows. Fails only on problems and differences (with --old-only, only on "
        "problems). Changes nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--old-only', action='store_true',
            help="Check only the old tables, for use before the first copy. Reports problems and "
                 "warnings, skips the comparison with the linked account table.",
        )

    def handle(self, *args, **options):
        old_only = options['old_only']
        problems = []
        warnings = []
        differences = []

        duplicate_ids = (
            Orcid.objects.exclude(orcid_id='')
            .values('orcid_id')
            .annotate(users=Count('user', distinct=True))
            .filter(users__gt=1)
            .order_by('orcid_id')
        )
        for duplicate in duplicate_ids:
            holders = Orcid.objects.filter(orcid_id=duplicate['orcid_id']).select_related('user').order_by('user_id')
            names = ', '.join(describe_user(row.user) for row in holders)
            problems.append(f"ORCID iD {duplicate['orcid_id']} is linked to more than one user: {names}")

        for row in Orcid.objects.exclude(orcid_id='').select_related('user').order_by('user_id'):
            try:
                validate_orcid_id(row.orcid_id)
            except ValidationError:
                warnings.append(f"{describe_user(row.user)}: ORCID iD {row.orcid_id!r} is not a valid ORCID iD")

        for mapping in PROVIDERS.values():
            name = mapping.describe()
            old_rows = {row.user_id: row for row in mapping.old_model.objects.select_related('user')}
            new_rows = {} if old_only else {
                row.user_id: row
                for row in LinkedAccount.objects.filter(provider=mapping.key).select_related('user')
            }
            for user_id in sorted(old_rows.keys() | new_rows.keys()):
                old = old_rows.get(user_id)
                linked = new_rows.get(user_id)
                user = (old or linked).user
                if old is None:
                    differences.append(f"{describe_user(user)}: {name} linked account has no old row")
                    continue
                try:
                    values = mapping.values_from_old(old)
                except LinkedAccountError as error:
                    problems.append(f"{describe_user(user)}: {name} row can't be copied: {error}")
                    continue
                if old_only:
                    continue
                if linked is None:
                    differences.append(f"{describe_user(user)}: {name} old row has no linked account")
                    continue
                changed = mapping.differences(linked, values)
                if changed:
                    differences.append(f"{describe_user(user)}: {name} rows differ in {', '.join(changed)}")

        sections = [
            ("Problems (fix these before copying)", problems),
            ("Warnings", warnings),
        ]
        if not old_only:
            sections.append(("Differences between old and new rows", differences))
        for title, lines in sections:
            self.stdout.write(f"{title}: {len(lines)}")
            for line in lines:
                self.stdout.write(f"  {line}")

        if old_only:
            if problems:
                raise CommandError(f"Found {len(problems)} problem(s).")
            self.stdout.write("No problems. Old tables only; not compared with the linked account table.")
            return
        if problems or differences:
            raise CommandError(f"Found {len(problems)} problem(s) and {len(differences)} difference(s).")
        self.stdout.write("No problems or differences.")
