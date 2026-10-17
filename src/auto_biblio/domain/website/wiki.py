"""The wiki on the site: notion pages, domain indexes, candidates and navigation."""

from collections.abc import Mapping
from pathlib import PurePosixPath

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.notes import Note
from auto_biblio.domain.website.nav import NavEntry
from auto_biblio.domain.website.pages import under_title
from auto_biblio.domain.website.text import (
    as_code_block,
    escape_html,
    escape_outside_code,
    link_text,
)
from auto_biblio.domain.wiki.links import WikiLinks
from auto_biblio.domain.wiki.pages import Domain, Notion, Wiki

WIKI = PurePosixPath("wiki")
CANDIDATES = WIKI / "candidates.md"
MY_NOTES = "## Mes notes"
EXAMPLES = 3
"""Notes shown for each candidate notion."""

WikiSection = tuple[dict[PurePosixPath, str], NavEntry | None, tuple[str, ...]]


def wiki_section(
    files: Mapping[PurePosixPath, str],
    wiki: Wiki,
    links: WikiLinks,
    notes: Mapping[ItemId, Note],
) -> WikiSection:
    """Lay out the wiki part of the site.

    Args:
        files: The wiki files, relative to `wiki/`; unreadable pages are published from them.
        wiki: The wiki, read from `files`.
        links: Links from notes to notions, and the candidate notions.
        notes: The notes of the knowledge base; links to other notes are ignored.

    Returns:
        The pages (under `wiki/`), the navigation entry and the warnings; nothing when the
        wiki has no page.
    """
    if not has_pages(wiki):
        return {}, None, ()
    pages = {
        WIKI / f"{n.id}.md": _notion_page(n, wiki, links, notes) for n in wiki.notions.values()
    }
    pages.update({WIKI / d.id / "index.md": _domain_page(d, wiki) for d in wiki.domains.values()})
    pages[CANDIDATES] = _candidates_page(links, notes)
    for path, reason in wiki.unreadable.items():
        pages[WIKI / path] = _unreadable_page(WIKI / path, reason, files[path])
    warnings = tuple(f"unreadable {(WIKI / path).as_posix()}" for path in sorted(wiki.unreadable))
    return pages, _nav(wiki), warnings


def has_pages(wiki: Wiki) -> bool:
    """Whether the wiki has anything to publish.

    Args:
        wiki: The wiki.

    Returns:
        True when it has a domain, a notion or an unreadable page.
    """
    return bool(wiki.domains or wiki.notions or wiki.unreadable)


def notion_links(wiki: Wiki, links: WikiLinks) -> dict[ItemId, tuple[tuple[str, str], ...]]:
    """List the notions each note links to, as seen from the note's page.

    Args:
        wiki: The wiki; links to notions it has no page for are ignored.
        links: Links from notes to notions.

    Returns:
        (title, path relative to `notes/<kind>s/`) pairs, by note.
    """
    found = {
        note_id: tuple(
            (wiki.notions[n].title, f"../../{WIKI / n}.md")
            for n in note.notions
            if n in wiki.notions
        )
        for note_id, note in links.notes.items()
    }
    return {note_id: pairs for note_id, pairs in found.items() if pairs}


def _href(source: str, target: str) -> str:
    # Notion pages and domain indexes both live in `wiki/<domain>/`.
    domain, name = target.split("/")
    return f"{name}.md" if source == domain else f"../{domain}/{name}.md"


def _notion_page(notion: Notion, wiki: Wiki, links: WikiLinks, notes: Mapping[ItemId, Note]) -> str:
    domain = notion.id.split("/")[0]
    page = escape_outside_code(notion.body.strip("\n")) + "\n"
    if notion.meta.prerequisites:
        parts = [
            f"[{link_text(wiki.notions[p].title)}]({_href(domain, p)})" if p in wiki.notions else p
            for p in notion.meta.prerequisites
        ]
        page = under_title(page, "> Prérequis : " + " · ".join(parts))
    linked = [
        notes[note_id]
        for note_id, note_links in links.notes.items()
        if notion.id in note_links.notions and note_id in notes
    ]
    if not linked:
        return page
    items = "\n".join(
        f"- [{link_text(n.meta.title)}](../../{n.path}) — vue le {n.meta.first_seen.isoformat()}"
        for n in sorted(linked, key=lambda n: (-n.meta.first_seen.toordinal(), n.meta.title))
    )
    news = f"## Nouveautés suivies\n\n{items}\n"
    if MY_NOTES not in page.split("\n"):
        return f"{page}\n{news}"
    before, _, after = page.partition(f"\n{MY_NOTES}\n")
    return f"{before}\n{news}\n{MY_NOTES}\n{after}"


def _domain_page(domain: Domain, wiki: Wiki) -> str:
    entries = "\n".join(
        f"{i}. [{link_text(wiki.notions[n].title)}]({_href(domain.id, n)})"
        if n in wiki.notions
        else f"{i}. {n} — *à rédiger*"
        for i, n in enumerate(domain.index.order, start=1)
    )
    intro = escape_outside_code(domain.intro.strip())
    return f"# {link_text(domain.index.title)}\n\n{intro}\n\n## Ordre de lecture\n\n{entries}\n"


def _unreadable_page(path: PurePosixPath, reason: str, text: str) -> str:
    # Shown verbatim: the site generator would choke on the invalid front-matter otherwise.
    why = escape_html(" ".join(reason.split()))
    return f"# {path.as_posix()}\n\n> Page illisible : {why}\n\n{as_code_block(text)}"


def _candidates_page(links: WikiLinks, notes: Mapping[ItemId, Note]) -> str:
    title = "# Notions à couvrir\n\nNotions citées par les fiches et absentes du wiki.\n"
    candidates = sorted(links.candidates.values(), key=lambda c: (-c.count, c.name.lower()))
    if not candidates:
        return f"{title}\nAucune notion en attente.\n"
    rows: list[str] = []
    for c in candidates:
        examples = [notes[i] for i in c.notes if i in notes][:EXAMPLES]
        cells = ", ".join(f"[{link_text(n.meta.title)}](../{n.path})" for n in examples)
        rows.append(f"| {link_text(c.name)} | {c.count} | {c.last_seen.isoformat()} | {cells} |")
    table = "\n".join(["| Notion | Fiches | Dernière vue | Exemples |", "|---|---|---|---|", *rows])
    return f"{title}\n{table}\n"


def _nav(wiki: Wiki) -> NavEntry:
    domains: list[NavEntry] = []
    ids = set(wiki.domains) | {n.split("/")[0] for n in wiki.notions}
    for domain_id in ids:
        domain = wiki.domains.get(domain_id)
        # A domain whose index.md is unreadable keeps its notions, in identifier order.
        order = domain.index.order if domain else ()
        ordered = [n for n in order if n in wiki.notions]
        rest = sorted(n for n in wiki.notions if n.split("/")[0] == domain_id and n not in ordered)
        children = (
            *(
                [NavEntry(title="Présentation", path=f"wiki/{domain_id}/index.md")]
                if domain
                else []
            ),
            *(
                NavEntry(title=wiki.notions[n].title, path=f"wiki/{n}.md")
                for n in [*ordered, *rest]
            ),
        )
        title = domain.index.title if domain else domain_id
        domains.append(NavEntry(title=title, children=children))
    domains.sort(key=lambda entry: entry.title)
    candidates = NavEntry(title="Notions à couvrir", path=CANDIDATES.as_posix())
    return NavEntry(title="Wiki", children=(*domains, candidates))
