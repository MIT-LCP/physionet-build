"""
Test cases for physionet templatetags.

This module tests the custom template filters defined in physionet_templatetags.py.
"""

from django.test import SimpleTestCase
from physionet.templatetags.physionet_templatetags import news_preview


class PhysionetTemplatetagsTestCase(SimpleTestCase):
    """Test cases for physionet templatetags."""

    def test_news_preview_empty_content(self):
        """Test news_preview filter with empty content."""
        result = news_preview("")
        self.assertEqual(result, "")

    def test_news_preview_none_content(self):
        """Test news_preview filter with None content."""
        result = news_preview(None)
        self.assertEqual(result, "")

    def test_news_preview_simple_text(self):
        """Test news_preview filter with simple text."""
        content = "This is a simple news article about PhysioNet."
        result = news_preview(content)
        self.assertEqual(result, "This is a simple news article about PhysioNet.")

    def test_news_preview_html_tags(self):
        """Test news_preview filter with HTML tags."""
        content = (
            '<p>This is a <strong>news</strong> article with <em>HTML</em> tags.</p>'
        )
        result = news_preview(content)
        self.assertEqual(result, "This is a news article with HTML tags.")

    def test_news_preview_html_entities(self):
        """Test news_preview filter with HTML entities."""
        content = "We&#39;ve been working on this project."
        result = news_preview(content)
        self.assertEqual(result, "We've been working on this project.")

    def test_news_preview_multiple_html_entities(self):
        """Test news_preview filter with multiple HTML entities."""
        content = 'The &quot;new&quot; feature is great &amp; useful!'
        result = news_preview(content)
        self.assertEqual(result, 'The "new" feature is great & useful!')

    def test_news_preview_with_images(self):
        """Test news_preview filter removes images."""
        content = (
            '<p>This article has an image: <img src="test.jpg" alt="Test"> '
            'and more text.</p>'
        )
        result = news_preview(content)
        self.assertEqual(result, "This article has an image: and more text.")

    def test_news_preview_with_complex_html(self):
        """Test news_preview filter with complex HTML structure."""
        content = '''
        <div>
            <h2>Important News</h2>
            <p>Here&#39;s some <strong>important</strong> content with an image:
            <img src="banner.png" alt="Banner" style="width: 100%;"> and more text.</p>
            <ul>
                <li>List item 1</li>
                <li>List item 2</li>
            </ul>
        </div>
        '''
        result = news_preview(content)
        # Should remove HTML tags, decode entities, and normalize whitespace
        expected = (
            "Important News Here's some important content with an image: "
            "and more text. List item 1 List item 2"
        )
        self.assertEqual(result, expected)

    def test_news_preview_truncation(self):
        """Test news_preview filter truncates long content."""
        content = (
            "This is a very long news article that contains a lot of text and "
            "should be truncated to a reasonable length for display on the "
            "front page. It goes on and on with more content that nobody "
            "wants to see in a preview."
        )
        result = news_preview(content, max_length=100)
        # Should truncate at word boundary and add ...
        self.assertTrue(len(result) <= 100)
        self.assertTrue(result.endswith('...'))
        # Should be truncated before "preview"
        self.assertNotIn('preview', result)

    def test_news_preview_custom_length(self):
        """Test news_preview filter with custom max length."""
        content = "Short content"
        result = news_preview(content, max_length=50)
        self.assertEqual(result, "Short content")

    def test_news_preview_whitespace_normalization(self):
        """Test news_preview filter normalizes whitespace."""
        content = "  Multiple    spaces   and\n\nline\nbreaks  "
        result = news_preview(content)
        self.assertEqual(result, "Multiple spaces and line breaks")

    def test_news_preview_mixed_content(self):
        """Test news_preview filter with mixed content types."""
        content = '''
        <div>
            <h1>Breaking News</h1>
            <p>We&#39;ve discovered &quot;amazing&quot; results!</p>
            <img src="chart.png" alt="Chart">
            <p>More details follow...</p>
        </div>
        '''
        result = news_preview(content)
        expected = (
            "Breaking News We've discovered \"amazing\" results! "
            "More details follow..."
        )
        self.assertEqual(result, expected)
