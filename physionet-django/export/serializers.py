
from rest_framework import serializers

from project.models import PublishedProject, License, DUA


class LicenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = License
        fields = (
            'name',
        )


class DUASerializer(serializers.ModelSerializer):
    class Meta:
        model = DUA
        fields = (
            'name',
        )


class PublishedProjectSerializer(serializers.ModelSerializer):
    license = LicenseSerializer()
    dua = DUASerializer()
    publish_date = serializers.SerializerMethodField()
    core_doi = serializers.SerializerMethodField()
    version_doi = serializers.SerializerMethodField()

    class Meta:
        model = PublishedProject
        fields = (
            'slug',
            'version',
            'core_doi',
            'version_doi',
            'is_latest_version',
            'short_description',
            'publish_date',
            'title',
            'abstract',
            'license',
            'dua',
            'main_storage_size',
            'compressed_storage_size',
        )

    def get_publish_date(self, obj):
        return obj.publish_datetime.date() if obj.publish_datetime else None

    def get_core_doi(self, obj):
        return obj.core_project.doi if hasattr(obj, 'core_project') else None

    def get_version_doi(self, obj):
        return obj.doi


class ProjectVersionsSerializer(serializers.ModelSerializer):
    citation = serializers.SerializerMethodField()

    class Meta:
        model = PublishedProject
        fields = (
            'slug',
            'title',
            'version',
            'abstract',
            'citation',
        )

    def get_citation(self, obj):
        return obj.citation_text(style="Vancouver")


class PublishedProjectDetailSerializer(serializers.ModelSerializer):
    license = LicenseSerializer()

    class Meta:
        model = PublishedProject
        fields = (
            'slug',
            'title',
            'version',
            'abstract',
            'license',
            'short_description',
            'project_home_page',
            'publish_datetime',
            'doi',
            'main_storage_size',
            'compressed_storage_size',
        )
