"""Show how the same paper seen on three sources collapses into one item.

Run with `uv run python examples/dedup.py` (no network needed).
"""

from datetime import UTC, datetime
from functools import reduce

from auto_biblio.domain.ids import canonical_id
from auto_biblio.domain.merge import merge_items
from auto_biblio.domain.models import Item, Sighting, SourceType

SEEN_AT = datetime(2026, 10, 10, 5, 0, tzinfo=UTC)


def observed(url: str, source: str, source_type: SourceType) -> Item:
    """Build the item a source would produce for `url`."""
    return Item.model_validate(
        {
            "id": canonical_id(url),
            "kind": "paper",
            "title": "Linear-Time Sequence Modeling",
            "summary": None,
            "url": url,
            "authors": (),
            "published_at": None,
            "first_seen": SEEN_AT,
            "sightings": (
                Sighting(source=source, source_type=source_type, seen_at=SEEN_AT, origin_url=url),
            ),
        }
    )


def main() -> None:
    """Merge three observations of one arXiv paper and print the result."""
    observations = [
        observed("https://arxiv.org/abs/2410.12345v2", "arxiv", "arxiv"),
        observed("https://huggingface.co/papers/2410.12345", "hf-papers", "hf_papers"),
        observed("https://arxiv.org/pdf/2410.12345v3", "hn", "hackernews"),
    ]
    item = reduce(merge_items, observations)
    sources = ", ".join(s.source for s in item.sightings)
    print(f"{item.id} — {len(item.sightings)} sightings ({sources})")


if __name__ == "__main__":
    main()
