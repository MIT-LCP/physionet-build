from django.contrib import admin
from search.models import FederatedSite, FederatedProject, FederationSyncLog


@admin.register(FederatedSite)
class FederatedSiteAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'site_identifier', 'is_active', 'last_sync_status', 'last_sync_datetime')
    list_filter = ('is_active', 'last_sync_status')
    search_fields = ('site_name', 'site_identifier', 'api_base_url')
    readonly_fields = ('created', 'modified', 'last_sync_datetime', 'last_sync_status')
    fieldsets = (
        ('Basic Information', {
            'fields': ('site_name', 'site_identifier', 'api_base_url')
        }),
        ('Status', {
            'fields': ('is_active', 'last_sync_status', 'last_sync_datetime')
        }),
        ('Metadata', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )


@admin.register(FederatedProject)
class FederatedProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'version', 'source_site', 'resource_type', 'access_policy', 'publish_datetime')
    list_filter = ('source_site', 'resource_type', 'access_policy', 'publish_datetime')
    search_fields = ('title', 'slug', 'abstract', 'public_project_uuid')
    readonly_fields = ('public_project_uuid', 'last_fetched')
    date_hierarchy = 'publish_datetime'
    fieldsets = (
        ('Source', {
            'fields': ('source_site', 'public_project_uuid', 'source_url')
        }),
        ('Project Information', {
            'fields': ('title', 'slug', 'version', 'abstract', 'doi')
        }),
        ('Classification', {
            'fields': ('resource_type', 'access_policy', 'topics')
        }),
        ('Storage & Publishing', {
            'fields': ('publish_datetime', 'main_storage_size')
        }),
        ('Sync Tracking', {
            'fields': ('last_fetched',),
            'classes': ('collapse',)
        }),
    )


@admin.register(FederationSyncLog)
class FederationSyncLogAdmin(admin.ModelAdmin):
    list_display = (
        'site', 'status', 'started_at', 'completed_at',
        'projects_fetched', 'projects_created',
        'projects_updated', 'projects_deleted'
    )
    list_filter = ('status', 'site', 'started_at')
    search_fields = ('site__site_name', 'error_message')
    readonly_fields = (
        'started_at', 'completed_at',
        'projects_fetched', 'projects_created',
        'projects_updated', 'projects_deleted', 'error_message'
    )
    date_hierarchy = 'started_at'
    fieldsets = (
        ('Sync Information', {
            'fields': ('site', 'status', 'started_at', 'completed_at')
        }),
        ('Statistics', {
            'fields': ('projects_fetched', 'projects_created', 'projects_updated', 'projects_deleted')
        }),
        ('Errors', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
    )
