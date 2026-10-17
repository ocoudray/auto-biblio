from datetime import date
from pathlib import PurePosixPath

import pytest

from auto_biblio.domain.errors import WikiFormatError
from auto_biblio.domain.wiki.pages import load_wiki, parse_domain, parse_notion

NOTION = """---
title: Mécanisme d'attention
aliases: [attention, self-attention]
prerequisites: [llm/embeddings]
related: [llm/transformer]
themes: [agentic]
updated_at: 2026-10-20
---

# Mécanisme d'attention

L'attention pondère les positions d'une séquence.

## Intuition

Texte.

## Références fondatrices

- Vaswani et al., 2017.
"""
INDEX = """---
title: LLM fondamentaux
order: [llm/embeddings, llm/attention]
---

Présentation du domaine.
"""


def test_parse_notion() -> None:
    notion = parse_notion(NOTION, "llm/attention", "llm/attention.md")
    assert notion.id == "llm/attention"
    assert notion.title == "Mécanisme d'attention"
    assert notion.summary == "L'attention pondère les positions d'une séquence."
    assert notion.headings == ("Intuition", "Références fondatrices")
    assert notion.meta.prerequisites == ("llm/embeddings",)
    assert notion.meta.updated_at == date(2026, 10, 20)
    assert notion.body.startswith("\n# Mécanisme")


def test_unknown_key_is_rejected() -> None:
    text = NOTION.replace("themes: [agentic]", "themes: [agentic]\nauthor: me")
    with pytest.raises(WikiFormatError, match=r"llm/attention\.md"):
        parse_notion(text, "llm/attention", "llm/attention.md")


def test_invalid_notion_id_is_rejected() -> None:
    text = NOTION.replace("[llm/embeddings]", "[Attention]")
    with pytest.raises(WikiFormatError):
        parse_notion(text, "llm/attention", "llm/attention.md")


def test_notion_needs_a_title_line() -> None:
    with pytest.raises(WikiFormatError, match="title"):
        parse_notion(NOTION.replace("# Mécanisme d'attention", "Mécanisme"), "llm/a", "a.md")


def test_parse_domain() -> None:
    domain = parse_domain(INDEX, "llm", "llm/index.md")
    assert domain.index.order == ("llm/embeddings", "llm/attention")
    assert domain.intro.strip() == "Présentation du domaine."


def test_load_wiki() -> None:
    files = {
        PurePosixPath("GUIDE.md"): "# Guide\n",
        PurePosixPath("llm/index.md"): INDEX,
        PurePosixPath("llm/attention.md"): NOTION,
        PurePosixPath("llm/broken.md"): "no front matter",
        PurePosixPath("llm/img/notes.md"): "ignored",
    }
    wiki = load_wiki(files, [PurePosixPath("llm/img/a.svg")])
    assert set(wiki.domains) == {"llm"}
    assert set(wiki.notions) == {"llm/attention"}
    assert set(wiki.unreadable) == {PurePosixPath("llm/broken.md")}
    assert wiki.assets == frozenset({PurePosixPath("llm/img/a.svg")})
