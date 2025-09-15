from rest_framework import serializers

from annotation.models import (
    Annotation, AnnotationCollection, AnnotationType,
    # TimeseriesIntervalLocation, ImageBBoxLocation, TextSpanLocation
)


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


# class TimeseriesIntervalLocationSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = TimeseriesIntervalLocation
#         fields = [
#             'coord_system',
#             'channel',
#             'start',
#             'end',
#             'created_datetime',
#         ]
#         read_only_fields = ['created_datetime']


# class ImageBBoxLocationSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = ImageBBoxLocation
#         fields = [
#             'coord_system',
#             'x',
#             'y',
#             'width',
#             'height',
#             'created_datetime',
#         ]
#         read_only_fields = ['created_datetime']


# class TextSpanLocationSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = TextSpanLocation
#         fields = [
#             'coord_system',
#             'begin',
#             'end',
#             'encoding',
#             'created_datetime',
#         ]
#         read_only_fields = ['created_datetime']


class AnnotationSerializer(serializers.ModelSerializer):
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
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)

