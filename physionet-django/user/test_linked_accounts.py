"""
Tests for the linked account table, its mapping from the old ORCID and KHDP
tables, and the backfill, check and restore commands.

The test database holds the demo data, which has one ORCID link (user
george, iD '12345'), so these tests filter by user instead of assuming the
tables are empty.
"""
import datetime
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase

from user.linked_accounts import (
    CREATED,
    DELETED,
    PROVIDERS,
    TOKEN_FIELDS,
    UNCHANGED,
    UPDATED,
    LinkedAccountError,
    datetime_to_expiry,
    expiry_to_datetime,
    sync_user,
)
from user.models import KhdpAccount, LinkedAccount, Orcid, User

UTC = datetime.timezone.utc

ORCID_ID = '0000-0002-8983-9907'
OTHER_ORCID_ID = '0000-0001-5109-3700'
KHDP_UUID = '6f1c2a9e-0b7d-4c55-9a31-2e8d4b7f0c11'

# Seconds since the epoch with a fraction that every database stores exactly.
EXPIRY = Decimal('2242899965.5')
EXPIRY_DATETIME = datetime.datetime(2041, 1, 27, 11, 46, 5, 500000, tzinfo=UTC)
LINKED_AT = datetime.datetime(2024, 5, 6, 7, 8, 9, 123456, tzinfo=UTC)
KHDP_LINKED_AT = datetime.datetime(2025, 2, 3, 4, 5, 6, tzinfo=UTC)

ORCID_FIELDS = {
    'orcid_id': ORCID_ID,
    'name': 'Ada Lovelace',
    'access_token': 'c4548597-e368-4acb-bd06-1d8bcf13de46',
    'refresh_token': '3c68e7a9-7418-4d8d-bf31-1afcd2b7c742',
    'token_type': 'bearer',
    'token_scope': '/read-limited /activities/update',
    'token_expiration': EXPIRY,
}

KHDP_FIELDS = {
    'public_uuid': KHDP_UUID,
    'khdp_user_id': 'ada.l',
    'name': 'Ada Lovelace',
    'affiliation': 'Analytical Engine Society',
    'email': 'ada@example.com',
    'orcid': ORCID_ID,
    'physionet_id': 'a1b2c3d4-0000-4000-8000-000000000001',
    'access_token': 'khdp-access-token-value',
    'token_type': 'Bearer',
    'token_expiration': EXPIRY,
}


def assert_linked_account_matches(test, user, provider):
    """Check that the user's LinkedAccount row for `provider` matches their old row."""
    mapping = PROVIDERS[provider]
    linked = LinkedAccount.objects.get(user=user, provider=mapping.key)
    old = mapping.old_model.objects.get(user=user)
    test.assertEqual(mapping.differences(linked, mapping.values_from_old(old)), [])


def make_user(username):
    return User.objects.create_user(username=username, email=f'{username}@example.com', password='Tester11!')


def make_orcid(user, linked_at=LINKED_AT, **fields):
    """Create an old ORCID row with the given date (the model sets it to now)."""
    row = Orcid.objects.create(user=user, **{**ORCID_FIELDS, **fields})
    Orcid.objects.filter(pk=row.pk).update(datetime_added=linked_at)
    return Orcid.objects.get(pk=row.pk)


def make_khdp(user, linked_at=KHDP_LINKED_AT, **fields):
    """Create an old KHDP row with the given date (the model sets it to now)."""
    row = KhdpAccount.objects.create(user=user, **{**KHDP_FIELDS, **fields})
    KhdpAccount.objects.filter(pk=row.pk).update(datetime_added=linked_at)
    return KhdpAccount.objects.get(pk=row.pk)


def run(command, *args):
    """Run a command; return its output."""
    out = StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


def run_failing(test, command, *args):
    """Run a command that must fail; return its output."""
    out = StringIO()
    with test.assertRaises(CommandError):
        call_command(command, *args, stdout=out)
    return out.getvalue()


def linked_values(user):
    """All LinkedAccount rows of a user, as comparable tuples."""
    return list(
        LinkedAccount.objects.filter(user=user).order_by('provider').values_list(
            'pk', 'provider', 'external_id', 'linked_at', 'access_token', 'refresh_token',
            'token_type', 'token_scope', 'token_expires_at', 'provider_data',
        )
    )


