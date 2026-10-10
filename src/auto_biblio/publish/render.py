"""Rendering of the digest view to HTML and plain text."""

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from auto_biblio.publish.view import DigestView

_ENV = Environment(
    loader=PackageLoader("auto_biblio.publish", "templates"),
    autoescape=select_autoescape(["html.j2"]),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


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
