from django.contrib import admin
from .models import *

# Registering the models
admin.site.register(Database)
admin.site.register(DataType)
admin.site.register(WFDB_Signal_Type)
admin.site.register(ClinicalType)
admin.site.register(WFDB_Signal_Info)
admin.site.register(WFDB_Record_Info)