class LinkedAccountConstraintTests(TestCase):
    """The database rules of the LinkedAccount table."""

    def setUp(self):
        self.user = make_user('rulesuser')
        self.other = make_user('rulesother')

    def create(self, user, provider='orcid', external_id=ORCID_ID):
        return LinkedAccount.objects.create(
            user=user, provider=provider, external_id=external_id, linked_at=LINKED_AT,
        )

    def test_refused_rows(self):
        self.create(self.user)
        cases = {
            'same iD on another user': {'user': self.other},
            'second link to one provider': {'user': self.user, 'external_id': OTHER_ORCID_ID},
            'blank iD': {'user': self.other, 'external_id': ''},
        }
        for case, fields in cases.items():
            with self.subTest(case), self.assertRaises(IntegrityError), transaction.atomic():
                self.create(**fields)

    def test_allowed_rows(self):
        # The same identifier at two providers, and one link to each provider.
        self.create(self.user, provider='orcid', external_id='shared-id')
        self.create(self.other, provider='khdp', external_id='shared-id')
        self.create(self.user, provider='khdp', external_id=KHDP_UUID)
        self.assertEqual(LinkedAccount.objects.filter(external_id='shared-id').count(), 2)
        self.assertEqual(LinkedAccount.objects.filter(user=self.user).count(), 2)

    def test_rows_are_deleted_with_the_user(self):
        self.create(self.user)
        self.user.delete()
        self.assertFalse(LinkedAccount.objects.filter(external_id=ORCID_ID).exists())


class ExpiryConversionTests(TestCase):
    """Old token expiry (seconds since the epoch) to datetime and back."""

    def test_conversion_is_exact_both_ways(self):
        cases = [
            (EXPIRY, EXPIRY_DATETIME),
            (Decimal('2242899965.166591'), datetime.datetime(2041, 1, 27, 11, 46, 5, 166591, tzinfo=UTC)),
        ]
        for seconds, moment in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(expiry_to_datetime(seconds), moment)
                self.assertEqual(datetime_to_expiry(moment), seconds)
        # 0 means no expiry.
        self.assertIsNone(expiry_to_datetime(Decimal(0)))
        self.assertIsNone(expiry_to_datetime(Decimal('0E-40')))
        self.assertEqual(datetime_to_expiry(None), 0)

    def test_odd_values_are_refused(self):
        for value in (Decimal(-1), Decimal('NaN'), Decimal('Infinity'), Decimal('1E+20'), 'soon', None):
            with self.subTest(value=value), self.assertRaises(LinkedAccountError):
                expiry_to_datetime(value)


class SyncUserTests(TestCase):
    """sync_user() makes the new row match the old one."""

    def setUp(self):
        self.user = make_user('syncuser')

    def test_results(self):
        make_khdp(self.user)
        self.assertEqual(sync_user(self.user, 'khdp'), CREATED)
        self.assertEqual(sync_user(self.user, 'orcid'), UNCHANGED)
        make_orcid(self.user)
        self.assertEqual(sync_user(self.user, 'orcid'), CREATED)
        self.assertEqual(sync_user(self.user, 'orcid'), UNCHANGED)
        Orcid.objects.filter(user=self.user).update(name='Augusta Ada King')
        self.assertEqual(sync_user(self.user, 'orcid'), UPDATED)
        self.assertEqual(
            LinkedAccount.objects.get(user=self.user, provider='orcid').provider_data, {'name': 'Augusta Ada King'},
        )
        Orcid.objects.filter(user=self.user).delete()
        self.assertEqual(sync_user(self.user, 'orcid'), DELETED)
        # The KHDP row is left alone.
        self.assertEqual(
            list(LinkedAccount.objects.filter(user=self.user).values_list('provider', flat=True)), ['khdp'],
        )

    def test_reads_the_old_row_from_the_database(self):
        make_orcid(self.user)
        user = User.objects.get(pk=self.user.pk)
        # Cache the old row on the user, then change it in the database.
        self.assertEqual(user.orcid.orcid_id, ORCID_ID)
        Orcid.objects.filter(user=user).update(orcid_id=OTHER_ORCID_ID)
        sync_user(user, 'orcid')
        self.assertEqual(LinkedAccount.objects.get(user=user).external_id, OTHER_ORCID_ID)

        Orcid.objects.filter(user=user).delete()
        self.assertEqual(sync_user(user, 'orcid'), DELETED)
        self.assertFalse(LinkedAccount.objects.filter(user=user).exists())

    def test_no_token_in_provider_data(self):
        for key, mapping in PROVIDERS.items():
            with self.subTest(provider=key):
                self.assertFalse(any('token' in field for field in mapping.kept_fields), mapping.kept_fields)
        make_orcid(self.user)
        make_khdp(self.user)
        sync_user(self.user, 'orcid')
        sync_user(self.user, 'khdp')
        tokens = {ORCID_FIELDS['access_token'], ORCID_FIELDS['refresh_token'], KHDP_FIELDS['access_token']}
        for linked in LinkedAccount.objects.filter(user=self.user):
            with self.subTest(provider=linked.provider):
                self.assertEqual(set(linked.provider_data), set(PROVIDERS[linked.provider].kept_fields))
                self.assertFalse(tokens & set(linked.provider_data.values()))


