import abc


class BaseProjectFiles(abc.ABC):
    """Base class that defines project file operations."""

    @abc.abstractproperty
    def file_root(self):
        """Default file root"""
        raise NotImplementedError

    @abc.abstractmethod
    def mkdir(self, path):
        """Make a directory."""
        raise NotImplementedError

    @abc.abstractmethod
    def rm(self, path):
        """Remove a file/directory."""
        raise NotImplementedError

    @abc.abstractmethod
    def fwrite(self, path, content):
        """Write the content of the string at a given path."""
        raise NotImplementedError

    @abc.abstractmethod
    def fput(self, path, file):
        """Put a file at a given path."""
        raise NotImplementedError

    @abc.abstractmethod
    def rename(self, source_path, target_path):
        """Change the name of a file/directory."""
        raise NotImplementedError

    @abc.abstractmethod
    def mv(self, source_path, target_path):
        """Move files."""
        raise NotImplementedError

    @abc.abstractmethod
    def open(self, path, mode='rb'):
        """Open files and dictionaries."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_project_directory_content(self, path, subdir, file_display_url, file_url):
        """
        Return information for displaying files and directories from
        the project's file root.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def cp_dir(self, source_path, target_path, ignored_files=None):
        """Copy directories."""
        raise NotImplementedError

    @abc.abstractmethod
    def raw_url(self, project, path):
        """Return a URL that can be used to view the file."""
        raise NotImplementedError

    @abc.abstractmethod
    def download_url(self, project, path):
        """Return a URL that can be used to download the file."""
        raise NotImplementedError

    @abc.abstractmethod
    def rm_dir(self, path, remove_zip):
        """Remove a directory."""
        raise NotImplementedError

    @abc.abstractmethod
    def rmtree(self, path):
        """Recursively delete a directory tree."""
        raise NotImplementedError

    @abc.abstractmethod
    def publish(self, active_project_path, published_project_path):
        """Operations on files performed before publishing a project."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_project_file_root(self, slug, access_policy, klass):
        """Root directory containing the published project's files."""
        raise NotImplementedError

    @abc.abstractmethod
    def storage_used(self, path, zip_name):
        """Total storage used in bytes."""
        raise NotImplementedError

    @abc.abstractmethod
    def make_zip(self, project):
        """Make a (new) zip file of the main files."""
        raise NotImplementedError

    @abc.abstractmethod
    def make_checksum_file(self, project):
        """Make the checksums file for the main files."""
        raise NotImplementedError
