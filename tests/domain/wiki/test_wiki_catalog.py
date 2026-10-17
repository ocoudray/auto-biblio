from pathlib import PurePosixPath

from auto_biblio.domain.wiki.catalog import CatalogEntry, alias_index, catalog, normalize, signature
from auto_biblio.domain.wiki.pages import load_wiki


def page(title: str, aliases: str = "[]") -> str:
    return (
        f"---\ntitle: {title}\naliases: {aliases}\nupdated_at: 2026-10-20\n---\n\n# {title}\n\nR.\n"
    )


def test_catalog_sorted_by_id() -> None:
    wiki = load_wiki(
        {
            PurePosixPath("llm/transformer.md"): page("Transformer"),
            PurePosixPath("llm/attention.md"): page("Attention", "[self-attention]"),
        },
        [],
    )
    assert catalog(wiki) == (
        CatalogEntry(id="llm/attention", title="Attention", aliases=("self-attention",)),
        CatalogEntry(id="llm/transformer", title="Transformer", aliases=()),
    )


def test_signature_ignores_order() -> None:
    a = CatalogEntry(id="llm/a", title="A", aliases=())
    b = CatalogEntry(id="llm/b", title="B", aliases=("bee",))
    assert signature((a, b)) == signature((b, a))
    assert signature((a,)) != signature((a, b))
    assert len(signature(())) == 64


def test_normalize() -> None:
    assert normalize("Multi-Head_Attention ") == "multi head attention"
    assert normalize("  KV   cache") == "kv cache"


def test_alias_index() -> None:
    entry = CatalogEntry(
        id="llm/multi-head-attention", title="Multi-head attention", aliases=("MHA",)
    )
    index = alias_index((entry,))
    assert index["multi head attention"] == "llm/multi-head-attention"
    assert index["mha"] == "llm/multi-head-attention"
    assert index["llm/multi head attention"] == "llm/multi-head-attention"
