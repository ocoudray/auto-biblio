from datetime import date

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.wiki.catalog import CatalogEntry
from auto_biblio.domain.wiki.links import (
    Candidate,
    LinkResult,
    NoteLinks,
    WikiLinks,
    merge_links,
    stale_notes,
)

ATTENTION = CatalogEntry(id="llm/attention", title="Attention", aliases=("self-attention",))
TODAY = date(2026, 10, 20)
A, B, C = ItemId("a:1"), ItemId("a:2"), ItemId("a:3")


def merge(
    links: WikiLinks,
    results: dict[ItemId, LinkResult],
    *,
    entries: tuple[CatalogEntry, ...] = (ATTENTION,),
    existing: frozenset[ItemId] = frozenset({A, B, C}),
    today: date = TODAY,
) -> WikiLinks:
    return merge_links(links, results, entries=entries, sig="s1", existing=existing, today=today)


def test_stale_notes() -> None:
    links = WikiLinks(
        notes={A: NoteLinks(notions=(), signature="s1"), B: NoteLinks(notions=(), signature="old")}
    )
    assert stale_notes([A, B, C], links, "s1") == [B, C]


def test_merge_records_notions_and_candidates() -> None:
    merged = merge(
        WikiLinks(),
        {
            A: LinkResult(notions=("llm/attention", "llm/attention"), missing=("KV cache",)),
            B: LinkResult(notions=(), missing=("kv-cache", "Self-Attention")),
        },
    )
    assert merged.notes[A] == NoteLinks(notions=("llm/attention",), signature="s1")
    assert merged.notes[B] == NoteLinks(notions=("llm/attention",), signature="s1")  # alias → link
    assert merged.candidates == {
        "kv cache": Candidate(name="KV cache", notes=(A, B), first_seen=TODAY, last_seen=TODAY)
    }
    assert merged.candidates["kv cache"].count == 2


def test_candidate_counted_once_per_note_on_retag() -> None:
    first = merge(WikiLinks(), {A: LinkResult(notions=(), missing=("KV cache",))})
    later = date(2026, 10, 27)
    again = merge(first, {A: LinkResult(notions=(), missing=("KV cache",))}, today=later)
    assert again.candidates["kv cache"] == Candidate(
        name="KV cache", notes=(A,), first_seen=TODAY, last_seen=later
    )


def test_retag_removes_a_dropped_candidate() -> None:
    first = merge(WikiLinks(), {A: LinkResult(notions=(), missing=("KV cache",))})
    assert merge(first, {A: LinkResult(notions=(), missing=())}).candidates == {}


def test_candidate_that_became_a_notion_is_dropped_without_retag() -> None:
    first = merge(WikiLinks(), {A: LinkResult(notions=(), missing=("KV cache",))})
    kv = CatalogEntry(id="llm/kv-cache", title="KV cache", aliases=())
    assert merge(first, {}, entries=(ATTENTION, kv)).candidates == {}


def test_removed_note_is_dropped() -> None:
    first = merge(WikiLinks(), {A: LinkResult(notions=("llm/attention",), missing=("KV cache",))})
    merged = merge(first, {}, existing=frozenset({B}))
    assert merged.notes == {}
    assert merged.candidates == {}
