"""Rendering of the digest view to HTML and plain text."""

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from auto_biblio.domain.website.text import link_text
from auto_biblio.publish.view import DigestView

_ENV = Environment(
    loader=PackageLoader("auto_biblio.publish", "templates"),
    autoescape=select_autoescape(["html.j2"]),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)
# Markdown pages are not HTML-escaped by Jinja: their untrusted fields go through this filter.
_ENV.filters["md"] = link_text


def render_digest(view: DigestView) -> tuple[str, str]:
    """Render the digest.

    Args:
        view: What to show.

    Returns:
        The HTML and plain-text bodies.
    """
    html = _ENV.get_template("digest.html.j2").render(view=view)
    text = _ENV.get_template("digest.txt.j2").render(view=view)
    return html, text


def render_digest_markdown(view: DigestView) -> str:
    """Render the digest as a page of the site's archive.

    The page has no health footer, cost or feedback links: those belong to the mail.

    Args:
        view: What to show.

    Returns:
        The Markdown page.
    """
    return _ENV.get_template("digest.md.j2").render(view=view)