class BackfillTests(TestCase):
    """The backfill_linked_accounts command."""

    def setUp(self):
        self.user = make_user('filluser')

    def test_copies_every_field(self):
        make_orcid(self.user)
        make_khdp(self.user)
        run('backfill_linked_accounts')
        expected = {
            'orcid': {
                'external_id': ORCID_ID,
                'linked_at': LINKED_AT,
                'access_token': ORCID_FIELDS['access_token'],
                'refresh_token': ORCID_FIELDS['refresh_token'],
                'token_type': 'bearer',
                'token_scope': '/read-limited /activities/update',
                'token_expires_at': EXPIRY_DATETIME,
                'provider_data': {'name': 'Ada Lovelace'},
            },
            'khdp': {
                'external_id': KHDP_UUID,
                'linked_at': KHDP_LINKED_AT,
                'access_token': 'khdp-access-token-value',
                'refresh_token': None,
                'token_type': 'Bearer',
                'token_scope': None,
                'token_expires_at': EXPIRY_DATETIME,
                'provider_data': {
                    'khdp_user_id': 'ada.l',
                    'name': 'Ada Lovelace',
                    'affiliation': 'Analytical Engine Society',
                    'email': 'ada@example.com',
                    'orcid': ORCID_ID,
                    'physionet_id': 'a1b2c3d4-0000-4000-8000-000000000001',
                },
            },
        }
        for provider, values in expected.items():
            with self.subTest(provider=provider):
                linked = LinkedAccount.objects.filter(user=self.user, provider=provider).values(*values).get()
                self.assertEqual(linked, values)
        # The demo row's invalid iD is copied too (check_linked_accounts warns about it).
        george = Orcid.objects.get(user__username='george')
        linked = LinkedAccount.objects.get(user=george.user, provider='orcid')
        self.assertEqual((linked.external_id, linked.linked_at), ('12345', george.datetime_added))

    def test_empty_values_become_null(self):
        make_orcid(self.user, name='', access_token='', refresh_token='', token_type='', token_scope='',
                   token_expiration=0)
        run('backfill_linked_accounts')
        linked = LinkedAccount.objects.get(user=self.user, provider='orcid')
        for field in TOKEN_FIELDS + ('token_expires_at',):
            with self.subTest(field=field):
                self.assertIsNone(getattr(linked, field))
        self.assertEqual(linked.provider_data, {'name': ''})

    def test_running_twice_gives_the_same_rows(self):
        make_orcid(self.user)
        make_khdp(self.user)
        run('backfill_linked_accounts')
        before = linked_values(self.user)
        self.assertEqual(len(before), 2)
        output = run('backfill_linked_accounts')
        self.assertIn('created 0, updated 0, deleted 0', output)
        self.assertEqual(linked_values(self.user), before)

    def test_brings_changed_rows_up_to_date(self):
        make_orcid(self.user)
        stray = make_user('strayuser')
        LinkedAccount.objects.create(user=stray, provider='khdp', external_id=KHDP_UUID, linked_at=LINKED_AT)
        run('backfill_linked_accounts')
        Orcid.objects.filter(user=self.user).update(orcid_id=OTHER_ORCID_ID)
        output = run('backfill_linked_accounts')
        self.assertIn('created 0, updated 1, deleted 0', output)
        self.assertEqual(LinkedAccount.objects.get(user=self.user).external_id, OTHER_ORCID_ID)
        # A new row without an old row was deleted by the first run.
        self.assertFalse(LinkedAccount.objects.filter(user=stray).exists())

    def test_rows_that_cannot_be_copied_are_listed_and_skipped(self):
        empty_id = make_user('emptyid')
        make_orcid(empty_id, orcid_id='')
        odd_expiry = make_user('oddexpiry')
        make_khdp(odd_expiry, token_expiration=Decimal(-5))
        # Two users with the same iD: the first is copied, the second clashes.
        make_orcid(self.user)
        clash = make_user('clashuser')
        make_orcid(clash)
        # A user whose ORCID row can be copied but whose KHDP row can't:
        # nothing is changed for that user.
        half = make_user('halfuser')
        make_orcid(half, orcid_id=OTHER_ORCID_ID)
        make_khdp(half, public_uuid='')

        # The run goes on past the skipped users, then fails.
        output = run_failing(self, 'backfill_linked_accounts')

        self.assertIn('skipped 4 user(s)', output)
        self.assertIn(f'emptyid (user {empty_id.pk}), ORCID: ORCID identifier is empty', output)
        self.assertIn(f'oddexpiry (user {odd_expiry.pk}), KHDP: token expiry -5 is not a valid time', output)
        self.assertIn(f'clashuser (user {clash.pk}), ORCID:', output)
        self.assertIn(f'halfuser (user {half.pk}), KHDP: KHDP identifier is empty', output)
        for user in (empty_id, odd_expiry, clash, half):
            with self.subTest(user=user.username):
                self.assertFalse(LinkedAccount.objects.filter(user=user).exists())
        self.assertEqual(LinkedAccount.objects.get(user=self.user).external_id, ORCID_ID)
        self.assertTrue(LinkedAccount.objects.filter(user__username='george').exists())


