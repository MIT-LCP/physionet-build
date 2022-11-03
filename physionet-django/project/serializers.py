# from user.models import User
from rest_framework import serializers

from .models import PublishedProject

class PublishedProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublishedProject
        fields = ('id', 'title', 'abstract')

class PublishedProjectDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublishedProject
        fields = '__all__'
    