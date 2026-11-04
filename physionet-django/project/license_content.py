from html2text import HTML2Text


def license_html_to_text(html):
    """Convert license HTML without wrapping copyright placeholders."""
    converter = HTML2Text()
    converter.body_width = 0
    converter.ignore_emphasis = True
    # Keep links and their destinations in the downloadable license.
    return converter.handle(html)
