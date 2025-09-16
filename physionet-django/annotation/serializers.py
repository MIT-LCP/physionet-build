from rest_framework import serializers
import jsonschema
from annotation.models import (
    Annotation, AnnotationCollection, AnnotationType,
    # TimeseriesIntervalLocation, ImageBBoxLocation, TextSpanLocation
)
from project.models import PublishedProject


class AnnotationCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnotationCollection
        fields = [
            'id',
            'name', 
            'description',
            'created_by',
            'created_datetime',
            'updated_datetime',
        ]
        read_only_fields = ['created_by', 'created_datetime', 'updated_datetime']
    
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)

class AnnotationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnotationType
        fields = [
            'id',
            'slug',
            'name',
            'description',
            'label_schema',
            'allowed_location_kind',
            'version',
            'created_datetime',
        ]
        read_only_fields = ['created_datetime']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class AnnotationSerializer(serializers.ModelSerializer):
    annotation_type = serializers.SlugRelatedField(
        queryset=AnnotationType.objects.all(), slug_field='slug'
    )
    collection = serializers.SlugRelatedField(
        queryset=AnnotationCollection.objects.all(), slug_field='slug'
    )
    project = serializers.SlugRelatedField(
        queryset=PublishedProject.objects.all(), slug_field='slug'
    )

    class Meta:
        model = Annotation
        fields = [
            'id',
            'collection',
            'annotation_type', 
            'project',
            'file_path',
            'labels',
            'created_by',
            'created_datetime',
            'updated_datetime',
        ]
        read_only_fields = ['created_by', 'created_datetime', 'updated_datetime']
    
    def create(self, validated_data):
        # Map the slug fields to the actual model fields
        if 'collection' in validated_data:
            validated_data['collection'] = validated_data.pop('collection')
        if 'annotation_type' in validated_data:
            validated_data['annotation_type'] = validated_data.pop('annotation_type')
        if 'project' in validated_data:
            validated_data['project'] = validated_data.pop('project')
            
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)
    
    def validate(self, data):
        annotation_type = self.initial_data.get('annotation_type')
        labels = self.initial_data.get('labels')
        try:
            annotation_type_obj = AnnotationType.objects.get(slug=annotation_type)
        except AnnotationType.DoesNotExist:
            raise serializers.ValidationError("Annotation type does not exist")
        if annotation_type:
            schema = annotation_type_obj.label_schema
            try:
                jsonschema.validate(labels, schema)
            except jsonschema.exceptions.ValidationError as e:
                raise serializers.ValidationError(e.message) from e
        return data

