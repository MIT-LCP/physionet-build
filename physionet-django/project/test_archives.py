import io
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile

from django.test import SimpleTestCase
from django.urls import reverse

from project.archives import ArchiveError, extract_archive, is_supported_archive
from project.models import ActiveProject, SubmissionStatus
from user.models import User
from user.test_views import TestMixin

MB = 1024 * 1024


def make_zip(path, entries):
    """entries: list of (name, data); data None makes a folder."""
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            if data is None:
                z.writestr(zipfile.ZipInfo(name.rstrip('/') + '/'), b'')
            else:
                z.writestr(name, data)


def make_tar(path, entries, mode='w:gz'):
    """entries: list of (name, data) or tarfile.TarInfo for special entries."""
    with tarfile.open(path, mode) as t:
        for entry in entries:
            if isinstance(entry, tarfile.TarInfo):
                t.addfile(entry)
                continue
            name, data = entry
            info = tarfile.TarInfo(name)
            if data is None:
                info.type = tarfile.DIRTYPE
                t.addfile(info)
            else:
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))


class TestExtractArchive(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmp, 'dest')
        os.mkdir(self.dest)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def listing(self):
        result = []
        for root, dirs, files in os.walk(self.dest):
            for name in dirs + files:
                result.append(os.path.relpath(os.path.join(root, name), self.dest))
        return sorted(result)

    def assertRejected(self, archive, message):
        with self.assertRaisesRegex(ArchiveError, message):
            extract_archive(archive, self.dest, max_size=MB)
        self.assertEqual(self.listing(), [])

    def test_supported_names(self):
        for name in ('a.zip', 'a.TAR.GZ', 'a.tgz', 'a.tar.bz2', 'a.tar.xz', 'a.tar'):
            self.assertTrue(is_supported_archive(name), name)
        for name in ('a.csv.gz', 'a.gz', 'a.dat', 'zip'):
            self.assertFalse(is_supported_archive(name), name)

    def test_zip(self):
        archive = os.path.join(self.tmp, 'a.zip')
        make_zip(archive, [('data/', None), ('data/x.csv', b'1,2'), ('README', b'hi'),
                           ('__MACOSX/._README', b'junk')])
        self.assertEqual(extract_archive(archive, self.dest, max_size=MB), 2)
        self.assertEqual(self.listing(), ['README', 'data', 'data/x.csv'])
        with open(os.path.join(self.dest, 'data', 'x.csv'), 'rb') as f:
            self.assertEqual(f.read(), b'1,2')
        # No temporary folder left behind
        self.assertFalse([n for n in os.listdir(self.dest) if n.startswith('.unpack-')])

    def test_tar_formats(self):
        for ext, mode in (('tar', 'w'), ('tar.gz', 'w:gz'), ('tar.bz2', 'w:bz2'), ('tar.xz', 'w:xz')):
            with self.subTest(ext=ext):
                shutil.rmtree(self.dest)
                os.mkdir(self.dest)
                archive = os.path.join(self.tmp, 'a.' + ext)
                make_tar(archive, [('top/sub/f.txt', b'abc')], mode)
                self.assertEqual(extract_archive(archive, self.dest, max_size=MB), 1)
                self.assertEqual(self.listing(), ['top', 'top/sub', 'top/sub/f.txt'])

    def test_rejects_parent_paths(self):
        archive = os.path.join(self.tmp, 'a.zip')
        make_zip(archive, [('ok.txt', b'x'), ('../escape.txt', b'x')])
        self.assertRejected(archive, 'outside')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'escape.txt')))

    def test_rejects_absolute_paths(self):
        archive = os.path.join(self.tmp, 'a.tar.gz')
        make_tar(archive, [('/tmp/abs.txt', b'x')])
        self.assertRejected(archive, 'absolute')

    def test_rejects_tar_links(self):
        for link_type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with self.subTest(link_type=link_type):
                archive = os.path.join(self.tmp, 'a.tar.gz')
                link = tarfile.TarInfo('passwd')
                link.type = link_type
                link.linkname = '/etc/passwd'
                make_tar(archive, [link])
                self.assertRejected(archive, 'link')

    def test_rejects_zip_symlinks(self):
        archive = os.path.join(self.tmp, 'a.zip')
        info = zipfile.ZipInfo('passwd')
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr(info, '/etc/passwd')
        self.assertRejected(archive, 'link')

    def test_rejects_existing_items(self):
        archive = os.path.join(self.tmp, 'a.zip')
        make_zip(archive, [('new.txt', b'x'), ('data/x.csv', b'new')])
        os.mkdir(os.path.join(self.dest, 'data'))
        with self.assertRaisesRegex(ArchiveError, 'already exists'):
            extract_archive(archive, self.dest, max_size=MB)
        # Nothing was written
        self.assertEqual(self.listing(), ['data'])

    def test_rejects_too_large(self):
        archive = os.path.join(self.tmp, 'a.zip')
        make_zip(archive, [('big.dat', b'\0' * 2000)])
        with self.assertRaisesRegex(ArchiveError, 'storage allowance'):
            extract_archive(archive, self.dest, max_size=1000)
        self.assertEqual(self.listing(), [])

    def test_rejects_misreported_size(self):
        """A zip whose headers understate the size is caught while writing."""
        archive = os.path.join(self.tmp, 'a.zip')
        make_zip(archive, [('big.dat', b'\0' * 5000)])
        # Rewrite the declared sizes in the local and central headers.
        with open(archive, 'rb') as f:
            data = bytearray(f.read())
        real = (5000).to_bytes(4, 'little')
        fake = (10).to_bytes(4, 'little')
        data = bytes(data).replace(real, fake)
        with open(archive, 'wb') as f:
            f.write(data)
        with self.assertRaises(ArchiveError):
            extract_archive(archive, self.dest, max_size=1000)
        self.assertEqual(self.listing(), [])

    def test_rejects_duplicates(self):
        archive = os.path.join(self.tmp, 'a.tar.gz')
        make_tar(archive, [('a.txt', b'1'), ('a.txt', b'2')])
        self.assertRejected(archive, 'duplicate')

    def test_rejects_invalid_archive(self):
        archive = os.path.join(self.tmp, 'a.zip')
        with open(archive, 'wb') as f:
            f.write(b'not a zip file')
        self.assertRejected(archive, 'not a valid archive')

    def test_rejects_empty_archive(self):
        archive = os.path.join(self.tmp, 'a.zip')
        make_zip(archive, [('__MACOSX/._x', b'junk')])
        self.assertRejected(archive, 'no files')


