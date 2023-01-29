
from rest_framework import serializers

from project.models import PublishedProject, License, DUA


class LicenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = License
        fields = ('name',)


class DUASerializer(serializers.ModelSerializer):
    class Meta:
        model = DUA
        fields = ('name',)


class PublishedProjectSerializer(serializers.ModelSerializer):
    license = LicenseSerializer()
    dua = DUASerializer()

    class Meta:
        model = PublishedProject
        fields = ('slug', 'title', 'abstract', 'license', 'dua', 'main_storage_size',
                  'compressed_storage_size')


class ProjectVersionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublishedProject
        fields = ('slug', 'title', 'version', 'abstract')


class PublishedProjectDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublishedProject
        fields = ("title", "abstract", "version", "short_description",
                  "project_home_page", "publish_datetime", "doi", "slug", "main_storage_size",
                  "compressed_storage_size")
