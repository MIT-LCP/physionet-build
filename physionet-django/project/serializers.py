from rest_framework import serializers

from .models import PublishedProject


class PublishedProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublishedProject
        fields = ('slug', 'title', 'abstract')