class TestUnpackArchiveView(TestMixin):
    """
    Editors can unpack archives from the copyedit file browser.
    """
    fixtures = ['demo-training-type.json', 'demo-user.json', 'site-data.json', 'demo-project.json']

    def setUp(self):
        super().setUp()
        self.project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.author = self.project.submitting_author().user
        self.archive = os.path.join(self.project.file_root(), 'extra.zip')
        make_zip(self.archive, [('extra/notes.txt', b'hello')])

    def start_copyedit(self):
        project = self.project
        project.submit(author_comments='')
        project.assign_editor(User.objects.get(username='admin'))
        project.submission_status = SubmissionStatus.NEEDS_DECISION
        project.save()
        self.client.login(username='admin', password='Tester11!')
        self.client.post(reverse('edit_submission', args=(project.slug,)), data={
            'soundly_produced': 1, 'well_described': 1, 'open_format': 1,
            'data_machine_readable': 1, 'reusable': 1, 'no_phi': 1,
            'pn_suitable': 1, 'editor_comments': 'Good.', 'decision': 2,
            'ethics_included': 1,
        })
        project.refresh_from_db()
        self.assertEqual(project.submission_status, SubmissionStatus.NEEDS_COPYEDIT)
        return reverse('copyedit_submission', args=(project.slug,))

    def test_editor_unpacks_archive(self):
        url = self.start_copyedit()
        response = self.client.get(url)
        self.assertContains(response, 'id="unpack-archive-button"')

        response = self.client.post(url, data={
            'unpack_archive': '', 'subdir': '', 'items': 'extra.zip', 'delete_archive': 'on'})
        self.assertMessage(response, 25)
        with open(os.path.join(self.project.file_root(), 'extra', 'notes.txt'), 'rb') as f:
            self.assertEqual(f.read(), b'hello')
        self.assertFalse(os.path.exists(self.archive))

        # Unpacking again is refused because the folder now exists
        make_zip(self.archive, [('extra/notes.txt', b'changed')])
        response = self.client.post(url, data={
            'unpack_archive': '', 'subdir': '', 'items': 'extra.zip'})
        self.assertMessage(response, 40)
        with open(os.path.join(self.project.file_root(), 'extra', 'notes.txt'), 'rb') as f:
            self.assertEqual(f.read(), b'hello')
        self.assertTrue(os.path.exists(self.archive))

    def test_editor_cannot_unpack_outside_folder(self):
        url = self.start_copyedit()
        for items, subdir in (('../extra.zip', ''), ('extra.zip', '..'), ('extra.zip', '/etc')):
            response = self.client.post(url, data={
                'unpack_archive': '', 'subdir': subdir, 'items': items})
            self.assertMessage(response, 40)
        self.assertFalse(os.path.exists(os.path.join(self.project.file_root(), 'extra')))

    def test_author_cannot_unpack(self):
        self.client.login(username=self.author.username, password='Tester11!')
        url = reverse('project_files', args=(self.project.slug,))
        response = self.client.get(url)
        self.assertNotContains(response, 'id="unpack-archive-button"')
        self.client.post(url, data={'unpack_archive': '', 'subdir': '', 'items': 'extra.zip'})
        self.assertFalse(os.path.exists(os.path.join(self.project.file_root(), 'extra')))
