from django.contrib import admin
from .models import Project, PublishedProject


admin.site.register(Project)
admin.site.register(PublishedProject)
