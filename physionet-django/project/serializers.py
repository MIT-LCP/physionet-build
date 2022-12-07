# from user.models import User
from rest_framework import serializers

from project.models import PublishedProject, License, DUA

# adding License & Dua for details


class LicenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = License
        fields = ('name', 'is_active')


class DUASerializer(serializers.ModelSerializer):
    class Meta:
        model = DUA
        fields = ('name', 'is_active')


class PublishedProjectSerializer(serializers.ModelSerializer):
    license = LicenseSerializer()
    dua = DUASerializer()

    class Meta:
        model = PublishedProject
        fields = ('id', 'title', 'abstract', 'license', 'dua')


class PublishedProjectDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublishedProject
        fields = ("title", "abstract", "background", "methods", "content_description", "usage_notes", "installation",
                  "acknowledgements", "conflicts_of_interest", "release_notes", "ethics_statement", "version",
                  "short_description", "project_home_page", "publish_datetime", "doi", "slug")
