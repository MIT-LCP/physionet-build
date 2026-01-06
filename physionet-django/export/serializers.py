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


class ProjectFieldsMixin:
    """
    Mixin providing serialization for resource_type, access_policy, and topics.

    This mixin provides methods to serialize these fields as human-readable
    strings instead of internal integer codes, making the API more extensible
    and future-proof.
    """

    def get_resource_type(self, obj):
        """
        Return resource type as string name (e.g., 'Database', 'Software').

        Args:
            obj: PublishedProject instance

        Returns:
            str or None: Resource type name or None if not set
        """
        return obj.resource_type.name if obj.resource_type else None

    def get_access_policy(self, obj):
        """
        Return access policy as string name (e.g., 'Open', 'Credentialed').

        Args:
            obj: PublishedProject instance

        Returns:
            str or None: Access policy name or None if not set
        """
        from project.models import AccessPolicy
        if obj.access_policy is None:
            return None
        try:
            return AccessPolicy(obj.access_policy).name.replace("_", " ").title()
        except ValueError:
            # Handle unexpected/invalid access policy values gracefully
            return None

    def get_topics(self, obj):
        """
        Return list of topic descriptions.

        Args:
            obj: PublishedProject instance

        Returns:
            list: List of topic description strings
        """
        return [topic.description for topic in obj.topics.all()]

    def get_source_url(self, obj):
        """Generate the full URL to this project's page."""
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(
                reverse('published_project', args=[obj.slug, obj.version])
            )
        return None


class PublishedProjectSerializer(ProjectFieldsMixin, serializers.ModelSerializer):
    license = LicenseSerializer()
    dua = DUASerializer()
    publish_date = serializers.SerializerMethodField()
    core_doi = serializers.SerializerMethodField()
    version_doi = serializers.SerializerMethodField()
    resource_type = serializers.SerializerMethodField()
    access_policy = serializers.SerializerMethodField()
    topics = serializers.SerializerMethodField()
    source_url = serializers.SerializerMethodField()

    class Meta:
        model = PublishedProject
        fields = (
            'public_project_uuid',
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
            'source_url',
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


class PublishedProjectDetailSerializer(ProjectFieldsMixin, serializers.ModelSerializer):
    license = LicenseSerializer()
    resource_type = serializers.SerializerMethodField()
    access_policy = serializers.SerializerMethodField()
    topics = serializers.SerializerMethodField()
    source_url = serializers.SerializerMethodField()

    class Meta:
        model = PublishedProject
        fields = (
            'public_project_uuid',
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
