from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from builders import NOW

from auto_biblio.domain.errors import SourceUnavailableError
from auto_biblio.repo_config.sources import ArxivSourceConfig
from auto_biblio.sources._http import Throttle
from auto_biblio.sources.arxiv import ArxivSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "arxiv"
SINCE = datetime(2026, 10, 1, tzinfo=UTC)


class Recorder:
    def __init__(self, *pages: str) -> None:
        self.pages = list(pages)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        page = self.pages.pop(0) if self.pages else "empty.xml"
        return httpx.Response(200, content=(FIXTURES / page).read_bytes())


class CountingThrottle(Throttle):
    def __init__(self) -> None:
        super().__init__(0)
        self.calls = 0

    def wait(self) -> None:
        self.calls += 1


def make_source(
    recorder: Recorder, *, max_results: int = 2000, throttle: Throttle | None = None
) -> ArxivSource:
    config = ArxivSourceConfig(
        name="arxiv", type="arxiv", categories=("cs.CL", "cs.LG"), max_results=max_results
    )
    client = httpx.Client(transport=httpx.MockTransport(recorder))
    return ArxivSource(config, client, lambda: NOW, throttle or Throttle(0))


def test_query_params() -> None:
    recorder = Recorder("empty.xml")
    make_source(recorder).fetch(SINCE)
    params = recorder.requests[0].url.params
    assert recorder.requests[0].url.host == "export.arxiv.org"
    assert params["search_query"] == "cat:cs.CL OR cat:cs.LG"
    assert params["sortBy"] == "submittedDate"
    assert params["sortOrder"] == "descending"
    assert params["start"] == "0"
    assert params["max_results"] == "100"


def test_paginates_until_older_than_since() -> None:
    recorder = Recorder("page1.xml", "page2.xml", "page1.xml")
    batch = make_source(recorder).fetch(SINCE)
    assert len(recorder.requests) == 2
    assert recorder.requests[1].url.params["start"] == "3"
    assert [i.id for i in batch.items] == [
        "arxiv:2610.12427",
        "arxiv:2610.12417",
        "arxiv:2610.12410",
    ]


def test_stops_at_max_results() -> None:
    recorder = Recorder("page1.xml", "page1.xml")
    batch = make_source(recorder, max_results=3).fetch(SINCE)
    assert len(recorder.requests) == 1
    assert recorder.requests[0].url.params["max_results"] == "3"
    assert len(batch.items) == 3


def test_throttle_called_between_pages() -> None:
    throttle = CountingThrottle()
    make_source(Recorder("page1.xml", "page2.xml"), throttle=throttle).fetch(SINCE)
    assert throttle.calls == 2


def test_item_fields() -> None:
    item = make_source(Recorder("page1.xml")).fetch(SINCE).items[0]
    assert item.id == "arxiv:2610.12427"
    assert item.kind == "paper"
    assert item.title == "FastBench: Can Streaming VLMs Perceive High-Dynamic Real-World Streams?"
    assert "\n" not in item.title
    assert item.tags == ("cs.CL", "cs.CV")
    assert item.authors[0] == "Yuxuan Hu"
    assert item.published_at == datetime(2026, 10, 8, 17, 55, 20, tzinfo=UTC)
    assert item.sightings[0].source_type == "arxiv"
    assert item.first_seen == NOW


def test_empty_feed_returns_empty_batch() -> None:
    assert make_source(Recorder("empty.xml")).fetch(SINCE).items == ()


class ScriptedArxiv:
    """Serves pages in order; `None` stands for a 429 answer."""

    def __init__(self, *pages: str | None) -> None:
        self.pages = list(pages)
        self.requests = 0

    def __call__(self, _request: httpx.Request) -> httpx.Response:
        self.requests += 1
        page = self.pages.pop(0) if self.pages else "empty.xml"
        if page is None:
            return httpx.Response(429)
        return httpx.Response(200, content=(FIXTURES / page).read_bytes())


def scripted_source(script: ScriptedArxiv, sleeps: list[float], max_retries: int) -> ArxivSource:
    config = ArxivSourceConfig(name="arxiv", type="arxiv", categories=("cs.CL",))
    client = httpx.Client(transport=httpx.MockTransport(script))
    throttle = Throttle(0, sleep=sleeps.append, max_retries=max_retries)
    return ArxivSource(config, client, lambda: NOW, throttle)


def test_rate_limited_page_is_retried() -> None:
    sleeps: list[float] = []
    script = ScriptedArxiv(None, "page1.xml", "page2.xml")
    batch = scripted_source(script, sleeps, max_retries=3).fetch(SINCE)
    assert len(batch.items) == 3
    assert batch.partial_error is None
    assert sleeps == [10.0]


def test_pages_read_before_a_lasting_failure_are_kept() -> None:
    script = ScriptedArxiv("page1.xml", None, None)
    batch = scripted_source(script, [], max_retries=1).fetch(SINCE)
    assert [i.id for i in batch.items] == [
        "arxiv:2610.12427",
        "arxiv:2610.12417",
        "arxiv:2610.12410",
    ]
    assert batch.partial_error is not None
    assert "429" in batch.partial_error


def test_failure_on_first_page_still_raises() -> None:
    script = ScriptedArxiv(None, None)
    with pytest.raises(SourceUnavailableError):
        scripted_source(script, [], max_retries=1).fetch(SINCE)
