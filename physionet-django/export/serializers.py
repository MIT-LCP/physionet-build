from django.conf import settings
from django.urls import reverse

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
    topics = serializers.SerializerMethodField()
    resource_type = serializers.IntegerField(source='resource_type.id')
    access_policy = serializers.IntegerField()

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
            'resource_type',
            'access_policy',
            'topics',
        )

    def get_publish_date(self, obj):
        return obj.publish_datetime.date() if obj.publish_datetime else None

    def get_core_doi(self, obj):
        return obj.core_project.doi if hasattr(obj, 'core_project') else None

    def get_version_doi(self, obj):
        return obj.doi

    def get_topics(self, obj):
        """Get list of topic descriptions."""
        return [topic.description for topic in obj.topics.all()]


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
    source_url = serializers.SerializerMethodField()
    topics = serializers.SerializerMethodField()
    resource_type = serializers.IntegerField(source='resource_type.id')
    access_policy = serializers.IntegerField()

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
            'resource_type',
            'access_policy',
            'topics',
            'source_url',
        )

    def get_source_url(self, obj):
        """Generate the full URL to this project's page."""
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(
                reverse('published_project', args=[obj.slug, obj.version])
            )
        else:
            # Fallback to settings-based URL
            site_url = getattr(settings, 'SITE_URL', 'https://physionet.org')
            path = reverse('published_project', args=[obj.slug, obj.version])
            return f"{site_url.rstrip('/')}{path}"

    def get_topics(self, obj):
        """Get list of topic descriptions."""
        return [topic.description for topic in obj.topics.all()]
