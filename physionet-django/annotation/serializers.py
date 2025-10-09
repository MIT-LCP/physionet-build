from rest_framework import serializers
import jsonschema
import json
from annotation.models import (
    Annotation,
    AnnotationCollection,
    AnnotationType,
    BaseLocation,
    TimeseriesIntervalLocation,
    ImageBBoxLocation,
    TextSpanLocation,
    AllowedLocationType,
)
from project.models import PublishedProject
from oauth2_provider.views.generic import (
    ProtectedResourceView,
    ScopedProtectedResourceView,
)
import uuid


class AnnotationCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnotationCollection
        fields = [
            "id",
            "slug",
            "name",
            "description",
            "created_by",
            "created_datetime",
            "updated_datetime",
        ]
        read_only_fields = ["created_by", "created_datetime", "updated_datetime"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class AnnotationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnotationType
        fields = [
            "id",
            "slug",
            "name",
            "description",
            "label_schema",
            "allowed_location_type",
            "version",
            "created_datetime",
        ]
        read_only_fields = ["created_datetime"]


class BaseLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaseLocation
        fields = "__all__"


class TimeseriesIntervalLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeseriesIntervalLocation
        fields = "__all__"


class ImageBBoxLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageBBoxLocation
        fields = "__all__"


class TextSpanLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TextSpanLocation
        fields = "__all__"


class AnnotationSerializer(serializers.ModelSerializer):
    annotation_type = serializers.SlugRelatedField(
        queryset=AnnotationType.objects.all(), slug_field="slug"
    )
    collection = serializers.SlugRelatedField(
        queryset=AnnotationCollection.objects.all(), slug_field="slug"
    )
    project = serializers.SlugRelatedField(
        queryset=PublishedProject.objects.all(), slug_field="slug"
    )
    location = serializers.JSONField(write_only=True)

    class Meta:
        model = Annotation
        fields = [
            "id",
            "collection",
            "annotation_type",
            "project",
            "file_path",
            "labels",
            "location",
            "created_by",
            "created_datetime",
            "updated_datetime",
        ]
        read_only_fields = ["created_by", "created_datetime", "updated_datetime"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.location:
            if instance.location.location_type == "text_span":  # TextSpanLocation
                data["location"] = TextSpanLocationSerializer(instance.location).data
            elif instance.location.location_type == "timeseries_interval":
                data["location"] = TimeseriesIntervalLocationSerializer(
                    instance.location
                ).data
            elif instance.location.location_type == "image_bbox":  # ImageBBoxLocation
                data["location"] = ImageBBoxLocationSerializer(instance.location).data
            else:
                raise serializers.ValidationError(
                    f"Unknown location_type: {instance.location.location_type}"
                )
        return data

    def create(self, validated_data):
        request = self.context.get("request")
        if "location" in validated_data:
            location_data = validated_data.pop("location")
            if "id" not in location_data:
                location_data["id"] = uuid.uuid4()
                if request.user and request.user.is_authenticated:
                    location_data["created_by"] = request.user
            location_obj = None
            if (
                location_data["location_type"]
                == AllowedLocationType.TIMESERIES_INTERVAL.value
            ):
                location_obj = TimeseriesIntervalLocation.objects.create(
                    **location_data
                )
            elif location_data["location_type"] == AllowedLocationType.IMAGE_BBOX.value:
                location_obj = ImageBBoxLocation.objects.create(**location_data)
            elif location_data["location_type"] == AllowedLocationType.TEXT_SPAN.value:
                location_obj = TextSpanLocation.objects.create(**location_data)
            validated_data["location"] = location_obj
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)

    def validate(self, data):
        annotation_type = self.initial_data.get("annotation_type")
        labels = self.initial_data.get("labels")
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
        # validate location type
        location_data = self.initial_data.get("location", {})
        if (
            location_data.get("location_type")
            != annotation_type_obj.allowed_location_type
        ):
            raise serializers.ValidationError(
                f"Location type must be '{annotation_type_obj.allowed_location_type} \
                    for annotation type '{annotation_type}' but got \
                        '{location_data.get('location_type')}'"
            )
        return data
