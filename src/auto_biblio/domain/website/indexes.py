"""Index pages of the site: notes by kind and by theme, home page, weekly lists."""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.kb.notes import Note, NoteKind
from auto_biblio.domain.kb.pages import ThemePage
from auto_biblio.domain.website.pages import DEPTH_LABELS
from auto_biblio.repo_config.profile import Profile

KIND_TITLES: dict[NoteKind, str] = {"paper": "Articles", "tool": "Outils", "post": "Billets"}
NO_NOTE = "Aucune fiche pour l'instant."


def table_cell(text: str) -> str:
    """Make a text safe inside a Markdown table cell and a link text.

    Args:
        text: Any one-line text.

    Returns:
        The text, with `|` escaped and square brackets turned into parentheses.
    """
    return text.replace("|", "\\|").replace("[", "(").replace("]", ")")


def _newest_first(notes: Sequence[Note]) -> list[Note]:
    return sorted(notes, key=lambda n: (-n.meta.first_seen.toordinal(), n.meta.title))


def _link(note: Note) -> str:
    # Index pages live in `notes/`, next to the per-kind folders.
    target = note.path.relative_to(PurePosixPath("notes"))
    return f"[{table_cell(note.meta.title)}]({target})"


def notes_index(kind: NoteKind, notes: Sequence[Note], labels: Mapping[ThemeId, str]) -> str:
    """Build the page listing the notes of one kind (`notes/<kind>s.md`).

    Args:
        kind: The kind listed.
        notes: Every note; only those of `kind` are listed.
        labels: Theme labels by id; an unknown theme shows its id.

    Returns:
        The page: a table, newest first.
    """
    rows = [
        f"| {_link(n)} | {table_cell(', '.join(labels.get(t, t) for t in n.meta.themes))} "
        f"| {DEPTH_LABELS[n.meta.depth]} | {n.meta.first_seen.isoformat()} |"
        for n in _newest_first([n for n in notes if n.meta.kind == kind])
    ]
    if not rows:
        return f"# {KIND_TITLES[kind]}\n\n{NO_NOTE}\n"
    table = "\n".join(["| Fiche | Thèmes | Profondeur | Vue le |", "|---|---|---|---|", *rows])
    return f"# {KIND_TITLES[kind]}\n\n{table}\n"


def notes_by_theme(notes: Sequence[Note], profile: Profile) -> str:
    """Build the page listing the notes of each theme (`notes/by-theme.md`).

    Args:
        notes: Every note.
        profile: The interest profile: its themes come first, in order.

    Returns:
        The page: the profile's themes, then the themes it no longer has.
    """
    known = [(ThemeId(t.id), t.label) for t in profile.themes]
    ids = {theme for theme, _ in known}
    unknown = sorted({t for n in notes for t in n.meta.themes if t not in ids})
    sections: list[str] = []
    for theme, label in [*known, *((t, t) for t in unknown)]:
        listed = _newest_first([n for n in notes if theme in n.meta.themes])
        body = "\n".join(f"- {_link(n)}" for n in listed) if listed else NO_NOTE
        sections.append(f"## {label}\n\n{body}\n")
    return "# Fiches par thème\n\n" + "\n".join(sections)


def home(
    title: str,
    profile: Profile,
    themes: Mapping[ThemeId, ThemePage],
    *,
    latest_digest: str | None,
    latest_changelog: str | None,
) -> str:
    """Build the home page (`index.md`).

    Args:
        title: Title of the site.
        profile: The interest profile, for theme order and labels.
        themes: The theme pages that exist, by theme.
        latest_digest: Week of the latest archived digest, if any.
        latest_changelog: Week of the latest changelog, if any.

    Returns:
        The page.
    """
    parts = [f"# {title}\n"]
    week = [
        *(
            [f"- [Digest de la semaine {latest_digest}](digests/{latest_digest}.md)"]
            if latest_digest
            else []
        ),
        *(
            [f"- [Journal de la base {latest_changelog}](changelog/{latest_changelog}.md)"]
            if latest_changelog
            else []
        ),
    ]
    if week:
        parts.append("## Cette semaine\n\n" + "\n".join(week) + "\n")
    with_page = [
        f"- [{t.label}](themes/{t.id}.md) — mis à jour le "
        f"{themes[ThemeId(t.id)].meta.updated_at.isoformat()}"
        for t in profile.themes
        if ThemeId(t.id) in themes
    ]
    parts.append(
        "## Thèmes\n\n"
        + ("\n".join(with_page) if with_page else "Aucune page thème pour l'instant.")
        + "\n"
    )
    without = [f"- {t.label}" for t in profile.themes if ThemeId(t.id) not in themes]
    if without:
        parts.append("## Thèmes sans page pour l'instant\n\n" + "\n".join(without) + "\n")
    return "\n".join(parts)


def weeks_index(title: str, weeks: Sequence[str]) -> str:
    """Build the list of weekly pages of a folder (journal or digests).

    Args:
        title: Title of the page.
        weeks: ISO weeks that have a page in the same folder.

    Returns:
        The page, newest week first.
    """
    if not weeks:
        return f"# {title}\n\nRien pour l'instant.\n"
    lines = "\n".join(f"- [{w}]({w}.md)" for w in sorted(weeks, reverse=True))
    return f"# {title}\n\n{lines}\n"
