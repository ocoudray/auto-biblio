import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from auto_biblio.domain.errors import ExtractionError
from auto_biblio.extract.fetchers import ArticleFetcher, ArxivFetcher, RepoFetcher
from auto_biblio.sources._http import Throttle

FIXTURES = Path(__file__).parent.parent / "fixtures" / "extract"
Routes = dict[str, tuple[int, bytes]]


def client(routes: Routes, seen: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        status, body = routes.get(str(request.url), (404, b""))
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def arxiv(routes: Routes) -> ArxivFetcher:
    return ArxivFetcher(client(routes), Throttle(0))


def test_arxiv_html() -> None:
    html = (FIXTURES / "arxiv.html").read_bytes()
    text = arxiv({"https://arxiv.org/html/2410.12345": (200, html)}).fetch("2410.12345")
    assert "checkpoints every tool call" in text
    assert "https://github.com/acme/durable-agents" in text
    assert "arXiv navigation menu" not in text


def test_arxiv_pdf_fallback() -> None:
    pdf = (FIXTURES / "paper.pdf").read_bytes()
    routes = {"https://arxiv.org/pdf/2410.12345": (200, pdf)}
    assert "Durable agents keep their state" in arxiv(routes).fetch("2410.12345")


def test_arxiv_all_fail() -> None:
    routes = {"https://arxiv.org/pdf/2410.12345": (200, b"not a pdf")}
    with pytest.raises(ExtractionError, match=r"HTML: .*PDF: .*unreadable"):
        arxiv(routes).fetch("2410.12345")


def test_arxiv_empty_pdf_text() -> None:
    pdf = (
        (FIXTURES / "paper.pdf")
        .read_bytes()
        .replace(b"(Durable agents keep their state across crashes.)", b"()")
    )
    with pytest.raises(ExtractionError, match="PDF"):
        arxiv({"https://arxiv.org/pdf/1": (200, pdf)}).fetch("1")


def repo(routes: Routes, seen: list[httpx.Request] | None = None) -> RepoFetcher:
    return RepoFetcher(client(routes, seen), SecretStr("tok"))


BASE = "https://api.github.com/repos/o/r"


def test_repo_readme_and_release() -> None:
    seen: list[httpx.Request] = []
    release = json.dumps({"tag_name": "v2.0", "body": "Breaking: new API."}).encode()
    routes = {f"{BASE}/readme": (200, b"# R\n\nA tool."), f"{BASE}/releases/latest": (200, release)}
    text = repo(routes, seen).fetch("o/r")
    assert text == "# R\n\nA tool.\n\n## Latest release v2.0\n\nBreaking: new API."
    assert seen[0].headers["Authorization"] == "Bearer tok"


@pytest.mark.parametrize(
    "release",
    [None, b"not json", b"[]", json.dumps({"tag_name": "v1", "body": ""}).encode()],
)
def test_repo_without_usable_release(release: bytes | None) -> None:
    routes = {f"{BASE}/readme": (200, b"Readme")}
    if release is not None:
        routes[f"{BASE}/releases/latest"] = (200, release)
    assert RepoFetcher(client(routes), None).fetch("o/r") == "Readme"


def test_repo_empty_readme() -> None:
    with pytest.raises(ExtractionError, match="empty README"):
        repo({f"{BASE}/readme": (200, b"  ")}).fetch("o/r")


def test_article() -> None:
    html = (FIXTURES / "blog.html").read_bytes()
    text = ArticleFetcher(client({"https://blog.example/uv": (200, html)})).fetch(
        "https://blog.example/uv"
    )
    assert "pip-tools to uv" in text
    assert "Footer" not in text


@pytest.mark.parametrize(
    "routes", [{}, {"https://blog.example/uv": (200, b"<html><p>Login</p></html>")}]
)
def test_article_failures(routes: Routes) -> None:
    with pytest.raises(ExtractionError):
        ArticleFetcher(client(routes)).fetch("https://blog.example/uv")
