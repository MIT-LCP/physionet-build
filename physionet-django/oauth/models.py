from django.conf import settings
from django.db import models
from oauth2_provider.settings import oauth2_settings


class Partner(models.Model):
    class Status(models.TextChoices):
        ACTIVE    = 'active',    'Active'
        SUSPENDED = 'suspended', 'Suspended'
        REVOKED   = 'revoked',   'Revoked'

    application           = models.OneToOneField(
                                oauth2_settings.APPLICATION_MODEL,
                                on_delete=models.CASCADE,
                                related_name='partner',
                            )
    organization_name     = models.CharField(max_length=200)
    contact_name          = models.CharField(max_length=200, blank=True)
    contact_email         = models.EmailField(blank=True)
    agreement_signed_date = models.DateField(null=True, blank=True)

    # Subset of OAUTH2_PROVIDER['SCOPES'] keys this partner is allowed to
    # request. Empty list = wildcard (all configured scopes), preserved for
    # legacy Applications that predate this model.
    allowed_scopes        = models.JSONField(default=list, blank=True)

    # Whitespace-separated list of URIs the partner may pass as
    # post_logout_redirect_uri to /oauth/end-session/. Stored on Partner
    # because DOT 2.2.0's swappable Application has no equivalent field.
    post_logout_redirect_uris = models.TextField(blank=True)

    # PKCE is required by default (OAuth 2.1 / RFC 9700). Some upstream
    # federators act as the OAuth client without sending a code_challenge;
    # opt those partners out here rather than disabling PKCE globally.
    requires_pkce         = models.BooleanField(default=True)

    status                = models.CharField(
                                max_length=20,
                                choices=Status.choices,
                                default=Status.ACTIVE,
                            )
    status_reason         = models.TextField(blank=True)
    status_changed_at     = models.DateTimeField(null=True, blank=True)

    created_at            = models.DateTimeField(auto_now_add=True)
    created_by            = models.ForeignKey(
                                settings.AUTH_USER_MODEL,
                                on_delete=models.PROTECT,
                                related_name='+',
                                null=True,
                            )

    class Meta:
        ordering = ['organization_name']

    def __str__(self):
        return f'{self.organization_name} ({self.application.client_id})'

    @property
    def is_legacy(self):
        return self.organization_name.startswith('Legacy: ')
