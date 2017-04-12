from django.contrib import admin
from models import *

# Custom form for admin site
#class ProjectAdmin(admin.ModelAdmin):
#    fields = ['projecttype', 'requestedstorage']

# register the model
#admin.site.register(Project, ProjectAdmin)
admin.site.register(Project)