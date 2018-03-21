from django.contrib import admin
from .models import Invitation, Project, PublishedProject


admin.site.register(Invitation)
admin.site.register(Project)
admin.site.register(PublishedProject)
