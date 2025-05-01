import functools

from django.db import models

from project.modelcomponents.metadata import Metadata


class ProjectType(models.Model):
    """
    The project types available on the platform
    """
    id = models.PositiveSmallIntegerField(primary_key=True)
    name = models.CharField(max_length=20)
    description = models.TextField()

    class Meta:
        default_permissions = ()

    def __str__(self):
        return self.name

    def content_section_headers(self):
        """
        Return a list of ContentSectionHeaders that form the outline.

        Each ContentSectionHeader represents a free-text field that
        may be edited by the project author.
        """
        return _PROJECT_TYPE_CONTENT_SECTIONS[self.id]


class ContentSectionHeader:
    """
    Metadata for a free-form HTML content section.

    A project description contains many sections (such as "Abstract",
    "Background", and "Methods"), which follow a particular structure
    that is defined for each project type.

    A ContentSectionHeader object defines the fixed metadata for the
    section, which applies to all projects of the given type.  It has
    the following attributes:

    - title: the human-readable title of the section

    - html_id: the ID that may be used to link to the section

    - required: True if the section is required (the project should
      not be published if this section is missing)

    - field_name: the name of the corresponding field in Metadata

    In the present implementation, every ContentSectionHeader
    corresponds to a particular field that is defined in the
    ActiveProject and PublishedProject classes (specifically, one of
    the fields defined in the Metadata class.)  In the future, this
    structure may become dynamic and site-configurable.
    """
    def __init__(self, *, title, html_id, required=True, field_name=None):
        self.title = title
        self.html_id = html_id
        self.required = required
        if field_name is None:
            field_name = html_id.replace('-', '_')
        self.field_name = field_name

        # field_name must be a field defined in the Metadata class
        Metadata._meta.get_field(field_name)

    def __repr__(self):
        return '<{}: {!r}>'.format(type(self).__name__, self.title)

    @classmethod
    def _factory(cls, **kwargs):
        return functools.partial(cls, **kwargs)


_abstract = ContentSectionHeader._factory(
    title='Abstract',
    html_id='abstract',
)
_background = ContentSectionHeader._factory(
    title='Background',
    html_id='background',
)
_methods = ContentSectionHeader._factory(
    title='Methods',
    html_id='methods',
)
_participation = ContentSectionHeader._factory(
    title='Participation',
    html_id='participation',
    field_name='methods',
)
_data_description = ContentSectionHeader._factory(
    title='Data Description',
    html_id='description',
    field_name='content_description',
)
_software_description = ContentSectionHeader._factory(
    title='Software Description',
    html_id='description',
    field_name='content_description',
)
_model_description = ContentSectionHeader._factory(
    title='Model Description',
    html_id='description',
    field_name='content_description',
)
_implementation = ContentSectionHeader._factory(
    title='Technical Implementation',
    html_id='implementation',
    field_name='methods',
)
_installation = ContentSectionHeader._factory(
    title='Installation and Requirements',
    html_id='installation',
)
_evaluation = ContentSectionHeader._factory(
    title='Evaluation',
    html_id='evaluation',
    field_name='usage_notes',
)
_usage_notes = ContentSectionHeader._factory(
    title='Usage Notes',
    html_id='usage-notes',
)
_release_notes = ContentSectionHeader._factory(
    title='Release Notes',
    html_id='release-notes',
)
_ethics = ContentSectionHeader._factory(
    title='Ethics',
    html_id='ethics',
    field_name='ethics_statement',
)
_acknowledgements = ContentSectionHeader._factory(
    title='Acknowledgements',
    html_id='acknowledgements',
)
_conflicts_of_interest = ContentSectionHeader._factory(
    title='Conflicts of Interest',
    html_id='conflicts-of-interest',
)

# Order of content sections for each resource type.
_PROJECT_TYPE_CONTENT_SECTIONS = {
    # Type 0: Database
    0: (
        _abstract(),
        _background(),
        _methods(),
        _data_description(),
        _usage_notes(),
        _release_notes(required=False),
        _ethics(),
        _acknowledgements(required=False),
        _conflicts_of_interest(),
    ),
    # Type 1: Software
    1: (
        _abstract(),
        _background(),
        _software_description(),
        _implementation(required=False),
        _installation(),
        _usage_notes(),
        _release_notes(required=False),
        _ethics(),
        _acknowledgements(required=False),
        _conflicts_of_interest(),
    ),
    # Type 2: Challenge
    2: (
        _abstract(),
        _background(),
        _participation(),
        _data_description(),
        _evaluation(),
        _release_notes(required=False),
        _ethics(),
        _acknowledgements(required=False),
        _conflicts_of_interest(),
    ),
    # Type 3: Model
    3: (
        _abstract(),
        _background(),
        _model_description(),
        _implementation(),
        _installation(),
        _usage_notes(),
        _release_notes(required=False),
        _ethics(),
        _acknowledgements(required=False),
        _conflicts_of_interest(),
    ),
}
