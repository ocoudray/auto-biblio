"""Pages taken from `kb/`, with a metadata line the files themselves do not show."""

from collections.abc import Mapping, Sequence

from auto_biblio.domain.errors import KBFormatError
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.kb.notes import Depth, Note, NoteKind, parse_note
from auto_biblio.domain.kb.pages import ThemePage, parse_theme_page
from auto_biblio.domain.website.text import escape_body, link_text

KIND_LABELS: dict[NoteKind, str] = {"paper": "Article", "tool": "Outil", "post": "Billet"}
DEPTH_LABELS: dict[Depth, str] = {"short": "fiche courte", "deep": "fiche approfondie"}


def note_page(
    text: str,
    origin: str,
    labels: Mapping[ThemeId, str],
    notions: Sequence[tuple[str, str]] = (),
) -> tuple[str, Note | None]:
    """Turn a note file into its page: the file, with its metadata under the title.

    Args:
        text: The note file.
        origin: Its path, for error messages.
        labels: Theme labels by id; an unknown theme shows its id.
        notions: Wiki notions the note is linked to, as (title, path relative to the note).

    Returns:
        The page (raw HTML neutralised) and the parsed note, or the page alone and None when
        the file cannot be read.
    """
    try:
        note = parse_note(text, origin)
    except KBFormatError:
        return escape_body(text), None
    meta = note.meta
    parts = [
        f"[Source]({meta.url})",
        KIND_LABELS[meta.kind],
        *(link_text(labels.get(theme, theme)) for theme in meta.themes),
        DEPTH_LABELS[meta.depth],
        f"vue le {meta.first_seen.isoformat()}",
        f"analysée le {meta.analyzed_at.isoformat()}",
    ]
    header = "> " + " · ".join(parts)
    if notions:
        links = " · ".join(f"[{link_text(title)}]({href})" for title, href in notions)
        header += f"\n\n> Notions : {links}"
    return under_title(escape_body(text), header), note


def theme_page(text: str, origin: str) -> tuple[str, ThemePage | None]:
    """Turn a theme page file into its page: the file, with its update date under the title.

    Args:
        text: The theme page file.
        origin: Its path, for error messages.

    Returns:
        The page and the parsed theme page, or the file unchanged and None when it cannot be
        read.
    """
    try:
        page = parse_theme_page(text, origin)
    except KBFormatError:
        return escape_body(text), None
    date_line = f"> Mise à jour le {page.meta.updated_at.isoformat()}"
    return under_title(escape_body(text), date_line), page


def under_title(text: str, line: str) -> str:
    """Insert a line under the `# ` title of a page, after a blank line.

    Args:
        text: A page that has a `# ` title.
        line: The text to insert.

    Returns:
        The page with the line under its title.
    """
    lines = text.split("\n")
    # Parsed files always have a `# ` title after their front-matter.
    title = next(i for i, current in enumerate(lines) if current.startswith("# "))
    return "\n".join([*lines[: title + 1], "", line, *lines[title + 1 :]])
