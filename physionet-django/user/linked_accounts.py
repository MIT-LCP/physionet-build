"""
Mapping between the old per-provider link tables (Orcid, KhdpAccount) and
the shared LinkedAccount table.

Each provider has one small mapping class that knows its old model, its
identifier field, its token fields and the other fields it keeps.
sync_user() makes a user's LinkedAccount row match their old row; the
views that write the old rows and the backfill_linked_accounts command use
it, and check_linked_accounts and
restore_linked_accounts use the same mappings, so the three can't drift
apart.
"""
import datetime
from decimal import Decimal, InvalidOperation

from user.models import KhdpAccount, LinkedAccount, Orcid

EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

# Token columns of LinkedAccount. A provider fills the ones it has; the
# rest stay null.
TOKEN_FIELDS = ('access_token', 'refresh_token', 'token_type', 'token_scope')

# The old tables store the token expiry as seconds since the epoch, which
# some databases round-trip with less than microsecond precision. Expiry
# times closer than this are treated as equal.
EXPIRY_TOLERANCE = datetime.timedelta(seconds=1)

# Results of sync_user()
CREATED = 'created'
UPDATED = 'updated'
DELETED = 'deleted'
UNCHANGED = 'unchanged'


class LinkedAccountError(ValueError):
    """An old row that cannot be copied to LinkedAccount."""


def expiry_to_datetime(value):
    """
    Convert an old token expiry (seconds since the epoch) to a datetime.

    The old tables store 0 when there is no expiry; that becomes None.
    Values that are not a usable time raise LinkedAccountError.
    """
    try:
        seconds = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise LinkedAccountError(f'token expiry {value!r} is not a number')
    if not seconds.is_finite() or seconds < 0:
        raise LinkedAccountError(f'token expiry {seconds.normalize()} is not a valid time')
    if seconds == 0:
        return None
    try:
        return EPOCH + datetime.timedelta(seconds=float(seconds))
    except OverflowError:
        raise LinkedAccountError(f'token expiry {seconds.normalize()} is out of range')


def datetime_to_expiry(value):
    """
    Convert a datetime back to the old format (seconds since the epoch).

    None becomes 0, as in the old tables. The conversion is exact.
    """
    if value is None:
        return Decimal(0)
    delta = value - EPOCH
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(10**6)


class ProviderMapping:
    """How one provider's old table maps to LinkedAccount."""
    # The LinkedAccount.Provider value, as a plain string
    key = None
    # The old model, with a one-to-one `user` field and `datetime_added`
    old_model = None
    # The old field that holds the provider's identifier
    id_field = None
    # Token fields the old model has (a subset of TOKEN_FIELDS)
    token_fields = ()
    # Other old fields copied into provider_data. Never list tokens here.
    kept_fields = ()

    def describe(self):
        return LinkedAccount.Provider(self.key).label

    def get_old_row(self, user_id):
        """Read the user's old row from the database (not a cached copy)."""
        return self.old_model.objects.filter(user_id=user_id).first()

    def values_from_old(self, old):
        """
        Return the LinkedAccount field values for an old row.

        Raises LinkedAccountError if the row cannot be copied.
        """
        external_id = getattr(old, self.id_field)
        if not external_id:
            raise LinkedAccountError(f'{self.describe()} identifier is empty')
        values = {
            'external_id': external_id,
            'linked_at': old.datetime_added,
            'token_expires_at': expiry_to_datetime(old.token_expiration),
            'provider_data': {field: getattr(old, field) for field in self.kept_fields},
        }
        for field in TOKEN_FIELDS:
            values[field] = (getattr(old, field) or None) if field in self.token_fields else None
        return values

    def values_to_old(self, linked):
        """
        Return the old model's field values for a LinkedAccount row.

        datetime_added is not included: the old models set it to the
        current time on creation, so it has to be written afterwards.
        """
        values = {
            self.id_field: linked.external_id,
            'token_expiration': datetime_to_expiry(linked.token_expires_at),
        }
        for field in self.token_fields:
            values[field] = getattr(linked, field) or ''
        for field in self.kept_fields:
            values[field] = linked.provider_data.get(field, '')
        return values

    @staticmethod
    def differences(linked, values):
        """Return the names of the fields where `linked` differs from `values`."""
        changed = []
        for field, value in values.items():
            current = getattr(linked, field)
            if field == 'token_expires_at' and current is not None and value is not None:
                if abs(current - value) < EXPIRY_TOLERANCE:
                    continue
            if current != value:
                changed.append(field)
        return changed


class OrcidMapping(ProviderMapping):
    key = LinkedAccount.Provider.ORCID.value
    old_model = Orcid
    id_field = 'orcid_id'
    token_fields = ('access_token', 'refresh_token', 'token_type', 'token_scope')
    kept_fields = ('name',)


class KhdpMapping(ProviderMapping):
    key = LinkedAccount.Provider.KHDP.value
    old_model = KhdpAccount
    id_field = 'public_uuid'
    token_fields = ('access_token', 'token_type')
    kept_fields = ('khdp_user_id', 'name', 'affiliation', 'email', 'orcid', 'physionet_id')


PROVIDERS = {mapping.key: mapping for mapping in (OrcidMapping(), KhdpMapping())}


def held_by_another_user(user, provider, external_id):
    """
    Return whether another user's old or LinkedAccount row has this identifier.

    `user` is None for a new user (sign-up): then any row counts. The views
    that write the old rows call this after an IntegrityError, to tell a
    clash with another user's link from other failures.
    """
    mapping = PROVIDERS[provider]
    old_rows = mapping.old_model.objects.filter(**{mapping.id_field: external_id})
    linked_rows = LinkedAccount.objects.filter(provider=mapping.key, external_id=external_id)
    if user is not None:
        old_rows = old_rows.exclude(user_id=user.pk)
        linked_rows = linked_rows.exclude(user_id=user.pk)
    return old_rows.exists() or linked_rows.exists()


def sync_user(user, provider):
    """
    Make the user's LinkedAccount row for `provider` match their old row.

    The old row is read fresh from the database. If the user has no old
    row, their LinkedAccount row (if any) is deleted. Returns CREATED,
    UPDATED, DELETED or UNCHANGED.

    Raises LinkedAccountError if the old row cannot be copied, and lets
    IntegrityError through if the database refuses the row (for example,
    another user already holds the identifier). Callers that keep going
    after an error should call this inside transaction.atomic().
    """
    mapping = PROVIDERS[provider]
    old = mapping.get_old_row(user.pk)
    linked = LinkedAccount.objects.filter(user_id=user.pk, provider=mapping.key).first()

    if old is None:
        if linked is None:
            return UNCHANGED
        linked.delete()
        return DELETED

    values = mapping.values_from_old(old)
    if linked is None:
        LinkedAccount.objects.create(user_id=user.pk, provider=mapping.key, **values)
        return CREATED

    changed = mapping.differences(linked, values)
    if not changed:
        return UNCHANGED
    for field in changed:
        setattr(linked, field, values[field])
    linked.save(update_fields=changed)
    return UPDATED
