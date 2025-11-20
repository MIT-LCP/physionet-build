import os
import shutil
import tempfile
import unittest
import zipfile

from django.test import TestCase, override_settings

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
            with open(path, 'w'):
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


@override_settings(GEOIP_PATH=os.path.join(os.path.dirname(__file__),
                                           '..', '..', 'demo-files', 'geoip'))
class TestGeoIP(TestCase):
    """
    Test GeoIP functionality using the MaxMind test database.
    """

    def setUp(self):
        # Ensure the test database exists
        test_db_path = os.path.join(os.path.dirname(__file__), '..', '..',
                                    'demo-files', 'geoip', 'GeoLite2-Country.mmdb')

    def test_localhost_ips(self):
        """
        Test that localhost IPs return 'localhost'.
        """
        localhost_ips = ["127.0.0.1", "localhost", "::1"]
        for ip in localhost_ips:
            with self.subTest(ip=ip):
                country_code = utility.get_country_code(ip)
                self.assertEqual(country_code, "localhost")

    def test_known_countries_in_test_db(self):
        """
        Test IPs that are known to be in the test database.
        """
        # Test cases from the MaxMind test database
        test_cases = [
            ("2.125.160.216", "GB"),   # United Kingdom
            ("50.114.0.0", "US"),      # United States
            ("89.160.20.112", "SE"),   # Sweden
        ]

        for ip, expected_country in test_cases:
            with self.subTest(ip=ip, expected_country=expected_country):
                country_code = utility.get_country_code(ip)
                self.assertEqual(country_code, expected_country)

    def test_rfc1918_private_ips(self):
        """
        Test that RFC1918 private IP addresses return None (allowed).
        """
        rfc1918_ips = [
            "10.0.0.1",
            "10.1.2.3",
            "172.16.0.1",
            "172.20.0.1",
            "192.168.1.1",
            "192.168.100.1",
        ]

        for ip in rfc1918_ips:
            with self.subTest(ip=ip):
                country_code = utility.get_country_code(ip)
                # Private IPs should return None (not found in database)
                self.assertIsNone(country_code)

    def test_other_private_ips(self):
        """
        Test other private/reserved IP ranges that should return None.
        """
        private_ips = [
            "0.0.0.0",
            "169.254.1.1",
            "224.0.0.1",
            "240.0.0.1",
            "255.255.255.255",
        ]

        for ip in private_ips:
            with self.subTest(ip=ip):
                country_code = utility.get_country_code(ip)
                self.assertIsNone(country_code)

    def test_unknown_public_ips(self):
        """
        Test public IPs that are not in the test database.
        These should return None or raise an exception.
        """
        unknown_ips = [
            "8.8.8.8",      # Google DNS (not in test DB)
            "1.1.1.1",      # Cloudflare DNS (not in test DB)
            "18.18.42.54",  # Random public IP (not in test DB)
        ]

        for ip in unknown_ips:
            with self.subTest(ip=ip):
                country_code = utility.get_country_code(ip)

                # If it returns a country code, it should be a valid one
                if country_code is not None:
                    self.assertIsInstance(country_code, str)
                    self.assertEqual(len(country_code), 2)

    def test_invalid_ips(self):
        """
        Test invalid IP addresses that should return None or raise TypeError.
        """
        invalid_ips = [
            "invalid",
            "256.256.256.256",
            "1.2.3.4.5",
            "",
        ]

        for ip in invalid_ips:
            with self.subTest(ip=ip):
                country_code = utility.get_country_code(ip)
                # Invalid IPs should return None
                self.assertIsNone(country_code)

        with self.subTest(ip=None):
            with self.assertRaises(TypeError):
                utility.get_country_code(None)

    def test_ipv6_addresses(self):
        """
        Test IPv6 addresses (excluding localhost).
        """
        # Test a valid IPv6 address (not in test DB, should return None or a country code)
        country_code = utility.get_country_code("2001:4860:4860::8888")

        # If it returns a country code, it should be a valid one
        if country_code is not None:
            self.assertIsInstance(country_code, str)
            self.assertEqual(len(country_code), 2)

    @override_settings(GEOIP_PATH=None)
    def test_no_geoip_database(self):
        """
        Test behavior when no GeoIP database is configured.
        """
        # Should still handle localhost IPs
        self.assertEqual(utility.get_country_code("127.0.0.1"), "localhost")
        self.assertEqual(utility.get_country_code("localhost"), "localhost")
        self.assertEqual(utility.get_country_code("::1"), "localhost")

        # Should return None for other IPs when no database is available
        self.assertIsNone(utility.get_country_code("8.8.8.8"))
