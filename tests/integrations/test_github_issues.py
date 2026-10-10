import json

import httpx
import pytest
from pydantic import SecretStr

from auto_biblio.domain.errors import SourceUnavailableError
from auto_biblio.integrations.github_issues import GithubIssues


def issue(number: int, **extra: object) -> dict[str, object]:
    return {
        "number": number,
        "title": f"👍 gh:o/r{number}",
        "created_at": "2026-10-09T10:00:00Z",
    } | extra


def client(handler: httpx.MockTransport) -> GithubIssues:
    return GithubIssues(httpx.Client(transport=handler), "me/data", SecretStr("tok"))


def test_pagination_and_pull_requests_skipped() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[issue(3)])
        link = '<https://api.github.com/repos/me/data/issues?page=2>; rel="next"'
        return httpx.Response(
            200, json=[issue(1), issue(2, pull_request={"url": "x"})], headers={"Link": link}
        )

    issues = client(httpx.MockTransport(handler)).open_feedback()
    assert [i.number for i in issues] == [1, 3]
    assert seen[0].url.params["labels"] == "feedback"
    assert seen[0].headers["Authorization"] == "Bearer tok"
    assert len(seen) == 2


def test_write_calls() -> None:
    calls: list[tuple[str, str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={})

    issues = client(httpx.MockTransport(handler))
    issues.comment(4, "hi")
    issues.add_label(4, "feedback-invalid")
    issues.close(4)
    assert calls == [
        ("POST", "/repos/me/data/issues/4/comments", {"body": "hi"}),
        ("POST", "/repos/me/data/issues/4/labels", {"labels": ["feedback-invalid"]}),
        ("PATCH", "/repos/me/data/issues/4", {"state": "closed", "state_reason": "completed"}),
    ]


def test_write_errors() -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={})

    with pytest.raises(SourceUnavailableError, match="HTTP 403"):
        client(httpx.MockTransport(refuse)).close(1)

    def down(request: httpx.Request) -> httpx.Response:
        message = "down"
        raise httpx.ConnectError(message, request=request)

    with pytest.raises(SourceUnavailableError, match="failed"):
        client(httpx.MockTransport(down)).comment(1, "x")
