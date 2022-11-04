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
        fields = '__all__'
