from events import models
from django.contrib import admin

# Register your models here.
# Register the Event and Participants on the site
admin.site.register(models.Event)
admin.site.register(models.EventParticipant)
