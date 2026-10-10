from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from builders import NOW

from auto_biblio.domain.errors import SourcePayloadError
from auto_biblio.repo_config.sources import HfPapersSourceConfig
from auto_biblio.sources._http import Throttle
from auto_biblio.sources.hf_papers import HfPapersSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "hf_papers"


def make_source(fixture: str, requests: list[httpx.Request] | None = None) -> HfPapersSource:
    body = (FIXTURES / fixture).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, content=body)

    config = HfPapersSourceConfig(name="hf-papers", type="hf_papers")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HfPapersSource(config, client, lambda: NOW, Throttle(0))


def test_one_request_per_day_since() -> None:
    requests: list[httpx.Request] = []
    make_source("day.json", requests).fetch(NOW - timedelta(days=2))
    assert [r.url.params["date"] for r in requests] == ["2026-10-08", "2026-10-09", "2026-10-10"]
    assert requests[0].url.path == "/api/daily_papers"


def test_items_are_deduplicated_across_days() -> None:
    batch = make_source("day.json").fetch(NOW - timedelta(days=2))
    assert [i.id for i in batch.items] == [
        "arxiv:2610.09823",
        "arxiv:2610.04299",
        "arxiv:2610.08077",
    ]
    assert len(batch.signals) == 3


def test_item_and_links() -> None:
    first, second, _ = make_source("day.json").fetch(NOW).items
    assert first.kind == "paper"
    assert first.links == ("gh:lins-lab/ultratext_bench",)
    assert first.authors[0] != ""
    assert first.published_at == datetime(2026, 10, 7, tzinfo=UTC)
    assert str(first.url) == "https://huggingface.co/papers/2610.09823"
    assert first.sightings[0].source_type == "hf_papers"
    assert second.links == ()


def test_upvotes_signal() -> None:
    signal = make_source("day.json").fetch(NOW).signals[0]
    assert (signal.item_id, signal.kind, signal.value) == ("arxiv:2610.09823", "hf_upvotes", 151)
    assert signal.observed_at == NOW
    assert signal.source == "hf-papers"


def test_malformed_raises_payload_error() -> None:
    with pytest.raises(SourcePayloadError) as excinfo:
        make_source("malformed.json").fetch(NOW)
    assert "no paper here" in excinfo.value.payload_excerpt
