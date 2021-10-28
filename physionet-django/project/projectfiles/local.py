import hashlib
import os
import shutil

from django.conf import settings

from physionet.utility import zip_dir, sorted_tree_files
from project.projectfiles.base import BaseProjectFiles
from project.utility import remove_items, write_uploaded_file, rename_file, move_items, list_items, get_file_info, \
    get_directory_info, clear_directory, get_tree_size


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
                if (directory == source_path and f in ignored_files):
                    continue
                try:
                    os.link(os.path.join(directory, f),
                            os.path.join(destination, f))
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

    def publish(self, active_project, published_project):
        if not os.path.isdir(published_project.project_file_root()):
            os.mkdir(published_project.project_file_root())
        os.rename(active_project.file_root(), published_project.file_root())

    def get_project_file_root(self, slug, access_policy, klass):
        if access_policy:
            return os.path.join(klass.PROTECTED_FILE_ROOT, slug)
        else:
            return os.path.join(klass.PUBLIC_FILE_ROOT, slug)

    def storage_used(self, path, zip_name):
        main = get_tree_size(path)
        compressed = os.path.getsize(zip_name) if os.path.isfile(zip_name) else 0
        return main, compressed

    def make_zip(self, project):
        fname = project.zip_name(full=True)
        if os.path.isfile(fname):
            os.remove(fname)

        zip_dir(zip_name=fname, target_dir=project.file_root(), enclosing_folder=project.slugged_label())

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
