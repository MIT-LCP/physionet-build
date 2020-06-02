import graphene
from graphene_django.types import DjangoObjectType

from project.models import PublishedProject


class PublishedProjectType(DjangoObjectType):
    class Meta:
        model = PublishedProject
        fields = ('title', 'version', 'slug', 'abstract', 'main_storage_size',
                  'compressed_storage_size')


class Query(object):
    all_published_projects = graphene.List(PublishedProjectType)

    def resolve_all_published_projects(self, info, **kwargs):
        return PublishedProject.objects.all()
