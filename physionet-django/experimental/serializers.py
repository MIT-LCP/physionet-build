from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404

from experimental.models import (
    Annotation, AnnotationCollection, AnnotationData, DocumentAnnotationData
)


class AnnotationCollectionSerializer(serializers.ModelSerializer):
    version = serializers.CharField(required=False, allow_blank=True)
    annotations = AnnotationSerializer(many=True)
    class Meta:
        model = AnnotationCollection
        fields = [
            'id',
            'name', 
            'project',
            'version',
            'description',
            'created_by',
            'created_datetime',
            'updated_datetime',
        ]
        read_only_fields = ['created_by', 'created_datetime', 'updated_datetime']
    
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user:
            validated_data['created_by'] = request.user
        return super().create(validated_data)



class AnnotationDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnotationData
        fields = '__all__'
    
    # def create(self, validated_data):
    #     request = self.context.get('request')
    #     if request and request.user:
    #         validated_data['created_by'] = request.user
    #     return super().create(validated_data)
    
    # def validate_annotation_data(self, value):
    #     """
    #     Validate annotation_data field using the custom validator.
    #     """
    #     if value is None:
    #         raise serializers.ValidationError("annotation_data is required")
        
    #     # Get target_modality from the validated data or initial data
    #     target_modality = self.initial_data.get('target_modality')
    #     target_text = self.initial_data.get('target_text')
        
    #     if not target_modality:
    #         raise serializers.ValidationError("target_modality must be specified to validate annotation_data")
        
    #     try:
    #         if target_modality == "document":
    #             _validate_document_annotation(data, target_text)
    #         elif target_modality == "image":
    #             _validate_image_annotation(data)
    #     except DjangoValidationError as e:
    #         raise serializers.ValidationError(str(e))
        
    #     return value

class AnnotationSerializer(serializers.ModelSerializer):
    # Allow passing target_text as a field for document annotations
    target_text = serializers.CharField(required=False, allow_blank=True)
    annotation_data = AnnotationDataSerializer(many=True)

    class Meta:
        model = Annotation
        fields = [
            'id',
            'collection',
            'target_project',
            'target_project_version',
            'target_filepath',
            'target_modality',
            'annotation_data',
            'annotation_description',
            'created_by',
            'created_datetime', 
            'updated_datetime',
        ]
        read_only_fields = ['created_by', 'created_datetime', 'updated_datetime']
    

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user:
            validated_data['created_by'] = request.user.id
        else:
            raise serializers.ValidationError("User not authenticated")
        
        ## Create the annotation
        annotation_data = validated_data.pop("annotation_data") #Extracting annotation data from validated data
        if validated_data['target_modality'] == 'document':
            annotation = Annotation.objects.create(**validated_data)
            
            return annotation
