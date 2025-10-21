from django.db import models
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
import re


class FederatedSite(models.Model):
    """
    Represents an external site for federated search.
    """
    SITE_TYPE_CHOICES = [
        ('physionet', 'PhysioNet Instance'),
        ('generic_api', 'Generic API Repository'),
    ]

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier (e.g., 'healthdatanexus')"
    )
    display_name = models.CharField(
        max_length=200,
        help_text="Display name shown in UI (e.g., 'HDN')"
    )
    base_url = models.URLField(
        max_length=500,
        help_text="Base URL (e.g., 'https://healthdatanexus.ca')"
    )
    api_endpoint = models.CharField(
        max_length=500,
        help_text="API endpoint path for search"
    )
    site_type = models.CharField(
        max_length=20,
        choices=SITE_TYPE_CHOICES,
        default='physionet',
        help_text="Type of repository"
    )
    enabled = models.BooleanField(
        default=True,
        help_text="Enable/disable this site in federated search"
    )
    auth_token = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Optional API key/token for authenticated access"
    )
    timeout_seconds = models.PositiveIntegerField(
        default=5,
        help_text="Request timeout in seconds"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order (lower = higher priority)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Federated Site'
        verbose_name_plural = 'Federated Sites'

    def __str__(self):
        return f"{self.display_name} ({self.name})"

    def clean(self):
        """Validate URL to prevent SSRF attacks"""
        super().clean()
        # Prevent localhost, 127.0.0.1, internal IPs
        forbidden_patterns = [
            r'localhost',
            r'127\.0\.0\.',
            r'192\.168\.',
            r'10\.',
            r'172\.(1[6-9]|2[0-9]|3[0-1])\.',
            r'0\.0\.0\.0',
            r'\[::1\]',
            r'\[::\]',
        ]
        for pattern in forbidden_patterns:
            if re.search(pattern, self.base_url, re.IGNORECASE):
                raise ValidationError({
                    'base_url': 'Internal/private IP addresses are not allowed'
                })

    def get_full_search_url(self):
        """Construct full search URL"""
        return f"{self.base_url.rstrip('/')}{self.api_endpoint}"
