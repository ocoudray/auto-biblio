from pathlib import Path

import httpx
import pytest
from builders import make_item
from pydantic import SecretStr

from auto_biblio.domain.errors import ContextFetchError
from auto_biblio.domain.models import Item
from auto_biblio.sources.context import ContextFetcher

FIXTURES = Path(__file__).parent.parent / "fixtures" / "context"


def fetcher(
    routes: dict[str, tuple[int, str]],
    seen: list[httpx.Request] | None = None,
    max_words: int = 150,
) -> ContextFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        status, body = routes.get(str(request.url), (404, ""))
        return httpx.Response(status, text=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ContextFetcher(client, max_words, SecretStr("tok"))


def blog_item(url: str = "https://blog.example/post") -> Item:
    item = make_item(item_id="url:abc", source_type="hackernews", summary=None, kind="discussion")
    return item.model_copy(update={"url": url})


def test_og_description() -> None:
    page = (FIXTURES / "page.html").read_text()
    snippet = fetcher({"https://blog.example/post": (200, page)}).fetch(blog_item())
    assert snippet == "A small library for durable agent workflows."


def test_meta_description_fallback() -> None:
    page = '<html><head><meta name="description" content="Only plain."></head></html>'
    assert fetcher({"https://blog.example/post": (200, page)}).fetch(blog_item()) == "Only plain."


def test_github_readme_stripped() -> None:
    seen: list[httpx.Request] = []
    readme = (FIXTURES / "readme.md").read_text()
    routes = {"https://api.github.com/repos/docling-project/docling/readme": (200, readme)}
    item = make_item(
        item_id="gh:docling-project/docling", source_type="github_search", summary=None, kind="repo"
    )
    snippet = fetcher(routes, seen).fetch(item)
    assert snippet == "Docling Docling parses documents and exports them to Markdown."
    assert seen[0].headers["Authorization"] == "Bearer tok"
    assert seen[0].headers["Accept"] == "application/vnd.github.raw"


def test_hf_model_card() -> None:
    card = "---\nlicense: mit\n---\n# Model\nA tiny OCR model."
    routes = {"https://huggingface.co/org/ocr-small/raw/main/README.md": (200, card)}
    snippet = fetcher(routes).fetch(blog_item("https://huggingface.co/org/ocr-small"))
    assert snippet == "Model A tiny OCR model."


def test_truncated_to_max_words() -> None:
    page = '<meta property="og:description" content="one two three four">'
    assert (
        fetcher({"https://blog.example/post": (200, page)}, max_words=2).fetch(blog_item())
        == "one two"
    )


def test_http_error_skipped(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ContextFetchError, match="HTTP 404"):
        fetcher({}).fetch(blog_item())
    assert fetcher({}).fetch_many([blog_item()]) == {}
    assert "no context for url:abc" in caplog.text


def test_empty_page_skipped() -> None:
    routes = {"https://blog.example/post": (200, "<html></html>")}
    with pytest.raises(ContextFetchError, match="no description"):
        fetcher(routes).fetch(blog_item())


def test_fetch_many_keeps_successes() -> None:
    page = '<meta property="og:description" content="ok">'
    routes = {"https://blog.example/a": (200, page)}
    good = blog_item("https://blog.example/a")
    bad = blog_item("https://blog.example/b").model_copy(update={"id": "url:def"})
    assert fetcher(routes).fetch_many([good, bad]) == {"url:abc": "ok"}
