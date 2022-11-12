# from user.models import User
from rest_framework import serializers

from project.models import PublishedProject


class PublishedProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublishedProject
        fields = ('id', 'title', 'abstract')


class PublishedProjectDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublishedProject
        fields = ("title", "abstract", "background", "methods", "content_description", "usage_notes", "installation", "acknowledgements", "conflicts_of_interest", "release_notes", "ethics_statement", "version",  "short_description", "project_home_page", "publish_datetime", "doi", "slug")
