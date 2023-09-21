import hashlib
import os
import shutil

from django.conf import settings
from physionet.utility import serve_file, sorted_tree_files, zip_dir
from project.projectfiles.base import BaseProjectFiles
from project.quota import DemoQuotaManager
from project.utility import (
    clear_directory,
    get_directory_info,
    get_file_info,
    get_tree_size,
    list_items,
    move_items,
    remove_items,
    rename_file,
    write_uploaded_file,
)


class LocalProjectFiles(BaseProjectFiles):
    @property
    def file_root(self):
        return settings.MEDIA_ROOT

    def mkdir(self, path):
        os.mkdir(path)

    def rm(self, path):
        remove_items([path], ignore_missing=False)

    def fwrite(self, path, content):
        with open(path, 'w') as outfile:
            outfile.write(content)

    def fput(self, path, file):
        write_uploaded_file(
            file=file,
            overwrite=False,
            write_file_path=os.path.join(path, file.name),
        )

    def rename(self, source_path, target_path):
        rename_file(source_path, target_path)

    def cp_file(self, source_path, target_path):
        shutil.copyfile(source_path, target_path)

    def mv(self, source_path, target_path):
        move_items([source_path], target_path)

    def open(self, path, mode='rb'):
        infile = open(path, mode)
        infile.size = os.stat(infile.fileno()).st_size

        return infile

    def get_project_directory_content(self, path, subdir, file_display_url, file_url):
        file_names, dir_names = list_items(path)
        display_files, display_dirs = [], []

        # Files require desciptive info and download links
        for file in file_names:
            file_info = get_file_info(os.path.join(path, file))
            file_info.url = file_display_url(subdir=subdir, file=file)
            file_info.raw_url = file_url(subdir=subdir, file=file)
            file_info.download_url = file_info.raw_url + '?download'
            display_files.append(file_info)

        # Directories require links
        for dir_name in dir_names:
            dir_info = get_directory_info(os.path.join(path, dir_name))
            dir_info.full_subdir = os.path.join(subdir, dir_name)
            display_dirs.append(dir_info)

        return display_files, display_dirs

    def cp_dir(self, source_path, target_path, ignored_files=None):
        os.mkdir(target_path)
        for (directory, subdirs, files) in os.walk(source_path):
            rel_dir = os.path.relpath(directory, source_path)
            destination = os.path.join(target_path, rel_dir)
            for d in subdirs:
                try:
                    os.mkdir(os.path.join(destination, d))
                except FileExistsError:
                    pass
            for f in files:
                # Skip linking files that are automatically generated
                # during publication.
                if directory == source_path and f in ignored_files:
                    continue
                try:
                    os.link(
                        os.path.join(directory, f),
                        os.path.join(destination, f),
                    )
                except FileExistsError:
                    pass

    def raw_url(self, project, path):
        return project.file_url('', path)

    def download_url(self, project, path):
        return self.raw_url(project, path) + '?download'

    def rm_dir(self, path, remove_zip):
        clear_directory(path)
        remove_zip()

    def rmtree(self, path):
        shutil.rmtree(path)

    def publish_initial(self, active_project, published_project):
        if not os.path.isdir(published_project.project_file_root()):
            os.mkdir(published_project.project_file_root())
        os.rename(active_project.file_root(), published_project.file_root())

    def publish_rollback(self, active_project, published_project):
        os.rename(published_project.file_root(), active_project.file_root())

    def publish_complete(self, active_project, published_project):
        pass

    def get_project_file_root(self, slug, version, access_policy, klass):
        if access_policy:
            return os.path.join(klass.PROTECTED_FILE_ROOT, slug)
        else:
            return os.path.join(klass.PUBLIC_FILE_ROOT, slug)

    def get_file_root(self, slug, version, access_policy, klass):
        return os.path.join(self.get_project_file_root(slug, version, access_policy, klass), version)

    def project_quota_manager(self, project):
        allowance = project.core_project.storage_allowance
        published = project.core_project.total_published_size
        limit = allowance - published

        # DemoQuotaManager needs to know the project's toplevel
        # directory as well as its creation time (so that files
        # present in multiple versions can be correctly attributed to
        # the version where they first appeared.)
        quota_manager = DemoQuotaManager(
            project_path=project.file_root(),
            creation_time=project.creation_datetime)
        quota_manager.set_limits(bytes_hard=limit, bytes_soft=limit)
        return quota_manager

    def published_project_storage_used(self, project):
        return get_tree_size(project.file_root())

    def get_zip_file_size(self, project):
        zip_name = project.zip_name(full=True)
        return os.path.getsize(zip_name) if os.path.isfile(zip_name) else 0

    def make_zip(self, project):
        fname = project.zip_name(full=True)
        if os.path.isfile(fname):
            os.remove(fname)

        zip_dir(
            zip_name=fname,
            target_dir=project.file_root(),
            enclosing_folder=project.slugged_label(),
        )

        project.compressed_storage_size = os.path.getsize(fname)
        project.save()

    def make_checksum_file(self, project):
        fname = os.path.join(project.file_root(), 'SHA256SUMS.txt')
        if os.path.isfile(fname):
            os.remove(fname)

        with open(fname, 'w') as outfile:
            for f in sorted_tree_files(project.file_root()):
                if f != 'SHA256SUMS.txt':
                    h = hashlib.sha256()
                    with open(os.path.join(project.file_root(), f), 'rb') as fp:
                        block = fp.read(h.block_size)
                        while block:
                            h.update(block)
                            block = fp.read(h.block_size)
                    outfile.write('{} {}\n'.format(h.hexdigest(), f))

        project.set_storage_info()

    def can_make_zip(self):
        return True

    def can_make_checksum(self):
        return True

    def is_lightwave_supported(self):
        return True

    def has_wfdb_files(self, project):
        return os.path.isfile(os.path.join(project.file_root(), 'RECORDS'))

    def is_wget_supported(self):
        return True

    def serve_file_field(self, field):
        return serve_file(field.path, attach=False)
