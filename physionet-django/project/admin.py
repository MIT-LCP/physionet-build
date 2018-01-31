from django.contrib import admin
from .models import Database, Project, SoftwarePackage

admin.site.register(Database)
admin.site.register(Project)
admin.site.register(SoftwarePackage)
