from schema import Query
from django.test.testcases import TestCase
import graphene
import pdb


class AnExampleTest(TestCase):

    def test_all_published_projects(self):
        schema = graphene.Schema(query=Query, auto_camelcase=False)
        query = """
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
        result = schema.execute(query)
        self.assertIsNone(result.errors)

    def test_all_published_authors(self):
        schema = graphene.Schema(query=Query, auto_camelcase=False)
        query = """
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
        result = schema.execute(query)
        self.assertIsNone(result.errors)

    def test_all_published_references(self):
        schema = graphene.Schema(query=Query, auto_camelcase=False)
        query = """
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
        result = schema.execute(query)
        self.assertIsNone(result.errors)
