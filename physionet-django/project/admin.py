from django.contrib import admin
from .models import Author, Invitation, Project, PublishedProject


admin.site.register(Author)
admin.site.register(Invitation)
admin.site.register(Project)
admin.site.register(PublishedProject)
