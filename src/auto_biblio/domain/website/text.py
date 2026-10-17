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


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(`+).+?\1")


def escape_outside_code(text: str) -> str:
    """Neutralise raw HTML except in code blocks and code spans, which Markdown already shows.

    Escaping inside code would display `&lt;` literally and break Mermaid diagrams.

    Args:
        text: Markdown text without front-matter.

    Returns:
        The text with raw HTML neutralised outside fenced code blocks and inline code.
    """
    lines: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        opening = _FENCE.match(line)
        if fence is not None:
            if opening and opening.group(1)[0] == fence[0] and len(opening.group(1)) >= len(fence):
                fence = None
            lines.append(line)
        elif opening:
            fence = opening.group(1)
            lines.append(line)
        else:
            lines.append(_escape_outside_spans(line))
    return "\n".join(lines)


def _escape_outside_spans(line: str) -> str:
    parts: list[str] = []
    end = 0
    for span in _CODE_SPAN.finditer(line):
        parts.extend([escape_html(line[end : span.start()]), span.group(0)])
        end = span.end()
    parts.append(escape_html(line[end:]))
    return "".join(parts)


def as_code_block(text: str) -> str:
    """Show a text verbatim, in a fenced code block longer than any backtick run it holds.

    Args:
        text: Any text.

    Returns:
        The fenced block, ending with a newline.
    """
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text.rstrip(chr(10))}\n{fence}\n"
