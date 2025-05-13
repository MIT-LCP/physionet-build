from enum import IntEnum
import logging
import os
import sys

from django.db import migrations
from django.conf import settings

LOGGER = logging.getLogger(__name__)

STATIC_ROOT = settings.STATIC_ROOT or settings.STATICFILES_DIRS[0]
OLD_PROJECTS_DIR = os.path.join(STATIC_ROOT, 'published-projects')
NEW_PROJECTS_DIR = os.path.join(settings.MEDIA_ROOT, 'published-projects')


class AccessPolicy(IntEnum):
    OPEN = 0
    RESTRICTED = 1
    CREDENTIALED = 2
    CONTRIBUTOR_REVIEW = 3


def exchange_paths(path1, path2):
    """
    Swap two filenames, atomically.

    The two filenames must be located under the same mount point (and
    that filesystem must support RENAME_EXCHANGE.)

    If running in debug mode on an unsupported operating system, the
    operation will be emulated in an unsafe way.  If running in
    production mode on an unsupported operating system, raise an
    exception.
    """
    if sys.platform.startswith('linux'):
        import renameat2
        renameat2.exchange(path1, path2)
    elif settings.DEBUG:
        import secrets
        path1 = os.path.normpath(path1)
        path2 = os.path.normpath(path2)
        path_tmp = '{}.{}'.format(path2, secrets.token_hex())
        os.rename(path1, path_tmp)
        try:
            os.rename(path2, path1)
        except BaseException:
            os.rename(path_tmp, path1)
            raise
        os.rename(path_tmp, path2)
    else:
        raise NotImplementedError(
            "Unsupported plaform: {}".format(sys.platform)
        )


def move_project_files(*, slug, version, old_parent_dir, new_parent_dir):
    old_project_dir = os.path.abspath(os.path.join(old_parent_dir, slug))
    new_project_dir = os.path.abspath(os.path.join(new_parent_dir, slug))

    if not os.path.isdir(old_project_dir):
        return

    if not os.path.isdir(new_project_dir):
        LOGGER.info("mkdir(%r)", new_project_dir)
        os.mkdir(new_project_dir, mode=os.stat(old_project_dir).st_mode)

    files_to_rename = []
    zip_suffix = "-{}.zip".format(version)
    for entry in os.scandir(old_project_dir):
        old_path = os.path.join(old_project_dir, entry.name)
        new_path = os.path.join(new_project_dir, entry.name)
        if entry.name == version or entry.name.endswith(zip_suffix):
            if entry.is_symlink():
                LOGGER.info("Skipping %s (already a symlink)", old_path)
            else:
                if os.path.exists(new_path):
                    raise Exception(
                        "Cannot move {}; {} already exists"
                        .format(old_path, new_path)
                    )
                files_to_rename.append((old_path, new_path))

    for old_path, new_path in files_to_rename:
        # new_path does not currently exist.  Create a link at
        # new_path pointing to itself.
        LOGGER.info("symlink(%r, %r)", new_path, new_path)
        os.symlink(new_path, new_path)

        # Move the file currently at old_path to new_path, while
        # moving the link at new_path (which points to new_path)
        # to old_path.
        LOGGER.info("exchange(%r, %r)", new_path, old_path)
        exchange_paths(new_path, old_path)


def migrate_forward(apps, schema_editor):
    PublishedProject = apps.get_model("project", "PublishedProject")
    projects = PublishedProject.objects.filter(access_policy=AccessPolicy.OPEN)
    for project in projects:
        move_project_files(
            slug=project.slug,
            version=project.version,
            old_parent_dir=OLD_PROJECTS_DIR,
            new_parent_dir=NEW_PROJECTS_DIR,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("project", "0083_alter_awsaccesspoint_name"),
    ]

    operations = [
        migrations.RunPython(
            migrate_forward,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
