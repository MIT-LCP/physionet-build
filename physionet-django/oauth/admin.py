from django.contrib import admin

from oauth.models import Partner


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display  = ('organization_name', 'application', 'status', 'agreement_signed_date', 'created_at')
    list_filter   = ('status',)
    search_fields = ('organization_name', 'contact_email', 'application__client_id')
    raw_id_fields = ('application', 'created_by')


# DOT auto-registers Application; we don't re-register here.