class CheckTests(TestCase):
    """The check_linked_accounts command."""

    def setUp(self):
        self.user = make_user('checkuser')
        make_orcid(self.user)
        make_khdp(self.user)
        run('backfill_linked_accounts')

    def test_clean_after_backfill(self):
        output = run('check_linked_accounts')
        george = User.objects.get(username='george')
        self.assertIn('Problems (fix these before copying): 0', output)
        # An invalid iD is only a warning.
        self.assertIn('Warnings: 1', output)
        self.assertIn(f"george (user {george.pk}): ORCID iD '12345' is not a valid ORCID iD", output)
        self.assertNotIn(ORCID_ID, output)
        self.assertIn('Differences between old and new rows: 0', output)
        self.assertIn('No problems or differences.', output)

    def test_expiry_within_a_second_is_not_a_difference(self):
        LinkedAccount.objects.filter(user=self.user, provider='orcid').update(
            token_expires_at=EXPIRY_DATETIME + datetime.timedelta(microseconds=400000),
        )
        output = run('check_linked_accounts')
        self.assertIn('Differences between old and new rows: 0', output)

    def test_reports_rows_that_cannot_be_copied(self):
        empty_orcid = make_user('emptyorcid')
        make_orcid(empty_orcid, orcid_id='')
        empty_khdp = make_user('emptykhdp')
        make_khdp(empty_khdp, public_uuid='')
        KhdpAccount.objects.filter(user=self.user).update(token_expiration=Decimal(-1))
        for args in ((), ('--old-only',)):
            with self.subTest(args=args):
                output = run_failing(self, 'check_linked_accounts', *args)
                self.assertIn('Problems (fix these before copying): 3', output)
                self.assertIn(f"emptyorcid (user {empty_orcid.pk}): ORCID row can't be copied: "
                              "ORCID identifier is empty", output)
                self.assertIn(f"emptykhdp (user {empty_khdp.pk}): KHDP row can't be copied: "
                              "KHDP identifier is empty", output)
                self.assertIn(f"checkuser (user {self.user.pk}): KHDP row can't be copied: "
                              "token expiry -1 is not a valid time", output)

    def test_reports_the_same_id_on_two_users(self):
        other = make_user('checkother')
        make_orcid(other)
        for args in ((), ('--old-only',)):
            with self.subTest(args=args):
                output = run_failing(self, 'check_linked_accounts', *args)
                self.assertIn(
                    f'ORCID iD {ORCID_ID} is linked to more than one user: checkuser (user {self.user.pk}), '
                    f'checkother (user {other.pk})',
                    output,
                )

    def test_reports_each_difference(self):
        def change(**fields):
            return lambda: LinkedAccount.objects.filter(user=self.user, provider='orcid').update(**fields)

        cases = [
            ('ORCID rows differ in external_id', change(external_id=OTHER_ORCID_ID)),
            ('ORCID rows differ in linked_at', change(linked_at=LINKED_AT + datetime.timedelta(days=1))),
            ('ORCID rows differ in access_token', change(access_token='other')),
            ('ORCID rows differ in refresh_token', change(refresh_token=None)),
            ('ORCID rows differ in token_type', change(token_type='mac')),
            ('ORCID rows differ in token_scope', change(token_scope='/authenticate')),
            ('ORCID rows differ in token_expires_at',
             change(token_expires_at=EXPIRY_DATETIME + datetime.timedelta(seconds=2))),
            ('ORCID rows differ in token_expires_at', change(token_expires_at=None)),
            ('ORCID rows differ in provider_data', change(provider_data={'name': 'Someone else'})),
            ('ORCID rows differ in provider_data',
             change(provider_data={'name': 'Ada Lovelace', 'access_token': 'x'})),
            ('ORCID old row has no linked account',
             LinkedAccount.objects.filter(user=self.user, provider='orcid').delete),
            ('KHDP linked account has no old row', KhdpAccount.objects.filter(user=self.user).delete),
        ]
        for number, (message, make_change) in enumerate(cases, 1):
            with self.subTest(case=number, message=message), transaction.atomic():
                make_change()
                output = run_failing(self, 'check_linked_accounts')
                self.assertIn(f'checkuser (user {self.user.pk}): {message}', output)
                self.assertIn('Differences between old and new rows: 1', output)
                transaction.set_rollback(True)

    def test_changes_nothing(self):
        Orcid.objects.filter(user=self.user).update(name='Changed')
        before = linked_values(self.user)
        old_before = list(Orcid.objects.filter(user=self.user).values())
        run_failing(self, 'check_linked_accounts')
        self.assertEqual(linked_values(self.user), before)
        self.assertEqual(list(Orcid.objects.filter(user=self.user).values()), old_before)

    def test_old_only_skips_the_comparison(self):
        # Old rows without new rows (as before the first copy) and a new row
        # without an old row: the full check fails, the old-only check doesn't.
        LinkedAccount.objects.filter(provider='orcid').delete()
        KhdpAccount.objects.filter(user=self.user).delete()
        output = run_failing(self, 'check_linked_accounts')
        self.assertIn(f'checkuser (user {self.user.pk}): ORCID old row has no linked account', output)
        self.assertIn(f'checkuser (user {self.user.pk}): KHDP linked account has no old row', output)

        count = LinkedAccount.objects.count()
        output = run('check_linked_accounts', '--old-only')
        self.assertIn('Problems (fix these before copying): 0', output)
        self.assertIn('Warnings: 1', output)
        self.assertNotIn('Differences', output)
        self.assertNotIn('has no linked account', output)
        self.assertNotIn('has no old row', output)
        self.assertIn('No problems. Old tables only', output)
        self.assertEqual(LinkedAccount.objects.count(), count)


