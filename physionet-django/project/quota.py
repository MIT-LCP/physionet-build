import errno
import os

from physionet.gcs import GCSObject


class QuotaManager:
    """
    Abstract class for tracking disk usage and size limits.
    """

    @property
    def block_size(self):
        """
        Filesystem block size.

        This can be used to estimate the actual disk usage of a file
        to be written (assuming that the filesystem allocates files in
        whole-block-sized units, which is usually the case.)
        """
        if not self._cache_valid:
            self.refresh()
        return self._block_size

    @property
    def bytes_used(self):
        """
        Current number of bytes of storage used.

        Depending on the implementation, this might be rounded to a
        multiple of the filesystem block size.  It might or might not
        include the space used by directory entries.
        """
        if not self._cache_valid:
            self.refresh()
        return self._bytes_used

    @property
    def bytes_soft(self):
        """
        Current soft limit on the number of bytes of storage.

        If there is no soft limit, this is 0.  It makes no sense for
        the soft limit to be greater than the hard limit.

        Depending on the implementation, this might be constrained to
        be a multiple of the filesystem block size.
        """
        if not self._cache_valid:
            self.refresh()
        return self._bytes_soft

    @property
    def bytes_hard(self):
        """
        Current hard limit on the number of bytes of storage.

        If there is no hard limit, this is 0.

        Depending on the implementation, this might be constrained to
        be a multiple of the filesystem block size.
        """
        if not self._cache_valid:
            self.refresh()
        return self._bytes_hard

    @property
    def inodes_used(self):
        """
        Current number of inodes (files + directories) used.
        """
        if not self._cache_valid:
            self.refresh()
        return self._inodes_used

    @property
    def inodes_soft(self):
        """
        Current soft limit on the number of inodes.

        If there is no soft limit, this is 0.  It makes no sense for
        the soft limit to be greater than the hard limit.
        """
        if not self._cache_valid:
            self.refresh()
        return self._inodes_soft

    @property
    def inodes_hard(self):
        """
        Current hard limit on the number of inodes.

        If there is no hard limit, this is 0.
        """
        if not self._cache_valid:
            self.refresh()
        return self._inodes_hard

    def refresh(self):
        """
        Refresh the current usage and limits from the backend.

        This should be called to update the cached information after
        an external process has made changes to the project.
        """
        raise NotImplementedError()

    def set_limits(self, bytes_soft=None, bytes_hard=None,
                   inodes_soft=None, inodes_hard=None):
        """
        Set limits on the number of bytes and/or inodes.
        """
        raise NotImplementedError()

    def create_toplevel_directory(self):
        """
        Create the top-level project directory.
        """
        raise NotImplementedError()

    def check_create_file(self, path, size):
        """
        Update usage when creating a file.

        This can be used to simulate the behavior of filesystem
        quotas; the DemoQuotaManager implementation will raise an
        OSError if the new file would exceed the limit.
        """
        pass

    def check_delete_file(self, path, size):
        """
        Update usage when deleting a file.
        """
        pass

    def check_create_directory(self, path):
        """
        Update usage when creating a directory.

        This can be used to simulate the behavior of filesystem
        quotas; the DemoQuotaManager implementation will raise an
        OSError if the new file would exceed the limit.
        """
        pass

    def check_delete_directory(self, path):
        """
        Update usage when removing a directory.
        """
        pass


