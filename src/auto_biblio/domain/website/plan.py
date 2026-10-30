"""The whole site: every page and the navigation, from `kb/` files and archived digests."""

from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.kb.notes import Note, NoteKind
from auto_biblio.domain.kb.pages import ThemePage
from auto_biblio.domain.website.indexes import (
    KIND_TITLES,
    home,
    notes_by_theme,
    notes_index,
    weeks_index,
)
from auto_biblio.domain.website.nav import NavEntry
from auto_biblio.domain.website.pages import note_page, theme_page
from auto_biblio.domain.website.wiki import has_pages, notion_links, wiki_section
from auto_biblio.domain.wiki.links import WikiLinks
from auto_biblio.domain.wiki.pages import load_wiki
from auto_biblio.repo_config.profile import Profile

KINDS: tuple[NoteKind, ...] = ("paper", "tool", "post")
WIKI = PurePosixPath("wiki")

__all__ = ["NavEntry", "SiteInputs", "SitePlan", "plan_site"]


class SiteInputs(BaseModel):
    """Everything the site is made of."""

    model_config = ConfigDict(frozen=True)

    title: str
    profile: Profile
    kb_files: dict[PurePosixPath, str]
    """Contents of `notes/*/*.md`, `themes/*.md` and `changelog/*.md`, relative to `kb/`."""
    digests: dict[str, str]
    """Archived digests: ISO week to Markdown page."""
    wiki_files: dict[PurePosixPath, str] = {}
    """Markdown files of `wiki/`, relative to it."""
    wiki_assets: dict[PurePosixPath, bytes] = {}
    """Figures and notebooks of `wiki/`, relative to it."""
    wiki_links: WikiLinks = WikiLinks()


class SitePlan(BaseModel):
    """The pages of the site, its navigation and what could not be read."""

    model_config = ConfigDict(frozen=True)

    pages: dict[PurePosixPath, str]
    """Markdown pages, relative to the site's sources."""
    nav: tuple[NavEntry, ...]
    warnings: tuple[str, ...] = ()
    assets: dict[PurePosixPath, bytes] = {}
    """Binary files (figures, notebooks), relative to the site's sources."""


def plan_site(inputs: SiteInputs) -> SitePlan:
    """Lay out the site.

    Args:
        inputs: The knowledge base files, the archived digests and the profile.

    Returns:
        Every page and the navigation. Unreadable files are published as they are and
        reported in `warnings`.
    """
    labels = {ThemeId(t.id): t.label for t in inputs.profile.themes}
    wiki = load_wiki(inputs.wiki_files, inputs.wiki_assets)
    notions = notion_links(wiki, inputs.wiki_links) if has_pages(wiki) else {}
    pages: dict[PurePosixPath, str] = {}
    notes: list[Note] = []
    themes: dict[ThemeId, ThemePage] = {}
    changelogs: list[str] = []
    warnings: list[str] = []
    for path, text in sorted(inputs.kb_files.items()):
        origin = path.as_posix()
        folder = path.parts[0]
        if folder == "changelog":
            pages[path] = text
            changelogs.append(path.stem)
            continue
        if folder == "notes":
            pages[path], note = note_page(text, origin, labels)
            if note is not None and note.meta.id in notions:
                # The note id is only known once the file is parsed.
                pages[path], _ = note_page(text, origin, labels, notions[note.meta.id])
            readable = note is not None
            notes.extend([note] if note is not None else [])
        else:
            pages[path], page = theme_page(text, origin)
            readable = page is not None
            themes.update({page.meta.theme: page} if page is not None else {})
        if not readable:
            warnings.append(f"unreadable {origin}")
    for week, text in inputs.digests.items():
        pages[PurePosixPath("digests", f"{week}.md")] = text
    for kind in KINDS:
        pages[PurePosixPath("notes", f"{kind}s.md")] = notes_index(kind, notes, labels)
    pages[PurePosixPath("notes/by-theme.md")] = notes_by_theme(notes, inputs.profile)
    pages[PurePosixPath("changelog/index.md")] = weeks_index("Journal", changelogs)
    pages[PurePosixPath("digests/index.md")] = weeks_index("Digests", tuple(inputs.digests))
    wiki_pages, wiki_nav, wiki_warnings = wiki_section(
        inputs.wiki_files, wiki, inputs.wiki_links, {n.meta.id: n for n in notes}
    )
    pages.update(wiki_pages)
    warnings.extend(wiki_warnings)
    pages[PurePosixPath("index.md")] = home(
        inputs.title,
        inputs.profile,
        themes,
        latest_digest=max(inputs.digests, default=None),
        latest_changelog=max(changelogs, default=None),
    )
    return SitePlan(
        pages=pages,
        nav=_nav(inputs.profile, themes, wiki_nav),
        warnings=tuple(warnings),
        assets={WIKI / path: data for path, data in inputs.wiki_assets.items()} if wiki_nav else {},
    )


def _nav(
    profile: Profile, themes: dict[ThemeId, ThemePage], wiki: NavEntry | None
) -> tuple[NavEntry, ...]:
    theme_entries = tuple(
        NavEntry(title=t.label, path=f"themes/{t.id}.md")
        for t in profile.themes
        if ThemeId(t.id) in themes
    )
    note_entries = (
        *(NavEntry(title=KIND_TITLES[k], path=f"notes/{k}s.md") for k in KINDS),
        NavEntry(title="Par thème", path="notes/by-theme.md"),
    )
    return (
        NavEntry(title="Accueil", path="index.md"),
        *((NavEntry(title="Thèmes", children=theme_entries),) if theme_entries else ()),
        *((wiki,) if wiki else ()),
        NavEntry(title="Fiches", children=note_entries),
        NavEntry(title="Journal", path="changelog/index.md"),
        NavEntry(title="Digests", path="digests/index.md"),
    )
