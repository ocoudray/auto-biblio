from auto_biblio.domain.website.text import escape_body, escape_html, link_text


def test_escape_html_keeps_comments() -> None:
    assert escape_html("a <b> <!-- note:x -->") == "a &lt;b> <!-- note:x -->"


def test_link_text() -> None:
    assert link_text("x|y[z] <i>") == "x\\|y(z) &lt;i>"


def test_escape_body_leaves_front_matter_alone() -> None:
    text = "---\ntitle: <x>\n---\n\n# T\n\n<script>\n"
    assert escape_body(text) == "---\ntitle: <x>\n---\n\n# T\n\n&lt;script>\n"
    assert escape_body("<b>") == "&lt;b>"
