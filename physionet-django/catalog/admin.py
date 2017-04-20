from django.contrib import admin
from models import *

# Registering the models
admin.site.register(Keyword)
admin.site.register(License)
admin.site.register(Contributor)
admin.site.register(Contact)
admin.site.register(Link)
admin.site.register(BaseFile)