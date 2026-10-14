"""Make untrusted text (titles, LLM output) safe to publish as Markdown on the site."""

import re

_RAW_TAG = re.compile(r"<(?!!--)")
"""Opening `<` of an HTML tag; HTML comments (`<!-- note:… -->` markers) are kept."""


def escape_html(text: str) -> str:
    """Neutralise raw HTML: titles and LLM output must never run as markup on the site.

    Args:
        text: Markdown text.

    Returns:
        The text with every `<` that is not an HTML comment written as `&lt;`.
    """
    return _RAW_TAG.sub("&lt;", text)


def link_text(text: str) -> str:
    """Make a text safe inside a Markdown link text and a table cell.

    Args:
        text: Any one-line text.

    Returns:
        The text with raw HTML neutralised, `|` escaped and square brackets turned into
        parentheses.
    """
    return escape_html(text).replace("|", "\\|").replace("[", "(").replace("]", ")")


def escape_body(text: str) -> str:
    """Neutralise raw HTML in a Markdown file, leaving its YAML front-matter alone.

    Args:
        text: A Markdown file, with or without front-matter.

    Returns:
        The file with raw HTML neutralised after its front-matter.
    """
    if text.startswith("---\n") and (end := text.find("\n---\n", 4)) != -1:
        split = end + len("\n---\n")
        return text[:split] + escape_html(text[split:])
    return escape_html(text)