class DemoQuotaManager(QuotaManager):
    """
    QuotaManager that scans the directory tree recursively.

    This implementation is meant to allow testing without superuser
    privileges, but is not robust or scalable.  Usage is calculated by
    reading the entire directory tree and adding up the sizes of the
    files.

    Files that have multiple hard links, and were modified before the
    project creation time, are not counted against the quota.

    The check_create_file and check_create_directory functions will
    raise an OSError if the specified hard limits would be exceeded,
    simulating the behavior of a filesystem that enforces quota.
    """
    def __init__(self, project_path, creation_time):
        self._project_path = project_path
        self._creation_time_ns = int(creation_time.timestamp()
                                     * 1000 * 1000 * 1000)
        self._cache_valid = False
        self._block_size = 1
        self._bytes_used = 0
        self._bytes_soft = 0
        self._bytes_hard = 0
        self._inodes_used = 0
        self._inodes_soft = 0
        self._inodes_hard = 0

    def refresh(self):
        """
        Refresh the current usage and limits from the backend.

        This is done by traversing the directory tree and counting the
        total number of files and bytes.
        """
        self._inodes_used = 0
        self._bytes_used = 0
        self._scan_tree(self._project_path)
        self._cache_valid = True

    def _scan_tree(self, path):
        self._inodes_used += 1
        for entry in os.scandir(path):
            if entry.is_dir(follow_symlinks=False):
                self._scan_tree(entry.path)
            else:
                s = entry.stat(follow_symlinks=False)
                # Files with multiple links are counted only if their
                # modification time is later than the project creation
                # time.  Files with a single link are always counted,
                # regardless of mtime: this accounts for simple cases
                # involving the demo projects, and also cases where
                # files have been manually uploaded (e.g., by an
                # administrator using rsync.)
                if s.st_nlink == 1 or s.st_mtime_ns >= self._creation_time_ns:
                    self._inodes_used += 1
                    self._bytes_used += s.st_size

    def set_limits(self, bytes_soft=None, bytes_hard=None,
                   inodes_soft=None, inodes_hard=None):
        """
        Set limits on the number of bytes and/or inodes.
        """
        if bytes_soft is not None:
            self._bytes_soft = bytes_soft
        if bytes_hard is not None:
            self._bytes_hard = bytes_hard
        if inodes_soft is not None:
            self._inodes_soft = inodes_soft
        if inodes_hard is not None:
            self._inodes_hard = inodes_hard

    def create_toplevel_directory(self):
        """
        Create the top-level project directory.
        """
        os.mkdir(self._project_path)

    def check_create_file(self, path, size):
        """
        Update usage when creating a file.

        If creating a file of the given size would cause the hard
        limits to be exceeded, this raises an OSError with errno =
        EDQUOT, and inodes_used/bytes_used are unchanged.  Otherwise,
        inodes_used and bytes_used are increased accordingly.
        """
        if not self._cache_valid:
            self.refresh()

        if self._inodes_used + 1 > self._inodes_hard > 0:
            raise OSError(errno.EDQUOT, 'Quota exceeded')

        if self._bytes_used + size > self._bytes_hard > 0:
            raise OSError(errno.EDQUOT, 'Quota exceeded')

        self._inodes_used += 1
        self._bytes_used += size

    def check_delete_file(self, path, size):
        """
        Update usage when deleting a file.
        """
        if not self._cache_valid:
            self.refresh()
        self._inodes_used -= 1
        self._bytes_used -= size

    def check_create_directory(self, path):
        """
        Update usage when creating a directory.

        If creating a new directory would cause the hard limits to be
        exceeded, this raises an OSError with errno = EDQUOT, and
        inodes_used is unchanged.  Otherwise, inodes_used is increased
        by 1.
        """
        if not self._cache_valid:
            self.refresh()

        if self._inodes_used + 1 > self._inodes_hard > 0:
            raise OSError(errno.EDQUOT, 'Quota exceeded')

        self._inodes_used += 1

    def check_delete_directory(self, path):
        """
        Update usage when deleting a directory.
        """
        if not self._cache_valid:
            self.refresh()
        self._inodes_used -= 1


class GCSQuotaManager(QuotaManager):
    """
    QuotaManager for Google Cloud storage.

    This implementation, like DemoQuotaManager, is not robust or
    scalable.  As far as I know, as of 2023, there is no way to
    implement robust, scalable storage quotas using GCS.

    - As with DemoQuotaManager, there is nothing to stop multiple
      authorized clients from uploading multiple files at once and
      exceeding the storage limit, even if all of them are
      well-behaved.

    - Usage is calculated by listing all objects in the specified
      prefix (which is only slightly more efficient than a "directory
      traversal" as DemoQuotaManager does) and adding up their sizes.

    There is no way to create hard links, so every new project version
    must have a copy of every file; therefore, all files are counted
    equally against the quota.

    The check_create_file function will raise an OSError if the
    specified hard limits would be exceeded, simulating the behavior
    of a filesystem that enforces quota.

    Currently this does not attempt to track or limit the number of
    objects, and inodes_used will be zero.
    """
    def __init__(self, project_path):
        # _project_path must be a directory name (ending with a
        # slash); see GCSObject.is_dir().
        self._project_path = project_path.rstrip('/') + '/'
        self._cache_valid = False
        self._block_size = 1
        self._bytes_used = 0
        self._bytes_soft = 0
        self._bytes_hard = 0
        self._inodes_used = 0
        self._inodes_soft = 0
        self._inodes_hard = 0

    def refresh(self):
        """
        Refresh the current usage and limits from the backend.

        This is done by listing objects underneath the project prefix
        and counting the total number of bytes.
        """
        # FIXME: it'd probably be a *good idea* to try to limit the
        # number of files.  GCSObject doesn't have a way to calculate
        # total size and number of objects all at once, but it'd be
        # easy to do.
        self._bytes_used = GCSObject(self._project_path).size()
        self._cache_valid = True

    def set_limits(self, bytes_soft=None, bytes_hard=None,
                   inodes_soft=None, inodes_hard=None):
        """
        Set limits on the number of bytes and/or inodes.
        """
        if bytes_soft is not None:
            self._bytes_soft = bytes_soft
        if bytes_hard is not None:
            self._bytes_hard = bytes_hard
        if inodes_soft is not None:
            self._inodes_soft = inodes_soft
        if inodes_hard is not None:
            self._inodes_hard = inodes_hard

    def create_toplevel_directory(self):
        """
        Create the top-level project directory.
        """
        GCSObject(self._project_path).mkdir()

    def check_create_file(self, path, size):
        """
        Update usage when creating a file.

        If creating a file of the given size would cause the hard
        limits to be exceeded, this raises an OSError with errno =
        EDQUOT, and bytes_used is unchanged.  Otherwise, bytes_used is
        increased accordingly.
        """
        if not self._cache_valid:
            self.refresh()

        if self._bytes_used + size > self._bytes_hard > 0:
            raise OSError(errno.EDQUOT, 'Quota exceeded')

        self._bytes_used += size

    def check_delete_file(self, path, size):
        """
        Update usage when deleting a file.
        """
        self._bytes_used -= size
