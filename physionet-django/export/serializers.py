from rest_framework import serializers

from project.models import PublishedProject


class PublishedProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublishedProject
        fields = ('title', 'version', 'slug', 'abstract', 'main_storage_size',
            'compressed_storage_size')
