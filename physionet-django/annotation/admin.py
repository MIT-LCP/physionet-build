from django.contrib import admin
from .models import AnnotationCollection, Annotation, AnnotationType


@admin.register(AnnotationCollection)
class AnnotationCollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_datetime')
    list_filter = ('created_datetime',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_datetime', 'updated_datetime')


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ('id', 'collection', 'annotation_type', 'project', 'file_path', 'created_by', 'created_datetime')
    list_filter = ('annotation_type', 'created_datetime')
    search_fields = ('file_path', 'collection__name', 'labels')
    readonly_fields = ('created_datetime', 'updated_datetime')

@admin.register(AnnotationType)
class AnnotationTypeAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'allowed_location_kind', 'version', 'created_datetime')
    list_filter = ('allowed_location_kind', 'version', 'created_datetime')
    search_fields = ('slug', 'name', 'description')
    readonly_fields = ('created_datetime',)