class RestoreTests(TestCase):
    """The restore_linked_accounts command."""

    def setUp(self):
        self.user = make_user('restoreuser')
        make_orcid(self.user, token_expiration=Decimal('2242899965.166591'))
        make_khdp(self.user)
        run('backfill_linked_accounts')

    def old_values(self, model):
        values = model.objects.filter(user=self.user).values()[0]
        del values['id']
        expiration = values.pop('token_expiration')
        return values, expiration

    def test_backfill_then_restore_gives_the_same_rows(self):
        before = {model: self.old_values(model) for model in (Orcid, KhdpAccount)}
        Orcid.objects.filter(user=self.user).delete()
        KhdpAccount.objects.filter(user=self.user).delete()

        output = run('restore_linked_accounts')

        self.assertIn('Restored 2,', output)
        for model, (values, expiration) in before.items():
            with self.subTest(model=model.__name__):
                restored_values, restored_expiration = self.old_values(model)
                # All fields, including the original datetime_added.
                self.assertEqual(restored_values, values)
                # Expiry to the second (databases differ below that).
                self.assertEqual(int(restored_expiration), int(expiration))
        self.assertEqual(Orcid.objects.get(user=self.user).datetime_added, LINKED_AT)
        run('check_linked_accounts')

    def test_never_overwrites(self):
        Orcid.objects.filter(user=self.user).update(name='Changed by hand')
        KhdpAccount.objects.filter(user=self.user).delete()
        output = run('restore_linked_accounts')
        self.assertIn('Restored 1,', output)
        self.assertEqual(list(Orcid.objects.filter(user=self.user).values_list('name', flat=True)),
                         ['Changed by hand'])
        self.assertTrue(KhdpAccount.objects.filter(user=self.user).exists())

    def test_clash_is_listed_and_skipped(self):
        KhdpAccount.objects.filter(user=self.user).delete()
        other = make_user('restoreother')
        make_khdp(other)
        # The run goes on past the clash, then fails.
        output = run_failing(self, 'restore_linked_accounts')
        self.assertIn('Restored 0,', output)
        self.assertIn('skipped 1.', output)
        self.assertIn(f'restoreuser (user {self.user.pk}), KHDP:', output)
        self.assertFalse(KhdpAccount.objects.filter(user=self.user).exists())
        self.assertTrue(Orcid.objects.filter(user=self.user).exists())
