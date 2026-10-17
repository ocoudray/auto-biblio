from auto_biblio.domain.website.text import (
    as_code_block,
    escape_body,
    escape_html,
    escape_outside_code,
    link_text,
)


def test_escape_html_keeps_comments() -> None:
    assert escape_html("a <b> <!-- note:x -->") == "a &lt;b> <!-- note:x -->"


def test_link_text() -> None:
    assert link_text("x|y[z] <i>") == "x\\|y(z) &lt;i>"


def test_escape_body_leaves_front_matter_alone() -> None:
    text = "---\ntitle: <x>\n---\n\n# T\n\n<script>\n"
    assert escape_body(text) == "---\ntitle: <x>\n---\n\n# T\n\n&lt;script>\n"
    assert escape_body("<b>") == "&lt;b>"


def test_escape_outside_code_keeps_code_verbatim() -> None:
    text = "<b> `a<b` ``x`<y``\n````\n<i>\n```\n<j>\n````\n~~~mermaid\nA <--> B\n~~~\n<k>"
    assert escape_outside_code(text) == (
        "&lt;b> `a<b` ``x`<y``\n````\n<i>\n```\n<j>\n````\n~~~mermaid\nA <--> B\n~~~\n&lt;k>"
    )


def test_as_code_block_outgrows_inner_fences() -> None:
    assert as_code_block("a\n```\n") == "````text\na\n```\n````\n"
    assert as_code_block("x") == "```text\nx\n```\n"
