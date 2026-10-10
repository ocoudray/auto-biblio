from datetime import UTC, datetime
from pathlib import Path

import httpx
from builders import NOW

from auto_biblio.repo_config.sources import RssSourceConfig
from auto_biblio.sources._http import Throttle
from auto_biblio.sources.rss import RssSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "rss"


def make_source(fixture: str, name: str = "hf-blog") -> RssSource:
    body = (FIXTURES / fixture).read_bytes()
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    config = RssSourceConfig(
        name=name,
        type="rss",
        url="https://huggingface.co/blog/feed.xml",  # pyright: ignore[reportArgumentType]
        family="applied",
    )
    return RssSource(config, client, lambda: NOW, Throttle(0))


def test_rss_name() -> None:
    assert make_source("rss2_sample.xml").name == "hf-blog"


def test_entry_without_date_is_kept() -> None:
    batch = make_source("rss2_sample.xml").fetch(datetime(2026, 10, 1, tzinfo=UTC))
    assert len(batch.items) == 3


def test_rss_filters_by_since() -> None:
    batch = make_source("rss2_sample.xml").fetch(datetime(2026, 10, 9, tzinfo=UTC))
    titles = [i.title for i in batch.items]
    assert "Multimodal open d1 decision models for the edge" not in titles
    assert len(titles) == 2


def test_rss_item_kind_from_link() -> None:
    items = make_source("rss2_sample.xml").fetch(datetime(2026, 10, 1, tzinfo=UTC)).items
    assert (items[0].id, items[0].kind) == ("arxiv:2410.12345", "paper")
    assert {i.kind for i in items[1:]} == {"blog_post"}


def test_rss_sighting() -> None:
    item = make_source("atom_sample.xml", name="simon").fetch(NOW.replace(day=1)).items[0]
    (sighting,) = item.sightings
    assert sighting.source == "simon"
    assert sighting.source_type == "rss"
    assert sighting.seen_at == NOW
    assert sighting.origin_url == "https://simonwillison.net/2026/Oct/10/the-new-york-times/"
    assert item.first_seen == NOW
    assert batch_signals_empty()


def batch_signals_empty() -> bool:
    return make_source("atom_sample.xml").fetch(NOW).signals == ()


def test_relative_links_resolved_against_feed_url() -> None:
    body = (
        b"<rss version='2.0'><channel><title>t</title><item><title>Post</title>"
        b"<link>/blog/post-1</link></item></channel></rss>"
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    config = RssSourceConfig(
        name="rel",
        type="rss",
        url="https://example.com/feed.xml",  # pyright: ignore[reportArgumentType]
        family="applied",
    )
    (item,) = RssSource(config, client, lambda: NOW, Throttle(0)).fetch(NOW).items
    assert str(item.url) == "https://example.com/blog/post-1"
