from django.contrib import admin

from .models import FederatedSite


@admin.register(FederatedSite)
class FederatedSiteAdmin(admin.ModelAdmin):
    list_display = [
        'display_name', 'name', 'base_url', 'site_type', 'enabled',
        'order', 'updated_at'
    ]
    list_filter = ['enabled', 'site_type']
    search_fields = ['name', 'display_name', 'base_url']
    list_editable = ['enabled', 'order']
    ordering = ['order', 'name']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'display_name', 'enabled', 'order')
        }),
        ('API Configuration', {
            'fields': ('base_url', 'api_endpoint', 'site_type', 'timeout_seconds')
        }),
        ('Authentication', {
            'fields': ('auth_token',),
            'classes': ('collapse',),
            'description': (
                'Optional: Provide API key or OAuth token if the '
                'external site requires authentication'
            )
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def get_fieldsets(self, request, obj=None):
        """Add metadata fieldset only when editing existing objects"""
        fieldsets = super().get_fieldsets(request, obj)
        if obj:  # Editing existing object - show metadata
            return fieldsets + (
                ('Metadata', {
                    'fields': ('created_at', 'updated_at'),
                    'classes': ('collapse',),
                }),
            )
        return fieldsets
