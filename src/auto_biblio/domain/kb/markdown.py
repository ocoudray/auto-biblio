"""Deterministic Markdown with a YAML front-matter and named sections.

Writing then reading a document gives back the same data, so the pipeline can re-read what
it wrote (to merge a note or keep a theme page's links) without a sidecar file.
"""

from collections.abc import Mapping, Sequence
from typing import cast

import yaml

from auto_biblio.domain.errors import KBFormatError


def clean(text: str) -> str:
    """Collapse whitespace so that a value survives a round trip through Markdown.

    Args:
        text: Any text.

    Returns:
        The text on one line, single-spaced.
    """
    return " ".join(text.split())


def render_document(
    front_matter: Mapping[str, object], title: str, sections: Sequence[tuple[str, str]]
) -> str:
    """Render a document.

    Args:
        front_matter: Metadata, dumped as YAML in the given key order.
        title: The `# title` line.
        sections: (heading, already rendered body) pairs, in order.

    Returns:
        The Markdown text, ending with one newline.
    """
    meta = yaml.safe_dump(dict(front_matter), sort_keys=False, allow_unicode=True, width=1000)
    parts = [f"---\n{meta}---", f"# {clean(title)}"]
    parts.extend(f"## {heading}\n\n{body}".rstrip() for heading, body in sections)
    return "\n\n".join(parts) + "\n"


def render_text(value: str) -> str:
    """Render the body of a text section.

    Args:
        value: The text.

    Returns:
        The text on one line.
    """
    return clean(value)


def render_list(values: Sequence[str]) -> str:
    """Render the body of a list section.

    Args:
        values: The items.

    Returns:
        One `- item` line per item.
    """
    return "\n".join(f"- {clean(value)}" for value in values)


def split_document(text: str, origin: str) -> tuple[dict[str, object], str, dict[str, str]]:
    """Split a document into front-matter, title and section bodies.

    Args:
        text: The Markdown text.
        origin: Where the text comes from, for error messages.

    Returns:
        The front-matter, the title and each section body by heading.

    Raises:
        KBFormatError: If the front-matter or the title is missing or invalid.
    """
    if not text.startswith("---\n") or "\n---\n" not in text:
        raise KBFormatError(origin, "missing YAML front-matter")
    head, _, rest = text[4:].partition("\n---\n")
    try:
        meta: object = yaml.safe_load(head)
    except yaml.YAMLError as exc:
        raise KBFormatError(origin, f"invalid front-matter: {exc}") from exc
    if not isinstance(meta, dict):
        raise KBFormatError(origin, "front-matter is not a mapping")
    # yaml.safe_load returns untyped data; the caller validates it with its Pydantic model.
    mapping = cast("dict[object, object]", meta)
    lines = rest.strip("\n").split("\n")
    if not lines or not lines[0].startswith("# "):
        raise KBFormatError(origin, "missing `# title` line")
    sections: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in lines[1:]:
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(body).strip("\n")
            current, body = line[3:].strip(), []
        else:
            body.append(line)
    if current is not None:
        sections[current] = "\n".join(body).strip("\n")
    return {str(k): v for k, v in mapping.items()}, lines[0][2:].strip(), sections


def parse_list(body: str) -> tuple[str, ...]:
    """Read back the items of a list section.

    Args:
        body: The section body.

    Returns:
        The items.
    """
    return tuple(line[2:].strip() for line in body.splitlines() if line.startswith("- "))
