"""Pages taken from `kb/`, with a metadata line the files themselves do not show."""

from collections.abc import Mapping

from auto_biblio.domain.errors import KBFormatError
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.kb.notes import Depth, Note, NoteKind, parse_note
from auto_biblio.domain.kb.pages import ThemePage, parse_theme_page

KIND_LABELS: dict[NoteKind, str] = {"paper": "Article", "tool": "Outil", "post": "Billet"}
DEPTH_LABELS: dict[Depth, str] = {"short": "fiche courte", "deep": "fiche approfondie"}


def note_page(text: str, origin: str, labels: Mapping[ThemeId, str]) -> tuple[str, Note | None]:
    """Turn a note file into its page: the file, with its metadata under the title.

    Args:
        text: The note file.
        origin: Its path, for error messages.
        labels: Theme labels by id; an unknown theme shows its id.

    Returns:
        The page and the parsed note, or the file unchanged and None when it cannot be read.
    """
    try:
        note = parse_note(text, origin)
    except KBFormatError:
        return text, None
    meta = note.meta
    parts = [
        f"[Source]({meta.url})",
        KIND_LABELS[meta.kind],
        *(labels.get(theme, theme) for theme in meta.themes),
        DEPTH_LABELS[meta.depth],
        f"vue le {meta.first_seen.isoformat()}",
        f"analysée le {meta.analyzed_at.isoformat()}",
    ]
    return _under_title(text, "> " + " · ".join(parts)), note


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
        return text, None
    return _under_title(text, f"> Mise à jour le {page.meta.updated_at.isoformat()}"), page


def _under_title(text: str, line: str) -> str:
    lines = text.split("\n")
    # Parsed files always have a `# ` title after their front-matter.
    title = next(i for i, current in enumerate(lines) if current.startswith("# "))
    return "\n".join([*lines[: title + 1], "", line, *lines[title + 1 :]])
