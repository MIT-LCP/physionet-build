from ckeditor.fields import RichTextField
from ckeditor.widgets import CKEditorWidget
from django.contrib import admin
from django.db.models import CharField, TextField
from django.forms import TextInput, Textarea

from . import models


class LicenseAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}


admin.site.register(models.Author)
admin.site.register(models.AuthorInvitation)
admin.site.register(models.CoreProject)
admin.site.register(models.License, LicenseAdmin)
admin.site.register(models.ActiveProject)
admin.site.register(models.Reference)
admin.site.register(models.PublishedProject)
admin.site.register(models.PublishedTopic)
admin.site.register(models.ProgrammingLanguage)
admin.site.register(models.Topic)




class LegacyProjectModelAdmin(admin.ModelAdmin):
    formfield_overrides = {
        CharField: {'widget': TextInput(attrs={'size':'200'})},
        TextField: {'widget': Textarea(attrs={'rows':4, 'cols':40})},
    }

admin.site.register(models.LegacyProject, LegacyProjectModelAdmin)
