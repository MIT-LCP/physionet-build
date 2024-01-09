import logging
import os
import shutil

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from physionet.settings.base import StorageTypes
from project.modelcomponents.metadata import Metadata
from project.utility import StorageInfo
from project.validators import MAX_PROJECT_SLUG_LENGTH

LOGGER = logging.getLogger(__name__)


class UnpublishedProject(models.Model):
    """
    Abstract model inherited by ActiveProject
    """

    # Date and time that the project's content was modified.
    # See content_modified() and save().
    modified_datetime = models.DateTimeField(auto_now=True)

    # Whether this project is being worked on as a new version
    is_new_version = models.BooleanField(default=False)
    # Access url slug, also used as a submitting project id.
    slug = models.SlugField(max_length=MAX_PROJECT_SLUG_LENGTH, db_index=True)
    latest_reminder = models.DateTimeField(null=True, blank=True)
    doi = models.CharField(max_length=50, blank=True, null=True)
    authors = GenericRelation('project.Author')
    references = GenericRelation('project.Reference')
    publications = GenericRelation('project.Publication')
    topics = GenericRelation('project.Topic')
    archive_datetime = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    @property
    def is_legacy(self):
        return False

    def is_published(self):
        return False

    def file_root(self):
        """
        Root directory containing the project's files
        """
        return os.path.join(self.files.file_root,
                            self.FILE_STORAGE_SUBDIR,
                            self.slug)

    def bucket(self):
        """
        Object storage bucket name
        """
        return os.path.join(self.files.file_root,
                            self.FILE_STORAGE_SUBDIR)

    def get_storage_info(self, force_calculate=True):
        """
        Return an object containing information about the project's
        storage usage.

        If force_calculate is true, calculate the size by recursively
        scanning the directory tree.  This is deprecated.
        """
        if force_calculate:
            used = self.storage_used()
        else:
            used = None
        allowance = self.core_project.storage_allowance
        published = self.core_project.total_published_size
        return StorageInfo(allowance=allowance, published=published, used=used)

    def get_previous_slug(self):
        """
        If this is a new version of a project, get the slug of the
        published versions.
        """
        if self.is_new_version:
            return self.core_project.publishedprojects.all().get(
                version_order=0).slug
        else:
            raise Exception('Not a new version')


    def remove(self):
        """
        Delete this project's file content and the object
        """
        shutil.rmtree(self.file_root())
        return self.delete()

    def has_wfdb(self):
        """
        Whether the project has wfdb files.
        """
        return self.files.has_wfdb_files(self)

    def content_modified(self):
        """
        Update the project's modification timestamp.

        The modification timestamp (modified_datetime) is
        automatically updated when the object is saved, if any of the
        project's Metadata fields have been modified (see
        UnpublishedProject.save).

        This function should be called when saving or deleting
        objects, other than the UnpublishedProject itself, that are
        part of the project's visible content.
        """

        # Note: modified_datetime is an auto_now field, so it is
        # automatically set to the current time whenever it is saved.
        self.save(update_fields=['modified_datetime'])

    @classmethod
    def from_db(cls, *args, **kwargs):
        """
        Instantiate an object from the database.
        """
        instance = super(UnpublishedProject, cls).from_db(*args, **kwargs)

        # Save the original field values so that we can later check if
        # they have been modified.  Note that by using __dict__, this
        # will omit any deferred fields.
        instance.orig_fields = instance.__dict__.copy()
        return instance

    def save(self, *, content_modified=None,
             force_insert=False, update_fields=None, **kwargs):
        """
        Save this object to the database.

        In addition to the standard keyword arguments, this accepts an
        optional content_modified argument: if true, modified_datetime
        will be set to the current time; if false, neither
        modified_datetime nor the Metadata fields will be saved.

        If this object was loaded from the database, and none of the
        Metadata fields have been changed from their original values,
        then content_modified defaults to False.  Otherwise,
        content_modified defaults to True.
        """

        # Note: modified_datetime is an auto_now field, so it is
        # automatically set to the current time (unless we exclude it
        # using update_fields.)

        if force_insert or update_fields:
            # If force_insert is specified, then we want to insert a
            # new object, which means setting the timestamp.  If
            # update_fields is specified, then we want to update
            # precisely those fields.  In either case, use the default
            # save method.
            return super().save(force_insert=force_insert,
                                update_fields=update_fields,
                                **kwargs)

        # If content_modified is not specified, then detect
        # automatically.
        if content_modified is None:
            if hasattr(self, 'orig_fields'):
                # Check whether any of the Metadata fields have been
                # modified since the object was loaded from the database.
                for f in Metadata._meta.fields:
                    fname = f.attname
                    if fname not in self.orig_fields:
                        # If the field was initially deferred (and
                        # thus its original value is unknown), assume
                        # that it has been modified.  This is not
                        # ideal, but in general, it should be possible
                        # to avoid this by explicitly setting
                        # update_fields or content_modified whenever
                        # deferred fields are used.
                        LOGGER.warning(
                            'saving project with initially deferred fields')
                        content_modified = True
                        break
                    if self.orig_fields[fname] != getattr(self, fname):
                        content_modified = True
                        break
            else:
                # If the object was not initially created by from_db,
                # assume content has been modified.
                content_modified = True

        if content_modified:
            # If content has been modified, then save normally.
            return super().save(**kwargs)
        else:
            # If content has not been modified, then exclude all of the
            # Metadata fields as well as modified_datetime.
            fields = ({f.name for f in self._meta.fields}
                      - {f.name for f in Metadata._meta.fields}
                      - {'id', 'modified_datetime'})
            return super().save(update_fields=fields, **kwargs)
