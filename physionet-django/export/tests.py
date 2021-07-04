from schema import Query
from django.test.testcases import TestCase
import graphene
import json

from project.models import (PublishedProject, PublishedAuthor,
                            PublishedReference)


class TestGraphQL(TestCase):

    def test_all_published_projects(self):
        schema = graphene.Schema(query=Query, auto_camelcase=False)
        query_correct = """
            query {
                all_published_projects {
                    title
                    version
                    slug
                    abstract
                    main_storage_size
                    compressed_storage_size
                }
            }
        """
        query_incorrect = """
            query {
                all_published_projects {
                    title
                    version
                    slug
                    abstract
                    main_storage_size
                    compressed_storage_size
                    author_comments
                }
            }
        """
        correct_output = []
        for p in PublishedProject.objects.all():
            correct_output.append({
                'title': p.title,
                'version': p.version,
                'slug': p.slug,
                'abstract': p.abstract,
                'main_storage_size': p.main_storage_size,
                'compressed_storage_size': p.compressed_storage_size,
            })
        result_correct = schema.execute(query_correct)
        self.assertIsNone(result_correct.errors)
        result_incorrect = schema.execute(query_incorrect)
        self.assertIsNotNone(result_incorrect.errors)
        result_correct = json.loads(json.dumps(result_correct.to_dict()))['data']['all_published_projects']
        matches = [i for i in result_correct if i not in correct_output]
        self.assertEqual(matches, [])

    def test_all_published_authors(self):
        schema = graphene.Schema(query=Query, auto_camelcase=False)
        query_correct = """
            query {
                all_published_authors {
                    first_names
                    last_name
                    corresponding_email
                    project {
                        title
                        version
                        slug
                        abstract
                        main_storage_size
                        compressed_storage_size
                    }
                }
            }
        """
        query_incorrect = """
            query {
                all_published_authors {
                    first_names
                    last_name
                    corresponding_email
                    project {
                        title
                        version
                        slug
                        abstract
                        main_storage_size
                        compressed_storage_size
                        author_comments
                    }
                }
            }
        """
        correct_output = []
        for p in PublishedAuthor.objects.all():
            correct_output.append({
                'first_names': p.first_names,
                'last_name': p.last_name,
                'corresponding_email': p.corresponding_email,
                'project': {
                        'title': p.project.title,
                        'version': p.project.version,
                        'slug': p.project.slug,
                        'abstract': p.project.abstract,
                        'main_storage_size': p.project.main_storage_size,
                        'compressed_storage_size': p.project.compressed_storage_size,
                    }
            })
        result_correct = schema.execute(query_correct)
        self.assertIsNone(result_correct.errors)
        result_incorrect = schema.execute(query_incorrect)
        self.assertIsNotNone(result_incorrect.errors)
        result_correct = json.loads(json.dumps(result_correct.to_dict()))['data']['all_published_authors']
        matches = [i for i in result_correct if i not in correct_output]
        self.assertEqual(matches, [])

    def test_all_published_references(self):
        schema = graphene.Schema(query=Query, auto_camelcase=False)
        query_correct = """
            query {
                all_published_references {
                    id
                    description
                    project {
                        title
                        version
                        slug
                        abstract
                        main_storage_size
                        compressed_storage_size
                    }
                }
            }
        """
        query_incorrect = """
            query {
                all_published_references {
                    id
                    description
                    project {
                        title
                        version
                        slug
                        abstract
                        main_storage_size
                        compressed_storage_size
                        author_comments
                    }
                }
            }
        """
        correct_output = []
        for p in PublishedReference.objects.all():
            correct_output.append({
                'id': str(p.id),
                'description': p.description,
                'project': {
                        'title': p.project.title,
                        'version': p.project.version,
                        'slug': p.project.slug,
                        'abstract': p.project.abstract,
                        'main_storage_size': p.project.main_storage_size,
                        'compressed_storage_size': p.project.compressed_storage_size,
                    }
            })
        result_correct = schema.execute(query_correct)
        self.assertIsNone(result_correct.errors)
        result_incorrect = schema.execute(query_incorrect)
        self.assertIsNotNone(result_incorrect.errors)
        result_correct = json.loads(json.dumps(result_correct.to_dict()))['data']['all_published_references']
        matches = [i for i in result_correct if i not in correct_output]
        self.assertEqual(matches, [])
