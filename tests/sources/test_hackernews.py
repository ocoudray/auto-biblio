from datetime import UTC, datetime
from pathlib import Path

import httpx
from builders import NOW

from auto_biblio.repo_config.sources import HackernewsSourceConfig
from auto_biblio.sources._http import Throttle
from auto_biblio.sources.hackernews import HackernewsSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "hackernews"
SINCE = datetime(2026, 10, 9, tzinfo=UTC)


def make_source(requests: list[httpx.Request] | None = None) -> HackernewsSource:
    body = (FIXTURES / "stories.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, content=body)

    config = HackernewsSourceConfig(name="hn", type="hackernews")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HackernewsSource(config, client, lambda: NOW, Throttle(0))


def test_hn_query() -> None:
    requests: list[httpx.Request] = []
    make_source(requests).fetch(SINCE)
    params = requests[0].url.params
    assert requests[0].url.host == "hn.algolia.com"
    assert requests[0].url.path == "/api/v1/search_by_date"
    assert params["tags"] == "story"
    assert params["numericFilters"] == f"created_at_i>{int(SINCE.timestamp())},points>30"
    assert params["hitsPerPage"] == "1000"


def test_hn_story_url_canonicalized() -> None:
    item = make_source().fetch(SINCE).items[0]
    assert item.id == "arxiv:2410.12345"
    assert item.kind == "paper"
    assert item.sightings[0].origin_url == "https://news.ycombinator.com/item?id=50029982"
    assert item.sightings[0].source_type == "hackernews"
    assert item.authors == ()


def test_hn_story_without_url_is_discussion() -> None:
    item = make_source().fetch(SINCE).items[1]
    assert item.kind == "discussion"
    assert str(item.url) == "https://news.ycombinator.com/item?id=50029630"
    assert item.id.startswith("url:")


def test_hn_other_links_are_blog_posts() -> None:
    assert make_source().fetch(SINCE).items[2].kind == "blog_post"


def test_hn_signals() -> None:
    signals = make_source().fetch(SINCE).signals
    assert [(s.item_id, s.kind, s.value) for s in signals[:2]] == [
        ("arxiv:2410.12345", "hn_points", 71),
        ("arxiv:2410.12345", "hn_comments", 51),
    ]
    assert len(signals) == 6
