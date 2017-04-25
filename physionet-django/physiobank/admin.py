from django.contrib import admin
from .models import *

# Registering the models
admin.site.register(Database)
admin.site.register(DataType)
admin.site.register(SignalType)
admin.site.register(ClinicalType)
admin.site.register(Signal)
