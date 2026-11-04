"""
Safely unpack zip and tar archives within a project's files.

Every entry is checked before anything is written:
- paths must stay inside the destination folder
- only regular files and folders are allowed (no links or devices)
- nothing may already exist at any of the paths
- the total size must fit in the given limit

Files are unpacked into a temporary folder first and only moved into
place once everything has been written, so a failure leaves the
project unchanged.
"""
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile

# Folders added by macOS when creating zip files; never wanted.
IGNORED_DIRS = {'__MACOSX'}

TAR_EXTENSIONS = ('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz')
ZIP_EXTENSIONS = ('.zip',)
SUPPORTED_EXTENSIONS = ZIP_EXTENSIONS + TAR_EXTENSIONS

COPY_CHUNK_SIZE = 1024 * 1024


class ArchiveError(Exception):
    """The archive cannot be unpacked. The message is safe to show to users."""


def is_supported_archive(name):
    return name.lower().endswith(SUPPORTED_EXTENSIONS)


class _Member:
    def __init__(self, parts, is_dir, size, open_func):
        self.parts = parts
        self.is_dir = is_dir
        self.size = size
        self.open = open_func

    @property
    def path(self):
        return '/'.join(self.parts)


def _split_path(name):
    """
    Split an archive entry name into path components, rejecting any
    that could point outside the destination folder.
    """
    if '\0' in name or '\\' in name:
        raise ArchiveError(f'Invalid path in archive: {name!r}')
    if name.startswith('/'):
        raise ArchiveError(f'Archive contains an absolute path: {name}')
    parts = [p for p in name.split('/') if p not in ('', '.')]
    if '..' in parts:
        raise ArchiveError(f'Archive contains a path outside its folder: {name}')
    return parts


def _zip_members(archive):
    for info in archive.infolist():
        # Zip files made on Unix record the file type in the top bits.
        # Many tools leave it out (only permission bits, or nothing).
        file_type = stat.S_IFMT(info.external_attr >> 16)
        if file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR):
            raise ArchiveError(f'Archive contains a link or special file: {info.filename}')
        yield _Member(
            parts=_split_path(info.filename),
            is_dir=info.is_dir(),
            size=info.file_size,
            open_func=lambda info=info: archive.open(info),
        )


def _tar_members(archive):
    for info in archive.getmembers():
        if not (info.isfile() or info.isdir()):
            raise ArchiveError(f'Archive contains a link or special file: {info.name}')
        yield _Member(
            parts=_split_path(info.name),
            is_dir=info.isdir(),
            size=info.size if info.isfile() else 0,
            open_func=lambda info=info: archive.extractfile(info),
        )


def _open_archive(path):
    name = path.lower()
    try:
        if name.endswith(ZIP_EXTENSIONS):
            archive = zipfile.ZipFile(path)
            return archive, list(_zip_members(archive))
        if name.endswith(TAR_EXTENSIONS):
            archive = tarfile.open(path)
            return archive, list(_tar_members(archive))
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as e:
        raise ArchiveError('The file is not a valid archive') from e
    raise ArchiveError('Unsupported archive type')


def _copy_limited(src, dst, limit):
    """Copy src to dst, failing if more than limit bytes are written."""
    written = 0
    while True:
        chunk = src.read(COPY_CHUNK_SIZE)
        if not chunk:
            return written
        written += len(chunk)
        if written > limit:
            raise ArchiveError('The unpacked files would exceed the remaining storage allowance')
        dst.write(chunk)


def extract_archive(archive_path, dest_dir, max_size):
    """
    Unpack archive_path into dest_dir.

    max_size is the most bytes the unpacked files may take up.

    Returns the number of files unpacked. Raises ArchiveError if the
    archive is unsafe, invalid, too large, or would overwrite anything.
    """
    archive, members = _open_archive(archive_path)
    with archive:
        members = [m for m in members if m.parts and m.parts[0] not in IGNORED_DIRS]
        if not any(not m.is_dir for m in members):
            raise ArchiveError('The archive contains no files')

        # Two entries with the same path, or a path both a file and a
        # folder, would make the result depend on the order of entries.
        files, dirs = set(), set()
        for m in members:
            key = tuple(m.parts)
            if key in files or (not m.is_dir and key in dirs):
                raise ArchiveError(f'Archive contains duplicate entries: {m.path}')
            (dirs if m.is_dir else files).add(key)
            dirs.update(key[:i] for i in range(1, len(key)))
        if files & dirs:
            raise ArchiveError('Archive contains a path that is both a file and a folder')

        total_size = sum(m.size for m in members if not m.is_dir)
        if total_size > max_size:
            raise ArchiveError('The unpacked files would exceed the remaining storage allowance')

        # Only top-level names can clash with existing items, because
        # nothing below a new top-level name exists yet.
        for name in {m.parts[0] for m in members}:
            if os.path.lexists(os.path.join(dest_dir, name)):
                raise ArchiveError(f'An item named {name} already exists in this folder')

        tmp_dir = tempfile.mkdtemp(prefix='.unpack-', dir=dest_dir)
        try:
            remaining = max_size
            for m in members:
                target = os.path.join(tmp_dir, *m.parts)
                if m.is_dir:
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                # Archives can misreport sizes, so count what is
                # actually written.
                with m.open() as src, open(target, 'xb') as dst:
                    remaining -= _copy_limited(src, dst, remaining)

            for name in os.listdir(tmp_dir):
                os.rename(os.path.join(tmp_dir, name), os.path.join(dest_dir, name))
        except (zipfile.BadZipFile, tarfile.TarError, EOFError, zipfile.LargeZipFile) as e:
            raise ArchiveError('The archive is damaged and could not be unpacked') from e
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return len(files)
