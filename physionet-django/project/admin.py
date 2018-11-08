from django.contrib import admin

from . import models


class LicenseAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}


class DataUseAgreementAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}


admin.site.register(models.Author)
admin.site.register(models.AuthorInvitation)
admin.site.register(models.CoreProject)
admin.site.register(models.DataUseAgreement, DataUseAgreementAdmin)
admin.site.register(models.License, LicenseAdmin)
admin.site.register(models.ActiveProject)
admin.site.register(models.Reference)
admin.site.register(models.PublishedProject)
admin.site.register(models.PublishedTopic)
admin.site.register(models.ProgrammingLanguage)
admin.site.register(models.Topic)
