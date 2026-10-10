from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from builders import NOW
from pydantic import SecretStr

from auto_biblio.domain.errors import SourcePayloadError, SourceUnavailableError
from auto_biblio.repo_config.sources import GithubReleasesSourceConfig, GithubSearchSourceConfig
from auto_biblio.sources._http import Throttle
from auto_biblio.sources.github import GithubReleasesSource, GithubSearchSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "github"


def client_for(fixture: str, requests: list[httpx.Request]) -> httpx.Client:
    body = (FIXTURES / fixture).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def search_source(
    requests: list[httpx.Request], token: SecretStr | None = None, fixture: str = "search.json"
) -> GithubSearchSource:
    config = GithubSearchSourceConfig(
        name="github-rising", type="github_search", topics=("llm", "agents")
    )
    return GithubSearchSource(
        config, client_for(fixture, requests), lambda: NOW, Throttle(0), token=token
    )


def releases_source(
    requests: list[httpx.Request], repos: tuple[str, ...] = ("astral-sh/uv",)
) -> GithubReleasesSource:
    config = GithubReleasesSourceConfig(name="github-releases", type="github_releases")
    client = client_for("releases.json", requests)
    return GithubReleasesSource(config, repos, client, lambda: NOW, Throttle(0), token=None)


def test_search_one_query_per_topic() -> None:
    requests: list[httpx.Request] = []
    search_source(requests).fetch(datetime(2000, 1, 1, tzinfo=UTC))
    queries = [r.url.params["q"] for r in requests]
    assert queries == [
        "topic:llm created:>2026-09-10 stars:>50",
        "topic:agents created:>2026-09-10 stars:>50",
    ]
    params = requests[0].url.params
    assert (params["sort"], params["order"], params["per_page"]) == ("stars", "desc", "100")
    assert requests[0].headers["Accept"] == "application/vnd.github+json"
    assert "Authorization" not in requests[0].headers


def test_search_auth_header_when_token() -> None:
    requests: list[httpx.Request] = []
    search_source(requests, SecretStr("ghp_x")).fetch(NOW)
    assert requests[0].headers["Authorization"] == "Bearer ghp_x"


def test_search_items_and_stars_signal() -> None:
    batch = search_source([]).fetch(NOW)
    item = batch.items[0]
    assert item.id == "gh:affaan-m/ecc"
    assert item.kind == "repo"
    assert item.title == "affaan-m/ECC"
    assert item.summary is not None
    assert "llm" in item.tags
    assert item.published_at == datetime(2026, 1, 18, 0, 51, 51, tzinfo=UTC)
    assert item.sightings[0].source_type == "github_search"
    signal = batch.signals[0]
    assert (signal.item_id, signal.kind, signal.value) == ("gh:affaan-m/ecc", "gh_stars", 276168)


def test_search_dedups_repo_across_topics() -> None:
    batch = search_source([]).fetch(NOW)
    assert len(batch.items) == 3
    assert len(batch.signals) == 3


def test_search_malformed_payload() -> None:
    with pytest.raises(SourcePayloadError):
        search_source([], fixture="releases.json").fetch(NOW)


def test_releases_filters_since_and_links_repo() -> None:
    requests: list[httpx.Request] = []
    batch = releases_source(requests).fetch(datetime(2026, 10, 5, tzinfo=UTC))
    assert requests[0].url.path == "/repos/astral-sh/uv/releases"
    assert requests[0].url.params["per_page"] == "30"
    assert [i.id for i in batch.items] == ["gh:astral-sh/uv@0.13.0", "gh:astral-sh/uv@0.12.24"]
    item = batch.items[0]
    assert item.kind == "release"
    assert item.links == ("gh:astral-sh/uv",)
    assert item.title == "astral-sh/uv 0.13.0"
    assert item.summary is not None
    assert len(item.summary) == 2000
    assert item.sightings[0].source_type == "github_releases"


def test_releases_no_repos_returns_empty_batch() -> None:
    requests: list[httpx.Request] = []
    assert releases_source(requests, repos=()).fetch(NOW).items == ()
    assert requests == []


def test_releases_skip_missing_repo() -> None:
    body = (FIXTURES / "releases.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/gone/repo/releases":
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, content=body)

    config = GithubReleasesSourceConfig(name="github-releases", type="github_releases")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = GithubReleasesSource(
        config, ("gone/repo", "astral-sh/uv"), client, lambda: NOW, Throttle(0), token=None
    )
    items = source.fetch(datetime(2026, 10, 5, tzinfo=UTC)).items
    assert [i.id for i in items] == ["gh:astral-sh/uv@0.13.0", "gh:astral-sh/uv@0.12.24"]


def test_releases_other_errors_fail_the_source() -> None:
    config = GithubReleasesSourceConfig(name="github-releases", type="github_releases")
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    source = GithubReleasesSource(
        config, ("astral-sh/uv",), client, lambda: NOW, Throttle(0), token=None
    )
    with pytest.raises(SourceUnavailableError, match="503"):
        source.fetch(NOW)
