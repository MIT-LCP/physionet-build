from django.contrib import admin
from .models import *

# Registering the models
admin.site.register(Database)
admin.site.register(DataType)
admin.site.register(ClinicalType)

admin.site.register(SignalClass)
admin.site.register(AnnotationClass)
admin.site.register(AnnotationLabel)

admin.site.register(Record)
admin.site.register(Signal)
admin.site.register(Annotation)
