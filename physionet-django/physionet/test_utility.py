import os
import shutil
import tempfile
import unittest
import zipfile

from django.test import TestCase

from physionet import utility


class TestZipFile(TestCase):
    """
    Test ZIP file creation.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

        self.files_dir = os.path.join(self.tmp_dir.name, 'files')
        self.subdir = os.path.join(self.files_dir, 'three')
        self.file1 = os.path.join(self.files_dir, 'one')
        self.file2 = os.path.join(self.files_dir, 'two')
        self.file3 = os.path.join(self.files_dir, 'three', 'abc')
        self.file4 = os.path.join(self.files_dir, 'three', 'def')

        os.mkdir(self.files_dir)
        os.mkdir(self.subdir)
        for path in [self.file1, self.file2, self.file3, self.file4]:
            with open(path, 'w') as f:
                pass

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_zip(self):
        """
        Test that we can create a valid ZIP file.

        This runs physionet.utility.zip_dir and checks that it writes
        files to the archive in alphabetical order.
        """
        zip_path = os.path.join(self.tmp_dir.name, "files.zip")
        utility.zip_dir(zip_path, self.files_dir)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            self.assertEqual(zf.namelist(),
                             ['one', 'three/abc', 'three/def', 'two'])

    @unittest.skipIf(shutil.which('zipdetails') is None,
                     "zipdetails is not installed")
    def test_zip_permissions(self):
        """
        Test that ZIP files not retain file permissions.

        This runs physionet.utility.zip_dir twice, with different
        permissions for the data files, and checks that the results
        are identical.  (All files in the archive should be normalized
        to mode 644 or 755.)
        """
        os.chmod(self.file1, 0o644)
        os.chmod(self.file2, 0o664)
        os.chmod(self.file3, 0o550)
        os.chmod(self.file4, 0o750)
        zip_path1 = os.path.join(self.tmp_dir.name, "files1.zip")
        utility.zip_dir(zip_path1, self.files_dir)

        os.chmod(self.file1, 0o444)
        os.chmod(self.file2, 0o444)
        os.chmod(self.file3, 0o555)
        os.chmod(self.file4, 0o555)
        zip_path2 = os.path.join(self.tmp_dir.name, "files2.zip")
        utility.zip_dir(zip_path2, self.files_dir)

        with open(zip_path1, 'rb') as zf1:
            contents1 = zf1.read()
        with open(zip_path2, 'rb') as zf2:
            contents2 = zf2.read()
        self.assertEqual(contents1, contents2)
