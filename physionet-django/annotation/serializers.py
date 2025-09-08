from rest_framework import serializers

from annotation.models import Annotation, AnnotationCollection, AnnotationType


class AnnotationSerializer(serializers.ModelSerializer):
    annotation_type_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Annotation
        fields = [
            'id',
            'collection',
            'annotation_type',
            'data',
            'modality',
            'label_text',
            'created_by',
            'created_datetime',
            'updated_datetime',
        ]
        read_only_fields = ['collection', 'modality', 'label_text', 'created_by', 'created_datetime', 'updated_datetime']

    def validate(self, attrs):
        if not attrs.get('annotation_type') and not attrs.get('annotation_type_name'):
            raise serializers.ValidationError({'annotation_type': 'Provide annotation_type (id) or annotation_type_name.'})
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        
        name = validated_data.pop('annotation_type_name', None)
        if name and not validated_data.get('annotation_type'):
            modality = None
            data = validated_data.get('data') or {}
            if isinstance(data, dict):
                modality = data.get('modality')
            annotation_type, _ = AnnotationType.objects.get_or_create(
                name=name,
                defaults={'modality': modality or 'label', 'is_active': True},
            )
            validated_data['annotation_type'] = annotation_type

        return super().create(validated_data)


class AnnotationCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnotationCollection
        fields = [
            'id',
            'name',
            'description',
            'project',
            'version',
            'is_active',
            'metadata',
            'created_by',
            'created_datetime',
            'updated_datetime',
        ]
        read_only_fields = ['created_by', 'created_datetime', 'updated_datetime']