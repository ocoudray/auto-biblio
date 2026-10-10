import json

import httpx
import pytest
from pydantic import SecretStr

from auto_biblio.domain.errors import SourcePayloadError, SourceUnavailableError
from auto_biblio.sources._http import Throttle
from auto_biblio.sources.refresh import GithubStarsClient, HfUpvotesClient


def graphql_client(
    requests: list[dict[str, str]], status: int = 200, body: object = None
) -> GithubStarsClient:
    def handler(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)["query"]
        requests.append({"query": query, "auth": request.headers["Authorization"]})
        if body is not None:
            return httpx.Response(status, json=body)
        count = query.count("repository(")
        data: dict[str, dict[str, int] | None] = {
            f"r{i}": {"stargazerCount": i} for i in range(count)
        }
        data["r1"] = None  # not found
        return httpx.Response(status, json={"data": data, "errors": [{"type": "NOT_FOUND"}]})

    return GithubStarsClient(httpx.Client(transport=httpx.MockTransport(handler)), SecretStr("t"))


def test_graphql_batches_of_100() -> None:
    requests: list[dict[str, str]] = []
    repos = [f"o/r{i}" for i in range(150)]
    stars = graphql_client(requests).stars(repos)
    assert len(requests) == 2
    assert requests[0]["query"].count("repository(") == 100
    assert requests[0]["auth"] == "Bearer t"
    assert stars["o/r0"] == 0
    assert stars["o/r2"] == 2
    assert stars["o/r100"] == 0


def test_missing_repo_absent() -> None:
    stars = graphql_client([]).stars(["a/b", "c/d"])
    assert "c/d" not in stars


def test_invalid_names_skipped() -> None:
    requests: list[dict[str, str]] = []
    graphql_client(requests).stars(['a/b"}', "x/y"])
    assert '"x"' in requests[0]["query"]
    assert "b\\" not in requests[0]["query"]


def test_graphql_http_error() -> None:
    with pytest.raises(SourceUnavailableError, match="HTTP 502"):
        graphql_client([], status=502, body={}).stars(["a/b"])


def test_graphql_without_data() -> None:
    with pytest.raises(SourcePayloadError):
        graphql_client([], body={"errors": [{"message": "bad"}]}).stars(["a/b"])


def test_graphql_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        message = "down"
        raise httpx.ConnectError(message, request=request)

    client = GithubStarsClient(httpx.Client(transport=httpx.MockTransport(handler)), SecretStr("t"))
    with pytest.raises(SourceUnavailableError):
        client.stars(["a/b"])


def hf_client(status: int, body: object) -> HfUpvotesClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return HfUpvotesClient(httpx.Client(transport=httpx.MockTransport(handler)), Throttle(0))


def test_hf_upvotes() -> None:
    assert hf_client(200, {"id": "2410.1", "upvotes": 42}).upvotes("2410.1") == 42


def test_hf_404_none() -> None:
    assert hf_client(404, {}).upvotes("2410.1") is None


def test_hf_500_raises() -> None:
    with pytest.raises(SourceUnavailableError):
        hf_client(500, {}).upvotes("2410.1")
