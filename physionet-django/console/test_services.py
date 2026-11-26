import io

from django.test import SimpleTestCase

from console.services import _parse_pdf_to_string


class TestParsePdfToString(SimpleTestCase):
    def test_truncated_pdf_returns_empty_string(self):
        # A PDF cut off inside its first object; pdfminer raises PSEOF, which
        # is not a subclass of PDFException.
        truncated = io.BytesIO(b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog')
        with self.assertLogs(level='ERROR') as logs:
            self.assertEqual(_parse_pdf_to_string(truncated), '')
        self.assertIn('Failed to extract text', logs.output[0])
