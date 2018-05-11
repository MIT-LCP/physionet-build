from django.contrib import admin
from . import models


admin.site.register(models.Author)
admin.site.register(models.Invitation)
admin.site.register(models.Project)
admin.site.register(models.PublishedProject)
admin.site.register(models.Topic)
admin.site.register(models.PublishedTopic)
