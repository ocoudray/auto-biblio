from datetime import date
from pathlib import PurePosixPath

from builders import make_note

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.notes import Note
from auto_biblio.domain.website.plan import NavEntry
from auto_biblio.domain.website.wiki import notion_links, wiki_section
from auto_biblio.domain.wiki.links import Candidate, NoteLinks, WikiLinks
from auto_biblio.domain.wiki.pages import load_wiki

P = PurePosixPath
ORDER = "[llm/embeddings, llm/attention, llm/transformer]"
INDEX = f"---\ntitle: LLM fondamentaux\norder: {ORDER}\n---\n\nIntro.\n"
ATTENTION = """---
title: Attention
prerequisites: [llm/embeddings, llm/transformer]
updated_at: 2026-10-20
---

# Attention

Résumé <b>.

## Références fondatrices

- Ref.

## Mes notes

Mine.
"""
EMBEDDINGS = "---\ntitle: Embeddings\nupdated_at: 2026-10-20\n---\n\n# Embeddings\n\nR.\n"
FILES = {
    P("llm/index.md"): INDEX,
    P("llm/attention.md"): ATTENTION,
    P("llm/embeddings.md"): EMBEDDINGS,
}


def note(note_id: str, seen: date) -> Note:
    base = make_note(note_id)
    return base.model_copy(update={"meta": base.meta.model_copy(update={"first_seen": seen})})


NOTES = {
    ItemId("a:1"): note("a:1", date(2026, 9, 1)),
    ItemId("a:2"): note("a:2", date(2026, 10, 1)),
}
LINKS = WikiLinks(
    notes={
        ItemId("a:1"): NoteLinks(notions=("llm/attention",), signature="s"),
        ItemId("a:2"): NoteLinks(notions=("llm/attention", "llm/gone"), signature="s"),
        ItemId("a:9"): NoteLinks(notions=("llm/attention",), signature="s"),
    },
    candidates={
        "kv cache": Candidate(
            name="KV cache",
            notes=(ItemId("a:1"), ItemId("a:2")),
            first_seen=date(2026, 9, 1),
            last_seen=date(2026, 10, 1),
        ),
        "rope": Candidate(
            name="RoPE",
            notes=(ItemId("a:9"),),
            first_seen=date(2026, 9, 1),
            last_seen=date(2026, 9, 1),
        ),
    },
)


def section() -> tuple[dict[PurePosixPath, str], NavEntry | None, tuple[str, ...]]:
    return wiki_section(FILES, load_wiki(FILES, []), LINKS, NOTES)


def test_notion_page() -> None:
    page = section()[0][P("wiki/llm/attention.md")]
    lines = page.splitlines()
    assert (
        lines[lines.index("# Attention") + 2]
        == "> Prérequis : [Embeddings](embeddings.md) · llm/transformer"
    )
    assert "&lt;b>" in page
    news = page.index("## Nouveautés suivies")
    assert news < page.index("## Mes notes")
    assert page.index("Title a:2") < page.index("Title a:1")  # newest first
    assert "(../../notes/papers/a-2.md)" in page
    assert "a:9" not in page  # note no longer in the base


def test_domain_index() -> None:
    page = section()[0][P("wiki/llm/index.md")]
    assert page.startswith("# LLM fondamentaux\n")
    assert "1. [Embeddings](embeddings.md)" in page
    assert "2. [Attention](attention.md)" in page
    assert "3. llm/transformer — *à rédiger*" in page


def test_candidates_page() -> None:
    page = section()[0][P("wiki/candidates.md")]
    rows = [line for line in page.splitlines() if line.startswith(("| KV", "| RoPE"))]
    assert rows[0].startswith("| KV cache | 2 | 2026-10-01 |")
    assert "[Title a:1](../notes/papers/a-1.md)" in rows[0]
    assert rows[1] == "| RoPE | 1 | 2026-09-01 |  |"


def test_navigation() -> None:
    nav = section()[1]
    assert nav == NavEntry(
        title="Wiki",
        children=(
            NavEntry(
                title="LLM fondamentaux",
                children=(
                    NavEntry(title="Présentation", path="wiki/llm/index.md"),
                    NavEntry(title="Embeddings", path="wiki/llm/embeddings.md"),
                    NavEntry(title="Attention", path="wiki/llm/attention.md"),
                ),
            ),
            NavEntry(title="Notions à couvrir", path="wiki/candidates.md"),
        ),
    )


def test_unreadable_page_is_published_with_a_warning() -> None:
    files = {**FILES, P("llm/broken.md"): "---\ntitle: Bad: yaml\n---\n\noops <script>\n````\n"}
    pages, _, warnings = wiki_section(files, load_wiki(files, []), LINKS, NOTES)
    page = pages[P("wiki/llm/broken.md")]
    # The site generator parses a front-matter: an invalid one must not reach it.
    assert page.startswith("# wiki/llm/broken.md\n")
    assert "\n`````text\n---\ntitle: Bad: yaml\n" in page
    assert page.endswith("\n`````\n")
    assert warnings == ("unreadable wiki/llm/broken.md",)


def test_unreadable_index_keeps_the_domain() -> None:
    files = {**FILES, P("llm/index.md"): "---\ntitle: LLM\nextra: 1\n---\n"}
    pages, nav, warnings = wiki_section(files, load_wiki(files, []), LINKS, NOTES)
    assert P("wiki/llm/attention.md") in pages
    assert P("wiki/llm/index.md") in pages
    assert warnings == ("unreadable wiki/llm/index.md",)
    assert nav is not None
    domain = nav.children[0]
    assert domain.title == "llm"
    assert [c.title for c in domain.children] == ["Attention", "Embeddings"]
    assert notion_links(load_wiki(files, []), LINKS)[ItemId("a:1")]


def test_code_is_not_escaped() -> None:
    body = "`List<int>` and <b>\n\n```mermaid\nA <--> B\n```\n\n~~~\nif a < b: pass\n~~~\n"
    files = {**FILES, P("llm/embeddings.md"): EMBEDDINGS + body}
    page = wiki_section(files, load_wiki(files, []), LINKS, NOTES)[0][P("wiki/llm/embeddings.md")]
    assert "`List<int>` and &lt;b>" in page
    assert "A <--> B" in page
    assert "if a < b: pass" in page


def test_no_domain_no_section() -> None:
    assert wiki_section({}, load_wiki({}, []), WikiLinks(), {}) == ({}, None, ())


def test_notion_links_of_notes() -> None:
    links = notion_links(load_wiki(FILES, []), LINKS)
    assert links[ItemId("a:2")] == (
        ("Attention", "../../wiki/llm/attention.md"),
    )  # llm/gone ignored
